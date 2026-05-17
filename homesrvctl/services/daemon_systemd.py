from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import shutil

from homesrvctl.shell import command_exists, run_command
from homesrvctl.state.db import default_state_db_path

DEFAULT_DAEMON_UNIT_NAME = "homesrvctl-daemon.service"
SYSTEM_UNIT_DIR = Path("/etc/systemd/system")


@dataclass(slots=True)
class DaemonUnitConfig:
    unit_name: str
    interval_seconds: float
    db_path: Path
    config_path: Path | None = None
    executable: str | None = None
    observe_runtime: bool = False


@dataclass(slots=True)
class DaemonInstallResult:
    ok: bool
    unit_name: str
    unit_path: Path
    service_mode: str
    interval_seconds: float
    db_path: Path
    config_path: Path | None
    dry_run: bool
    wrote_unit: bool
    daemon_reload_ran: bool
    enabled: bool
    started: bool
    observe_runtime: bool = False
    commands: list[list[str]] = field(default_factory=list)
    unit_content: str | None = None
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "unit_name": self.unit_name,
            "unit_path": str(self.unit_path),
            "service_mode": self.service_mode,
            "interval_seconds": self.interval_seconds,
            "db_path": str(self.db_path),
            "config_path": str(self.config_path) if self.config_path else None,
            "dry_run": self.dry_run,
            "wrote_unit": self.wrote_unit,
            "daemon_reload_ran": self.daemon_reload_ran,
            "enabled": self.enabled,
            "started": self.started,
            "observe_runtime": self.observe_runtime,
            "commands": self.commands,
            "unit_content": self.unit_content,
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class DaemonUninstallResult:
    ok: bool
    unit_name: str
    unit_path: Path
    service_mode: str
    dry_run: bool
    existed: bool
    removed: bool
    stopped: bool
    disabled: bool
    daemon_reload_ran: bool
    db_preserved: bool = True
    commands: list[list[str]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "unit_name": self.unit_name,
            "unit_path": str(self.unit_path),
            "service_mode": self.service_mode,
            "dry_run": self.dry_run,
            "existed": self.existed,
            "removed": self.removed,
            "stopped": self.stopped,
            "disabled": self.disabled,
            "daemon_reload_ran": self.daemon_reload_ran,
            "db_preserved": self.db_preserved,
            "commands": self.commands,
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class DaemonSystemdStatus:
    systemd_available: bool
    unit_name: str
    unit_path: Path
    unit_installed: bool
    active_state: str | None
    sub_state: str | None
    enabled_state: str | None
    supervised: bool
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "systemd_available": self.systemd_available,
            "unit_name": self.unit_name,
            "unit_path": str(self.unit_path),
            "unit_installed": self.unit_installed,
            "active_state": self.active_state,
            "sub_state": self.sub_state,
            "enabled_state": self.enabled_state,
            "supervised": self.supervised,
            "systemd_issues": self.issues,
        }


