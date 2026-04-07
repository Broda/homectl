from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

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

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


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

    commands: list[list[str]] = []

    class FakeCommandResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

        @property
        def ok(self) -> bool:
            return True

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    monkeypatch.setattr(domain_cmd, "command_exists", lambda name: name == "systemctl")
    monkeypatch.setattr(
        domain_cmd,
        "run_command",
        lambda command: commands.append(command) or FakeCommandResult(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert commands == [["systemctl", "restart", "cloudflared"]]
    assert "Restarted cloudflared" in result.output


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
