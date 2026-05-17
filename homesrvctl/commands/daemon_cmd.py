from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.services import daemon_systemd
from homesrvctl.services.daemon import DEFAULT_DAEMON_INTERVAL_SECONDS, get_daemon_status, run_daemon
from homesrvctl.state.db import default_state_db_path
from homesrvctl.utils import success, warn, with_json_schema

daemon_cli = typer.Typer(help="Run and inspect the read-only local observer daemon.")


@daemon_cli.command("run")
def daemon_run(
    interval_seconds: float = typer.Option(
        DEFAULT_DAEMON_INTERVAL_SECONDS,
        "--interval-seconds",
        min=1.0,
        help="Seconds to sleep between refresh cycles.",
    ),
    once: bool = typer.Option(False, "--once", help="Run one refresh cycle and exit."),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Read config from a custom path."),
    json_output: bool = typer.Option(False, "--json", help="Print the daemon result as JSON."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress per-cycle human output."),
) -> None:
    """Run the read-only local observer daemon."""
    if json_output and not once:
        typer.echo(
            json.dumps(
                with_json_schema(
                    {
                        "action": "daemon_run",
                        "ok": False,
                        "mode": "loop",
                        "error": "`--json` is only supported with `--once`",
                    }
                ),
                indent=2,
            )
        )
        raise typer.Exit(code=1)

    target_db_path = db_path or default_state_db_path()
    if not quiet and not json_output:
        typer.echo(f"Starting homesrvctl daemon: interval={interval_seconds:g}s db={target_db_path}")

    result = run_daemon(
        db_path=target_db_path,
        config_path=config_path,
        interval_seconds=interval_seconds,
        once=once,
        on_cycle=None if quiet or json_output else _print_cycle_result,
    )

    payload = {"action": "daemon_run", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if not quiet:
        success("Stopped homesrvctl daemon")
    if once and not result.ok:
        raise typer.Exit(code=1)


@daemon_cli.command("status")
def daemon_status(
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Inspect a custom systemd unit name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print daemon status as JSON."),
) -> None:
    """Show read-only daemon/cache status."""
    status = get_daemon_status(db_path=db_path or default_state_db_path())
    systemd_status = daemon_systemd.inspect_daemon_systemd(unit_name=unit_name)
    payload = {"action": "daemon_status", **status.to_dict(), **systemd_status.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not status.ok:
            raise typer.Exit(code=1)
        return

    if status.ok:
        success(
            "Daemon state: "
            f"db={status.db_path} initialized=yes stacks={status.stack_count} "
            f"cache_available={'yes' if status.cache_available else 'no'}"
        )
        typer.echo(
            "systemd: "
            f"installed={'yes' if systemd_status.unit_installed else 'no'} "
            f"active={systemd_status.active_state or 'unknown'} "
            f"enabled={systemd_status.enabled_state or 'unknown'}"
        )
        typer.echo(f"last_refresh_at: {status.last_refresh_at or 'N/A'}")
        typer.echo(f"daemon_heartbeat_at: {status.daemon_heartbeat_at or 'N/A'}")
        for issue in systemd_status.issues:
            typer.echo(f"- {issue}")
        return
    warn(f"Daemon state not ready: {status.db_path}")
    typer.echo(
        "systemd: "
        f"installed={'yes' if systemd_status.unit_installed else 'no'} "
        f"active={systemd_status.active_state or 'unknown'} "
        f"enabled={systemd_status.enabled_state or 'unknown'}"
    )
    for issue in status.issues:
        typer.echo(f"- {issue}")
    for issue in systemd_status.issues:
        typer.echo(f"- {issue}")
    raise typer.Exit(code=1)


@daemon_cli.command("install")
def daemon_install(
    interval_seconds: float = typer.Option(
        DEFAULT_DAEMON_INTERVAL_SECONDS,
        "--interval-seconds",
        min=1.0,
        help="Seconds to sleep between refresh cycles.",
    ),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Read config from a custom path."),
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Install a custom systemd unit name.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing unit file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the planned unit and commands without changing systemd."),
    now: bool = typer.Option(False, "--now", help="Enable and start the unit after installing it."),
    json_output: bool = typer.Option(False, "--json", help="Print install result as JSON."),
) -> None:
    """Install the read-only daemon as a systemd system service."""
    result = daemon_systemd.install_daemon_unit(
        unit_name=unit_name,
        interval_seconds=interval_seconds,
        db_path=db_path,
        config_path=config_path,
        force=force,
        dry_run=dry_run,
        now=now,
    )
    payload = {"action": "daemon_install", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if result.unit_content and dry_run:
        typer.echo(result.unit_content)
        _print_planned_commands(result.commands)
    if result.ok:
        if dry_run:
            success(f"Would install homesrvctl daemon unit: {result.unit_path}")
        else:
            success(f"Installed homesrvctl daemon unit: {result.unit_path}")
        if result.started:
            success("Started homesrvctl daemon service")
        else:
            typer.echo(f"Run `sudo systemctl enable --now {result.unit_name}` to start at boot.")
        return
    warn(f"Daemon install failed: {result.error or 'unknown error'}")
    raise typer.Exit(code=1)


@daemon_cli.command("uninstall")
def daemon_uninstall(
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Remove a custom systemd unit name.",
    ),
    force: bool = typer.Option(False, "--force", help="Stop and disable the unit before removing it."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned changes without modifying systemd."),
    json_output: bool = typer.Option(False, "--json", help="Print uninstall result as JSON."),
) -> None:
    """Uninstall the systemd unit without deleting local state."""
    result = daemon_systemd.uninstall_daemon_unit(unit_name=unit_name, force=force, dry_run=dry_run)
    payload = {"action": "daemon_uninstall", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if result.ok:
        if dry_run:
            success(f"Would remove homesrvctl daemon unit: {result.unit_path}")
            _print_planned_commands(result.commands)
        elif result.removed:
            success(f"Removed homesrvctl daemon unit: {result.unit_path}")
        else:
            warn(f"Daemon unit was not installed: {result.unit_path}")
        typer.echo("State database left intact.")
        return
    warn(f"Daemon uninstall failed: {result.error or 'unknown error'}")
    raise typer.Exit(code=1)


@daemon_cli.command("start")
def daemon_start(
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Start a custom systemd unit name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print command result as JSON."),
) -> None:
    """Start the systemd-managed read-only daemon."""
    _run_systemd_action("start", unit_name=unit_name, json_output=json_output)


@daemon_cli.command("stop")
def daemon_stop(
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Stop a custom systemd unit name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print command result as JSON."),
) -> None:
    """Stop the systemd-managed read-only daemon."""
    _run_systemd_action("stop", unit_name=unit_name, json_output=json_output)


@daemon_cli.command("restart")
def daemon_restart(
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Restart a custom systemd unit name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print command result as JSON."),
) -> None:
    """Restart the systemd-managed read-only daemon."""
    _run_systemd_action("restart", unit_name=unit_name, json_output=json_output)


@daemon_cli.command("logs")
def daemon_logs(
    unit_name: str = typer.Option(
        daemon_systemd.DEFAULT_DAEMON_UNIT_NAME,
        "--unit-name",
        help="Read logs for a custom systemd unit name.",
    ),
    lines: int = typer.Option(100, "--lines", min=1, help="Number of journal lines to show."),
    json_output: bool = typer.Option(False, "--json", help="Print log command result as JSON."),
) -> None:
    """Show recent journal logs for the systemd-managed daemon."""
    result = daemon_systemd.run_daemon_logs(unit_name=unit_name, lines=lines)
    payload = result.to_dict()
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.ok:
        typer.echo(result.stdout)
        return
    warn(f"Daemon logs failed: {result.error or 'unknown error'}")
    raise typer.Exit(code=1)


def _print_cycle_result(cycle) -> None:  # noqa: ANN001
    if cycle.ok:
        success(f"Refreshed local stack state: scanned={cycle.scanned_count} updated={cycle.updated_count}")
        return
    warn(f"Refresh completed with issues: scanned={cycle.scanned_count} updated={cycle.updated_count}")
    if cycle.error:
        typer.echo(f"- {cycle.error}")
    for issue in cycle.issues:
        typer.echo(f"- {issue}")


def _run_systemd_action(action: str, *, unit_name: str, json_output: bool) -> None:
    result = daemon_systemd.run_daemon_systemd_action(action, unit_name=unit_name)
    payload = result.to_dict()
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.ok:
        success(f"Daemon service {action} completed: {unit_name}")
        return
    warn(f"Daemon service {action} failed: {result.error or 'unknown error'}")
    raise typer.Exit(code=1)


def _print_planned_commands(commands: list[list[str]]) -> None:
    if not commands:
        return
    typer.echo("Planned commands:")
    for command in commands:
        typer.echo(f"- {' '.join(command)}")
