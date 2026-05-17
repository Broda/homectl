from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DatabaseStatus:
    db_path: Path
    exists: bool
    initialized: bool
    schema_version: int | None
    stack_count: int
    last_refresh_at: str | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and self.initialized and not self.issues

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["db_path"] = str(self.db_path)
        payload["ok"] = self.ok
        payload["state_schema_version"] = payload.pop("schema_version")
        return payload


@dataclass(slots=True)
class StackSnapshot:
    hostname: str
    stack_dir: Path
    compose_file: Path | None
    has_compose: bool
    has_stack_config: bool
    scaffold_kind: str | None
    scaffold_template: str | None
    profile: str | None
    docker_network: str | None
    traefik_url: str | None
    managed_by_homesrvctl: bool = True

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["stack_dir"] = str(self.stack_dir)
        payload["compose_file"] = str(self.compose_file) if self.compose_file else None
        return payload


@dataclass(slots=True)
class RefreshResult:
    db_path: Path
    scanned_count: int
    updated_count: int
    stacks: list[StackSnapshot]
    started_at: str
    finished_at: str
    ok: bool = True
    dry_run: bool = False
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "db_path": str(self.db_path),
            "scanned_count": self.scanned_count,
            "updated_count": self.updated_count,
            "stacks": [stack.to_dict() for stack in self.stacks],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "dry_run": self.dry_run,
            "issues": self.issues,
        }
