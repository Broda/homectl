from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from homesrvctl.tui.data import build_dashboard_snapshot, run_stack_action, stack_sites, summarize_stack_action

SECTIONS = ["stacks", "cloudflared", "validate"]


class HomesrvctlTextualApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #11161d;
        color: #d9e1ea;
    }

    #body {
        layout: horizontal;
        height: 1fr;
    }

    #sidebar {
        width: 38;
        min-width: 32;
        padding: 1 1;
        background: #18212b;
        border: round #3f556b;
    }

    #content {
        width: 1fr;
        padding: 1 1;
        background: #0f141b;
    }

    #summary_title, #stack_title, #detail_title, #status_title {
        color: #8bc6ff;
        text-style: bold;
        margin-bottom: 1;
    }

    #summary, #stack_list, #detail, #status {
        padding: 0 1;
    }

    #stack_list {
        height: 1fr;
    }

    #detail_box {
        height: 1fr;
        border: round #3f556b;
        padding: 1 1;
        margin-bottom: 1;
    }

    #status_box {
        height: 5;
        border: round #3f556b;
        padding: 1 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("w,up", "previous_section", "Prev Section", show=False),
        Binding("s,down,tab", "next_section", "Next Section", show=False),
        Binding("a,left", "previous_stack", "Prev Stack", show=False),
        Binding("d,right", "next_stack", "Next Stack", show=False),
        Binding("i", "site_init", "Init Site", show=False),
        Binding("g", "doctor", "Doctor", show=False),
        Binding("u", "up", "Up", show=False),
        Binding("t", "restart", "Restart", show=False),
        Binding("x", "down", "Down", show=False),
    ]

    def __init__(self, refresh_seconds: float = 0.0) -> None:
        super().__init__()
        self.refresh_seconds = refresh_seconds
        self.snapshot: dict[str, object] = {}
        self.selected_section_index = 0
        self.selected_stack_index = 0
        self.status_message = "dashboard starting"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("Summary", id="summary_title")
                yield Static("", id="summary")
                yield Static("Stacks", id="stack_title")
                yield Static("", id="stack_list")
            with Vertical(id="content"):
                yield Static("Detail", id="detail_title")
                yield Static("", id="detail_box")
                yield Static("Status", id="status_title")
                yield Static("", id="status_box")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_snapshot("dashboard ready")
        if self.refresh_seconds > 0:
            self.set_interval(self.refresh_seconds, self._auto_refresh)

    def action_refresh(self) -> None:
        self._refresh_snapshot("dashboard refreshed")

    def action_next_section(self) -> None:
        self.selected_section_index = (self.selected_section_index + 1) % len(SECTIONS)
        self._render()

    def action_previous_section(self) -> None:
        self.selected_section_index = (self.selected_section_index - 1) % len(SECTIONS)
        self._render()

    def action_next_stack(self) -> None:
        sites = stack_sites(self.snapshot)
        if not sites:
            self.status_message = "no stacks available"
            self._render()
            return
        self.selected_stack_index = (self.selected_stack_index + 1) % len(sites)
        self._render()

    def action_previous_stack(self) -> None:
        sites = stack_sites(self.snapshot)
        if not sites:
            self.status_message = "no stacks available"
            self._render()
            return
        self.selected_stack_index = (self.selected_stack_index - 1) % len(sites)
        self._render()

    def action_site_init(self) -> None:
        self._run_selected_stack_action("init-site")

    def action_doctor(self) -> None:
        self._run_selected_stack_action("doctor")

    def action_up(self) -> None:
        self._run_selected_stack_action("up")

    def action_restart(self) -> None:
        self._run_selected_stack_action("restart")

    def action_down(self) -> None:
        self._run_selected_stack_action("down")

    def _auto_refresh(self) -> None:
        self._refresh_snapshot("dashboard refreshed")

    def _refresh_snapshot(self, status_message: str) -> None:
        self.snapshot = build_dashboard_snapshot()
        sites = stack_sites(self.snapshot)
        if sites:
            self.selected_stack_index = max(0, min(self.selected_stack_index, len(sites) - 1))
        else:
            self.selected_stack_index = 0
        self.status_message = status_message
        self._render()

    def _run_selected_stack_action(self, action: str) -> None:
        sites = stack_sites(self.snapshot)
        if not sites:
            self.status_message = "no stacks available"
            self._render()
            return
        hostname = str(sites[self.selected_stack_index].get("hostname", ""))
        payload = run_stack_action(hostname, action)
        self.status_message = summarize_stack_action(hostname, action, payload)
        self.snapshot = build_dashboard_snapshot()
        sites = stack_sites(self.snapshot)
        if sites:
            self.selected_stack_index = max(0, min(self.selected_stack_index, len(sites) - 1))
        else:
            self.selected_stack_index = 0
        self._render()

    def _render(self) -> None:
        self.query_one("#summary", Static).update(self._summary_text())
        self.query_one("#stack_list", Static).update(self._stack_list_text())
        self.query_one("#detail_box", Static).update(self._detail_text())
        self.query_one("#status_box", Static).update(self._status_text())

    def _summary_text(self) -> str:
        selected = SECTIONS[self.selected_section_index]
        lines = [
            self._summary_line("stacks", self._stacks_summary(), selected),
            self._summary_line("cloudflared", self._cloudflared_summary(), selected),
            self._summary_line("validate", self._validate_summary(), selected),
        ]
        return "\n".join(lines)

    def _stack_list_text(self) -> str:
        sites = stack_sites(self.snapshot)
        if not sites:
            return "no stacks found"
        selected_index = max(0, min(self.selected_stack_index, len(sites) - 1))
        selected_site = sites[selected_index]
        lines = [
            f"selected: {selected_site.get('hostname', '<unknown>')}",
            f"compose: {'yes' if selected_site.get('compose') else 'no'}",
            "actions: a/d i g u t x",
            "",
        ]
        for site in sites[:12]:
            marker = ">" if site is selected_site else "-"
            status = "compose=yes" if site.get("compose") else "compose=no"
            lines.append(f"{marker} {site.get('hostname', '<unknown>')} [{status}]")
        if len(sites) > 12:
            lines.append(f"... {len(sites) - 12} more")
        return "\n".join(lines)

    def _detail_text(self) -> str:
        section = SECTIONS[self.selected_section_index]
        if section == "stacks":
            return self._stack_detail_text()
        if section == "cloudflared":
            return self._cloudflared_detail_text()
        return self._validate_detail_text()

    def _status_text(self) -> str:
        mode = f"auto refresh {self.refresh_seconds:g}s" if self.refresh_seconds > 0 else "manual refresh"
        lines = [
            self.status_message,
            f"mode: {mode}",
            f"generated: {self.snapshot.get('generated_at', 'unknown')}",
            "keys: q quit | r refresh | w/s section | a/d stack | i/g/u/t/x actions",
        ]
        return "\n".join(lines)

    def _summary_line(self, name: str, detail: str, selected: str) -> str:
        marker = ">" if name == selected else " "
        label = name.title() if name != "cloudflared" else "Cloudflared"
        return f"{marker} {label}: {detail}"

    def _stacks_summary(self) -> str:
        payload = self.snapshot.get("list")
        if not isinstance(payload, dict):
            return "unavailable"
        if not payload.get("ok"):
            return f"error: {payload.get('error', 'unknown error')}"
        sites = payload.get("sites", [])
        if not sites:
            return "no stacks found"
        compose_ready = sum(1 for site in sites if site.get("compose"))
        return f"{len(sites)} stack(s), {compose_ready} ready"

    def _cloudflared_summary(self) -> str:
        payload = self.snapshot.get("cloudflared")
        if not isinstance(payload, dict):
            return "unavailable"
        runtime = payload.get("mode", "unknown")
        active = "active" if payload.get("active") else "inactive"
        config_validation = payload.get("config_validation")
        if isinstance(config_validation, dict) and config_validation.get("warnings"):
            return f"{runtime} ({active}), {len(config_validation['warnings'])} warning(s)"
        return f"{runtime} ({active})"

    def _validate_summary(self) -> str:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "unavailable"
        checks = payload.get("checks", [])
        failures = [check for check in checks if not check.get("ok")]
        if not checks:
            return "no checks"
        return f"{len(checks)} checks, {len(failures)} failing"

    def _stack_detail_text(self) -> str:
        payload = self.snapshot.get("list")
        if not isinstance(payload, dict):
            return "unavailable"
        if not payload.get("ok"):
            return f"error: {payload.get('error', 'unknown error')}"
        sites = stack_sites(self.snapshot)
        if not sites:
            return "no stacks found"
        selected_site = sites[max(0, min(self.selected_stack_index, len(sites) - 1))]
        lines = [
            "Stacks Detail",
            "",
            f"hostname: {selected_site.get('hostname', '<unknown>')}",
            f"compose file: {'yes' if selected_site.get('compose') else 'no'}",
            "",
            "Use i to scaffold a site for an empty hostname directory,",
            "then u to start it and g to run doctor checks.",
        ]
        return "\n".join(lines)

    def _cloudflared_detail_text(self) -> str:
        payload = self.snapshot.get("cloudflared")
        if not isinstance(payload, dict):
            return "unavailable"
        lines = [
            "Cloudflared Detail",
            "",
            f"runtime: {payload.get('mode', 'unknown')}",
            f"active: {payload.get('active', False)}",
            f"detail: {payload.get('detail', 'unknown')}",
        ]
        config_validation = payload.get("config_validation")
        if isinstance(config_validation, dict):
            lines.append(f"config ok: {config_validation.get('ok', False)}")
            lines.append(f"config detail: {config_validation.get('detail', 'unknown')}")
            warnings = config_validation.get("warnings", [])
            lines.append("")
            if warnings:
                lines.append("warnings:")
                lines.extend(f"- {warning}" for warning in warnings[:5])
            else:
                lines.append("warnings: none")
        return "\n".join(lines)

    def _validate_detail_text(self) -> str:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "unavailable"
        if not payload.get("ok") and "checks" not in payload:
            return f"error: {payload.get('error', 'unknown error')}"
        checks = payload.get("checks", [])
        failures = [check for check in checks if not check.get("ok")]
        if not failures:
            return "all validation checks passing"
        lines = ["Validate Detail", ""]
        for check in failures[:10]:
            lines.append(f"- {check.get('name', '<unknown>')}: {check.get('detail', '')}")
        if len(failures) > 10:
            lines.append(f"... {len(failures) - 10} more")
        return "\n".join(lines)
