from __future__ import annotations

from pathlib import Path

import json
import yaml
from typer.testing import CliRunner

from homectl.cloudflared_service import CloudflaredRuntime
from homectl.main import app


def _write_config(home: Path, sites_root: Path) -> None:
    config_dir = home / ".config" / "homectl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "tunnel_name": "homectl-tunnel",
        "sites_root": str(sites_root),
        "docker_network": "web",
        "traefik_url": "http://localhost:8081",
        "cloudflared_config": "/etc/cloudflared/config.yml",
        "cloudflare_api_token": "test-token",
    }
    (config_dir / "config.yml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _write_cloudflared_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [{"service": "http_status:404"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_site_init_scaffolds_files(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com"])

    assert result.exit_code == 0, result.output
    compose_file = sites_root / "test.example.com" / "docker-compose.yml"
    index_file = sites_root / "test.example.com" / "html" / "index.html"
    assert compose_file.exists()
    assert index_file.exists()
    compose = compose_file.read_text(encoding="utf-8")
    assert "traefik.http.routers.test-example-com.rule=Host(`test.example.com`)" in compose
    assert "external: true" in compose
    assert "test.example.com" in index_file.read_text(encoding="utf-8")


def test_app_init_node_template_creates_placeholder(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--template", "node"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "notes.example.com"
    assert (app_dir / "docker-compose.yml").exists()
    assert (app_dir / ".env.example").exists()
    assert (app_dir / "README.node-template.md").exists()


def test_cloudflared_status_json_output(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["mode"] == "docker"
    assert payload["restart_command"] == ["docker", "restart", "cloudflared"]


def test_cloudflared_status_json_failure(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="absent",
            active=False,
            detail="cloudflared not detected via systemd, docker, or process scan",
            restart_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "status", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["mode"] == "absent"
    assert payload["active"] is False


def test_cloudflared_restart_dry_run(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output
    assert "Dry-run complete for cloudflared restart via systemd" in result.output


def test_cloudflared_restart_reports_unmanaged_process(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "restart_cloudflared_service",
        lambda: (_ for _ in ()).throw(cloudflared_cmd.CloudflaredServiceError("process present; restart cloudflared manually")),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart"])

    assert result.exit_code == 1, result.output
    assert "restart cloudflared manually" in result.output


def test_cloudflared_restart_json_dry_run(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["mode"] == "docker"
    assert payload["restart_command"] == ["docker", "restart", "cloudflared"]


def test_cloudflared_restart_json_failure(monkeypatch) -> None:
    from homectl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="process",
            active=True,
            detail="process present: 123 cloudflared",
            restart_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert payload["mode"] == "process"


def test_domain_add_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            assert zone_id == "zone-123"
            assert content == "11111111-2222-4333-8444-555555555555.cfargotunnel.com"
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] create DNS CNAME example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create DNS CNAME *.example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create ingress example.com -> http://localhost:8081" in result.output
    assert "[dry-run] create ingress *.example.com -> http://localhost:8081" in result.output


def test_domain_add_dry_run_prints_restart_command(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            assert zone_id == "zone-123"
            assert content == "11111111-2222-4333-8444-555555555555.cfargotunnel.com"
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


def test_domain_add_json_output(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": "zone-123"}

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run", "--json", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "add"
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["dns"][0]["record_name"] == "example.com"
    assert payload["ingress"][1]["hostname"] == "*.example.com"
    assert payload["restart"]["restart_command"] == ["systemctl", "restart", "cloudflared"]


def test_domain_add_updates_cloudflared_ingress(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com"])

    assert result.exit_code == 0, result.output
    updated = yaml.safe_load(cloudflared_config.read_text(encoding="utf-8"))
    assert updated["ingress"] == [
        {"hostname": "example.com", "service": "http://localhost:8081"},
        {"hostname": "*.example.com", "service": "http://localhost:8081"},
        {"service": "http_status:404"},
    ]
    assert "Restart cloudflared to apply ingress changes" in result.output


def test_domain_add_restarts_cloudflared_when_requested(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "restart_cloudflared_service",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "Restarted cloudflared via systemd" in result.output


def test_domain_repair_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            assert zone_id == "zone-123"
            return type("Plan", (), {"action": "update", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] update DNS CNAME example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create ingress *.example.com -> http://localhost:8081" in result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


def test_domain_repair_reports_repaired(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "update", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 0, result.output
    assert "Repaired domain routing for example.com" in result.output


def test_domain_repair_json_error(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": "zone-123"}

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "example.com", "service": "http://localhost:9000"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "repair"
    assert payload["ok"] is False
    assert "duplicate ingress hostname entry found: example.com" in payload["error"]


def test_domain_remove_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def plan_dns_record_removal(self, zone_id: str, record_name: str):  # noqa: ANN202
            assert zone_id == "zone-123"
            return type("Plan", (), {"action": "delete", "record_type": "CNAME", "record_name": record_name, "content": ""})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "remove", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] delete DNS CNAME example.com" in result.output
    assert "[dry-run] delete DNS CNAME *.example.com" in result.output
    assert "[dry-run] delete ingress example.com" in result.output
    assert "[dry-run] delete ingress *.example.com" in result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


def test_domain_remove_json_output(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": "zone-123"}

        def plan_dns_record_removal(self, zone_id: str, record_name: str):  # noqa: ANN202
            return type("Plan", (), {"action": "delete", "record_type": "CNAME", "record_name": record_name, "content": ""})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "remove", "example.com", "--dry-run", "--json", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "remove"
    assert payload["ok"] is True
    assert payload["dns"][0]["action"] == "delete"
    assert payload["ingress"][1]["hostname"] == "*.example.com"
    assert payload["restart"]["mode"] == "systemd"


def test_domain_add_warns_with_docker_restart_hint(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com"])

    assert result.exit_code == 0, result.output
    assert "Restart cloudflared to apply ingress changes: docker restart cloudflared" in result.output


def test_domain_remove_updates_cloudflared_ingress(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"hostname": "keep.example.net", "service": "http://localhost:9000"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record_removal(self, zone_id: str, record_name: str):  # noqa: ANN202
            return type("Plan", (), {"action": "delete", "record_type": "CNAME", "record_name": record_name, "content": ""})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "remove", "example.com"])

    assert result.exit_code == 0, result.output
    updated = yaml.safe_load(cloudflared_config.read_text(encoding="utf-8"))
    assert updated["ingress"] == [
        {"hostname": "keep.example.net", "service": "http://localhost:9000"},
        {"service": "http_status:404"},
    ]
    assert "Restart cloudflared to apply ingress changes" in result.output


def test_domain_remove_restarts_cloudflared_when_requested(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record_removal(self, zone_id: str, record_name: str):  # noqa: ANN202
            return type("Plan", (), {"action": "delete", "record_type": "CNAME", "record_name": record_name, "content": ""})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "restart_cloudflared_service",
        lambda: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "remove", "example.com", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "Restarted cloudflared via systemd" in result.output


def test_domain_status_reports_ok(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str):  # noqa: ANN202
            return type(
                "Status",
                (),
                {
                    "record_name": record_name,
                    "exists": True,
                    "record_type": "CNAME",
                    "content": expected_content,
                    "proxied": True,
                    "matches_expected": True,
                },
            )()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 0, result.output
    assert "PASS DNS example.com: CNAME -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)" in result.output
    assert "PASS ingress *.example.com: http://localhost:8081" in result.output
    assert "Overall status for example.com: ok" in result.output


def test_domain_status_reports_partial(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str):  # noqa: ANN202
            if record_name == "example.com":
                return type(
                    "Status",
                    (),
                    {
                        "record_name": record_name,
                        "exists": True,
                        "record_type": "CNAME",
                        "content": expected_content,
                        "proxied": True,
                        "matches_expected": True,
                    },
                )()
            return type(
                "Status",
                (),
                {
                    "record_name": record_name,
                    "exists": False,
                    "record_type": "",
                    "content": "",
                    "proxied": False,
                    "matches_expected": False,
                },
            )()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert "FAIL DNS *.example.com: record missing" in result.output
    assert "FAIL ingress *.example.com: entry missing" in result.output
    assert "Overall status for example.com: partial" in result.output


def test_domain_status_reports_misconfigured(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:9000"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str):  # noqa: ANN202
            content = "wrong-target.example.com" if record_name == "example.com" else expected_content
            return type(
                "Status",
                (),
                {
                    "record_name": record_name,
                    "exists": True,
                    "record_type": "CNAME",
                    "content": content,
                    "proxied": True,
                    "matches_expected": record_name != "example.com",
                },
            )()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert "FAIL DNS example.com: CNAME -> wrong-target.example.com (proxied)" in result.output
    assert "FAIL ingress example.com: http://localhost:9000" in result.output
    assert "Overall status for example.com: misconfigured" in result.output


def test_domain_status_json_output(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "*.example.com", "service": "http://localhost:8081"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": "zone-123"}

        def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str):  # noqa: ANN202
            return type(
                "Status",
                (),
                {
                    "record_name": record_name,
                    "exists": True,
                    "record_type": "CNAME",
                    "content": expected_content,
                    "proxied": True,
                    "matches_expected": True,
                },
            )()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["domain"] == "example.com"
    assert payload["ok"] is True
    assert payload["overall"] == "ok"
    assert payload["dns"][0]["record_name"] == "example.com"
    assert payload["ingress"][1]["hostname"] == "*.example.com"


def test_domain_repair_reports_duplicate_ingress_hint(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                    {"hostname": "example.com", "service": "http://localhost:9000"},
                    {"service": "http_status:404"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            assert zone_name == "example.com"
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            return type("Plan", (), {"action": "noop", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 1, result.output
    assert "duplicate ingress hostname entry found: example.com" in result.output
    assert "Hint: remove the duplicate 'example.com' ingress entry" in result.output


def test_domain_status_reports_fallback_order_hint(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homectl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"service": "http_status:404"},
                    {"hostname": "example.com", "service": "http://localhost:8081"},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": "zone-123"}

        def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str):  # noqa: ANN202
            return type(
                "Status",
                (),
                {
                    "record_name": record_name,
                    "exists": True,
                    "record_type": "CNAME",
                    "content": expected_content,
                    "proxied": True,
                    "matches_expected": True,
                },
            )()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert "cloudflared fallback service must be the last ingress entry" in result.output
    assert "Hint: move the hostname-less fallback service to the end of the ingress list" in result.output


def test_deploy_dry_run_commands(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    site_result = runner.invoke(app, ["site", "init", "example.com"])
    assert site_result.exit_code == 0, site_result.output

    up_result = runner.invoke(app, ["up", "example.com", "--dry-run"])
    down_result = runner.invoke(app, ["down", "example.com", "--dry-run"])
    restart_result = runner.invoke(app, ["restart", "example.com", "--dry-run"])

    assert up_result.exit_code == 0, up_result.output
    assert down_result.exit_code == 0, down_result.output
    assert restart_result.exit_code == 0, restart_result.output
    assert "docker compose up -d" in up_result.output
    assert "docker compose down" in down_result.output
    assert "docker compose up -d" in restart_result.output


def test_deploy_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    site_result = runner.invoke(app, ["site", "init", "example.com"])
    assert site_result.exit_code == 0, site_result.output

    up_result = runner.invoke(app, ["up", "example.com", "--dry-run", "--json"])
    down_result = runner.invoke(app, ["down", "example.com", "--dry-run", "--json"])
    restart_result = runner.invoke(app, ["restart", "example.com", "--dry-run", "--json"])

    assert up_result.exit_code == 0, up_result.output
    assert down_result.exit_code == 0, down_result.output
    assert restart_result.exit_code == 0, restart_result.output

    up_payload = json.loads(up_result.output)
    down_payload = json.loads(down_result.output)
    restart_payload = json.loads(restart_result.output)

    assert up_payload["action"] == "up"
    assert up_payload["dry_run"] is True
    assert up_payload["ok"] is True
    assert up_payload["commands"][0]["command"] == ["docker", "compose", "up", "-d"]

    assert down_payload["action"] == "down"
    assert down_payload["commands"][0]["command"] == ["docker", "compose", "down"]

    assert restart_payload["action"] == "restart"
    assert len(restart_payload["commands"]) == 2
    assert restart_payload["commands"][1]["command"] == ["docker", "compose", "up", "-d"]


def test_deploy_json_reports_missing_stack(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["up", "missing.example.com", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "up"
    assert payload["ok"] is False
    assert payload["stack_dir"] is None
    assert "hostname directory does not exist" in payload["error"]


def test_deploy_json_reports_missing_compose(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    (sites_root / "example.com").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(app, ["down", "example.com", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "down"
    assert payload["ok"] is False
    assert payload["stack_dir"] is None
    assert "missing docker-compose.yml" in payload["error"]


def test_validate_json_output(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import validate_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    checks = [
        validate_cmd.CheckResult("cloudflared binary", True, "found in PATH"),
        validate_cmd.CheckResult("docker binary", True, "found in PATH"),
    ]
    monkeypatch.setattr(validate_cmd, "build_validate_report", lambda config: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "cloudflared binary"


def test_doctor_json_output(monkeypatch, tmp_path: Path) -> None:
    from homectl.commands import validate_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    checks = [
        validate_cmd.CheckResult("hostname directory", True, "/tmp/example.com"),
        validate_cmd.CheckResult("host-header request", True, "example.com returned HTTP 200"),
    ]
    monkeypatch.setattr(validate_cmd, "build_hostname_doctor_report", lambda config, hostname: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["hostname"] == "example.com"
    assert payload["ok"] is True
    assert payload["checks"][1]["name"] == "host-header request"


def test_list_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    example_dir = sites_root / "example.com"
    notes_dir = sites_root / "notes.example.com"
    example_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)
    (example_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["sites_root"] == str(sites_root)
    assert payload["sites"] == [
        {"hostname": "example.com", "compose": True},
        {"hostname": "notes.example.com", "compose": False},
    ]


def test_list_json_reports_missing_sites_root(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "missing-sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["sites"] == []
    assert "Sites root does not exist" in payload["error"]
