from __future__ import annotations

import json

import typer

from homesrvctl.cloudflared import test_cloudflared_config
from homesrvctl.cloudflared_service import (
    CloudflaredServiceError,
    detect_cloudflared_runtime,
    reload_cloudflared_service,
    restart_cloudflared_service,
)
from homesrvctl.config import load_config
from homesrvctl.utils import info, success, warn, with_json_schema

cloudflared_cli = typer.Typer(help="Inspect and control the local cloudflared runtime.")


@cloudflared_cli.command("status")
def cloudflared_status(
    json_output: bool = typer.Option(False, "--json", help="Print the cloudflared runtime status as JSON."),
) -> None:
    """Show how cloudflared is currently managed and whether it is active."""
    runtime = detect_cloudflared_runtime(quiet=json_output)
    config_validation = None
    try:
        config = load_config()
        config_validation = test_cloudflared_config(config.cloudflared_config)
    except typer.BadParameter:
        config_validation = None
    if json_output:
        payload = _runtime_payload(runtime, ok=runtime.active)
        if config_validation is not None:
            payload["config_validation"] = _config_validation_payload(config_validation)
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
    else:
        detail = f"{runtime.mode}: {runtime.detail}"
        if runtime.active:
            success(detail)
            if runtime.restart_command:
                info(f"restart command: {' '.join(runtime.restart_command)}")
            if runtime.reload_command:
                info(f"reload command: {' '.join(runtime.reload_command)}")
        else:
            warn(detail)
        if config_validation is not None:
            if config_validation.ok:
                info(f"config: {config_validation.detail}")
                for warning_message in config_validation.warnings or []:
                    warn(f"config warning: {warning_message}")
                if config_validation.warnings:
                    info("config warnings are advisory; cloudflared status remains healthy while the config stays valid")
            else:
                warn(f"config: {config_validation.detail}")
    if not runtime.active:
        raise typer.Exit(code=1)


@cloudflared_cli.command("restart")
def cloudflared_restart(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the restart command without running it."),
    json_output: bool = typer.Option(False, "--json", help="Print the restart result as JSON."),
) -> None:
    """Restart cloudflared when it is managed by a supported runtime."""
    runtime = detect_cloudflared_runtime(quiet=json_output)
    if dry_run:
        if runtime.restart_command:
            if json_output:
                typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=True, dry_run=True)), indent=2))
            else:
                info(f"[dry-run] {' '.join(runtime.restart_command)}")
                success(f"Dry-run complete for cloudflared restart via {runtime.mode}")
            return
        if json_output:
            typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=False, dry_run=True)), indent=2))
        else:
            warn(f"[dry-run] {runtime.detail}")
        raise typer.Exit(code=1)

    try:
        runtime = restart_cloudflared_service()
    except CloudflaredServiceError as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema({
                        "ok": False,
                        "dry_run": False,
                        "mode": runtime.mode,
                        "active": runtime.active,
                        "detail": str(exc),
                        "restart_command": runtime.restart_command,
                    }),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    if json_output:
        typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=True, dry_run=False)), indent=2))
        return
    success(f"Restarted cloudflared via {runtime.mode}")


@cloudflared_cli.command("reload")
def cloudflared_reload(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the reload command without running it."),
    json_output: bool = typer.Option(False, "--json", help="Print the reload result as JSON."),
) -> None:
    """Reload cloudflared when the detected runtime supports it."""
    runtime = detect_cloudflared_runtime(quiet=json_output)
    if dry_run:
        if runtime.reload_command:
            if json_output:
                typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=True, dry_run=True)), indent=2))
            else:
                info(f"[dry-run] {' '.join(runtime.reload_command)}")
                success(f"Dry-run complete for cloudflared reload via {runtime.mode}")
            return
        if json_output:
            typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=False, dry_run=True)), indent=2))
        else:
            warn(f"[dry-run] {runtime.detail}; reload is not supported for this runtime")
        raise typer.Exit(code=1)

    try:
        runtime = reload_cloudflared_service()
    except CloudflaredServiceError as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema({
                        "ok": False,
                        "dry_run": False,
                        "mode": runtime.mode,
                        "active": runtime.active,
                        "detail": str(exc),
                        "restart_command": runtime.restart_command,
                        "reload_command": runtime.reload_command,
                        "logs_command": runtime.logs_command,
                    }),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc

    if json_output:
        typer.echo(json.dumps(with_json_schema(_runtime_payload(runtime, ok=True, dry_run=False)), indent=2))
        return
    success(f"Reloaded cloudflared via {runtime.mode}")


@cloudflared_cli.command("logs")
def cloudflared_logs(
    follow: bool = typer.Option(False, "--follow", help="Suggest a follow/tail command for the detected runtime."),
    json_output: bool = typer.Option(False, "--json", help="Print the log-command guidance as JSON."),
) -> None:
    """Show the right log command for the detected cloudflared runtime."""
    runtime = detect_cloudflared_runtime(quiet=json_output)
    logs_command = _logs_command(runtime, follow=follow)
    ok = logs_command is not None
    if json_output:
        payload = _runtime_payload(runtime, ok=ok)
        payload["follow"] = follow
        payload["logs_command"] = logs_command
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
    else:
        if logs_command:
            info(" ".join(logs_command))
        else:
            warn(f"No automatic log command available for {runtime.mode}: {runtime.detail}")
    if not ok:
        raise typer.Exit(code=1)


@cloudflared_cli.command("config-test")
def cloudflared_config_test(
    json_output: bool = typer.Option(False, "--json", help="Print the config-test result as JSON."),
) -> None:
    """Validate the configured cloudflared ingress config."""
    config = load_config()
    result = test_cloudflared_config(config.cloudflared_config)
    payload = with_json_schema({
        "ok": result.ok,
        "config_path": str(config.cloudflared_config),
        "method": result.method,
        "command": result.command,
        "detail": result.detail,
        "warnings": result.warnings or [],
    })
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if result.command:
            info(f"$ {' '.join(result.command)}")
        if result.ok:
            success(result.detail)
            for warning_message in result.warnings or []:
                warn(f"warning: {warning_message}")
        else:
            warn(result.detail)
    if not result.ok:
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
        "reload_command": runtime.reload_command,
        "logs_command": runtime.logs_command,
    }
    if dry_run is not None:
        payload["dry_run"] = dry_run
    return payload


def _config_validation_payload(result) -> dict[str, object]:  # noqa: ANN001
    warnings = result.warnings or []
    return {
        "ok": result.ok,
        "detail": result.detail,
        "method": result.method,
        "command": result.command,
        "warnings": warnings,
        "has_warnings": bool(warnings),
        "warning_policy": "non-fatal" if result.ok and warnings else None,
    }


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
