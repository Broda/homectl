from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Static

from homesrvctl.tui.data import (
    build_dashboard_snapshot,
    render_config_payload_detail,
    render_domain_status_detail,
    render_tool_action_detail,
    render_stack_config_detail,
    render_stack_action_detail,
    run_stack_domain_status,
    run_stack_action,
    run_stack_config_view,
    run_tool_action,
    stack_sites,
    summarize_stack_action,
    summarize_tool_action,
)
from homesrvctl.tui.prompts import (
    AppInitTemplateScreen,
    CloudflaredLogsModeScreen,
    ConfirmActionScreen,
    StackActionMenuScreen,
    ToolActionMenuScreen,
)
from homesrvctl.utils import validate_bare_domain


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

    AppInitTemplateScreen {
        align: center middle;
        background: rgba(3, 8, 10, 0.72);
    }

    ConfirmActionScreen {
        align: center middle;
        background: rgba(3, 8, 10, 0.72);
    }

    StackActionMenuScreen {
        align: center middle;
        background: rgba(3, 8, 10, 0.72);
    }

    #app_init_prompt {
        width: 72;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        background: #0b1419;
        border: round #ffcf5a;
        color: #d7fff7;
    }

    #confirm_prompt {
        width: 64;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        background: #0b1419;
        border: round #ffcf5a;
        color: #d7fff7;
    }

    #stack_action_prompt {
        width: 72;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        background: #0b1419;
        border: round #ffcf5a;
        color: #d7fff7;
    }

    .prompt_title {
        color: #ffcf5a;
        text-style: bold;
        margin-bottom: 1;
    }

    .prompt_help {
        color: #8ccfc5;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter,o", "stack_action_menu", "Actions", show=False),
        Binding("w,up", "previous_control", "Prev", show=False),
        Binding("s,down,tab", "next_control", "Next", show=False),
        Binding("a", "app_init_prompt", "App Init", show=False),
        Binding("n", "domain_add_prompt", "Add Domain", show=False),
        Binding("p", "domain_repair", "Repair Domain", show=False),
        Binding("m", "domain_remove_prompt", "Remove Domain", show=False),
        Binding("c", "cloudflared_config_test", "Config Test", show=False),
        Binding("l", "cloudflared_reload", "Reload", show=False),
        Binding("k", "cloudflared_restart", "Restart CF", show=False),
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
        self.stack_config_views: dict[str, dict[str, object]] = {}
        self.stack_domain_views: dict[str, dict[str, object]] = {}
        self.last_tool_actions: dict[str, dict[str, object]] = {}

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

    def action_stack_action_menu(self) -> None:
        item = self._selected_control_item()
        if item.get("kind") == "tool":
            tool = str(item.get("tool", ""))
            if tool not in {"config", "cloudflared"}:
                self.status_message = f"no guided actions for {item.get('label', 'this tool')}"
                self._render()
                return
            self.push_screen(ToolActionMenuScreen(tool), lambda selected_action: self._complete_tool_action_menu(tool, selected_action))
            return
        if item.get("kind") != "stack":
            self.status_message = "select a stack or supported tool to open the action menu"
            self._render()
            return
        hostname = str(item.get("hostname", ""))
        is_apex_domain = True
        try:
            validate_bare_domain(hostname)
        except Exception:
            is_apex_domain = False
        self.push_screen(
            StackActionMenuScreen(hostname=hostname, is_apex_domain=is_apex_domain),
            lambda selected_action: self._complete_stack_action_menu(hostname, selected_action),
        )

    def action_app_init_prompt(self) -> None:
        item = self._selected_control_item()
        if item.get("kind") != "stack":
            self.status_message = "select a stack to scaffold an app"
            self._render()
            return
        hostname = str(item.get("hostname", ""))
        self.push_screen(AppInitTemplateScreen(), lambda template: self._complete_app_init_prompt(hostname, template))

    def action_domain_add_prompt(self) -> None:
        self._push_domain_confirmation("domain-add", "Confirm Domain Add")

    def action_domain_repair(self) -> None:
        item = self._selected_control_item()
        if item.get("kind") != "stack":
            self.status_message = "select an apex stack to run domain repair"
            self._render()
            return
        hostname = str(item.get("hostname", ""))
        try:
            validate_bare_domain(hostname)
        except Exception:
            self.status_message = f"domain repair is only available for apex stacks: {hostname}"
            self._render()
            return
        self._run_stack_action_for_hostname(hostname, "domain-repair")

    def action_domain_remove_prompt(self) -> None:
        self._push_domain_confirmation("domain-remove", "Confirm Domain Remove")

    def action_cloudflared_config_test(self) -> None:
        self._run_selected_tool_action("cloudflared", "config-test")

    def action_cloudflared_reload(self) -> None:
        self._run_selected_tool_action("cloudflared", "reload")

    def action_cloudflared_restart(self) -> None:
        self._run_selected_tool_action("cloudflared", "restart")

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
        self.stack_config_views = {}
        self.stack_domain_views = {}
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
        self._run_stack_action_for_hostname(hostname, action)

    def _complete_app_init_prompt(self, hostname: str, template: str | None) -> None:
        if template is None:
            self.status_message = f"app init cancelled for {hostname}"
            self._render()
            return
        self._run_stack_action_for_hostname(hostname, "app-init", template=template)

    def _complete_stack_action_menu(self, hostname: str, selected_action: str | None) -> None:
        if selected_action is None:
            self.status_message = f"stack action menu cancelled for {hostname}"
            self._render()
            return
        if selected_action == "app-init":
            self.push_screen(AppInitTemplateScreen(), lambda template: self._complete_app_init_prompt(hostname, template))
            return
        if selected_action == "domain-add":
            self._push_domain_confirmation("domain-add", "Confirm Domain Add", hostname=hostname)
            return
        if selected_action == "domain-remove":
            self._push_domain_confirmation("domain-remove", "Confirm Domain Remove", hostname=hostname)
            return
        if selected_action == "site-init":
            self._run_stack_action_for_hostname(hostname, "init-site")
            return
        self._run_stack_action_for_hostname(hostname, selected_action)

    def _complete_tool_action_menu(self, tool: str, selected_action: str | None) -> None:
        if selected_action is None:
            self.status_message = f"tool action menu cancelled for {tool}"
            self._render()
            return
        if tool == "config":
            if selected_action == "show":
                self._refresh_snapshot("config detail refreshed")
                return
            if selected_action == "init":
                self._run_config_init()
                return
        if tool == "cloudflared":
            if selected_action == "logs":
                self.push_screen(CloudflaredLogsModeScreen(), self._complete_cloudflared_logs_mode)
                return
            self._run_selected_tool_action("cloudflared", selected_action)
            return
        self.status_message = f"unsupported tool action: {tool} {selected_action}"
        self._render()

    def _complete_cloudflared_logs_mode(self, follow: bool | None) -> None:
        if follow is None:
            self.status_message = "cloudflared logs cancelled"
            self._render()
            return
        self._run_selected_tool_action("cloudflared", "logs", follow=follow)

    def _run_config_init(self, *, force: bool = False) -> None:
        payload = run_tool_action("config", "init", force=force)
        if (
            not payload.get("ok")
            and not force
            and "config already exists" in str(payload.get("error", ""))
        ):
            config_path = str(payload.get("config_path", "the default config path"))
            body = f"A config file already exists at {config_path}. Overwrite it?"
            self.push_screen(
                ConfirmActionScreen(title="Confirm Config Overwrite", body=body),
                self._complete_config_init_overwrite,
            )
            return
        self.last_tool_actions["config"] = {"action": "init", "payload": payload}
        self.status_message = summarize_tool_action("config", "init", payload)
        self.snapshot = build_dashboard_snapshot()
        self.stack_config_views = {}
        self.stack_domain_views = {}
        items = self._control_items()
        if items:
            self.selected_control_index = min(self.selected_control_index, len(items) - 1)
        else:
            self.selected_control_index = 0
        self._render()

    def _complete_config_init_overwrite(self, confirmed: bool) -> None:
        if not confirmed:
            self.status_message = "config init cancelled"
            self._render()
            return
        self._run_config_init(force=True)

    def _push_domain_confirmation(self, action: str, title: str, hostname: str | None = None) -> None:
        if hostname is None:
            item = self._selected_control_item()
            if item.get("kind") != "stack":
                self.status_message = "select an apex stack for domain actions"
                self._render()
                return
            hostname = str(item.get("hostname", ""))
        try:
            validate_bare_domain(hostname)
        except Exception:
            action_label = "domain add/remove" if action in {"domain-add", "domain-remove"} else action
            self.status_message = f"{action_label} is only available for apex stacks: {hostname}"
            self._render()
            return
        body = f"Run {action.replace('-', ' ')} for {hostname}?"
        self.push_screen(ConfirmActionScreen(title=title, body=body), lambda confirmed: self._complete_domain_confirmation(hostname, action, confirmed))

    def _complete_domain_confirmation(self, hostname: str, action: str, confirmed: bool) -> None:
        if not confirmed:
            self.status_message = f"{action.replace('-', ' ')} cancelled for {hostname}"
            self._render()
            return
        self._run_stack_action_for_hostname(hostname, action)

    def _run_stack_action_for_hostname(self, hostname: str, action: str, template: str | None = None) -> None:
        if template is None:
            payload = run_stack_action(hostname, action)
        else:
            payload = run_stack_action(hostname, action, template=template)
        self.last_stack_actions[hostname] = {"action": action, "payload": payload}
        self.status_message = summarize_stack_action(hostname, action, payload)
        self.snapshot = build_dashboard_snapshot()
        self.stack_config_views = {}
        self.stack_domain_views = {}
        items = self._control_items()
        if items:
            self.selected_control_index = min(self.selected_control_index, len(items) - 1)
        else:
            self.selected_control_index = 0
        self._render()

    def _run_selected_tool_action(self, tool: str, action: str, *, follow: bool = False) -> None:
        item = self._selected_control_item()
        if item.get("kind") != "tool" or item.get("tool") != tool:
            self.status_message = f"select {tool} to run {action}"
            self._render()
            return
        payload = run_tool_action(tool, action, follow=follow)
        self.last_tool_actions[tool] = {"action": action, "payload": payload}
        self.status_message = summarize_tool_action(tool, action, payload)
        self.snapshot = build_dashboard_snapshot()
        self.stack_config_views = {}
        self.stack_domain_views = {}
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
            {"kind": "tool", "tool": "config", "label": "Config"},
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
            return {"kind": "tool", "tool": "config", "label": "Config"}
        index = max(0, min(self.selected_control_index, len(items) - 1))
        return items[index]

    def _control_list_text(self) -> str:
        items = self._control_items()
        if not items:
            return "Tools\n\n> Config\n  Cloudflared\n  Validate\n\nStacks\n\n(no stacks found)"

        tool_count = 3
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
            if item.get("tool") == "config":
                return self._config_detail_text()
            if item.get("tool") == "cloudflared":
                return self._cloudflared_detail_text()
            return self._validate_detail_text()
        return self._stack_detail_text(str(item.get("hostname", "")), bool(item.get("compose")))

    def _command_bar_text(self) -> str:
        item = self._selected_control_item()
        mode = f"auto refresh {self.refresh_seconds:g}s" if self.refresh_seconds > 0 else "manual refresh"
        if item.get("kind") == "stack":
            focus = f"focus: {item.get('hostname', '<unknown>')}"
            actions = "actions: enter open-menu | a app-init | n domain-add | p domain-repair | m domain-remove | i site-init | g doctor | u up | t restart | x down | r refresh | q quit"
        else:
            focus = f"focus: {item.get('label', 'Tool')}"
            if item.get("tool") == "config":
                actions = "actions: enter open-menu | r refresh | q quit"
            elif item.get("tool") == "cloudflared":
                actions = "actions: enter open-menu | c config-test | l reload | k restart | r refresh | q quit"
            else:
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
        if isinstance(config_validation, dict):
            issues = config_validation.get("issues", [])
            if isinstance(issues, list) and issues:
                blocking_count = sum(1 for issue in issues if isinstance(issue, dict) and issue.get("blocking"))
                advisory_count = sum(
                    1 for issue in issues if isinstance(issue, dict) and issue.get("severity") == "advisory"
                )
                return f"{runtime} ({active})\n\n{blocking_count} blocking, {advisory_count} advisory"
            if config_validation.get("warnings"):
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
        config_view = self.stack_config_views.get(hostname)
        if config_view is None:
            config_view = run_stack_config_view(hostname)
            self.stack_config_views[hostname] = config_view
        domain_view = self.stack_domain_views.get(hostname)
        if domain_view is None:
            domain_view = run_stack_domain_status(hostname)
            self.stack_domain_views[hostname] = domain_view
        lines = [
            "Stack Detail",
            "",
            f"hostname: {hostname or '<unknown>'}",
            f"compose file: {'yes' if compose else 'no'}",
            "",
            *render_stack_config_detail(config_view),
            "",
            *render_domain_status_detail(hostname, domain_view),
            "",
            "This pane is the control surface for stack lifecycle work.",
            "Use Enter or o to open the guided action menu for the focused stack.",
            "Use a to choose an app scaffold template for the focused hostname.",
            "Use n to confirm domain add and m to confirm domain remove for apex domains.",
            "Use p to run domain repair when the focused hostname is an apex domain.",
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
                    f"config severity: {config_validation.get('max_severity', 'none')}",
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
            issues = config_validation.get("issues", [])
            lines.append("")
            if issues:
                lines.append("issues:")
                for issue in issues[:5]:
                    if not isinstance(issue, dict):
                        continue
                    severity = "blocking" if issue.get("blocking") else str(issue.get("severity", "unknown"))
                    lines.append(f"- {severity}: {issue.get('message', issue.get('detail', ''))}")
            else:
                lines.append("issues: none")
        cached = self.last_tool_actions.get("cloudflared")
        if isinstance(cached, dict):
            action = cached.get("action")
            payload = cached.get("payload")
            if isinstance(action, str) and isinstance(payload, dict):
                lines.extend(["", *render_tool_action_detail("cloudflared", action, payload)])
        lines.extend(["", "This is a global tool item. Use Enter to open the guided tool menu, including logs guidance."])
        return "\n".join(lines)

    def _config_detail_text(self) -> str:
        payload = self.snapshot.get("config")
        if not isinstance(payload, dict):
            return "Config detail unavailable"
        lines = ["Config Detail", "", *render_config_payload_detail(payload)]
        cached = self.last_tool_actions.get("config")
        if isinstance(cached, dict):
            action = cached.get("action")
            action_payload = cached.get("payload")
            if isinstance(action, str) and isinstance(action_payload, dict):
                lines.extend(["", *render_tool_action_detail("config", action, action_payload)])
        lines.extend(["", "This is a global tool item. Use Enter to open the guided tool menu for config actions."])
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
