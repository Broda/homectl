from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.services.refresh import rebuild_local_stack_state, utc_now_iso
from homesrvctl.state.db import default_state_db_path
from homesrvctl.state.store import StateStore
from homesrvctl.utils import success, warn, with_json_schema

db_cli = typer.Typer(help="Manage the local homesrvctl state database.")


@db_cli.command("init")
def db_init(
    path: Path | None = typer.Option(None, "--path", help="Use a custom state database path."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Create the local state database and schema."""
    db_path = path or default_state_db_path()
    store = StateStore(db_path)
    created = store.initialize(utc_now_iso())
    status = store.status()
    payload = {
        "action": "db_init",
        "ok": status.initialized and not status.issues,
        "db_path": str(store.path),
        "initialized": status.initialized,
        "created": created,
        "state_schema_version": status.schema_version,
        "issues": status.issues,
    }
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not payload["ok"]:
            raise typer.Exit(code=1)
        return
    if payload["ok"]:
        success(f"Initialized state database: {store.path}")
        return
    for issue in status.issues:
        warn(issue)
    raise typer.Exit(code=1)


@db_cli.command("status")
def db_status(
    path: Path | None = typer.Option(None, "--path", help="Use a custom state database path."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Show local state database status."""
    store = StateStore(path or default_state_db_path())
    status = store.status()
    payload = {"action": "db_status", **status.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not status.ok:
            raise typer.Exit(code=1)
        return
    if status.ok:
        success(
            f"State database OK: schema={status.schema_version} "
            f"stacks={status.stack_count} path={status.db_path}"
        )
        if status.last_refresh_at:
            typer.echo(f"last_refresh_at: {status.last_refresh_at}")
        return
    warn(f"State database not ready: {status.db_path}")
    for issue in status.issues:
        typer.echo(f"- {issue}")
    raise typer.Exit(code=1)


@db_cli.command("rebuild")
def db_rebuild(
    path: Path | None = typer.Option(None, "--path", help="Use a custom state database path."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Read config from a custom path."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Rebuild cached local stack state from the filesystem."""
    target_path = path or default_state_db_path()
    try:
        result = rebuild_local_stack_state(db_path=target_path, config_path=config_path)
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema(
                        {
                            "action": "db_rebuild",
                            "ok": False,
                            "db_path": str(target_path),
                            "error": str(exc),
                        }
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise
    payload = {"action": "db_rebuild", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.ok:
        success(f"Rebuilt local stack state: scanned={result.scanned_count} updated={result.updated_count}")
        return
    warn(f"Rebuilt local stack state with issues: scanned={result.scanned_count} updated={result.updated_count}")
    for issue in result.issues:
        typer.echo(f"- {issue}")
    raise typer.Exit(code=1)
