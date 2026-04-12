from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from homesrvctl.cloudflare import (
    CloudflareApiClient,
    CloudflareApiError,
    account_id_from_cloudflared_config,
    account_id_from_zone,
    inspect_configured_tunnel,
    tunnel_cname_target,
    tunnel_cname_target_for_account,
)
from homesrvctl.models import HomesrvctlConfig


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def test_apply_dns_record_updates_existing_record(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        seen.append((method, path, body))
        if method == "GET":
            return {
                "success": True,
                "result": [{"id": "record-123", "name": "example.com", "type": "A", "content": "1.2.3.4", "proxied": True}],
            }
        return {"success": True, "result": {"id": "record-123"}}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.apply_dns_record("zone-123", "example.com", "uuid.cfargotunnel.com")

    assert result.action == "update"
    assert seen[1][0] == "PUT"
    assert seen[1][1] == "/zones/zone-123/dns_records/record-123"
    assert seen[1][2] == {
        "type": "CNAME",
        "name": "example.com",
        "content": "uuid.cfargotunnel.com",
        "proxied": True,
        "ttl": 1,
    }


def test_apply_dns_record_noops_when_expected_cname_coexists_with_mail_records(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        seen.append((method, path, body))
        return {
            "success": True,
            "result": [
                {"id": "record-123", "name": "example.com", "type": "CNAME", "content": "uuid.cfargotunnel.com", "proxied": True},
                {"id": "record-234", "name": "example.com", "type": "MX", "content": "route1.mx.cloudflare.net", "proxied": False},
                {"id": "record-345", "name": "example.com", "type": "TXT", "content": "\"v=spf1 include:_spf.mx.cloudflare.net ~all\"", "proxied": False},
            ],
        }

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.apply_dns_record("zone-123", "example.com", "uuid.cfargotunnel.com")

    assert result.action == "noop"
    assert seen == [("GET", "/zones/zone-123/dns_records?name=example.com", None)]


def test_apply_dns_record_removal_deletes_existing_record(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        seen.append((method, path, body))
        if method == "GET":
            return {
                "success": True,
                "result": [
                    {
                        "id": "record-123",
                        "name": "example.com",
                        "type": "CNAME",
                        "content": "uuid.cfargotunnel.com",
                        "proxied": True,
                    }
                ],
            }
        return {"success": True, "result": {"id": "record-123"}}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.apply_dns_record_removal("zone-123", "example.com")

    assert result.action == "delete"
    assert seen[1][0] == "DELETE"
    assert seen[1][1] == "/zones/zone-123/dns_records/record-123"


def test_apply_dns_record_removal_keeps_mail_records_and_deletes_matching_cname(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request_json(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        seen.append((method, path, body))
        if method == "GET":
            return {
                "success": True,
                "result": [
                    {"id": "record-123", "name": "example.com", "type": "CNAME", "content": "uuid.cfargotunnel.com", "proxied": True},
                    {"id": "record-234", "name": "example.com", "type": "MX", "content": "route1.mx.cloudflare.net", "proxied": False},
                ],
            }
        return {"success": True, "result": {"id": "record-123"}}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.apply_dns_record_removal("zone-123", "example.com")

    assert result.action == "delete"
    assert seen[1] == ("DELETE", "/zones/zone-123/dns_records/record-123", None)


def test_get_dns_record_status_allows_expected_cname_with_mail_records(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda method, path, body=None: {
            "success": True,
            "result": [
                {"id": "record-123", "name": "example.com", "type": "CNAME", "content": "uuid.cfargotunnel.com", "proxied": True},
                {"id": "record-234", "name": "example.com", "type": "MX", "content": "route1.mx.cloudflare.net", "proxied": False},
                {"id": "record-345", "name": "example.com", "type": "TXT", "content": "\"v=spf1 include:_spf.mx.cloudflare.net ~all\"", "proxied": False},
            ],
        },
    )

    status = client.get_dns_record_status("zone-123", "example.com", "uuid.cfargotunnel.com")

    assert status.matches_expected is True
    assert status.multiple_records is False
    assert "ancillary records present" in status.detail


def test_plan_dns_record_removal_noop(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")

    monkeypatch.setattr(client, "_request_json", lambda method, path, body=None: {"success": True, "result": []})

    result = client.plan_dns_record_removal("zone-123", "example.com")

    assert result.action == "noop"


def test_plan_dns_record_noop(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda method, path, body=None: {
            "success": True,
            "result": [{"id": "record-123", "name": "*.example.com", "type": "CNAME", "content": "uuid.cfargotunnel.com", "proxied": True}],
        },
    )

    result = client.plan_dns_record("zone-123", "*.example.com", "uuid.cfargotunnel.com")

    assert result.action == "noop"


def test_get_zone_raises_for_missing_zone(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")
    monkeypatch.setattr(client, "_request_json", lambda method, path, body=None: {"success": True, "result": []})

    with pytest.raises(CloudflareApiError):
        client.get_zone("missing.example.com")


def test_tunnel_cname_target_uses_cloudflared_config_uuid(tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text("tunnel: 11111111-2222-4333-8444-555555555555\n", encoding="utf-8")
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
        cloudflare_api_token="token",
    )

    assert tunnel_cname_target(config) == "11111111-2222-4333-8444-555555555555.cfargotunnel.com"


def test_tunnel_cname_target_errors_without_local_uuid(tmp_path: Path) -> None:
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=tmp_path / "missing.yml",
        cloudflare_api_token="token",
    )

    with pytest.raises(typer.BadParameter, match="could not resolve local tunnel ID for homesrvctl-tunnel"):
        tunnel_cname_target(config)


def test_account_id_from_zone_returns_nested_account_id() -> None:
    zone = {"id": "zone-123", "account": {"id": "account-456"}}

    assert account_id_from_zone(zone) == "account-456"


def test_account_id_from_zone_errors_when_missing() -> None:
    with pytest.raises(CloudflareApiError):
        account_id_from_zone({"id": "zone-123"})


def test_account_id_from_cloudflared_config_uses_credentials_file(tmp_path: Path) -> None:
    credentials_path = tmp_path / "example.json"
    credentials_path.write_text('{"AccountTag":"account-456"}', encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        f"tunnel: homesrvctl-tunnel\ncredentials-file: {credentials_path}\n",
        encoding="utf-8",
    )

    assert account_id_from_cloudflared_config(cloudflared_config) == "account-456"


def test_get_tunnel_looks_up_by_name(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")

    def fake_request_json(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        assert method == "GET"
        assert body is None
        assert path == "/accounts/account-123/cfd_tunnel?name=homesrvctl-tunnel"
        return {
            "success": True,
            "result": [
                {"id": "11111111-2222-4333-8444-555555555555", "name": "homesrvctl-tunnel", "status": "healthy"},
            ],
        }

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    tunnel = client.get_tunnel("account-123", "homesrvctl-tunnel")

    assert tunnel.id == "11111111-2222-4333-8444-555555555555"
    assert tunnel.name == "homesrvctl-tunnel"
    assert tunnel.status == "healthy"


def test_get_tunnel_errors_when_multiple_names_match(monkeypatch) -> None:
    client = CloudflareApiClient("test-token")

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda method, path, body=None: {
            "success": True,
            "result": [
                {"id": "11111111-2222-4333-8444-555555555555", "name": "homesrvctl-tunnel", "status": "healthy"},
                {"id": "66666666-7777-4888-9999-000000000000", "name": "homesrvctl-tunnel", "status": "down"},
            ],
        },
    )

    with pytest.raises(CloudflareApiError, match="multiple Cloudflare tunnels matched homesrvctl-tunnel"):
        client.get_tunnel("account-123", "homesrvctl-tunnel")


def test_tunnel_cname_target_for_account_uses_api_lookup(monkeypatch, tmp_path: Path) -> None:
    client = CloudflareApiClient("test-token")
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=tmp_path / "missing.yml",
        cloudflare_api_token="token",
    )

    monkeypatch.setattr(
        client,
        "get_tunnel",
        lambda account_id, tunnel_ref: type(
            "Tunnel",
            (),
            {"id": "11111111-2222-4333-8444-555555555555", "name": tunnel_ref, "status": "healthy"},
        )(),
    )

    target = tunnel_cname_target_for_account(config, account_id="account-123", api_client=client)

    assert target == "11111111-2222-4333-8444-555555555555.cfargotunnel.com"


def test_tunnel_cname_target_for_account_surfaces_lookup_error(tmp_path: Path) -> None:
    client = CloudflareApiClient("test-token")
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=tmp_path / "missing.yml",
        cloudflare_api_token="token",
    )

    with pytest.raises(typer.BadParameter, match="could not resolve tunnel ID for homesrvctl-tunnel"):
        tunnel_cname_target_for_account(config, account_id="account-123", api_client=client)


def test_inspect_configured_tunnel_uses_local_uuid_without_api(tmp_path: Path) -> None:
    config = HomesrvctlConfig(
        tunnel_name="11111111-2222-4333-8444-555555555555",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=tmp_path / "missing.yml",
    )

    inspection = inspect_configured_tunnel(config)

    assert inspection.resolved_tunnel_id == "11111111-2222-4333-8444-555555555555"
    assert inspection.resolution_source == "config:tunnel_name"
    assert inspection.api_status is None


def test_inspect_configured_tunnel_uses_credentials_api_lookup(monkeypatch, tmp_path: Path) -> None:
    credentials_path = tmp_path / "example.json"
    credentials_path.write_text('{"AccountTag":"account-456"}', encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        f"tunnel: homesrvctl-tunnel\ncredentials-file: {credentials_path}\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
        cloudflare_api_token="token",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "token"

        def get_tunnel(self, account_id: str, tunnel_ref: str):  # noqa: ANN202
            assert account_id == "account-456"
            assert tunnel_ref == "homesrvctl-tunnel"
            return type(
                "Tunnel",
                (),
                {"id": "11111111-2222-4333-8444-555555555555", "name": tunnel_ref, "status": "healthy"},
            )()

    monkeypatch.setattr("homesrvctl.cloudflare.CloudflareApiClient", FakeClient)

    inspection = inspect_configured_tunnel(config)

    assert inspection.resolved_tunnel_id == "11111111-2222-4333-8444-555555555555"
    assert inspection.resolution_source == "credentials+api"
    assert inspection.api_status is not None
    assert inspection.api_status.status == "healthy"


def test_inspect_configured_tunnel_errors_without_local_uuid_or_api_context(tmp_path: Path) -> None:
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=tmp_path / "missing.yml",
    )

    inspection = inspect_configured_tunnel(config)

    assert inspection.resolved_tunnel_id is None
    assert inspection.resolution_source is None
    assert inspection.api_available is False
    assert inspection.resolution_error is not None
    assert "cloudflared config file missing" in inspection.resolution_error


def test_client_requires_api_token() -> None:
    with pytest.raises(typer.BadParameter):
        CloudflareApiClient("")
