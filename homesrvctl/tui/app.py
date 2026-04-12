from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Click
from textual.widget import Widget
from textual.widgets import Button, Header, Label, Static

from homesrvctl.tui.data import (
    TOOL_ITEMS,
    normalize_config_validation_detail,
    build_dashboard_snapshot,
    render_check_list_detail,
    render_bootstrap_assessment_detail,
    render_cloudflared_setup_detail,
    render_config_payload_detail,
    render_domain_status_detail,
    format_key_value_lines,
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
from homesrvctl.cloudflare import summarize_tunnel_api_detail
from homesrvctl.tui.prompts import (
    AppInitTemplateScreen,
    BooleanChoiceScreen,
    CloudflaredLogsModeScreen,
    ConfirmActionScreen,
    CreationModeScreen,
    StackActionMenuScreen,
    TextEntryScreen,
    ToolActionMenuScreen,
)
from homesrvctl.utils import validate_bare_domain, validate_hostname


class SummaryCardWidget(Widget, can_focus=False):
    """Clickable summary card in the top strip. Click focuses the related control row."""

    DEFAULT_CSS = """
    SummaryCardWidget {
        width: 1fr;
        height: 1fr;
        margin-right: 1;
        padding: 1 2;
        background: #0d161b;
        border: round #1fd6c1;
        color: #d7fff7;
        layout: vertical;
    }
    SummaryCardWidget:last-of-type {
        margin-right: 0;
    }
    SummaryCardWidget:hover {
        border: round #ffcf5a;
    }
    SummaryCardWidget .card_title {
        color: #ffcf5a;
        text-style: bold;
        height: 1;
    }
    SummaryCardWidget .card_status {
        height: 1;
    }
    SummaryCardWidget .card_detail {
        color: #8ccfc5;
        height: 1fr;
    }
    """

    def __init__(self, widget_id: str, title: str, focus_index: int) -> None:
        super().__init__(id=widget_id)
        self._title = title
        self._focus_index = focus_index
        self._status = ""
        self._detail = ""

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="card_title")
        yield Static("", id=f"{self.id}_status", classes="card_status")
        yield Static("", id=f"{self.id}_detail", classes="card_detail")

    def update_content(self, status: str, detail: str) -> None:
        self._status = status
        self._detail = detail
        self.query_one(f"#{self.id}_status", Static).update(status)
        self.query_one(f"#{self.id}_detail", Static).update(detail)

    def on_click(self, event: Click) -> None:  # noqa: ARG002
        app = self.app
        if isinstance(app, HomesrvctlTextualApp):
            items = app._control_items()
            target = max(0, min(self._focus_index, len(items) - 1))
            app.selected_control_index = target
            app._render()


