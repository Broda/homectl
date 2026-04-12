from __future__ import annotations

from dataclasses import dataclass
import getpass
import grp
import os
from pathlib import Path
import pwd
import shlex
import stat

import typer
import yaml

from homesrvctl.cloudflared import CloudflaredConfigError, cloudflared_credentials_path
from homesrvctl.shell import run_command

SHARED_GROUP_NAME = "homesrvctl"
SHARED_CONFIG_DIR = Path("/srv/homesrvctl/cloudflared")
SHARED_CONFIG_PATH = SHARED_CONFIG_DIR / "config.yml"


@dataclass(slots=True)
class CloudflaredRuntime:
    mode: str
    active: bool
    detail: str
    restart_command: list[str] | None = None
    reload_command: list[str] | None = None
    logs_command: list[str] | None = None


@dataclass(slots=True)
class CloudflaredSystemdUnit:
    present: bool
    exec_start: str | None
    config_path: str | None
    user: str | None
    group: str | None


@dataclass(slots=True)
class CloudflaredSetupReport:
    ok: bool
    setup_state: str
    mode: str
    systemd_managed: bool
    active: bool
    configured_path: str
    configured_exists: bool
    configured_writable: bool
    configured_credentials_path: str | None
    configured_credentials_exists: bool | None
    configured_credentials_readable: bool | None
    configured_credentials_group_readable: bool | None
    configured_credentials_owner: str | None
    configured_credentials_group: str | None
    configured_credentials_mode: str | None
    runtime_path: str | None
    runtime_exists: bool | None
    runtime_readable: bool | None
    paths_aligned: bool | None
    ingress_mutation_available: bool
    account_inspection_available: bool
    service_user: str | None
    service_group: str | None
    shared_group: str
    detail: str
    issues: list[str]
    next_commands: list[str]
    override_path: str | None = None
    override_content: str | None = None
    notes: list[str] | None = None


class CloudflaredServiceError(RuntimeError):
    pass


def detect_cloudflared_runtime(*, quiet: bool = False) -> CloudflaredRuntime:
    systemctl = run_command(["systemctl", "is-active", "cloudflared"], quiet=quiet)
    if systemctl.ok and systemctl.stdout == "active":
        can_reload = run_command(
            ["systemctl", "show", "cloudflared", "--property", "CanReload", "--value"],
            quiet=quiet,
        )
        reload_command = ["systemctl", "reload", "cloudflared"] if can_reload.ok and can_reload.stdout.lower() == "yes" else None
        return CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=reload_command,
            logs_command=["journalctl", "-u", "cloudflared", "-n", "100", "--no-pager"],
        )

    docker_ps = run_command(
        ["docker", "ps", "--filter", "name=cloudflared", "--filter", "status=running", "--format", "{{.Names}}"],
        quiet=quiet,
    )
    container_names = [line.strip() for line in docker_ps.stdout.splitlines() if line.strip()]
    if container_names:
        container_name = container_names[0]
        detail = f"running container(s): {', '.join(container_names)}"
        return CloudflaredRuntime(
            mode="docker",
            active=True,
            detail=detail,
            restart_command=["docker", "restart", container_name],
            reload_command=None,
            logs_command=["docker", "logs", "--tail", "100", container_name],
        )

    pgrep = run_command(["pgrep", "-fa", "cloudflared"], quiet=quiet)
    if pgrep.ok and pgrep.stdout.strip():
        return CloudflaredRuntime(
            mode="process",
            active=True,
            detail=f"process present: {pgrep.stdout}",
            restart_command=None,
            reload_command=None,
            logs_command=None,
        )

    detail = systemctl.stderr or systemctl.stdout or "cloudflared not detected via systemd, docker, or process scan"
    return CloudflaredRuntime(mode="absent", active=False, detail=detail, restart_command=None, reload_command=None, logs_command=None)


