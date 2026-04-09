from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

APP_INIT_TEMPLATE_OPTIONS: list[tuple[str, str]] = [
    ("placeholder", "Smallest possible app scaffold."),
    ("static", "nginx static site with starter assets."),
    ("static-api", "Static site plus a small Python API."),
    ("node", "Node app scaffold with healthcheck."),
    ("python", "Python app scaffold with healthcheck."),
]


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
        if event.character and event.character in {"1", "2", "3", "4", "5"}:
            self.selected_index = int(event.character) - 1
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
