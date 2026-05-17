from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.services.observers.runner import get_observer_status, run_observers
from homesrvctl.state.db import default_state_db_path
from homesrvctl.utils import success, warn, with_json_schema

observe_cli = typer.Typer(help="Run and inspect read-only local runtime observers.")


@observe_cli.command("run")
def observe_run(
    stack_runtime: bool = typer.Option(True, "--stack-runtime/--no-stack-runtime", help="Observe Docker Compose stack runtime state."),
    cloudflared: bool = typer.Option(True, "--cloudflared/--no-cloudflared", help="Observe local cloudflared runtime/config state."),
    traefik: bool = typer.Option(True, "--traefik/--no-traefik", help="Observe configured Traefik URL reachability."),
    all_observers: bool = typer.Option(False, "--all", help="Run all implemented local observers."),
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Read config from a custom path."),
    json_output: bool = typer.Option(False, "--json", help="Print observer result as JSON."),
) -> None:
    """Run selected read-only local runtime observers once."""
    if all_observers:
        stack_runtime = True
        cloudflared = True
        traefik = True
    if not any([stack_runtime, cloudflared, traefik]):
        payload = {
            "action": "observe_run",
            "ok": False,
            "error": "at least one observer must be enabled",
        }
        if json_output:
            typer.echo(json.dumps(with_json_schema(payload), indent=2))
        else:
            warn(str(payload["error"]))
        raise typer.Exit(code=1)

    result = run_observers(
        db_path=db_path or default_state_db_path(),
        config_path=config_path,
        stack_runtime=stack_runtime,
        cloudflared=cloudflared,
        traefik=traefik,
    )
    payload = {"action": "observe_run", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    for observer in result.results:
        label = "PASS" if observer.ok else "WARN"
        typer.echo(f"{label} {observer.observer_name}: {observer.summary}")
        for issue in observer.issues:
            typer.echo(f"- {issue}")
    if result.ok:
        success("Observer run complete")
        return
    raise typer.Exit(code=1)


@observe_cli.command("status")
def observe_status(
    db_path: Path | None = typer.Option(None, "--db-path", help="Use a custom state database path."),
    json_output: bool = typer.Option(False, "--json", help="Print observer status as JSON."),
) -> None:
    """Show latest persisted observer snapshots without running live checks."""
    result = get_observer_status(db_path=db_path or default_state_db_path())
    payload = {"action": "observe_status", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return

    if result.stack_runtime:
        success(
            "stack-runtime: "
            f"stacks={result.stack_runtime['stack_count']} observed_at={result.stack_runtime['latest_observed_at']}"
        )
    else:
        warn("stack-runtime: no observations")
    _print_runtime_status("cloudflared", result.cloudflared)
    _print_runtime_status("traefik", result.traefik)
    for issue in result.issues:
        typer.echo(f"- {issue}")
    if not result.ok:
        raise typer.Exit(code=1)


def _print_runtime_status(name: str, payload: dict[str, object] | None) -> None:
    if payload is None:
        warn(f"{name}: no observations")
        return
    data = payload.get("data")
    status = None
    detail = None
    if isinstance(data, dict):
        status = data.get("status")
        detail = data.get("detail")
    success(f"{name}: {status or payload.get('message') or 'observed'}")
    if detail:
        typer.echo(str(detail))
