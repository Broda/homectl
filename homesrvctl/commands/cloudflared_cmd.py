from __future__ import annotations

import json

import typer

from homesrvctl.cloudflared import test_cloudflared_config
from homesrvctl.cloudflared_service import (
    CloudflaredServiceError,
    detect_cloudflared_runtime,
    inspect_cloudflared_setup,
    reload_cloudflared_service,
    restart_cloudflared_service,
    service_control_command,
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
    setup = None
    try:
        config = load_config()
        config_validation = test_cloudflared_config(config.cloudflared_config)
        setup = inspect_cloudflared_setup(config.cloudflared_config, runtime=runtime, quiet=json_output)
    except typer.BadParameter:
        config_validation = None
        setup = None
    runtime_ok = runtime.active
    config_ok = config_validation is None or config_validation.ok
    setup_ok = setup is None or setup.ok
    overall_ok = runtime_ok and config_ok and setup_ok
    if json_output:
        payload = _runtime_payload(runtime, ok=overall_ok)
        if config_validation is not None:
            payload["config_validation"] = _config_validation_payload(config_validation)
        if setup is not None:
            payload["setup"] = _setup_payload(setup)
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
            issues = list(getattr(config_validation, "issues", []) or [])
            if config_validation.ok:
                info(f"config: {config_validation.detail}")
                for issue in issues:
                    if issue.severity == "advisory":
                        warn(f"config advisory: {issue.render()}")
                if any(issue.severity == "advisory" for issue in issues):
                    info("config warnings are advisory; cloudflared status remains healthy while the config stays valid")
            else:
                warn(f"config: {config_validation.detail}")
                for issue in issues:
                    prefix = "config blocking issue" if issue.blocking else "config advisory"
                    warn(f"{prefix}: {issue.render()}")
        if setup is not None:
            if setup.ok:
                info(f"setup: {setup.detail}")
                info(f"setup state: {getattr(setup, 'setup_state', 'ready')}")
                info(
                    "account inspection available: "
                    f"{'yes' if getattr(setup, 'account_inspection_available', False) else 'no'}"
                )
                credentials_path = getattr(setup, "configured_credentials_path", None)
                if credentials_path:
                    info(f"credentials path: {credentials_path}")
                if getattr(setup, "notes", None):
                    for note in setup.notes:
                        info(f"setup note: {note}")
                if getattr(setup, "next_commands", None):
                    info("run `homesrvctl cloudflared setup` for the shared-group migration commands")
            else:
                warn(f"setup: {setup.detail}")
                warn(f"setup state: {getattr(setup, 'setup_state', 'repair needed')}")
                for issue in setup.issues:
                    warn(f"setup issue: {issue}")
                if getattr(setup, "notes", None):
                    for note in setup.notes:
                        info(f"setup note: {note}")
                if getattr(setup, "next_commands", None):
                    info("run `homesrvctl cloudflared setup` for the shared-group migration commands")
    if not overall_ok:
        raise typer.Exit(code=1)


@cloudflared_cli.command("setup")
def cloudflared_setup(
    json_output: bool = typer.Option(False, "--json", help="Print the cloudflared setup assessment as JSON."),
) -> None:
    """Assess cloudflared config ownership and runtime alignment for homesrvctl."""
    config = load_config()
    runtime = detect_cloudflared_runtime(quiet=json_output)
    setup = inspect_cloudflared_setup(config.cloudflared_config, runtime=runtime, quiet=json_output)
    payload = with_json_schema(_setup_payload(setup))
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if setup.ok and setup.setup_state == "ready":
            success(setup.detail)
        elif setup.ok:
            info(setup.detail)
        else:
            warn(setup.detail)
        info(f"configured path: {setup.configured_path}")
        info(f"runtime path: {setup.runtime_path or '<unavailable>'}")
        info(f"paths aligned: {'yes' if setup.paths_aligned else 'no' if setup.paths_aligned is False else 'unknown'}")
        info(f"configured exists: {'yes' if setup.configured_exists else 'no'}")
        info(f"configured writable: {'yes' if setup.configured_writable else 'no'}")
        info(f"credentials path: {getattr(setup, 'configured_credentials_path', None) or '<unavailable>'}")
        info(
            "credentials readable: "
            f"{'yes' if getattr(setup, 'configured_credentials_readable', None) else 'no' if getattr(setup, 'configured_credentials_readable', None) is False else 'unknown'}"
        )
        info(f"ingress mutations available: {'yes' if setup.ingress_mutation_available else 'no'}")
        info(f"account inspection available: {'yes' if getattr(setup, 'account_inspection_available', False) else 'no'}")
        info(f"current user: {getattr(setup, 'current_user', '<unknown>')}")
        info(
            f"in homesrvctl group: {'yes' if getattr(setup, 'current_user_in_shared_group', False) else 'no'}"
        )
        info(f"in docker group: {'yes' if getattr(setup, 'current_user_in_docker_group', False) else 'no'}")
        info(
            "service control available: "
            f"{'yes' if getattr(setup, 'service_control_available', False) else 'no'}"
        )
        service_command = getattr(setup, "service_control_command", None)
        if service_command:
            info(f"service control command: {' '.join(service_command)}")
        info(f"setup state: {getattr(setup, 'setup_state', 'repair needed' if not setup.ok else 'ready')}")
        if getattr(setup, "notes", None):
            for note in setup.notes:
                info(f"note: {note}")
        if setup.issues:
            for issue in setup.issues:
                warn(f"issue: {issue}")
        if setup.override_content:
            info(f"systemd override path: {setup.override_path}")
            typer.echo("")
            typer.echo(setup.override_content)
        if setup.next_commands:
            typer.echo("")
            info("next commands:")
            for command in setup.next_commands:
                typer.echo(command)
    if not setup.ok:
        raise typer.Exit(code=1)


@cloudflared_cli.command("restart")
def cloudflared_restart(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the restart command without running it."),
    json_output: bool = typer.Option(False, "--json", help="Print the restart result as JSON."),
) -> None:
    """Restart cloudflared when it is managed by a supported runtime."""
    runtime = detect_cloudflared_runtime(quiet=json_output)
    if dry_run:
        restart_command = service_control_command(runtime.restart_command)
        if restart_command:
            display_runtime = _runtime_with_commands(runtime, restart_command=restart_command)
            if json_output:
                typer.echo(json.dumps(with_json_schema(_runtime_payload(display_runtime, ok=True, dry_run=True)), indent=2))
            else:
                info(f"[dry-run] {' '.join(restart_command)}")
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
        reload_command = service_control_command(runtime.reload_command)
        if reload_command:
            display_runtime = _runtime_with_commands(runtime, reload_command=reload_command)
            if json_output:
                typer.echo(json.dumps(with_json_schema(_runtime_payload(display_runtime, ok=True, dry_run=True)), indent=2))
            else:
                info(f"[dry-run] {' '.join(reload_command)}")
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
        "issues": _config_issue_payloads(getattr(result, "issues", []) or []),
        "warnings": result.warnings or [],
    })
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if result.command:
            info(f"$ {' '.join(result.command)}")
        if result.ok:
            success(result.detail)
        else:
            warn(result.detail)
        for issue in getattr(result, "issues", []) or []:
            prefix = "warning" if issue.severity == "advisory" else "blocking issue"
            warn(f"{prefix}: {issue.render()}")
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
    issues = list(getattr(result, "issues", []) or [])
    has_blocking_issues = any(issue.blocking for issue in issues)
    advisory_count = sum(1 for issue in issues if issue.severity == "advisory")
    return {
        "ok": result.ok,
        "detail": result.detail,
        "method": result.method,
        "command": result.command,
        "issues": _config_issue_payloads(issues),
        "warnings": warnings,
        "has_warnings": bool(warnings),
        "has_blocking_issues": has_blocking_issues,
        "max_severity": "blocking" if has_blocking_issues else ("advisory" if advisory_count else None),
        "warning_policy": "non-fatal" if result.ok and warnings else None,
    }


