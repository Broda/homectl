from __future__ import annotations

from pathlib import Path

from homesrvctl import cloudflared_service
from homesrvctl.cloudflared_service import CloudflaredServiceError
from homesrvctl.shell import CommandResult


def test_detect_cloudflared_runtime_prefers_systemd(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        calls.append((command, quiet))
        if command[:2] == ["systemctl", "is-active"]:
            return CommandResult(command, 0, "active", "")
        if command[:4] == ["systemctl", "show", "cloudflared", "--property"]:
            return CommandResult(command, 0, "yes", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    runtime = cloudflared_service.detect_cloudflared_runtime()

    assert runtime.mode == "systemd"
    assert runtime.active
    assert runtime.restart_command == ["systemctl", "restart", "cloudflared"]
    assert runtime.reload_command == ["systemctl", "reload", "cloudflared"]
    assert calls == [
        (["systemctl", "is-active", "cloudflared"], False),
        (["systemctl", "show", "cloudflared", "--property", "CanReload", "--value"], False),
    ]


def test_detect_cloudflared_runtime_honors_quiet(monkeypatch) -> None:
    quiet_flags: list[bool] = []

    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        quiet_flags.append(quiet)
        if command[:2] == ["systemctl", "is-active"]:
            return CommandResult(command, 0, "active", "")
        if command[:4] == ["systemctl", "show", "cloudflared", "--property"]:
            return CommandResult(command, 0, "yes", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    runtime = cloudflared_service.detect_cloudflared_runtime(quiet=True)

    assert runtime.mode == "systemd"
    assert quiet_flags == [True, True]


def test_detect_cloudflared_runtime_uses_docker_when_systemd_inactive(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        if command[:2] == ["systemctl", "is-active"]:
            return CommandResult(command, 3, "inactive", "")
        if command[:2] == ["docker", "ps"]:
            return CommandResult(command, 0, "cloudflared\ncloudflared-sidecar", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    runtime = cloudflared_service.detect_cloudflared_runtime()

    assert runtime.mode == "docker"
    assert runtime.active
    assert runtime.restart_command == ["docker", "restart", "cloudflared"]
    assert runtime.reload_command is None


def test_restart_cloudflared_service_errors_for_unmanaged_process(monkeypatch) -> None:
    monkeypatch.setattr(
        cloudflared_service,
        "detect_cloudflared_runtime",
        lambda: cloudflared_service.CloudflaredRuntime(
            mode="process",
            active=True,
            detail="process present: 123 cloudflared",
            restart_command=None,
            reload_command=None,
        ),
    )

    try:
        cloudflared_service.restart_cloudflared_service()
    except CloudflaredServiceError as exc:
        assert "restart cloudflared manually" in str(exc)
    else:
        raise AssertionError("expected CloudflaredServiceError")


def test_reload_cloudflared_service_runs_reload_command(monkeypatch) -> None:
    runtime = cloudflared_service.CloudflaredRuntime(
        mode="systemd",
        active=True,
        detail="systemd service is active",
        restart_command=["systemctl", "restart", "cloudflared"],
        reload_command=["systemctl", "reload", "cloudflared"],
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(cloudflared_service, "detect_cloudflared_runtime", lambda: runtime)
    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 0)

    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        calls.append(command)
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    returned = cloudflared_service.reload_cloudflared_service()

    assert returned is runtime
    assert calls == [["systemctl", "reload", "cloudflared"]]


def test_reload_cloudflared_service_uses_noninteractive_sudo_for_operator(monkeypatch) -> None:
    runtime = cloudflared_service.CloudflaredRuntime(
        mode="systemd",
        active=True,
        detail="systemd service is active",
        restart_command=["systemctl", "restart", "cloudflared"],
        reload_command=["systemctl", "reload", "cloudflared"],
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(cloudflared_service, "detect_cloudflared_runtime", lambda: runtime)
    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cloudflared_service.shutil, "which", lambda binary: "/usr/bin/sudo" if binary == "sudo" else None)

    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        calls.append(command)
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    returned = cloudflared_service.reload_cloudflared_service()

    assert returned is runtime
    assert calls == [["/usr/bin/sudo", "-n", "systemctl", "reload", "cloudflared"]]


def test_reload_cloudflared_service_errors_when_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(
        cloudflared_service,
        "detect_cloudflared_runtime",
        lambda: cloudflared_service.CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )

    try:
        cloudflared_service.reload_cloudflared_service()
    except CloudflaredServiceError as exc:
        assert "reload is not supported" in str(exc)
    else:
        raise AssertionError("expected CloudflaredServiceError")


def test_render_cloudflared_sudoers_scopes_to_restart_and_reload() -> None:
    rendered = cloudflared_service.render_cloudflared_sudoers("/usr/bin/systemctl")

    assert "%homesrvctl ALL=(root) NOPASSWD:" in rendered
    assert "/usr/bin/systemctl restart cloudflared" in rendered
    assert "/usr/bin/systemctl reload cloudflared" in rendered
    assert "docker" not in rendered


def test_inspect_cloudflared_setup_reports_partial_when_credentials_unreadable(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "cloudflared" / "config.yml"
    credentials_path = tmp_path / "cloudflared" / "tunnel.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("tunnel: test\ncredentials-file: tunnel.json\ningress:\n  - service: http_status:404\n", encoding="utf-8")
    credentials_path.write_text('{"AccountTag": "account-123"}', encoding="utf-8")
    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 0)

    monkeypatch.setattr(
        cloudflared_service,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: cloudflared_service.CloudflaredSystemdUnit(
            present=True,
            exec_start="argv[]=/usr/bin/cloudflared --no-autoupdate --config "
            f"{config_path} tunnel run ;",
            config_path=str(config_path),
            user="root",
            group="root",
        ),
    )
    runtime = cloudflared_service.CloudflaredRuntime(mode="systemd", active=True, detail="systemd service is active")
    original_is_readable = cloudflared_service._path_is_readable
    monkeypatch.setattr(
        cloudflared_service,
        "_path_is_readable",
        lambda path: False if path == credentials_path else original_is_readable(path),
    )

    setup = cloudflared_service.inspect_cloudflared_setup(config_path, runtime=runtime)

    assert setup.ok is True
    assert setup.setup_state == "partial"
    assert setup.ingress_mutation_available is True
    assert setup.account_inspection_available is False
    assert setup.configured_credentials_path == str(credentials_path)
    assert setup.override_content is not None
    assert "Group=homesrvctl" in setup.override_content
    assert any(command == "sudo groupadd -f homesrvctl" for command in setup.next_commands)


def test_inspect_cloudflared_setup_reports_ready_when_credentials_readable(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "cloudflared" / "config.yml"
    credentials_path = tmp_path / "cloudflared" / "tunnel.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("tunnel: test\ncredentials-file: tunnel.json\ningress:\n  - service: http_status:404\n", encoding="utf-8")
    credentials_path.write_text('{"AccountTag": "account-123"}', encoding="utf-8")
    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 0)

    monkeypatch.setattr(
        cloudflared_service,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: cloudflared_service.CloudflaredSystemdUnit(
            present=True,
            exec_start="argv[]=/usr/bin/cloudflared --no-autoupdate --config "
            f"{config_path} tunnel run ;",
            config_path=str(config_path),
            user="root",
            group="homesrvctl",
        ),
    )
    runtime = cloudflared_service.CloudflaredRuntime(mode="systemd", active=True, detail="systemd service is active")

    setup = cloudflared_service.inspect_cloudflared_setup(config_path, runtime=runtime)

    assert setup.ok is True
    assert setup.setup_state == "ready"
    assert setup.account_inspection_available is True
    assert setup.ingress_mutation_available is True
    assert setup.next_commands == []


def test_inspect_cloudflared_setup_reports_missing_operator_service_control(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "cloudflared" / "config.yml"
    credentials_path = tmp_path / "cloudflared" / "tunnel.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("tunnel: test\ncredentials-file: tunnel.json\ningress:\n  - service: http_status:404\n", encoding="utf-8")
    credentials_path.write_text('{"AccountTag": "account-123"}', encoding="utf-8")

    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cloudflared_service, "_current_user_groups", lambda: {"homesrvctl", "docker"})
    monkeypatch.setattr(cloudflared_service, "SUDOERS_PATH", str(tmp_path / "missing-sudoers"))
    monkeypatch.setattr(cloudflared_service.shutil, "which", lambda binary: "/usr/bin/sudo" if binary == "sudo" else None)
    monkeypatch.setattr(
        cloudflared_service,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: cloudflared_service.CloudflaredSystemdUnit(
            present=True,
            exec_start="argv[]=/usr/bin/cloudflared --no-autoupdate --config "
            f"{config_path} tunnel run ;",
            config_path=str(config_path),
            user="root",
            group="homesrvctl",
        ),
    )
    runtime = cloudflared_service.CloudflaredRuntime(mode="systemd", active=True, detail="systemd service is active")

    setup = cloudflared_service.inspect_cloudflared_setup(config_path, runtime=runtime)

    assert setup.ok is False
    assert setup.setup_state == "repair needed"
    assert setup.service_control_available is False
    assert any("service restart/reload is not available" in issue for issue in setup.issues)


def test_inspect_cloudflared_setup_handles_unreadable_runtime_path(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "cloudflared" / "config.yml"
    credentials_path = tmp_path / "cloudflared" / "tunnel.json"
    runtime_path = tmp_path / "restricted" / "config.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("tunnel: test\ncredentials-file: tunnel.json\ningress:\n  - service: http_status:404\n", encoding="utf-8")
    credentials_path.write_text('{"AccountTag": "account-123"}', encoding="utf-8")
    runtime_path.write_text("tunnel: test\ncredentials-file: tunnel.json\n", encoding="utf-8")
    monkeypatch.setattr(cloudflared_service.os, "geteuid", lambda: 0)

    monkeypatch.setattr(
        cloudflared_service,
        "inspect_cloudflared_systemd_unit",
        lambda quiet=False: cloudflared_service.CloudflaredSystemdUnit(
            present=True,
            exec_start="argv[]=/usr/bin/cloudflared --no-autoupdate --config "
            f"{runtime_path} tunnel run ;",
            config_path=str(runtime_path),
            user="root",
            group="homesrvctl",
        ),
    )
    runtime = cloudflared_service.CloudflaredRuntime(mode="systemd", active=True, detail="systemd service is active")
    original_path_exists = cloudflared_service._path_exists
    original_is_readable = cloudflared_service._path_is_readable

    monkeypatch.setattr(
        cloudflared_service,
        "_path_exists",
        lambda path: False if path == runtime_path else original_path_exists(path),
    )
    monkeypatch.setattr(
        cloudflared_service,
        "_path_is_readable",
        lambda path: False if path == runtime_path else original_is_readable(path),
    )

    setup = cloudflared_service.inspect_cloudflared_setup(config_path, runtime=runtime)

    assert setup.ok is False
    assert setup.setup_state == "misaligned"
    assert any(f"systemd cloudflared config path is missing: {runtime_path}" == issue for issue in setup.issues)
    assert any(command == f"sudo chmod 660 {cloudflared_service.SHARED_CONFIG_PATH}" for command in setup.next_commands)
