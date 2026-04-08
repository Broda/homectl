from __future__ import annotations

import curses
import time

from homesrvctl.tui.data import build_dashboard_snapshot

SECTIONS = ["stacks", "cloudflared", "validate"]


def run_dashboard(initial_snapshot: dict[str, object], refresh_seconds: float) -> None:
    curses.wrapper(_run_dashboard, initial_snapshot, refresh_seconds)


def render_dashboard(snapshot: dict[str, object], width: int = 100, selected: str = "stacks") -> str:
    lines: list[str] = []
    lines.append("homesrvctl dashboard")
    lines.append("q quit | r refresh | tab/arrow move")
    lines.append("")
    lines.extend(_render_summary(snapshot, width, selected))
    lines.append("")
    lines.extend(_render_detail(snapshot, width, selected))
    lines.append("")
    lines.append(_render_footer(refresh_mode=None))
    lines.append(f"generated: {snapshot.get('generated_at', 'unknown')}")
    return "\n".join(lines)


def _run_dashboard(stdscr, snapshot: dict[str, object], refresh_seconds: float) -> None:  # noqa: ANN001
    curses.curs_set(0)
    stdscr.nodelay(refresh_seconds > 0)
    current = snapshot
    selected_index = 0
    next_refresh = time.monotonic() + refresh_seconds if refresh_seconds > 0 else None

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        refresh_mode = f"auto {refresh_seconds:g}s" if refresh_seconds > 0 else "manual refresh"
        rendered = render_dashboard(current, width=max(width - 1, 40), selected=SECTIONS[selected_index])
        lines = rendered.splitlines()
        if len(lines) >= 2:
            lines[-2] = _render_footer(refresh_mode=refresh_mode)
        for row, line in enumerate(lines):
            if row >= height - 1:
                break
            stdscr.addnstr(row, 0, line, max(width - 1, 1))
        stdscr.refresh()

        timeout_ms = -1
        if refresh_seconds > 0 and next_refresh is not None:
            remaining = max(next_refresh - time.monotonic(), 0.0)
            timeout_ms = int(remaining * 1000)
        stdscr.timeout(timeout_ms)
        key = stdscr.getch()

        if key in {ord("q"), ord("Q")}:
            return
        if key in {ord("r"), ord("R")}:
            current = build_dashboard_snapshot()
            if refresh_seconds > 0:
                next_refresh = time.monotonic() + refresh_seconds
            continue
        if key in {9, curses.KEY_RIGHT, curses.KEY_DOWN, ord("j"), ord("J")}:
            selected_index = (selected_index + 1) % len(SECTIONS)
            continue
        if key in {curses.KEY_LEFT, curses.KEY_UP, ord("k"), ord("K")}:
            selected_index = (selected_index - 1) % len(SECTIONS)
            continue
        if key == -1 and refresh_seconds > 0:
            current = build_dashboard_snapshot()
            next_refresh = time.monotonic() + refresh_seconds


def _render_summary(snapshot: dict[str, object], width: int, selected: str) -> list[str]:
    return [
        _heading("Summary", width),
        _summary_line("stacks", selected, _stacks_summary(snapshot.get("list"))),
        _summary_line("cloudflared", selected, _cloudflared_summary(snapshot.get("cloudflared"))),
        _summary_line("validate", selected, _validate_summary(snapshot.get("validate"))),
    ]


def _render_detail(snapshot: dict[str, object], width: int, selected: str) -> list[str]:
    label = selected.title() if selected != "cloudflared" else "Cloudflared"
    heading = _heading(f"{label} detail", width)
    if selected == "stacks":
        return [heading, *_render_stack_detail(snapshot.get("list"))]
    if selected == "cloudflared":
        return [heading, *_render_cloudflared_detail(snapshot.get("cloudflared"))]
    return [heading, *_render_validate_detail(snapshot.get("validate"))]


def _render_footer(refresh_mode: str | None) -> str:
    mode = refresh_mode or "manual refresh"
    return f"controls: q quit | r refresh | tab/arrow move | mode: {mode}"


def _summary_line(name: str, selected: str, detail: str) -> str:
    marker = ">" if name == selected else " "
    label = name.title() if name != "cloudflared" else "Cloudflared"
    return f"{marker} {label}: {detail}"


def _stacks_summary(payload) -> str:  # noqa: ANN001
    if not isinstance(payload, dict):
        return "unavailable"
    if not payload.get("ok"):
        return f"error: {payload.get('error', 'unknown error')}"
    sites = payload.get("sites", [])
    if not sites:
        return "no stacks found"
    compose_ready = sum(1 for site in sites if site.get("compose"))
    return f"{len(sites)} stack(s), {compose_ready} ready"


def _cloudflared_summary(payload) -> str:  # noqa: ANN001
    if not isinstance(payload, dict):
        return "unavailable"
    runtime = payload.get("mode", "unknown")
    active = "active" if payload.get("active") else "inactive"
    config_validation = payload.get("config_validation")
    if isinstance(config_validation, dict) and config_validation.get("warnings"):
        return f"{runtime} ({active}), {len(config_validation['warnings'])} warning(s)"
    return f"{runtime} ({active})"


def _validate_summary(payload) -> str:  # noqa: ANN001
    if not isinstance(payload, dict):
        return "unavailable"
    checks = payload.get("checks", [])
    failures = [check for check in checks if not check.get("ok")]
    if not checks:
        return "no checks"
    return f"{len(checks)} checks, {len(failures)} failing"


def _render_stack_detail(payload) -> list[str]:  # noqa: ANN001
    if not isinstance(payload, dict):
        return ["unavailable"]
    if not payload.get("ok"):
        return [f"error: {payload.get('error', 'unknown error')}"]
    sites = payload.get("sites", [])
    if not sites:
        return ["no stacks found"]
    lines = []
    for site in sites[:12]:
        status = "compose=yes" if site.get("compose") else "compose=no"
        lines.append(f"- {site.get('hostname', '<unknown>')} [{status}]")
    if len(sites) > 12:
        lines.append(f"... {len(sites) - 12} more")
    return lines


def _render_cloudflared_detail(payload) -> list[str]:  # noqa: ANN001
    if not isinstance(payload, dict):
        return ["unavailable"]
    lines = [
        f"runtime: {payload.get('mode', 'unknown')}",
        f"active: {payload.get('active', False)}",
        f"detail: {payload.get('detail', 'unknown')}",
    ]
    config_validation = payload.get("config_validation")
    if isinstance(config_validation, dict):
        lines.append(f"config ok: {config_validation.get('ok', False)}")
        lines.append(f"config detail: {config_validation.get('detail', 'unknown')}")
        warnings = config_validation.get("warnings", [])
        if warnings:
            lines.append("warnings:")
            for warning in warnings[:5]:
                lines.append(f"- {warning}")
        else:
            lines.append("warnings: none")
    return lines


def _render_validate_detail(payload) -> list[str]:  # noqa: ANN001
    if not isinstance(payload, dict):
        return ["unavailable"]
    if not payload.get("ok") and "checks" not in payload:
        return [f"error: {payload.get('error', 'unknown error')}"]
    checks = payload.get("checks", [])
    failures = [check for check in checks if not check.get("ok")]
    if not failures:
        return ["all validation checks passing"]
    lines = []
    for check in failures[:10]:
        lines.append(f"- {check.get('name', '<unknown>')}: {check.get('detail', '')}")
    if len(failures) > 10:
        lines.append(f"... {len(failures) - 10} more")
    return lines


def _heading(label: str, width: int) -> str:
    rule = "=" * max(min(width - len(label) - 3, 40), 8)
    return f"{label} {rule}"
