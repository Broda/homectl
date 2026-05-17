from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from homesrvctl.commands import infra_cmd
from homesrvctl.main import app
from homesrvctl.services.infra.mail_workspace import (
    build_mail_workspace_config,
    plan_mail_workspace,
    render_mail_workspace,
)
from homesrvctl.services.infra.opentofu import inspect_tofu
from homesrvctl.shell import CommandResult


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
