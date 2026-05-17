from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.cloudflare import CloudflareApiError, DnsRecordStatus, TunnelInspection
from homesrvctl.main import app
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers import cloudflare_provider, runner as observer_runner
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.state.store import StateStore


def _write_config(home: Path, sites_root: Path, *, token: str = "test-token") -> Path:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "tunnel_name": "11111111-1111-1111-1111-111111111111",
                "sites_root": str(sites_root),
                "docker_network": "web",
                "traefik_url": "http://localhost:80",
                "cloudflared_config": str(home / "cloudflared" / "config.yml"),
                "cloudflare_api_token": token,
                "profiles": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_stack(sites_root: Path, hostname: str) -> None:
    stack_dir = sites_root / hostname
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")


def _inspection() -> TunnelInspection:
    return TunnelInspection(
        configured_tunnel="11111111-1111-1111-1111-111111111111",
        resolved_tunnel_id="11111111-1111-1111-1111-111111111111",
        resolution_source="config:tunnel_name",
        account_id=None,
        api_available=False,
    )


class FakeCloudflareClient:
    def __init__(self, token: str, *, status: DnsRecordStatus | None = None) -> None:
        self.token = token
        self.status = status or DnsRecordStatus(
            record_name="app.example.com",
            exists=True,
            record_type="CNAME",
            content="11111111-1111-1111-1111-111111111111.cfargotunnel.com",
            proxied=True,
            matches_expected=True,
            record_count=1,
            detail="CNAME -> 11111111-1111-1111-1111-111111111111.cfargotunnel.com (proxied)",
        )
        self.mutations: list[str] = []

    def get_zone(self, zone_name: str) -> dict[str, object]:
        if zone_name == "example.com":
            return {"id": "zone-1", "name": "example.com", "account": {"id": "account-1"}}
        raise CloudflareApiError(f"Cloudflare zone not found or not accessible: {zone_name}")

    def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str) -> DnsRecordStatus:
        return self.status

    def apply_dns_record(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.mutations.append("apply_dns_record")
        raise AssertionError("observer must not mutate DNS")


def test_cloudflare_observer_missing_token_makes_no_api_calls(tmp_path: Path) -> None:
    called = False

    def client_factory(token: str) -> object:
        nonlocal called
        called = True
        raise AssertionError("client should not be created without a token")

    result = cloudflare_provider.observe_cloudflare_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites", cloudflare_api_token=""),
        client_factory=client_factory,
    )

    assert result.ok is False
    assert result.status == "blocked"
    assert result.observations[0].data["token_configured"] is False
    assert "Cloudflare API token is not configured" in result.issues
    assert "test-token" not in json.dumps(result.to_dict())
    assert called is False


def test_cloudflare_observer_no_stacks_reports_no_targets(tmp_path: Path) -> None:
    result = cloudflare_provider.observe_cloudflare_provider(
        HomesrvctlConfig(sites_root=tmp_path / "missing", cloudflare_api_token="test-token"),
        client_factory=lambda token: (_ for _ in ()).throw(AssertionError("client should not be created without targets")),
    )

    assert result.ok is True
    assert result.status == "unknown"
    assert result.observations[0].data["target_count"] == 0


def test_cloudflare_observer_success_persists_and_status_reads_latest(monkeypatch, tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    _write_stack(sites_root, "app.example.com")
    db_path = tmp_path / "state.db"
    monkeypatch.setattr(cloudflare_provider, "inspect_configured_tunnel", lambda config: _inspection())
    monkeypatch.setattr(
        observer_runner,
        "observe_cloudflare_provider",
        lambda config: cloudflare_provider.observe_cloudflare_provider(
            config,
            client_factory=lambda token: FakeCloudflareClient(token),
        ),
    )

    result = observer_runner.run_observers(
        db_path=db_path,
        config=HomesrvctlConfig(sites_root=sites_root, cloudflare_api_token="test-token"),
        stack_runtime=False,
        cloudflared=False,
        traefik=False,
        cloudflare=True,
    )
    status = observer_runner.get_observer_status(db_path=db_path)

    assert result.ok is True
    assert result.results[0].status == "ready"
    assert status.cloudflare is not None
    assert status.cloudflare["source"] == "cloudflare_provider"
    assert status.cloudflare["data"]["data"]["status"] == "ready"


def test_cloudflare_observer_missing_dns_record(monkeypatch, tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setattr(cloudflare_provider, "inspect_configured_tunnel", lambda config: _inspection())

    client = FakeCloudflareClient(
        "test-token",
        status=DnsRecordStatus(
            record_name="app.example.com",
            exists=False,
            record_type="",
            content="",
            proxied=False,
            matches_expected=False,
            detail="record missing",
        ),
    )
    result = cloudflare_provider.observe_cloudflare_provider(
        HomesrvctlConfig(sites_root=sites_root, cloudflare_api_token="test-token"),
        client_factory=lambda token: client,
    )

    assert result.ok is False
    assert result.status == "degraded"
    data = result.observations[0].data
    assert data["records_missing"] == ["app.example.com"]
    assert "app.example.com: DNS record missing" in result.issues


def test_cloudflare_observer_wrong_and_ambiguous_dns_records(monkeypatch, tmp_path: Path) -> None:
    sites_root = tmp_path / "sites"
    _write_stack(sites_root, "app.example.com")
    monkeypatch.setattr(cloudflare_provider, "inspect_configured_tunnel", lambda config: _inspection())

    wrong = cloudflare_provider.observe_cloudflare_provider(
        HomesrvctlConfig(sites_root=sites_root, cloudflare_api_token="test-token"),
        client_factory=lambda token: FakeCloudflareClient(
            token,
            status=DnsRecordStatus(
                record_name="app.example.com",
                exists=True,
                record_type="A",
                content="192.0.2.10",
                proxied=False,
                matches_expected=False,
                record_count=1,
                detail="wrong type A -> 192.0.2.10; expected CNAME",
            ),
        ),
    )
    ambiguous = cloudflare_provider.observe_cloudflare_provider(
        HomesrvctlConfig(sites_root=sites_root, cloudflare_api_token="test-token"),
        client_factory=lambda token: FakeCloudflareClient(
            token,
            status=DnsRecordStatus(
                record_name="app.example.com",
                exists=True,
                record_type="multiple",
                content="",
                proxied=True,
                matches_expected=False,
                multiple_records=True,
                record_count=2,
                detail="multiple conflicting records exist",
            ),
        ),
    )

    assert wrong.status == "degraded"
    assert wrong.observations[0].data["records_wrong_target"] == ["app.example.com"]
    assert ambiguous.status == "degraded"
    assert ambiguous.observations[0].data["records_duplicate_or_ambiguous"] == ["app.example.com"]


def test_observe_run_cloudflare_json_persists_fake_result(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    now = "2026-05-17T00:00:00Z"

    def fake_cloudflare(config: HomesrvctlConfig) -> ObserverResult:
        return ObserverResult(
            observer_name="cloudflare_provider",
            ok=True,
            started_at=now,
            finished_at=now,
            target_type="provider",
            target="cloudflare",
            status="ready",
            summary="Cloudflare DNS ready",
            observations=[
                ObservationRecord(
                    source="cloudflare_provider",
                    target_type="provider",
                    target="cloudflare",
                    status="ready",
                    detail="Cloudflare DNS ready",
                    data={"status": "ready", "token_configured": True},
                )
            ],
        )

    monkeypatch.setattr(observer_runner, "observe_cloudflare_provider", fake_cloudflare)

    result = CliRunner().invoke(
        app,
        [
            "observe",
            "run",
            "--no-stack-runtime",
            "--no-cloudflared",
            "--no-traefik",
            "--cloudflare",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "observe_run"
    assert payload["observers"][0]["observer_name"] == "cloudflare_provider"
    assert StateStore(db_path).latest_event(source="cloudflare_provider") is not None


def test_observe_status_includes_cloudflare_observation(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize(utc_now_iso())
    store.add_event(
        created_at="2026-05-17T00:00:00Z",
        severity="info",
        source="cloudflare_provider",
        target_type="provider",
        target="cloudflare",
        message="Cloudflare DNS ready",
        data={"status": "ready"},
    )

    result = CliRunner().invoke(app, ["observe", "status", "--db-path", str(db_path), "--json"])

    payload = json.loads(result.output)
    assert payload["cloudflare"]["data"]["status"] == "ready"
    assert payload["provider_observers"]["cloudflare"]["data"]["status"] == "ready"


def test_observe_run_default_does_not_run_cloudflare(monkeypatch, tmp_path: Path) -> None:
    def fail_cloudflare(config: HomesrvctlConfig) -> ObserverResult:
        raise AssertionError("Cloudflare observer should be opt-in")

    monkeypatch.setattr(observer_runner, "observe_cloudflare_provider", fail_cloudflare)
    result = observer_runner.run_observers(
        db_path=tmp_path / "state.db",
        config=HomesrvctlConfig(sites_root=tmp_path / "missing"),
        stack_runtime=False,
        cloudflared=False,
        traefik=False,
    )

    assert result.ok is True
    assert result.results == []
