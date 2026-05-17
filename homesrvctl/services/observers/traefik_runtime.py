from __future__ import annotations

from typing import Callable
import urllib.error
import urllib.request

from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso

TRAEFIK_RUNTIME_OBSERVER = "traefik_runtime"


def observe_traefik_runtime(
    config: HomesrvctlConfig,
    *,
    urlopen: Callable[..., object] = urllib.request.urlopen,
    timeout: float = 2.0,
) -> ObserverResult:
    started_at = utc_now_iso()
    url = config.traefik_url
    issues: list[str] = []
    data: dict[str, object] = {"traefik_url": url, "reachable": False, "status_code": None}
    status = "unreachable"
    detail = f"{url} is unreachable"

    try:
        response = urlopen(url, timeout=timeout)
        status_code = int(getattr(response, "status", getattr(response, "code", 0)) or 0)
        data.update({"reachable": True, "status_code": status_code})
        status = "reachable"
        detail = f"{url} reachable"
    except urllib.error.HTTPError as exc:
        data.update({"reachable": True, "status_code": exc.code})
        status = "reachable"
        detail = f"{url} reachable with HTTP {exc.code}"
    except Exception as exc:
        data["error"] = str(exc)
        issues.append(str(exc))

    finished_at = utc_now_iso()
    return ObserverResult(
        observer_name=TRAEFIK_RUNTIME_OBSERVER,
        ok=not issues,
        started_at=started_at,
        finished_at=finished_at,
        target_type="runtime",
        target=url,
        status=status,
        summary=detail,
        observations=[
            ObservationRecord(
                source=TRAEFIK_RUNTIME_OBSERVER,
                target_type="runtime",
                target=url,
                status=status,
                detail=detail,
                data=data,
            )
        ],
        issues=issues,
    )
