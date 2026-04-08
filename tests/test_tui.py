from __future__ import annotations

import json
import sys
import types

from typer.testing import CliRunner

from homesrvctl.commands import tui_cmd
from homesrvctl.main import app
from homesrvctl.shell import CommandResult
from homesrvctl.tui import app as textual_app, dashboard, data


def test_run_json_command_parses_success_payload(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        assert command[-1] == "--json"
        return CommandResult(command, 0, json.dumps({"ok": True, "sites": []}), "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["list"])

    assert payload["ok"] is True
    assert payload["sites"] == []
    assert payload["command"][-1] == "--json"
    assert payload["returncode"] == 0


def test_run_json_command_handles_invalid_json(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 0, "not json", "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["list"])

    assert payload["ok"] is False
    assert payload["error"] == "invalid JSON output"


def test_run_json_command_reports_noisy_stdout(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 0, "$ systemctl is-active cloudflared\n{\"ok\": true}", "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["cloudflared", "status"])

    assert payload["ok"] is False
    assert payload["error"] == "invalid JSON output"


def test_run_json_command_parses_json_even_when_exit_code_is_nonzero(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 1, json.dumps({"ok": False, "checks": [{"name": "docker", "ok": False}]}), "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["validate"])

    assert payload["ok"] is False
    assert payload["checks"][0]["name"] == "docker"
    assert payload["returncode"] == 1


def test_build_dashboard_snapshot_uses_existing_json_surfaces() -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(tuple(args))
        if args == ["list"]:
            return {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]}
        if args == ["cloudflared", "status"]:
            return {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"}
        if args == ["validate"]:
            return {"ok": True, "checks": [{"name": "docker", "ok": True, "detail": "found"}]}
        raise AssertionError(f"unexpected args: {args}")

    snapshot = data.build_dashboard_snapshot(run_json_command=fake_run_json_command)

    assert calls == [("list",), ("cloudflared", "status"), ("validate",)]
    assert snapshot["list"]["sites"][0]["hostname"] == "example.com"
    assert snapshot["cloudflared"]["mode"] == "systemd"
    assert snapshot["validate"]["checks"][0]["name"] == "docker"


def test_run_stack_action_dispatches_to_existing_commands(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "doctor")

    assert payload["ok"] is True
    assert calls == [["doctor", "example.com"]]


def test_run_stack_action_dispatches_site_init(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "init-site")

    assert payload["ok"] is True
    assert calls == [["site", "init", "example.com"]]


def test_summarize_stack_action_reports_failure_detail() -> None:
    summary = data.summarize_stack_action("example.com", "up", {"ok": False, "error": "missing docker-compose.yml"})

    assert summary == "up failed for example.com: missing docker-compose.yml"


def test_summarize_stack_action_uses_failing_check_detail() -> None:
    summary = data.summarize_stack_action(
        "example.com",
        "doctor",
        {
            "ok": False,
            "checks": [
                {"name": "hostname directory", "ok": True, "detail": "/srv/homesrvctl/sites/example.com"},
                {"name": "docker-compose.yml", "ok": False, "detail": "/srv/homesrvctl/sites/example.com/docker-compose.yml"},
            ],
        },
    )

    assert summary == "doctor failed for example.com: docker-compose.yml: /srv/homesrvctl/sites/example.com/docker-compose.yml"


def test_summarize_stack_action_labels_site_init() -> None:
    summary = data.summarize_stack_action("example.com", "init-site", {"ok": False, "error": "file exists"})

    assert summary == "site init failed for example.com: file exists"


def test_render_dashboard_includes_sections_and_failures() -> None:
    snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {
            "ok": True,
            "mode": "docker",
            "active": True,
            "detail": "running container(s): cloudflared",
            "config_validation": {
                "ok": True,
                "detail": "fallback service http_status:404",
                "warnings": ["earlier wildcard rule *.com may capture later hostname *.example.com"],
            },
        },
        "validate": {
            "ok": False,
            "checks": [
                {"name": "docker", "ok": True, "detail": "found"},
                {"name": "Traefik URL", "ok": False, "detail": "unreachable"},
            ],
        },
    }

    rendered = dashboard.render_dashboard(snapshot, width=80, selected="validate")

    assert "homesrvctl dashboard" in rendered
    assert "Summary" in rendered
    assert "> Validate: 2 checks, 1 failing" in rendered
    assert "Cloudflared: docker (active), 1 warning(s)" in rendered
    assert "Validate detail" in rendered
    assert "Traefik URL: unreachable" in rendered
    assert "controls: q quit | r refresh | tab/arrow or w/s move | stacks a/d/i/g/u/t/x | mode: manual refresh" in rendered


def test_render_dashboard_stack_detail_includes_stack_rows() -> None:
    snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "list": {
            "ok": True,
            "sites": [
                {"hostname": "example.com", "compose": True},
                {"hostname": "notes.example.com", "compose": False},
            ],
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }

    rendered = dashboard.render_dashboard_state(snapshot, width=80, selected="stacks", selected_stack_index=1)

    assert "> Stacks: 2 stack(s), 1 ready" in rendered
    assert "Stacks detail" in rendered
    assert "selected stack: notes.example.com" in rendered
    assert "stack actions: a/d select | i init site | g doctor | u up | t restart | x down" in rendered
    assert "- example.com [compose=yes]" in rendered
    assert "> notes.example.com [compose=no]" in rendered


def test_tui_requires_interactive_terminal(monkeypatch) -> None:
    monkeypatch.setattr(tui_cmd.sys.stdout, "isatty", lambda: False)
    monkeypatch.setattr(tui_cmd.sys.stdin, "isatty", lambda: False)

    runner = CliRunner()
    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 2, result.output
    assert "tui requires an interactive terminal" in result.output


def test_tui_invokes_textual_app(monkeypatch) -> None:
    monkeypatch.setattr(tui_cmd.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(tui_cmd.sys.stdin, "isatty", lambda: True)
    calls: list[tuple[str, float]] = []

    class FakeTextualApp:
        def __init__(self, refresh_seconds: float = 0.0) -> None:
            calls.append(("init", refresh_seconds))

        def run(self) -> None:
            calls.append(("run", 0.0))

    monkeypatch.setitem(sys.modules, "homesrvctl.tui.app", types.SimpleNamespace(HomesrvctlTextualApp=FakeTextualApp))

    tui_cmd.tui(refresh_seconds=5.0)

    assert calls == [("init", 5.0), ("run", 0.0)]


def test_textual_app_summary_and_stack_list_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "list": {
            "ok": True,
            "sites": [
                {"hostname": "example.com", "compose": True},
                {"hostname": "notes.example.com", "compose": False},
            ],
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_section_index = 0
    app.selected_stack_index = 1

    summary = app._summary_text()
    stack_list = app._stack_list_text()

    assert "> Stacks: 2 stack(s), 1 ready" in summary
    assert "selected: notes.example.com" in stack_list
    assert "> notes.example.com [compose=no]" in stack_list


def test_textual_app_selected_stack_action_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": False}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action: calls.append((hostname, action)) or {"ok": True},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._run_selected_stack_action("up")

    assert calls == [("example.com", "up")]
    assert app.status_message == "up succeeded for example.com"
    assert app.snapshot["list"]["sites"][0]["compose"] is True
