from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.config import load_config, load_config_details
from homesrvctl.shell import require_success, run_command
from homesrvctl.utils import info, success, validate_hostname, warn, with_json_schema


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
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Run docker compose up -d for a hostname."""
    stack_dir = _resolve_stack_dir_for_output(hostname, json_output, "up", dry_run)
    command = ["docker", "compose", "up", "-d"]
    result = run_command(command, cwd=stack_dir, dry_run=dry_run, quiet=json_output)
    _emit_deploy_result(result, f"docker compose up for {hostname}", hostname, stack_dir, dry_run, json_output, "up")
    if not json_output:
        success(f"{'Would bring up' if dry_run else 'Started'} stack for {hostname}")


def down(
    hostname: str = typer.Argument(..., help="Hostname to bring down."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the compose command without running it."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Run docker compose down for a hostname."""
    stack_dir = _resolve_stack_dir_for_output(hostname, json_output, "down", dry_run)
    command = ["docker", "compose", "down"]
    result = run_command(command, cwd=stack_dir, dry_run=dry_run, quiet=json_output)
    _emit_deploy_result(result, f"docker compose down for {hostname}", hostname, stack_dir, dry_run, json_output, "down")
    if not json_output:
        success(f"{'Would stop' if dry_run else 'Stopped'} stack for {hostname}")


def restart(
    hostname: str = typer.Argument(..., help="Hostname to restart."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the compose commands without running them."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Restart a hostname stack by bringing it down and up again."""
    stack_dir = _resolve_stack_dir_for_output(hostname, json_output, "restart", dry_run)
    executed: list[dict[str, object]] = []
    for command, label in (
        (["docker", "compose", "down"], "docker compose down"),
        (["docker", "compose", "up", "-d"], "docker compose up"),
    ):
        result = run_command(command, cwd=stack_dir, dry_run=dry_run, quiet=json_output)
        if json_output and not result.ok:
            payload = _deploy_payload(
                hostname=hostname,
                stack_dir=stack_dir,
                action="restart",
                dry_run=dry_run,
                ok=False,
                commands=executed + [_command_result_to_dict(result)],
                error=result.stderr or result.stdout or f"{label} failed",
            )
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1)
        require_success(result, f"{label} for {hostname}")
        executed.append(_command_result_to_dict(result))
    if json_output:
        payload = _deploy_payload(
            hostname=hostname,
            stack_dir=stack_dir,
            action="restart",
            dry_run=dry_run,
            ok=True,
            commands=executed,
        )
        typer.echo(json.dumps(payload, indent=2))
        return
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
            payload = with_json_schema({
                "sites_root": str(config.sites_root),
                "ok": False,
                "sites": [],
                "error": f"Sites root does not exist: {config.sites_root}",
            })
            typer.echo(json.dumps(payload, indent=2))
        else:
            warn(f"Sites root does not exist: {config.sites_root}")
        raise typer.Exit(code=1)

    sites: list[dict[str, object]] = []
    for child in sorted(path for path in config.sites_root.iterdir() if path.is_dir()):
        compose_file = child / "docker-compose.yml"
        sites.append({"hostname": child.name, "compose": compose_file.exists()})

    if json_output:
        payload = with_json_schema({
            "sites_root": str(config.sites_root),
            "ok": True,
            "sites": sites,
        })
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
    from homesrvctl.commands.validate_cmd import build_hostname_doctor_report

    config, global_sources = load_config_details()
    valid_hostname = validate_hostname(hostname)
    results = build_hostname_doctor_report(config, valid_hostname, global_sources, quiet=json_output)
    failures = [item for item in results if not item.ok]
    if json_output:
        payload = with_json_schema({
            "hostname": valid_hostname,
            "ok": not failures,
            "checks": [{"name": result.name, "ok": result.ok, "detail": result.detail} for result in results],
        })
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


def _emit_deploy_result(
    result,
    action_label: str,
    hostname: str,
    stack_dir: Path,
    dry_run: bool,
    json_output: bool,
    action: str,
) -> None:
    if json_output and not result.ok:
        payload = _deploy_payload(
            hostname=hostname,
            stack_dir=stack_dir,
            action=action,
            dry_run=dry_run,
            ok=False,
            commands=[_command_result_to_dict(result)],
            error=result.stderr or result.stdout or f"{action_label} failed",
        )
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=1)
    require_success(result, action_label)
    if json_output:
        payload = _deploy_payload(
            hostname=hostname,
            stack_dir=stack_dir,
            action=action,
            dry_run=dry_run,
            ok=True,
            commands=[_command_result_to_dict(result)],
        )
        typer.echo(json.dumps(payload, indent=2))


def _deploy_payload(
    hostname: str,
    stack_dir: Path,
    action: str,
    dry_run: bool,
    ok: bool,
    commands: list[dict[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = with_json_schema({
        "hostname": hostname,
        "stack_dir": str(stack_dir),
        "action": action,
        "dry_run": dry_run,
        "ok": ok,
        "commands": commands,
    })
    if error:
        payload["error"] = error
    return payload


def _command_result_to_dict(result) -> dict[str, object]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _resolve_stack_dir_for_output(hostname: str, json_output: bool, action: str, dry_run: bool) -> Path:
    try:
        return _resolve_stack_dir(hostname)
    except typer.BadParameter as exc:
        if json_output:
            payload = _deploy_payload(
                hostname=hostname,
                stack_dir=Path(),
                action=action,
                dry_run=dry_run,
                ok=False,
                commands=[],
                error=str(exc),
            )
            payload["stack_dir"] = None
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1) from exc
        raise
