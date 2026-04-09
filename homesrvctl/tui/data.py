from __future__ import annotations

import json
import sys
import time

from homesrvctl.shell import run_command
from homesrvctl.utils import validate_bare_domain


def build_dashboard_snapshot(run_json_command=None) -> dict[str, object]:  # noqa: ANN001
    if run_json_command is None:
        run_json_command = run_json_subcommand
    list_payload = run_json_command(["list"])
    config_payload = run_json_command(["config", "show"])
    cloudflared_payload = run_json_command(["cloudflared", "status"])
    validate_payload = run_json_command(["validate"])
    return {
        "list": list_payload,
        "config": config_payload,
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


def run_stack_action(hostname: str, action: str, template: str | None = None) -> dict[str, object]:
    if action == "doctor":
        return run_json_subcommand(["doctor", hostname])
    if action == "init-site":
        return run_json_subcommand(["site", "init", hostname])
    if action == "app-init":
        if not template:
            raise ValueError("template is required for app-init")
        return run_json_subcommand(["app", "init", hostname, "--template", template])
    if action == "up":
        return run_json_subcommand(["up", hostname])
    if action == "restart":
        return run_json_subcommand(["restart", hostname])
    if action == "down":
        return run_json_subcommand(["down", hostname])
    raise ValueError(f"unsupported stack action: {action}")


def run_tool_action(tool: str, action: str) -> dict[str, object]:
    if tool == "config":
        if action == "show":
            return run_json_subcommand(["config", "show"])
    if tool == "cloudflared":
        if action == "config-test":
            return run_json_subcommand(["cloudflared", "config-test"])
        if action == "reload":
            return run_json_subcommand(["cloudflared", "reload"])
        if action == "restart":
            return run_json_subcommand(["cloudflared", "restart"])
    raise ValueError(f"unsupported tool action: {tool} {action}")


def run_stack_config_view(hostname: str) -> dict[str, object]:
    return run_json_subcommand(["config", "show", "--stack", hostname])


def run_stack_domain_status(hostname: str) -> dict[str, object]:
    return run_json_subcommand(["domain", "status", hostname])


def summarize_stack_action(hostname: str, action: str, payload: dict[str, object]) -> str:
    label = action_label(action)
    if payload.get("ok"):
        return f"{label} succeeded for {hostname}"
    checks = payload.get("checks")
    if isinstance(checks, list):
        failing_checks = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
        if failing_checks:
            first_failure = failing_checks[0]
            error = f"{first_failure.get('name', 'check failed')}: {first_failure.get('detail', 'command failed')}"
            return f"{label} failed for {hostname}: {error}"
    error = str(payload.get("error") or payload.get("detail") or "command failed")
    return f"{label} failed for {hostname}: {error}"


def action_label(action: str) -> str:
    if action == "init-site":
        return "site init"
    if action == "app-init":
        return "app init"
    return action


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

    template = payload.get("template")
    if template:
        lines.append(f"template: {template}")

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

    files = payload.get("files")
    if isinstance(files, list) and files:
        lines.extend(["", f"files: {len(files)}", ""])
        for output_path in files[:6]:
            lines.append(f"- {output_path}")
        if len(files) > 6:
            lines.append(f"... {len(files) - 6} more")
        target_dir = payload.get("target_dir")
        if target_dir:
            lines.extend(["", f"target dir: {target_dir}"])
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


def render_config_payload_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok"):
        return [f"error: {payload.get('error', 'unknown error')}"]

    global_config = payload.get("global")
    if not isinstance(global_config, dict):
        return ["global config unavailable"]

    lines = [
        f"config path: {payload.get('config_path', '<unknown>')}",
        "",
        f"sites root: {global_config.get('sites_root', '<unknown>')}",
        f"docker network: {global_config.get('docker_network', '<unknown>')}",
        f"traefik url: {global_config.get('traefik_url', '<unknown>')}",
        f"cloudflared config: {global_config.get('cloudflared_config', '<unknown>')}",
        f"api token present: {global_config.get('cloudflare_api_token_present', False)}",
    ]

    profiles = global_config.get("profiles")
    if isinstance(profiles, dict):
        profile_names = sorted(str(name) for name in profiles)
        lines.extend(["", f"profiles: {len(profile_names)}"])
        if profile_names:
            lines.extend(f"- {name}" for name in profile_names[:8])
            if len(profile_names) > 8:
                lines.append(f"... {len(profile_names) - 8} more")
    return lines


def render_stack_config_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok"):
        return [f"config view error: {payload.get('error', 'unknown error')}"]

    stack = payload.get("stack")
    if not isinstance(stack, dict):
        return ["config view unavailable"]

    effective = stack.get("effective", {})
    effective_sources = stack.get("effective_sources", {})
    return [
        "Effective config",
        "",
        f"profile: {stack.get('profile') or 'none'}",
        f"has local config: {stack.get('has_local_config', False)}",
        f"docker network: {effective.get('docker_network', '<unknown>')} ({effective_sources.get('docker_network', 'unknown')})",
        f"traefik url: {effective.get('traefik_url', '<unknown>')} ({effective_sources.get('traefik_url', 'unknown')})",
        f"stack config path: {stack.get('stack_config_path', '<unknown>')}",
    ]


def render_domain_status_detail(hostname: str, payload: dict[str, object]) -> list[str]:
    try:
        validate_bare_domain(hostname)
    except Exception:
        return [
            "Domain status",
            "",
            "Not available for subdomain stacks.",
            "Focus the apex hostname to inspect domain-level DNS and ingress state.",
        ]

    if not payload.get("ok") and "domain" not in payload:
        return [
            "Domain status",
            "",
            f"error: {payload.get('error', 'unknown error')}",
        ]

    lines = [
        "Domain status",
        "",
        f"overall: {payload.get('overall', 'unknown')}",
        f"repairable: {payload.get('repairable', False)}",
        f"manual fix required: {payload.get('manual_fix_required', False)}",
        f"expected tunnel target: {payload.get('expected_tunnel_target', '<unknown>')}",
        f"expected ingress service: {payload.get('expected_ingress_service', '<unknown>')}",
    ]

    coverage_issues = payload.get("coverage_issues")
    if isinstance(coverage_issues, list):
        lines.extend(["", f"coverage issues: {len(coverage_issues)}"])
        for issue in coverage_issues[:4]:
            lines.append(f"- {issue}")
        if len(coverage_issues) > 4:
            lines.append(f"... {len(coverage_issues) - 4} more")

    ingress_warnings = payload.get("ingress_warnings")
    if isinstance(ingress_warnings, list):
        lines.extend(["", f"ingress warnings: {len(ingress_warnings)}"])
        for warning in ingress_warnings[:3]:
            lines.append(f"- {warning}")
        if len(ingress_warnings) > 3:
            lines.append(f"... {len(ingress_warnings) - 3} more")

    dns = payload.get("dns")
    if isinstance(dns, list):
        lines.extend(["", f"dns records: {len(dns)}"])
        for item in dns[:2]:
            if not isinstance(item, dict):
                continue
            status = "ok" if item.get("matches_expected") else "mismatch"
            lines.append(f"- {item.get('record_name', '<unknown>')}: {status} | {item.get('detail', '')}")

    ingress = payload.get("ingress")
    if isinstance(ingress, list):
        lines.extend(["", f"ingress routes: {len(ingress)}"])
        for item in ingress[:2]:
            if not isinstance(item, dict):
                continue
            status = "ok" if item.get("matches_expected") else "mismatch"
            lines.append(f"- {item.get('hostname', '<unknown>')}: {status} | {item.get('detail', '')}")

    suggested_command = payload.get("suggested_command")
    if suggested_command:
        lines.extend(["", f"suggested command: {suggested_command}"])

    return lines
