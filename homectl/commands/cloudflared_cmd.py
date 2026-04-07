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
        typer.echo(json.dumps(_runtime_payload(runtime, ok=runtime.active), indent=2))
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
                typer.echo(json.dumps(_runtime_payload(runtime, ok=True, dry_run=True), indent=2))
            else:
                info(f"[dry-run] {' '.join(runtime.restart_command)}")
                success(f"Dry-run complete for cloudflared restart via {runtime.mode}")
            return
        if json_output:
            typer.echo(json.dumps(_runtime_payload(runtime, ok=False, dry_run=True), indent=2))
        else:
            warn(f"[dry-run] {runtime.detail}")
        raise typer.Exit(code=1)

    try:
        runtime = restart_cloudflared_service()
    except CloudflaredServiceError as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "dry_run": False,
                        "mode": runtime.mode,
                        "active": runtime.active,
                        "detail": str(exc),
                        "restart_command": runtime.restart_command,
                    },
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    if json_output:
        typer.echo(json.dumps(_runtime_payload(runtime, ok=True, dry_run=False), indent=2))
        return
    success(f"Restarted cloudflared via {runtime.mode}")


@cloudflared_cli.command("logs")
def cloudflared_logs(
    follow: bool = typer.Option(False, "--follow", help="Suggest a follow/tail command for the detected runtime."),
    json_output: bool = typer.Option(False, "--json", help="Print the log-command guidance as JSON."),
) -> None:
    """Show the right log command for the detected cloudflared runtime."""
    runtime = detect_cloudflared_runtime()
    logs_command = _logs_command(runtime, follow=follow)
    ok = logs_command is not None
    if json_output:
        payload = _runtime_payload(runtime, ok=ok)
        payload["follow"] = follow
        payload["logs_command"] = logs_command
        typer.echo(json.dumps(payload, indent=2))
    else:
        if logs_command:
            info(" ".join(logs_command))
        else:
            warn(f"No automatic log command available for {runtime.mode}: {runtime.detail}")
    if not ok:
        raise typer.Exit(code=1)


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1


def _runtime_payload(runtime, ok: bool, dry_run: bool | None = None) -> dict[str, object]:  # noqa: ANN001
    payload: dict[str, object] = {
        "ok": ok,
        "mode": runtime.mode,
        "active": runtime.active,
        "detail": runtime.detail,
        "restart_command": runtime.restart_command,
        "logs_command": runtime.logs_command,
    }
    if dry_run is not None:
        payload["dry_run"] = dry_run
    return payload


def _logs_command(runtime, follow: bool) -> list[str] | None:  # noqa: ANN001
    if runtime.logs_command is None:
        return None
    if not follow:
        return runtime.logs_command

    if runtime.mode == "systemd":
        return runtime.logs_command + ["-f"]
    if runtime.mode == "docker":
        return runtime.logs_command[:-1] + ["--follow", runtime.logs_command[-1]]
    return runtime.logs_command
