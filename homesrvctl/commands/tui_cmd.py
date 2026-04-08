from __future__ import annotations

import sys

import typer


def tui(
    refresh_seconds: float = typer.Option(
        0.0,
        "--refresh-seconds",
        min=0.0,
        help="Automatically refresh the dashboard every N seconds. Use 0 to refresh manually with r.",
    ),
) -> None:
    """Launch the terminal dashboard."""
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        raise typer.BadParameter("tui requires an interactive terminal")

    try:
        from homesrvctl.tui.app import HomesrvctlTextualApp
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise typer.BadParameter("tui now requires the Textual dependency; reinstall homesrvctl to update the environment") from exc
        raise

    app = HomesrvctlTextualApp(refresh_seconds=refresh_seconds)
    app.run()
