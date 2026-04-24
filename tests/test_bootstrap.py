from __future__ import annotations

from pathlib import Path
import json
import stat
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


def test_validate_bootstrap_reports_ready_baseline(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    assessment = bootstrap.BootstrapAssessment(
        ok=True,
        bootstrap_state="ready",
        bootstrap_ready=True,
        host_supported=True,
        detail="host matches the current shipped bootstrap baseline",
        config_path=str(config_path),
        os={"supported": True},
        systemd={"present": True},
        packages={"docker": True, "docker_compose": True, "cloudflared": True},
        services={"traefik_running": True, "cloudflared_active": True},
        config={"path": str(config_path), "exists": True, "valid": True, "detail": "ok"},
        network={"name": "web", "exists": True, "detail": '"web"'},
        cloudflare={"token_present": True, "api_reachable": True, "detail": "Cloudflare token verified (active)"},
        issues=[],
        next_steps=["Host baseline is ready for stack operations and domain onboarding."],
    )
    monkeypatch.setattr(bootstrap, "assess_bootstrap", lambda path=None, quiet=False: assessment)
    monkeypatch.setattr(
        bootstrap,
        "_config_assessment",
        lambda path: (
            {"path": str(path), "exists": True, "valid": True, "detail": "config file loaded successfully"},
            HomesrvctlConfig(
                tunnel_name="11111111-2222-4333-8444-555555555555",
                cloudflared_config=tmp_path / "cloudflared" / "config.yml",
                cloudflare_api_token="token",
            ),
        ),
    )

    class FakeTunnelStatus:
        configured_tunnel = "11111111-2222-4333-8444-555555555555"
        resolved_tunnel_id = "11111111-2222-4333-8444-555555555555"
        resolution_source = "local_credentials"
        account_id = "account-123"
        api_available = True
        api_status = type("ApiStatus", (), {"id": "11111111-2222-4333-8444-555555555555", "name": "home", "status": "healthy"})()
        api_error = None
        resolution_error = None

    monkeypatch.setattr(bootstrap, "inspect_configured_tunnel", lambda config: FakeTunnelStatus())
    monkeypatch.setattr(
        bootstrap,
        "detect_cloudflared_runtime",
        lambda quiet=False: type("Runtime", (), {"mode": "systemd", "active": True, "detail": "systemd service is active"})(),
    )
    monkeypatch.setattr(
        bootstrap,
        "inspect_cloudflared_setup",
        lambda config_path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": True,
                "setup_state": "ready",
                "mode": "systemd",
                "systemd_managed": True,
                "active": True,
                "configured_path": str(config_path),
                "configured_exists": True,
                "configured_writable": True,
                "configured_credentials_path": str(tmp_path / "cloudflared" / "tunnel.json"),
                "configured_credentials_exists": True,
                "configured_credentials_readable": True,
                "configured_credentials_group_readable": True,
                "configured_credentials_owner": "root",
                "configured_credentials_group": "homesrvctl",
                "configured_credentials_mode": "0o640",
                "runtime_path": str(config_path),
                "runtime_exists": True,
                "runtime_readable": True,
                "paths_aligned": True,
                "ingress_mutation_available": True,
                "account_inspection_available": True,
                "service_user": "root",
                "service_group": "homesrvctl",
                "shared_group": "homesrvctl",
                "detail": "shared-group cloudflared setup is ready",
                "issues": [],
                "notes": [],
                "next_commands": [],
                "override_path": None,
                "override_content": None,
            },
        )(),
    )

    from homesrvctl.commands import validate_cmd

    monkeypatch.setattr(
        validate_cmd,
        "build_validate_report",
        lambda config, quiet=False: [
            validate_cmd.CheckResult("cloudflared binary", True, "found in PATH"),
            validate_cmd.CheckResult("docker binary", True, "found in PATH"),
        ],
    )

    validation = bootstrap.validate_bootstrap(config_path)

    assert validation.ok is True
    assert validation.validation_state == "ready"
    assert validation.bootstrap_ready is True
    assert validation.validate_blocking_failures == 0
    assert validation.tunnel["ok"] is True
    assert validation.cloudflared_setup["setup_state"] == "ready"


