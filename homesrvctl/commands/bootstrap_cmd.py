from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.bootstrap import (
    assess_bootstrap,
    provision_bootstrap_runtime,
    provision_bootstrap_tunnel,
    provision_bootstrap_wiring,
)
from homesrvctl.cloudflared import CloudflaredConfigError
from homesrvctl.config import default_config_path
from homesrvctl.utils import info, success, warn, with_json_schema

bootstrap_cli = typer.Typer(help="Assess and stage fresh-host bootstrap work.")


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


@bootstrap_cli.command("tunnel")
def bootstrap_tunnel(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Read homesrvctl config from a custom path instead of the default user config location.",
    ),
    account_id: str | None = typer.Option(
        None,
        "--account-id",
        help="Cloudflare account ID for the shared host tunnel. Required when no readable local cloudflared credentials exist yet.",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Create or reuse a tunnel with this name instead of the current config tunnel reference.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing local bootstrap tunnel material when needed."),
    json_output: bool = typer.Option(False, "--json", help="Print the tunnel provisioning result as JSON."),
) -> None:
    """Create or reuse the shared Cloudflare tunnel and write local bootstrap material."""
    target_path = path or default_config_path()
    try:
        provisioned = provision_bootstrap_tunnel(
            target_path,
            account_id=account_id,
            tunnel_name=name,
            force=force,
        )
    except (typer.BadParameter, CloudflaredConfigError) as exc:
        payload = with_json_schema(
            {
                "action": "bootstrap_tunnel",
                "ok": False,
                "config_path": str(target_path),
                "error": str(exc),
            }
        )
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1) from exc
        raise

    payload = with_json_schema(
        {
            "action": "bootstrap_tunnel",
            "ok": provisioned.ok,
            "created": provisioned.created,
            "reused": provisioned.reused,
            "detail": provisioned.detail,
            "config_path": provisioned.config_path,
            "account_id": provisioned.account_id,
            "requested_tunnel": provisioned.requested_tunnel,
            "tunnel": {
                "id": provisioned.tunnel_id,
                "name": provisioned.tunnel_name,
                "config_src": provisioned.config_src,
                "status": provisioned.status,
            },
            "credentials_path": provisioned.credentials_path,
            "cloudflared_config_path": provisioned.cloudflared_config_path,
            "config_updated": provisioned.config_updated,
            "credentials_written": provisioned.credentials_written,
            "cloudflared_config_written": provisioned.cloudflared_config_written,
            "next_steps": provisioned.next_steps,
        }
    )

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    success(provisioned.detail)
    info(f"account id: {provisioned.account_id}")
    info(f"requested tunnel: {provisioned.requested_tunnel}")
    info(f"configured tunnel id: {provisioned.tunnel_id}")
    info(f"credentials path: {provisioned.credentials_path}")
    info(f"cloudflared config path: {provisioned.cloudflared_config_path}")
    if provisioned.next_steps:
        typer.echo("")
        info("next steps:")
        for step in provisioned.next_steps:
            typer.echo(f"- {step}")


@bootstrap_cli.command("runtime")
def bootstrap_runtime(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Read homesrvctl config from a custom path instead of the default user config location.",
    ),
    operator_user: str | None = typer.Option(
        None,
        "--operator-user",
        help="Non-root operator account to add to the homesrvctl and docker groups. Defaults to SUDO_USER or USER when available.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite the baseline Traefik compose file when it already exists."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the planned host runtime changes without applying them."),
    json_output: bool = typer.Option(False, "--json", help="Print the runtime bootstrap result as JSON."),
) -> None:
    """Install and converge the local runtime baseline for the bootstrap target."""
    target_path = path or default_config_path()
    try:
        provisioned = provision_bootstrap_runtime(
            target_path,
            operator_user=operator_user,
            force=force,
            dry_run=dry_run,
        )
    except (typer.BadParameter, CloudflaredConfigError) as exc:
        payload = with_json_schema(
            {
                "action": "bootstrap_runtime",
                "ok": False,
                "dry_run": dry_run,
                "config_path": str(target_path),
                "error": str(exc),
            }
        )
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1) from exc
        raise

    payload = with_json_schema(
        {
            "action": "bootstrap_runtime",
            "ok": provisioned.ok,
            "dry_run": provisioned.dry_run,
            "detail": provisioned.detail,
            "operator_user": provisioned.operator_user,
            "config_path": provisioned.config_path,
            "docker_network": provisioned.docker_network,
            "homesrvctl_group": provisioned.homesrvctl_group,
            "package_commands": provisioned.package_commands,
            "directories": provisioned.directories,
            "groups": provisioned.groups,
            "network": provisioned.network,
            "traefik": provisioned.traefik,
            "next_steps": provisioned.next_steps,
        }
    )

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    if provisioned.dry_run:
        info(provisioned.detail)
    else:
        success(provisioned.detail)
    info(f"operator user: {provisioned.operator_user or '<none>'}")
    info(f"docker network: {provisioned.docker_network}")
    info(f"Traefik compose: {provisioned.traefik['compose_path']}")
    if provisioned.next_steps:
        typer.echo("")
        info("next steps:")
        for step in provisioned.next_steps:
            typer.echo(f"- {step}")


@bootstrap_cli.command("wiring")
def bootstrap_wiring(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Read homesrvctl config from a custom path instead of the default user config location.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing local config or systemd wiring when needed."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the planned wiring changes without applying them."),
    json_output: bool = typer.Option(False, "--json", help="Print the wiring result as JSON."),
) -> None:
    """Converge the shared cloudflared config path and systemd wiring."""
    target_path = path or default_config_path()
    try:
        provisioned = provision_bootstrap_wiring(target_path, dry_run=dry_run, force=force)
    except (typer.BadParameter, CloudflaredConfigError) as exc:
        payload = with_json_schema(
            {
                "action": "bootstrap_wiring",
                "ok": False,
                "dry_run": dry_run,
                "config_path": str(target_path),
                "error": str(exc),
            }
        )
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1) from exc
        raise

    payload = with_json_schema(
        {
            "action": "bootstrap_wiring",
            "ok": provisioned.ok,
            "dry_run": provisioned.dry_run,
            "detail": provisioned.detail,
            "config_path": provisioned.config_path,
            "config_created": provisioned.config_created,
            "config_updated": provisioned.config_updated,
            "cloudflared_config_path": provisioned.cloudflared_config_path,
            "credentials_path": provisioned.credentials_path,
            "cloudflared_config_written": provisioned.cloudflared_config_written,
            "credentials_written": provisioned.credentials_written,
            "systemd": {
                "mode": provisioned.systemd_mode,
                "path": provisioned.systemd_path,
                "written": provisioned.systemd_written,
            },
            "service_enabled": provisioned.service_enabled,
            "next_steps": provisioned.next_steps,
        }
    )

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return

    if provisioned.dry_run:
        info(provisioned.detail)
    else:
        success(provisioned.detail)
    info(f"config path: {provisioned.config_path}")
    info(f"cloudflared config path: {provisioned.cloudflared_config_path}")
    info(f"credentials path: {provisioned.credentials_path}")
    info(f"systemd {provisioned.systemd_mode}: {provisioned.systemd_path}")
    if provisioned.next_steps:
        typer.echo("")
        info("next steps:")
        for step in provisioned.next_steps:
            typer.echo(f"- {step}")
