from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ObservationRecord:
    source: str
    target_type: str
    target: str
    status: str
    detail: str
    data: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ObserverResult:
    observer_name: str
    ok: bool
    started_at: str
    finished_at: str
    target_type: str | None
    target: str | None
    status: str
    summary: str
    observations: list[ObservationRecord] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "observer_name": self.observer_name,
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "target_type": self.target_type,
            "target": self.target,
            "status": self.status,
            "summary": self.summary,
            "observations": [observation.to_dict() for observation in self.observations],
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class ObserverRunResult:
    ok: bool
    db_path: Path
    started_at: str
    finished_at: str
    results: list[ObserverResult]
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "db_path": str(self.db_path),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "observers": [result.to_dict() for result in self.results],
            "issues": self.issues,
        }


@dataclass(slots=True)
class ObserverStatusResult:
    ok: bool
    db_path: Path
    stack_runtime: dict[str, object] | None
    cloudflared: dict[str, object] | None
    traefik: dict[str, object] | None
    cloudflare: dict[str, object] | None = None
    ses: dict[str, object] | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "db_path": str(self.db_path),
            "stack_runtime": self.stack_runtime,
            "cloudflared": self.cloudflared,
            "traefik": self.traefik,
            "cloudflare": self.cloudflare,
            "ses": self.ses,
            "provider_observers": {
                "cloudflare": self.cloudflare,
                "ses": self.ses,
            },
            "issues": self.issues,
        }
