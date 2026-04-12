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


def _append_scaffold_flags(
    args: list[str],
    *,
    force: bool = False,
    profile: str | None = None,
    docker_network: str | None = None,
    traefik_url: str | None = None,
) -> list[str]:
    if force:
        args.append("--force")
    if profile:
        args.extend(["--profile", profile])
    if docker_network:
        args.extend(["--docker-network", docker_network])
    if traefik_url:
        args.extend(["--traefik-url", traefik_url])
    return args


def _append_domain_flags(
    args: list[str],
    *,
    dry_run: bool = False,
    restart_cloudflared: bool = False,
) -> list[str]:
    if dry_run:
        args.append("--dry-run")
    if restart_cloudflared:
        args.append("--restart-cloudflared")
    return args


def run_stack_action(
    hostname: str,
    action: str,
    template: str | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    profile: str | None = None,
    docker_network: str | None = None,
    traefik_url: str | None = None,
    restart_cloudflared: bool = False,
) -> dict[str, object]:
    if action == "doctor":
        return run_json_subcommand(["doctor", hostname])
    if action == "domain-add":
        return run_json_subcommand(
            _append_domain_flags(
                ["domain", "add", hostname],
                dry_run=dry_run,
                restart_cloudflared=restart_cloudflared,
            )
        )
    if action == "domain-repair":
        return run_json_subcommand(
            _append_domain_flags(
                ["domain", "repair", hostname],
                dry_run=dry_run,
                restart_cloudflared=restart_cloudflared,
            )
        )
    if action == "domain-remove":
        return run_json_subcommand(
            _append_domain_flags(
                ["domain", "remove", hostname],
                dry_run=dry_run,
                restart_cloudflared=restart_cloudflared,
            )
        )
    if action == "init-site":
        return run_json_subcommand(
            _append_scaffold_flags(
                ["site", "init", hostname],
                force=force,
                profile=profile,
                docker_network=docker_network,
                traefik_url=traefik_url,
            )
        )
    if action == "app-init":
        if not template:
            raise ValueError("template is required for app-init")
        return run_json_subcommand(
            _append_scaffold_flags(
                ["app", "init", hostname, "--template", template],
                force=force,
                profile=profile,
                docker_network=docker_network,
                traefik_url=traefik_url,
            )
        )
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
        if action == "setup":
            return run_json_subcommand(["cloudflared", "setup"])
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

    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(["", f"next commands: {len(next_commands)}", ""])
        for command in next_commands[:6]:
            lines.append(str(command))
        if len(next_commands) > 6:
            lines.append(f"... {len(next_commands) - 6} more")

    override_path = payload.get("override_path")
    if override_path:
        lines.extend(["", *format_key_value_lines([("override path", str(override_path))])])

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

    setup = payload.get("setup")
    if isinstance(setup, dict):
        lines.extend(["", *render_cloudflared_setup_detail(setup)])

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
                ("has local config", "yes" if stack.get("has_local_config", False) else "no"),
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
                ("repairable", _render_repairable(payload)),
                ("manual fix required", "yes" if payload.get("manual_fix_required", False) else "no"),
                (
                    "ingress mutations",
                    "yes" if payload.get("ingress_mutation_available", False) else "no",
                ),
                ("expected tunnel target", str(payload.get("expected_tunnel_target", "<unknown>"))),
                ("expected ingress service", str(payload.get("expected_ingress_service", "<unknown>"))),
            ]
        ),
    ]

    ingress_mutation_detail = payload.get("ingress_mutation_detail")
    if ingress_mutation_detail:
        lines.extend(["", *format_key_value_lines([("mutation detail", str(ingress_mutation_detail))])])

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
        rows: list[list[str]] = []
        for item in dns:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    str(item.get("record_name", "<unknown>")),
                    "[green]ok[/green]" if item.get("matches_expected") else "[red]mismatch[/red]",
                    str(item.get("record_type") or "<unknown>"),
                    str(item.get("content") or "<unknown>"),
                    str(item.get("detail", "")),
                ]
            )
        if rows:
            lines.extend(["", "[bold #ffcf5a]DNS Records[/bold #ffcf5a]", "", *render_bordered_table(
                ["hostname", "match", "type", "target", "detail"],
                rows,
            )])

    ingress = payload.get("ingress")
    if isinstance(ingress, list):
        rows = []
        for item in ingress:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    str(item.get("hostname", "<unknown>")),
                    "[green]ok[/green]" if item.get("matches_expected") else "[red]mismatch[/red]",
                    str(item.get("service") or "<none>"),
                    str(item.get("effective_service") or "<none>"),
                    str(item.get("detail", "")),
                ]
            )
        if rows:
            lines.extend(["", "[bold #ffcf5a]Ingress Routes[/bold #ffcf5a]", "", *render_bordered_table(
                ["hostname", "match", "configured", "effective", "detail"],
                rows,
            )])

    suggested_command = payload.get("suggested_command")
    if suggested_command:
        lines.extend(["", *format_key_value_lines([("suggested command", str(suggested_command))])])

    return lines


def format_key_value_lines(items: list[tuple[str, str]]) -> list[str]:
    if not items:
        return []
    width = max(len(label) for label, _ in items)
    return [f"{label.rjust(width)} : {value}" for label, value in items]


def render_bordered_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not headers:
        return []
    if not rows:
        return []
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row[: len(headers)]):
            widths[index] = max(widths[index], len(str(cell)))

    def _render_row(cells: list[str]) -> str:
        padded = [str(cell).ljust(widths[index]) for index, cell in enumerate(cells[: len(headers)])]
        return f"| {' | '.join(padded)} |"

    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    return [
        border,
        _render_row(headers),
        border,
        *[_render_row(row) for row in rows],
        border,
    ]


def _render_repairable(payload: dict[str, object]) -> str:
    overall = str(payload.get("overall", "unknown"))
    if overall == "ok":
        return "N/A"
    return "Yes" if payload.get("repairable", False) else "No"


def render_cloudflared_setup_detail(payload: dict[str, object]) -> list[str]:
    lines = [
        "[bold #ffcf5a]Setup Alignment[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("configured path", str(payload.get("configured_path", "<unknown>"))),
                ("runtime path", str(payload.get("runtime_path") or "<unavailable>")),
                (
                    "paths aligned",
                    "yes" if payload.get("paths_aligned") else "no" if payload.get("paths_aligned") is False else "unknown",
                ),
                ("configured exists", "yes" if payload.get("configured_exists") else "no"),
                ("configured writable", "yes" if payload.get("configured_writable") else "no"),
                (
                    "ingress mutations available",
                    "yes" if payload.get("ingress_mutation_available") else "no",
                ),
            ]
        ),
    ]

    notes = payload.get("notes")
    if isinstance(notes, list):
        lines.extend(["", f"notes: {len(notes)}"])
        for note in notes[:4]:
            lines.append(f"- {note}")
        if len(notes) > 4:
            lines.append(f"... {len(notes) - 4} more")

    issues = payload.get("issues")
    if isinstance(issues, list):
        lines.extend(["", f"setup issues: {len(issues)}"])
        for issue in issues[:5]:
            lines.append(f"- {issue}")
        if len(issues) > 5:
            lines.append(f"... {len(issues) - 5} more")

    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(["", f"next commands: {len(next_commands)}"])
        for command in next_commands[:6]:
            lines.append(f"- {command}")
        if len(next_commands) > 6:
            lines.append(f"... {len(next_commands) - 6} more")
    return lines