def _setup_payload(setup) -> dict[str, object]:  # noqa: ANN001
    return {
        "ok": setup.ok,
        "setup_state": getattr(setup, "setup_state", "repair needed" if not setup.ok else "ready"),
        "mode": setup.mode,
        "systemd_managed": setup.systemd_managed,
        "active": setup.active,
        "configured_path": setup.configured_path,
        "configured_exists": setup.configured_exists,
        "configured_writable": setup.configured_writable,
        "configured_credentials_path": getattr(setup, "configured_credentials_path", None),
        "configured_credentials_exists": getattr(setup, "configured_credentials_exists", None),
        "configured_credentials_readable": getattr(setup, "configured_credentials_readable", None),
        "configured_credentials_group_readable": getattr(setup, "configured_credentials_group_readable", None),
        "configured_credentials_owner": getattr(setup, "configured_credentials_owner", None),
        "configured_credentials_group": getattr(setup, "configured_credentials_group", None),
        "configured_credentials_mode": getattr(setup, "configured_credentials_mode", None),
        "runtime_path": setup.runtime_path,
        "runtime_exists": setup.runtime_exists,
        "runtime_readable": setup.runtime_readable,
        "paths_aligned": setup.paths_aligned,
        "ingress_mutation_available": setup.ingress_mutation_available,
        "account_inspection_available": getattr(setup, "account_inspection_available", False),
        "service_user": getattr(setup, "service_user", None),
        "service_group": getattr(setup, "service_group", None),
        "shared_group": getattr(setup, "shared_group", "homesrvctl"),
        "current_user": getattr(setup, "current_user", None),
        "current_user_in_shared_group": getattr(setup, "current_user_in_shared_group", None),
        "current_user_in_docker_group": getattr(setup, "current_user_in_docker_group", None),
        "service_control_available": getattr(setup, "service_control_available", None),
        "service_control_command": getattr(setup, "service_control_command", None),
        "sudoers_path": getattr(setup, "sudoers_path", None),
        "detail": setup.detail,
        "issues": setup.issues,
        "notes": setup.notes or [],
        "next_commands": setup.next_commands,
        "override_path": setup.override_path,
        "override_content": setup.override_content,
    }


def _config_issue_payloads(issues) -> list[dict[str, object]]:  # noqa: ANN001
    return [
        {
            "code": issue.code,
            "severity": issue.severity,
            "blocking": issue.blocking,
            "detail": issue.detail,
            "hint": issue.hint,
            "message": issue.render(),
        }
        for issue in issues
    ]


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


def _runtime_with_commands(runtime, *, restart_command=None, reload_command=None):  # noqa: ANN001, ANN202
    runtime.restart_command = restart_command if restart_command is not None else runtime.restart_command
    runtime.reload_command = reload_command if reload_command is not None else runtime.reload_command
    return runtime
