from __future__ import annotations

import os
import sqlite3
from pathlib import Path


STATE_DB_ENV = "HOMESRVCTL_STATE_DB_PATH"


def default_state_db_path() -> Path:
    override = os.environ.get(STATE_DB_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "homesrvctl" / "homesrvctl.db"


def connect_state_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
