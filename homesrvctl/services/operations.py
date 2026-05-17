from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from homesrvctl.state.store import StateStore

OPERATION_STATUSES = {"pending", "running", "completed", "failed", "canceled"}


@dataclass(slots=True)
class OperationRecord:
    id: int
    operation_type: str
    target_type: str | None
    target: str | None
    status: str
    started_at: str
    finished_at: str | None
    summary: str | None
    error: str | None
    data: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "target_type": self.target_type,
            "target": self.target,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "error": self.error,
            "data": self.data,
        }


@dataclass(slots=True)
class OperationListResult:
    ok: bool
    db_path: Path
    operations: list[OperationRecord]
    issues: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.operations)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "db_path": str(self.db_path),
            "operations": [operation.to_dict() for operation in self.operations],
            "count": self.count,
            "issues": self.issues,
        }


@dataclass(slots=True)
class OperationResult:
    ok: bool
    db_path: Path
    operation: OperationRecord | None
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "db_path": str(self.db_path),
            "operation": self.operation.to_dict() if self.operation else None,
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def list_operations(
    *,
    db_path: Path,
    limit: int = 20,
    status: str | None = None,
    operation_type: str | None = None,
    target: str | None = None,
) -> OperationListResult:
    store = StateStore(db_path)
    db_status = store.status()
    if not db_status.initialized:
        return OperationListResult(
            ok=False,
            db_path=db_status.db_path,
            operations=[],
            issues=db_status.issues,
        )
    rows = store.list_operations(
        status=status,
        operation_type=operation_type,
        target=target,
        limit=limit,
    )
    return OperationListResult(
        ok=not db_status.issues,
        db_path=db_status.db_path,
        operations=[operation_from_row(row) for row in rows],
        issues=db_status.issues,
    )


def get_operation(*, db_path: Path, operation_id: int) -> OperationResult:
    store = StateStore(db_path)
    db_status = store.status()
    if not db_status.initialized:
        return OperationResult(
            ok=False,
            db_path=db_status.db_path,
            operation=None,
            issues=db_status.issues,
            error=db_status.issues[0] if db_status.issues else "database is not initialized",
        )
    row = store.get_operation(operation_id)
    if row is None:
        return OperationResult(
            ok=False,
            db_path=db_status.db_path,
            operation=None,
            error=f"operation not found: {operation_id}",
        )
    return OperationResult(
        ok=not db_status.issues,
        db_path=db_status.db_path,
        operation=operation_from_row(row),
        issues=db_status.issues,
    )


def operation_from_row(row: dict[str, object]) -> OperationRecord:
    data_json = row.get("data_json")
    data: dict[str, object] | None = None
    if isinstance(data_json, str) and data_json:
        try:
            decoded = json.loads(data_json)
            if isinstance(decoded, dict):
                data = decoded
            else:
                data = {"value": decoded}
        except json.JSONDecodeError:
            data = {"raw": data_json}
    return OperationRecord(
        id=int(row["id"]),
        operation_type=str(row["operation_type"]),
        target_type=str(row["target_type"]) if row.get("target_type") else None,
        target=str(row["target"]) if row.get("target") else None,
        status=str(row["status"]),
        started_at=str(row["started_at"]),
        finished_at=str(row["finished_at"]) if row.get("finished_at") else None,
        summary=str(row["summary"]) if row.get("summary") else None,
        error=str(row["error"]) if row.get("error") else None,
        data=data,
    )
