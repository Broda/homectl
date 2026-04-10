from __future__ import annotations

import json
import sys
import time

from homesrvctl.shell import run_command
from homesrvctl.utils import validate_bare_domain

TOOL_ITEMS: list[tuple[str, str]] = [
    ("config", "Config"),
    ("tunnel", "Tunnel"),
    ("cloudflared", "Cloudflared"),
    ("validate", "Validate"),
]


def build_dashboard_snapshot(run_json_command=None) -> dict[str, object]:  # noqa: ANN001
    if run_json_command is None:
        run_json_command = run_json_subcommand
    list_payload = run_json_command(["list"])
    config_payload = run_json_command(["config", "show"])
    tunnel_payload = run_json_command(["tunnel", "status"])
    cloudflared_payload = run_json_command(["cloudflared", "status"])
    validate_payload = run_json_command(["validate"])
    return {
        "list": list_payload,
        "config": config_payload,
        "tunnel": tunnel_payload,
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
    if action == "domain-add":
        return run_json_subcommand(["domain", "add", hostname])
    if action == "domain-repair":
        return run_json_subcommand(["domain", "repair", hostname])
    if action == "domain-remove":
        return run_json_subcommand(["domain", "remove", hostname])
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


def run_tool_action(
    tool: str,
    action: str,
    *,
    force: bool = False,
    follow: bool = False,
) -> dict[str, object]:
    if tool == "config":
        if action == "init":
            args = ["config", "init"]
            if force:
                args.append("--force")
            return run_json_subcommand(args)
        if action == "show":
            return run_json_subcommand(["config", "show"])
    if tool == "tunnel":
        if action == "show":
            return run_json_subcommand(["tunnel", "status"])
    if tool == "cloudflared":
        if action == "config-test":
            return run_json_subcommand(["cloudflared", "config-test"])
        if action == "logs":
            args = ["cloudflared", "logs"]
            if follow:
                args.append("--follow")
            return run_json_subcommand(args)
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
    if action == "domain-add":
        return "domain add"
    if action == "domain-repair":
        return "domain repair"
    if action == "domain-remove":
        return "domain remove"
    return action


def render_stack_action_detail(action: str, payload: dict[str, object]) -> list[str]:
    label = action_label(action)
    ok = payload.get("ok")
    status_markup = "[green]ok[/green]" if ok else "[red]failed[/red]"
    lines = [
        "[bold #ffcf5a]Last action[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("action", label),
                ("status", status_markup),
            ]
        ),
    ]

    if "dry_run" in payload:
        lines.extend(format_key_value_lines([("dry run", "yes" if payload.get("dry_run") else "no")]))

    template = payload.get("template")
    if template:
        lines.extend(format_key_value_lines([("template", str(template))]))

    checks = payload.get("checks")
    if isinstance(checks, list):
        failing_checks = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
        advisory_checks = [
            check for check in checks if isinstance(check, dict) and str(check.get("severity")) == "advisory"
        ]
        lines.extend(
            [
                "",
                f"checks: {len(checks)} total, {len(failing_checks)} failing, {len(advisory_checks)} advisory",
                "",
            ]
        )
        for check in checks[:8]:
            if not isinstance(check, dict):
                continue
            severity = str(check.get("severity") or ("pass" if check.get("ok") else "blocking"))
            if severity == "advisory":
                marker = "[yellow]WARN[/yellow]"
            elif check.get("ok"):
                marker = "[green]PASS[/green]"
            else:
                marker = "[red]FAIL[/red]"
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
    ok = payload.get("ok")
    status_markup = "[green]ok[/green]" if ok else "[red]failed[/red]"
    lines = [
        "[bold #ffcf5a]Last action[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("tool", tool),
                ("action", action),
                ("status", status_markup),
            ]
        ),
    ]

    if "dry_run" in payload:
        lines.extend(format_key_value_lines([("dry run", "yes" if payload.get("dry_run") else "no")]))

    if "follow" in payload:
        lines.extend(format_key_value_lines([("follow", "yes" if payload.get("follow") else "no")]))

    detail = payload.get("detail")
    if detail:
        lines.extend(["", *format_key_value_lines([("detail", str(detail))])])

    logs_command = payload.get("logs_command")
    if isinstance(logs_command, list) and logs_command:
        rendered_command = " ".join(str(part) for part in logs_command)
        lines.extend(["", *format_key_value_lines([("logs command", rendered_command)])])

    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        lines.extend(["", f"warnings: {len(warnings)}", ""])
        for warning in warnings[:5]:
            lines.append(f"- {warning}")
        if len(warnings) > 5:
            lines.append(f"... {len(warnings) - 5} more")

    issues = payload.get("issues")
    if isinstance(issues, list):
        blocking_count = sum(1 for issue in issues if isinstance(issue, dict) and issue.get("blocking"))
        advisory_count = sum(
            1 for issue in issues if isinstance(issue, dict) and issue.get("severity") == "advisory"
        )
        lines.extend(["", f"issues: {len(issues)} total, {blocking_count} blocking, {advisory_count} advisory", ""])
        for issue in issues[:5]:
            if not isinstance(issue, dict):
                continue
            severity = "blocking" if issue.get("blocking") else str(issue.get("severity", "unknown"))
            lines.append(f"- {severity}: {issue.get('message', issue.get('detail', ''))}")
        if len(issues) > 5:
            lines.append(f"... {len(issues) - 5} more")

    config_validation = payload.get("config_validation")
    if isinstance(config_validation, dict):
        max_severity = str(config_validation.get("max_severity") or "none")
        lines.extend(
            [
                "",
                *format_key_value_lines(
                    [
                        ("config ok", str(config_validation.get("ok", False))),
                        ("config severity", max_severity),
                        ("config detail", str(config_validation.get("detail", "unknown"))),
                    ]
                ),
            ]
        )
        validation_warnings = config_validation.get("warnings", [])
        if isinstance(validation_warnings, list):
            lines.extend(["", f"config warnings: {len(validation_warnings)}", ""])
            for warning in validation_warnings[:5]:
                lines.append(f"- {warning}")
            if len(validation_warnings) > 5:
                lines.append(f"... {len(validation_warnings) - 5} more")
        validation_issues = config_validation.get("issues", [])
        if isinstance(validation_issues, list):
            blocking_count = sum(
                1 for issue in validation_issues if isinstance(issue, dict) and issue.get("blocking")
            )
            advisory_count = sum(
                1 for issue in validation_issues if isinstance(issue, dict) and issue.get("severity") == "advisory"
            )
            lines.extend(["", f"config issues: {len(validation_issues)} total, {blocking_count} blocking, {advisory_count} advisory", ""])
            for issue in validation_issues[:5]:
                if not isinstance(issue, dict):
                    continue
                severity = "blocking" if issue.get("blocking") else str(issue.get("severity", "unknown"))
                lines.append(f"- {severity}: {issue.get('message', issue.get('detail', ''))}")
            if len(validation_issues) > 5:
                lines.append(f"... {len(validation_issues) - 5} more")

    return lines


