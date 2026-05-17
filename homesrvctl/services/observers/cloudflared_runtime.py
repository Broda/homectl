from __future__ import annotations

import os

import typer

from homesrvctl.cloudflared import CloudflaredConfigError, cloudflared_credentials_path, test_cloudflared_config
from homesrvctl.cloudflared_service import detect_cloudflared_runtime, inspect_cloudflared_systemd_unit
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso

CLOUDFLARED_RUNTIME_OBSERVER = "cloudflared_runtime"


def observe_cloudflared_runtime(config: HomesrvctlConfig) -> ObserverResult:
    started_at = utc_now_iso()
    issues: list[str] = []
    config_path = config.cloudflared_config
    runtime = detect_cloudflared_runtime(quiet=True)
    unit = inspect_cloudflared_systemd_unit(quiet=True)
    config_exists = config_path.exists()
    config_readable = _path_readable(config_path)
    config_writable = os.access(config_path, os.W_OK) if config_exists else os.access(config_path.parent, os.W_OK)
    validation_data: dict[str, object] | None = None
    credentials_data = _credentials_data(config_path) if config_exists and config_readable else {}

    if not config_exists:
        issues.append(f"configured cloudflared config is missing: {config_path}")
    elif not config_readable:
        issues.append(f"configured cloudflared config is not readable: {config_path}")
    else:
        validation = test_cloudflared_config(config_path)
        validation_data = {
            "ok": validation.ok,
            "detail": validation.detail,
            "method": validation.method,
            "command": validation.command,
            "warnings": validation.warnings or [],
        }
        if not validation.ok:
            issues.append(validation.detail)

    if not runtime.active:
        issues.append(runtime.detail)

    runtime_path = unit.config_path
    paths_aligned = str(config_path) == runtime_path if runtime_path else None
    if runtime_path and paths_aligned is False:
        issues.append(f"cloudflared runtime uses {runtime_path}, config points at {config_path}")

    status = "active" if runtime.active and not issues else ("inactive" if not runtime.active else "issues")
    detail = runtime.detail if runtime.active else f"cloudflared inactive: {runtime.detail}"
    data: dict[str, object] = {
        "runtime_mode": runtime.mode,
        "active": runtime.active,
        "runtime_detail": runtime.detail,
        "config_path": str(config_path),
        "config_exists": config_exists,
        "config_readable": config_readable,
        "config_writable": config_writable,
        "systemd_unit_present": unit.present,
        "runtime_path": runtime_path,
        "paths_aligned": paths_aligned,
        "config_validation": validation_data,
        **credentials_data,
    }
    finished_at = utc_now_iso()
    return ObserverResult(
        observer_name=CLOUDFLARED_RUNTIME_OBSERVER,
        ok=not issues,
        started_at=started_at,
        finished_at=finished_at,
        target_type="runtime",
        target="cloudflared",
        status=status,
        summary=detail,
        observations=[
            ObservationRecord(
                source=CLOUDFLARED_RUNTIME_OBSERVER,
                target_type="runtime",
                target="cloudflared",
                status=status,
                detail=detail,
                data=data,
            )
        ],
        issues=issues,
    )


def _path_readable(path) -> bool:  # noqa: ANN001
    try:
        path.read_text(encoding="utf-8")
    except OSError:
        return False
    return True


def _credentials_data(config_path) -> dict[str, object]:  # noqa: ANN001
    try:
        credentials_path = cloudflared_credentials_path(config_path)
    except (CloudflaredConfigError, typer.BadParameter):
        return {
            "configured_credentials_path": None,
            "configured_credentials_exists": None,
            "configured_credentials_readable": None,
        }
    return {
        "configured_credentials_path": str(credentials_path),
        "configured_credentials_exists": credentials_path.exists(),
        "configured_credentials_readable": _path_readable(credentials_path),
    }
