from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from homesrvctl.state.db import connect_state_db, default_state_db_path
from homesrvctl.state.models import DatabaseStatus, StackSnapshot
from homesrvctl.state.schema import SCHEMA_SQL, SCHEMA_VERSION


LOCAL_STACK_REFRESH_SOURCE = "local_stack_refresh"


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()

    def initialize(self, applied_at: str) -> bool:
        existed = self.path.exists()
        with connect_state_db(self.path) as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, applied_at),
            )
        return not existed

    def status(self) -> DatabaseStatus:
        if not self.path.exists():
            return DatabaseStatus(
                db_path=self.path,
                exists=False,
                initialized=False,
                schema_version=None,
                stack_count=0,
                last_refresh_at=None,
                issues=["database does not exist; run `homesrvctl db init`"],
            )

        try:
            with sqlite3.connect(self.path) as connection:
                connection.row_factory = sqlite3.Row
                initialized = self._table_exists(connection, "schema_version")
                if not initialized:
                    return DatabaseStatus(
                        db_path=self.path,
                        exists=True,
                        initialized=False,
                        schema_version=None,
                        stack_count=0,
                        last_refresh_at=None,
                        issues=["database schema is not initialized; run `homesrvctl db init`"],
                    )
                schema_version = connection.execute("SELECT max(version) FROM schema_version").fetchone()[0]
                stack_count = (
                    connection.execute("SELECT count(*) FROM stacks").fetchone()[0]
                    if self._table_exists(connection, "stacks")
                    else 0
                )
                last_refresh_at = (
                    connection.execute(
                        "SELECT max(observed_at) FROM stack_observations WHERE source = ?",
                        (LOCAL_STACK_REFRESH_SOURCE,),
                    ).fetchone()[0]
                    if self._table_exists(connection, "stack_observations")
                    else None
                )
        except sqlite3.DatabaseError as exc:
            return DatabaseStatus(
                db_path=self.path,
                exists=True,
                initialized=False,
                schema_version=None,
                stack_count=0,
                last_refresh_at=None,
                issues=[f"database could not be read: {exc}"],
            )

        issues: list[str] = []
        if schema_version != SCHEMA_VERSION:
            issues.append(f"expected schema version {SCHEMA_VERSION}, found {schema_version}")
        return DatabaseStatus(
            db_path=self.path,
            exists=True,
            initialized=True,
            schema_version=schema_version,
            stack_count=stack_count,
            last_refresh_at=last_refresh_at,
            issues=issues,
        )

    def upsert_stack_snapshot(self, snapshot: StackSnapshot, observed_at: str) -> None:
        compose_file = str(snapshot.compose_file) if snapshot.compose_file else None
        data_json = json.dumps(snapshot.to_dict(), sort_keys=True)
        with connect_state_db(self.path) as connection:
            connection.execute(
                """
                INSERT INTO stacks (
                  hostname,
                  stack_dir,
                  compose_file,
                  has_compose,
                  has_stack_config,
                  scaffold_kind,
                  scaffold_template,
                  profile,
                  docker_network,
                  traefik_url,
                  managed_by_homesrvctl,
                  discovered_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hostname) DO UPDATE SET
                  stack_dir = excluded.stack_dir,
                  compose_file = excluded.compose_file,
                  has_compose = excluded.has_compose,
                  has_stack_config = excluded.has_stack_config,
                  scaffold_kind = excluded.scaffold_kind,
                  scaffold_template = excluded.scaffold_template,
                  profile = excluded.profile,
                  docker_network = excluded.docker_network,
                  traefik_url = excluded.traefik_url,
                  managed_by_homesrvctl = excluded.managed_by_homesrvctl,
                  updated_at = excluded.updated_at
                """,
                (
                    snapshot.hostname,
                    str(snapshot.stack_dir),
                    compose_file,
                    int(snapshot.has_compose),
                    int(snapshot.has_stack_config),
                    snapshot.scaffold_kind,
                    snapshot.scaffold_template,
                    snapshot.profile,
                    snapshot.docker_network,
                    snapshot.traefik_url,
                    int(snapshot.managed_by_homesrvctl),
                    observed_at,
                    observed_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO stack_observations (
                  stack_hostname,
                  observed_at,
                  source,
                  status,
                  detail,
                  data_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.hostname,
                    observed_at,
                    LOCAL_STACK_REFRESH_SOURCE,
                    "observed",
                    "local stack state refreshed",
                    data_json,
                ),
            )

    def add_stack_observation(
        self,
        *,
        stack_hostname: str,
        observed_at: str,
        source: str,
        status: str,
        detail: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        data_json = json.dumps(data, sort_keys=True) if data is not None else None
        with connect_state_db(self.path) as connection:
            connection.execute(
                """
                INSERT INTO stack_observations (
                  stack_hostname,
                  observed_at,
                  source,
                  status,
                  detail,
                  data_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (stack_hostname, observed_at, source, status, detail, data_json),
            )

    def list_stack_observations(
        self,
        *,
        source: str | None = None,
        stack_hostname: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        if not self.status().initialized:
            return []
        sql = "SELECT * FROM stack_observations"
        clauses: list[str] = []
        params: list[object] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if stack_hostname:
            clauses.append("stack_hostname = ?")
            params.append(stack_hostname)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY observed_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def latest_stack_observation(
        self,
        *,
        source: str | None = None,
        stack_hostname: str | None = None,
    ) -> dict[str, object] | None:
        observations = self.list_stack_observations(
            source=source,
            stack_hostname=stack_hostname,
            limit=1,
        )
        return observations[0] if observations else None

    def list_stacks(self) -> list[dict[str, object]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM stacks ORDER BY hostname").fetchall()
        return [dict(row) for row in rows]

    def list_stack_snapshots(self) -> list[StackSnapshot]:
        if not self.status().initialized:
            return []
        return [
            StackSnapshot(
                hostname=str(row["hostname"]),
                stack_dir=Path(str(row["stack_dir"])),
                compose_file=Path(str(row["compose_file"])) if row.get("compose_file") else None,
                has_compose=bool(row["has_compose"]),
                has_stack_config=bool(row["has_stack_config"]),
                scaffold_kind=str(row["scaffold_kind"]) if row.get("scaffold_kind") else None,
                scaffold_template=str(row["scaffold_template"]) if row.get("scaffold_template") else None,
                profile=str(row["profile"]) if row.get("profile") else None,
                docker_network=str(row["docker_network"]) if row.get("docker_network") else None,
                traefik_url=str(row["traefik_url"]) if row.get("traefik_url") else None,
                managed_by_homesrvctl=bool(row["managed_by_homesrvctl"]),
                updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
            )
            for row in self.list_stacks()
        ]

    def stack_count(self) -> int:
        return self.status().stack_count

    def has_cached_stack_data(self) -> bool:
        return self.stack_count() > 0

    def last_stack_refresh_at(self) -> str | None:
        return self.status().last_refresh_at

    def add_event(
        self,
        *,
        created_at: str,
        severity: str,
        source: str,
        message: str,
        target_type: str | None = None,
        target: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        data_json = json.dumps(data, sort_keys=True) if data is not None else None
        with connect_state_db(self.path) as connection:
            connection.execute(
                """
                INSERT INTO events (
                  created_at,
                  severity,
                  source,
                  target_type,
                  target,
                  message,
                  data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (created_at, severity, source, target_type, target, message, data_json),
            )

    def list_recent_events(self, *, source: str | None = None, limit: int = 10) -> list[dict[str, object]]:
        if not self.status().initialized:
            return []
        sql = "SELECT * FROM events"
        params: list[object] = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def latest_event(self, *, source: str | None = None) -> dict[str, object] | None:
        events = self.list_recent_events(source=source, limit=1)
        return events[0] if events else None

    def create_operation(
        self,
        *,
        operation_type: str,
        status: str,
        started_at: str,
        target_type: str | None = None,
        target: str | None = None,
        summary: str | None = None,
        error: str | None = None,
        data: dict[str, object] | None = None,
    ) -> int:
        data_json = json.dumps(data, sort_keys=True) if data is not None else None
        with connect_state_db(self.path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO operations (
                  operation_type,
                  target_type,
                  target,
                  status,
                  started_at,
                  summary,
                  error,
                  data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (operation_type, target_type, target, status, started_at, summary, error, data_json),
            )
            return int(cursor.lastrowid)

    def update_operation(
        self,
        operation_id: int,
        *,
        status: str | None = None,
        finished_at: str | None = None,
        summary: str | None = None,
        error: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        assignments: list[str] = []
        params: list[object] = []
        if status is not None:
            assignments.append("status = ?")
            params.append(status)
        if finished_at is not None:
            assignments.append("finished_at = ?")
            params.append(finished_at)
        if summary is not None:
            assignments.append("summary = ?")
            params.append(summary)
        if error is not None:
            assignments.append("error = ?")
            params.append(error)
        if data is not None:
            assignments.append("data_json = ?")
            params.append(json.dumps(data, sort_keys=True))
        if not assignments:
            return
        params.append(operation_id)
        with connect_state_db(self.path) as connection:
            connection.execute(
                f"UPDATE operations SET {', '.join(assignments)} WHERE id = ?",
                params,
            )

    def finish_operation(
        self,
        operation_id: int,
        *,
        finished_at: str,
        summary: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.update_operation(
            operation_id,
            status="completed",
            finished_at=finished_at,
            summary=summary,
            error="",
            data=data,
        )

    def fail_operation(
        self,
        operation_id: int,
        *,
        finished_at: str,
        error: str,
        summary: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.update_operation(
            operation_id,
            status="failed",
            finished_at=finished_at,
            summary=summary,
            error=error,
            data=data,
        )

    def get_operation(self, operation_id: int) -> dict[str, object] | None:
        if not self.status().initialized:
            return None
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM operations WHERE id = ?",
                (operation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_operations(
        self,
        *,
        status: str | None = None,
        operation_type: str | None = None,
        target: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        if not self.status().initialized:
            return []
        sql = "SELECT * FROM operations"
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if operation_type:
            clauses.append("operation_type = ?")
            params.append(operation_type)
        if target:
            clauses.append("target = ?")
            params.append(target)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def clear_local_stack_state(self) -> None:
        with connect_state_db(self.path) as connection:
            connection.execute(
                "DELETE FROM stack_observations WHERE source = ?",
                (LOCAL_STACK_REFRESH_SOURCE,),
            )
            connection.execute("DELETE FROM stacks")

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None
