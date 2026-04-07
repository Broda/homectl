from __future__ import annotations

import json

import typer

from homectl.cloudflared_service import (
    CloudflaredServiceError,
    detect_cloudflared_runtime,
    restart_cloudflared_service,
)
from homectl.utils import info, success, warn

cloudflared_cli = typer.Typer(help="Inspect and control the local cloudflared runtime.")


@cloudflared_cli.command("status")
def cloudflared_status(
    json_output: bool = typer.Option(False, "--json", help="Print the cloudflared runtime status as JSON."),
) -> None:
    """Show how cloudflared is currently managed and whether it is active."""
    runtime = detect_cloudflared_runtime()
    if json_output:
        payload = {
            "ok": runtime.active,
            "mode": runtime.mode,
            "active": runtime.active,
            "detail": runtime.detail,
            "restart_command": runtime.restart_command,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        detail = f"{runtime.mode}: {runtime.detail}"
        if runtime.active:
            success(detail)
            if runtime.restart_command:
                info(f"restart command: {' '.join(runtime.restart_command)}")
        else:
            warn(detail)
    if not runtime.active:
        raise typer.Exit(code=1)


@cloudflared_cli.command("restart")
def cloudflared_restart(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the restart command without running it."),
    json_output: bool = typer.Option(False, "--json", help="Print the restart result as JSON."),
) -> None:
    """Restart cloudflared when it is managed by a supported runtime."""
    runtime = detect_cloudflared_runtime()
    if dry_run:
        if runtime.restart_command:
            if json_output:
                payload = {
                    "ok": True,
                    "dry_run": True,
                    "mode": runtime.mode,
                    "detail": runtime.detail,
                    "restart_command": runtime.restart_command,
                }
                typer.echo(json.dumps(payload, indent=2))
            else:
                info(f"[dry-run] {' '.join(runtime.restart_command)}")
                success(f"Dry-run complete for cloudflared restart via {runtime.mode}")
            return
        if json_output:
            payload = {
                "ok": False,
                "dry_run": True,
                "mode": runtime.mode,
                "detail": runtime.detail,
                "restart_command": runtime.restart_command,
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            warn(f"[dry-run] {runtime.detail}")
        raise typer.Exit(code=1)

    try:
        runtime = restart_cloudflared_service()
    except CloudflaredServiceError as exc:
        if json_output:
            payload = {
                "ok": False,
                "dry_run": False,
                "detail": str(exc),
            }
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    if json_output:
        payload = {
            "ok": True,
            "dry_run": False,
            "mode": runtime.mode,
            "detail": runtime.detail,
            "restart_command": runtime.restart_command,
        }
        typer.echo(json.dumps(payload, indent=2))
        return
    success(f"Restarted cloudflared via {runtime.mode}")


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1