class ControlSectionLabel(Widget):
    """Non-clickable section header in the controls pane."""

    DEFAULT_CSS = """
    ControlSectionLabel {
        height: auto;
        color: #1fd6c1;
        text-style: bold;
        padding: 0 0;
        margin-top: 1;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def render(self) -> str:
        return self._text


class ControlRowWidget(Widget, can_focus=False):
    """Clickable row in the controls pane. Carries --selected when active."""

    DEFAULT_CSS = """
    ControlRowWidget {
        height: 1;
        padding: 0 1;
        color: #d7fff7;
    }
    ControlRowWidget:hover {
        background: #0d2028;
    }
    ControlRowWidget.--selected {
        background: #13bfae;
        color: #081014;
        text-style: bold;
    }
    """

    def __init__(self, index: int, label: str, suffix: str = "") -> None:
        super().__init__()
        self._index = index
        self._label = label
        self._suffix = suffix

    @property
    def row_index(self) -> int:
        return self._index

    def render(self) -> str:
        if self._suffix:
            return f"{self._label} {self._suffix}"
        return self._label

    def on_click(self, event: Click) -> None:  # noqa: ARG002
        app = self.app
        if isinstance(app, HomesrvctlTextualApp):
            app.selected_control_index = self._index
            app._render()


class HomesrvctlTextualApp(App[None]):
    TITLE = "Home Server Controller"
    CSS = """
    /* Palette reference:
     *   status ok / success : green (#00ff7f or Rich [green])
     *   status warning       : yellow / amber ([yellow])
     *   status error / failed: red ([red])
     *   accent / titles      : #ffcf5a (bold)
     *   primary borders      : #1fd6c1 / #13bfae
     */

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
        overflow-y: auto;
    }

    .compose_yes {
        color: #1fd6c1;
    }

    .compose_no {
        color: #3a5a5a;
    }

    #detail_pane {
        width: 1fr;
        min-width: 0;
        padding: 1 2;
        background: #091116;
        border: round #0fa697;
        layout: vertical;
    }

    #detail_scroll {
        height: 1fr;
        padding: 0 1;
    }

    #detail_buttons {
        height: auto;
        padding: 1 0 0 0;
        border-top: solid #13bfae;
    }

    #detail_buttons Button {
        margin: 0 1 0 0;
        min-width: 10;
        height: 3;
        border: tall #1fd6c1;
        background: #0d1e26;
        color: #1fd6c1;
    }

    #detail_buttons Button:hover {
        background: #0d2a38;
        border: tall #ffcf5a;
        color: #ffcf5a;
    }

    #detail_buttons Button:focus {
        border: tall #ffcf5a;
        color: #ffcf5a;
    }

    .pane_title {
        color: #ffcf5a;
        text-style: bold;
        margin-bottom: 1;
    }

    #command_bar {
        padding: 0 1;
    }

    #controls_box {
        height: 1fr;
        padding: 0;
    }

    #detail_box {
        height: auto;
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

    TextEntryScreen {
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

    #text_entry_prompt {
        width: 80;
        max-width: 92%;
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

    .prompt_input {
        min-height: 3;
        padding: 1 1;
        background: #081014;
        border: round #13bfae;
        color: #d7fff7;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter,o", "stack_action_menu", "Actions", show=False),
        Binding("w,up", "previous_control", "Prev", show=False),
        Binding("s,down,tab", "next_control", "Next", show=False),
        Binding("b", "create_stack_flow", "Create", show=False),
        Binding("d", "domain_onboarding_flow", "Domain", show=False),
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
        self.pending_create_request: dict[str, object] | None = None
        self.pending_domain_request: dict[str, object] | None = None
        self.global_domain_action: dict[str, object] | None = None
        self.global_domain_status_view: dict[str, object] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="summary_strip"):
            yield SummaryCardWidget("summary_stacks", "Stacks", focus_index=len(TOOL_ITEMS))
            yield SummaryCardWidget("summary_cloudflared", "Cloudflared", focus_index=2)
            yield SummaryCardWidget("summary_validate", "Validate", focus_index=3)
            yield SummaryCardWidget("summary_bootstrap", "Bootstrap", focus_index=4)
        with Horizontal(id="body"):
            with Vertical(id="controls_pane"):
                yield Static("Controls", classes="pane_title")
                yield Vertical(id="controls_box")
            with Vertical(id="detail_pane"):
                yield Static("Detail", id="detail_pane_title", classes="pane_title")
                with VerticalScroll(id="detail_scroll"):
                    yield Static("", id="detail_box")
                with Horizontal(id="detail_buttons"):
                    pass
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

    def action_create_stack_flow(self) -> None:
        self.pending_create_request = None
        self.push_screen(
            TextEntryScreen(
                "New Stack Hostname",
                "Enter the hostname to scaffold. Press enter to continue or esc to cancel.",
                placeholder="app.example.com",
            ),
            self._complete_create_hostname,
        )

    def action_domain_onboarding_flow(self) -> None:
        self.pending_domain_request = None
        self.push_screen(
            TextEntryScreen(
                "Onboard Apex Domain",
                "Enter the bare domain to route through the configured tunnel. Press enter to continue or esc to cancel.",
                placeholder="example.com",
            ),
            self._complete_domain_onboarding_domain,
        )

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

    def action_cloudflared_setup(self) -> None:
        self._run_selected_tool_action("cloudflared", "setup")

    def action_cloudflared_reload(self) -> None:
        self._run_selected_tool_action("cloudflared", "reload")

    def action_cloudflared_restart(self) -> None:
        self._run_selected_tool_action("cloudflared", "restart")

    def action_bootstrap_assess(self) -> None:
        self._run_selected_tool_action("bootstrap", "assess")

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
        if tool == "tunnel":
            if selected_action == "show":
                self._run_selected_tool_action("tunnel", "show")
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

    def _complete_create_hostname(self, hostname: str | None) -> None:
        if hostname is None:
            self.pending_create_request = None
            self.status_message = "create flow cancelled"
            self._render()
            return
        try:
            valid_hostname = validate_hostname(hostname)
        except Exception as exc:
            self.pending_create_request = None
            self.status_message = f"create flow rejected hostname: {exc}"
            self._render()
            return
        self.pending_create_request = {"hostname": valid_hostname}
        self.push_screen(CreationModeScreen(valid_hostname), self._complete_create_mode)

    def _complete_create_mode(self, action: str | None) -> None:
        if action is None:
            self.pending_create_request = None
            self.status_message = "create flow cancelled"
            self._render()
            return
        if self.pending_create_request is None:
            self.pending_create_request = {}
        self.pending_create_request["action"] = action
        hostname = str(self.pending_create_request.get("hostname", ""))
        if action == "app-init":
            self.push_screen(AppInitTemplateScreen(), lambda template: self._complete_create_template(hostname, template))
            return
        self._push_create_profile_prompt()

    def _complete_create_template(self, hostname: str, template: str | None) -> None:
        if template is None:
            self.pending_create_request = None
            self.status_message = f"app init cancelled for {hostname}"
            self._render()
            return
        if self.pending_create_request is None:
            self.pending_create_request = {"hostname": hostname, "action": "app-init"}
        self.pending_create_request["template"] = template
        self._push_create_profile_prompt()

    def _push_create_profile_prompt(self) -> None:
        self.push_screen(
            TextEntryScreen(
                "Routing Profile",
                "Optional: enter a named profile, or leave blank to use direct/default settings.",
                placeholder="edge",
            ),
            self._complete_create_profile,
        )

    def _complete_create_profile(self, profile: str | None) -> None:
        if profile is None:
            self.pending_create_request = None
            self.status_message = "create flow cancelled"
            self._render()
            return
        if self.pending_create_request is None:
            self.pending_create_request = {}
        self.pending_create_request["profile"] = profile or None
        self.push_screen(
            TextEntryScreen(
                "Docker Network",
                "Optional: enter a stack-local docker network override, or leave blank.",
                placeholder="edge",
            ),
            self._complete_create_docker_network,
        )

    def _complete_create_docker_network(self, docker_network: str | None) -> None:
        if docker_network is None:
            self.pending_create_request = None
            self.status_message = "create flow cancelled"
            self._render()
            return
        if self.pending_create_request is None:
            self.pending_create_request = {}
        self.pending_create_request["docker_network"] = docker_network or None
        self.push_screen(
            TextEntryScreen(
                "Traefik URL",
                "Optional: enter a stack-local ingress target override, or leave blank.",
                placeholder="http://localhost:8081",
            ),
            self._complete_create_traefik_url,
        )

    def _complete_create_traefik_url(self, traefik_url: str | None) -> None:
        if traefik_url is None:
            self.pending_create_request = None
            self.status_message = "create flow cancelled"
            self._render()
            return
        if self.pending_create_request is None:
            self.pending_create_request = {}
        self.pending_create_request["traefik_url"] = traefik_url or None
        self._run_pending_create_request()

    def _run_pending_create_request(self, *, force: bool = False) -> None:
        request = dict(self.pending_create_request or {})
        hostname = str(request.get("hostname", ""))
        action = str(request.get("action", ""))
        template = request.get("template")
        payload = run_stack_action(
            hostname,
            action,
            template=str(template) if isinstance(template, str) else None,
            force=force,
            profile=str(request["profile"]) if request.get("profile") else None,
            docker_network=str(request["docker_network"]) if request.get("docker_network") else None,
            traefik_url=str(request["traefik_url"]) if request.get("traefik_url") else None,
        )
        error_text = str(payload.get("error") or "")
        if not payload.get("ok") and not force and "already exist" in error_text:
            label = "app init" if action == "app-init" else "site init"
            self.push_screen(
                ConfirmActionScreen(
                    title="Confirm Scaffold Overwrite",
                    body=f"{label} reported existing files for {hostname}. Overwrite them?",
                ),
                self._complete_create_overwrite,
            )
            return
        self.pending_create_request = None
        self.last_stack_actions[hostname] = {"action": action, "payload": payload}
        self.status_message = summarize_stack_action(hostname, action, payload)
        self.snapshot = build_dashboard_snapshot()
        self.stack_config_views = {}
        self.stack_domain_views = {}
        self._reselect_hostname(hostname)
        self._render()

    def _complete_create_overwrite(self, confirmed: bool) -> None:
        if not confirmed:
            self.pending_create_request = None
            self.status_message = "create overwrite cancelled"
            self._render()
            return
        self._run_pending_create_request(force=True)

    def _complete_domain_onboarding_domain(self, hostname: str | None) -> None:
        if hostname is None:
            self.pending_domain_request = None
            self.status_message = "domain onboarding cancelled"
            self._render()
            return
        try:
            bare_domain = validate_bare_domain(hostname)
        except Exception as exc:
            self.pending_domain_request = None
            self.status_message = f"domain onboarding rejected domain: {exc}"
            self._render()
            return
        self.pending_domain_request = {"hostname": bare_domain}
        self.push_screen(
            BooleanChoiceScreen(
                "Domain Add Dry Run",
                f"Run domain add for {bare_domain} in dry-run mode?",
                true_label="yes",
                false_label="no",
            ),
            self._complete_domain_onboarding_dry_run,
        )

    def _complete_domain_onboarding_dry_run(self, dry_run: bool | None) -> None:
        if dry_run is None:
            self.pending_domain_request = None
            self.status_message = "domain onboarding cancelled"
            self._render()
            return
        if self.pending_domain_request is None:
            self.pending_domain_request = {}
        self.pending_domain_request["dry_run"] = dry_run
        hostname = str(self.pending_domain_request.get("hostname", ""))
        self.push_screen(
            BooleanChoiceScreen(
                "Restart Cloudflared",
                f"Restart cloudflared automatically after domain add for {hostname} when ingress changes are written?",
                true_label="yes",
                false_label="no",
            ),
            self._complete_domain_onboarding_restart,
        )

    def _complete_domain_onboarding_restart(self, restart_cloudflared: bool | None) -> None:
        if restart_cloudflared is None:
            self.pending_domain_request = None
            self.status_message = "domain onboarding cancelled"
            self._render()
            return
        if self.pending_domain_request is None:
            self.pending_domain_request = {}
        self.pending_domain_request["restart_cloudflared"] = restart_cloudflared
        self._run_pending_domain_request()

    def _run_pending_domain_request(self) -> None:
        request = dict(self.pending_domain_request or {})
        hostname = str(request.get("hostname", ""))
        dry_run = bool(request.get("dry_run", False))
        restart_cloudflared = bool(request.get("restart_cloudflared", False))
        payload = run_stack_action(
            hostname,
            "domain-add",
            dry_run=dry_run,
            restart_cloudflared=restart_cloudflared,
        )
        self.pending_domain_request = None
        self.global_domain_action = {"hostname": hostname, "action": "domain-add", "payload": payload}
        self.global_domain_status_view = run_stack_domain_status(hostname)
        self.last_stack_actions[hostname] = {"action": "domain-add", "payload": payload}
        self.status_message = summarize_stack_action(hostname, "domain-add", payload)
        self.snapshot = build_dashboard_snapshot()
        self.stack_config_views = {}
        self.stack_domain_views = {}
        if self._has_stack(hostname):
            self._reselect_hostname(hostname)
        else:
            self.selected_control_index = 1
        self._render()

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
        self._reselect_hostname(hostname)
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
        stacks_status, stacks_detail = self._stacks_summary_parts()
        self.query_one("#summary_stacks", SummaryCardWidget).update_content(stacks_status, stacks_detail)
        cf_status, cf_detail = self._cloudflared_summary_parts()
        self.query_one("#summary_cloudflared", SummaryCardWidget).update_content(cf_status, cf_detail)
        val_status, val_detail = self._validate_summary_parts()
        self.query_one("#summary_validate", SummaryCardWidget).update_content(val_status, val_detail)
        bootstrap_status, bootstrap_detail = self._bootstrap_summary_parts()
        self.query_one("#summary_bootstrap", SummaryCardWidget).update_content(bootstrap_status, bootstrap_detail)
        self._rebuild_controls()
        self.query_one("#detail_pane_title", Static).update(self._detail_pane_title())
        self.query_one("#detail_box", Static).update(self._detail_text())
        self._rebuild_detail_buttons()
        self.query_one("#command_bar_text", Static).update(self._command_bar_text())

    def _reselect_hostname(self, hostname: str) -> None:
        items = self._control_items()
        for index, item in enumerate(items):
            if item.get("kind") == "stack" and item.get("hostname") == hostname:
                self.selected_control_index = index
                return
        if items:
            self.selected_control_index = min(self.selected_control_index, len(items) - 1)
        else:
            self.selected_control_index = 0

    def _has_stack(self, hostname: str) -> bool:
        return any(item.get("kind") == "stack" and item.get("hostname") == hostname for item in self._control_items())

    #: Maps detail button label → action method name; rebuilt each render.
    _detail_button_actions: dict[str, str]

    def _rebuild_detail_buttons(self) -> None:
        buttons_bar = self.query_one("#detail_buttons", Horizontal)
        buttons_bar.remove_children()
        item = self._selected_control_item()
        if item.get("kind") == "stack":
            specs = [
                ("Up (u)", "up"),
                ("Down (x)", "down"),
                ("Restart (t)", "restart"),
                ("Doctor (g)", "doctor"),
                ("Actions (Enter)", "stack_action_menu"),
                ("Create (b)", "create_stack_flow"),
                ("Onboard Domain (d)", "domain_onboarding_flow"),
            ]
        elif item.get("tool") == "cloudflared":
            specs = [
                ("Fix Setup", "cloudflared_setup"),
                ("Config Test (c)", "cloudflared_config_test"),
                ("Reload (l)", "cloudflared_reload"),
                ("Restart CF (k)", "cloudflared_restart"),
                ("Create (b)", "create_stack_flow"),
                ("Onboard Domain (d)", "domain_onboarding_flow"),
            ]
        elif item.get("tool") == "bootstrap":
            specs = [
                ("Refresh (r)", "bootstrap_assess"),
                ("Create (b)", "create_stack_flow"),
                ("Onboard Domain (d)", "domain_onboarding_flow"),
            ]
        else:
            specs = [
                ("Refresh (r)", "refresh"),
                ("Create (b)", "create_stack_flow"),
                ("Onboard Domain (d)", "domain_onboarding_flow"),
            ]
        self._detail_button_actions = {}
        for label, action in specs:
            btn = Button(label)
            self._detail_button_actions[label] = action
            buttons_bar.mount(btn)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        label = str(event.button.label)
        action_name = getattr(self, "_detail_button_actions", {}).get(label)
        if action_name:
            action_method = getattr(self, f"action_{action_name}", None)
            if callable(action_method):
                action_method()

    def _rebuild_controls(self) -> None:
        controls_box = self.query_one("#controls_box", Vertical)
        controls_box.remove_children()
        items = self._control_items()
        tool_count = len(TOOL_ITEMS)
        controls_box.mount(ControlSectionLabel("Tools"))
        for index, item in enumerate(items[:tool_count]):
            row = ControlRowWidget(index, str(item["label"]))
            if index == self.selected_control_index:
                row.add_class("--selected")
            controls_box.mount(row)
        controls_box.mount(ControlSectionLabel("Stacks"))
        stack_items = items[tool_count:]
        if not stack_items:
            controls_box.mount(Static("(no stacks found)"))
        for offset, item in enumerate(stack_items):
            index = tool_count + offset
            has_compose = bool(item.get("compose"))
            symbol = "●" if has_compose else "○"
            symbol_class = "compose_yes" if has_compose else "compose_no"
            suffix = f"[{symbol_class}]{symbol}[/{symbol_class}]"
            row = ControlRowWidget(index, str(item["label"]), suffix)
            if index == self.selected_control_index:
                row.add_class("--selected")
            controls_box.mount(row)

    def _control_items(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = [{"kind": "tool", "tool": tool, "label": label} for tool, label in TOOL_ITEMS]
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
            return "Tools\n\n> Config\n  Tunnel\n  Cloudflared\n  Validate\n\nStacks\n\n(no stacks found)"

        tool_count = len(TOOL_ITEMS)
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

    def _detail_pane_title(self) -> str:
        item = self._selected_control_item()
        if item.get("kind") == "stack":
            return f"Stack: {item.get('hostname', '<unknown>')}"
        tool = str(item.get("tool", ""))
        if tool == "config":
            return "Tool: Config"
        if tool == "tunnel":
            return "Tool: Tunnel"
        if tool == "cloudflared":
            return "Tool: Cloudflared"
        if tool == "bootstrap":
            return "Tool: Bootstrap"
        return "Tool: Validate"

    def _detail_text(self) -> str:
        item = self._selected_control_item()
        if item.get("kind") == "tool":
            if item.get("tool") == "config":
                return self._config_detail_text()
            if item.get("tool") == "tunnel":
                return self._tunnel_detail_text()
            if item.get("tool") == "cloudflared":
                return self._cloudflared_detail_text()
            if item.get("tool") == "bootstrap":
                return self._bootstrap_detail_text()
            return self._validate_detail_text()
        return self._stack_detail_text(str(item.get("hostname", "")), bool(item.get("compose")))

    def _command_bar_text(self) -> str:
        mode = f"auto refresh {self.refresh_seconds:g}s" if self.refresh_seconds > 0 else "manual refresh"
        return f"status: {self.status_message}  ·  {mode}"

    def _stacks_summary_parts(self) -> tuple[str, str]:
        payload = self.snapshot.get("list")
        if not isinstance(payload, dict):
            return "○ unavailable", ""
        if not payload.get("ok"):
            return "[red]✗ error[/red]", str(payload.get("error", "unknown error"))
        sites = payload.get("sites", [])
        if not sites:
            return "○ none ready", "Nothing scaffolded yet."
        compose_ready = sum(1 for site in sites if site.get("compose"))
        status = f"[green]✓ {compose_ready} ready[/green]" if compose_ready else "○ none ready"
        return status, f"{len(sites)} stack(s)"

    def _cloudflared_summary_parts(self) -> tuple[str, str]:
        payload = self.snapshot.get("cloudflared")
        if not isinstance(payload, dict):
            return "○ unavailable", ""
        active = payload.get("active")
        runtime = str(payload.get("mode", "unknown"))
        if active:
            status = "[green]✓ active[/green]"
        else:
            status = "[yellow]⚠ inactive[/yellow]"
        config_validation = payload.get("config_validation")
        setup = payload.get("setup")
        if isinstance(setup, dict) and not setup.get("ok", False):
            issue_count = len(setup.get("issues", [])) if isinstance(setup.get("issues"), list) else 1
            status = f"[yellow]⚠ {issue_count} setup[/yellow]"
            return status, str(setup.get("detail", runtime))
        if isinstance(config_validation, dict):
            issues = config_validation.get("issues", [])
            if isinstance(issues, list) and issues:
                blocking_count = sum(1 for issue in issues if isinstance(issue, dict) and issue.get("blocking"))
                advisory_count = sum(
                    1 for issue in issues if isinstance(issue, dict) and issue.get("severity") == "advisory"
                )
                if blocking_count:
                    status = f"[yellow]⚠ {blocking_count} warnings[/yellow]"
                return status, f"{runtime} · {advisory_count} advisory"
            if config_validation.get("warnings"):
                count = len(config_validation["warnings"])
                status = f"[yellow]⚠ {count} warnings[/yellow]"
                return status, runtime
        return status, f"{runtime} · {payload.get('detail', 'no detail')}"

    def _validate_summary_parts(self) -> tuple[str, str]:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "○ unavailable", ""
        checks = payload.get("checks", [])
        failures = [check for check in checks if not check.get("ok")]
        if not checks:
            return "○ no checks", "Validation returned no checks."
        if failures:
            return f"[red]✗ {len(failures)} failing[/red]", f"{len(checks)} checks"
        return "[green]✓ all passing[/green]", f"{len(checks)} checks"

    def _bootstrap_summary_parts(self) -> tuple[str, str]:
        payload = self.snapshot.get("bootstrap")
        if not isinstance(payload, dict):
            return "○ unavailable", ""
        state = str(payload.get("bootstrap_state", "unknown"))
        issues = payload.get("issues", [])
        issue_count = len(issues) if isinstance(issues, list) else 0
        if state == "ready":
            return "[green]✓ ready[/green]", "Debian target"
        if state == "fresh":
            return "○ fresh", "Debian target"
        if state == "partial":
            return "[yellow]⚠ partial[/yellow]", f"{issue_count} issue(s)"
        if state == "unsupported":
            return "[red]✗ unsupported[/red]", str(payload.get("detail", "unsupported host"))
        return "○ unknown", str(payload.get("detail", "no detail"))

    def _tunnel_detail_text(self) -> str:
        payload = self.snapshot.get("tunnel")
        if not isinstance(payload, dict):
            return "Tunnel detail unavailable"
        if not payload.get("ok") and payload.get("configured_tunnel") in {None, ""}:
            return f"error: {payload.get('detail') or payload.get('error', 'unknown error')}"
        rows = [
            ("configured tunnel", str(payload.get("configured_tunnel", "<unknown>"))),
            ("resolved tunnel id", str(payload.get("resolved_tunnel_id") or "<unresolved>")),
            ("resolution source", str(payload.get("resolution_source") or "unknown")),
        ]
        lines = [
            "[bold #ffcf5a]Tunnel Detail[/bold #ffcf5a]",
            "",
            *format_key_value_lines(rows),
        ]
        account_id = payload.get("account_id")
        if account_id:
            lines.extend(["", *format_key_value_lines([("account id", str(account_id))])])
        api_status = payload.get("api_status")
        if isinstance(api_status, dict):
            lines.extend(
                [
                    "",
                    *format_key_value_lines(
                        [
                            ("api tunnel name", str(api_status.get("name", "<unknown>"))),
                            ("api tunnel status", str(api_status.get("status", "unknown"))),
                        ]
                    ),
                ]
            )
        api_detail, is_warning = summarize_tunnel_api_detail(
            resolved_tunnel_id=str(payload.get("resolved_tunnel_id")) if payload.get("resolved_tunnel_id") else None,
            api_available=bool(payload.get("api_available")),
            api_status=api_status if isinstance(api_status, dict) else None,
            api_error=str(payload.get("api_error")) if payload.get("api_error") else None,
        )
        if api_detail:
            label = "api detail" if is_warning else "api note"
            lines.extend(["", f"{label}: {api_detail}"])
        cached = self.last_tool_actions.get("tunnel")
        if isinstance(cached, dict):
            action = cached.get("action")
            action_payload = cached.get("payload")
            if isinstance(action, str) and isinstance(action_payload, dict):
                lines.extend(["", *render_tool_action_detail("tunnel", action, action_payload)])
        if isinstance(self.global_domain_action, dict):
            hostname = str(self.global_domain_action.get("hostname", ""))
            action = self.global_domain_action.get("action")
            payload = self.global_domain_action.get("payload")
            if hostname and isinstance(action, str) and isinstance(payload, dict):
                lines.extend(
                    [
                        "",
                        "[bold #ffcf5a]Last Domain Onboarding[/bold #ffcf5a]",
                        "",
                        f"domain: {hostname}",
                        "",
                        *render_stack_action_detail(action, payload),
                    ]
                )
                if isinstance(self.global_domain_status_view, dict):
                    lines.extend(["", *render_domain_status_detail(hostname, self.global_domain_status_view)])
        return "\n".join(lines)

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
            "[bold #ffcf5a]Stack Detail[/bold #ffcf5a]",
            "",
            f"hostname: {hostname or '<unknown>'}",
            f"compose file: {'exists' if compose else 'does not exist'}",
            "",
            *render_stack_config_detail(config_view),
            "",
            *render_domain_status_detail(hostname, domain_view),
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
        active = payload.get("active", False)
        active_markup = "[green]active[/green]" if active else "[yellow]inactive[/yellow]"
        lines = [
            "[bold #ffcf5a]Cloudflared Detail[/bold #ffcf5a]",
            "",
            f"runtime: {payload.get('mode', 'unknown')}",
            f"active: {active_markup}",
            f"detail: {payload.get('detail', 'unknown')}",
        ]
        setup = payload.get("setup")
        if isinstance(setup, dict):
            lines.extend(["", *render_cloudflared_setup_detail(setup)])
        config_validation = payload.get("config_validation")
        if isinstance(config_validation, dict):
            config_ok = config_validation.get("ok", False)
            config_ok_markup = "[green]True[/green]" if config_ok else "[red]False[/red]"
            lines.extend(
                [
                    "",
                    f"config ok: {config_ok_markup}",
                    f"config severity: {config_validation.get('max_severity', 'none')}",
                    f"config detail: {normalize_config_validation_detail(config_validation.get('detail', 'unknown'))}",
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
        return "\n".join(lines)

    def _bootstrap_detail_text(self) -> str:
        payload = self.snapshot.get("bootstrap")
        if not isinstance(payload, dict):
            return "Bootstrap detail unavailable"
        lines = ["[bold #ffcf5a]Bootstrap Detail[/bold #ffcf5a]", "", *render_bootstrap_assessment_detail(payload)]
        cached = self.last_tool_actions.get("bootstrap")
        if isinstance(cached, dict):
            action = cached.get("action")
            action_payload = cached.get("payload")
            if isinstance(action, str) and isinstance(action_payload, dict):
                lines.extend(["", *render_tool_action_detail("bootstrap", action, action_payload)])
        return "\n".join(lines)

    def _config_detail_text(self) -> str:
        payload = self.snapshot.get("config")
        if not isinstance(payload, dict):
            return "Config detail unavailable"
        lines = ["[bold #ffcf5a]Config Detail[/bold #ffcf5a]", "", *render_config_payload_detail(payload)]
        cached = self.last_tool_actions.get("config")
        if isinstance(cached, dict):
            action = cached.get("action")
            action_payload = cached.get("payload")
            if isinstance(action, str) and isinstance(action_payload, dict):
                lines.extend(["", *render_tool_action_detail("config", action, action_payload)])
        return "\n".join(lines)

    def _validate_detail_text(self) -> str:
        payload = self.snapshot.get("validate")
        if not isinstance(payload, dict):
            return "Validate detail unavailable"
        if not payload.get("ok") and "checks" not in payload:
            return f"error: {payload.get('error', 'unknown error')}"
        lines = ["[bold #ffcf5a]Validate Detail[/bold #ffcf5a]", ""]
        checks = payload.get("checks", [])
        if isinstance(checks, list):
            lines.extend(render_check_list_detail(checks, empty_message="[green]No validation checks were returned.[/green]"))
        else:
            lines.append("error: invalid validate payload")
        return "\n".join(lines)
