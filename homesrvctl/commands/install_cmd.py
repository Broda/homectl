from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import typer

from homesrvctl import __version__
from homesrvctl.utils import with_json_schema

install_cli = typer.Typer(help="Inspect homesrvctl installation and command-path wiring.")


@install_cli.command("status")
def install_status(
    json_output: bool = typer.Option(False, "--json", help="Print the install status as JSON."),
) -> None:
    """Show package, executable, and common pipx path-conflict status."""
    payload = build_install_status()
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        return

    typer.echo(f"homesrvctl version: {payload['version']}")
    typer.echo(f"python executable: {payload['python_executable']}")
    typer.echo(f"invoked script: {payload['invoked_script']}")
    typer.echo(f"PATH command: {payload['path_command'] or '<not found>'}")
    typer.echo(f"pipx venv: {payload['pipx_venv']}")
    typer.echo(f"pipx app: {payload['pipx_app']}")
    typer.echo(f"pipx installed: {'yes' if payload['pipx_installed'] else 'no'}")
    typer.echo(f"running from pipx: {'yes' if payload['running_from_pipx'] else 'no'}")
    typer.echo(f"user bin: {payload['user_bin']}")
    typer.echo(f"user bin exists: {'yes' if payload['user_bin_exists'] else 'no'}")
    typer.echo(f"user bin symlink: {'yes' if payload['user_bin_is_symlink'] else 'no'}")
    typer.echo(f"user bin target: {payload['user_bin_target'] or '<none>'}")
    typer.echo(f"user bin points to pipx: {'yes' if payload['user_bin_points_to_pipx'] else 'no'}")
    typer.echo(f"install state: {payload['install_state']}")
    for issue in payload["issues"]:
        typer.echo(f"issue: {issue}")
    next_commands = payload["next_commands"]
    if next_commands:
        typer.echo("")
        typer.echo("next commands:")
        for command in next_commands:
            typer.echo(command)


def version(
    json_output: bool = typer.Option(False, "--json", help="Print version details as JSON."),
) -> None:
    """Print the homesrvctl package version and executable context."""
    payload = {
        "action": "version",
        "ok": True,
        "version": __version__,
        "python_executable": sys.executable,
        "invoked_script": sys.argv[0],
        "path_command": shutil.which("homesrvctl"),
    }
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        return
    typer.echo(__version__)


def build_install_status() -> dict[str, object]:
    home = Path.home()
    pipx_venv = home / ".local/share/pipx/venvs/homesrvctl"
    pipx_app = pipx_venv / "bin/homesrvctl"
    user_bin = home / ".local/bin/homesrvctl"
    path_command = shutil.which("homesrvctl")
    user_bin_target = _symlink_target(user_bin)
    pipx_installed = pipx_app.exists()
    running_from_pipx = _path_is_under(Path(sys.executable), pipx_venv)
    user_bin_points_to_pipx = _same_resolved_path(user_bin, pipx_app)
    path_command_points_to_pipx = _same_resolved_path(Path(path_command), pipx_app) if path_command else False

    issues: list[str] = []
    next_commands: list[str] = []
    if pipx_installed and user_bin.exists() and not user_bin_points_to_pipx:
        issues.append(
            f"{user_bin} exists but does not point to the pipx homesrvctl executable at {pipx_app}"
        )
        next_commands.extend(
            [
                f"mv {user_bin} {user_bin}.old",
                "pipx ensurepath",
                "pipx reinstall homesrvctl",
            ]
        )
    elif pipx_installed and path_command and not path_command_points_to_pipx and not running_from_pipx:
        issues.append(f"PATH resolves homesrvctl to {path_command}, not the pipx executable at {pipx_app}")
    elif not pipx_installed:
        issues.append("pipx homesrvctl environment was not found")
        next_commands.append("python3 -m pipx install homesrvctl")

    if pipx_installed and not running_from_pipx:
        next_commands.append(f"{pipx_app} --help")

    install_state = "ok" if not issues else "attention"
    return {
        "action": "install_status",
        "ok": not issues,
        "version": __version__,
        "python_executable": sys.executable,
        "invoked_script": sys.argv[0],
        "path_command": path_command,
        "pipx_venv": str(pipx_venv),
        "pipx_app": str(pipx_app),
        "pipx_installed": pipx_installed,
        "running_from_pipx": running_from_pipx,
        "user_bin": str(user_bin),
        "user_bin_exists": user_bin.exists(),
        "user_bin_is_symlink": user_bin.is_symlink(),
        "user_bin_target": user_bin_target,
        "user_bin_points_to_pipx": user_bin_points_to_pipx,
        "path_command_points_to_pipx": path_command_points_to_pipx,
        "install_state": install_state,
        "issues": issues,
        "next_commands": _dedupe(next_commands),
    }


def _symlink_target(path: Path) -> str | None:
    if not path.is_symlink():
        return None
    try:
        return os.readlink(path)
    except OSError:
        return None


def _same_resolved_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _path_is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _dedupe(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        deduped.append(command)
    return deduped
