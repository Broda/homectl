from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.config import load_config
from homesrvctl.main import app
from homesrvctl.services.refresh import refresh_local_stack_state, utc_now_iso
from homesrvctl.state.schema import SCHEMA_VERSION
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
                "profiles": {
                    "edge": {
                        "docker_network": "edge",
                        "traefik_url": "http://localhost:9000",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_stack(
    sites_root: Path,
    hostname: str,
    *,
    compose: bool = True,
    stack_config: dict[str, object] | None = None,
) -> Path:
    stack_dir = sites_root / hostname
    stack_dir.mkdir(parents=True, exist_ok=True)
    if compose:
        (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    if stack_config is not None:
        (stack_dir / "homesrvctl.yml").write_text(yaml.safe_dump(stack_config, sort_keys=False), encoding="utf-8")
    return stack_dir


def test_state_schema_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "homesrvctl.db"
    store = StateStore(db_path)

    assert store.initialize(utc_now_iso()) is True
    assert store.initialize(utc_now_iso()) is False

    status = store.status()
    assert status.exists is True
    assert status.initialized is True
    assert status.schema_version == SCHEMA_VERSION
    assert status.stack_count == 0
    assert status.issues == []


def test_db_status_reports_missing_and_initialized_json(tmp_path: Path) -> None:
    db_path = tmp_path / "homesrvctl.db"
    runner = CliRunner()

    missing_result = runner.invoke(app, ["db", "status", "--path", str(db_path), "--json"])

    assert missing_result.exit_code == 1
    missing_payload = json.loads(missing_result.output)
    assert missing_payload["schema_version"] == "1"
    assert missing_payload["ok"] is False
    assert missing_payload["exists"] is False
    assert missing_payload["initialized"] is False
    assert missing_payload["state_schema_version"] is None
    assert missing_payload["db_path"] == str(db_path)

    init_result = runner.invoke(app, ["db", "init", "--path", str(db_path), "--json"])
    assert init_result.exit_code == 0, init_result.output
    init_payload = json.loads(init_result.output)
    assert init_payload["ok"] is True
    assert init_payload["initialized"] is True
    assert init_payload["schema_version"] == "1"
    assert init_payload["state_schema_version"] == SCHEMA_VERSION

    status_result = runner.invoke(app, ["db", "status", "--path", str(db_path), "--json"])
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    assert status_payload["schema_version"] == "1"
    assert status_payload["ok"] is True
    assert status_payload["exists"] is True
    assert status_payload["initialized"] is True
    assert status_payload["state_schema_version"] == SCHEMA_VERSION
    assert status_payload["cache_available"] is False
    assert status_payload["stack_count"] == 0


def test_db_status_reports_uninitialized_database_json(tmp_path: Path) -> None:
    db_path = tmp_path / "homesrvctl.db"
    sqlite3.connect(db_path).close()

    result = CliRunner().invoke(app, ["db", "status", "--path", str(db_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["exists"] is True
    assert payload["initialized"] is False
    assert payload["schema_version"] == "1"
    assert payload["state_schema_version"] is None
    assert payload["issues"]


def test_refresh_discovers_stack_directories_and_writes_rows(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(
        sites_root,
        "app.example.com",
        stack_config={
            "scaffold": {"kind": "app", "template": "node"},
            "profile": "edge",
        },
    )
    _write_stack(sites_root, "draft.example.com", compose=False)

    result = refresh_local_stack_state(db_path=db_path, config=load_config())

    assert result.ok is True
    assert result.scanned_count == 2
    assert result.updated_count == 2
    assert [stack.hostname for stack in result.stacks] == ["app.example.com", "draft.example.com"]

    rows = StateStore(db_path).list_stacks()
    assert [row["hostname"] for row in rows] == ["app.example.com", "draft.example.com"]
    app_row = rows[0]
    assert app_row["has_compose"] == 1
    assert app_row["has_stack_config"] == 1
    assert app_row["scaffold_kind"] == "app"
    assert app_row["scaffold_template"] == "node"
    assert app_row["profile"] == "edge"
    assert app_row["docker_network"] == "edge"
    assert app_row["traefik_url"] == "http://localhost:9000"
    draft_row = rows[1]
    assert draft_row["has_compose"] == 0
    assert draft_row["has_stack_config"] == 0

    store = StateStore(db_path)
    snapshots = store.list_stack_snapshots()
    assert [snapshot.hostname for snapshot in snapshots] == ["app.example.com", "draft.example.com"]
    assert snapshots[0].has_compose is True
    assert snapshots[0].has_stack_config is True
    assert snapshots[0].scaffold_kind == "app"
    assert snapshots[0].updated_at is not None
    assert store.has_cached_stack_data() is True
    assert store.last_stack_refresh_at() is not None


def test_refresh_is_idempotent_and_supports_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(sites_root, "app.example.com", stack_config={"scaffold": {"kind": "site", "template": "static"}})

    runner = CliRunner()
    first = runner.invoke(app, ["refresh", "--db-path", str(db_path), "--json"])
    second = runner.invoke(app, ["refresh", "--db-path", str(db_path), "--json"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    payload = json.loads(second.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "refresh"
    assert payload["ok"] is True
    assert payload["scanned_count"] == 1
    assert payload["updated_count"] == 1
    assert payload["stacks"][0]["hostname"] == "app.example.com"
    assert payload["stacks"][0]["has_compose"] is True
    assert payload["stacks"][0]["scaffold_kind"] == "site"
    assert len(StateStore(db_path).list_stacks()) == 1


def test_refresh_stack_missing_reports_json_error(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(
        app,
        ["refresh", "--stack", "missing.example.com", "--db-path", str(db_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is False
    assert "hostname directory does not exist" in payload["error"]


def test_db_rebuild_repopulates_stack_state_without_clearing_operations(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(sites_root, "old.example.com")
    refresh_local_stack_state(db_path=db_path, config=load_config())

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO operations (operation_type, status, started_at, summary)
            VALUES (?, ?, ?, ?)
            """,
            ("test", "ok", utc_now_iso(), "preserve me"),
        )

    old_stack_dir = sites_root / "old.example.com"
    for child in old_stack_dir.iterdir():
        child.unlink()
    old_stack_dir.rmdir()
    _write_stack(sites_root, "new.example.com", stack_config={"docker_network": "edge"})

    result = CliRunner().invoke(app, ["db", "rebuild", "--path", str(db_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is True
    assert payload["scanned_count"] == 1
    assert payload["updated_count"] == 1
    assert payload["stacks"][0]["hostname"] == "new.example.com"
    assert [row["hostname"] for row in StateStore(db_path).list_stacks()] == ["new.example.com"]
    with sqlite3.connect(db_path) as connection:
        operation_count = connection.execute("SELECT count(*) FROM operations").fetchone()[0]
    assert operation_count == 1


def test_db_rebuild_reports_config_errors_as_json(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "homesrvctl.db"
    missing_config = tmp_path / "missing.yml"

    result = CliRunner().invoke(
        app,
        ["db", "rebuild", "--path", str(db_path), "--config-path", str(missing_config), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is False
    assert payload["db_path"] == str(db_path)
    assert "config file not found" in payload["error"]


def test_list_cached_uses_database_without_sites_root(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(
        sites_root,
        "app.example.com",
        stack_config={"scaffold": {"kind": "app", "template": "node"}},
    )
    refresh_local_stack_state(db_path=db_path, config=load_config())
    for child in (sites_root / "app.example.com").iterdir():
        child.unlink()
    (sites_root / "app.example.com").rmdir()
    sites_root.rmdir()

    result = CliRunner().invoke(app, ["list", "--cached", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is True
    assert payload["source"] == "cache"
    assert payload["cache_available"] is True
    assert payload["last_refresh_at"] is not None
    assert payload["db_path"] == str(db_path)
    assert payload["sites"][0]["hostname"] == "app.example.com"
    assert payload["sites"][0]["compose"] is True
    assert payload["sites"][0]["scaffold_kind"] == "app"
    assert payload["sites"][0]["scaffold_template"] == "node"
    assert payload["sites"][0]["updated_at"] is not None


def test_list_cached_human_output_is_concise(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(sites_root, "app.example.com")
    refresh_local_stack_state(db_path=db_path, config=load_config())

    result = CliRunner().invoke(app, ["list", "--cached", "--db-path", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "app.example.com" in result.output
    assert "compose=yes" in result.output
    assert "source=cache" not in result.output


def test_list_cached_missing_database_reports_helpful_json(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "missing.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(app, ["list", "--cached", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is False
    assert payload["source"] == "cache"
    assert payload["cache_available"] is False
    assert "homesrvctl refresh" in payload["error"]
    assert "homesrvctl db rebuild" in payload["error"]
    assert "homesrvctl list --live" in payload["error"]


def test_list_refresh_updates_cache_and_returns_cached_json(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state" / "homesrvctl.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    _write_stack(sites_root, "app.example.com", stack_config={"profile": "edge"})

    result = CliRunner().invoke(app, ["list", "--refresh", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is True
    assert payload["source"] == "cache"
    assert payload["cache_available"] is True
    assert payload["sites"][0]["hostname"] == "app.example.com"
    assert payload["sites"][0]["profile"] == "edge"
    assert StateStore(db_path).has_cached_stack_data() is True
