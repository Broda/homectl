from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Click, Key
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Static

from homesrvctl.template_catalog import app_template_options

APP_INIT_TEMPLATE_OPTIONS: list[tuple[str, str]] = app_template_options()


class OptionRowWidget(Widget, can_focus=False):
    """Clickable option row for modal prompt screens.

    Carries --selected CSS class when it is the active choice.
    Clicking fires the screen's select callback directly via the screen ref.
    """

    DEFAULT_CSS = """
    OptionRowWidget {
        height: auto;
        padding: 0 1;
        color: #d7fff7;
    }
    OptionRowWidget:hover {
        background: #0d2028;
    }
    OptionRowWidget.--selected {
        background: #13bfae;
        color: #081014;
        text-style: bold;
    }
    OptionRowWidget .option_number {
        color: #8ccfc5;
    }
    OptionRowWidget.--selected .option_number {
        color: #081014;
    }
    OptionRowWidget .option_description {
        color: #8ccfc5;
    }
    OptionRowWidget.--selected .option_description {
        color: #0d3030;
    }
    """

    def __init__(self, index: int, number: int, label: str, description: str = "") -> None:
        super().__init__()
        self._index = index
        self._number = number
        self._label = label
        self._description = description

    @property
    def option_index(self) -> int:
        return self._index

    def compose(self) -> ComposeResult:
        num = f" [{self._number}]" if self._number > 0 else ""
        yield Static(f"[dim]{num}[/dim] {self._label}", classes="option_label")
        if self._description:
            yield Static(f"   {self._description}", classes="option_description")

    def on_click(self, event: Click) -> None:  # noqa: ARG002
        screen = self.screen
        if hasattr(screen, "_select_option_by_index"):
            screen._select_option_by_index(self._index)


def creation_mode_options() -> list[tuple[str, str, str]]:
    return [
        ("init-site", "site init", "Scaffold a simple site layout for a new hostname."),
        ("app-init", "app init", "Scaffold an app stack for a new hostname."),
    ]


