from __future__ import annotations

from homesrvctl import cloudflared_service
from homesrvctl.cloudflared_service import CloudflaredServiceError
from homesrvctl.shell import CommandResult


def test_detect_cloudflared_runtime_prefers_systemd(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False):  # noqa: ANN001, ANN202
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


def test_detect_cloudflared_runtime_uses_docker_when_systemd_inactive(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False):  # noqa: ANN001, ANN202
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

    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False):  # noqa: ANN001, ANN202
        calls.append(command)
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(cloudflared_service, "run_command", fake_run_command)

    returned = cloudflared_service.reload_cloudflared_service()

    assert returned is runtime
    assert calls == [["systemctl", "reload", "cloudflared"]]


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
