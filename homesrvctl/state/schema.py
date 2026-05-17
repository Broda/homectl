from __future__ import annotations

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stacks (
  id INTEGER PRIMARY KEY,
  hostname TEXT UNIQUE NOT NULL,
  stack_dir TEXT NOT NULL,
  compose_file TEXT,
  has_compose INTEGER NOT NULL,
  has_stack_config INTEGER NOT NULL,
  scaffold_kind TEXT,
  scaffold_template TEXT,
  profile TEXT,
  docker_network TEXT,
  traefik_url TEXT,
  managed_by_homesrvctl INTEGER NOT NULL DEFAULT 1,
  discovered_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stack_observations (
  id INTEGER PRIMARY KEY,
  stack_hostname TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  data_json TEXT
);

CREATE TABLE IF NOT EXISTS operations (
  id INTEGER PRIMARY KEY,
  operation_type TEXT NOT NULL,
  target_type TEXT,
  target TEXT,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  summary TEXT,
  error TEXT,
  data_json TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  severity TEXT NOT NULL,
  source TEXT NOT NULL,
  target_type TEXT,
  target TEXT,
  message TEXT NOT NULL,
  data_json TEXT
);
"""
