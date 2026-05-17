from __future__ import annotations

import json
from pathlib import Path

import typer

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
    json_output: bool = typer.Option(False, "--json", help="Print daemon status as JSON."),
) -> None:
    """Show read-only daemon/cache status."""
    status = get_daemon_status(db_path=db_path or default_state_db_path())
    payload = {"action": "daemon_status", **status.to_dict()}
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
        typer.echo("process supervision: not implemented")
        typer.echo(f"last_refresh_at: {status.last_refresh_at or 'N/A'}")
        typer.echo(f"daemon_heartbeat_at: {status.daemon_heartbeat_at or 'N/A'}")
        return
    warn(f"Daemon state not ready: {status.db_path}")
    typer.echo("process supervision: not implemented")
    for issue in status.issues:
        typer.echo(f"- {issue}")
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
