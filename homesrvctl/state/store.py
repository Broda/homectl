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

    def list_stacks(self) -> list[dict[str, object]]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM stacks ORDER BY hostname").fetchall()
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
