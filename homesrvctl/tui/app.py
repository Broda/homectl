from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Static

from homesrvctl.tui.data import (
    build_dashboard_snapshot,
    render_stack_action_detail,
    run_stack_action,
    stack_sites,
    summarize_stack_action,
)


class HomesrvctlTextualApp(App[None]):
    TITLE = "Home Server Controller"
    CSS = """
    Screen {
        layout: vertical;
        background: #081014;
        color: #d7fff7;
    }

    Header {
        background: #0fa697;
        color: #081014;
    }

    HeaderClock {
        color: #081014;
    }

    #summary_strip {
        layout: horizontal;
        width: 100%;
        height: 9;
        padding: 1 2 0 2;
    }

    .summary_card {
        width: 1fr;
        height: 1fr;
        margin-right: 1;
        padding: 1 2;
        background: #0d161b;
        border: round #1fd6c1;
        color: #d7fff7;
    }

    .summary_card:last-child {
        margin-right: 0;
    }

    .card_title {
        color: #ffcf5a;
        text-style: bold;
        margin-bottom: 1;
    }

    #body {
        layout: horizontal;
        width: 100%;
        height: 1fr;
        padding: 0 2 0 2;
    }

    #controls_pane {
        width: 42;
        min-width: 34;
        margin-right: 1;
        padding: 1 2;
        background: #0b1419;
        border: round #13bfae;
    }

    #detail_pane {
        width: 1fr;
        min-width: 0;
        padding: 1 2;
        background: #091116;
        border: round #0fa697;
    }

    .pane_title {
        color: #ffcf5a;
        text-style: bold;
        margin-bottom: 1;
    }

    #controls_box, #detail_box, #command_bar {
        padding: 0 1;
    }

    #controls_box, #detail_box {
        height: 1fr;
    }

    #command_bar {
        layout: horizontal;
        width: 100%;
        height: 3;
        margin: 0;
        padding: 0 2;
        background: #0fa697;
        color: #081014;
        border: none;
    }

    #command_bar_text {
        width: 1fr;
        height: 1fr;
        background: #0fa697;
        color: #081014;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("w,up", "previous_control", "Prev", show=False),
        Binding("s,down,tab", "next_control", "Next", show=False),
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
        self.selected_control_index = 0
        self.status_message = "dashboard starting"
        self.last_stack_actions: dict[str, dict[str, object]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="summary_strip"):
            yield Static("", id="summary_stacks", classes="summary_card")
            yield Static("", id="summary_cloudflared", classes="summary_card")
            yield Static("", id="summary_validate", classes="summary_card")
        with Horizontal(id="body"):
            with Vertical(id="controls_pane"):
                yield Static("Controls", classes="pane_title")
                yield Static("", id="controls_box")
            with Vertical(id="detail_pane"):
                yield Static("Detail", classes="pane_title")
                yield Static("", id="detail_box")
        with Horizontal(id="command_bar"):
            yield Static("", id="command_bar_text")

    def on_mount(self) -> None:
        self._refresh_snapshot("dashboard ready")
        if self.refresh_seconds > 0:
            self.set_interval(self.refresh_seconds, self._auto_refresh)

    def action_refresh(self) -> None:
        self._refresh_snapshot("dashboard refreshed")

    def action_next_control(self) -> None:
        items = self._control_items()
        if not items:
            return
        self.selected_control_index = (self.selected_control_index + 1) % len(items)
        self._render()

    def action_previous_control(self) -> None:
        items = self._control_items()
        if not items:
            return
        self.selected_control_index = (self.selected_control_index - 1) % len(items)
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
        items = self._control_items()
        if items:
            self.selected_control_index = max(0, min(self.selected_control_index, len(items) - 1))
        else:
            self.selected_control_index = 0
        self.status_message = status_message
        self._render()

    def _run_selected_stack_action(self, action: str) -> None:
        item = self._selected_control_item()
        if item.get("kind") != "stack":
            self.status_message = "select a stack to run stack actions"
            self._render()
            return
        hostname = str(item.get("hostname", ""))
        payload = run_stack_action(hostname, action)
        self.last_stack_actions[hostname] = {"action": action, "payload": payload}
        self.status_message = summarize_stack_action(hostname, action, payload)
        self.snapshot = build_dashboard_snapshot()
        items = self._control_items()
        if items:
            self.selected_control_index = min(self.selected_control_index, len(items) - 1)
        else:
            self.selected_control_index = 0
        self._render()

    def _render(self) -> None:
        self.query_one("#summary_stacks", Static).update(self._summary_card("Stacks", self._stacks_summary()))
        self.query_one("#summary_cloudflared", Static).update(self._summary_card("Cloudflared", self._cloudflared_summary()))
        self.query_one("#summary_validate", Static).update(self._summary_card("Validate", self._validate_summary()))
        self.query_one("#controls_box", Static).update(self._control_list_text())
        self.query_one("#detail_box", Static).update(self._detail_text())
        self.query_one("#command_bar_text", Static).update(self._command_bar_text())

    def _summary_card(self, title: str, detail: str) -> str:
        return f"{title}\n\n{detail}"

    def _control_items(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = [
            {"kind": "tool", "tool": "cloudflared", "label": "Cloudflared"},
            {"kind": "tool", "tool": "validate", "label": "Validate"},
        ]
        for site in stack_sites(self.snapshot):
            hostname = str(site.get("hostname", "<unknown>"))
            items.append(
                {
                    "kind": "stack",
                    "hostname": hostname,
                    "compose": bool(site.get("compose")),
                    "label": hostname,
                }
            )
        return items

    def _selected_control_item(self) -> dict[str, object]:
        items = self._control_items()
        if not items:
            return {"kind": "tool", "tool": "cloudflared", "label": "Cloudflared"}
        index = max(0, min(self.selected_control_index, len(items) - 1))
        return items[index]

    def _control_list_text(self) -> str:
        items = self._control_items()
        if not items:
            return "Tools\n\n> Cloudflared\n  Validate\n\nStacks\n\n(no stacks found)"

        tool_count = 2
        lines = ["Tools", ""]
        for index, item in enumerate(items[:tool_count]):
            marker = ">" if index == self.selected_control_index else " "
            lines.append(f"{marker} {item['label']}")

        lines.extend(["", "Stacks", ""])
        stack_items = items[tool_count:]
        if not stack_items:
            lines.append("(no stacks found)")
            return "\n".join(lines)

        for offset, item in enumerate(stack_items):
            index = tool_count + offset
            marker = ">" if index == self.selected_control_index else " "
            compose = "compose=yes" if item.get("compose") else "compose=no"
            lines.append(f"{marker} {item['label']} [{compose}]")
        return "\n".join(lines)

    def _detail_text(self) -> str:
        item = self._selected_control_item()
        if item.get("kind") == "tool":
            if item.get("tool") == "cloudflared":
                return self._cloudflared_detail_text()
            return self._validate_detail_text()
        return self._stack_detail_text(str(item.get("hostname", "")), bool(item.get("compose")))

    def _command_bar_text(self) -> str:
        item = self._selected_control_item()
        mode = f"auto refresh {self.refresh_seconds:g}s" if self.refresh_seconds > 0 else "manual refresh"
        if item.get("kind") == "stack":
            focus = f"focus: {item.get('hostname', '<unknown>')}"
            actions = "actions: i init | g doctor | u up | t restart | x down | r refresh | q quit"
        else:
            focus = f"focus: {item.get('label', 'Tool')}"
            actions = "actions: w/s move | r refresh | q quit"
        return "\n".join([focus, actions, f"status: {self.status_message} | mode: {mode}"])

    def _stacks_summary(self) -> str:
        payload = self.snapshot.get("list")
        if not isinstance(payload, dict):
            return "Unavailable"
        if not payload.get("ok"):
            return f"Error\n\n{payload.get('error', 'unknown error')}"
        sites = payload.get("sites", [])
        if not sites:
            return "No stacks\n\nNothing scaffolded yet."
        compose_ready = sum(1 for site in sites if site.get("compose"))
        return f"{len(sites)} stack(s)\n\n{compose_ready} ready for compose actions"

    def _cloudflared_summary(self) -> str:
        payload = self.snapshot.get("cloudflared")
        if not isinstance(payload, dict):
            return "Unavailable"
        runtime = payload.get("mode", "unknown")
        active = "active" if payload.get("active") else "inactive"
        config_validation = payload.get("config_validation")
        if isinstance(config_validation, dict) and config_validation.get("warnings"):
            return f"{runtime} ({active})\n\n{len(config_validation['warnings'])} warning(s)"
        return f"{runtime} ({active})\n\n{payload.get('detail', 'no detail')}"

    def _validate_summary(self) -> str:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "Unavailable"
        checks = payload.get("checks", [])
        failures = [check for check in checks if not check.get("ok")]
        if not checks:
            return "No checks\n\nValidation returned no checks."
        if failures:
            return f"{len(checks)} checks\n\n{len(failures)} failing"
        return f"{len(checks)} checks\n\nAll passing"

    def _stack_detail_text(self, hostname: str, compose: bool) -> str:
        lines = [
            "Stack Detail",
            "",
            f"hostname: {hostname or '<unknown>'}",
            f"compose file: {'yes' if compose else 'no'}",
            "",
            "This pane is the control surface for stack lifecycle work.",
            "Use i to scaffold a simple site if the hostname directory is empty.",
            "Use u to start the stack, g to run doctor, t to restart, or x to stop it.",
        ]
        cached = self.last_stack_actions.get(hostname)
        if isinstance(cached, dict):
            action = cached.get("action")
            payload = cached.get("payload")
            if isinstance(action, str) and isinstance(payload, dict):
                lines.extend(["", *render_stack_action_detail(action, payload)])
        return "\n".join(lines)

    def _cloudflared_detail_text(self) -> str:
        payload = self.snapshot.get("cloudflared")
        if not isinstance(payload, dict):
            return "Cloudflared detail unavailable"
        lines = [
            "Cloudflared Detail",
            "",
            f"runtime: {payload.get('mode', 'unknown')}",
            f"active: {payload.get('active', False)}",
            f"detail: {payload.get('detail', 'unknown')}",
        ]
        config_validation = payload.get("config_validation")
        if isinstance(config_validation, dict):
            lines.extend(
                [
                    "",
                    f"config ok: {config_validation.get('ok', False)}",
                    f"config detail: {config_validation.get('detail', 'unknown')}",
                ]
            )
            warnings = config_validation.get("warnings", [])
            lines.append("")
            if warnings:
                lines.append("warnings:")
                lines.extend(f"- {warning}" for warning in warnings[:5])
            else:
                lines.append("warnings: none")
        lines.extend(["", "This is a global tool item. Refresh here to re-check runtime and ingress health."])
        return "\n".join(lines)

    def _validate_detail_text(self) -> str:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "Validate detail unavailable"
        if not payload.get("ok") and "checks" not in payload:
            return f"error: {payload.get('error', 'unknown error')}"
        checks = payload.get("checks", [])
        failures = [check for check in checks if not check.get("ok")]
        lines = ["Validate Detail", ""]
        if not failures:
            lines.append("All validation checks are currently passing.")
        else:
            lines.append("Failing checks:")
            lines.append("")
            for check in failures[:10]:
                lines.append(f"- {check.get('name', '<unknown>')}: {check.get('detail', '')}")
            if len(failures) > 10:
                lines.append(f"... {len(failures) - 10} more")
        lines.extend(["", "This is a global tool item. Use it to monitor baseline operator health."])
        return "\n".join(lines)
