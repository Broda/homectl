from __future__ import annotations

import urllib.error
from pathlib import Path

from homesrvctl.cloudflared_service import CloudflaredRuntime
from homesrvctl.cloudflared import CloudflaredConfigValidation, collect_cloudflared_config_warnings
from homesrvctl.commands import validate_cmd
from homesrvctl.models import HomesrvctlConfig, RoutingProfile
from homesrvctl.shell import CommandResult


def test_build_validate_report_uses_cloudflared_config_fallback(monkeypatch, tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:8081\n  - hostname: '*.example.com'\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_command_exists(binary: str) -> bool:
        return binary in {"cloudflared", "docker"}

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
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
    monkeypatch.setattr(
        validate_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_validate_report(config)
    indexed = {check.name: check for check in checks}

    assert indexed["configured tunnel"].ok
    assert "references tunnel 1234-uuid" in indexed["configured tunnel"].detail
    assert indexed["Traefik URL"].ok
    assert indexed["cloudflared service"].ok
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
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
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
    assert indexed["routing profile"].detail == "none"
    assert indexed["default ingress target"].detail == "http://localhost:8081"
    assert indexed["effective ingress target"].detail == "http://localhost:8081 (global-config)"
    assert indexed["docker compose ps"].ok
    assert indexed["cloudflared ingress hostname"].ok
    assert indexed["host-header request"].ok


def test_build_hostname_doctor_report_uses_stack_override_traefik_url(monkeypatch, tmp_path: Path) -> None:
    stack_dir = tmp_path / "sites" / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (stack_dir / "homesrvctl.yml").write_text("traefik_url: http://localhost:9000\n", encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:9000\n  - hostname: '*.example.com'\n    service: http://localhost:9000\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
        if command[:4] == ["docker", "compose", "ps", "--format"]:
            return CommandResult(command, 0, "[]", "")
        raise AssertionError(f"unexpected command: {command}")

    def fake_urlopen(request, timeout: int = 3):  # noqa: ANN001
        assert request.full_url == "http://localhost:9000"
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(validate_cmd, "run_command", fake_run_command)
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_hostname_doctor_report(config, "example.com")
    indexed = {check.name: check for check in checks}

    assert indexed["effective ingress target"].detail == "http://localhost:9000 (stack-local)"
    assert indexed["host-header request"].ok


def test_build_hostname_doctor_report_uses_profile_backed_traefik_url(monkeypatch, tmp_path: Path) -> None:
    stack_dir = tmp_path / "sites" / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (stack_dir / "homesrvctl.yml").write_text("profile: edge\n", encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:9000\n  - hostname: '*.example.com'\n    service: http://localhost:9000\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
        profiles={"edge": RoutingProfile(docker_network="edge", traefik_url="http://localhost:9000")},
    )

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
        if command[:4] == ["docker", "compose", "ps", "--format"]:
            return CommandResult(command, 0, "[]", "")
        raise AssertionError(f"unexpected command: {command}")

    def fake_urlopen(request, timeout: int = 3):  # noqa: ANN001
        assert request.full_url == "http://localhost:9000"
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(validate_cmd, "run_command", fake_run_command)
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_hostname_doctor_report(config, "example.com")
    indexed = {check.name: check for check in checks}

    assert indexed["routing profile"].detail == "edge"
    assert indexed["effective ingress target"].detail == "http://localhost:9000 (profile:edge)"
    assert indexed["host-header request"].ok


def test_build_hostname_doctor_report_includes_ingress_warnings(monkeypatch, tmp_path: Path) -> None:
    stack_dir = tmp_path / "sites" / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: '*.com'\n    service: http://localhost:9000\n  - hostname: example.com\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
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
    warning_checks = [check for check in checks if check.name == "cloudflared ingress warnings"]

    assert len(warning_checks) == 1
    assert not warning_checks[0].ok
    assert warning_checks[0].detail == (
        "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
    )


def test_build_validate_report_includes_cloudflared_hint(monkeypatch, tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - service: http_status:404\n  - hostname: example.com\n    service: http://localhost:8081\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_command_exists(binary: str) -> bool:
        return binary in {"cloudflared", "docker"}

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
        if command[:3] == ["docker", "compose", "version"]:
            return CommandResult(command, 0, "Docker Compose version v5.1.1", "")
        if command[:4] == ["cloudflared", "--config", str(cloudflared_config), "tunnel"]:
            return CommandResult(command, 1, "", "origin cert missing")
        if command[:3] == ["docker", "network", "inspect"]:
            return CommandResult(command, 0, "\"web\"", "")
        if command[:2] == ["docker", "ps"]:
            return CommandResult(command, 0, "traefik", "")
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
    monkeypatch.setattr(
        validate_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="absent",
            active=False,
            detail="cloudflared not detected via systemd, docker, or process scan",
            restart_command=None,
        ),
    )
    monkeypatch.setattr(
        validate_cmd,
        "test_cloudflared_config",
        lambda path: CloudflaredConfigValidation(
            ok=False,
            detail="cloudflared fallback service must be the last ingress entry: /tmp/test. Hint: move the hostname-less fallback service to the end of the ingress list",
            command=None,
            method="structural",
        ),
    )
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_validate_report(config)
    indexed = {check.name: check for check in checks}

    assert not indexed["cloudflared ingress config"].ok
    assert "Hint: move the hostname-less fallback service to the end of the ingress list" in indexed[
        "cloudflared ingress config"
    ].detail


def test_build_validate_report_uses_cloudflared_cli_config_test(monkeypatch, tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:8081\n  - hostname: '*.example.com'\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )

    def fake_command_exists(binary: str) -> bool:
        return binary in {"cloudflared", "docker"}

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
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
    monkeypatch.setattr(
        validate_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        validate_cmd,
        "test_cloudflared_config",
        lambda path: CloudflaredConfigValidation(
            ok=True,
            detail="Everything OK",
            command=["cloudflared", "tunnel", "--config", str(path), "ingress", "validate"],
            method="cloudflared",
        ),
    )
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_validate_report(config)
    indexed = {check.name: check for check in checks}

    assert indexed["cloudflared ingress config"].ok
    assert "cloudflared tunnel --config" in indexed["cloudflared ingress config"].detail
    assert "Everything OK" in indexed["cloudflared ingress config"].detail


def test_build_validate_report_uses_quiet_probes_when_requested(monkeypatch, tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: example.com\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )
    config = HomesrvctlConfig(
        tunnel_name="homesrvctl-tunnel",
        sites_root=tmp_path / "sites",
        docker_network="web",
        traefik_url="http://localhost:8081",
        cloudflared_config=cloudflared_config,
    )
    quiet_flags: list[bool] = []

    def fake_command_exists(binary: str) -> bool:
        return binary in {"cloudflared", "docker"}

    def fake_run_command(command: list[str], cwd: Path | None = None, dry_run: bool = False, quiet: bool = False) -> CommandResult:
        quiet_flags.append(quiet)
        if command[:3] == ["docker", "compose", "version"]:
            return CommandResult(command, 0, "Docker Compose version v5.1.1", "")
        if command[:4] == ["cloudflared", "--config", str(cloudflared_config), "tunnel"]:
            return CommandResult(command, 1, "", "origin cert missing")
        if command[:3] == ["docker", "network", "inspect"]:
            return CommandResult(command, 0, "\"web\"", "")
        if command[:2] == ["docker", "ps"]:
            return CommandResult(command, 0, "traefik", "")
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
    monkeypatch.setattr(
        validate_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(validate_cmd.urllib.request, "urlopen", fake_urlopen)

    checks = validate_cmd.build_validate_report(config, quiet=True)

    assert checks
    assert quiet_flags == [True, True, True, True]


def test_collect_cloudflared_config_warnings_reports_shadowing_wildcard(tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: '*.com'\n    service: http://localhost:9000\n  - hostname: example.com\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )

    warnings = collect_cloudflared_config_warnings(cloudflared_config)

    assert warnings == [
        "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
    ]


def test_collect_cloudflared_config_warnings_reports_wildcard_precedence_risk(tmp_path: Path) -> None:
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        "tunnel: 1234-uuid\ningress:\n  - hostname: '*.com'\n    service: http://localhost:9000\n  - hostname: '*.example.com'\n    service: http://localhost:8081\n  - service: http_status:404\n",
        encoding="utf-8",
    )

    warnings = collect_cloudflared_config_warnings(cloudflared_config)

    assert warnings == [
        "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard "
        "*.example.com at ingress index 1. Hint: move the narrower wildcard *.example.com above *.com, "
        "or narrow/remove the broader wildcard if it is no longer needed"
    ]