def render_config_payload_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok"):
        return [f"error: {payload.get('error', 'unknown error')}"]

    global_config = payload.get("global")
    if not isinstance(global_config, dict):
        return ["global config unavailable"]

    lines = [
        *format_key_value_lines([("config path", str(payload.get("config_path", "<unknown>")))]),
        "",
        *format_key_value_lines(
            [
                ("sites root", str(global_config.get("sites_root", "<unknown>"))),
                ("docker network", str(global_config.get("docker_network", "<unknown>"))),
                ("traefik url", str(global_config.get("traefik_url", "<unknown>"))),
                ("cloudflared config", str(global_config.get("cloudflared_config", "<unknown>"))),
                ("api token present", str(global_config.get("cloudflare_api_token_present", False))),
            ]
        ),
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
        "[bold #ffcf5a]Effective config[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("profile", str(stack.get("profile") or "none")),
                ("has local config", str(stack.get("has_local_config", False))),
                (
                    "docker network",
                    f"{effective.get('docker_network', '<unknown>')} ({effective_sources.get('docker_network', 'unknown')})",
                ),
                (
                    "traefik url",
                    f"{effective.get('traefik_url', '<unknown>')} ({effective_sources.get('traefik_url', 'unknown')})",
                ),
                ("stack config path", str(stack.get("stack_config_path", "<unknown>"))),
            ]
        ),
    ]


