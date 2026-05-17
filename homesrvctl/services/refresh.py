from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from homesrvctl.config import load_config
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.stacks import inspect_stack, iter_stack_dirs
from homesrvctl.state.models import RefreshResult, StackSnapshot
from homesrvctl.state.store import StateStore
from homesrvctl.utils import validate_hostname


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refresh_local_stack_state(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    config: HomesrvctlConfig | None = None,
    stack: str | None = None,
    dry_run: bool = False,
) -> RefreshResult:
    started_at = utc_now_iso()
    store = StateStore(db_path)
    active_config = config or load_config(config_path)
    store.initialize(started_at)

    issues: list[str] = []
    snapshots: list[StackSnapshot] = []
    if stack:
        try:
            snapshot, stack_issues = inspect_stack(active_config, validate_hostname(stack))
            snapshots = [snapshot]
            issues.extend(f"{snapshot.hostname}: {issue}" for issue in stack_issues)
        except typer.BadParameter:
            raise
    elif not active_config.sites_root.exists():
        issues.append(f"sites root does not exist: {active_config.sites_root}")
    else:
        for stack_dir in iter_stack_dirs(active_config):
            snapshot, stack_issues = inspect_stack(active_config, stack_dir.name)
            snapshots.append(snapshot)
            issues.extend(f"{snapshot.hostname}: {issue}" for issue in stack_issues)

    if not dry_run:
        for snapshot in snapshots:
            store.upsert_stack_snapshot(snapshot, started_at)

    finished_at = utc_now_iso()
    return RefreshResult(
        db_path=store.path,
        scanned_count=len(snapshots),
        updated_count=0 if dry_run else len(snapshots),
        stacks=snapshots,
        started_at=started_at,
        finished_at=finished_at,
        ok=not issues,
        dry_run=dry_run,
        issues=issues,
    )


def rebuild_local_stack_state(
    *,
    db_path: Path | None = None,
    config_path: Path | None = None,
    config: HomesrvctlConfig | None = None,
) -> RefreshResult:
    started_at = utc_now_iso()
    store = StateStore(db_path)
    store.initialize(started_at)
    store.clear_local_stack_state()
    return refresh_local_stack_state(db_path=store.path, config_path=config_path, config=config)
