from __future__ import annotations

import json
import re
import sys
import time

from rich.markup import escape

from homesrvctl.shell import run_command
from homesrvctl.utils import validate_bare_domain

TOOL_ITEMS: list[tuple[str, str]] = [
    ("config", "Config"),
    ("tunnel", "Tunnel"),
    ("cloudflared", "Cloudflared"),
    ("validate", "Validate"),
    ("bootstrap", "Bootstrap"),
]

CONTINUATION_PREFIX = "<<CONT>>"
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RICH_MARKUP_TAG_PATTERN = re.compile(r"(?<!\\)\[/?[^\]]+\]")


def plain_markup(value: object) -> str:
    return escape(ANSI_ESCAPE_PATTERN.sub("", str(value)))


def visible_width(value: object) -> int:
    rendered = ANSI_ESCAPE_PATTERN.sub("", str(value))
    rendered = RICH_MARKUP_TAG_PATTERN.sub("", rendered)
    return len(rendered)


def render_yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def render_tristate_yes_no(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "N/A"


def render_exists(value: object) -> str:
    return "exists" if bool(value) else "does not exist"


def render_tristate_exists(value: object) -> str:
    if value is True:
        return "exists"
    if value is False:
        return "does not exist"
    return "N/A"


def render_optional_value(value: object) -> str:
    if value in {None, ""}:
        return "N/A"
    return str(value)


def build_dashboard_snapshot(run_json_command=None) -> dict[str, object]:  # noqa: ANN001
    if run_json_command is None:
        run_json_command = run_json_subcommand
    list_payload = run_json_command(["list"])
    config_payload = run_json_command(["config", "show"])
    tunnel_payload = run_json_command(["tunnel", "status"])
    cloudflared_payload = run_json_command(["cloudflared", "status"])
    validate_payload = run_json_command(["validate"])
    bootstrap_payload = run_json_command(["bootstrap", "assess"])
    return {
        "list": list_payload,
        "config": config_payload,
        "tunnel": tunnel_payload,
        "cloudflared": cloudflared_payload,
        "validate": validate_payload,
        "bootstrap": bootstrap_payload,
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
    if action == "cleanup":
        return run_json_subcommand(["cleanup", hostname, "--force"])
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
    if tool == "bootstrap":
        if action == "assess":
            return run_json_subcommand(["bootstrap", "assess"])
    raise ValueError(f"unsupported tool action: {tool} {action}")


def run_stack_config_view(hostname: str) -> dict[str, object]:
    return run_json_subcommand(["config", "show", "--stack", hostname])


def run_stack_domain_status(hostname: str) -> dict[str, object]:
    return run_json_subcommand(["domain", "status", hostname])


def run_stack_doctor_view(hostname: str) -> dict[str, object]:
    return run_json_subcommand(["doctor", hostname])


def summarize_stack_action(hostname: str, action: str, payload: dict[str, object]) -> str:
    label = action_label(action)
    if payload.get("ok"):
        restart = payload.get("restart")
        if action in {"domain-add", "domain-repair", "domain-remove"} and isinstance(restart, dict) and not restart.get("ok", True):
            detail = str(restart.get("detail") or "cloudflared restart did not complete")
            return f"{label} partially succeeded for {hostname}: {detail}"
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

    restart = payload.get("restart")
    if isinstance(restart, dict):
        restart_status = "[green]ok[/green]" if restart.get("ok") else "[red]failed[/red]"
        restart_pairs: list[tuple[str, str]] = [("apply status", restart_status)]
        restart_detail = restart.get("detail")
        if restart_detail:
            restart_pairs.append(("apply detail", str(restart_detail)))
        restart_command = restart.get("restart_command")
        if isinstance(restart_command, list) and restart_command:
            restart_pairs.append(("apply command", " ".join(str(part) for part in restart_command)))
        lines.extend(["", *format_key_value_lines(restart_pairs)])

    checks = payload.get("checks")
    if isinstance(checks, list):
        lines.extend(["", *render_check_table(checks, limit=8, normalize_detail=False)])
        return lines

    commands = payload.get("commands")
    if isinstance(commands, list) and commands:
        lines.extend(["", *render_command_table(commands)])
        return lines

    files = payload.get("files")
    if isinstance(files, list) and files:
        lines.extend(["", f"files: {len(files)}", ""])
        for output_path in files[:6]:
            lines.append(f"- {plain_markup(output_path)}")
        if len(files) > 6:
            lines.append(f"... {len(files) - 6} more")
        target_dir = payload.get("target_dir")
        if target_dir:
            lines.extend(["", f"target dir: {plain_markup(target_dir)}"])
        return lines

    error = payload.get("error")
    detail = payload.get("detail")
    if error or detail:
        lines.extend(["", f"detail: {plain_markup(error or detail)}"])
    return lines


def render_check_list_detail(
    checks: list[object],
    *,
    empty_message: str,
    limit: int = 10,
) -> list[str]:
    if not checks:
        return [empty_message]
    return render_check_table(checks, limit=limit, normalize_detail=True)


def render_check_table(
    checks: list[object],
    *,
    limit: int = 10,
    normalize_detail: bool = True,
) -> list[str]:
    failing_checks = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
    advisory_checks = [check for check in checks if isinstance(check, dict) and str(check.get("severity")) == "advisory"]
    rows: list[list[str]] = []
    for check in checks[:limit]:
        if not isinstance(check, dict):
            continue
        name = plain_markup(check.get("name", "<unknown>"))
        detail = normalize_check_detail(name, check.get("detail", "")) if normalize_detail else str(check.get("detail", ""))
        rows.append([check_marker(check), name, plain_markup(detail)])

    lines = [f"checks: {len(checks)} total, {len(failing_checks)} failing, {len(advisory_checks)} advisory", ""]
    if rows:
        lines.extend(render_bordered_table(["status", "check", "detail"], rows))
    if len(checks) > limit:
        lines.append(f"... {len(checks) - limit} more")
    return lines


def check_marker(check: dict[str, object]) -> str:
    severity = str(check.get("severity") or ("pass" if check.get("ok") else "blocking"))
    if severity == "advisory":
        return "[yellow]WARN[/yellow]"
    if check.get("ok"):
        return "[green]PASS[/green]"
    return "[red]FAIL[/red]"


def render_command_table(commands: list[object], *, limit: int = 4) -> list[str]:
    rows: list[list[str]] = []
    for command_result in commands[:limit]:
        if not isinstance(command_result, dict):
            continue
        command = command_result.get("command", [])
        rendered_command = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
        stdout = first_output_line(command_result.get("stdout", ""))
        stderr = first_output_line(command_result.get("stderr", ""))
        rows.append(
            [
                str(command_result.get("returncode", "?")),
                plain_markup(rendered_command),
                plain_markup(stdout or stderr or ""),
            ]
        )

    lines = [f"commands: {len(commands)}", ""]
    if rows:
        lines.extend(render_bordered_table(["rc", "command", "first output"], rows))
    if len(commands) > limit:
        lines.append(f"... {len(commands) - limit} more")
    return lines


def first_output_line(output: object) -> str:
    return str(output or "").strip().splitlines()[0] if str(output or "").strip() else ""

def normalize_check_detail(name: str, detail: object) -> str:
    rendered = str(detail or "").strip()
    lines = [line.strip() for line in rendered.splitlines() if line.strip()]
    if len(lines) >= 2 and lines[-1] == "OK":
        lines = lines[:-1]
    rendered = "\n".join(lines) if lines else rendered
    if name == "cloudflared ingress config":
        prefix = "cloudflared tunnel"
        if rendered.startswith(prefix) and ": " in rendered:
            rendered = rendered.split(": ", 1)[1]
    return rendered or "unknown"


def split_dns_detail(detail: object) -> tuple[str, str | None]:
    rendered = str(detail or "").strip()
    marker = "; ancillary records present: "
    if marker not in rendered:
        return rendered or "unknown", None
    main_detail, ancillary = rendered.split(marker, 1)
    return main_detail.strip() or "unknown", ancillary.strip() or None


def split_ancillary_records(detail: str) -> list[str]:
    return [part.strip() for part in detail.split(", ") if part.strip()]


def split_dns_detail_records(detail: str) -> list[str]:
    parts = [part.strip() for part in detail.split(", ") if part.strip()]
    if len(parts) <= 1:
        return [detail]
    if all(" -> " in part for part in parts):
        return parts
    return [detail]


def format_key_value_with_continuations(label: str, values: list[str]) -> list[str]:
    if not values:
        return []
    lines = [f"{label} : {values[0]}"]
    lines.extend(f"{CONTINUATION_PREFIX}{value}" for value in values[1:])
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

    if tool == "cloudflared" and action == "setup":
        lines.extend(["", *render_cloudflared_setup_detail(payload)])
    if tool == "bootstrap" and action == "assess":
        lines.extend(["", *render_bootstrap_assessment_detail(payload)])

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
                        ("config ok", render_yes_no(config_validation.get("ok", False))),
                        ("config severity", max_severity),
                        ("config detail", normalize_config_validation_detail(config_validation.get("detail", "unknown"))),
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


def normalize_config_validation_detail(detail: object) -> str:
    rendered = str(detail or "unknown")
    lines = [line.strip() for line in rendered.splitlines() if line.strip()]
    if len(lines) >= 2 and lines[-1] == "OK":
        lines = lines[:-1]
    return lines[0] if len(lines) == 1 else "\n".join(lines)


def render_config_payload_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok"):
        return [f"error: {plain_markup(payload.get('error', 'unknown error'))}"]

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
                ("api token present", render_yes_no(global_config.get("cloudflare_api_token_present", False))),
            ]
        ),
    ]

    profiles = global_config.get("profiles")
    if isinstance(profiles, dict):
        profile_names = sorted(str(name) for name in profiles)
        lines.extend(["", *format_key_value_lines([("profiles", str(len(profile_names)))])])
        if profile_names:
            lines.extend(f"- {name}" for name in profile_names[:8])
            if len(profile_names) > 8:
                lines.append(f"... {len(profile_names) - 8} more")
    return lines


