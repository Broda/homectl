from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.bootstrap import assess_bootstrap
from homesrvctl.utils import info, success, warn, with_json_schema

bootstrap_cli = typer.Typer(help="Assess fresh-host bootstrap readiness.")


@bootstrap_cli.command("assess")
def bootstrap_assess(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Read homesrvctl config from a custom path instead of the default user config location.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the bootstrap assessment as JSON."),
) -> None:
    """Assess how close this host is to the planned fresh-bootstrap target."""
    assessment = assess_bootstrap(path, quiet=json_output)
    payload = with_json_schema(
        {
            "action": "bootstrap_assess",
            "ok": assessment.ok,
            "bootstrap_state": assessment.bootstrap_state,
            "bootstrap_ready": assessment.bootstrap_ready,
            "host_supported": assessment.host_supported,
            "detail": assessment.detail,
            "config_path": assessment.config_path,
            "os": assessment.os,
            "systemd": assessment.systemd,
            "packages": assessment.packages,
            "services": assessment.services,
            "config": assessment.config,
            "network": assessment.network,
            "cloudflare": assessment.cloudflare,
            "issues": assessment.issues,
            "next_steps": assessment.next_steps,
        }
    )

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if assessment.bootstrap_state == "ready":
            success(assessment.detail)
        elif assessment.bootstrap_state == "unsupported":
            warn(assessment.detail)
        else:
            info(assessment.detail)

        info(f"bootstrap state: {assessment.bootstrap_state}")
        info(f"host supported: {'yes' if assessment.host_supported else 'no'}")
        info(f"os: {assessment.os.get('pretty_name', 'unknown')}")
        info(f"config path: {assessment.config_path}")
        info(f"docker: {'yes' if assessment.packages.get('docker') else 'no'}")
        info(f"docker compose: {'yes' if assessment.packages.get('docker_compose') else 'no'}")
        info(f"cloudflared: {'yes' if assessment.packages.get('cloudflared') else 'no'}")
        info(f"Traefik running: {'yes' if assessment.services.get('traefik_running') else 'no'}")
        info(f"cloudflared active: {'yes' if assessment.services.get('cloudflared_active') else 'no'}")
        network_exists = assessment.network.get("exists")
        info(
            "docker network ready: "
            f"{'yes' if network_exists else 'no' if network_exists is False else 'unknown'}"
        )
        token_present = assessment.cloudflare.get("token_present")
        info(f"Cloudflare token present: {'yes' if token_present else 'no'}")
        api_reachable = assessment.cloudflare.get("api_reachable")
        info(
            "Cloudflare API reachable: "
            f"{'yes' if api_reachable else 'no' if api_reachable is False else 'unknown'}"
        )
        if assessment.issues:
            typer.echo("")
            warn(f"issues: {len(assessment.issues)}")
            for issue in assessment.issues:
                typer.echo(f"- {issue}")
        if assessment.next_steps:
            typer.echo("")
            info("next steps:")
            for step in assessment.next_steps:
                typer.echo(f"- {step}")

    if not assessment.ok:
        raise typer.Exit(code=1)
