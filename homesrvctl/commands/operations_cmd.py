from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.services.operations import OPERATION_STATUSES, get_operation, list_operations
from homesrvctl.state.db import default_state_db_path
from homesrvctl.utils import success, warn, with_json_schema

operations_cli = typer.Typer(help="Inspect durable operation history.")


@operations_cli.command("list")
def operations_list(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum number of operations to show."),
    status: str | None = typer.Option(None, "--status", help="Filter by operation status."),
    operation_type: str | None = typer.Option(None, "--type", help="Filter by operation type."),
    target: str | None = typer.Option(None, "--target", help="Filter by operation target."),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    json_output: bool = typer.Option(False, "--json", help="Print operation history as JSON."),
) -> None:
    """List recent operations from the local state database."""
    if status is not None and status not in OPERATION_STATUSES:
        raise typer.BadParameter(f"status must be one of: {', '.join(sorted(OPERATION_STATUSES))}")
    result = list_operations(
        db_path=db_path or default_state_db_path(),
        limit=limit,
        status=status,
        operation_type=operation_type,
        target=target,
    )
    payload = {"action": "operations_list", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if not result.ok:
        warn(result.issues[0] if result.issues else "operation history is unavailable")
        raise typer.Exit(code=1)
    if not result.operations:
        success("No operations recorded")
        return
    for operation in result.operations:
        target_label = operation.target or "-"
        typer.echo(
            f"{operation.id} {operation.status} {operation.operation_type} "
            f"{operation.target_type or '-'} {target_label} {operation.started_at}"
        )


@operations_cli.command("show")
def operations_show(
    operation_id: int = typer.Argument(..., help="Operation ID to inspect."),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    json_output: bool = typer.Option(False, "--json", help="Print one operation as JSON."),
) -> None:
    """Show one recorded operation."""
    result = get_operation(db_path=db_path or default_state_db_path(), operation_id=operation_id)
    payload = {"action": "operations_show", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if not result.ok or result.operation is None:
        warn(result.error or "operation not found")
        raise typer.Exit(code=1)
    operation = result.operation
    success(f"Operation {operation.id}: {operation.status}")
    typer.echo(f"type: {operation.operation_type}")
    typer.echo(f"target: {operation.target_type or '-'} {operation.target or '-'}")
    typer.echo(f"started_at: {operation.started_at}")
    typer.echo(f"finished_at: {operation.finished_at or '-'}")
    if operation.summary:
        typer.echo(f"summary: {operation.summary}")
    if operation.error:
        typer.echo(f"error: {operation.error}")
    if operation.data:
        typer.echo("data:")
        typer.echo(json.dumps(operation.data, indent=2, sort_keys=True))
