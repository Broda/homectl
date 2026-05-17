from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.services.refresh import refresh_local_stack_state
from homesrvctl.state.db import default_state_db_path
from homesrvctl.utils import success, warn, with_json_schema


def refresh(
    stack: str | None = typer.Option(None, "--stack", help="Refresh one hostname stack instead of all stacks."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Inspect stack state without writing stack rows."),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Read config from a custom path."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Snapshot current local stack state into the state database."""
    target_db_path = db_path or default_state_db_path()
    try:
        result = refresh_local_stack_state(
            db_path=target_db_path,
            config_path=config_path,
            stack=stack,
            dry_run=dry_run,
        )
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema(
                        {
                            "action": "refresh",
                            "ok": False,
                            "db_path": str(target_db_path),
                            "stack": stack,
                            "dry_run": dry_run,
                            "error": str(exc),
                        }
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise

    payload = {"action": "refresh", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.ok:
        verb = "Would refresh" if dry_run else "Refreshed"
        success(f"{verb} local stack state: scanned={result.scanned_count} updated={result.updated_count}")
        return
    warn(f"Refreshed local stack state with issues: scanned={result.scanned_count} updated={result.updated_count}")
    for issue in result.issues:
        typer.echo(f"- {issue}")
    raise typer.Exit(code=1)
