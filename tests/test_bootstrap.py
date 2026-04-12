from __future__ import annotations

from pathlib import Path
import json
import pytest
import typer

from homesrvctl import bootstrap
from homesrvctl.models import HomesrvctlConfig


def test_assess_bootstrap_classifies_fresh_host(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    monkeypatch.setattr(
        bootstrap,
        "_os_assessment",
        lambda: {
            "id": "debian",
            "version_id": "12",
            "pretty_name": "Debian GNU/Linux 12",
            "supported": True,
            "detail": "Debian-family host detected",
        },
    )
    monkeypatch.setattr(bootstrap, "_systemd_assessment", lambda: {"present": True, "detail": "systemd detected"})
    monkeypatch.setattr(
        bootstrap,
        "_config_assessment",
        lambda path: (
            {
                "path": str(path),
                "exists": False,
                "valid": False,
                "detail": f"config file not found: {path}",
                "docker_network": "web",
                "cloudflared_config": "/srv/homesrvctl/cloudflared/config.yml",
                "token_present": False,
                "token_source": "missing",
            },
            HomesrvctlConfig(),
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "_packages_assessment",
        lambda quiet=False: {
            "docker": False,
            "docker_detail": "missing from PATH",
            "docker_compose": False,
            "docker_compose_detail": "docker binary missing",
            "cloudflared": False,
            "cloudflared_detail": "missing from PATH",
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_services_assessment",
        lambda packages_info, quiet=False: {
            "traefik_running": False,
            "traefik_detail": "docker binary missing",
            "cloudflared_active": False,
            "cloudflared_mode": "absent",
            "cloudflared_detail": "cloudflared not detected",
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_network_assessment",
        lambda docker_network, packages_info, quiet=False: {
            "name": docker_network,
            "exists": None,
            "detail": "docker binary missing",
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_cloudflare_assessment",
        lambda api_token, token_source: {
            "token_present": False,
            "token_source": token_source,
            "api_reachable": None,
            "detail": "Cloudflare API token is not configured",
        },
    )

    assessment = bootstrap.assess_bootstrap(config_path)

    assert assessment.ok is True
    assert assessment.bootstrap_state == "fresh"
    assert assessment.bootstrap_ready is False
    assert "docker binary is missing" in assessment.issues
    assert assessment.next_steps[-1] == (
        "`homesrvctl bootstrap apply` is not shipped yet; use this assessment to prepare the host manually."
    )


def test_assess_bootstrap_classifies_ready_host(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    monkeypatch.setattr(
        bootstrap,
        "_os_assessment",
        lambda: {
            "id": "debian",
            "version_id": "12",
            "pretty_name": "Debian GNU/Linux 12",
            "supported": True,
            "detail": "Debian-family host detected",
        },
    )
    monkeypatch.setattr(bootstrap, "_systemd_assessment", lambda: {"present": True, "detail": "systemd detected"})
    monkeypatch.setattr(
        bootstrap,
        "_config_assessment",
        lambda path: (
            {
                "path": str(path),
                "exists": True,
                "valid": True,
                "detail": "config file loaded successfully",
                "docker_network": "web",
                "cloudflared_config": "/srv/homesrvctl/cloudflared/config.yml",
                "token_present": True,
                "token_source": "file",
            },
            HomesrvctlConfig(cloudflare_api_token="token"),
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "_packages_assessment",
        lambda quiet=False: {
            "docker": True,
            "docker_detail": "found in PATH",
            "docker_compose": True,
            "docker_compose_detail": "Docker Compose version v2",
            "cloudflared": True,
            "cloudflared_detail": "found in PATH",
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_services_assessment",
        lambda packages_info, quiet=False: {
            "traefik_running": True,
            "traefik_detail": "traefik",
            "cloudflared_active": True,
            "cloudflared_mode": "systemd",
            "cloudflared_detail": "systemd service is active",
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_network_assessment",
        lambda docker_network, packages_info, quiet=False: {
            "name": docker_network,
            "exists": True,
            "detail": '"web"',
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_cloudflare_assessment",
        lambda api_token, token_source: {
            "token_present": True,
            "token_source": token_source,
            "api_reachable": True,
            "detail": "Cloudflare token verified (active)",
        },
    )

    assessment = bootstrap.assess_bootstrap(config_path)

    assert assessment.ok is True
    assert assessment.bootstrap_state == "ready"
    assert assessment.bootstrap_ready is True
    assert assessment.issues == []


def test_provision_bootstrap_tunnel_creates_local_material(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    cloudflared_config = tmp_path / "cloudflared" / "config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "tunnel_name: homesrvctl-tunnel",
                f"sites_root: {tmp_path / 'sites'}",
                "docker_network: web",
                "traefik_url: http://localhost:8081",
                f"cloudflared_config: {cloudflared_config}",
                "cloudflare_api_token: token",
                "",
            ]
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "token"

        def get_tunnel(self, account_id: str, tunnel_ref: str):  # noqa: ANN202
            raise bootstrap.CloudflareApiError(f"Cloudflare tunnel not found in account for {tunnel_ref}")

        def create_tunnel(self, account_id: str, tunnel_name: str, *, config_src: str = "local", tunnel_secret: str | None = None):  # noqa: ANN202,E501
            assert account_id == "account-123"
            assert tunnel_name == "homesrvctl-tunnel"
            assert config_src == "local"
            assert tunnel_secret == "fixed-secret"
            return type(
                "Provision",
                (),
                {
                    "id": "11111111-2222-4333-8444-555555555555",
                    "name": "homesrvctl-tunnel",
                    "account_tag": account_id,
                    "config_src": "local",
                    "status": "inactive",
                    "credentials_file": {
                        "AccountTag": account_id,
                        "TunnelID": "11111111-2222-4333-8444-555555555555",
                        "TunnelName": "homesrvctl-tunnel",
                        "TunnelSecret": tunnel_secret,
                    },
                },
            )()

    monkeypatch.setattr(bootstrap, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(bootstrap, "generate_local_tunnel_secret", lambda: "fixed-secret")

    provisioned = bootstrap.provision_bootstrap_tunnel(config_path, account_id="account-123")

    assert provisioned.created is True
    assert provisioned.reused is False
    assert provisioned.tunnel_id == "11111111-2222-4333-8444-555555555555"
    credentials_path = Path(provisioned.credentials_path)
    assert credentials_path.exists()
    assert json.loads(credentials_path.read_text(encoding="utf-8"))["TunnelSecret"] == "fixed-secret"
    assert cloudflared_config.exists()
    assert "http_status:404" in cloudflared_config.read_text(encoding="utf-8")
    assert "11111111-2222-4333-8444-555555555555" in config_path.read_text(encoding="utf-8")


def test_provision_bootstrap_tunnel_reuses_existing_local_credentials(monkeypatch, tmp_path: Path) -> None:
    credentials_path = tmp_path / "cloudflared" / "11111111-2222-4333-8444-555555555555.json"
    credentials_path.parent.mkdir(parents=True)
    credentials_path.write_text(
        json.dumps(
            {
                "AccountTag": "account-123",
                "TunnelID": "11111111-2222-4333-8444-555555555555",
                "TunnelName": "homesrvctl-tunnel",
                "TunnelSecret": "fixed-secret",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cloudflared_config = tmp_path / "cloudflared" / "config.yml"
    cloudflared_config.write_text(
        "\n".join(
            [
                "tunnel: 11111111-2222-4333-8444-555555555555",
                f"credentials-file: {credentials_path}",
                "ingress:",
                "  - service: http_status:404",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "tunnel_name: homesrvctl-tunnel",
                f"sites_root: {tmp_path / 'sites'}",
                "docker_network: web",
                "traefik_url: http://localhost:8081",
                f"cloudflared_config: {cloudflared_config}",
                "cloudflare_api_token: token",
                "",
            ]
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "token"

        def get_tunnel(self, account_id: str, tunnel_ref: str):  # noqa: ANN202
            return type(
                "Tunnel",
                (),
                {
                    "id": "11111111-2222-4333-8444-555555555555",
                    "name": "homesrvctl-tunnel",
                    "status": "healthy",
                },
            )()

    monkeypatch.setattr(bootstrap, "CloudflareApiClient", FakeClient)

    provisioned = bootstrap.provision_bootstrap_tunnel(config_path, account_id="account-123")

    assert provisioned.created is False
    assert provisioned.reused is True
    assert provisioned.credentials_written is False
    assert provisioned.credentials_path == str(credentials_path)


def test_provision_bootstrap_runtime_converges_runtime_baseline(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    monkeypatch.setattr(
        bootstrap,
        "_os_assessment",
        lambda: {
            "id": "debian",
            "version_id": "12",
            "pretty_name": "Debian GNU/Linux 12",
            "supported": True,
            "detail": "Debian-family host detected",
        },
    )
    monkeypatch.setattr(bootstrap, "_systemd_assessment", lambda: {"present": True, "detail": "systemd detected"})
    monkeypatch.setattr(
        bootstrap,
        "_config_assessment",
        lambda path: (
            {
                "path": str(path),
                "exists": True,
                "valid": True,
                "detail": "config file loaded successfully",
                "docker_network": "web",
                "cloudflared_config": "/srv/homesrvctl/cloudflared/config.yml",
                "token_present": True,
                "token_source": "file",
            },
            HomesrvctlConfig(
                sites_root=tmp_path / "sites",
                cloudflared_config=tmp_path / "cloudflared" / "config.yml",
                cloudflare_api_token="token",
            ),
        ),
    )
    monkeypatch.setattr(bootstrap, "_resolve_operator_user", lambda explicit_user=None: "broda")
    monkeypatch.setattr(bootstrap, "_debian_codename", lambda os_info: "bookworm")
    monkeypatch.setattr(bootstrap, "_dpkg_architecture", lambda dry_run=False: "arm64")
    monkeypatch.setattr(
        bootstrap,
        "_runtime_package_commands",
        lambda codename, architecture: [["apt-get", "update"], ["apt-get", "install", "-y", "cloudflared"]],
    )
    seen_commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        bootstrap,
        "_run_runtime_command",
        lambda command, dry_run=False: seen_commands.append(tuple(command)),
    )
    monkeypatch.setattr(bootstrap, "_write_runtime_repo_files", lambda codename, architecture, dry_run=False: None)
    monkeypatch.setattr(
        bootstrap,
        "_ensure_runtime_groups",
        lambda operator_user, dry_run=False: [{"group": "homesrvctl", "created": True}],
    )
    monkeypatch.setattr(
        bootstrap,
        "_ensure_runtime_directories",
        lambda config, dry_run=False: [{"path": "/srv/homesrvctl/sites", "mode": "0o2775", "existed": False}],
    )
    monkeypatch.setattr(
        bootstrap,
        "_ensure_runtime_docker_network",
        lambda docker_network, dry_run=False: {"name": docker_network, "created": True, "detail": "created"},
    )
    monkeypatch.setattr(
        bootstrap,
        "_ensure_runtime_traefik",
        lambda docker_network, force=False, dry_run=False: {
            "compose_path": "/srv/homesrvctl/traefik/docker-compose.yml",
            "written": True,
            "started": True,
        },
    )
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)

    provisioned = bootstrap.provision_bootstrap_runtime(config_path, dry_run=False)

    assert provisioned.ok is True
    assert provisioned.operator_user == "broda"
    assert provisioned.network["created"] is True
    assert provisioned.traefik["started"] is True
    assert seen_commands == [
        ("apt-get", "update"),
        ("apt-get", "install", "-y", "cloudflared"),
    ]


def test_provision_bootstrap_runtime_rejects_non_root_without_dry_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        bootstrap,
        "_os_assessment",
        lambda: {"supported": True, "pretty_name": "Debian GNU/Linux 12", "detail": "Debian-family host detected"},
    )
    monkeypatch.setattr(bootstrap, "_systemd_assessment", lambda: {"present": True, "detail": "systemd detected"})
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 1000)

    with pytest.raises(typer.BadParameter, match="requires root privileges"):
        bootstrap.provision_bootstrap_runtime(tmp_path / "config.yml")
