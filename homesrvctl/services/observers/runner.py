from __future__ import annotations

import json
from pathlib import Path

from homesrvctl.config import load_config
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.cloudflared_runtime import (
    CLOUDFLARED_RUNTIME_OBSERVER,
    observe_cloudflared_runtime,
)
from homesrvctl.services.observers.cloudflare_provider import (
    CLOUDFLARE_PROVIDER_OBSERVER,
    observe_cloudflare_provider,
)
from homesrvctl.services.observers.models import ObserverResult, ObserverRunResult, ObserverStatusResult
from homesrvctl.services.observers.stacks_runtime import STACK_RUNTIME_OBSERVER, observe_stack_runtime
from homesrvctl.services.observers.traefik_runtime import TRAEFIK_RUNTIME_OBSERVER, observe_traefik_runtime
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.state.store import StateStore


def run_observers(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    config: HomesrvctlConfig | None = None,
    stack_runtime: bool = True,
    cloudflared: bool = True,
    traefik: bool = True,
    cloudflare: bool = False,
) -> ObserverRunResult:
    started_at = utc_now_iso()
    store = StateStore(db_path)
    store.initialize(started_at)
    active_config = config or load_config(config_path)

    results: list[ObserverResult] = []
    if stack_runtime:
        results.append(observe_stack_runtime(active_config))
    if cloudflared:
        results.append(observe_cloudflared_runtime(active_config))
    if traefik:
        results.append(observe_traefik_runtime(active_config))
    if cloudflare:
        results.append(observe_cloudflare_provider(active_config))

    for result in results:
        _persist_observer_result(store, result)

    issues = [issue for result in results for issue in result.issues]
    finished_at = utc_now_iso()
    return ObserverRunResult(
        ok=not issues and all(result.ok for result in results),
        db_path=store.path,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
        issues=issues,
    )


def get_observer_status(*, db_path: Path | None = None) -> ObserverStatusResult:
    store = StateStore(db_path)
    status = store.status()
    if not status.initialized:
        return ObserverStatusResult(
            ok=False,
            db_path=store.path,
            stack_runtime=None,
            cloudflared=None,
            traefik=None,
            cloudflare=None,
            issues=status.issues or ["no observer state found; run `homesrvctl observe run`"],
        )

    stack_observations = store.list_stack_observations(source=STACK_RUNTIME_OBSERVER, limit=200)
    latest_by_stack: dict[str, dict[str, object]] = {}
    for observation in stack_observations:
        hostname = str(observation["stack_hostname"])
        if hostname not in latest_by_stack:
            latest_by_stack[hostname] = _decode_row_data(observation)
    stack_runtime = None
    if latest_by_stack:
        stack_runtime = {
            "source": STACK_RUNTIME_OBSERVER,
            "stack_count": len(latest_by_stack),
            "latest_observed_at": max(str(row["observed_at"]) for row in stack_observations),
            "stacks": latest_by_stack,
        }

    cloudflared = _decode_event(store.latest_event(source=CLOUDFLARED_RUNTIME_OBSERVER))
    traefik = _decode_event(store.latest_event(source=TRAEFIK_RUNTIME_OBSERVER))
    cloudflare = _decode_event(store.latest_event(source=CLOUDFLARE_PROVIDER_OBSERVER))
    issues: list[str] = []
    if stack_runtime is None:
        issues.append("no stack runtime observations found; run `homesrvctl observe run`")
    if cloudflared is None:
        issues.append("no cloudflared observations found; run `homesrvctl observe run`")
    if traefik is None:
        issues.append("no Traefik observations found; run `homesrvctl observe run`")
    return ObserverStatusResult(
        ok=not issues,
        db_path=store.path,
        stack_runtime=stack_runtime,
        cloudflared=cloudflared,
        traefik=traefik,
        cloudflare=cloudflare,
        issues=issues,
    )


def _persist_observer_result(store: StateStore, result: ObserverResult) -> None:
    for observation in result.observations:
        if observation.target_type == "stack":
            store.add_stack_observation(
                stack_hostname=observation.target,
                observed_at=result.finished_at,
                source=observation.source,
                status=observation.status,
                detail=observation.detail,
                data=observation.data,
            )
            continue
        severity = "info" if result.ok else "warning"
        store.add_event(
            created_at=result.finished_at,
            severity=severity,
            source=observation.source,
            target_type=observation.target_type,
            target=observation.target,
            message=observation.detail,
            data=observation.to_dict(),
        )


def _decode_row_data(row: dict[str, object]) -> dict[str, object]:
    payload = dict(row)
    payload["data"] = _decode_json(payload.pop("data_json", None))
    return payload


def _decode_event(event: dict[str, object] | None) -> dict[str, object] | None:
    if event is None:
        return None
    payload = dict(event)
    payload["data"] = _decode_json(payload.pop("data_json", None))
    return payload


def _decode_json(raw: object) -> object:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw
