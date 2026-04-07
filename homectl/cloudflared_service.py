from __future__ import annotations

from dataclasses import dataclass

from homectl.shell import run_command


@dataclass(slots=True)
class CloudflaredRuntime:
    mode: str
    active: bool
    detail: str
    restart_command: list[str] | None = None
    logs_command: list[str] | None = None


class CloudflaredServiceError(RuntimeError):
    pass


def detect_cloudflared_runtime() -> CloudflaredRuntime:
    systemctl = run_command(["systemctl", "is-active", "cloudflared"])
    if systemctl.ok and systemctl.stdout == "active":
        return CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            logs_command=["journalctl", "-u", "cloudflared", "-n", "100", "--no-pager"],
        )

    docker_ps = run_command(
        ["docker", "ps", "--filter", "name=cloudflared", "--filter", "status=running", "--format", "{{.Names}}"]
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
            logs_command=["docker", "logs", "--tail", "100", container_name],
        )

    pgrep = run_command(["pgrep", "-fa", "cloudflared"])
    if pgrep.ok and pgrep.stdout.strip():
        return CloudflaredRuntime(
            mode="process",
            active=True,
            detail=f"process present: {pgrep.stdout}",
            restart_command=None,
            logs_command=None,
        )

    detail = systemctl.stderr or systemctl.stdout or "cloudflared not detected via systemd, docker, or process scan"
    return CloudflaredRuntime(mode="absent", active=False, detail=detail, restart_command=None, logs_command=None)


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