def test_validate_bootstrap_reports_missing_tunnel_and_partial_setup(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    assessment = bootstrap.BootstrapAssessment(
        ok=True,
        bootstrap_state="partial",
        bootstrap_ready=False,
        host_supported=True,
        detail="host is partially provisioned relative to the current bootstrap target",
        config_path=str(config_path),
        os={"supported": True},
        systemd={"present": True},
        packages={"docker": True, "docker_compose": True, "cloudflared": True},
        services={"traefik_running": True, "cloudflared_active": True},
        config={"path": str(config_path), "exists": True, "valid": True, "detail": "ok"},
        network={"name": "web", "exists": True, "detail": '"web"'},
        cloudflare={"token_present": True, "api_reachable": True, "detail": "Cloudflare token verified (active)"},
        issues=["cloudflared is not active"],
        next_steps=["Install or start the cloudflared service for the shared host tunnel."],
    )
    monkeypatch.setattr(bootstrap, "assess_bootstrap", lambda path=None, quiet=False: assessment)
    monkeypatch.setattr(
        bootstrap,
        "_config_assessment",
        lambda path: (
            {"path": str(path), "exists": True, "valid": True, "detail": "config file loaded successfully"},
            HomesrvctlConfig(
                tunnel_name="homesrvctl-tunnel",
                cloudflared_config=tmp_path / "cloudflared" / "config.yml",
                cloudflare_api_token="token",
            ),
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "detect_cloudflared_runtime",
        lambda quiet=False: type("Runtime", (), {"mode": "systemd", "active": True, "detail": "systemd service is active"})(),
    )

    def fail_tunnel(config):  # noqa: ANN001,ANN202
        raise bootstrap.CloudflareApiError("configured tunnel could not be resolved")

    monkeypatch.setattr(bootstrap, "inspect_configured_tunnel", fail_tunnel)
    monkeypatch.setattr(
        bootstrap,
        "inspect_cloudflared_setup",
        lambda config_path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": True,
                "setup_state": "partial",
                "mode": "systemd",
                "systemd_managed": True,
                "active": True,
                "configured_path": str(config_path),
                "configured_exists": True,
                "configured_writable": True,
                "configured_credentials_path": str(tmp_path / "cloudflared" / "tunnel.json"),
                "configured_credentials_exists": True,
                "configured_credentials_readable": False,
                "configured_credentials_group_readable": False,
                "configured_credentials_owner": "root",
                "configured_credentials_group": "root",
                "configured_credentials_mode": "0o600",
                "runtime_path": str(config_path),
                "runtime_exists": True,
                "runtime_readable": True,
                "paths_aligned": True,
                "ingress_mutation_available": True,
                "account_inspection_available": False,
                "service_user": "root",
                "service_group": "homesrvctl",
                "shared_group": "homesrvctl",
                "detail": "ingress mutations are ready, but account inspection is unavailable from the current user",
                "issues": [],
                "notes": ["account inspection unavailable: cloudflared credentials are not readable by the current user"],
                "next_commands": ["homesrvctl cloudflared setup"],
                "override_path": None,
                "override_content": None,
            },
        )(),
    )

    from homesrvctl.commands import validate_cmd

    monkeypatch.setattr(
        validate_cmd,
        "build_validate_report",
        lambda config, quiet=False: [
            validate_cmd.CheckResult("cloudflared binary", True, "found in PATH"),
            validate_cmd.CheckResult("Traefik URL", False, "http://localhost:8081 unreachable: connection refused"),
        ],
    )

    validation = bootstrap.validate_bootstrap(config_path)

    assert validation.ok is False
    assert validation.validation_state == "not_ready"
    assert validation.bootstrap_ready is False
    assert validation.validate_blocking_failures == 1
    assert validation.tunnel["ok"] is False
    assert validation.cloudflared_setup["setup_state"] == "partial"
    assert any("validate blocking failure: Traefik URL" in issue for issue in validation.issues)
    assert any("tunnel status: configured tunnel could not be resolved" in issue for issue in validation.issues)


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
    monkeypatch.setattr(bootstrap, "_apt_codename", lambda os_info: "bookworm")
    monkeypatch.setattr(bootstrap, "_docker_repo_family", lambda os_info: "debian")
    monkeypatch.setattr(bootstrap, "_dpkg_architecture", lambda dry_run=False: "arm64")
    monkeypatch.setattr(bootstrap, "_remove_stale_docker_repo_file", lambda dry_run=False: False)
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
    monkeypatch.setattr(
        bootstrap,
        "_write_runtime_repo_files",
        lambda codename, architecture, docker_repo_family, dry_run=False: None,
    )
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


