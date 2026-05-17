from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.commands import daemon_cmd
from homesrvctl.main import app
from homesrvctl.services import daemon_systemd
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.services.daemon_systemd import DaemonUnitConfig
from homesrvctl.shell import CommandResult
from homesrvctl.state.store import StateStore


def _command_result(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(command=command, returncode=returncode, stdout=stdout, stderr=stderr)


def _write_config(home: Path, sites_root: Path) -> None:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yml").write_text(
        yaml.safe_dump(
            {
                "tunnel_name": "homesrvctl-tunnel",
                "sites_root": str(sites_root),
                "docker_network": "web",
                "traefik_url": "http://localhost:8081",
                "cloudflared_config": "/etc/cloudflared/config.yml",
                "cloudflare_api_token": "",
                "profiles": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_stack(sites_root: Path, hostname: str) -> None:
    stack_dir = sites_root / hostname
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")


def test_render_daemon_unit_includes_expected_exec_start(tmp_path: Path) -> None:
    unit = daemon_systemd.render_daemon_unit(
        DaemonUnitConfig(
            unit_name="homesrvctl-daemon.service",
            interval_seconds=60,
            db_path=tmp_path / "state" / "homesrvctl.db",
            config_path=tmp_path / "config.yml",
            executable="/usr/local/bin/homesrvctl",
            observe_runtime=True,
        )
    )

    assert "Description=homesrvctl read-only local observer daemon" in unit
    assert "Restart=on-failure" in unit
    assert "ExecStart=/usr/local/bin/homesrvctl daemon run --interval-seconds 60" in unit
    assert f"--db-path {tmp_path / 'state' / 'homesrvctl.db'}" in unit
    assert f"--config-path {tmp_path / 'config.yml'}" in unit
    assert "--observe-runtime" in unit
    assert "cloudflare_api_token" not in unit


def test_daemon_install_dry_run_json_does_not_write_unit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(daemon_systemd, "resolve_homesrvctl_executable", lambda: "/usr/local/bin/homesrvctl")
    db_path = tmp_path / "state" / "homesrvctl.db"

    result = CliRunner().invoke(
        app,
        [
            "daemon",
            "install",
            "--dry-run",
            "--json",
            "--interval-seconds",
            "45",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "daemon_install"
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["wrote_unit"] is False
    assert payload["daemon_reload_ran"] is False
    assert payload["unit_path"] == "/etc/systemd/system/homesrvctl-daemon.service"
    assert "ExecStart=/usr/local/bin/homesrvctl daemon run" in payload["unit_content"]


def test_daemon_install_requires_root_for_system_unit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(daemon_systemd, "resolve_homesrvctl_executable", lambda: "/usr/local/bin/homesrvctl")
    monkeypatch.setattr(daemon_systemd.os, "geteuid", lambda: 1000)

    result = daemon_systemd.install_daemon_unit(
        interval_seconds=60,
        db_path=tmp_path / "state" / "homesrvctl.db",
        unit_dir=tmp_path / "systemd",
    )

    assert result.ok is False
    assert result.wrote_unit is False
    assert result.error == "system daemon install requires sudo/root"
    assert not result.unit_path.exists()


def test_daemon_install_writes_unit_and_runs_systemctl_with_fake_runner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(daemon_systemd, "resolve_homesrvctl_executable", lambda: "/usr/local/bin/homesrvctl")
    monkeypatch.setattr(daemon_systemd.os, "geteuid", lambda: 0)
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: True)
    commands: list[list[str]] = []

    def runner(command: list[str], quiet: bool = False) -> CommandResult:
        commands.append(command)
        return _command_result(command)

    result = daemon_systemd.install_daemon_unit(
        interval_seconds=60,
        db_path=tmp_path / "state" / "homesrvctl.db",
        unit_dir=tmp_path / "systemd",
        now=True,
        runner=runner,
    )

    assert result.ok is True
    assert result.wrote_unit is True
    assert result.daemon_reload_ran is True
    assert result.enabled is True
    assert result.started is True
    assert result.unit_path.exists()
    assert commands == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "homesrvctl-daemon.service"],
    ]


def test_daemon_install_fails_without_systemctl_before_writing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(daemon_systemd, "resolve_homesrvctl_executable", lambda: "/usr/local/bin/homesrvctl")
    monkeypatch.setattr(daemon_systemd.os, "geteuid", lambda: 0)
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: False)

    result = daemon_systemd.install_daemon_unit(
        interval_seconds=60,
        db_path=tmp_path / "state" / "homesrvctl.db",
        unit_dir=tmp_path / "systemd",
    )

    assert result.ok is False
    assert result.error == "systemctl is not available"
    assert result.wrote_unit is False
    assert not result.unit_path.exists()


def test_daemon_uninstall_dry_run_preserves_unit(tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd"
    unit_dir.mkdir()
    unit_path = unit_dir / "homesrvctl-daemon.service"
    unit_path.write_text("[Unit]\nDescription=test\n", encoding="utf-8")

    result = daemon_systemd.uninstall_daemon_unit(unit_dir=unit_dir, force=True, dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert result.existed is True
    assert result.removed is False
    assert result.db_preserved is True
    assert unit_path.exists()


def test_daemon_status_includes_systemd_unavailable_fields(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: False)

    run_result = CliRunner().invoke(app, ["daemon", "run", "--once", "--db-path", str(db_path), "--json"])
    assert run_result.exit_code == 0, run_result.output
    status = CliRunner().invoke(app, ["daemon", "status", "--db-path", str(db_path), "--json"])

    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["ok"] is True
    assert payload["initialized"] is True
    assert payload["stack_count"] == 1
    assert payload["systemd_available"] is False
    assert payload["unit_installed"] is False
    assert payload["supervised"] is False
    assert "systemctl is not available" in payload["systemd_issues"]


def test_daemon_systemd_status_reports_unit_state(monkeypatch, tmp_path: Path) -> None:
    unit_dir = tmp_path / "systemd"
    unit_dir.mkdir()
    (unit_dir / "homesrvctl-daemon.service").write_text("[Unit]\nDescription=test\n", encoding="utf-8")
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: True)

    def runner(command: list[str], quiet: bool = False) -> CommandResult:
        if "--property" in command and "ActiveState" in command:
            return _command_result(command, stdout="active")
        if "--property" in command and "SubState" in command:
            return _command_result(command, stdout="running")
        if command[:2] == ["systemctl", "is-enabled"]:
            return _command_result(command, stdout="enabled")
        raise AssertionError(command)

    status = daemon_systemd.inspect_daemon_systemd(unit_dir=unit_dir, runner=runner)

    assert status.systemd_available is True
    assert status.unit_installed is True
    assert status.active_state == "active"
    assert status.sub_state == "running"
    assert status.enabled_state == "enabled"
    assert status.supervised is True


def test_daemon_start_stop_restart_use_systemctl(monkeypatch) -> None:
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: True)
    commands: list[list[str]] = []

    def runner(command: list[str], quiet: bool = False) -> CommandResult:
        commands.append(command)
        return _command_result(command)

    for action in ("start", "stop", "restart"):
        result = daemon_systemd.run_daemon_systemd_action(action, runner=runner)
        assert result.ok is True
        assert result.action == f"daemon_{action}"

    assert commands == [
        ["systemctl", "start", "homesrvctl-daemon.service"],
        ["systemctl", "stop", "homesrvctl-daemon.service"],
        ["systemctl", "restart", "homesrvctl-daemon.service"],
    ]


def test_daemon_start_failure_reports_error(monkeypatch) -> None:
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: True)

    def runner(command: list[str], quiet: bool = False) -> CommandResult:
        return _command_result(command, returncode=5, stderr="unit not found")

    result = daemon_systemd.run_daemon_systemd_action("start", runner=runner)

    assert result.ok is False
    assert result.returncode == 5
    assert result.error == "unit not found"


def test_daemon_logs_use_journalctl(monkeypatch) -> None:
    monkeypatch.setattr(daemon_systemd, "command_exists", lambda command: True)

    def runner(command: list[str], quiet: bool = False) -> CommandResult:
        return _command_result(command, stdout="daemon log line")

    result = daemon_systemd.run_daemon_logs(lines=25, runner=runner)

    assert result.ok is True
    assert result.command == ["journalctl", "-u", "homesrvctl-daemon.service", "-n", "25", "--no-pager"]
    assert result.stdout == "daemon log line"


def test_daemon_status_cli_keeps_existing_db_fields_when_unit_missing(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "homesrvctl.db"
    StateStore(db_path).initialize(utc_now_iso())
    monkeypatch.setattr(daemon_cmd.daemon_systemd, "command_exists", lambda command: False)

    result = CliRunner().invoke(app, ["daemon", "status", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "daemon_status"
    assert payload["initialized"] is True
    assert payload["state_schema_version"] == 1
    assert payload["stack_count"] == 0
    assert payload["cache_available"] is False
    assert payload["systemd_available"] is False
