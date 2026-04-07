from __future__ import annotations

import urllib.error
from pathlib import Path

from homectl.commands import validate_cmd
from homectl.models import HomectlConfig
from homectl.shell import CommandResult


def test_build_validate_report_uses_cloudflared_config_fallback(monkeypatch, tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:8081\n  - hostname: '*.example.com'\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomectlConfig(
        tunnel_name="homectl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_command_exists(binary: str) -> bool:
        return binary in {"cloudflared", "docker"}

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False) -> CommandResult:
        if command[:3] == ["docker", "compose", "version"]:
            return CommandResult(command, 0, "Docker Compose version v5.1.1", "")
        if command[:4] == ["cloudflared", "--config", str(cloudflared_config), "tunnel"]:
            return CommandResult(command, 1, "", "origin cert missing")
        if command[:3] == ["docker", "network", "inspect"]:
            return CommandResult(command, 0, "\"web\"", "")
        if command[:2] == ["docker", "ps"]:
            return CommandResult(command, 0, "traefik", "")
        if command[:2] == ["systemctl", "is-active"]:
            return CommandResult(command, 0, "active", "")
        if command[:2] == ["pgrep", "-fa"]:
            return CommandResult(command, 1, "", "")
        raise AssertionError(f"unexpected command: {command}")

    def fake_urlopen(request, timeout: int = 3):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url=config.traefik_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(validate_cmd, "command_exists", fake_command_exists)
    monkeypatch.setattr(validate_cmd, "run_command", fake_run_command)
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_validate_report(config)
    indexed = {check.name: check for check in checks}

    assert indexed["configured tunnel"].ok
    assert "references tunnel 1234-uuid" in indexed["configured tunnel"].detail
    assert indexed["Traefik URL"].ok
    assert indexed["cloudflared ingress config"].ok


def test_build_hostname_doctor_report(monkeypatch, tmp_path: Path) -> None:
    stack_dir = tmp_path / "sites" / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:8081\n  - hostname: '*.example.com'\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomectlConfig(
        tunnel_name="homectl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False) -> CommandResult:
        if command[:4] == ["docker", "compose", "ps", "--format"]:
            return CommandResult(command, 0, "[]", "")
        raise AssertionError(f"unexpected command: {command}")

    def fake_urlopen(request, timeout: int = 3):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url=config.traefik_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(validate_cmd, "run_command", fake_run_command)
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_hostname_doctor_report(config, "example.com")
    indexed = {check.name: check for check in checks}

    assert indexed["hostname directory"].ok
    assert indexed["docker-compose.yml"].ok
    assert indexed["docker compose ps"].ok
    assert indexed["cloudflared ingress hostname"].ok
    assert indexed["host-header request"].ok