def test_write_runtime_repo_files_uses_ubuntu_docker_repo_for_noble(monkeypatch) -> None:
    written: dict[Path, bytes] = {}

    monkeypatch.setattr(bootstrap, "_fetch_url_bytes", lambda url, dry_run=False: f"key:{url}".encode("utf-8"))
    monkeypatch.setattr(
        bootstrap,
        "_ensure_file_content",
        lambda path, content, dry_run=False: written.__setitem__(path, content) or True,
    )

    bootstrap._write_runtime_repo_files(
        codename="noble",
        architecture="arm64",
        docker_repo_family="ubuntu",
        dry_run=False,
    )

    assert written[bootstrap.DOCKER_APT_KEYRING_PATH] == b"key:https://download.docker.com/linux/ubuntu/gpg"
    assert (
        written[bootstrap.DOCKER_APT_SOURCE_PATH].decode("utf-8")
        == "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\n"
    )


def test_docker_repo_family_selects_ubuntu_for_ubuntu_like_hosts() -> None:
    assert bootstrap._docker_repo_family({"id": "ubuntu", "id_like": ["debian"]}) == "ubuntu"
    assert bootstrap._docker_repo_family({"id": "linuxmint", "id_like": ["ubuntu", "debian"]}) == "ubuntu"
    assert bootstrap._docker_repo_family({"id": "raspbian", "id_like": ["debian"]}) == "debian"


