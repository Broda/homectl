from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from homesrvctl.template_catalog import app_template_options

APP_INIT_TEMPLATE_OPTIONS: list[tuple[str, str]] = app_template_options()


def stack_action_options(is_apex_domain: bool) -> list[tuple[str, str, str]]:
    options = [
        ("app-init", "app init", "Choose an app scaffold template."),
        ("site-init", "site init", "Scaffold a simple site layout."),
        ("doctor", "doctor", "Run hostname diagnostics."),
        ("up", "up", "Start the stack with docker compose."),
        ("restart", "restart", "Restart the stack."),
        ("down", "down", "Stop the stack."),
    ]
    if is_apex_domain:
        options.extend(
            [
                ("domain-add", "domain add", "Create apex and wildcard tunnel routes."),
                ("domain-repair", "domain repair", "Reconcile apex and wildcard DNS and ingress state."),
                ("domain-remove", "domain remove", "Remove apex and wildcard tunnel routes."),
            ]
        )
    return options


def tool_action_options(tool: str) -> list[tuple[str, str, str]]:
    if tool == "config":
        return [
            ("show", "config show", "Refresh the current config detail view."),
            ("init", "config init", "Write the default starter config if it is missing."),
        ]
    if tool == "cloudflared":
        return [
            ("config-test", "config-test", "Validate the configured ingress file."),
            ("logs", "logs", "Show the suggested runtime log command."),
            ("reload", "reload", "Run the detected cloudflared reload command."),
            ("restart", "restart", "Run the detected cloudflared restart command."),
        ]
    return []


class AppInitTemplateScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("up,w", "previous_template", "Prev", show=False),
        Binding("down,s,tab", "next_template", "Next", show=False),
        Binding("enter", "select_template", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="app_init_prompt"):
            yield Static("App Init Template", classes="prompt_title")
            yield Static(
                "Choose a scaffold template for the focused hostname. Use w/s or arrow keys, Enter to confirm, Esc to cancel.",
                classes="prompt_help",
            )
            yield Static("", id="app_init_options")

    def on_mount(self) -> None:
        self._render()

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(APP_INIT_TEMPLATE_OPTIONS):
                self.selected_index = index
                self._render()
                self.action_select_template()
                event.stop()

    def action_previous_template(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(APP_INIT_TEMPLATE_OPTIONS)
        self._render()

    def action_next_template(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(APP_INIT_TEMPLATE_OPTIONS)
        self._render()

    def action_select_template(self) -> None:
        self.dismiss(APP_INIT_TEMPLATE_OPTIONS[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _render(self) -> None:
        self.query_one("#app_init_options", Static).update(self._options_text())

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (template, description) in enumerate(APP_INIT_TEMPLATE_OPTIONS):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {template}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class ConfirmActionScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("enter,y", "confirm", "Confirm", show=False),
        Binding("escape,q,n", "cancel", "Cancel", show=False),
    ]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.title = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_prompt"):
            yield Static(self.title, classes="prompt_title")
            yield Static(self.body, classes="prompt_help")
            yield Static("Enter or y confirms. Esc, q, or n cancels.")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ToolActionMenuScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("up,w", "previous_action", "Prev", show=False),
        Binding("down,s,tab", "next_action", "Next", show=False),
        Binding("enter", "select_action", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    def __init__(self, tool: str) -> None:
        super().__init__()
        self.tool = tool
        self.options = tool_action_options(tool)
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="stack_action_prompt"):
            yield Static("Tool Actions", classes="prompt_title")
            yield Static(
                f"Choose an action for {self.tool}. Use w/s or arrow keys, Enter to confirm, Esc to cancel.",
                classes="prompt_help",
            )
            yield Static("", id="tool_action_options")

    def on_mount(self) -> None:
        self._render()

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self.selected_index = index
                self._render()
                self.action_select_action()
                event.stop()

    def action_previous_action(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._render()

    def action_next_action(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._render()

    def action_select_action(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _render(self) -> None:
        self.query_one("#tool_action_options", Static).update(self._options_text())

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.options):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class CloudflaredLogsModeScreen(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("up,w", "previous_mode", "Prev", show=False),
        Binding("down,s,tab", "next_mode", "Next", show=False),
        Binding("enter", "select_mode", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    OPTIONS: list[tuple[bool, str, str]] = [
        (False, "standard", "Show the normal log-command guidance for the detected runtime."),
        (True, "follow", "Show the follow or tail variant for the detected runtime."),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="stack_action_prompt"):
            yield Static("Cloudflared Logs Mode", classes="prompt_title")
            yield Static(
                "Choose whether to show the standard or follow log command. Use w/s or arrow keys, Enter to confirm, Esc to cancel.",
                classes="prompt_help",
            )
            yield Static("", id="cloudflared_logs_mode_options")

    def on_mount(self) -> None:
        self._render()

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.OPTIONS):
                self.selected_index = index
                self._render()
                self.action_select_mode()
                event.stop()

    def action_previous_mode(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.OPTIONS)
        self._render()

    def action_next_mode(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.OPTIONS)
        self._render()

    def action_select_mode(self) -> None:
        self.dismiss(self.OPTIONS[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _render(self) -> None:
        self.query_one("#cloudflared_logs_mode_options", Static).update(self._options_text())

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.OPTIONS):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class StackActionMenuScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("up,w", "previous_action", "Prev", show=False),
        Binding("down,s,tab", "next_action", "Next", show=False),
        Binding("enter", "select_action", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    def __init__(self, hostname: str, is_apex_domain: bool) -> None:
        super().__init__()
        self.hostname = hostname
        self.options = stack_action_options(is_apex_domain)
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="stack_action_prompt"):
            yield Static("Stack Actions", classes="prompt_title")
            yield Static(
                f"Choose an action for {self.hostname}. Use w/s or arrow keys, Enter to confirm, Esc to cancel.",
                classes="prompt_help",
            )
            yield Static("", id="stack_action_options")

    def on_mount(self) -> None:
        self._render()

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self.selected_index = index
                self._render()
                self.action_select_action()
                event.stop()

    def action_previous_action(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._render()

    def action_next_action(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._render()

    def action_select_action(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _render(self) -> None:
        self.query_one("#stack_action_options", Static).update(self._options_text())

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.options):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()
