from __future__ import annotations

import json
from pathlib import Path

import typer

from homectl.config import load_config
from homectl.shell import require_success, run_command
from homectl.utils import info, success, validate_hostname, warn


def _resolve_stack_dir(hostname: str) -> Path:
    config = load_config()
    valid_hostname = validate_hostname(hostname)
    stack_dir = config.hostname_dir(valid_hostname)
    compose_file = stack_dir / "docker-compose.yml"
    if not stack_dir.exists():
        raise typer.BadParameter(f"hostname directory does not exist: {stack_dir}")
    if not compose_file.exists():
        raise typer.BadParameter(f"missing docker-compose.yml: {compose_file}")
    return stack_dir


def up(
    hostname: str = typer.Argument(..., help="Hostname to bring up."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the compose command without running it."),
) -> None:
    """Run docker compose up -d for a hostname."""
    stack_dir = _resolve_stack_dir(hostname)
    result = run_command(["docker", "compose", "up", "-d"], cwd=stack_dir, dry_run=dry_run)
    require_success(result, f"docker compose up for {hostname}")
    success(f"{'Would bring up' if dry_run else 'Started'} stack for {hostname}")


def down(
    hostname: str = typer.Argument(..., help="Hostname to bring down."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the compose command without running it."),
) -> None:
    """Run docker compose down for a hostname."""
    stack_dir = _resolve_stack_dir(hostname)
    result = run_command(["docker", "compose", "down"], cwd=stack_dir, dry_run=dry_run)
    require_success(result, f"docker compose down for {hostname}")
    success(f"{'Would stop' if dry_run else 'Stopped'} stack for {hostname}")


def restart(
    hostname: str = typer.Argument(..., help="Hostname to restart."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the compose commands without running them."),
) -> None:
    """Restart a hostname stack by bringing it down and up again."""
    stack_dir = _resolve_stack_dir(hostname)
    for command, label in (
        (["docker", "compose", "down"], "docker compose down"),
        (["docker", "compose", "up", "-d"], "docker compose up"),
    ):
        result = run_command(command, cwd=stack_dir, dry_run=dry_run)
        require_success(result, f"{label} for {hostname}")
    success(f"{'Would restart' if dry_run else 'Restarted'} stack for {hostname}")


def list_sites() -> None:
    """List scaffolded hostnames under the configured sites root."""
    list_sites_with_format()


def list_sites_with_format(
    json_output: bool = typer.Option(False, "--json", help="Print the site list as JSON."),
) -> None:
    """List scaffolded hostnames under the configured sites root."""
    config = load_config()
    if not config.sites_root.exists():
        if json_output:
            payload = {
                "sites_root": str(config.sites_root),
                "ok": False,
                "sites": [],
                "error": f"Sites root does not exist: {config.sites_root}",
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            warn(f"Sites root does not exist: {config.sites_root}")
        raise typer.Exit(code=1)

    sites: list[dict[str, object]] = []
    for child in sorted(path for path in config.sites_root.iterdir() if path.is_dir()):
        compose_file = child / "docker-compose.yml"
        sites.append({"hostname": child.name, "compose": compose_file.exists()})

    if json_output:
        payload = {
            "sites_root": str(config.sites_root),
            "ok": True,
            "sites": sites,
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    if not sites:
        warn(f"No hostnames found under {config.sites_root}")
        return

    for site in sites:
        status = "compose=yes" if site["compose"] else "compose=no"
        info(f"{site['hostname']}\t{status}")


def doctor(
    hostname: str = typer.Argument(..., help="Hostname to diagnose."),
    json_output: bool = typer.Option(False, "--json", help="Print the doctor report as JSON."),
) -> None:
    """Diagnose one hostname stack and local Traefik routing."""
    from homectl.commands.validate_cmd import build_hostname_doctor_report

    config = load_config()
    valid_hostname = validate_hostname(hostname)
    results = build_hostname_doctor_report(config, valid_hostname)
    failures = [item for item in results if not item.ok]
    if json_output:
        payload = {
            "hostname": valid_hostname,
            "ok": not failures,
            "checks": [{"name": result.name, "ok": result.ok, "detail": result.detail} for result in results],
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        for result in results:
            symbol = "PASS" if result.ok else "FAIL"
            info(f"{symbol} {result.name}: {result.detail}")

    if failures:
        if not json_output:
            warn(f"Doctor found {len(failures)} issue(s) for {valid_hostname}")
        raise typer.Exit(code=1)

    if not json_output:
        success(f"Doctor checks passed for {valid_hostname}")