def render_domain_status_detail(hostname: str, payload: dict[str, object]) -> list[str]:
    try:
        validate_bare_domain(hostname)
    except Exception:
        return [
            "[bold #ffcf5a]Domain status[/bold #ffcf5a]",
            "",
            "Not available for subdomain stacks.",
            "Focus the apex hostname to inspect domain-level DNS and ingress state.",
        ]

    if not payload.get("ok") and "domain" not in payload:
        return [
            "[bold #ffcf5a]Domain status[/bold #ffcf5a]",
            "",
            f"[red]error:[/red] {payload.get('error', 'unknown error')}",
        ]

    overall = str(payload.get("overall", "unknown"))
    if overall == "ok":
        overall_markup = "[green]ok[/green]"
    elif overall == "partial":
        overall_markup = "[yellow]partial[/yellow]"
    else:
        overall_markup = f"[red]{overall}[/red]"

    lines = [
        "[bold #ffcf5a]Domain status[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("overall", overall_markup),
                ("repairable", str(payload.get("repairable", False))),
                ("manual fix required", str(payload.get("manual_fix_required", False))),
                ("expected tunnel target", str(payload.get("expected_tunnel_target", "<unknown>"))),
                ("expected ingress service", str(payload.get("expected_ingress_service", "<unknown>"))),
            ]
        ),
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
    ingress_issues = payload.get("ingress_issues")
    if isinstance(ingress_issues, list):
        blocking_count = sum(1 for issue in ingress_issues if isinstance(issue, dict) and issue.get("blocking"))
        advisory_count = sum(
            1 for issue in ingress_issues if isinstance(issue, dict) and issue.get("severity") == "advisory"
        )
        lines.extend(["", f"ingress issues: {len(ingress_issues)} total, {blocking_count} blocking, {advisory_count} advisory"])
        for issue in ingress_issues[:3]:
            if not isinstance(issue, dict):
                continue
            severity = "blocking" if issue.get("blocking") else str(issue.get("severity", "unknown"))
            lines.append(f"- {severity}: {issue.get('message', issue.get('detail', ''))}")
        if len(ingress_issues) > 3:
            lines.append(f"... {len(ingress_issues) - 3} more")

    dns = payload.get("dns")
    if isinstance(dns, list):
        lines.extend(["", f"dns records: {len(dns)}"])
        for item in dns[:2]:
            if not isinstance(item, dict):
                continue
            if item.get("matches_expected"):
                status = "[green]ok[/green]"
            else:
                status = "[red]mismatch[/red]"
            lines.append(f"- {item.get('record_name', '<unknown>')}: {status} | {item.get('detail', '')}")

    ingress = payload.get("ingress")
    if isinstance(ingress, list):
        lines.extend(["", f"ingress routes: {len(ingress)}"])
        for item in ingress[:2]:
            if not isinstance(item, dict):
                continue
            if item.get("matches_expected"):
                status = "[green]ok[/green]"
            else:
                status = "[red]mismatch[/red]"
            lines.append(f"- {item.get('hostname', '<unknown>')}: {status} | {item.get('detail', '')}")

    suggested_command = payload.get("suggested_command")
    if suggested_command:
        lines.extend(["", *format_key_value_lines([("suggested command", str(suggested_command))])])

    return lines


def format_key_value_lines(items: list[tuple[str, str]]) -> list[str]:
    if not items:
        return []
    width = max(len(label) for label, _ in items)
    return [f"{label.rjust(width)} : {value}" for label, value in items]
