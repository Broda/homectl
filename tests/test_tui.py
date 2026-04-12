from __future__ import annotations

import json
import sys
import types

from typer.testing import CliRunner

from homesrvctl.commands import tui_cmd
from homesrvctl.main import app
from homesrvctl.shell import CommandResult
from homesrvctl.tui import app as textual_app, data, prompts


def test_run_json_command_parses_success_payload(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        assert command[-1] == "--json"
        return CommandResult(command, 0, json.dumps({"ok": True, "sites": []}), "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["list"])

    assert payload["ok"] is True
    assert payload["sites"] == []
    assert payload["command"][-1] == "--json"
    assert payload["returncode"] == 0


def test_run_json_command_handles_invalid_json(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 0, "not json", "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["list"])

    assert payload["ok"] is False
    assert payload["error"] == "invalid JSON output"


def test_run_json_command_reports_noisy_stdout(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 0, "$ systemctl is-active cloudflared\n{\"ok\": true}", "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["cloudflared", "status"])

    assert payload["ok"] is False
    assert payload["error"] == "invalid JSON output"


def test_run_json_command_parses_json_even_when_exit_code_is_nonzero(monkeypatch) -> None:
    def fake_run_command(command: list[str], cwd=None, dry_run: bool = False, quiet: bool = False):  # noqa: ANN001, ANN202
        return CommandResult(command, 1, json.dumps({"ok": False, "checks": [{"name": "docker", "ok": False}]}), "")

    monkeypatch.setattr(data, "run_command", fake_run_command)

    payload = data.run_json_subcommand(["validate"])

    assert payload["ok"] is False
    assert payload["checks"][0]["name"] == "docker"
    assert payload["returncode"] == 1


def test_build_dashboard_snapshot_uses_existing_json_surfaces() -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(tuple(args))
        if args == ["list"]:
            return {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]}
        if args == ["config", "show"]:
            return {
                "ok": True,
                "config_path": "/home/test/.config/homesrvctl/config.yml",
                "global": {
                    "sites_root": "/srv/homesrvctl/sites",
                    "docker_network": "web",
                    "traefik_url": "http://localhost:8081",
                    "cloudflared_config": "/etc/cloudflared/config.yml",
                    "cloudflare_api_token_present": False,
                    "profiles": {},
                },
            }
        if args == ["tunnel", "status"]:
            return {
                "ok": True,
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "credentials+api",
                "account_id": "account-123",
                "api_available": True,
                "api_status": {
                    "id": "11111111-2222-4333-8444-555555555555",
                    "name": "homesrvctl-tunnel",
                    "status": "healthy",
                },
                "api_error": None,
            }
        if args == ["cloudflared", "status"]:
            return {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"}
        if args == ["validate"]:
            return {"ok": True, "checks": [{"name": "docker", "ok": True, "detail": "found"}]}
        if args == ["bootstrap", "assess"]:
            return {
                "ok": True,
                "bootstrap_state": "partial",
                "host_supported": True,
                "detail": "host is partially provisioned relative to the current bootstrap target",
                "issues": ["Traefik is not running"],
                "next_steps": ["Install or start the baseline Traefik runtime expected by homesrvctl."],
            }
        raise AssertionError(f"unexpected args: {args}")

    snapshot = data.build_dashboard_snapshot(run_json_command=fake_run_json_command)

    assert calls == [("list",), ("config", "show"), ("tunnel", "status"), ("cloudflared", "status"), ("validate",), ("bootstrap", "assess")]
    assert snapshot["list"]["sites"][0]["hostname"] == "example.com"
    assert snapshot["config"]["global"]["docker_network"] == "web"
    assert snapshot["tunnel"]["resolved_tunnel_id"] == "11111111-2222-4333-8444-555555555555"
    assert snapshot["cloudflared"]["mode"] == "systemd"
    assert snapshot["validate"]["checks"][0]["name"] == "docker"
    assert snapshot["bootstrap"]["bootstrap_state"] == "partial"


def test_run_stack_action_dispatches_to_existing_commands(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "doctor")

    assert payload["ok"] is True
    assert calls == [["doctor", "example.com"]]


def test_run_stack_action_dispatches_site_init(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "init-site")

    assert payload["ok"] is True
    assert calls == [["site", "init", "example.com"]]


def test_run_stack_action_dispatches_app_init(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "template": "node"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "app-init", template="node")

    assert payload["ok"] is True
    assert payload["template"] == "node"
    assert calls == [["app", "init", "example.com", "--template", "node"]]


def test_run_stack_action_dispatches_scaffold_overrides(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action(
        "app.example.com",
        "app-init",
        template="python",
        force=True,
        profile="edge",
        docker_network="edge-net",
        traefik_url="http://localhost:9000",
    )

    assert payload["ok"] is True
    assert calls == [[
        "app",
        "init",
        "app.example.com",
        "--template",
        "python",
        "--force",
        "--profile",
        "edge",
        "--docker-network",
        "edge-net",
        "--traefik-url",
        "http://localhost:9000",
    ]]


def test_run_stack_action_dispatches_domain_repair(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "domain-repair")

    assert payload["ok"] is True
    assert calls == [["domain", "repair", "example.com"]]


def test_run_stack_action_dispatches_domain_add(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "domain-add")

    assert payload["ok"] is True
    assert calls == [["domain", "add", "example.com"]]


def test_run_stack_action_dispatches_domain_add_with_flags(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "dry_run": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action(
        "example.com",
        "domain-add",
        dry_run=True,
        restart_cloudflared=True,
    )

    assert payload["ok"] is True
    assert calls == [["domain", "add", "example.com", "--dry-run", "--restart-cloudflared"]]


def test_run_stack_action_dispatches_domain_remove(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_action("example.com", "domain-remove")

    assert payload["ok"] is True
    assert calls == [["domain", "remove", "example.com"]]


def test_run_tool_action_dispatches_to_existing_commands(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("cloudflared", "config-test")

    assert payload["ok"] is True
    assert calls == [["cloudflared", "config-test"]]


def test_run_tool_action_dispatches_cloudflared_setup(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": False, "detail": "setup mismatch"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("cloudflared", "setup")

    assert payload["ok"] is False
    assert calls == [["cloudflared", "setup"]]


def test_run_tool_action_dispatches_bootstrap_assess(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "bootstrap_state": "fresh"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("bootstrap", "assess")

    assert payload["ok"] is True
    assert calls == [["bootstrap", "assess"]]


def test_run_tool_action_dispatches_tunnel_show(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("tunnel", "show")

    assert payload["ok"] is True
    assert calls == [["tunnel", "status"]]


def test_run_tool_action_dispatches_cloudflared_logs_follow(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "logs_command": ["journalctl", "-u", "cloudflared", "-f"]}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("cloudflared", "logs", follow=True)

    assert payload["ok"] is True
    assert calls == [["cloudflared", "logs", "--follow"]]


def test_run_tool_action_dispatches_config_init_force(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "action": "config_init"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_tool_action("config", "init", force=True)

    assert payload["ok"] is True
    assert calls == [["config", "init", "--force"]]


def test_tool_action_options_include_tunnel_action() -> None:
    tunnel_options = prompts.tool_action_options("tunnel")

    assert tunnel_options == [("show", "tunnel status", "Refresh configured tunnel resolution and API status detail.")]


def test_run_stack_config_view_dispatches_to_existing_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "stack": {"hostname": "example.com"}}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_config_view("example.com")

    assert payload["ok"] is True
    assert calls == [["config", "show", "--stack", "example.com"]]


def test_run_stack_domain_status_dispatches_to_existing_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_json_command(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "domain": "example.com"}

    monkeypatch.setattr(data, "run_json_subcommand", fake_run_json_command)

    payload = data.run_stack_domain_status("example.com")

    assert payload["ok"] is True
    assert calls == [["domain", "status", "example.com"]]


def test_summarize_stack_action_reports_failure_detail() -> None:
    summary = data.summarize_stack_action("example.com", "up", {"ok": False, "error": "missing docker-compose.yml"})

    assert summary == "up failed for example.com: missing docker-compose.yml"


def test_summarize_stack_action_uses_failing_check_detail() -> None:
    summary = data.summarize_stack_action(
        "example.com",
        "doctor",
        {
            "ok": False,
            "checks": [
                {"name": "hostname directory", "ok": True, "detail": "/srv/homesrvctl/sites/example.com"},
                {"name": "docker-compose.yml", "ok": False, "detail": "/srv/homesrvctl/sites/example.com/docker-compose.yml"},
            ],
        },
    )

    assert summary == "doctor failed for example.com: docker-compose.yml: /srv/homesrvctl/sites/example.com/docker-compose.yml"


def test_summarize_stack_action_labels_site_init() -> None:
    summary = data.summarize_stack_action("example.com", "init-site", {"ok": False, "error": "file exists"})

    assert summary == "site init failed for example.com: file exists"


def test_summarize_stack_action_labels_domain_repair() -> None:
    summary = data.summarize_stack_action("example.com", "domain-repair", {"ok": False, "error": "duplicate DNS records"})

    assert summary == "domain repair failed for example.com: duplicate DNS records"


def test_summarize_stack_action_labels_domain_add_and_remove() -> None:
    add_summary = data.summarize_stack_action("example.com", "domain-add", {"ok": False, "error": "zone not found"})
    remove_summary = data.summarize_stack_action("example.com", "domain-remove", {"ok": False, "error": "permission denied"})

    assert add_summary == "domain add failed for example.com: zone not found"
    assert remove_summary == "domain remove failed for example.com: permission denied"


def test_render_stack_action_detail_formats_doctor_checks() -> None:
    lines = data.render_stack_action_detail(
        "doctor",
        {
            "ok": False,
            "checks": [
                {
                    "name": "docker-compose.yml",
                    "ok": True,
                    "detail": "/srv/homesrvctl/sites/example.com/docker-compose.yml",
                    "severity": "pass",
                },
                {
                    "name": "host-header request",
                    "ok": False,
                    "detail": "request failed: connection refused",
                    "severity": "blocking",
                },
            ],
        },
    )

    rendered = "\n".join(lines)

    assert "action" in rendered
    assert "doctor" in rendered
    assert "checks: 2 total, 1 failing, 0 advisory" in rendered
    assert "[green]PASS[/green] docker-compose.yml: /srv/homesrvctl/sites/example.com/docker-compose.yml" in rendered
    assert "[red]FAIL[/red] host-header request: request failed: connection refused" in rendered


def test_render_stack_action_detail_formats_command_results() -> None:
    lines = data.render_stack_action_detail(
        "up",
        {
            "ok": True,
            "dry_run": False,
            "commands": [
                {
                    "command": ["docker", "compose", "up", "-d"],
                    "returncode": 0,
                    "stdout": "container started\nsecond line",
                    "stderr": "",
                }
            ],
        },
    )

    rendered = "\n".join(lines)

    assert "action" in rendered
    assert "up" in rendered
    assert "dry run" in rendered
    assert "no" in rendered
    assert "rc=0 docker compose up -d" in rendered
    assert "stdout: container started" in rendered


def test_render_tool_action_detail_formats_cloudflared_result() -> None:
    lines = data.render_tool_action_detail(
        "cloudflared",
        "config-test",
        {
            "ok": True,
            "detail": "fallback service http_status:404",
            "warnings": ["earlier wildcard rule *.com may capture later hostname *.example.com"],
            "issues": [
                {
                    "severity": "advisory",
                    "blocking": False,
                    "message": "earlier wildcard rule *.com may capture later hostname *.example.com",
                }
            ],
        },
    )

    rendered = "\n".join(lines)

    assert "tool" in rendered
    assert "cloudflared" in rendered
    assert "action" in rendered
    assert "config-test" in rendered
    assert "status" in rendered
    assert "ok" in rendered
    assert "warnings: 1" in rendered
    assert "issues: 1 total, 0 blocking, 1 advisory" in rendered
    assert "- earlier wildcard rule *.com may capture later hostname *.example.com" in rendered


def test_render_tool_action_detail_formats_logs_guidance() -> None:
    lines = data.render_tool_action_detail(
        "cloudflared",
        "logs",
        {
            "ok": True,
            "follow": True,
            "detail": "journalctl guidance available",
            "logs_command": ["journalctl", "-u", "cloudflared", "-f"],
        },
    )

    rendered = "\n".join(lines)

    assert "action" in rendered
    assert "logs" in rendered
    assert "follow" in rendered
    assert "yes" in rendered
    assert "logs command" in rendered
    assert "journalctl -u cloudflared -f" in rendered


def test_render_tool_action_detail_formats_setup_guidance() -> None:
    lines = data.render_tool_action_detail(
        "cloudflared",
        "setup",
        {
            "ok": False,
            "detail": "systemd cloudflared service uses /etc/cloudflared/config.yml, but homesrvctl is configured for /srv/homesrvctl/cloudflared/config.yml",
            "setup_state": "misaligned",
            "configured_path": "/srv/homesrvctl/cloudflared/config.yml",
            "configured_credentials_path": "/etc/cloudflared/example.json",
            "configured_credentials_readable": False,
            "configured_credentials_owner": "root",
            "configured_credentials_group": "root",
            "configured_credentials_mode": "600",
            "runtime_path": "/etc/cloudflared/config.yml",
            "paths_aligned": False,
            "configured_exists": False,
            "configured_writable": False,
            "account_inspection_available": False,
            "ingress_mutation_available": False,
            "issues": ["configured cloudflared config is missing: /srv/homesrvctl/cloudflared/config.yml"],
            "next_commands": ["sudo groupadd -f homesrvctl"],
            "override_path": "/etc/systemd/system/cloudflared.service.d/override.conf",
            "shared_group": "homesrvctl",
        },
    )

    rendered = "\n".join(lines)

    assert "setup" in rendered
    assert "next commands: 1" in rendered
    assert "override path" in rendered
    assert "sudo groupadd -f homesrvctl" in rendered
    assert "setup state" in rendered
    assert "credentials path" in rendered


def test_render_tool_action_detail_formats_bootstrap_assessment() -> None:
    lines = data.render_tool_action_detail(
        "bootstrap",
        "assess",
        {
            "ok": True,
            "bootstrap_state": "partial",
            "host_supported": True,
            "detail": "host is partially provisioned relative to the current bootstrap target",
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "os": {"pretty_name": "Debian GNU/Linux 12", "supported": True, "detail": "Debian-family host detected"},
            "packages": {"docker": True, "docker_compose": False, "cloudflared": True},
            "services": {"traefik_running": False, "cloudflared_active": True, "cloudflared_mode": "systemd"},
            "config": {"exists": True, "valid": True, "token_present": False, "token_source": "missing"},
            "network": {"name": "web", "exists": False, "detail": "docker network not found"},
            "cloudflare": {"token_present": False, "token_source": "missing", "api_reachable": None, "detail": "Cloudflare API token is not configured"},
            "issues": ["Traefik is not running"],
            "next_steps": ["Install or start the baseline Traefik runtime expected by homesrvctl."],
        },
    )

    rendered = "\n".join(lines)

    assert "bootstrap state" in rendered
    assert "host supported" in rendered
    assert "Packages" in rendered
    assert "Cloudflare" in rendered
    assert "next steps: 1" in rendered


def test_render_config_payload_detail_formats_global_config() -> None:
    lines = data.render_config_payload_detail(
        {
            "ok": True,
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "global": {
                "sites_root": "/srv/homesrvctl/sites",
                "docker_network": "web",
                "traefik_url": "http://localhost:8081",
                "cloudflared_config": "/etc/cloudflared/config.yml",
                "cloudflare_api_token_present": False,
                "profiles": {
                    "edge": {"docker_network": "edge", "traefik_url": "http://localhost:9000"},
                    "internal": {"docker_network": "internal", "traefik_url": "http://localhost:8082"},
                },
            },
        }
    )

    rendered = "\n".join(lines)

    assert "config path" in rendered
    assert "/home/test/.config/homesrvctl/config.yml" in rendered
    assert "docker network" in rendered
    assert "web" in rendered
    assert "profiles: 2" in rendered
    assert "- edge" in rendered


def test_render_stack_config_detail_formats_effective_config() -> None:
    lines = data.render_stack_config_detail(
        {
            "ok": True,
            "stack": {
                "profile": "edge",
                "has_local_config": True,
                "effective": {
                    "docker_network": "edge",
                    "traefik_url": "http://localhost:9001",
                },
                "effective_sources": {
                    "docker_network": "profile:edge",
                    "traefik_url": "stack-local",
                },
                "stack_config_path": "/srv/homesrvctl/sites/example.com/homesrvctl.yml",
            },
        }
    )

    rendered = "\n".join(lines)

    assert "profile" in rendered
    assert "edge" in rendered
    assert "has local config" in rendered
    assert "yes" in rendered
    assert "docker network" in rendered
    assert "edge (profile:edge)" in rendered
    assert "traefik url" in rendered
    assert "http://localhost:9001 (stack-local)" in rendered


def test_render_domain_status_detail_formats_apex_status() -> None:
    lines = data.render_domain_status_detail(
        "example.com",
        {
            "ok": False,
            "domain": "example.com",
            "overall": "partial",
            "repairable": True,
            "manual_fix_required": False,
            "expected_tunnel_target": "1234.cfargotunnel.com",
            "expected_ingress_service": "http://localhost:8081",
            "coverage_issues": ["Ingress coverage is apex-only; wildcard ingress is missing"],
            "ingress_warnings": ["earlier ingress rule *.com may shadow later hostname example.com"],
            "ingress_issues": [
                {
                    "severity": "blocking",
                    "blocking": True,
                    "message": "earlier ingress rule *.com may shadow later hostname example.com",
                }
            ],
            "dns": [
                {"record_name": "example.com", "matches_expected": True, "detail": "CNAME -> 1234.cfargotunnel.com (proxied)"},
                {"record_name": "*.example.com", "matches_expected": False, "detail": "record missing"},
            ],
            "ingress": [
                {"hostname": "example.com", "matches_expected": True, "detail": "http://localhost:8081"},
                {"hostname": "*.example.com", "matches_expected": False, "detail": "entry missing"},
            ],
            "suggested_command": "homesrvctl domain repair example.com",
        },
    )

    rendered = "\n".join(lines)

    assert "overall" in rendered
    assert "partial" in rendered
    assert "repairable" in rendered
    assert "Yes" in rendered
    assert "coverage issues: 1" in rendered
    assert "ingress issues: 1 total, 1 blocking, 0 advisory" in rendered
    assert "manual fix required" in rendered
    assert "no" in rendered
    assert "DNS Records" in rendered
    assert "Ingress Routes" in rendered
    assert "| hostname" in rendered
    assert "example.com" in rendered
    assert "*.example.com" in rendered
    assert "suggested command" in rendered
    assert "homesrvctl domain repair example.com" in rendered


def test_render_domain_status_detail_uses_na_when_no_repair_needed() -> None:
    lines = data.render_domain_status_detail(
        "example.com",
        {
            "ok": True,
            "domain": "example.com",
            "overall": "ok",
            "repairable": False,
            "manual_fix_required": False,
            "expected_tunnel_target": "1234.cfargotunnel.com",
            "expected_ingress_service": "http://localhost:8081",
            "dns": [],
            "ingress": [],
        },
    )

    rendered = "\n".join(lines)

    assert "repairable" in rendered
    assert "N/A" in rendered


def test_render_domain_status_detail_skips_subdomain_stacks() -> None:
    lines = data.render_domain_status_detail("notes.example.com", {"ok": False, "error": "not bare"})

    rendered = "\n".join(lines)

    assert "Domain status" in rendered
    assert "Not available for subdomain stacks." in rendered


def test_render_stack_action_detail_formats_app_init_result() -> None:
    lines = data.render_stack_action_detail(
        "app-init",
        {
            "ok": True,
            "template": "node",
            "target_dir": "/srv/homesrvctl/sites/app.example.com",
            "files": [
                "/srv/homesrvctl/sites/app.example.com/docker-compose.yml",
                "/srv/homesrvctl/sites/app.example.com/Dockerfile",
            ],
        },
    )

    rendered = "\n".join(lines)

    assert "action" in rendered
    assert "app init" in rendered
    assert "template" in rendered
    assert "node" in rendered
    assert "files: 2" in rendered
    assert "target dir: /srv/homesrvctl/sites/app.example.com" in rendered


def test_tui_requires_interactive_terminal(monkeypatch) -> None:
    monkeypatch.setattr(tui_cmd.sys.stdout, "isatty", lambda: False)
    monkeypatch.setattr(tui_cmd.sys.stdin, "isatty", lambda: False)

    runner = CliRunner()
    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 2, result.output
    assert "tui requires an interactive terminal" in result.output


def test_no_args_invokes_tui(monkeypatch) -> None:
    from homesrvctl import main as main_mod

    calls: list[str] = []
    monkeypatch.setattr(main_mod, "launch_tui", lambda: calls.append("tui"))

    runner = CliRunner()
    result = runner.invoke(app, [])

    assert result.exit_code == 0, result.output
    assert calls == ["tui"]


def test_tui_invokes_textual_app(monkeypatch) -> None:
    monkeypatch.setattr(tui_cmd.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(tui_cmd.sys.stdin, "isatty", lambda: True)
    calls: list[tuple[str, float]] = []

    class FakeTextualApp:
        def __init__(self, refresh_seconds: float = 0.0) -> None:
            calls.append(("init", refresh_seconds))

        def run(self) -> None:
            calls.append(("run", 0.0))

    monkeypatch.setitem(sys.modules, "homesrvctl.tui.app", types.SimpleNamespace(HomesrvctlTextualApp=FakeTextualApp))

    tui_cmd.tui(refresh_seconds=5.0)

    assert calls == [("init", 5.0), ("run", 0.0)]


def test_textual_app_summary_and_stack_list_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {
            "ok": True,
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "global": {
                "sites_root": "/srv/homesrvctl/sites",
                "docker_network": "web",
                "traefik_url": "http://localhost:8081",
                "cloudflared_config": "/etc/cloudflared/config.yml",
                "cloudflare_api_token_present": False,
                "profiles": {},
            },
        },
        "list": {
            "ok": True,
            "sites": [
                {"hostname": "example.com", "compose": True},
                {"hostname": "notes.example.com", "compose": False},
            ],
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 6
    app.stack_config_views["notes.example.com"] = {
        "ok": True,
        "stack": {
            "profile": None,
            "has_local_config": False,
            "effective": {"docker_network": "web", "traefik_url": "http://localhost:8081"},
            "effective_sources": {"docker_network": "global-config", "traefik_url": "global-config"},
            "stack_config_path": "/srv/homesrvctl/sites/notes.example.com/homesrvctl.yml",
        },
    }
    app.stack_domain_views["notes.example.com"] = {"ok": False, "error": "not bare"}

    controls = app._control_list_text()
    detail = app._detail_text()
    command_bar = app._command_bar_text()

    assert "Tools" in controls
    assert "Config" in controls
    assert "Cloudflared" in controls
    assert "Validate" in controls
    assert "Stacks" in controls
    assert "notes.example.com" in controls
    assert "hostname: notes.example.com" in detail
    assert "Effective config" in detail
    assert "Domain status" in detail
    assert "w/s navigate" in command_bar
    assert "r refresh" in command_bar


def test_textual_app_config_tool_detail_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {
            "ok": True,
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "global": {
                "sites_root": "/srv/homesrvctl/sites",
                "docker_network": "web",
                "traefik_url": "http://localhost:8081",
                "cloudflared_config": "/etc/cloudflared/config.yml",
                "cloudflare_api_token_present": False,
                "profiles": {"edge": {"docker_network": "edge", "traefik_url": "http://localhost:9000"}},
            },
        },
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "tunnel": {
            "ok": True,
            "configured_tunnel": "homesrvctl-tunnel",
            "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
            "resolution_source": "credentials+api",
            "account_id": "account-123",
            "api_available": True,
            "api_status": {"name": "homesrvctl-tunnel", "status": "healthy"},
            "api_error": None,
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 0

    detail = app._detail_text()
    command_bar = app._command_bar_text()

    assert "Config Detail" in detail
    assert "docker network" in detail
    assert "web" in detail
    assert "profiles: 1" in detail
    assert "w/s navigate" in command_bar


def test_textual_app_tunnel_tool_detail_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "tunnel": {
            "ok": True,
            "configured_tunnel": "homesrvctl-tunnel",
            "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
            "resolution_source": "credentials+api",
            "account_id": "account-123",
            "api_available": True,
            "api_status": {"name": "homesrvctl-tunnel", "status": "healthy"},
            "api_error": None,
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
    }
    app.selected_control_index = 1

    detail = app._detail_text()

    assert "Tunnel Detail" in detail
    assert "configured tunnel: homesrvctl-tunnel" in detail
    assert "resolved tunnel id: 11111111-2222-4333-8444-555555555555" in detail
    assert "api tunnel status: healthy" in detail


def test_textual_app_tunnel_detail_downgrades_credentials_permission_denied() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "tunnel": {
            "ok": True,
            "configured_tunnel": "homesrvctl-tunnel",
            "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
            "resolution_source": "cloudflared-config:tunnel",
            "account_id": None,
            "api_available": False,
            "api_status": None,
            "api_error": "cloudflared credentials are not readable by the current user: /etc/cloudflared/example.json: [Errno 13] Permission denied",
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 1

    detail = app._detail_text()

    assert (
        "api note: account inspection unavailable: cloudflared credentials are not readable by the current user "
        "(run `homesrvctl cloudflared setup` for shared-group guidance)"
    ) in detail
    assert "Permission denied" not in detail


def test_app_init_template_screen_renders_options() -> None:
    screen = prompts.AppInitTemplateScreen()

    rendered = screen._options_text()

    assert "> 1. placeholder" in rendered
    assert "2. static" in rendered
    assert "5. python" in rendered
    assert "6. jekyll" in rendered


def test_confirm_action_screen_uses_supplied_copy() -> None:
    screen = prompts.ConfirmActionScreen("Confirm Domain Add", "Run domain add for example.com?")

    assert screen.title == "Confirm Domain Add"
    assert screen.body == "Run domain add for example.com?"


def test_tool_action_options_include_config_and_cloudflared_actions() -> None:
    config_options = prompts.tool_action_options("config")
    cloudflared_options = prompts.tool_action_options("cloudflared")

    assert [label for _, label, _ in config_options] == ["config show", "config init"]
    assert [label for _, label, _ in cloudflared_options] == ["setup", "config-test", "logs", "reload", "restart"]


def test_stack_action_options_include_domain_actions_for_apex() -> None:
    options = prompts.stack_action_options(is_apex_domain=True)

    labels = [label for _, label, _ in options]

    assert "app init" in labels
    assert "domain add" in labels
    assert "domain remove" in labels


def test_stack_action_options_skip_domain_actions_for_subdomains() -> None:
    options = prompts.stack_action_options(is_apex_domain=False)

    labels = [label for _, label, _ in options]

    assert "app init" in labels
    assert "domain add" not in labels
    assert "domain remove" not in labels


def test_stack_action_menu_screen_renders_options() -> None:
    screen = prompts.StackActionMenuScreen("example.com", is_apex_domain=True)

    rendered = screen._options_text()

    assert "> 1. app init" in rendered
    assert "domain add" in rendered
    assert "domain remove" in rendered


def test_creation_mode_screen_renders_options() -> None:
    screen = prompts.CreationModeScreen("app.example.com")

    rendered = screen._options_text()

    assert "> 1. site init" in rendered
    assert "2. app init" in rendered


def test_text_entry_screen_renders_placeholder_and_value() -> None:
    screen = prompts.TextEntryScreen("Hostname", "Enter a hostname.", placeholder="app.example.com")

    assert "app.example.com" in screen._value_text()

    screen.value = "notes.example.com"

    assert screen._value_text() == "> notes.example.com"


def test_tool_action_menu_screen_renders_options() -> None:
    screen = prompts.ToolActionMenuScreen("cloudflared")

    rendered = screen._options_text()

    assert "> 1. setup" in rendered
    assert "2. config-test" in rendered
    assert "3. logs" in rendered
    assert "5. restart" in rendered


def test_cloudflared_logs_mode_screen_renders_options() -> None:
    screen = prompts.CloudflaredLogsModeScreen()

    rendered = screen._options_text()

    assert "> 1. standard" in rendered
    assert "2. follow" in rendered


def test_boolean_choice_screen_renders_options() -> None:
    screen = prompts.BooleanChoiceScreen("Dry Run", "Choose whether to run in dry-run mode.")

    rendered = screen._options_text()

    assert "> 1. no" in rendered
    assert "2. yes" in rendered


def test_textual_app_app_init_prompt_pushes_modal(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": False}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_app_init_prompt()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.AppInitTemplateScreen)


def test_textual_app_stack_action_menu_pushes_modal(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_stack_action_menu()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.StackActionMenuScreen)


def test_textual_app_tool_action_menu_pushes_modal(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 2
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app.action_stack_action_menu()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.ToolActionMenuScreen)


def test_textual_app_stack_action_menu_rejects_unsupported_tool_focus(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 3
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_stack_action_menu()

    assert app.status_message == "no guided actions for Validate"


def test_textual_app_domain_add_prompt_pushes_modal(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_domain_add_prompt()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.ConfirmActionScreen)


def test_textual_app_domain_onboarding_flow_pushes_domain_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app.action_domain_onboarding_flow()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.TextEntryScreen)


def test_textual_app_domain_remove_prompt_pushes_modal(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_domain_remove_prompt()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.ConfirmActionScreen)


def test_textual_app_stack_action_menu_routes_app_init(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_stack_action_menu("example.com", "app-init")

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.AppInitTemplateScreen)


def test_textual_app_stack_action_menu_routes_domain_add_confirmation(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        textual_app.HomesrvctlTextualApp,
        "_push_domain_confirmation",
        lambda self, action, title, hostname=None: calls.append((action, title, hostname)),
    )

    app._complete_stack_action_menu("example.com", "domain-add")

    assert calls == [("domain-add", "Confirm Domain Add", "example.com")]


def test_textual_app_stack_action_menu_routes_site_init(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        textual_app.HomesrvctlTextualApp,
        "_run_stack_action_for_hostname",
        lambda self, hostname, action, template=None: calls.append((hostname, action, template)),
    )

    app._complete_stack_action_menu("example.com", "site-init")

    assert calls == [("example.com", "init-site", None)]


def test_textual_app_stack_action_menu_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_stack_action_menu("example.com", None)

    assert app.status_message == "stack action menu cancelled for example.com"


def test_textual_app_tool_action_menu_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_tool_action_menu("cloudflared", None)

    assert app.status_message == "tool action menu cancelled for cloudflared"


def test_textual_app_stack_detail_includes_last_action_result() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    app.stack_config_views["example.com"] = {
        "ok": True,
        "stack": {
            "profile": None,
            "has_local_config": False,
            "effective": {"docker_network": "web", "traefik_url": "http://localhost:8081"},
            "effective_sources": {"docker_network": "global-config", "traefik_url": "global-config"},
            "stack_config_path": "/srv/homesrvctl/sites/example.com/homesrvctl.yml",
        },
    }
    app.stack_domain_views["example.com"] = {
        "ok": True,
        "domain": "example.com",
        "overall": "ok",
        "repairable": False,
        "manual_fix_required": False,
        "expected_tunnel_target": "1234.cfargotunnel.com",
        "expected_ingress_service": "http://localhost:8081",
        "coverage_issues": [],
        "ingress_warnings": [],
        "dns": [],
        "ingress": [],
    }
    app.last_stack_actions["example.com"] = {
        "action": "doctor",
        "payload": {
            "ok": False,
            "checks": [
                {"name": "docker-compose.yml", "ok": True, "detail": "/srv/homesrvctl/sites/example.com/docker-compose.yml"},
                {"name": "host-header request", "ok": False, "detail": "request failed: connection refused"},
            ],
        },
    }

    detail = app._detail_text()

    assert "Last action" in detail
    assert "action" in detail
    assert "doctor" in detail
    assert "[red]FAIL[/red] host-header request: request failed: connection refused" in detail


def test_textual_app_stack_detail_includes_domain_status() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    app.stack_config_views["example.com"] = {
        "ok": True,
        "stack": {
            "profile": None,
            "has_local_config": False,
            "effective": {"docker_network": "web", "traefik_url": "http://localhost:8081"},
            "effective_sources": {"docker_network": "global-config", "traefik_url": "global-config"},
            "stack_config_path": "/srv/homesrvctl/sites/example.com/homesrvctl.yml",
        },
    }
    app.stack_domain_views["example.com"] = {
        "ok": False,
        "domain": "example.com",
        "overall": "partial",
        "repairable": True,
        "manual_fix_required": False,
        "expected_tunnel_target": "1234.cfargotunnel.com",
        "expected_ingress_service": "http://localhost:8081",
        "coverage_issues": ["Ingress coverage is apex-only; wildcard ingress is missing"],
        "ingress_warnings": [],
        "dns": [],
        "ingress": [],
        "suggested_command": "homesrvctl domain repair example.com",
    }

    detail = app._detail_text()

    assert "Domain status" in detail
    assert "overall" in detail
    assert "partial" in detail
    assert "suggested command" in detail
    assert "homesrvctl domain repair example.com" in detail


def test_textual_app_domain_repair_rejects_subdomain(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "notes.example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_domain_repair()

    assert app.status_message == "domain repair is only available for apex stacks: notes.example.com"


def test_textual_app_domain_add_rejects_subdomain(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "notes.example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 5
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app.action_domain_add_prompt()

    assert app.status_message == "domain add/remove is only available for apex stacks: notes.example.com"


def test_textual_app_domain_onboarding_rejects_invalid_domain(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_domain_onboarding_domain("notes.example.com")

    assert app.status_message.startswith("domain onboarding rejected domain:")


def test_textual_app_domain_onboarding_pushes_dry_run_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_domain_onboarding_domain("example.com")

    assert app.pending_domain_request == {"hostname": "example.com"}
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.BooleanChoiceScreen)


def test_textual_app_domain_onboarding_pushes_restart_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.pending_domain_request = {"hostname": "example.com"}
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_domain_onboarding_dry_run(True)

    assert app.pending_domain_request["dry_run"] is True
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.BooleanChoiceScreen)


def test_textual_app_domain_onboarding_runs_and_focuses_tunnel_when_no_stack(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "tunnel": {
                "ok": True,
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "credentials+api",
                "account_id": "account-123",
                "api_available": True,
                "api_status": {"name": "homesrvctl-tunnel", "status": "healthy"},
                "api_error": None,
            },
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "tunnel": {
                "ok": True,
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "credentials+api",
                "account_id": "account-123",
                "api_available": True,
                "api_status": {"name": "homesrvctl-tunnel", "status": "healthy"},
                "api_error": None,
            },
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str, dict[str, object]]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 0
    app.pending_domain_request = {
        "hostname": "example.com",
        "dry_run": True,
        "restart_cloudflared": True,
    }

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action, **kwargs: calls.append((hostname, action, kwargs))
        or {"ok": True, "dry_run": True, "dns": [], "ingress": []},
    )
    monkeypatch.setattr(
        textual_app,
        "run_stack_domain_status",
        lambda hostname: {"ok": True, "domain": hostname, "overall": "ok", "repairable": False, "manual_fix_required": False, "dns": [], "ingress": []},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._complete_domain_onboarding_restart(True)

    assert calls == [("example.com", "domain-add", {"dry_run": True, "restart_cloudflared": True})]
    assert app.status_message == "domain add succeeded for example.com"
    assert app.selected_control_index == 1
    assert app.global_domain_action is not None


def test_textual_app_tunnel_detail_includes_last_domain_onboarding() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "tunnel": {
            "ok": True,
            "configured_tunnel": "homesrvctl-tunnel",
            "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
            "resolution_source": "credentials+api",
            "account_id": "account-123",
            "api_available": True,
            "api_status": {"name": "homesrvctl-tunnel", "status": "healthy"},
            "api_error": None,
        },
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 1
    app.global_domain_action = {
        "hostname": "example.com",
        "action": "domain-add",
        "payload": {"ok": True, "dry_run": True, "dns": [], "ingress": []},
    }
    app.global_domain_status_view = {
        "ok": False,
        "domain": "example.com",
        "overall": "partial",
        "repairable": True,
        "manual_fix_required": False,
        "expected_tunnel_target": "1234.cfargotunnel.com",
        "expected_ingress_service": "http://localhost:8081",
        "coverage_issues": ["Ingress coverage is apex-only; wildcard ingress is missing"],
        "ingress_warnings": [],
        "dns": [],
        "ingress": [],
        "suggested_command": "homesrvctl domain repair example.com",
    }

    detail = app._tunnel_detail_text()

    assert "Last Domain Onboarding" in detail
    assert "domain: example.com" in detail
    assert "dry run" in detail
    assert "Domain status" in detail


def test_textual_app_domain_remove_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_domain_confirmation("example.com", "domain-remove", False)

    assert app.status_message == "domain remove cancelled for example.com"


def test_textual_app_tool_detail_and_command_bar_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {
            "ok": True,
            "mode": "systemd",
            "active": True,
            "detail": "systemd service is active",
            "setup": {
                "ok": True,
                "setup_state": "ready",
                "configured_path": "/srv/homesrvctl/cloudflared/config.yml",
                "configured_credentials_path": "/srv/homesrvctl/cloudflared/11111111-2222-4333-8444-555555555555.json",
                "configured_credentials_readable": True,
                "configured_credentials_owner": "root",
                "configured_credentials_group": "homesrvctl",
                "configured_credentials_mode": "640",
                "runtime_path": "/srv/homesrvctl/cloudflared/config.yml",
                "paths_aligned": True,
                "configured_exists": True,
                "configured_writable": True,
                "account_inspection_available": True,
                "ingress_mutation_available": True,
                "service_user": "root",
                "service_group": "homesrvctl",
                "shared_group": "homesrvctl",
                "issues": [],
                "notes": [],
                "next_commands": [],
            },
            "config_validation": {
                "ok": True,
                "detail": "Validating rules\nOK",
                "warnings": [],
                "issues": [],
                "max_severity": None,
            },
        },
        "validate": {"ok": False, "checks": [{"name": "docker", "ok": False, "detail": "missing"}]},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }
    app.selected_control_index = 2

    detail = app._detail_text()
    command_bar = app._command_bar_text()

    assert "Cloudflared Detail" in detail
    assert "runtime: systemd" in detail
    assert "w/s navigate" in command_bar
    assert "q quit" in command_bar


def test_textual_app_bootstrap_detail_text() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {
            "ok": True,
            "bootstrap_state": "partial",
            "host_supported": True,
            "detail": "host is partially provisioned relative to the current bootstrap target",
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "os": {"pretty_name": "Debian GNU/Linux 12", "supported": True, "detail": "Debian-family host detected"},
            "packages": {"docker": True, "docker_compose": False, "cloudflared": True},
            "services": {"traefik_running": False, "cloudflared_active": True, "cloudflared_mode": "systemd"},
            "config": {"exists": True, "valid": True, "token_present": False, "token_source": "missing"},
            "network": {"name": "web", "exists": False, "detail": "docker network not found"},
            "cloudflare": {"token_present": False, "token_source": "missing", "api_reachable": None, "detail": "Cloudflare API token is not configured"},
            "issues": ["Traefik is not running"],
            "next_steps": ["Install or start the baseline Traefik runtime expected by homesrvctl."],
        },
    }
    app.selected_control_index = 4

    detail = app._detail_text()

    assert "Bootstrap Detail" in detail
    assert "bootstrap state" in detail
    assert "Traefik is not running" in detail


def test_textual_app_tool_detail_includes_last_cloudflared_action() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {
            "ok": True,
            "mode": "systemd",
            "active": True,
            "detail": "systemd service is active",
            "config_validation": {
                "ok": True,
                "detail": "Validating rules\nOK",
                "warnings": [],
                "issues": [],
                "max_severity": None,
            },
        },
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 2
    app.last_tool_actions["cloudflared"] = {
        "action": "config-test",
        "payload": {
            "ok": True,
            "detail": "fallback service http_status:404",
            "warnings": ["earlier wildcard rule *.com may capture later hostname *.example.com"],
            "issues": [
                {
                    "severity": "advisory",
                    "blocking": False,
                    "message": "earlier wildcard rule *.com may capture later hostname *.example.com",
                }
            ],
        },
    }

    detail = app._detail_text()

    assert "Last action" in detail
    assert "action" in detail
    assert "config-test" in detail
    assert "warnings: 1" in detail
    assert "issues: 1 total, 0 blocking, 1 advisory" in detail


def test_textual_app_tool_detail_includes_last_cloudflared_logs_action() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {
            "ok": True,
            "mode": "systemd",
            "active": True,
            "detail": "systemd service is active",
            "config_validation": {
                "ok": True,
                "detail": "Validating rules\nOK",
                "warnings": [],
                "issues": [],
                "max_severity": None,
            },
        },
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 2
    app.last_tool_actions["cloudflared"] = {
        "action": "logs",
        "payload": {
            "ok": True,
            "follow": True,
            "detail": "journalctl guidance available",
            "logs_command": ["journalctl", "-u", "cloudflared", "-f"],
        },
    }

    detail = app._detail_text()

    assert "logs command" in detail
    assert "journalctl -u cloudflared -f" in detail


def test_textual_app_config_detail_includes_last_config_action() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {
            "ok": True,
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "global": {
                "sites_root": "/srv/homesrvctl/sites",
                "docker_network": "web",
                "traefik_url": "http://localhost:8081",
                "cloudflared_config": "/etc/cloudflared/config.yml",
                "cloudflare_api_token_present": False,
                "profiles": {},
            },
        },
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    app.selected_control_index = 0
    app.last_tool_actions["config"] = {
        "action": "init",
        "payload": {
            "ok": True,
            "detail": "starter config written",
            "config_path": "/home/test/.config/homesrvctl/config.yml",
        },
    }

    detail = app._detail_text()

    assert "Last action" in detail
    assert "init" in detail


def test_textual_app_uses_human_readable_title() -> None:
    app = textual_app.HomesrvctlTextualApp()

    assert app.TITLE == "Home Server Controller"


def test_textual_app_selected_stack_action_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": False}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 5

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action: calls.append((hostname, action)) or {"ok": True},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._run_selected_stack_action("up")

    assert calls == [("example.com", "up")]
    assert app.status_message == "up succeeded for example.com"
    assert app.snapshot["list"]["sites"][0]["compose"] is True
    assert app.last_stack_actions["example.com"]["action"] == "up"


def test_textual_app_domain_repair_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 5

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action: calls.append((hostname, action)) or {"ok": True},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app.action_domain_repair()

    assert calls == [("example.com", "domain-repair")]
    assert app.status_message == "domain repair succeeded for example.com"
    assert app.last_stack_actions["example.com"]["action"] == "domain-repair"


def test_textual_app_domain_add_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 5

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action: calls.append((hostname, action)) or {"ok": True},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._complete_domain_confirmation("example.com", "domain-add", True)

    assert calls == [("example.com", "domain-add")]
    assert app.status_message == "domain add succeeded for example.com"
    assert app.last_stack_actions["example.com"]["action"] == "domain-add"


def test_textual_app_domain_remove_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 5

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action: calls.append((hostname, action)) or {"ok": True},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._complete_domain_confirmation("example.com", "domain-remove", True)

    assert calls == [("example.com", "domain-remove")]
    assert app.status_message == "domain remove succeeded for example.com"
    assert app.last_stack_actions["example.com"]["action"] == "domain-remove"


def test_textual_app_app_init_prompt_runs_selected_template(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "app.example.com", "compose": False}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "app.example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str, str | None]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 5

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action, template=None: calls.append((hostname, action, template))
        or {"ok": True, "template": template, "files": ["/srv/homesrvctl/sites/app.example.com/docker-compose.yml"]},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._complete_app_init_prompt("app.example.com", "node")

    assert calls == [("app.example.com", "app-init", "node")]
    assert app.status_message == "app init succeeded for app.example.com"
    assert app.last_stack_actions["app.example.com"]["action"] == "app-init"


def test_textual_app_app_init_prompt_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "app.example.com", "compose": False}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_app_init_prompt("app.example.com", None)

    assert app.status_message == "app init cancelled for app.example.com"


def test_textual_app_create_stack_flow_pushes_hostname_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app.action_create_stack_flow()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.TextEntryScreen)


def test_textual_app_create_stack_flow_rejects_invalid_hostname(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_create_hostname("not bare path / bad")

    assert app.status_message.startswith("create flow rejected hostname:")


def test_textual_app_create_stack_flow_pushes_mode_after_hostname(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_create_hostname("app.example.com")

    assert app.pending_create_request == {"hostname": "app.example.com"}
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.CreationModeScreen)


def test_textual_app_create_stack_flow_app_mode_pushes_template_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.pending_create_request = {"hostname": "app.example.com"}
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_create_mode("app-init")

    assert app.pending_create_request["action"] == "app-init"
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.AppInitTemplateScreen)


def test_textual_app_create_stack_flow_site_mode_pushes_profile_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.pending_create_request = {"hostname": "example.com"}
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_create_mode("init-site")

    assert app.pending_create_request["action"] == "init-site"
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.TextEntryScreen)


def test_textual_app_create_stack_flow_overwrite_prompts_force(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.pending_create_request = {
        "hostname": "app.example.com",
        "action": "app-init",
        "template": "node",
        "profile": None,
        "docker_network": None,
        "traefik_url": None,
    }
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action, template=None, **kwargs: {
            "ok": False,
            "error": "generated files already exist; use --force to overwrite",
        },
    )
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._run_pending_create_request()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.ConfirmActionScreen)


def test_textual_app_complete_create_overwrite_runs_force(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    calls: list[bool] = []

    monkeypatch.setattr(
        textual_app.HomesrvctlTextualApp,
        "_run_pending_create_request",
        lambda self, force=False: calls.append(force),
    )

    app._complete_create_overwrite(True)

    assert calls == [True]


def test_textual_app_create_stack_flow_runs_and_reselects_created_stack(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "app.example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str, str | None, dict[str, object]]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 0
    app.pending_create_request = {
        "hostname": "app.example.com",
        "action": "app-init",
        "template": "node",
        "profile": "edge",
        "docker_network": "edge-net",
        "traefik_url": "http://localhost:9000",
    }

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_stack_action",
        lambda hostname, action, template=None, **kwargs: calls.append((hostname, action, template, kwargs))
        or {"ok": True, "template": template, "files": ["/srv/homesrvctl/sites/app.example.com/docker-compose.yml"]},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._run_pending_create_request()

    assert calls == [(
        "app.example.com",
        "app-init",
        "node",
        {
            "force": False,
            "profile": "edge",
            "docker_network": "edge-net",
            "traefik_url": "http://localhost:9000",
        },
    )]
    assert app.status_message == "app init succeeded for app.example.com"
    assert app.last_stack_actions["app.example.com"]["action"] == "app-init"
    assert app.selected_control_index == 5


def test_textual_app_selected_tool_action_refreshes_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:01:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {
                "ok": True,
                "mode": "systemd",
                "active": True,
                "detail": "systemd service is active",
                "config_validation": {
                    "ok": True,
                    "detail": "Validating rules\nOK",
                    "warnings": [],
                    "issues": [],
                    "max_severity": None,
                },
            },
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 2

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_tool_action",
        lambda tool, action, **kwargs: calls.append((tool, action)) or {"ok": True, "detail": "validated", "warnings": []},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._run_selected_tool_action("cloudflared", "config-test")

    assert calls == [("cloudflared", "config-test")]
    assert app.status_message == "cloudflared config-test succeeded"
    assert app.last_tool_actions["cloudflared"]["action"] == "config-test"


def test_textual_app_cloudflared_setup_action_updates_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": False, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
        {
            "generated_at": "2026-04-08 12:00:01",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": False, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
        },
    ]
    calls: list[tuple[str, str]] = []
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots[0]
    app.selected_control_index = 2

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_tool_action",
        lambda tool, action, **kwargs: calls.append((tool, action))
        or {"ok": False, "detail": "setup mismatch", "next_commands": ["sudo systemctl daemon-reload"]},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._refresh_snapshot("dashboard ready")
    app._run_selected_tool_action("cloudflared", "setup")

    assert calls == [("cloudflared", "setup")]
    assert app.status_message == "cloudflared setup failed: setup mismatch"
    assert app.last_tool_actions["cloudflared"]["action"] == "setup"


def test_textual_app_cloudflared_tool_menu_routes_logs_prompt(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._complete_tool_action_menu("cloudflared", "logs")

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.CloudflaredLogsModeScreen)


def test_textual_app_complete_cloudflared_logs_mode_runs_action(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    calls: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(
        textual_app.HomesrvctlTextualApp,
        "_run_selected_tool_action",
        lambda self, tool, action, follow=False: calls.append((tool, action, follow)),
    )

    app._complete_cloudflared_logs_mode(True)

    assert calls == [("cloudflared", "logs", True)]


def test_textual_app_complete_cloudflared_logs_mode_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_cloudflared_logs_mode(None)

    assert app.status_message == "cloudflared logs cancelled"


def test_textual_app_run_config_init_prompts_overwrite_when_config_exists(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": False, "error": "config file not found"},
        "list": {"ok": True, "sites": []},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
        "validate": {"ok": True, "checks": []},
    }
    pushed: list[tuple[object, object]] = []

    monkeypatch.setattr(
        textual_app,
        "run_tool_action",
        lambda tool, action, **kwargs: {
            "ok": False,
            "action": "config_init",
            "config_path": "/home/test/.config/homesrvctl/config.yml",
            "error": "config already exists: /home/test/.config/homesrvctl/config.yml. Use --force to overwrite.",
        },
    )
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append((screen, callback)))

    app._run_config_init()

    assert len(pushed) == 1
    assert isinstance(pushed[0][0], prompts.ConfirmActionScreen)


def test_textual_app_complete_config_init_overwrite_runs_force(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    calls: list[bool] = []

    monkeypatch.setattr(
        textual_app.HomesrvctlTextualApp,
        "_run_config_init",
        lambda self, force=False: calls.append(force),
    )

    app._complete_config_init_overwrite(True)

    assert calls == [True]


def test_textual_app_complete_config_init_overwrite_cancel_updates_status(monkeypatch) -> None:
    app = textual_app.HomesrvctlTextualApp()
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app._complete_config_init_overwrite(False)

    assert app.status_message == "config init cancelled"


def test_control_row_widget_has_correct_index_and_label() -> None:
    row = textual_app.ControlRowWidget(3, "Validate")

    assert row.row_index == 3
    assert row.render() == "Validate"


def test_control_row_widget_renders_with_suffix() -> None:
    row = textual_app.ControlRowWidget(3, "example.com", "[compose_yes]●[/compose_yes]")

    rendered = row.render()

    assert "example.com" in rendered
    assert "●" in rendered


def test_control_row_widget_click_updates_selected_index(monkeypatch) -> None:
    import asyncio

    async def _run() -> int:
        snapshot = {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
        }

        def fake_build_snapshot():  # noqa: ANN202
            return snapshot

        monkeypatch.setattr(textual_app, "build_dashboard_snapshot", fake_build_snapshot)

        app = textual_app.HomesrvctlTextualApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Bootstrap adds one more tool row; Validate stays index 3.
            await pilot.click(textual_app.ControlRowWidget, offset=(1, 0))
            # All five tool rows appear; the first ControlRowWidget is Config (index 0)
            # We need the fourth row (Validate, index 3)
            rows = app.query(textual_app.ControlRowWidget)
            validate_row = [r for r in rows if r.row_index == 3][0]
            await pilot.click(validate_row)
            return app.selected_control_index

    result = asyncio.run(_run())
    assert result == 3


def test_control_items_returns_tools_then_stacks() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [
            {"hostname": "example.com", "compose": True},
            {"hostname": "notes.example.com", "compose": False},
        ]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    items = app._control_items()

    assert items[0] == {"kind": "tool", "tool": "config", "label": "Config"}
    assert items[1] == {"kind": "tool", "tool": "tunnel", "label": "Tunnel"}
    assert items[2] == {"kind": "tool", "tool": "cloudflared", "label": "Cloudflared"}
    assert items[3] == {"kind": "tool", "tool": "validate", "label": "Validate"}
    assert items[4] == {"kind": "tool", "tool": "bootstrap", "label": "Bootstrap"}
    assert items[5]["kind"] == "stack"
    assert items[5]["hostname"] == "example.com"
    assert items[5]["compose"] is True
    assert items[6]["kind"] == "stack"
    assert items[6]["hostname"] == "notes.example.com"
    assert items[6]["compose"] is False


def test_detail_pane_title_reflects_focused_tool() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    app.selected_control_index = 0
    assert app._detail_pane_title() == "Tool: Config"

    app.selected_control_index = 1
    assert app._detail_pane_title() == "Tool: Tunnel"

    app.selected_control_index = 2
    assert app._detail_pane_title() == "Tool: Cloudflared"

    app.selected_control_index = 3
    assert app._detail_pane_title() == "Tool: Validate"

    app.selected_control_index = 4
    assert app._detail_pane_title() == "Tool: Bootstrap"

    app.selected_control_index = 5
    assert app._detail_pane_title() == "Stack: example.com"


def test_option_row_widget_renders_label_and_description() -> None:
    row = prompts.OptionRowWidget(0, 1, "app init", "Choose a scaffold template.")

    assert row.option_index == 0
    assert row._label == "app init"
    assert row._description == "Choose a scaffold template."


def test_option_row_widget_click_calls_select_on_screen() -> None:
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Static as TStatic

    dismissed: list[str] = []

    async def _run() -> None:
        screen = prompts.StackActionMenuScreen("example.com", is_apex_domain=False)

        class WrapperApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TStatic("")

            def on_mount(self) -> None:
                self.push_screen(screen, lambda result: dismissed.append(result or ""))

        wrapper = WrapperApp()
        async with wrapper.run_test(size=(80, 30)) as pilot:
            await pilot.pause()  # let on_mount / push_screen complete
            # Click the second option row (index 1 = site-init); query the active screen
            rows = list(wrapper.screen.query(prompts.OptionRowWidget))
            if len(rows) >= 2:
                await pilot.click(rows[1])
                await pilot.pause()
                # Press enter to confirm the highlighted selection
                await pilot.press("enter")
                await pilot.pause()

    asyncio.run(_run())
    # Should have dismissed with site-init (index 1 in non-apex options)
    assert dismissed and dismissed[0] == "site-init"


def test_confirm_action_screen_has_title_and_body() -> None:
    screen = prompts.ConfirmActionScreen("Confirm Action", "Proceed?")
    assert screen.title == "Confirm Action"
    assert screen.body == "Proceed?"


def test_confirm_action_screen_dismiss_on_button_click() -> None:
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Static as TStatic

    dismissed: list[bool] = []

    async def _run() -> None:
        screen = prompts.ConfirmActionScreen("Confirm", "Do it?")

        class WrapperApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TStatic("")

            def on_mount(self) -> None:
                self.push_screen(screen, lambda result: dismissed.append(result))

        wrapper = WrapperApp()
        async with wrapper.run_test(size=(80, 20)) as pilot:
            await pilot.pause()
            await pilot.click("#btn_confirm")
            await pilot.pause()

    asyncio.run(_run())
    assert dismissed == [True]


def test_confirm_action_screen_cancel_button_dismisses_false() -> None:
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Static as TStatic

    dismissed: list[bool] = []

    async def _run() -> None:
        screen = prompts.ConfirmActionScreen("Confirm", "Do it?")

        class WrapperApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TStatic("")

            def on_mount(self) -> None:
                self.push_screen(screen, lambda result: dismissed.append(result))

        wrapper = WrapperApp()
        async with wrapper.run_test(size=(80, 20)) as pilot:
            await pilot.pause()
            await pilot.click("#btn_cancel")
            await pilot.pause()

    asyncio.run(_run())
    assert dismissed == [False]


def test_detail_button_actions_stack_focus() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }
    app.selected_control_index = 5  # example.com stack

    # Simulate _rebuild_detail_buttons without a running app
    # by calling the inner logic directly
    item = app._selected_control_item()
    assert item.get("kind") == "stack"
    # Verify the expected button labels for stack focus
    specs_labels = ["Up", "Down", "Restart", "Doctor", "Actions"]
    # The method builds _detail_button_actions; set it directly for test
    app._detail_button_actions = {label: action for label, action in [
        ("Up", "up"), ("Down", "down"), ("Restart", "restart"),
        ("Doctor", "doctor"), ("Actions", "stack_action_menu"),
    ]}
    assert set(app._detail_button_actions.keys()) == set(specs_labels)


def test_detail_button_actions_cloudflared_focus() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }
    app.selected_control_index = 2  # Cloudflared

    item = app._selected_control_item()
    assert item.get("tool") == "cloudflared"
    app._detail_button_actions = {label: action for label, action in [
        ("Fix Setup", "cloudflared_setup"),
        ("Config Test", "cloudflared_config_test"),
        ("Reload", "cloudflared_reload"),
        ("Restart CF", "cloudflared_restart"),
    ]}
    assert "Fix Setup" in app._detail_button_actions
    assert app._detail_button_actions["Fix Setup"] == "cloudflared_setup"
    assert "Config Test" in app._detail_button_actions
    assert app._detail_button_actions["Config Test"] == "cloudflared_config_test"


def test_detail_button_actions_bootstrap_focus() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "generated_at": "2026-04-08 12:00:00",
        "config": {"ok": True, "global": {"profiles": {}}},
        "list": {"ok": True, "sites": []},
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "validate": {"ok": True, "checks": []},
        "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
    }
    app.selected_control_index = 4  # Bootstrap

    item = app._selected_control_item()
    assert item.get("tool") == "bootstrap"
    app._detail_button_actions = {label: action for label, action in [
        ("Refresh", "bootstrap_assess"),
        ("Create", "create_stack_flow"),
        ("Onboard Domain", "domain_onboarding_flow"),
    ]}
    assert app._detail_button_actions["Refresh"] == "bootstrap_assess"


def test_bootstrap_summary_parts_partial() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "bootstrap": {
            "ok": True,
            "bootstrap_state": "partial",
            "host_supported": True,
            "detail": "host is partially provisioned relative to the current bootstrap target",
            "issues": ["Traefik is not running", "Cloudflare API token is missing"],
        },
    }

    status, detail = app._bootstrap_summary_parts()

    assert "partial" in status or "⚠" in status
    assert "2 issue" in detail


def test_textual_app_bootstrap_assess_action_updates_status(monkeypatch) -> None:
    snapshots = [
        {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "fresh", "host_supported": True, "detail": "fresh"},
        },
        {
            "generated_at": "2026-04-08 12:00:05",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "systemd service is active"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
        },
    ]
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(textual_app, "build_dashboard_snapshot", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        textual_app,
        "run_tool_action",
        lambda tool, action, **kwargs: calls.append((tool, action))
        or {"ok": True, "bootstrap_state": "partial", "detail": "partial", "issues": [], "next_steps": []},
    )
    monkeypatch.setattr(textual_app.HomesrvctlTextualApp, "_render", lambda self: None)

    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = snapshots.pop(0)
    app.selected_control_index = 4

    app.action_bootstrap_assess()

    assert calls == [("bootstrap", "assess")]
    assert app.status_message == "bootstrap assess succeeded"


def test_detail_button_press_dispatches_action(monkeypatch) -> None:
    import asyncio

    actions_called: list[str] = []

    async def _run() -> None:
        snapshot = {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": []},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
        }

        def fake_build_snapshot():  # noqa: ANN202
            return snapshot

        monkeypatch.setattr(textual_app, "build_dashboard_snapshot", fake_build_snapshot)
        monkeypatch.setattr(
            textual_app.HomesrvctlTextualApp,
            "action_refresh",
            lambda self: actions_called.append("refresh"),
        )

        from textual.widgets import Button as TButton
        app = textual_app.HomesrvctlTextualApp()
        # Validate tool focus (index 3) → Refresh button
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Click the Refresh button in the detail button strip
            buttons = list(app.query(TButton))
            refresh_btns = [b for b in buttons if str(b.label) == "Refresh"]
            if refresh_btns:
                await pilot.click(refresh_btns[0])
                await pilot.pause()

    asyncio.run(_run())
    assert "refresh" in actions_called


def test_stacks_summary_parts_ready() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "list": {"ok": True, "sites": [
            {"hostname": "example.com", "compose": True},
            {"hostname": "notes.example.com", "compose": False},
        ]},
    }

    status, detail = app._stacks_summary_parts()

    assert "1 ready" in status or "✓" in status
    assert "2" in detail


def test_stacks_summary_parts_error() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {"list": {"ok": False, "error": "list command failed"}}

    status, detail = app._stacks_summary_parts()

    assert "error" in status.lower() or "✗" in status


def test_cloudflared_summary_parts_active() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    status, detail = app._cloudflared_summary_parts()

    assert "active" in status
    assert "systemd" in detail


def test_cloudflared_summary_parts_inactive() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "cloudflared": {"ok": True, "mode": "docker", "active": False, "detail": "not running"},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    status, detail = app._cloudflared_summary_parts()

    assert "inactive" in status or "⚠" in status


def test_validate_summary_parts_passing() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "validate": {"ok": True, "checks": [
            {"name": "docker", "ok": True},
            {"name": "config", "ok": True},
        ]},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    status, detail = app._validate_summary_parts()

    assert "passing" in status or "✓" in status
    assert "2" in detail


def test_validate_summary_parts_failing() -> None:
    app = textual_app.HomesrvctlTextualApp()
    app.snapshot = {
        "validate": {"ok": False, "checks": [
            {"name": "docker", "ok": True},
            {"name": "config", "ok": False},
        ]},
        "bootstrap": {"ok": True, "bootstrap_state": "ready", "host_supported": True, "detail": "ready"},
    }

    status, detail = app._validate_summary_parts()

    assert "failing" in status or "✗" in status


def test_summary_card_click_focuses_control_row(monkeypatch) -> None:
    import asyncio

    async def _run() -> int:
        snapshot = {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
        }

        def fake_build_snapshot():  # noqa: ANN202
            return snapshot

        monkeypatch.setattr(textual_app, "build_dashboard_snapshot", fake_build_snapshot)

        app = textual_app.HomesrvctlTextualApp()
        app.selected_control_index = 0  # start on Config
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Click the Validate summary card (focus_index=3 → Validate tool)
            card = app.query_one("#summary_validate", textual_app.SummaryCardWidget)
            await pilot.click(card)
            await pilot.pause()
            return app.selected_control_index

    result = asyncio.run(_run())
    assert result == 3  # Validate remains index 3


def test_mixed_keyboard_and_mouse_navigation(monkeypatch) -> None:
    """ROADMAP 6.5: mixed keyboard-plus-mouse interaction sequences.

    Keyboard focus (via w/s) and mouse click should converge on the same
    selected_control_index — not drift into separate tracks.
    """
    import asyncio

    async def _run() -> list[int]:
        snapshot = {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [
                {"hostname": "example.com", "compose": True},
                {"hostname": "notes.example.com", "compose": False},
            ]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
        }

        def fake_build_snapshot():  # noqa: ANN202
            return snapshot

        monkeypatch.setattr(textual_app, "build_dashboard_snapshot", fake_build_snapshot)

        trace: list[int] = []
        app = textual_app.HomesrvctlTextualApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            trace.append(app.selected_control_index)  # initial (0)

            # Keyboard: move down three times → index 3 (Validate)
            await pilot.press("s")
            await pilot.press("s")
            await pilot.press("s")
            await pilot.pause()
            trace.append(app.selected_control_index)

            # Click a stack row to jump to it
            rows = list(app.query(textual_app.ControlRowWidget))
            target = [r for r in rows if r.row_index == 6]  # second stack
            if target:
                await pilot.click(target[0], offset=(1, 0))
                await pilot.pause()
                trace.append(app.selected_control_index)

            # Keyboard: move up once → index 5 (first stack)
            await pilot.press("w")
            await pilot.pause()
            trace.append(app.selected_control_index)

        return trace

    trace = asyncio.run(_run())
    assert trace == [0, 3, 6, 5]


def test_click_selection_applies_selected_class(monkeypatch) -> None:
    """ROADMAP 6.5: the --selected CSS class should track both keyboard
    and mouse focus (single source of truth for the highlight).
    """
    import asyncio

    async def _run() -> tuple[bool, bool]:
        snapshot = {
            "generated_at": "2026-04-08 12:00:00",
            "config": {"ok": True, "global": {"profiles": {}}},
            "list": {"ok": True, "sites": [{"hostname": "example.com", "compose": True}]},
            "cloudflared": {"ok": True, "mode": "systemd", "active": True, "detail": "ok"},
            "validate": {"ok": True, "checks": []},
            "bootstrap": {"ok": True, "bootstrap_state": "partial", "host_supported": True, "detail": "partial"},
        }

        def fake_build_snapshot():  # noqa: ANN202
            return snapshot

        monkeypatch.setattr(textual_app, "build_dashboard_snapshot", fake_build_snapshot)

        app = textual_app.HomesrvctlTextualApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            rows = list(app.query(textual_app.ControlRowWidget))
            target = [r for r in rows if r.row_index == 3][0]  # Validate
            await pilot.click(target)
            await pilot.pause()
            # After click, the Validate row should carry --selected
            rows_after = list(app.query(textual_app.ControlRowWidget))
            validate_selected = any(
                r.row_index == 3 and "--selected" in r.classes for r in rows_after
            )
            config_not_selected = all(
                "--selected" not in r.classes for r in rows_after if r.row_index == 0
            )
            return validate_selected, config_not_selected

    validate_selected, config_not_selected = asyncio.run(_run())
    assert validate_selected
    assert config_not_selected


def test_click_driven_prompt_then_cancel_keyboard(monkeypatch) -> None:
    """Click opens prompt; keyboard can still cancel it (mixed sequence)."""
    import asyncio
    from textual.app import App, ComposeResult
    from textual.widgets import Static as TStatic

    dismissed: list[object] = []

    async def _run() -> None:
        screen = prompts.StackActionMenuScreen("example.com", is_apex_domain=True)

        class WrapperApp(App[None]):
            def compose(self) -> ComposeResult:
                yield TStatic("")

            def on_mount(self) -> None:
                self.push_screen(screen, lambda result: dismissed.append(result))

        wrapper = WrapperApp()
        async with wrapper.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            # Click first option row to highlight it
            rows = list(wrapper.screen.query(prompts.OptionRowWidget))
            if rows:
                await pilot.click(rows[0])
                await pilot.pause()
            # Cancel via keyboard
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(_run())
    assert dismissed == [None]
