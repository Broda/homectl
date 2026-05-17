from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.services.stacks import iter_stack_dirs
from homesrvctl.shell import CommandResult, command_exists, run_command

STACK_RUNTIME_OBSERVER = "stack_runtime"


def observe_stack_runtime(
    config: HomesrvctlConfig,
    *,
    runner: Callable[..., CommandResult] = run_command,
    command_exists_func: Callable[[str], bool] = command_exists,
) -> ObserverResult:
    started_at = utc_now_iso()
    observations: list[ObservationRecord] = []
    issues: list[str] = []
    docker_available = command_exists_func("docker")

    if not config.sites_root.exists():
        finished_at = utc_now_iso()
        issue = f"sites root does not exist: {config.sites_root}"
        return ObserverResult(
            observer_name=STACK_RUNTIME_OBSERVER,
            ok=False,
            started_at=started_at,
            finished_at=finished_at,
            target_type="stack",
            target=None,
            status="error",
            summary=issue,
            issues=[issue],
        )

    for stack_dir in iter_stack_dirs(config):
        observations.append(
            _observe_stack_dir(
                stack_dir,
                docker_available=docker_available,
                runner=runner,
            )
        )

    issues.extend(observation.detail for observation in observations if observation.status == "error")
    running_count = sum(1 for observation in observations if observation.status == "running")
    degraded_count = sum(1 for observation in observations if observation.status == "degraded")
    error_count = sum(1 for observation in observations if observation.status == "error")
    finished_at = utc_now_iso()
    summary = (
        f"observed {len(observations)} stacks"
        f" running={running_count} degraded={degraded_count} errors={error_count}"
    )
    return ObserverResult(
        observer_name=STACK_RUNTIME_OBSERVER,
        ok=not issues,
        started_at=started_at,
        finished_at=finished_at,
        target_type="stack",
        target=None,
        status="ok" if not issues else "issues",
        summary=summary,
        observations=observations,
        issues=issues,
    )


def _observe_stack_dir(
    stack_dir: Path,
    *,
    docker_available: bool,
    runner: Callable[..., CommandResult],
) -> ObservationRecord:
    hostname = stack_dir.name
    compose_file = stack_dir / "docker-compose.yml"
    base_data: dict[str, object] = {
        "hostname": hostname,
        "stack_dir": str(stack_dir),
        "compose_file": str(compose_file),
        "has_compose": compose_file.exists(),
        "docker_available": docker_available,
    }
    if not compose_file.exists():
        return ObservationRecord(
            source=STACK_RUNTIME_OBSERVER,
            target_type="stack",
            target=hostname,
            status="no_compose",
            detail="stack has no docker-compose.yml",
            data={**base_data, "compose_available": False},
        )
    if not docker_available:
        return ObservationRecord(
            source=STACK_RUNTIME_OBSERVER,
            target_type="stack",
            target=hostname,
            status="error",
            detail="docker command is not available",
            data={**base_data, "compose_available": False, "command": ["docker", "compose", "ps", "--format", "json"]},
        )

    json_command = ["docker", "compose", "ps", "--format", "json"]
    json_result = runner(json_command, cwd=stack_dir, quiet=True)
    if json_result.ok:
        try:
            containers = _parse_compose_json(json_result.stdout)
        except ValueError as exc:
            return _fallback_compose_ps(stack_dir, runner, base_data, detail=f"could not parse compose JSON: {exc}")
        status, detail, parsed_data = _summarize_containers(containers)
        return ObservationRecord(
            source=STACK_RUNTIME_OBSERVER,
            target_type="stack",
            target=hostname,
            status=status,
            detail=detail,
            data={
                **base_data,
                "compose_available": True,
                "command": json_result.command,
                "returncode": json_result.returncode,
                **parsed_data,
            },
        )

    return _fallback_compose_ps(
        stack_dir,
        runner,
        base_data,
        detail=json_result.stderr or json_result.stdout or "docker compose ps --format json failed",
        json_command=json_result.command,
        json_returncode=json_result.returncode,
    )


def _fallback_compose_ps(
    stack_dir: Path,
    runner: Callable[..., CommandResult],
    base_data: dict[str, object],
    *,
    detail: str,
    json_command: list[str] | None = None,
    json_returncode: int | None = None,
) -> ObservationRecord:
    command = ["docker", "compose", "ps"]
    result = runner(command, cwd=stack_dir, quiet=True)
    data = {
        **base_data,
        "compose_available": result.ok,
        "command": result.command,
        "returncode": result.returncode,
        "json_command": json_command,
        "json_returncode": json_returncode,
        "output": result.stdout,
        "stderr": result.stderr,
    }
    if not result.ok:
        error_detail = result.stderr or result.stdout or detail
        return ObservationRecord(
            source=STACK_RUNTIME_OBSERVER,
            target_type="stack",
            target=str(base_data["hostname"]),
            status="error",
            detail=error_detail,
            data=data,
        )
    text = result.stdout.strip()
    status = "unknown"
    if "Up" in text or "running" in text.lower():
        status = "running"
    elif text:
        status = "not_running"
    return ObservationRecord(
        source=STACK_RUNTIME_OBSERVER,
        target_type="stack",
        target=str(base_data["hostname"]),
        status=status,
        detail=text or "docker compose ps returned no containers",
        data=data,
    )


def _parse_compose_json(raw: str) -> list[dict[str, object]]:
    stripped = raw.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed_lines = [json.loads(line) for line in stripped.splitlines() if line.strip()]
        return [item for item in parsed_lines if isinstance(item, dict)]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError("expected object or array")


def _summarize_containers(containers: list[dict[str, object]]) -> tuple[str, str, dict[str, object]]:
    names = [str(container.get("Name") or container.get("Service") or "") for container in containers]
    services = [str(container.get("Service") or "") for container in containers if container.get("Service")]
    states = [str(container.get("State") or container.get("Status") or "").lower() for container in containers]
    running_count = sum(1 for state in states if "running" in state or state == "up")
    container_count = len(containers)
    if container_count == 0:
        status = "not_running"
        detail = "no compose containers found"
    elif running_count == container_count:
        status = "running"
        detail = f"{running_count}/{container_count} containers running"
    elif running_count > 0:
        status = "degraded"
        detail = f"{running_count}/{container_count} containers running"
    else:
        status = "not_running"
        detail = f"0/{container_count} containers running"
    return status, detail, {
        "container_count": container_count,
        "running_count": running_count,
        "container_names": [name for name in names if name],
        "service_names": services,
        "containers": containers,
    }