def stack_action_options(is_apex_domain: bool) -> list[tuple[str, str, str]]:
    options = [
        ("app-init", "app init", "Choose an app scaffold template."),
        ("site-init", "site init", "Scaffold a simple site layout."),
        ("doctor", "doctor", "Run hostname diagnostics."),
        ("up", "up", "Start the stack with docker compose."),
        ("restart", "restart", "Restart the stack."),
        ("down", "down", "Stop the stack."),
        ("cleanup", "cleanup", "Stop and delete the stack directory."),
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
    if tool == "tunnel":
        return [
            ("show", "tunnel status", "Refresh configured tunnel resolution and API status detail."),
        ]
    if tool == "cloudflared":
        return [
            ("setup", "setup", "Assess config ownership and generate repair commands."),
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
                "· w/s navigate  · enter select  · esc cancel",
                classes="prompt_help",
            )
            with Vertical(id="app_init_options"):
                for i, (template, description) in enumerate(APP_INIT_TEMPLATE_OPTIONS):
                    row = OptionRowWidget(i, i + 1, template, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(APP_INIT_TEMPLATE_OPTIONS):
                self._select_option_by_index(index)
                self.action_select_template()
                event.stop()

    def action_previous_template(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(APP_INIT_TEMPLATE_OPTIONS)
        self._update_selection()

    def action_next_template(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(APP_INIT_TEMPLATE_OPTIONS)
        self._update_selection()

    def action_select_template(self) -> None:
        self.dismiss(APP_INIT_TEMPLATE_OPTIONS[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        """Legacy text rendering kept for tests."""
        lines: list[str] = []
        for index, (template, description) in enumerate(APP_INIT_TEMPLATE_OPTIONS):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {template}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class TextEntryScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("enter", "submit", "Submit", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
        Binding("backspace", "backspace", "Backspace", show=False),
        Binding("ctrl+u", "clear", "Clear", show=False),
    ]

    def __init__(self, title: str, help_text: str, *, placeholder: str = "", initial_value: str = "") -> None:
        super().__init__()
        self.title = title
        self.help_text = help_text
        self.placeholder = placeholder
        self.value = initial_value

    def compose(self) -> ComposeResult:
        with Vertical(id="text_entry_prompt"):
            yield Static(self.title, classes="prompt_title")
            yield Static(self.help_text, classes="prompt_help")
            yield Static("", id="text_entry_value", classes="prompt_input")

    def on_mount(self) -> None:
        self._update_value_view()

    def on_key(self, event: Key) -> None:
        if event.is_printable and event.character:
            self.value += event.character
            self._update_value_view()
            event.stop()

    def action_submit(self) -> None:
        self.dismiss(self.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_backspace(self) -> None:
        if self.value:
            self.value = self.value[:-1]
            self._update_value_view()

    def action_clear(self) -> None:
        self.value = ""
        self._update_value_view()

    def _update_value_view(self) -> None:
        rendered = self._value_text()
        self.query_one("#text_entry_value", Static).update(rendered)

    def _value_text(self) -> str:
        if self.value:
            return f"> {self.value}"
        if self.placeholder:
            return f"[dim]> {self.placeholder}[/dim]"
        return "> "


class CreationModeScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("up,w", "previous_mode", "Prev", show=False),
        Binding("down,s,tab", "next_mode", "Next", show=False),
        Binding("enter", "select_mode", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    def __init__(self, hostname: str) -> None:
        super().__init__()
        self.hostname = hostname
        self.options = creation_mode_options()
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="stack_action_prompt"):
            yield Static("Create New Stack", classes="prompt_title")
            yield Static(
                f"{self.hostname}  · w/s navigate  · enter select  · esc cancel",
                classes="prompt_help",
            )
            with Vertical(id="creation_mode_options"):
                for i, (_, label, description) in enumerate(self.options):
                    row = OptionRowWidget(i, i + 1, label, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self._select_option_by_index(index)
                self.action_select_mode()
                event.stop()

    def action_previous_mode(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._update_selection()

    def action_next_mode(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._update_selection()

    def action_select_mode(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.options):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class BooleanChoiceScreen(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("up,w,left,a", "previous_choice", "Prev", show=False),
        Binding("down,s,right,d,tab", "next_choice", "Next", show=False),
        Binding("enter", "select_choice", "Select", show=False),
        Binding("escape,q", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        title: str,
        help_text: str,
        *,
        true_label: str = "yes",
        false_label: str = "no",
    ) -> None:
        super().__init__()
        self.title = title
        self.help_text = help_text
        self.options: list[tuple[bool, str, str]] = [
            (False, false_label, ""),
            (True, true_label, ""),
        ]
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="stack_action_prompt"):
            yield Static(self.title, classes="prompt_title")
            yield Static(self.help_text, classes="prompt_help")
            with Vertical(id="boolean_choice_options"):
                for i, (_, label, description) in enumerate(self.options):
                    row = OptionRowWidget(i, i + 1, label, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self._select_option_by_index(index)
                self.action_select_choice()
                event.stop()

    def action_previous_choice(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._update_selection()

    def action_next_choice(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._update_selection()

    def action_select_choice(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.options):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            if description:
                lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()


class ConfirmActionScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("enter,y", "confirm", "Confirm", show=False),
        Binding("escape,q,n", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    ConfirmActionScreen #confirm_buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    ConfirmActionScreen Button {
        margin: 0 1;
        min-width: 12;
    }
    ConfirmActionScreen Button.confirm_btn {
        background: #13bfae;
        color: #081014;
        border: tall #1fd6c1;
    }
    ConfirmActionScreen Button.confirm_btn:hover {
        background: #1fd6c1;
    }
    ConfirmActionScreen Button.cancel_btn {
        background: #1a2a30;
        color: #d7fff7;
        border: tall #3a5a5a;
    }
    ConfirmActionScreen Button.cancel_btn:hover {
        background: #0d2028;
    }
    """

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.title = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_prompt"):
            yield Static(self.title, classes="prompt_title")
            yield Static(self.body, classes="prompt_help")
            with Horizontal(id="confirm_buttons"):
                yield Button("Confirm", id="btn_confirm", classes="confirm_btn")
                yield Button("Cancel", id="btn_cancel", classes="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

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
                f"Tool: {self.tool}  · w/s navigate  · enter select  · esc cancel",
                classes="prompt_help",
            )
            with Vertical(id="tool_action_options"):
                for i, (_, label, description) in enumerate(self.options):
                    row = OptionRowWidget(i, i + 1, label, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self._select_option_by_index(index)
                self.action_select_action()
                event.stop()

    def action_previous_action(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._update_selection()

    def action_next_action(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._update_selection()

    def action_select_action(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        """Legacy text rendering kept for tests."""
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
                "· w/s navigate  · enter select  · esc cancel",
                classes="prompt_help",
            )
            with Vertical(id="cloudflared_logs_mode_options"):
                for i, (_, label, description) in enumerate(self.OPTIONS):
                    row = OptionRowWidget(i, i + 1, label, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.OPTIONS):
                self._select_option_by_index(index)
                self.action_select_mode()
                event.stop()

    def action_previous_mode(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.OPTIONS)
        self._update_selection()

    def action_next_mode(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.OPTIONS)
        self._update_selection()

    def action_select_mode(self) -> None:
        self.dismiss(self.OPTIONS[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        """Legacy text rendering kept for tests."""
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
                f"{self.hostname}  · w/s navigate  · enter select  · esc cancel",
                classes="prompt_help",
            )
            with Vertical(id="stack_action_options"):
                for i, (_, label, description) in enumerate(self.options):
                    row = OptionRowWidget(i, i + 1, label, description)
                    if i == self.selected_index:
                        row.add_class("--selected")
                    yield row

    def on_key(self, event: Key) -> None:
        if event.character and event.character.isdigit():
            index = int(event.character) - 1
            if 0 <= index < len(self.options):
                self._select_option_by_index(index)
                self.action_select_action()
                event.stop()

    def action_previous_action(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.options)
        self._update_selection()

    def action_next_action(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.options)
        self._update_selection()

    def action_select_action(self) -> None:
        self.dismiss(self.options[self.selected_index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_option_by_index(self, index: int) -> None:
        self.selected_index = index
        self._update_selection()

    def _update_selection(self) -> None:
        for row in self.query(OptionRowWidget):
            if row.option_index == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def _options_text(self) -> str:
        """Legacy text rendering kept for tests."""
        lines: list[str] = []
        for index, (_, label, description) in enumerate(self.options):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {index + 1}. {label}")
            lines.append(f"  {description}")
            lines.append("")
        return "\n".join(lines).rstrip()