@dataclass(slots=True)
class DaemonActionResult:
    ok: bool
    action: str
    unit_name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "action": self.action,
            "unit_name": self.unit_name,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def render_daemon_unit(config: DaemonUnitConfig) -> str:
    executable = config.executable or resolve_homesrvctl_executable()
    command = [
        executable,
        "daemon",
        "run",
        "--interval-seconds",
        f"{config.interval_seconds:g}",
        "--db-path",
        str(config.db_path),
        "--quiet",
    ]
    if config.config_path:
        command.extend(["--config-path", str(config.config_path)])
    if config.observe_runtime:
        command.append("--observe-runtime")
    exec_start = " ".join(shlex.quote(part) for part in command)
    return "\n".join(
        [
            "[Unit]",
            "Description=homesrvctl read-only local observer daemon",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart={exec_start}",
            "Restart=on-failure",
            "RestartSec=10",
            "Environment=PYTHONUNBUFFERED=1",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def install_daemon_unit(
    *,
    unit_name: str = DEFAULT_DAEMON_UNIT_NAME,
    interval_seconds: float,
    db_path: Path | None = None,
    config_path: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    now: bool = False,
    observe_runtime: bool = False,
    unit_dir: Path = SYSTEM_UNIT_DIR,
    runner=run_command,  # noqa: ANN001
) -> DaemonInstallResult:
    unit_path = unit_dir / unit_name
    target_db_path = db_path or default_state_db_path()
    commands = [["systemctl", "daemon-reload"]]
    if now:
        commands.append(["systemctl", "enable", "--now", unit_name])
    try:
        unit_content = render_daemon_unit(
            DaemonUnitConfig(
                unit_name=unit_name,
                interval_seconds=interval_seconds,
                db_path=target_db_path,
                config_path=config_path,
                observe_runtime=observe_runtime,
            )
        )
    except RuntimeError as exc:
        return _install_result(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=dry_run,
            commands=commands,
            observe_runtime=observe_runtime,
            error=str(exc),
        )
    if dry_run:
        return _install_result(
            ok=True,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=True,
            commands=commands,
            unit_content=unit_content,
            observe_runtime=observe_runtime,
        )
    if os.geteuid() != 0:
        return _install_result(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=False,
            commands=commands,
            unit_content=unit_content,
            observe_runtime=observe_runtime,
            error="system daemon install requires sudo/root",
        )
    if not command_exists("systemctl"):
        return _install_result(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=False,
            commands=commands,
            unit_content=unit_content,
            observe_runtime=observe_runtime,
            error="systemctl is not available",
        )
    if unit_path.exists() and not force:
        return _install_result(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=False,
            commands=commands,
            unit_content=unit_content,
            observe_runtime=observe_runtime,
            error=f"unit already exists; rerun with --force: {unit_path}",
        )
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit_content, encoding="utf-8")
    reload_result = runner(["systemctl", "daemon-reload"], quiet=True)
    if not reload_result.ok:
        return _install_result(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            interval_seconds=interval_seconds,
            db_path=target_db_path,
            config_path=config_path,
            dry_run=False,
            wrote_unit=True,
            commands=commands,
            unit_content=unit_content,
            observe_runtime=observe_runtime,
            error=reload_result.stderr or reload_result.stdout or "systemctl daemon-reload failed",
        )
    enabled = False
    started = False
    if now:
        now_result = runner(["systemctl", "enable", "--now", unit_name], quiet=True)
        if not now_result.ok:
            return _install_result(
                ok=False,
                unit_name=unit_name,
                unit_path=unit_path,
                interval_seconds=interval_seconds,
                db_path=target_db_path,
                config_path=config_path,
                dry_run=False,
                wrote_unit=True,
                daemon_reload_ran=True,
                commands=commands,
                unit_content=unit_content,
                observe_runtime=observe_runtime,
                error=now_result.stderr or now_result.stdout or "systemctl enable --now failed",
            )
        enabled = True
        started = True
    return _install_result(
        ok=True,
        unit_name=unit_name,
        unit_path=unit_path,
        interval_seconds=interval_seconds,
        db_path=target_db_path,
        config_path=config_path,
        dry_run=False,
        wrote_unit=True,
        daemon_reload_ran=True,
        enabled=enabled,
        started=started,
        commands=commands,
        unit_content=unit_content,
        observe_runtime=observe_runtime,
    )


def uninstall_daemon_unit(
    *,
    unit_name: str = DEFAULT_DAEMON_UNIT_NAME,
    force: bool = False,
    dry_run: bool = False,
    unit_dir: Path = SYSTEM_UNIT_DIR,
    runner=run_command,  # noqa: ANN001
) -> DaemonUninstallResult:
    unit_path = unit_dir / unit_name
    existed = unit_path.exists()
    commands: list[list[str]] = []
    if force:
        commands.extend([["systemctl", "stop", unit_name], ["systemctl", "disable", unit_name]])
    commands.append(["systemctl", "daemon-reload"])
    if dry_run:
        return DaemonUninstallResult(
            ok=True,
            unit_name=unit_name,
            unit_path=unit_path,
            service_mode="system",
            dry_run=True,
            existed=existed,
            removed=False,
            stopped=False,
            disabled=False,
            daemon_reload_ran=False,
            commands=commands,
        )
    if os.geteuid() != 0:
        return DaemonUninstallResult(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            service_mode="system",
            dry_run=False,
            existed=existed,
            removed=False,
            stopped=False,
            disabled=False,
            daemon_reload_ran=False,
            commands=commands,
            error="system daemon uninstall requires sudo/root",
        )
    if not command_exists("systemctl"):
        return DaemonUninstallResult(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            service_mode="system",
            dry_run=False,
            existed=existed,
            removed=False,
            stopped=False,
            disabled=False,
            daemon_reload_ran=False,
            commands=commands,
            error="systemctl is not available",
        )
    stopped = False
    disabled = False
    if force:
        stop_result = runner(["systemctl", "stop", unit_name], quiet=True)
        stopped = stop_result.ok
        disable_result = runner(["systemctl", "disable", unit_name], quiet=True)
        disabled = disable_result.ok
    if existed:
        unit_path.unlink()
    reload_result = runner(["systemctl", "daemon-reload"], quiet=True)
    if not reload_result.ok:
        return DaemonUninstallResult(
            ok=False,
            unit_name=unit_name,
            unit_path=unit_path,
            service_mode="system",
            dry_run=False,
            existed=existed,
            removed=existed and not unit_path.exists(),
            stopped=stopped,
            disabled=disabled,
            daemon_reload_ran=False,
            commands=commands,
            error=reload_result.stderr or reload_result.stdout or "systemctl daemon-reload failed",
        )
    return DaemonUninstallResult(
        ok=True,
        unit_name=unit_name,
        unit_path=unit_path,
        service_mode="system",
        dry_run=False,
        existed=existed,
        removed=existed,
        stopped=stopped,
        disabled=disabled,
        daemon_reload_ran=True,
        commands=commands,
    )


def inspect_daemon_systemd(
    *,
    unit_name: str = DEFAULT_DAEMON_UNIT_NAME,
    unit_dir: Path = SYSTEM_UNIT_DIR,
    runner=run_command,  # noqa: ANN001
) -> DaemonSystemdStatus:
    unit_path = unit_dir / unit_name
    issues: list[str] = []
    if not command_exists("systemctl"):
        return DaemonSystemdStatus(
            systemd_available=False,
            unit_name=unit_name,
            unit_path=unit_path,
            unit_installed=unit_path.exists(),
            active_state=None,
            sub_state=None,
            enabled_state=None,
            supervised=False,
            issues=["systemctl is not available"],
        )
    active_state = _systemctl_show_value(unit_name, "ActiveState", runner)
    sub_state = _systemctl_show_value(unit_name, "SubState", runner)
    enabled_result = runner(["systemctl", "is-enabled", unit_name], quiet=True)
    enabled_state = enabled_result.stdout if enabled_result.ok else None
    unit_installed = unit_path.exists() or active_state not in {None, "not-found"}
    if not unit_installed:
        issues.append(f"systemd unit is not installed: {unit_name}")
    return DaemonSystemdStatus(
        systemd_available=True,
        unit_name=unit_name,
        unit_path=unit_path,
        unit_installed=unit_installed,
        active_state=active_state,
        sub_state=sub_state,
        enabled_state=enabled_state,
        supervised=unit_installed and active_state == "active",
        issues=issues,
    )


def run_daemon_systemd_action(
    action: str,
    *,
    unit_name: str = DEFAULT_DAEMON_UNIT_NAME,
    runner=run_command,  # noqa: ANN001
) -> DaemonActionResult:
    command = ["systemctl", action, unit_name]
    if not command_exists("systemctl"):
        return DaemonActionResult(
            ok=False,
            action=f"daemon_{action}",
            unit_name=unit_name,
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            error="systemctl is not available",
        )
    result = runner(command, quiet=True)
    return DaemonActionResult(
        ok=result.ok,
        action=f"daemon_{action}",
        unit_name=unit_name,
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        error=None if result.ok else (result.stderr or result.stdout or f"systemctl {action} failed"),
    )


def run_daemon_logs(
    *,
    unit_name: str = DEFAULT_DAEMON_UNIT_NAME,
    lines: int = 100,
    follow: bool = False,
    runner=run_command,  # noqa: ANN001
) -> DaemonActionResult:
    command = ["journalctl", "-u", unit_name, "-n", str(lines), "--no-pager"]
    if follow:
        command.append("-f")
    if not command_exists("journalctl"):
        return DaemonActionResult(
            ok=False,
            action="daemon_logs",
            unit_name=unit_name,
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            error="journalctl is not available",
        )
    result = runner(command, quiet=True)
    return DaemonActionResult(
        ok=result.ok,
        action="daemon_logs",
        unit_name=unit_name,
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        error=None if result.ok else (result.stderr or result.stdout or "journalctl failed"),
    )


def resolve_homesrvctl_executable() -> str:
    resolved = shutil.which("homesrvctl")
    if resolved:
        return resolved
    raise RuntimeError("could not find `homesrvctl` on PATH; install homesrvctl or run with PATH configured")


def _systemctl_show_value(unit_name: str, property_name: str, runner) -> str | None:  # noqa: ANN001
    result = runner(["systemctl", "show", unit_name, "--property", property_name, "--value"], quiet=True)
    if not result.ok:
        return None
    return result.stdout or None


def _install_result(
    *,
    ok: bool,
    unit_name: str,
    unit_path: Path,
    interval_seconds: float,
    db_path: Path,
    config_path: Path | None,
    dry_run: bool,
    commands: list[list[str]],
    wrote_unit: bool = False,
    daemon_reload_ran: bool = False,
    enabled: bool = False,
    started: bool = False,
    unit_content: str | None = None,
    observe_runtime: bool = False,
    error: str | None = None,
) -> DaemonInstallResult:
    return DaemonInstallResult(
        ok=ok,
        unit_name=unit_name,
        unit_path=unit_path,
        service_mode="system",
        interval_seconds=interval_seconds,
        db_path=db_path,
        config_path=config_path,
        dry_run=dry_run,
        wrote_unit=wrote_unit,
        daemon_reload_ran=daemon_reload_ran,
        enabled=enabled,
        started=started,
        observe_runtime=observe_runtime,
        commands=commands,
        unit_content=unit_content,
        error=error,
    )
