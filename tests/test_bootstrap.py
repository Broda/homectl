from __future__ import annotations

from pathlib import Path

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
