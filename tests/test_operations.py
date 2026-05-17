from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from homesrvctl.main import app
from homesrvctl.services.operations import get_operation, list_operations
from homesrvctl.state.store import StateStore


def test_state_store_operation_helpers_create_finish_fail_and_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize("2026-05-17T00:00:00Z")
    first_id = store.create_operation(
        operation_type="infra.plan.mail",
        target_type="domain",
        target="example.com",
        status="running",
        started_at="2026-05-17T00:00:01Z",
        summary="planning",
        data={"workspace_path": "/tmp/workspace"},
    )
    second_id = store.create_operation(
        operation_type="infra.apply.mail",
        target_type="domain",
        target="example.net",
        status="running",
        started_at="2026-05-17T00:00:02Z",
        summary="applying",
    )

    store.finish_operation(
        first_id,
        finished_at="2026-05-17T00:00:03Z",
        summary="planned",
        data={"has_changes": True},
    )
    store.fail_operation(
        second_id,
        finished_at="2026-05-17T00:00:04Z",
        summary="apply failed",
        error="tofu failed",
        data={"applied": False},
    )

    newest_first = store.list_operations(limit=10)
    assert [row["id"] for row in newest_first] == [second_id, first_id]
    failed = store.list_operations(status="failed", limit=10)
    assert [row["id"] for row in failed] == [second_id]
    plan = store.get_operation(first_id)
    assert plan is not None
    assert plan["status"] == "completed"

    decoded = get_operation(db_path=db_path, operation_id=first_id)
    assert decoded.ok is True
    assert decoded.operation is not None
    assert decoded.operation.data == {"has_changes": True}


def test_operations_list_missing_db_json_reports_issue(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"

    result = CliRunner().invoke(
        app,
        ["operations", "list", "--db-path", str(db_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "operations_list"
    assert payload["ok"] is False
    assert payload["operations"] == []
    assert "database does not exist" in payload["issues"][0]


def test_operations_list_initialized_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    StateStore(db_path).initialize("2026-05-17T00:00:00Z")

    result = CliRunner().invoke(
        app,
        ["operations", "list", "--db-path", str(db_path), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["operations"] == []


def test_operations_list_and_show_populated_db(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize("2026-05-17T00:00:00Z")
    operation_id = store.create_operation(
        operation_type="observe.run",
        target_type="observer",
        target="selected",
        status="completed",
        started_at="2026-05-17T00:00:01Z",
        summary="observers complete",
        data={"observers": ["stack-runtime"]},
    )

    list_result = CliRunner().invoke(
        app,
        ["operations", "list", "--db-path", str(db_path), "--type", "observe.run", "--json"],
    )
    assert list_result.exit_code == 0, list_result.output
    list_payload = json.loads(list_result.output)
    assert list_payload["count"] == 1
    assert list_payload["operations"][0]["id"] == operation_id
    assert list_payload["operations"][0]["data"] == {"observers": ["stack-runtime"]}

    show_result = CliRunner().invoke(
        app,
        ["operations", "show", str(operation_id), "--db-path", str(db_path), "--json"],
    )
    assert show_result.exit_code == 0, show_result.output
    show_payload = json.loads(show_result.output)
    assert show_payload["action"] == "operations_show"
    assert show_payload["operation"]["id"] == operation_id
    assert show_payload["operation"]["summary"] == "observers complete"


def test_operations_show_missing_operation_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    StateStore(db_path).initialize("2026-05-17T00:00:00Z")

    result = CliRunner().invoke(
        app,
        ["operations", "show", "999", "--db-path", str(db_path), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["operation"] is None
    assert "operation not found" in payload["error"]


def test_operations_service_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    store.initialize("2026-05-17T00:00:00Z")
    store.create_operation(
        operation_type="infra.plan.mail",
        target_type="domain",
        target="example.com",
        status="completed",
        started_at="2026-05-17T00:00:01Z",
    )
    store.create_operation(
        operation_type="infra.apply.mail",
        target_type="domain",
        target="example.net",
        status="failed",
        started_at="2026-05-17T00:00:02Z",
    )

    result = list_operations(
        db_path=db_path,
        status="failed",
        operation_type="infra.apply.mail",
        target="example.net",
    )

    assert result.ok is True
    assert result.count == 1
    assert result.operations[0].operation_type == "infra.apply.mail"
