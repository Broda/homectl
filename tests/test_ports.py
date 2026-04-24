from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from homesrvctl.main import app


def _write_config(home: Path, sites_root: Path) -> None:
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "tunnel_name": "homesrvctl-tunnel",
        "sites_root": str(sites_root),
        "docker_network": "web",
        "traefik_url": "http://localhost:8081",
        "cloudflared_config": "/etc/cloudflared/config.yml",
        "cloudflare_api_token": "test-token",
    }
    (config_dir / "config.yml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def test_app_init_node_accepts_port_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--template", "node", "--port", "app=3100"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "notes.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    server_js = (app_dir / "src" / "server.js").read_text(encoding="utf-8")

    assert "PORT: ${PORT:-3100}" in compose
    assert "loadbalancer.server.port=3100" in compose
    assert "http://127.0.0.1:${PORT:-3100}/healthz" in compose
    assert "PORT=3100" in env_example
    assert "EXPOSE 3100" in dockerfile
    assert 'process.env.PORT || "3100"' in server_js


def test_app_init_static_api_accepts_port_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "portal.example.com", "--template", "static-api", "--port", "api=8100"],
    )

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "portal.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (app_dir / "api" / "Dockerfile").read_text(encoding="utf-8")
    api_main = (app_dir / "api" / "app" / "main.py").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")

    assert "http://127.0.0.1:8100/healthz" in compose
    assert "loadbalancer.server.port=8100" in compose
    assert "EXPOSE 8100" in dockerfile
    assert 'HTTPServer(("0.0.0.0", 8100), Handler)' in api_main
    assert "API container listens on port `8100`" in readme


def test_app_init_rust_react_postgres_accepts_api_port_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "app.example.com", "--template", "rust-react-postgres", "--port", "api=8181"],
    )

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "app.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    dockerfile = (app_dir / "api" / "Dockerfile").read_text(encoding="utf-8")
    api_main = (app_dir / "api" / "src" / "main.rs").read_text(encoding="utf-8")
    nginx = (app_dir / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "APP_PORT: ${APP_PORT:-8181}" in compose
    assert "http://127.0.0.1:${APP_PORT:-8181}/healthz" in compose
    assert "DATABASE_URL: postgresql://${POSTGRES_USER:-app}:${POSTGRES_PASSWORD:-change-me}@postgres:5432/${POSTGRES_DB:-app}" in compose
    assert "APP_PORT=8181" in env_example
    assert "EXPOSE 8181" in dockerfile
    assert ".unwrap_or(8181);" in api_main
    assert "proxy_pass http://api:8181;" in nginx


def test_app_init_rejects_fixed_port_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "app.example.com", "--template", "rust-react-postgres", "--port", "postgres=6543"],
    )

    assert result.exit_code != 0
    assert "port `postgres`" in result.output
    assert "cannot be overridden" in result.output


def test_app_init_json_output_includes_selected_ports(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "notes.example.com", "--template", "node", "--port", "app=3200", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ports"] == {"app": 3200}


def test_ports_list_json_reports_detected_stack_ports(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    node_result = runner.invoke(
        app,
        ["app", "init", "notes.example.com", "--template", "node", "--port", "app=3100"],
    )
    rust_result = runner.invoke(
        app,
        ["app", "init", "app.example.com", "--template", "rust-react-postgres", "--port", "api=8181"],
    )

    assert node_result.exit_code == 0, node_result.output
    assert rust_result.exit_code == 0, rust_result.output

    result = runner.invoke(app, ["ports", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "ports_list"
    stacks = {stack["hostname"]: stack for stack in payload["stacks"]}

    node_services = {service["service"]: service["ports"] for service in stacks["notes.example.com"]["services"]}
    assert node_services["app"] == [{"port": 3100, "sources": ["Dockerfile EXPOSE", "environment PORT", "healthcheck", "traefik loadbalancer"]}]

    rust_services = {service["service"]: service["ports"] for service in stacks["app.example.com"]["services"]}
    assert rust_services["frontend"] == [{"port": 80, "sources": ["Dockerfile EXPOSE", "traefik loadbalancer"]}]
    assert rust_services["api"] == [{"port": 8181, "sources": ["Dockerfile EXPOSE", "environment APP_PORT", "healthcheck"]}]
    assert rust_services["postgres"] == [{"port": 5432, "sources": ["postgres command port"]}]


def test_ports_list_text_reports_one_stack(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    scaffold = runner.invoke(
        app,
        ["app", "init", "api.example.com", "--template", "python", "--port", "app=9100"],
    )
    assert scaffold.exit_code == 0, scaffold.output

    result = runner.invoke(app, ["ports", "list", "--stack", "api.example.com"])

    assert result.exit_code == 0, result.output
    assert "api.example.com" in result.output
    assert "app: 9100" in result.output