def render_stack_config_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok"):
        return [f"config view error: {plain_markup(payload.get('error', 'unknown error'))}"]

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


def render_external_http_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok") and "checks" not in payload:
        return [
            "[bold #ffcf5a]External HTTP[/bold #ffcf5a]",
            "",
            f"status: [red]unavailable[/red]",
            f"detail: {plain_markup(payload.get('error', 'doctor view unavailable'))}",
        ]
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return [
            "[bold #ffcf5a]External HTTP[/bold #ffcf5a]",
            "",
            "status: [red]unavailable[/red]",
            "detail: doctor check data unavailable",
        ]
    external = next(
        (check for check in checks if isinstance(check, dict) and check.get("name") == "external HTTPS request"),
        None,
    )
    if not isinstance(external, dict):
        return [
            "[bold #ffcf5a]External HTTP[/bold #ffcf5a]",
            "",
            "status: [red]unavailable[/red]",
            "detail: external HTTPS check not reported",
        ]
    severity = str(external.get("severity", "pass"))
    if severity == "advisory":
        status = "[yellow]warning[/yellow]"
    elif external.get("ok"):
        status = "[green]ok[/green]"
    else:
        status = "[red]failed[/red]"
    return [
        "[bold #ffcf5a]External HTTP[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("status", status),
                ("detail", plain_markup(external.get("detail", "<unknown>"))),
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
            f"[red]error:[/red] {plain_markup(payload.get('error', 'unknown error'))}",
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
                ("manual fix required", render_yes_no(payload.get("manual_fix_required", False))),
                (
                    "ingress mutations",
                    render_yes_no(payload.get("ingress_mutation_available", False)),
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
        lines.extend(["", *format_key_value_lines([("coverage issues", str(len(coverage_issues)))])])
        for issue in coverage_issues[:4]:
            lines.append(f"- {issue}")
        if len(coverage_issues) > 4:
            lines.append(f"... {len(coverage_issues) - 4} more")

    dns_warnings = payload.get("dns_warnings")
    if isinstance(dns_warnings, list):
        lines.extend(["", *format_key_value_lines([("dns warnings", str(len(dns_warnings)))])])
        for warning in dns_warnings[:3]:
            lines.append(f"- {warning}")
        if len(dns_warnings) > 3:
            lines.append(f"... {len(dns_warnings) - 3} more")

    ingress_warnings = payload.get("ingress_warnings")
    if isinstance(ingress_warnings, list):
        lines.extend(["", *format_key_value_lines([("ingress warnings", str(len(ingress_warnings)))])])
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
        lines.extend(
            [
                "",
                *format_key_value_lines(
                    [("ingress issues", f"{len(ingress_issues)} total, {blocking_count} blocking, {advisory_count} advisory")]
                ),
            ]
        )
        for issue in ingress_issues[:3]:
            if not isinstance(issue, dict):
                continue
            severity = "blocking" if issue.get("blocking") else str(issue.get("severity", "unknown"))
            lines.append(f"- {severity}: {issue.get('message', issue.get('detail', ''))}")
        if len(ingress_issues) > 3:
            lines.append(f"... {len(ingress_issues) - 3} more")

    dns = payload.get("dns")
    if isinstance(dns, list):
        dns_lines: list[str] = []
        for item in dns:
            if not isinstance(item, dict):
                continue
            detail, ancillary = split_dns_detail(item.get("detail", ""))
            row_items = [
                ("hostname", str(item.get("record_name", "<unknown>"))),
                ("match", "[green]ok[/green]" if item.get("matches_expected") else "[red]mismatch[/red]"),
                ("type", str(item.get("record_type") or "<unknown>")),
                ("target", str(item.get("content") or "<unknown>")),
            ]
            dns_lines.extend(
                [
                    *format_key_value_lines(row_items),
                    *(format_key_value_with_continuations("detail", split_dns_detail_records(detail)) if detail else []),
                    *(format_key_value_with_continuations("ancillary records", split_ancillary_records(ancillary)) if ancillary else []),
                    "",
                ]
            )
        if dns_lines:
            if dns_lines[-1] == "":
                dns_lines.pop()
            lines.extend(
                [
                    "",
                    "[bold #ffcf5a]DNS Records[/bold #ffcf5a]",
                    "",
                    *dns_lines,
                ]
            )

    ingress = payload.get("ingress")
    if isinstance(ingress, list):
        ingress_lines: list[str] = []
        for item in ingress:
            if not isinstance(item, dict):
                continue
            ingress_lines.extend(
                [
                    *format_key_value_lines(
                        [
                            ("hostname", str(item.get("hostname", "<unknown>"))),
                            ("match", "[green]ok[/green]" if item.get("matches_expected") else "[red]mismatch[/red]"),
                            ("configured", str(item.get("service") or "<none>")),
                            ("effective", str(item.get("effective_service") or "<none>")),
                            ("detail", str(item.get("detail", ""))),
                        ]
                    ),
                    "",
                ]
            )
        if ingress_lines:
            if ingress_lines[-1] == "":
                ingress_lines.pop()
            lines.extend(
                [
                    "",
                    "[bold #ffcf5a]Ingress Routes[/bold #ffcf5a]",
                    "",
                    *ingress_lines,
                ]
            )

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
    widths = [visible_width(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row[: len(headers)]):
            widths[index] = max(widths[index], visible_width(cell))

    def _render_row(cells: list[str]) -> str:
        padded = [
            f"{cell}{' ' * (widths[index] - visible_width(cell))}"
            for index, cell in enumerate(cells[: len(headers)])
        ]
        return f"│ {' │ '.join(padded)} │"

    top_border = "╭─" + "─┬─".join("─" * width for width in widths) + "─╮"
    header_border = "├─" + "─┼─".join("─" * width for width in widths) + "─┤"
    bottom_border = "╰─" + "─┴─".join("─" * width for width in widths) + "─╯"
    return [
        top_border,
        _render_row(headers),
        header_border,
        *[_render_row(row) for row in rows],
        bottom_border,
    ]


def _render_repairable(payload: dict[str, object]) -> str:
    overall = str(payload.get("overall", "unknown"))
    if overall == "ok":
        return "N/A"
    return render_yes_no(payload.get("repairable", False))


def render_cloudflared_setup_detail(payload: dict[str, object]) -> list[str]:
    lines = [
        "[bold #ffcf5a]Setup Alignment[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("setup state", str(payload.get("setup_state", "unknown"))),
                ("configured path", str(payload.get("configured_path", "<unknown>"))),
                ("credentials path", render_optional_value(payload.get("configured_credentials_path"))),
                ("runtime path", render_optional_value(payload.get("runtime_path"))),
                ("paths aligned", render_tristate_yes_no(payload.get("paths_aligned"))),
                ("configured exists", render_tristate_exists(payload.get("configured_exists"))),
                ("configured writable", render_tristate_yes_no(payload.get("configured_writable"))),
                ("credentials readable", render_tristate_yes_no(payload.get("configured_credentials_readable"))),
                (
                    "account inspection available",
                    render_yes_no(payload.get("account_inspection_available")),
                ),
                (
                    "ingress mutations available",
                    render_yes_no(payload.get("ingress_mutation_available")),
                ),
                ("current user", str(payload.get("current_user") or "<unknown>")),
                (
                    "in homesrvctl group",
                    render_yes_no(payload.get("current_user_in_shared_group")),
                ),
                ("in docker group", render_yes_no(payload.get("current_user_in_docker_group"))),
                (
                    "service control available",
                    render_yes_no(payload.get("service_control_available")),
                ),
            ]
        ),
    ]

    metadata_items: list[tuple[str, str]] = []
    if payload.get("configured_credentials_owner"):
        metadata_items.append(("credentials owner", str(payload.get("configured_credentials_owner"))))
    if payload.get("configured_credentials_group"):
        metadata_items.append(("credentials group", str(payload.get("configured_credentials_group"))))
    if payload.get("configured_credentials_mode"):
        metadata_items.append(("credentials mode", str(payload.get("configured_credentials_mode"))))
    if payload.get("service_user"):
        metadata_items.append(("service user", str(payload.get("service_user"))))
    if payload.get("service_group"):
        metadata_items.append(("service group", str(payload.get("service_group"))))
    if payload.get("shared_group"):
        metadata_items.append(("shared group", str(payload.get("shared_group"))))
    if payload.get("sudoers_path"):
        metadata_items.append(("sudoers path", str(payload.get("sudoers_path"))))
    if payload.get("service_control_command"):
        metadata_items.append(("service control", " ".join(str(part) for part in payload.get("service_control_command", []))))
    if metadata_items:
        lines.extend(["", *format_key_value_lines(metadata_items)])

    notes = payload.get("notes")
    if isinstance(notes, list):
        lines.extend(["", *format_key_value_lines([("notes", str(len(notes)))])])
        for note in notes[:4]:
            lines.append(f"- {note}")
        if len(notes) > 4:
            lines.append(f"... {len(notes) - 4} more")

    issues = payload.get("issues")
    if isinstance(issues, list):
        lines.extend(["", *format_key_value_lines([("setup issues", str(len(issues)))])])
        for issue in issues[:5]:
            lines.append(f"- {issue}")
        if len(issues) > 5:
            lines.append(f"... {len(issues) - 5} more")

    next_commands = payload.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(["", *format_key_value_lines([("next commands", str(len(next_commands)))])])
        for command in next_commands[:6]:
            lines.append(f"- {command}")
        if len(next_commands) > 6:
            lines.append(f"... {len(next_commands) - 6} more")
    return lines


def render_bootstrap_assessment_detail(payload: dict[str, object]) -> list[str]:
    if not payload.get("ok") and "bootstrap_state" not in payload:
        return [
            "[bold #ffcf5a]Bootstrap Assessment[/bold #ffcf5a]",
            "",
            f"[red]error:[/red] {payload.get('error', payload.get('detail', 'unknown error'))}",
        ]

    lines = [
        "[bold #ffcf5a]Bootstrap Assessment[/bold #ffcf5a]",
        "",
        *format_key_value_lines(
            [
                ("bootstrap state", str(payload.get("bootstrap_state", "unknown"))),
                ("host supported", render_yes_no(payload.get("host_supported"))),
                ("detail", str(payload.get("detail", "unknown"))),
                ("config path", str(payload.get("config_path", "<unknown>"))),
            ]
        ),
    ]

    os_payload = payload.get("os")
    if isinstance(os_payload, dict):
        lines.extend(
            [
                "",
                "[bold #ffcf5a]OS[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("name", str(os_payload.get("pretty_name", "unknown"))),
                        ("supported", render_yes_no(os_payload.get("supported"))),
                        ("detail", str(os_payload.get("detail", "unknown"))),
                    ]
                ),
            ]
        )

    packages = payload.get("packages")
    if isinstance(packages, dict):
        lines.extend(
            [
                "",
                "[bold #ffcf5a]Packages[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("docker", render_yes_no(packages.get("docker"))),
                        ("docker compose", render_yes_no(packages.get("docker_compose"))),
                        ("cloudflared", render_yes_no(packages.get("cloudflared"))),
                    ]
                ),
            ]
        )

    services = payload.get("services")
    if isinstance(services, dict):
        cloudflared_active = services.get("cloudflared_active")
        lines.extend(
            [
                "",
                "[bold #ffcf5a]Services[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("Traefik running", render_yes_no(services.get("traefik_running"))),
                        ("cloudflared active", render_tristate_yes_no(cloudflared_active)),
                        ("cloudflared mode", str(services.get("cloudflared_mode", "unknown"))),
                    ]
                ),
            ]
        )

    config_payload = payload.get("config")
    if isinstance(config_payload, dict):
        lines.extend(
            [
                "",
                "[bold #ffcf5a]Config[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("exists", render_tristate_exists(config_payload.get("exists"))),
                        ("valid", render_yes_no(config_payload.get("valid"))),
                        ("token present", render_yes_no(config_payload.get("token_present"))),
                        ("token source", str(config_payload.get("token_source", "unknown"))),
                    ]
                ),
            ]
        )

    network_payload = payload.get("network")
    if isinstance(network_payload, dict):
        exists = network_payload.get("exists")
        lines.extend(
            [
                "",
                "[bold #ffcf5a]Network[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("name", str(network_payload.get("name", "<unknown>"))),
                        ("ready", render_tristate_yes_no(exists)),
                        ("detail", str(network_payload.get("detail", "unknown"))),
                    ]
                ),
            ]
        )

    cloudflare = payload.get("cloudflare")
    if isinstance(cloudflare, dict):
        api_reachable = cloudflare.get("api_reachable")
        lines.extend(
            [
                "",
                "[bold #ffcf5a]Cloudflare[/bold #ffcf5a]",
                "",
                *format_key_value_lines(
                    [
                        ("token present", render_yes_no(cloudflare.get("token_present"))),
                        ("token source", str(cloudflare.get("token_source", "unknown"))),
                        (
                            "API reachable",
                            render_tristate_yes_no(api_reachable),
                        ),
                        ("detail", str(cloudflare.get("detail", "unknown"))),
                    ]
                ),
            ]
        )

    issues = payload.get("issues")
    if isinstance(issues, list):
        lines.extend(["", *format_key_value_lines([("issues", str(len(issues)))])])
        for issue in issues[:6]:
            lines.append(f"- {issue}")
        if len(issues) > 6:
            lines.append(f"... {len(issues) - 6} more")

    next_steps = payload.get("next_steps")
    if isinstance(next_steps, list):
        lines.extend(["", *format_key_value_lines([("next steps", str(len(next_steps)))])])
        for step in next_steps[:6]:
            lines.append(f"- {step}")
        if len(next_steps) > 6:
            lines.append(f"... {len(next_steps) - 6} more")

    return lines
