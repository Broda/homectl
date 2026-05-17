from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import sleep as default_sleep
from typing import Callable

from homesrvctl.services.observers.models import ObserverRunResult
from homesrvctl.services.observers.runner import run_observers
from homesrvctl.services.refresh import refresh_local_stack_state, utc_now_iso
from homesrvctl.state.models import RefreshResult
from homesrvctl.state.store import StateStore

DAEMON_EVENT_SOURCE = "daemon"
DEFAULT_DAEMON_INTERVAL_SECONDS = 60.0


@dataclass(slots=True)
class DaemonCycleResult:
    ok: bool
    started_at: str
    finished_at: str
    scanned_count: int
    updated_count: int
    issues: list[str] = field(default_factory=list)
    error: str | None = None
    observer_run: ObserverRunResult | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "scanned_count": self.scanned_count,
            "updated_count": self.updated_count,
            "issues": self.issues,
            "error": self.error,
            "observer_run": self.observer_run.to_dict() if self.observer_run else None,
        }
        return payload


@dataclass(slots=True)
class DaemonRunResult:
    ok: bool
    mode: str
    db_path: Path
    interval_seconds: float
    cycle_count: int
    started_at: str
    stopped_at: str | None
    last_cycle: DaemonCycleResult | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "mode": self.mode,
            "db_path": str(self.db_path),
            "interval_seconds": self.interval_seconds,
            "cycle_count": self.cycle_count,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_refresh": self.last_cycle.to_dict() if self.last_cycle else None,
            "issues": self.issues,
        }
        if self.last_cycle and self.last_cycle.error:
            payload["error"] = self.last_cycle.error
        return payload


@dataclass(slots=True)
class DaemonStatus:
    ok: bool
    db_path: Path
    initialized: bool
    state_schema_version: int | None
    stack_count: int
    cache_available: bool
    last_refresh_at: str | None
    daemon_heartbeat_at: str | None
    daemon_active: bool | None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "db_path": str(self.db_path),
            "initialized": self.initialized,
            "state_schema_version": self.state_schema_version,
            "stack_count": self.stack_count,
            "cache_available": self.cache_available,
            "last_refresh_at": self.last_refresh_at,
            "daemon_heartbeat_at": self.daemon_heartbeat_at,
            "daemon_active": self.daemon_active,
            "issues": self.issues,
        }


def run_daemon_cycle(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    observe_runtime: bool = False,
    observe_cloudflare: bool = False,
) -> DaemonCycleResult:
    try:
        refresh_result = refresh_local_stack_state(db_path=db_path, config_path=config_path)
    except Exception as exc:
        now = utc_now_iso()
        return DaemonCycleResult(
            ok=False,
            started_at=now,
            finished_at=now,
            scanned_count=0,
            updated_count=0,
            issues=[],
            error=str(exc),
        )
    cycle = _cycle_from_refresh(refresh_result)
    if not observe_runtime and not observe_cloudflare:
        return cycle
    observer_run = run_observers(
        db_path=db_path,
        config_path=config_path,
        stack_runtime=observe_runtime,
        cloudflared=observe_runtime,
        traefik=observe_runtime,
        cloudflare=observe_cloudflare,
    )
    cycle.observer_run = observer_run
    cycle.issues.extend(observer_run.issues)
    cycle.ok = cycle.ok and observer_run.ok
    return cycle


def run_daemon(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    interval_seconds: float = DEFAULT_DAEMON_INTERVAL_SECONDS,
    once: bool = False,
    sleep_func: Callable[[float], None] = default_sleep,
    max_cycles: int | None = None,
    on_cycle: Callable[[DaemonCycleResult], None] | None = None,
    observe_runtime: bool = False,
    observe_cloudflare: bool = False,
) -> DaemonRunResult:
    started_at = utc_now_iso()
    store = StateStore(db_path)
    store.initialize(started_at)
    _record_daemon_event(store, created_at=started_at, severity="info", message="daemon started")

    cycle_count = 0
    issues: list[str] = []
    last_cycle: DaemonCycleResult | None = None
    stopped_at: str | None = None
    interrupted = False

    try:
        while True:
            last_cycle = run_daemon_cycle(
                db_path=store.path,
                config_path=config_path,
                observe_runtime=observe_runtime,
                observe_cloudflare=observe_cloudflare,
            )
            cycle_count += 1
            if not last_cycle.ok:
                _record_cycle_issue_event(store, last_cycle)
                issues.extend(_cycle_issue_messages(last_cycle))
            if on_cycle:
                on_cycle(last_cycle)
            if once or (max_cycles is not None and cycle_count >= max_cycles):
                break
            sleep_func(interval_seconds)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        stopped_at = utc_now_iso()
        _record_daemon_event(store, created_at=stopped_at, severity="info", message="daemon stopped")

    ok = (not issues and last_cycle is not None and last_cycle.ok) or (interrupted and cycle_count > 0)
    if once and last_cycle is not None:
        ok = last_cycle.ok
    return DaemonRunResult(
        ok=ok,
        mode="once" if once else "loop",
        db_path=store.path,
        interval_seconds=interval_seconds,
        cycle_count=cycle_count,
        started_at=started_at,
        stopped_at=stopped_at,
        last_cycle=last_cycle,
        issues=issues,
    )


def get_daemon_status(*, db_path: Path | None = None) -> DaemonStatus:
    store = StateStore(db_path)
    status = store.status()
    latest_daemon_event = store.latest_event(source=DAEMON_EVENT_SOURCE) if status.initialized else None
    daemon_heartbeat_at = str(latest_daemon_event["created_at"]) if latest_daemon_event else None
    return DaemonStatus(
        ok=status.ok,
        db_path=store.path,
        initialized=status.initialized,
        state_schema_version=status.schema_version,
        stack_count=status.stack_count,
        cache_available=status.stack_count > 0,
        last_refresh_at=status.last_refresh_at,
        daemon_heartbeat_at=daemon_heartbeat_at,
        daemon_active=None,
        issues=status.issues,
    )


def _cycle_from_refresh(refresh_result: RefreshResult) -> DaemonCycleResult:
    return DaemonCycleResult(
        ok=refresh_result.ok,
        started_at=refresh_result.started_at,
        finished_at=refresh_result.finished_at,
        scanned_count=refresh_result.scanned_count,
        updated_count=refresh_result.updated_count,
        issues=refresh_result.issues,
    )


def _record_daemon_event(
    store: StateStore,
    *,
    created_at: str,
    severity: str,
    message: str,
    data: dict[str, object] | None = None,
) -> None:
    store.add_event(
        created_at=created_at,
        severity=severity,
        source=DAEMON_EVENT_SOURCE,
        message=message,
        data=data,
    )


def _record_cycle_issue_event(store: StateStore, cycle: DaemonCycleResult) -> None:
    data = cycle.to_dict()
    _record_daemon_event(
        store,
        created_at=cycle.finished_at,
        severity="warning",
        message="refresh failed" if cycle.error else "refresh completed with issues",
        data=data,
    )


def _cycle_issue_messages(cycle: DaemonCycleResult) -> list[str]:
    if cycle.error:
        return [cycle.error]
    return list(cycle.issues)
