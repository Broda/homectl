from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.cloudflare import CloudflareApiError
from homesrvctl.main import app
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers import runner as observer_runner
from homesrvctl.services.observers import ses_provider
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.state.store import StateStore


def _write_config(home: Path, sites_root: Path, *, token: str = "") -> Path:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "tunnel_name": "homesrvctl-tunnel",
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


class FakeSesClient:
    def __init__(
        self,
        *,
        sending_enabled: bool = True,
        identities: list[str] | None = None,
        verification: dict[str, dict[str, object]] | None = None,
        dkim: dict[str, dict[str, object]] | None = None,
        mail_from: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.sending_enabled = sending_enabled
        self.identities = ["example.com"] if identities is None else identities
        self.verification = (
            {
                "example.com": {
                    "VerificationStatus": "Success",
                    "VerificationToken": "verification-token",
                }
            }
            if verification is None
            else verification
        )
        self.dkim = (
            {
                "example.com": {
                    "DkimEnabled": True,
                    "DkimVerificationStatus": "Success",
                    "DkimTokens": ["dkim1", "dkim2", "dkim3"],
                }
            }
            if dkim is None
            else dkim
        )
        self.mail_from = (
            {
                "example.com": {
                    "MailFromDomain": "mail.example.com",
                    "MailFromDomainStatus": "Success",
                }
            }
            if mail_from is None
            else mail_from
        )
        self.mutations: list[str] = []

    def get_account(self) -> dict[str, object]:
        return {"sending_enabled": self.sending_enabled}

    def list_domain_identities(self) -> list[str]:
        return self.identities

    def get_verification_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return {domain: self.verification[domain] for domain in domains if domain in self.verification}

    def get_dkim_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return {domain: self.dkim[domain] for domain in domains if domain in self.dkim}

    def get_mail_from_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return {domain: self.mail_from[domain] for domain in domains if domain in self.mail_from}

    def verify_domain_identity(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.mutations.append("verify_domain_identity")
        raise AssertionError("observer must not mutate SES identities")


class FakeCloudflareClient:
    def __init__(self, records: dict[str, list[dict[str, object]]]) -> None:
        self.records = records

    def get_zone(self, zone_name: str) -> dict[str, object]:
        if zone_name == "example.com":
            return {"id": "zone-1", "name": "example.com"}
        raise CloudflareApiError(f"Cloudflare zone not found or not accessible: {zone_name}")

    def list_dns_records(self, zone_id: str, name: str) -> list[dict[str, object]]:
        return self.records.get(name, [])


class NoCredentialsError(Exception):
    pass


def test_ses_observer_missing_boto3_reports_blocked(tmp_path: Path) -> None:
    def missing_boto3(region: str) -> object:
        raise ses_provider.SesObserverSetupError(
            "AWS SES observer requires boto3; install `homesrvctl[aws]`",
            "missing_boto3",
        )

    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=missing_boto3,
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    assert result.ok is False
    assert result.status == "blocked"
    assert result.observations[0].data["boto3_available"] is False
    assert "AWS SES observer requires boto3" in result.issues[0]
    assert "AWS_SECRET_ACCESS_KEY" not in json.dumps(result.to_dict())


def test_ses_observer_missing_region_does_not_create_client(tmp_path: Path) -> None:
    def fail_client(region: str) -> object:
        raise AssertionError("client should not be created without a region")

    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=fail_client,
        env={ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    assert result.status == "blocked"
    assert "AWS region is not configured" in result.issues
    assert "set aws_region" in " ".join(result.observations[0].data["next_steps"]).lower()


def test_ses_observer_missing_credentials_reports_issue(tmp_path: Path) -> None:
    class MissingCredentialsClient(FakeSesClient):
        def get_account(self) -> dict[str, object]:
            raise NoCredentialsError("unable to locate credentials")

    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=lambda region: MissingCredentialsClient(),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    assert result.status == "blocked"
    assert result.observations[0].data["credentials_available"] is False
    assert "AWS credentials unavailable" in result.issues[0]


def test_ses_observer_ready_domain_reports_dns_requirements(tmp_path: Path) -> None:
    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=lambda region: FakeSesClient(),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    data = result.observations[0].data
    records = data["required_dns_records"]

    assert result.ok is True
    assert result.status == "ready"
    assert data["sending_enabled"] is True
    assert data["identities_checked"] == 1
    assert any(record["purpose"] == "ses_identity_verification" for record in records)
    assert sum(1 for record in records if record["purpose"] == "ses_dkim") == 3
    assert any(record["purpose"] == "ses_mail_from_mx" for record in records)
    assert any(record["purpose"] == "dmarc_guidance" for record in records)


def test_ses_observer_missing_domain_identity_is_degraded(tmp_path: Path) -> None:
    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=lambda region: FakeSesClient(identities=[], verification={}, dkim={}, mail_from={}),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    assert result.status == "degraded"
    assert "example.com: SES domain identity is missing" in result.issues
    assert result.observations[0].data["domain_results"][0]["identity_exists"] is False


def test_ses_observer_pending_identity_includes_verification_record(tmp_path: Path) -> None:
    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=lambda region: FakeSesClient(
            verification={
                "example.com": {
                    "VerificationStatus": "Pending",
                    "VerificationToken": "pending-token",
                }
            }
        ),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    records = result.observations[0].data["required_dns_records"]

    assert result.status == "degraded"
    assert "example.com: SES domain identity verification is Pending" in result.issues
    assert {
        "name": "_amazonses.example.com",
        "type": "TXT",
        "content": "pending-token",
        "purpose": "ses_identity_verification",
        "recommended": False,
    } in records


def test_ses_observer_dkim_and_mail_from_pending(tmp_path: Path) -> None:
    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(sites_root=tmp_path / "sites"),
        client_factory=lambda region: FakeSesClient(
            dkim={
                "example.com": {
                    "DkimEnabled": True,
                    "DkimVerificationStatus": "Pending",
                    "DkimTokens": ["dkim1"],
                }
            },
            mail_from={
                "example.com": {
                    "MailFromDomain": "mail.example.com",
                    "MailFromDomainStatus": "Pending",
                }
            },
        ),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    data = result.observations[0].data

    assert result.status == "degraded"
    assert "example.com: DKIM verification is Pending" in result.issues
    assert "example.com: custom MAIL FROM verification is Pending" in result.issues
    assert data["domain_results"][0]["mail_from_domain"] == "mail.example.com"
    assert any(record["purpose"] == "ses_mail_from_spf" for record in data["required_dns_records"])


def test_ses_observer_cloudflare_dns_comparison_reports_missing(tmp_path: Path) -> None:
    result = ses_provider.observe_ses_provider(
        HomesrvctlConfig(
            sites_root=tmp_path / "sites",
            cloudflare_api_token="cf-token",
        ),
        client_factory=lambda region: FakeSesClient(),
        cloudflare_client_factory=lambda token: FakeCloudflareClient(
            {
                "_amazonses.example.com": [
                    {"type": "TXT", "name": "_amazonses.example.com", "content": "verification-token"}
                ],
            }
        ),
        env={"AWS_REGION": "us-east-1", ses_provider.SES_DOMAIN_ENV: "example.com"},
    )

    data = result.observations[0].data

    assert result.status == "degraded"
    assert data["dns_check_provider"] == "cloudflare"
    assert data["dns_records_checked"] > 0
    assert any(item["status"] == "missing" for item in data["dns_results"])


def test_observe_run_ses_json_persists_fake_result(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    db_path = tmp_path / "state.db"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    now = "2026-05-17T00:00:00Z"

    def fake_ses(config: HomesrvctlConfig) -> ObserverResult:
        return ObserverResult(
            observer_name="ses_provider",
            ok=True,
            started_at=now,
            finished_at=now,
            target_type="provider",
            target="ses",
            status="ready",
            summary="SES ready",
            observations=[
                ObservationRecord(
                    source="ses_provider",
                    target_type="provider",
                    target="ses",
                    status="ready",
                    detail="SES ready",
                    data={"status": "ready", "aws_region": "us-east-1"},
                )
            ],
        )

    monkeypatch.setattr(observer_runner, "observe_ses_provider", fake_ses)

    result = CliRunner().invoke(
        app,
        [
            "observe",
            "run",
            "--no-stack-runtime",
            "--no-cloudflared",
            "--no-traefik",
            "--ses",
            "--db-path",
            str(db_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["observers"][0]["observer_name"] == "ses_provider"
    assert StateStore(db_path).latest_event(source="ses_provider") is not None


def test_observe_status_includes_ses_observation(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize(utc_now_iso())
    store.add_event(
        created_at="2026-05-17T00:00:00Z",
        severity="info",
        source="ses_provider",
        target_type="provider",
        target="ses",
        message="SES ready",
        data={"status": "ready"},
    )

    result = CliRunner().invoke(app, ["observe", "status", "--db-path", str(db_path), "--json"])

    payload = json.loads(result.output)
    assert payload["ses"]["data"]["status"] == "ready"
    assert payload["provider_observers"]["ses"]["data"]["status"] == "ready"


def test_observe_run_default_does_not_run_ses(monkeypatch, tmp_path: Path) -> None:
    def fail_ses(config: HomesrvctlConfig) -> ObserverResult:
        raise AssertionError("SES observer should be opt-in")

    monkeypatch.setattr(observer_runner, "observe_ses_provider", fail_ses)
    result = observer_runner.run_observers(
        db_path=tmp_path / "state.db",
        config=HomesrvctlConfig(sites_root=tmp_path / "missing"),
        stack_runtime=False,
        cloudflared=False,
        traefik=False,
    )

    assert result.ok is True
    assert result.results == []
