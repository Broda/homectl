from __future__ import annotations

import json
from pathlib import Path
import urllib.error

import yaml
from typer.testing import CliRunner

from homesrvctl.cloudflared import CloudflaredConfigValidation
from homesrvctl.cloudflared_service import CloudflaredRuntime, CloudflaredSystemdUnit
from homesrvctl.main import app
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers import cloudflared_runtime, runner as observer_runner, stacks_runtime, traefik_runtime
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.shell import CommandResult
from homesrvctl.state.store import StateStore


def _command_result(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(command=command, returncode=returncode, stdout=stdout, stderr=stderr)


def _write_config(home: Path, sites_root: Path, *, traefik_url: str = "http://localhost:80") -> Path:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yml"
    cloudflared_config = home / "cloudflared" / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "tunnel_name": "homesrvctl-tunnel",
                "sites_root": str(sites_root),
                "docker_network": "web",
                "traefik_url": traefik_url,
                "cloudflared_config": str(cloudflared_config),
                "cloudflare_api_token": "",
                "profiles": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def test_observer_models_to_dict_shape() -> None:
    record = ObservationRecord(
        source="test",
        target_type="runtime",
        target="thing",
        status="ok",
        detail="observed",
        data={"count": 1},
    )
    result = ObserverResult(
        observer_name="test",
        ok=True,
        started_at="2026-05-17T00:00:00Z",
        finished_at="2026-05-17T00:00:01Z",
        target_type="runtime",
        target="thing",
        status="ok",
        summary="done",
        observations=[record],
    )

    payload = result.to_dict()

    assert payload["observer_name"] == "test"
    assert payload["observations"] == [record.to_dict()]
    assert payload["issues"] == []


def test_state_store_stack_observation_helpers(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize(utc_now_iso())
    store.add_stack_observation(
        stack_hostname="app.example.com",
        observed_at="2026-05-17T00:00:00Z",
        source="stack_runtime",
        status="running",
        detail="1/1 containers running",
        data={"running_count": 1},
    )

    rows = store.list_stack_observations(source="stack_runtime")
    latest = store.latest_stack_observation(source="stack_runtime", stack_hostname="app.example.com")

    assert len(rows) == 1
    assert rows[0]["stack_hostname"] == "app.example.com"
    assert rows[0]["data_json"] == '{"running_count": 1}'
    assert latest is not None
    assert latest["status"] == "running"


def test_stack_runtime_observer_records_no_compose(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    (sites_root / "app.example.com").mkdir(parents=True)
    config = HomesrvctlConfig(sites_root=sites_root)

    result = stacks_runtime.observe_stack_runtime(config, command_exists_func=lambda command: False)

    assert result.ok is True
    assert result.observations[0].target == "app.example.com"
    assert result.observations[0].status == "no_compose"


def test_stack_runtime_observer_records_missing_docker_without_crashing(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    stack_dir = sites_root / "app.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    config = HomesrvctlConfig(sites_root=sites_root)

    result = stacks_runtime.observe_stack_runtime(config, command_exists_func=lambda command: False)

    assert result.ok is False
    assert result.observations[0].status == "error"
    assert "docker command is not available" in result.issues[0]


def test_stack_runtime_observer_parses_compose_json_and_uses_only_ps(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    stack_dir = sites_root / "app.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path | None = None, quiet: bool = False) -> CommandResult:
        commands.append(command)
        assert "up" not in command
        assert "down" not in command
        assert "restart" not in command
        return _command_result(
            command,
            stdout=json.dumps([{"Name": "app-1", "Service": "web", "State": "running"}]),
        )

    result = stacks_runtime.observe_stack_runtime(
        HomesrvctlConfig(sites_root=sites_root),
        runner=fake_runner,
        command_exists_func=lambda command: True,
    )

    assert result.ok is True
    assert result.observations[0].status == "running"
    assert result.observations[0].data["container_count"] == 1
    assert commands == [["docker", "compose", "ps", "--format", "json"]]


def test_stack_runtime_observer_falls_back_to_text_ps(tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    stack_dir = sites_root / "app.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_runner(command: list[str], cwd: Path | None = None, quiet: bool = False) -> CommandResult:
        if command == ["docker", "compose", "ps", "--format", "json"]:
            return _command_result(command, returncode=1, stderr="unknown flag")
        return _command_result(command, stdout="NAME STATUS\napp-1 Up")

    result = stacks_runtime.observe_stack_runtime(
        HomesrvctlConfig(sites_root=sites_root),
        runner=fake_runner,
        command_exists_func=lambda command: True,
    )

    assert result.ok is True
    assert result.observations[0].status == "running"
    assert result.observations[0].data["json_returncode"] == 1


def test_cloudflared_observer_uses_read_only_helpers(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "cloudflared" / "config.yml"
    credentials_path = tmp_path / "cloudflared" / "creds.json"
    config_path.parent.mkdir()
    config_path.write_text(f"credentials-file: {credentials_path}\ningress:\n- service: http_status:404\n", encoding="utf-8")
    credentials_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cloudflared_runtime,
        "detect_cloudflared_runtime",
        lambda quiet=True: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=None,
            logs_command=None,
        ),
    )
    monkeypatch.setattr(
        cloudflared_runtime,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=True: CloudflaredSystemdUnit(
            present=True,
            exec_start=None,
            config_path=str(config_path),
            user=None,
            group=None,
        ),
    )
    monkeypatch.setattr(
        cloudflared_runtime,
        "test_cloudflared_config",
        lambda path: CloudflaredConfigValidation(ok=True, detail="valid", method="structural"),
    )

    result = cloudflared_runtime.observe_cloudflared_runtime(HomesrvctlConfig(cloudflared_config=config_path))

    assert result.ok is True
    assert result.observations[0].status == "active"
    data = result.observations[0].data
    assert data["config_exists"] is True
    assert data["paths_aligned"] is True
    assert data["configured_credentials_readable"] is True


def test_traefik_observer_records_reachable_response() -> None:
    class Response:
        status = 200

    result = traefik_runtime.observe_traefik_runtime(
        HomesrvctlConfig(traefik_url="http://localhost:80"),
        urlopen=lambda url, timeout: Response(),
    )

    assert result.ok is True
    assert result.observations[0].status == "reachable"
    assert result.observations[0].data["status_code"] == 200


def test_traefik_observer_records_error_without_network() -> None:
    def fake_urlopen(url: str, timeout: float) -> object:
        raise urllib.error.URLError("connection refused")

    result = traefik_runtime.observe_traefik_runtime(
        HomesrvctlConfig(traefik_url="http://localhost:80"),
        urlopen=fake_urlopen,
    )

    assert result.ok is False
    assert result.observations[0].status == "unreachable"
    assert "connection refused" in result.issues[0]


def test_observe_run_command_writes_observations_with_fake_observers(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    now = "2026-05-17T00:00:00Z"

    def fake_stack(config: HomesrvctlConfig) -> ObserverResult:
        return ObserverResult(
            observer_name="stack_runtime",
            ok=True,
            started_at=now,
            finished_at=now,
            target_type="stack",
            target=None,
            status="ok",
            summary="observed 1 stacks",
            observations=[
                ObservationRecord(
                    source="stack_runtime",
                    target_type="stack",
                    target="app.example.com",
                    status="running",
                    detail="1/1 containers running",
                    data={"running_count": 1},
                )
            ],
        )

    monkeypatch.setattr(observer_runner, "observe_stack_runtime", fake_stack)

    result = CliRunner().invoke(
        app,
        [
            "observe",
            "run",
            "--no-cloudflared",
            "--no-traefik",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "observe_run"
    assert payload["ok"] is True
    assert StateStore(db_path).latest_stack_observation(source="stack_runtime") is not None


def test_observe_status_reports_missing_and_latest_observations(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    missing = CliRunner().invoke(app, ["observe", "status", "--db-path", str(db_path), "--json"])
    assert missing.exit_code == 1
    missing_payload = json.loads(missing.output)
    assert missing_payload["ok"] is False

    store = StateStore(db_path)
    store.initialize(utc_now_iso())
    store.add_stack_observation(
        stack_hostname="app.example.com",
        observed_at="2026-05-17T00:00:00Z",
        source="stack_runtime",
        status="running",
        detail="1/1 containers running",
        data={"running_count": 1},
    )
    store.add_event(
        created_at="2026-05-17T00:00:00Z",
        severity="info",
        source="cloudflared_runtime",
        target_type="runtime",
        target="cloudflared",
        message="active",
        data={"status": "active"},
    )
    store.add_event(
        created_at="2026-05-17T00:00:00Z",
        severity="info",
        source="traefik_runtime",
        target_type="runtime",
        target="http://localhost:80",
        message="reachable",
        data={"status": "reachable"},
    )

    status = CliRunner().invoke(app, ["observe", "status", "--db-path", str(db_path), "--json"])

    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["ok"] is True
    assert payload["stack_runtime"]["stack_count"] == 1
    assert payload["cloudflared"]["data"]["status"] == "active"
    assert payload["traefik"]["data"]["status"] == "reachable"