def test_remove_stale_docker_repo_file_before_first_apt_update(monkeypatch, tmp_path: Path) -> None:
    stale_source = tmp_path / "docker.list"
    stale_source.write_text(
        "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian noble stable\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bootstrap, "DOCKER_APT_SOURCE_PATH", stale_source)

    removed = bootstrap._remove_stale_docker_repo_file(dry_run=False)

    assert removed is True
    assert not stale_source.exists()


def test_provision_bootstrap_wiring_converges_shared_config_and_service(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    source_cloudflared = tmp_path / "legacy" / "config.yml"
    source_credentials = tmp_path / "legacy" / "legacy.json"
    source_cloudflared.parent.mkdir(parents=True)
    source_credentials.write_text('{"AccountTag":"account-123","TunnelID":"11111111-2222-4333-8444-555555555555"}\n', encoding="utf-8")
    source_cloudflared.write_text(
        "\n".join(
            [
                "tunnel: 11111111-2222-4333-8444-555555555555",
                f"credentials-file: {source_credentials}",
                "ingress:",
                "  - service: http_status:404",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "tunnel_name: 11111111-2222-4333-8444-555555555555",
                f"sites_root: {tmp_path / 'sites'}",
                "docker_network: web",
                "traefik_url: http://localhost:8081",
                f"cloudflared_config: {source_cloudflared}",
                "cloudflare_api_token: token",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "SHARED_CONFIG_PATH", tmp_path / "shared" / "config.yml")
    monkeypatch.setattr(bootstrap, "SYSTEMD_OVERRIDE_PATH", str(tmp_path / "override.conf"))
    monkeypatch.setattr(bootstrap, "SYSTEMD_UNIT_PATH", str(tmp_path / "cloudflared.service"))
    monkeypatch.setattr(bootstrap, "SUDOERS_PATH", str(tmp_path / "sudoers.d" / "homesrvctl-cloudflared"))
    monkeypatch.setattr(
        bootstrap,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: type("Unit", (), {"present": False})(),
    )
    monkeypatch.setattr(bootstrap, "_ensure_shared_cloudflared_permissions", lambda config_path, credentials_path, dry_run=False: None)
    seen_commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        bootstrap,
        "_run_runtime_command",
        lambda command, dry_run=False: seen_commands.append(tuple(command)),
    )

    provisioned = bootstrap.provision_bootstrap_wiring(config_path)

    assert provisioned.ok is True
    assert provisioned.systemd_mode == "unit"
    assert provisioned.systemd_written is True
    assert Path(provisioned.cloudflared_config_path).exists()
    assert Path(provisioned.credentials_path).exists()
    assert any(command[:3] == ("systemctl", "enable", "--now") for command in seen_commands)


def test_provision_bootstrap_wiring_accepts_equivalent_existing_shared_config(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    shared_config = tmp_path / "shared" / "config.yml"
    shared_credentials = tmp_path / "shared" / "tunnel.json"
    shared_config.parent.mkdir(parents=True)
    shared_credentials.write_text('{"AccountTag":"account-123","TunnelID":"11111111-2222-4333-8444-555555555555"}\n', encoding="utf-8")
    shared_config.write_text(
        "\n".join(
            [
                "tunnel: 11111111-2222-4333-8444-555555555555",
                f"credentials-file: {shared_credentials}",
                "ingress:",
                "- service: http_status:404",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "tunnel_name: 11111111-2222-4333-8444-555555555555",
                f"sites_root: {tmp_path / 'sites'}",
                "docker_network: web",
                "traefik_url: http://localhost:8081",
                f"cloudflared_config: {shared_config}",
                "cloudflare_api_token: token",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "SHARED_CONFIG_PATH", shared_config)
    monkeypatch.setattr(bootstrap, "SYSTEMD_UNIT_PATH", str(tmp_path / "cloudflared.service"))
    monkeypatch.setattr(bootstrap, "SUDOERS_PATH", str(tmp_path / "sudoers.d" / "homesrvctl-cloudflared"))
    monkeypatch.setattr(
        bootstrap,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: type("Unit", (), {"present": False})(),
    )
    monkeypatch.setattr(bootstrap, "_ensure_shared_cloudflared_permissions", lambda config_path, credentials_path, dry_run=False: None)
    monkeypatch.setattr(bootstrap, "_run_runtime_command", lambda command, dry_run=False: None)

    provisioned = bootstrap.provision_bootstrap_wiring(config_path)

    assert provisioned.ok is True
    assert provisioned.cloudflared_config_written is False


def test_provision_bootstrap_wiring_rejects_missing_credentials(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "tunnel_name: homesrvctl-tunnel",
                f"sites_root: {tmp_path / 'sites'}",
                "docker_network: web",
                "traefik_url: http://localhost:8081",
                f"cloudflared_config: {tmp_path / 'missing.yml'}",
                "cloudflare_api_token: token",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "SHARED_CONFIG_PATH", tmp_path / "shared" / "config.yml")

    with pytest.raises(typer.BadParameter, match="could not find cloudflared tunnel credentials"):
        bootstrap.provision_bootstrap_wiring(config_path)


def test_ensure_shared_cloudflared_permissions_makes_config_group_writable(monkeypatch, tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    config_path = shared_dir / "config.yml"
    credentials_path = shared_dir / "tunnel.json"
    shared_dir.mkdir(parents=True)
    config_path.write_text("tunnel: test\n", encoding="utf-8")
    credentials_path.write_text('{"TunnelID":"11111111-2222-4333-8444-555555555555"}\n', encoding="utf-8")

    monkeypatch.setattr(bootstrap, "HOMESRVCTL_GROUP", grp_name := "homesrvctl")
    monkeypatch.setattr(
        bootstrap.grp,
        "getgrnam",
        lambda name: type("Group", (), {"gr_gid": 1005})() if name == grp_name else (_ for _ in ()).throw(KeyError(name)),
    )
    monkeypatch.setattr(bootstrap.os, "chown", lambda path, uid, gid: None)

    bootstrap._ensure_shared_cloudflared_permissions(config_path, credentials_path, dry_run=False)

    assert stat.S_IMODE(shared_dir.stat().st_mode) == 0o2770
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o660
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o640
