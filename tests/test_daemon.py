from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.main import app
from homesrvctl.services.daemon import run_daemon
from homesrvctl.state.store import StateStore


def _write_config(home: Path, sites_root: Path) -> Path:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yml"
    config_path.write_text(
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
    return config_path


def _write_stack(sites_root: Path, hostname: str) -> Path:
    stack_dir = sites_root / hostname
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return stack_dir


def test_daemon_run_once_json_refreshes_stack_state(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(app, ["daemon", "run", "--once", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "daemon_run"
    assert payload["mode"] == "once"
    assert payload["ok"] is True
    assert payload["db_path"] == str(db_path)
    assert payload["cycle_count"] == 1
    assert payload["last_refresh"]["scanned_count"] == 1
    assert payload["last_refresh"]["updated_count"] == 1
    assert [row["hostname"] for row in StateStore(db_path).list_stacks()] == ["app.example.com"]


def test_daemon_run_once_missing_config_reports_json_error(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "homesrvctl.db"
    missing_config = tmp_path / "missing.yml"

    result = CliRunner().invoke(
        app,
        ["daemon", "run", "--once", "--db-path", str(db_path), "--config-path", str(missing_config), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "daemon_run"
    assert payload["ok"] is False
    assert payload["cycle_count"] == 1
    assert "config file not found" in payload["error"]
    assert "config file not found" in payload["issues"][0]


def test_daemon_run_json_requires_once(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "homesrvctl.db"

    result = CliRunner().invoke(app, ["daemon", "run", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "daemon_run"
    assert payload["ok"] is False
    assert payload["mode"] == "loop"
    assert "--once" in payload["error"]


def test_daemon_loop_can_run_bounded_cycles_without_sleeping(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setenv("HOME", str(home))
    sleep_calls: list[float] = []
    cycles: list[object] = []

    result = run_daemon(
        db_path=db_path,
        interval_seconds=2.5,
        sleep_func=sleep_calls.append,
        max_cycles=2,
        on_cycle=cycles.append,
    )

    assert result.ok is True
    assert result.mode == "loop"
    assert result.cycle_count == 2
    assert sleep_calls == [2.5]
    assert len(cycles) == 2
    assert StateStore(db_path).has_cached_stack_data() is True


def test_daemon_status_reports_missing_and_initialized_db(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setenv("HOME", str(home))
    runner = CliRunner()

    missing = runner.invoke(app, ["daemon", "status", "--db-path", str(db_path), "--json"])

    assert missing.exit_code == 1
    missing_payload = json.loads(missing.output)
    assert missing_payload["schema_version"] == "1"
    assert missing_payload["action"] == "daemon_status"
    assert missing_payload["ok"] is False
    assert missing_payload["initialized"] is False
    assert missing_payload["cache_available"] is False

    run_result = runner.invoke(app, ["daemon", "run", "--once", "--db-path", str(db_path), "--json"])
    assert run_result.exit_code == 0, run_result.output
    status = runner.invoke(app, ["daemon", "status", "--db-path", str(db_path), "--json"])

    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is True
    assert payload["initialized"] is True
    assert payload["stack_count"] == 1
    assert payload["cache_available"] is True
    assert payload["last_refresh_at"] is not None
    assert payload["daemon_heartbeat_at"] is not None
    assert payload["daemon_active"] is None


def test_daemon_records_lifecycle_and_issue_events(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "missing-sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(app, ["daemon", "run", "--once", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 1
    events = StateStore(db_path).list_recent_events(source="daemon", limit=10)
    assert [event["message"] for event in reversed(events)] == [
        "daemon started",
        "refresh completed with issues",
        "daemon stopped",
    ]
