from __future__ import annotations

import json
import sys
import time

from homesrvctl.shell import run_command


def build_dashboard_snapshot(run_json_command=None) -> dict[str, object]:  # noqa: ANN001
    if run_json_command is None:
        run_json_command = run_json_subcommand
    list_payload = run_json_command(["list"])
    cloudflared_payload = run_json_command(["cloudflared", "status"])
    validate_payload = run_json_command(["validate"])
    return {
        "list": list_payload,
        "cloudflared": cloudflared_payload,
        "validate": validate_payload,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def run_json_subcommand(args: list[str]) -> dict[str, object]:
    command = [sys.executable, "-m", "homesrvctl.main", *args, "--json"]
    result = run_command(command, quiet=True)
    if result.stdout:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            payload.setdefault("ok", result.ok)
            payload["command"] = command
            payload["returncode"] = result.returncode
            return payload
    if result.stdout:
        return {
            "ok": False,
            "error": "invalid JSON output",
            "stdout": result.stdout,
            "command": command,
        }
    return {
        "ok": False,
        "error": result.stderr or result.stdout or "command failed",
        "command": command,
        "returncode": result.returncode,
    }


def stack_sites(snapshot: dict[str, object]) -> list[dict[str, object]]:
    list_payload = snapshot.get("list")
    if not isinstance(list_payload, dict) or not list_payload.get("ok"):
        return []
    sites = list_payload.get("sites", [])
    if not isinstance(sites, list):
        return []
    return [site for site in sites if isinstance(site, dict)]


def run_stack_action(hostname: str, action: str) -> dict[str, object]:
    if action == "doctor":
        return run_json_subcommand(["doctor", hostname])
    if action == "init-site":
        return run_json_subcommand(["site", "init", hostname])
    if action == "up":
        return run_json_subcommand(["up", hostname])
    if action == "restart":
        return run_json_subcommand(["restart", hostname])
    if action == "down":
        return run_json_subcommand(["down", hostname])
    raise ValueError(f"unsupported stack action: {action}")


def run_tool_action(tool: str, action: str) -> dict[str, object]:
    if tool == "cloudflared":
        if action == "config-test":
            return run_json_subcommand(["cloudflared", "config-test"])
        if action == "reload":
            return run_json_subcommand(["cloudflared", "reload"])
        if action == "restart":
            return run_json_subcommand(["cloudflared", "restart"])
    raise ValueError(f"unsupported tool action: {tool} {action}")


def summarize_stack_action(hostname: str, action: str, payload: dict[str, object]) -> str:
    if payload.get("ok"):
        action_label = "site init" if action == "init-site" else action
        return f"{action_label} succeeded for {hostname}"
    checks = payload.get("checks")
    if isinstance(checks, list):
        failing_checks = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
        if failing_checks:
            first_failure = failing_checks[0]
            error = f"{first_failure.get('name', 'check failed')}: {first_failure.get('detail', 'command failed')}"
            action_label = "site init" if action == "init-site" else action
            return f"{action_label} failed for {hostname}: {error}"
    error = str(payload.get("error") or payload.get("detail") or "command failed")
    action_label = "site init" if action == "init-site" else action
    return f"{action_label} failed for {hostname}: {error}"


def action_label(action: str) -> str:
    return "site init" if action == "init-site" else action


def render_stack_action_detail(action: str, payload: dict[str, object]) -> list[str]:
    label = action_label(action)
    status = "ok" if payload.get("ok") else "failed"
    lines = [
        "Last action",
        "",
        f"action: {label}",
        f"status: {status}",
    ]

    if "dry_run" in payload:
        lines.append(f"dry run: {'yes' if payload.get('dry_run') else 'no'}")

    checks = payload.get("checks")
    if isinstance(checks, list):
        failing_checks = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
        lines.extend(
            [
                "",
                f"checks: {len(checks)} total, {len(failing_checks)} failing",
                "",
            ]
        )
        for check in checks[:8]:
            if not isinstance(check, dict):
                continue
            marker = "PASS" if check.get("ok") else "FAIL"
            lines.append(f"{marker} {check.get('name', '<unknown>')}: {check.get('detail', '')}")
        if len(checks) > 8:
            lines.append(f"... {len(checks) - 8} more")
        return lines

    commands = payload.get("commands")
    if isinstance(commands, list) and commands:
        lines.extend(["", f"commands: {len(commands)}", ""])
        for command_result in commands[:4]:
            if not isinstance(command_result, dict):
                continue
            command = command_result.get("command", [])
            rendered_command = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
            returncode = command_result.get("returncode", "?")
            lines.append(f"rc={returncode} {rendered_command}")
            stdout = str(command_result.get("stdout", "")).strip()
            stderr = str(command_result.get("stderr", "")).strip()
            if stdout:
                lines.append(f"stdout: {stdout.splitlines()[0]}")
            if stderr:
                lines.append(f"stderr: {stderr.splitlines()[0]}")
        if len(commands) > 4:
            lines.append(f"... {len(commands) - 4} more")
        return lines

    error = payload.get("error")
    detail = payload.get("detail")
    if error or detail:
        lines.extend(["", f"detail: {error or detail}"])
    return lines


def summarize_tool_action(tool: str, action: str, payload: dict[str, object]) -> str:
    tool_label = str(tool)
    label = str(action)
    if payload.get("ok"):
        return f"{tool_label} {label} succeeded"
    error = str(payload.get("error") or payload.get("detail") or "command failed")
    return f"{tool_label} {label} failed: {error}"


def render_tool_action_detail(tool: str, action: str, payload: dict[str, object]) -> list[str]:
    lines = [
        "Last action",
        "",
        f"tool: {tool}",
        f"action: {action}",
        f"status: {'ok' if payload.get('ok') else 'failed'}",
    ]

    if "dry_run" in payload:
        lines.append(f"dry run: {'yes' if payload.get('dry_run') else 'no'}")

    detail = payload.get("detail")
    if detail:
        lines.extend(["", f"detail: {detail}"])

    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        lines.extend(["", f"warnings: {len(warnings)}", ""])
        for warning in warnings[:5]:
            lines.append(f"- {warning}")
        if len(warnings) > 5:
            lines.append(f"... {len(warnings) - 5} more")

    config_validation = payload.get("config_validation")
    if isinstance(config_validation, dict):
        lines.extend(
            [
                "",
                f"config ok: {config_validation.get('ok', False)}",
                f"config detail: {config_validation.get('detail', 'unknown')}",
            ]
        )
        validation_warnings = config_validation.get("warnings", [])
        if isinstance(validation_warnings, list):
            lines.extend(["", f"config warnings: {len(validation_warnings)}", ""])
            for warning in validation_warnings[:5]:
                lines.append(f"- {warning}")
            if len(validation_warnings) > 5:
                lines.append(f"... {len(validation_warnings) - 5} more")

    return lines
