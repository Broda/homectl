from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from homesrvctl.commands import infra_cmd
from homesrvctl.main import app
from homesrvctl.services.infra.mail_workspace import (
    INFRA_EVENT_SOURCE,
    apply_mail_workspace,
    build_mail_workspace_config,
    plan_mail_workspace,
    render_mail_workspace,
)
from homesrvctl.services.infra.opentofu import inspect_tofu
from homesrvctl.shell import CommandResult
from homesrvctl.state.store import StateStore


def _command_result(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(command=command, returncode=returncode, stdout=stdout, stderr=stderr)


def test_infra_status_when_tofu_missing(monkeypatch) -> None:
    monkeypatch.setattr(infra_cmd.shutil, "which", lambda binary: None)

    result = CliRunner().invoke(app, ["infra", "status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "infra_status"
    assert payload["tofu_available"] is False
    assert "OpenTofu binary `tofu` not found" in payload["issues"][0]


def test_infra_status_when_tofu_available(monkeypatch) -> None:
    monkeypatch.setattr(infra_cmd.shutil, "which", lambda binary: "/usr/bin/tofu")
    monkeypatch.setattr(
        infra_cmd,
        "run_command",
        lambda command, cwd=None, quiet=False: _command_result(command, stdout="OpenTofu v1.9.0\n"),
    )

    result = CliRunner().invoke(app, ["infra", "status", "--domain", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tofu_available"] is True
    assert payload["tofu_path"] == "/usr/bin/tofu"
    assert payload["tofu_version"] == "OpenTofu v1.9.0"
    assert payload["domain"] == "example.com"
    assert payload["workspace_exists"] is False


def test_workspace_render_dry_run_does_not_write_files(tmp_path: Path) -> None:
    config = build_mail_workspace_config("example.com", region="us-east-1")
    workspace = tmp_path / "mail" / "example.com"

    result = render_mail_workspace(config, workspace_path=workspace, dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert result.wrote_files is False
    assert not workspace.exists()
    assert {file.path.name for file in result.files} == {
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraform.tfvars.json",
        "README.md",
    }
    assert all("CLOUDFLARE_API_TOKEN" not in file.content for file in result.files if file.path.name != "README.md")


def test_workspace_render_writes_expected_files_without_secrets(tmp_path: Path) -> None:
    config = build_mail_workspace_config(
        "example.com",
        region="us-west-2",
        mail_from_subdomain="bounce",
        dmarc_policy="quarantine",
        rua="postmaster@example.com",
        cloudflare_zone_id="zone_123",
        manage_domain_spf=True,
    )
    workspace = tmp_path / "workspace"

    result = render_mail_workspace(config, workspace_path=workspace)

    assert result.ok is True
    main_tf = (workspace / "main.tf").read_text(encoding="utf-8")
    tfvars = json.loads((workspace / "terraform.tfvars.json").read_text(encoding="utf-8"))
    assert "aws_ses_domain_identity" in main_tf
    assert "aws_ses_domain_dkim" in main_tf
    assert "aws_ses_domain_mail_from" in main_tf
    assert "cloudflare_dns_record" in main_tf
    assert tfvars["domain"] == "example.com"
    assert tfvars["aws_region"] == "us-west-2"
    assert tfvars["mail_from_subdomain"] == "bounce"
    assert tfvars["dmarc_rua"] == "mailto:postmaster@example.com"
    assert tfvars["cloudflare_zone_id"] == "zone_123"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in workspace.iterdir() if path.is_file())
    assert "AKIA" not in combined
    assert "secret-cloudflare-token" not in combined.lower()
    assert "smtp_password" not in combined.lower()
    assert "smtp_username" not in combined.lower()


def test_workspace_render_rejects_invalid_domain_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter):
        build_mail_workspace_config("../example.com", region="us-east-1")


def test_render_existing_workspace_without_force_fails(tmp_path: Path) -> None:
    config = build_mail_workspace_config("example.com", region="us-east-1")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main.tf").write_text("# existing\n", encoding="utf-8")

    result = render_mail_workspace(config, workspace_path=workspace)

    assert result.ok is False
    assert "workspace already exists" in str(result.error)


def test_plan_mail_workspace_no_changes_with_fake_tofu(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=0, stdout="No changes.")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = plan_mail_workspace(
        config,
        workspace_path=tmp_path / "workspace",
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is True
    assert result.has_changes is False
    assert commands[1][1] == "init"
    assert commands[2][1] == "plan"
    assert "-detailed-exitcode" in commands[2]


def test_plan_mail_workspace_changes_with_fake_tofu(tmp_path: Path) -> None:
    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=2, stdout="Plan: 5 to add.")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = plan_mail_workspace(
        config,
        workspace_path=tmp_path / "workspace",
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is True
    assert result.has_changes is True
    assert result.plan_result is not None
    assert result.plan_result.returncode == 2


def test_plan_mail_workspace_out_saves_plan_metadata_with_fake_tofu(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=2, stdout="Plan: 5 to add.")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    workspace = tmp_path / "workspace"
    result = plan_mail_workspace(
        config,
        workspace_path=workspace,
        out=Path("tfplan"),
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is True
    assert result.has_changes is True
    assert result.saved_plan is True
    assert result.plan_file == workspace / "tfplan"
    assert f"-out={workspace / 'tfplan'}" in commands[2]
    payload = result.to_dict()
    assert payload["saved_plan"] is True
    assert payload["plan_file"] == str(workspace / "tfplan")
    assert "sensitive" in str(payload["sensitive_artifact_warning"]).lower()


def test_infra_plan_mail_cli_out_json_includes_saved_plan(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=2, stdout="Plan: 5 to add.")

    monkeypatch.setattr(infra_cmd.shutil, "which", lambda binary: "/usr/bin/tofu")
    monkeypatch.setattr(infra_cmd, "run_command", runner)
    workspace = tmp_path / "workspace"

    result = CliRunner().invoke(
        app,
        [
            "infra",
            "plan",
            "mail",
            "example.com",
            "--region",
            "us-east-1",
            "--workspace",
            str(workspace),
            "--out",
            "tfplan",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "infra_plan"
    assert payload["ok"] is True
    assert payload["has_changes"] is True
    assert payload["saved_plan"] is True
    assert payload["plan_file"] == str(workspace / "tfplan")
    assert f"-out={workspace / 'tfplan'}" in commands[2]


def test_plan_mail_workspace_error_with_fake_tofu(tmp_path: Path) -> None:
    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=1, stderr="provider auth failed")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = plan_mail_workspace(
        config,
        workspace_path=tmp_path / "workspace",
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is False
    assert result.has_changes is None
    assert result.error == "provider auth failed"


def test_plan_mail_workspace_tofu_missing_does_not_render(tmp_path: Path) -> None:
    config = build_mail_workspace_config("example.com", region="us-east-1")
    workspace = tmp_path / "workspace"

    result = plan_mail_workspace(
        config,
        workspace_path=workspace,
        which=lambda binary: None,
        runner=lambda command, cwd=None, quiet=False: _command_result(command),
    )

    assert result.ok is False
    assert result.tofu_available is False
    assert not workspace.exists()
    assert "OpenTofu binary `tofu` not found" in str(result.error)


def test_plan_mail_workspace_out_error_is_not_ok(tmp_path: Path) -> None:
    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        if command[1] == "init":
            return _command_result(command, stdout="init ok")
        return _command_result(command, returncode=1, stderr="plan failed")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = plan_mail_workspace(
        config,
        workspace_path=tmp_path / "workspace",
        out=Path("tfplan"),
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is False
    assert result.saved_plan is False
    assert result.plan_file == tmp_path / "workspace" / "tfplan"
    assert result.error == "plan failed"


def test_apply_mail_requires_existing_plan_file_before_running_tofu(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        return _command_result(command, stdout="OpenTofu v1.9.0\n")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = apply_mail_workspace(
        config,
        workspace_path=tmp_path / "workspace",
        plan_file=Path("missing.tfplan"),
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is False
    assert result.applied is False
    assert "saved plan file does not exist" in str(result.error)
    assert len(commands) == 1
    assert commands[0][-1] == "version"


def test_apply_mail_uses_saved_plan_only_and_records_sanitized_event(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan_file = workspace / "tfplan"
    plan_file.write_text("fake sensitive plan contents", encoding="utf-8")
    db_path = tmp_path / "state.db"

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        return _command_result(command, stdout="apply stdout with secret-looking value")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = apply_mail_workspace(
        config,
        workspace_path=workspace,
        plan_file=Path("tfplan"),
        db_path=db_path,
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is True
    assert result.applied is True
    assert result.event_recorded is True
    assert commands[1][1] == "apply"
    assert "destroy" not in commands[1]
    assert "plan" not in commands[1]
    assert str(plan_file) in commands[1]
    event = StateStore(db_path).latest_event(source=INFRA_EVENT_SOURCE)
    assert event is not None
    event_blob = json.dumps(event, sort_keys=True)
    assert "apply stdout" not in event_blob
    assert "fake sensitive plan contents" not in event_blob
    assert "AKIA" not in event_blob
    assert "cloudflare_api_token" not in event_blob.lower()


def test_apply_mail_failure_records_failure_event(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tfplan").write_text("fake plan", encoding="utf-8")
    db_path = tmp_path / "state.db"

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        return _command_result(command, returncode=1, stderr="apply failed")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = apply_mail_workspace(
        config,
        workspace_path=workspace,
        plan_file=Path("tfplan"),
        db_path=db_path,
        which=lambda binary: "/usr/bin/tofu",
        runner=runner,
    )

    assert result.ok is False
    assert result.applied is False
    assert result.event_recorded is True
    assert result.error == "apply failed"
    event = StateStore(db_path).latest_event(source=INFRA_EVENT_SOURCE)
    assert event is not None
    assert event["severity"] == "warning"


def test_apply_mail_tofu_missing_does_not_apply(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tfplan").write_text("fake plan", encoding="utf-8")

    config = build_mail_workspace_config("example.com", region="us-east-1")
    result = apply_mail_workspace(
        config,
        workspace_path=workspace,
        plan_file=Path("tfplan"),
        which=lambda binary: None,
        runner=lambda command, cwd=None, quiet=False: _command_result(command),
    )

    assert result.ok is False
    assert result.tofu_available is False
    assert result.applied is False
    assert "OpenTofu binary `tofu` not found" in str(result.error)


def test_infra_apply_mail_requires_plan_file_option() -> None:
    result = CliRunner().invoke(app, ["infra", "apply", "mail", "example.com", "--yes"])

    assert result.exit_code == 2
    assert "Applied OpenTofu mail plan" not in result.output


def test_infra_apply_mail_json_requires_yes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tfplan").write_text("fake plan", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "infra",
            "apply",
            "mail",
            "example.com",
            "--region",
            "us-east-1",
            "--workspace",
            str(workspace),
            "--plan-file",
            "tfplan",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["applied"] is False
    assert "requires --yes" in payload["error"]


def test_infra_apply_mail_cli_yes_json_applies_saved_plan(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tfplan").write_text("fake plan", encoding="utf-8")
    db_path = tmp_path / "state.db"

    def runner(command: list[str], cwd=None, quiet=False):  # noqa: ANN001, ANN202
        commands.append(command)
        if command[-1] == "version":
            return _command_result(command, stdout="OpenTofu v1.9.0\n")
        return _command_result(command, stdout="apply ok")

    monkeypatch.setattr(infra_cmd.shutil, "which", lambda binary: "/usr/bin/tofu")
    monkeypatch.setattr(infra_cmd, "run_command", runner)

    result = CliRunner().invoke(
        app,
        [
            "infra",
            "apply",
            "mail",
            "example.com",
            "--region",
            "us-east-1",
            "--workspace",
            str(workspace),
            "--plan-file",
            "tfplan",
            "--db-path",
            str(db_path),
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "infra_apply"
    assert payload["ok"] is True
    assert payload["applied"] is True
    assert payload["event_recorded"] is True
    assert payload["plan_file"] == str(workspace / "tfplan")
    assert commands[1][1] == "apply"
    assert str(workspace / "tfplan") in commands[1]


def test_infra_render_mail_cli_json_dry_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = CliRunner().invoke(
        app,
        [
            "infra",
            "render",
            "mail",
            "example.com",
            "--region",
            "us-east-1",
            "--workspace",
            str(workspace),
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1"
    assert payload["action"] == "infra_render"
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert not workspace.exists()


def test_inspect_tofu_reports_version_with_fake_runner() -> None:
    status = inspect_tofu(
        which=lambda binary: "/usr/bin/tofu",
        runner=lambda command, cwd=None, quiet=False: _command_result(command, stdout="OpenTofu v1.9.0\n"),
    )

    assert status.available is True
    assert status.version == "OpenTofu v1.9.0"