def inspect_cloudflared_setup(config_path: Path, *, runtime: CloudflaredRuntime | None = None, quiet: bool = False) -> CloudflaredSetupReport:
    resolved_runtime = runtime or detect_cloudflared_runtime(quiet=quiet)
    unit = inspect_cloudflared_systemd_unit(quiet=quiet)
    configured_exists = config_path.exists()
    configured_writable = _path_is_writable(config_path)
    runtime_path = unit.config_path if unit.present else None
    runtime_exists = Path(runtime_path).exists() if runtime_path else None
    runtime_readable = _path_is_readable(Path(runtime_path)) if runtime_path else None
    paths_aligned = str(config_path) == runtime_path if runtime_path else None

    issues: list[str] = []
    notes: list[str] = []
    next_commands: list[str] = []
    override_path = "/etc/systemd/system/cloudflared.service.d/override.conf" if unit.present else None
    current_user = getpass.getuser()
    configured_credentials_path: str | None = None
    configured_credentials_exists: bool | None = None
    configured_credentials_readable: bool | None = None
    configured_credentials_group_readable: bool | None = None
    configured_credentials_owner: str | None = None
    configured_credentials_group: str | None = None
    configured_credentials_mode: str | None = None
    target_config_path = SHARED_CONFIG_PATH if unit.present else config_path
    target_credentials_path: Path | None = None
    override_content = _systemd_override_content(target_config_path) if unit.present else None

    if not configured_exists:
        issues.append(f"configured cloudflared config is missing: {config_path}")
    if not configured_writable:
        issues.append(f"configured cloudflared config is not writable by the current user: {config_path}")
    if unit.present and runtime_path and not paths_aligned:
        issues.append(
            f"systemd cloudflared service uses {runtime_path}, but homesrvctl is configured for {config_path}"
        )
    if unit.present and runtime_path and runtime_exists is False:
        issues.append(f"systemd cloudflared config path is missing: {runtime_path}")
    if unit.present and runtime_path and runtime_exists and runtime_readable is False:
        issues.append(f"systemd cloudflared config path is not readable by the current user: {runtime_path}")

    try:
        credentials_path = cloudflared_credentials_path(config_path)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        credentials_path = None
        if configured_exists:
            issues.append(str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        credentials_path = None
        if configured_exists:
            issues.append(str(exc))
    else:
        configured_credentials_path = str(credentials_path)
        configured_credentials_exists = credentials_path.exists()
        if configured_credentials_exists:
            configured_credentials_readable = _path_is_readable(credentials_path)
            metadata = _path_metadata(credentials_path)
            configured_credentials_group_readable = metadata["group_readable"]
            configured_credentials_owner = metadata["owner"]
            configured_credentials_group = metadata["group"]
            configured_credentials_mode = metadata["mode"]
            if configured_credentials_readable:
                target_credentials_path = credentials_path
            else:
                notes.append(
                    "account inspection unavailable: cloudflared credentials are not readable by the current user"
                )
                target_credentials_path = SHARED_CONFIG_DIR / credentials_path.name
        else:
            issues.append(f"cloudflared credentials file missing: {credentials_path}")
            target_credentials_path = SHARED_CONFIG_DIR / credentials_path.name

    if resolved_runtime.mode in {"docker", "process"}:
        notes.append(
            f"{resolved_runtime.mode} runtime detected; automatic setup repair is only modeled for systemd in this slice"
        )
    if resolved_runtime.mode == "absent" and not unit.present:
        notes.append("cloudflared runtime not detected; setup guidance is based on the configured path only")

    ingress_mutation_available = configured_exists and configured_writable and (paths_aligned is not False)
    account_inspection_available = bool(configured_credentials_exists and configured_credentials_readable)

    if unit.present and paths_aligned is False:
        setup_state = "misaligned"
    elif issues:
        setup_state = "repair needed"
    elif account_inspection_available:
        setup_state = "ready"
    else:
        setup_state = "partial"

    if unit.present and setup_state in {"misaligned", "repair needed", "partial"}:
        next_commands.extend(
            _systemd_setup_commands(
                current_user=current_user,
                configured_path=config_path,
                runtime_path=Path(runtime_path) if runtime_path else None,
                runtime_exists=runtime_exists is True,
                configured_credentials_path=Path(configured_credentials_path) if configured_credentials_path else None,
                target_config_path=target_config_path,
                target_credentials_path=target_credentials_path,
                override_path=override_path,
                override_content=override_content,
            )
        )

    if setup_state == "ready":
        detail = f"shared-group cloudflared setup is ready: {config_path}"
    elif setup_state == "partial":
        detail = "ingress mutations are ready, but account inspection is unavailable from the current user"
    else:
        detail = issues[0]

    return CloudflaredSetupReport(
        ok=setup_state in {"ready", "partial"},
        setup_state=setup_state,
        mode=resolved_runtime.mode,
        systemd_managed=unit.present,
        active=resolved_runtime.active,
        configured_path=str(config_path),
        configured_exists=configured_exists,
        configured_writable=configured_writable,
        configured_credentials_path=configured_credentials_path,
        configured_credentials_exists=configured_credentials_exists,
        configured_credentials_readable=configured_credentials_readable,
        configured_credentials_group_readable=configured_credentials_group_readable,
        configured_credentials_owner=configured_credentials_owner,
        configured_credentials_group=configured_credentials_group,
        configured_credentials_mode=configured_credentials_mode,
        runtime_path=runtime_path,
        runtime_exists=runtime_exists,
        runtime_readable=runtime_readable,
        paths_aligned=paths_aligned,
        ingress_mutation_available=ingress_mutation_available,
        account_inspection_available=account_inspection_available,
        service_user=unit.user,
        service_group=unit.group,
        shared_group=SHARED_GROUP_NAME,
        detail=detail,
        issues=issues,
        next_commands=next_commands,
        override_path=override_path,
        override_content=override_content,
        notes=notes,
    )


def inspect_cloudflared_systemd_unit(*, quiet: bool = False) -> CloudflaredSystemdUnit:
    result = run_command(
        ["systemctl", "show", "cloudflared", "--property", "ExecStart", "--property", "User", "--property", "Group"],
        quiet=quiet,
    )
    if not result.ok:
        return CloudflaredSystemdUnit(present=False, exec_start=None, config_path=None, user=None, group=None)

    lines = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        lines[key.strip()] = value.strip()

    exec_start = lines.get("ExecStart")
    if not exec_start:
        return CloudflaredSystemdUnit(present=False, exec_start=None, config_path=None, user=None, group=None)

    return CloudflaredSystemdUnit(
        present=True,
        exec_start=exec_start,
        config_path=_config_path_from_exec_start(exec_start),
        user=lines.get("User") or None,
        group=lines.get("Group") or None,
    )


def restart_cloudflared_service() -> CloudflaredRuntime:
    runtime = detect_cloudflared_runtime()
    if not runtime.active:
        raise CloudflaredServiceError(runtime.detail)
    if runtime.restart_command is None:
        raise CloudflaredServiceError(f"{runtime.detail}; restart cloudflared manually")

    result = run_command(runtime.restart_command)
    if not result.ok:
        detail = result.stderr or result.stdout or "command failed"
        raise CloudflaredServiceError(f"{runtime.mode} restart failed: {detail}")
    return runtime


def reload_cloudflared_service() -> CloudflaredRuntime:
    runtime = detect_cloudflared_runtime()
    if not runtime.active:
        raise CloudflaredServiceError(runtime.detail)
    if runtime.reload_command is None:
        raise CloudflaredServiceError(f"{runtime.detail}; reload is not supported for this runtime")

    result = run_command(runtime.reload_command)
    if not result.ok:
        detail = result.stderr or result.stdout or "command failed"
        raise CloudflaredServiceError(f"{runtime.mode} reload failed: {detail}")
    return runtime


def _config_path_from_exec_start(exec_start: str) -> str | None:
    marker = "argv[]="
    if marker not in exec_start:
        return None
    argv = exec_start.split(marker, 1)[1].split(" ;", 1)[0].strip()
    parts = shlex.split(argv)
    for index, part in enumerate(parts):
        if part == "--config" and index + 1 < len(parts):
            return parts[index + 1]
    return None


def _path_is_readable(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except OSError:
        return False
    return True


def _path_is_writable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    target = path.parent
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return target.exists() and os.access(target, os.W_OK)


def _systemd_override_content(config_path: Path) -> str:
    return "\n".join(
        [
            "[Service]",
            f"Group={SHARED_GROUP_NAME}",
            "ExecStart=",
            f"ExecStart=/usr/bin/cloudflared --no-autoupdate --config {config_path} tunnel run",
        ]
    )


def _systemd_setup_commands(
    *,
    current_user: str,
    configured_path: Path,
    runtime_path: Path | None,
    runtime_exists: bool,
    configured_credentials_path: Path | None,
    target_config_path: Path,
    target_credentials_path: Path | None,
    override_path: str | None,
    override_content: str | None,
) -> list[str]:
    commands = [
        f"sudo groupadd -f {SHARED_GROUP_NAME}",
        f"sudo usermod -aG {SHARED_GROUP_NAME} {current_user}",
        f"sudo install -d -o root -g {SHARED_GROUP_NAME} -m 750 {shlex.quote(str(SHARED_CONFIG_DIR))}",
    ]
    source_config_path = configured_path if configured_path.exists() else runtime_path
    rendered_config = _render_target_config_content(source_config_path, target_credentials_path)
    if rendered_config is not None:
        commands.append(
            f"sudo tee {shlex.quote(str(target_config_path))} >/dev/null <<'EOF'\n{rendered_config}\nEOF"
        )
        commands.append(f"sudo chown root:{SHARED_GROUP_NAME} {shlex.quote(str(target_config_path))}")
        commands.append(f"sudo chmod 640 {shlex.quote(str(target_config_path))}")
    elif runtime_path and runtime_exists:
        commands.append(
            f"sudo install -o root -g {SHARED_GROUP_NAME} -m 640 {shlex.quote(str(runtime_path))} {shlex.quote(str(target_config_path))}"
        )
    else:
        commands.append(f"sudoedit {shlex.quote(str(target_config_path))}")

    if configured_credentials_path and configured_credentials_path.exists() and target_credentials_path is not None:
        commands.append(
            f"sudo install -o root -g {SHARED_GROUP_NAME} -m 640 {shlex.quote(str(configured_credentials_path))} {shlex.quote(str(target_credentials_path))}"
        )
    elif target_credentials_path is not None:
        commands.append(f"sudoedit {shlex.quote(str(target_credentials_path))}")

    if override_path and override_content:
        commands.extend(
            [
                "sudo install -d -m 755 /etc/systemd/system/cloudflared.service.d",
                f"sudo tee {override_path} >/dev/null <<'EOF'\n{override_content}\nEOF",
                "sudo systemctl daemon-reload",
                "sudo systemctl restart cloudflared",
            ]
        )
    return commands


def _render_target_config_content(config_path: Path | None, target_credentials_path: Path | None) -> str | None:
    if config_path is None or not config_path.exists():
        return None
    try:
        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(parsed, dict):
        return None
    if target_credentials_path is not None:
        parsed["credentials-file"] = str(target_credentials_path)
    return yaml.safe_dump(parsed, sort_keys=False).rstrip()


def _path_metadata(path: Path) -> dict[str, object]:
    try:
        stat_result = path.stat()
    except OSError:
        return {
            "owner": None,
            "group": None,
            "mode": None,
            "group_readable": None,
        }
    mode = stat.S_IMODE(stat_result.st_mode)
    try:
        owner = pwd.getpwuid(stat_result.st_uid).pw_name
    except KeyError:
        owner = str(stat_result.st_uid)
    try:
        group = grp.getgrgid(stat_result.st_gid).gr_name
    except KeyError:
        group = str(stat_result.st_gid)
    return {
        "owner": owner,
        "group": group,
        "mode": format(mode, "03o"),
        "group_readable": bool(mode & stat.S_IRGRP),
    }
