from __future__ import annotations

from pathlib import Path

import json
import pytest
import typer
import yaml
from typer.testing import CliRunner

from homesrvctl.cloudflared_service import CloudflaredRuntime
from homesrvctl.main import app


def _assert_schema_version(payload: dict[str, object]) -> None:
    assert payload["schema_version"] == "1"


def _write_config(home: Path, sites_root: Path, profiles: dict[str, dict[str, str]] | None = None) -> None:
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
    if profiles:
        config["profiles"] = profiles
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


@pytest.fixture(autouse=True)
def _default_domain_cloudflared_setup(monkeypatch) -> None:
    from homesrvctl.commands import domain_cmd

    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, *args, **kwargs: type(
            "Setup",
            (),
            {
                "ok": True,
                "setup_state": "ready",
                "mode": "systemd",
                "systemd_managed": False,
                "active": True,
                "configured_path": str(path),
                "configured_exists": True,
                "configured_writable": True,
                "configured_credentials_path": None,
                "configured_credentials_exists": None,
                "configured_credentials_readable": None,
                "configured_credentials_group_readable": None,
                "configured_credentials_owner": None,
                "configured_credentials_group": None,
                "configured_credentials_mode": None,
                "runtime_path": None,
                "runtime_exists": None,
                "runtime_readable": None,
                "paths_aligned": None,
                "ingress_mutation_available": True,
                "account_inspection_available": False,
                "service_user": None,
                "service_group": None,
                "shared_group": "homesrvctl",
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
                "issues": [],
                "next_commands": [],
                "override_path": None,
                "override_content": None,
                "notes": [],
            },
        )(),
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


def test_site_init_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com"])

    assert result.exit_code == 0, result.output
    stack_dir = sites_root / "test.example.com"
    compose = (stack_dir / "docker-compose.yml").read_text(encoding="utf-8")
    index_html = (stack_dir / "html" / "index.html").read_text(encoding="utf-8")

    assert "image: nginx:alpine" in compose
    assert "volumes:" in compose
    assert "./html:/usr/share/nginx/html:ro" in compose
    assert "traefik.http.services.test-example-com.loadbalancer.server.port=80" in compose
    assert "healthcheck:" not in compose
    assert not (stack_dir / "README.md").exists()
    assert "This site was scaffolded by homesrvctl." in index_html
    assert "<title>test.example.com</title>" in index_html


def test_site_init_writes_stack_overrides(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "site",
            "init",
            "test.example.com",
            "--docker-network",
            "edge",
            "--traefik-url",
            "http://localhost:9000",
        ],
    )

    assert result.exit_code == 0, result.output
    compose_file = sites_root / "test.example.com" / "docker-compose.yml"
    stack_config = sites_root / "test.example.com" / "homesrvctl.yml"
    assert stack_config.exists()
    assert "edge" in compose_file.read_text(encoding="utf-8")
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {
        "docker_network": "edge",
        "traefik_url": "http://localhost:9000",
    }


def test_site_init_with_profile_writes_profile_selection(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com", "--profile", "edge"])

    assert result.exit_code == 0, result.output
    compose_file = sites_root / "test.example.com" / "docker-compose.yml"
    stack_config = sites_root / "test.example.com" / "homesrvctl.yml"
    assert "edge" in compose_file.read_text(encoding="utf-8")
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"profile": "edge"}


def test_site_init_with_docker_network_override_only_writes_network_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com", "--docker-network", "edge"])

    assert result.exit_code == 0, result.output
    compose_file = sites_root / "test.example.com" / "docker-compose.yml"
    stack_config = sites_root / "test.example.com" / "homesrvctl.yml"
    assert "edge" in compose_file.read_text(encoding="utf-8")
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"docker_network": "edge"}


def test_site_init_with_traefik_override_only_writes_traefik_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com", "--traefik-url", "http://localhost:9000"])

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "test.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"traefik_url": "http://localhost:9000"}


def test_app_init_with_profile_writes_profile_selection(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "app.example.com", "--template", "node", "--profile", "edge"])

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "app.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"profile": "edge"}


def test_app_init_with_traefik_override_only_writes_traefik_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "app.example.com", "--template", "node", "--traefik-url", "http://localhost:9000"],
    )

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "app.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"traefik_url": "http://localhost:9000"}


def test_app_init_with_both_overrides_writes_both_overrides(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "app",
            "init",
            "app.example.com",
            "--template",
            "python",
            "--docker-network",
            "edge",
            "--traefik-url",
            "http://localhost:9000",
        ],
    )

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "app.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {
        "docker_network": "edge",
        "traefik_url": "http://localhost:9000",
    }


def test_app_init_node_template_creates_scaffold(monkeypatch, tmp_path: Path) -> None:
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
    assert (app_dir / ".dockerignore").exists()
    assert (app_dir / "Dockerfile").exists()
    assert (app_dir / "README.md").exists()
    assert (app_dir / "package.json").exists()
    assert (app_dir / "src" / "server.js").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    package_json = (app_dir / "package.json").read_text(encoding="utf-8")
    server_js = (app_dir / "src" / "server.js").read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile" in compose
    assert "loadbalancer.server.port=3000" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1:${PORT:-3000}/healthz" in compose
    assert "Copy to .env only if you need to override these defaults." in env_example
    assert "docker compose up --build" in readme
    assert "container becomes healthy" in readme
    assert "ENV NODE_ENV=production" in dockerfile
    assert "RUN npm install --omit=dev" in dockerfile
    assert "/healthz" in server_js
    assert "requestMethod" in server_js
    assert "\"GET /healthz\": lightweight health response used by the container healthcheck" not in readme
    assert "GET /healthz" in readme
    assert "\"start\": \"node src/server.js\"" in package_json
    assert "Replace src/server.js with your real Node application." in server_js


def test_app_init_static_template_creates_scaffold(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "www.example.com", "--template", "static"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "www.example.com"
    assert (app_dir / "docker-compose.yml").exists()
    assert (app_dir / "README.md").exists()
    assert (app_dir / "html" / "index.html").exists()
    assert (app_dir / "html" / "favicon.svg").exists()
    assert (app_dir / "html" / "assets" / "css" / "main.css").exists()
    assert (app_dir / "html" / "assets" / "js" / "main.js").exists()
    assert (app_dir / "html" / "assets" / "images" / ".gitkeep").exists()
    assert not (app_dir / ".env.example").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    index_html = (app_dir / "html" / "index.html").read_text(encoding="utf-8")
    favicon = (app_dir / "html" / "favicon.svg").read_text(encoding="utf-8")
    main_css = (app_dir / "html" / "assets" / "css" / "main.css").read_text(encoding="utf-8")
    main_js = (app_dir / "html" / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    assert "image: nginx:alpine" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1/" in compose
    assert "docker compose up -d" in readme
    assert "html/favicon.svg" in readme
    assert "html/assets/css/main.css" in readme
    assert "html/assets/js/main.js" in readme
    assert "html/assets/images/" in readme
    assert "www.example.com" in index_html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in index_html
    assert '<link rel="stylesheet" href="/assets/css/main.css">' in index_html
    assert '<script src="/assets/js/main.js"></script>' in index_html
    assert "<svg" in favicon
    assert 'aria-label="www.example.com"' in favicon
    assert "W" in favicon
    assert "font-family: Georgia" in main_css
    assert "Static site scaffold loaded for www.example.com" in main_js


def test_app_init_static_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "www.example.com", "--template", "static"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "www.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    index_html = (app_dir / "html" / "index.html").read_text(encoding="utf-8")
    main_css = (app_dir / "html" / "assets" / "css" / "main.css").read_text(encoding="utf-8")
    main_js = (app_dir / "html" / "assets" / "js" / "main.js").read_text(encoding="utf-8")

    assert "healthcheck:" in compose
    assert 'test: ["CMD-SHELL", "wget -qO- http://127.0.0.1/ >/dev/null || exit 1"]' in compose
    assert "loadbalancer.server.port=80" in compose
    assert "docker compose up -d" in readme
    assert "html/assets/images/" in readme
    assert '<link rel="stylesheet" href="/assets/css/main.css">' in index_html
    assert '<script src="/assets/js/main.js"></script>' in index_html
    assert "font-size: clamp(2.25rem, 6vw, 4rem);" in main_css
    assert 'console.log("Static site scaffold loaded for www.example.com");' in main_js
    assert not (app_dir / ".dockerignore").exists()


def test_app_init_static_api_template_creates_scaffold(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "portal.example.com", "--template", "static-api"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "portal.example.com"
    assert (app_dir / "docker-compose.yml").exists()
    assert (app_dir / ".dockerignore").exists()
    assert (app_dir / "README.md").exists()
    assert (app_dir / "html" / "index.html").exists()
    assert (app_dir / "html" / "favicon.svg").exists()
    assert (app_dir / "html" / "assets" / "css" / "main.css").exists()
    assert (app_dir / "html" / "assets" / "js" / "main.js").exists()
    assert (app_dir / "api" / "Dockerfile").exists()
    assert (app_dir / "api" / "requirements.txt").exists()
    assert (app_dir / "api" / "app" / "main.py").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (app_dir / ".dockerignore").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    index_html = (app_dir / "html" / "index.html").read_text(encoding="utf-8")
    main_js = (app_dir / "html" / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    api_main = (app_dir / "api" / "app" / "main.py").read_text(encoding="utf-8")
    assert "site:" in compose
    assert "api:" in compose
    assert "PathPrefix(`/api`)" in compose
    assert "priority=100" in compose
    assert ".env" in dockerignore
    assert "docker compose up --build" in readme
    assert "/api/status" in readme
    assert "portal.example.com" in index_html
    assert "/api/status" in main_js
    assert 'self.path == "/api/status"' in api_main
    assert 'self.path == "/healthz"' in api_main


def test_app_init_static_api_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "portal.example.com", "--template", "static-api"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "portal.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (app_dir / ".dockerignore").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    api_dockerfile = (app_dir / "api" / "Dockerfile").read_text(encoding="utf-8")
    api_main = (app_dir / "api" / "app" / "main.py").read_text(encoding="utf-8")

    assert 'test: ["CMD-SHELL", "wget -qO- http://127.0.0.1/ >/dev/null || exit 1"]' in compose
    assert 'test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8000/healthz >/dev/null || exit 1"]' in compose
    assert "traefik.http.routers.portal-example-com-api.priority=100" in compose
    assert "__pycache__" in dockerignore
    assert "api/*.pyc" in dockerignore
    assert ".env" in dockerignore
    assert ".dockerignore" in readme
    assert "python -m pip install --no-cache-dir -r requirements.txt" in api_dockerfile
    assert '"message": "Replace api/app/main.py with your real API."' in api_main


def test_app_init_python_template_creates_scaffold(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "api.example.com", "--template", "python"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "api.example.com"
    assert (app_dir / "docker-compose.yml").exists()
    assert (app_dir / ".env.example").exists()
    assert (app_dir / ".dockerignore").exists()
    assert (app_dir / "Dockerfile").exists()
    assert (app_dir / "README.md").exists()
    assert (app_dir / "requirements.txt").exists()
    assert (app_dir / "app" / "main.py").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    main_py = (app_dir / "app" / "main.py").read_text(encoding="utf-8")
    assert "loadbalancer.server.port=8000" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1:${PORT:-8000}/healthz" in compose
    assert "Copy to .env only if you need to override these defaults." in env_example
    assert "docker compose up --build" in readme
    assert "container becomes healthy" in readme
    assert "ENV PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "ENV PYTHONUNBUFFERED=1" in dockerfile
    assert "python -m pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "if self.path == \"/healthz\":" in main_py
    assert "requestMethod" in main_py
    assert "GET /healthz" in readme
    assert "Replace app/main.py with your real Python application." in main_py


def test_app_init_jekyll_template_creates_scaffold(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "blog.example.com", "--template", "jekyll"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "blog.example.com"
    assert (app_dir / "docker-compose.yml").exists()
    assert (app_dir / ".dockerignore").exists()
    assert (app_dir / "Dockerfile").exists()
    assert (app_dir / "README.md").exists()
    assert (app_dir / "site" / "Gemfile").exists()
    assert (app_dir / "site" / "_config.yml").exists()
    assert (app_dir / "site" / "index.md").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (app_dir / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    gemfile = (app_dir / "site" / "Gemfile").read_text(encoding="utf-8")
    config_yml = (app_dir / "site" / "_config.yml").read_text(encoding="utf-8")
    index_md = (app_dir / "site" / "index.md").read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile" in compose
    assert "loadbalancer.server.port=80" in compose
    assert "http://127.0.0.1/" in compose
    assert "site/_site" in dockerignore
    assert "site/.jekyll-cache" in dockerignore
    assert "FROM ruby:3.3-alpine AS build" in dockerfile
    assert "bundle exec jekyll build" in dockerfile
    assert "FROM nginx:alpine" in dockerfile
    assert "docker compose up --build" in readme
    assert "Replace the generated contents under `site/`" in readme
    assert "Gemfile" in readme
    assert 'gem "jekyll"' in gemfile
    assert 'title: "blog.example.com"' in config_yml
    assert "blog.example.com" in index_md


def test_app_init_placeholder_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "hold.example.com", "--template", "placeholder"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "hold.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")

    assert "image: nginx:alpine" in compose
    assert "loadbalancer.server.port=80" in compose
    assert "healthcheck:" not in compose
    assert "HOSTNAME=hold.example.com" in env_example
    assert "APP_TEMPLATE=placeholder" in env_example
    assert not (app_dir / "README.md").exists()
    assert not (app_dir / ".dockerignore").exists()


def test_app_init_jekyll_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "blog.example.com", "--template", "jekyll"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "blog.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore = (app_dir / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    gemfile = (app_dir / "site" / "Gemfile").read_text(encoding="utf-8")
    config_yml = (app_dir / "site" / "_config.yml").read_text(encoding="utf-8")
    index_md = (app_dir / "site" / "index.md").read_text(encoding="utf-8")

    assert "traefik.http.routers.blog-example-com.rule=Host(`blog.example.com`)" in compose
    assert "traefik.docker.network=web" in compose
    assert 'test: ["CMD-SHELL", "wget -qO- http://127.0.0.1/ >/dev/null || exit 1"]' in compose
    assert "start_period: 10s" in compose
    assert "site/.jekyll-cache" in dockerignore
    assert "site/.sass-cache" in dockerignore
    assert "site/vendor" in dockerignore
    assert "RUN apk add --no-cache build-base libffi-dev linux-headers yaml-dev zlib-dev" in dockerfile
    assert "RUN test -f Gemfile" in dockerfile
    assert "bundle config set path vendor/bundle" in dockerfile
    assert "bundle exec jekyll build --source /src --destination /out" in dockerfile
    assert "COPY --from=build /out/ /usr/share/nginx/html/" in dockerfile
    assert "keep the generated root-level stack wiring files" in readme
    assert "Replace the generated contents under `site/`" in readme
    assert "adopted source root lives directly under `site/`" in readme
    assert "gems that need extra Alpine packages during `apk add`" in readme
    assert "the generated root-level `.dockerignore`" in readme
    assert 'gem "jekyll", "~> 4.4"' in gemfile
    assert 'title: "blog.example.com"' in config_yml
    assert "layout: home" in index_md


def test_app_init_jekyll_with_profile_writes_profile_stack_config(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "blog.example.com", "--template", "jekyll", "--profile", "edge"])

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "blog.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"profile": "edge"}


def test_app_init_jekyll_with_docker_network_override_writes_stack_config(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "blog.example.com", "--template", "jekyll", "--docker-network", "edge"],
    )

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "blog.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"docker_network": "edge"}


def test_app_init_jekyll_with_traefik_override_writes_stack_config(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["app", "init", "blog.example.com", "--template", "jekyll", "--traefik-url", "http://localhost:9000"],
    )

    assert result.exit_code == 0, result.output
    stack_config = sites_root / "blog.example.com" / "homesrvctl.yml"
    overrides = yaml.safe_load(stack_config.read_text(encoding="utf-8"))
    assert overrides == {"traefik_url": "http://localhost:9000"}


def test_app_init_node_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--template", "node"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "notes.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    server_js = (app_dir / "src" / "server.js").read_text(encoding="utf-8")

    assert "PORT: ${PORT:-3000}" in compose
    assert "loadbalancer.server.port=3000" in compose
    assert "http://127.0.0.1:${PORT:-3000}/healthz" in compose
    assert "EXPOSE 3000" in dockerfile
    assert "COPY package*.json ./" in dockerfile
    assert "RUN npm install --omit=dev" in dockerfile
    assert "PORT=3000" in env_example
    assert "APP_HOSTNAME=notes.example.com" in env_example
    assert "NODE_ENV=production" in env_example
    assert "APP_TEMPLATE=" not in env_example
    assert "\nHOSTNAME=" not in env_example
    assert "port = Number.parseInt(process.env.PORT || \"3000\", 10)" in server_js
    assert "method not allowed" in server_js
    assert "https://notes.example.com/" in readme


def test_app_init_python_template_artifacts_stay_coherent(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "api.example.com", "--template", "python"])

    assert result.exit_code == 0, result.output
    app_dir = sites_root / "api.example.com"
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (app_dir / "Dockerfile").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    env_example = (app_dir / ".env.example").read_text(encoding="utf-8")
    main_py = (app_dir / "app" / "main.py").read_text(encoding="utf-8")

    assert "PORT: ${PORT:-8000}" in compose
    assert "loadbalancer.server.port=8000" in compose
    assert "http://127.0.0.1:${PORT:-8000}/healthz" in compose
    assert "EXPOSE 8000" in dockerfile
    assert "ENV PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "python -m pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "PORT=8000" in env_example
    assert "APP_HOSTNAME=api.example.com" in env_example
    assert "APP_TEMPLATE=" not in env_example
    assert "\nHOSTNAME=" not in env_example
    assert "PORT = int(os.environ.get(\"PORT\", \"8000\"))" in main_py
    assert "def _method_not_allowed(self) -> None:" in main_py
    assert "https://api.example.com/" in readme


def test_config_init_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["config", "init", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "config_init"
    assert payload["ok"] is True
    assert payload["created"] is True
    assert payload["overwrote"] is False
    assert payload["config_path"].endswith("/.config/homesrvctl/config.yml")


def test_config_init_json_reports_existing_config(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "homesrvctl"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yml"
    config_path.write_text("tunnel_name: existing\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["config", "init", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "config_init"
    assert payload["ok"] is False
    assert payload["created"] is False
    assert payload["overwrote"] is False
    assert "config already exists" in payload["error"]


def test_config_show_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["config", "show", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "config_show"
    assert payload["ok"] is True
    assert payload["global"]["sites_root"] == str(sites_root)
    assert payload["global_sources"]["docker_network"] == "file"
    assert payload["global"]["cloudflare_api_token_present"] is True


def test_config_show_json_output_with_stack(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))
    stack_dir = sites_root / "notes.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "homesrvctl.yml").write_text("traefik_url: http://localhost:9000\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["config", "show", "--stack", "notes.example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["stack"]["hostname"] == "notes.example.com"
    assert payload["stack"]["has_local_config"] is True
    assert payload["stack"]["effective"]["docker_network"] == "web"
    assert payload["stack"]["effective"]["traefik_url"] == "http://localhost:9000"
    assert payload["stack"]["effective_sources"] == {
        "docker_network": "global-file",
        "traefik_url": "stack-local",
    }
    assert payload["stack"]["local_overrides"] == {
        "traefik_url": "http://localhost:9000",
    }


def test_config_show_json_output_with_profile(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))
    stack_dir = sites_root / "notes.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "homesrvctl.yml").write_text("profile: edge\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["config", "show", "--stack", "notes.example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["global"]["profiles"]["edge"] == {
        "docker_network": "edge",
        "traefik_url": "http://localhost:9000",
    }
    assert payload["stack"]["profile"] == "edge"
    assert payload["stack"]["effective"] == {
        "docker_network": "edge",
        "traefik_url": "http://localhost:9000",
    }
    assert payload["stack"]["effective_sources"] == {
        "docker_network": "profile:edge",
        "traefik_url": "profile:edge",
    }


def test_config_show_json_output_with_profile_and_direct_override(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))
    stack_dir = sites_root / "notes.example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "homesrvctl.yml").write_text(
        yaml.safe_dump({"profile": "edge", "traefik_url": "http://localhost:9001"}, sort_keys=False),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["config", "show", "--stack", "notes.example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["stack"]["profile"] == "edge"
    assert payload["stack"]["effective"] == {
        "docker_network": "edge",
        "traefik_url": "http://localhost:9001",
    }
    assert payload["stack"]["effective_sources"] == {
        "docker_network": "profile:edge",
        "traefik_url": "stack-local",
    }
    assert payload["stack"]["local_overrides"] == {
        "profile": "edge",
        "traefik_url": "http://localhost:9001",
    }


def test_config_show_json_output_for_default_and_override_stacks(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    monkeypatch.setenv("HOME", str(home))

    default_dir = sites_root / "default.com"
    default_dir.mkdir(parents=True)
    override_dir = sites_root / "override.com"
    override_dir.mkdir(parents=True)
    (override_dir / "homesrvctl.yml").write_text(
        yaml.safe_dump({"profile": "edge", "traefik_url": "http://localhost:9001"}, sort_keys=False),
        encoding="utf-8",
    )

    runner = CliRunner()
    default_result = runner.invoke(app, ["config", "show", "--stack", "default.com", "--json"])
    override_result = runner.invoke(app, ["config", "show", "--stack", "override.com", "--json"])

    assert default_result.exit_code == 0, default_result.output
    assert override_result.exit_code == 0, override_result.output
    default_payload = json.loads(default_result.output)
    override_payload = json.loads(override_result.output)

    assert default_payload["stack"]["effective_sources"] == {
        "docker_network": "global-file",
        "traefik_url": "global-file",
    }
    assert override_payload["stack"]["effective_sources"] == {
        "docker_network": "profile:edge",
        "traefik_url": "stack-local",
    }


def test_config_show_text_output_with_stack(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["config", "show", "--stack", "notes.example.com"])

    assert result.exit_code == 0, result.output
    assert "Global configuration:" in result.output
    assert "Stack configuration for notes.example.com:" in result.output
    assert "docker_network: web (global-file)" in result.output
    assert "traefik_url: http://localhost:8081 (global-file)" in result.output


def test_site_init_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["site", "init", "test.example.com", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "site_init"
    assert payload["hostname"] == "test.example.com"
    assert payload["template"] == "static"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][0].endswith("/test.example.com/docker-compose.yml")
    assert payload["rendered_templates"][0]["template"] == "static/docker-compose.yml.j2"


def test_app_init_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--template", "node", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "app_init"
    assert payload["hostname"] == "notes.example.com"
    assert payload["template"] == "node"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][-1].endswith("/notes.example.com/src/server.js")
    assert payload["rendered_templates"][0]["template"] == "app/node/docker-compose.yml.j2"


def test_app_init_static_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "www.example.com", "--template", "static", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "app_init"
    assert payload["hostname"] == "www.example.com"
    assert payload["template"] == "static"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][-1].endswith("/www.example.com/html/assets/images/.gitkeep")
    templates = {entry["template"] for entry in payload["rendered_templates"]}
    assert templates == {
        "app/static/docker-compose.yml.j2",
        "app/static/README.md.j2",
        "app/static/index.html.j2",
        "app/static/favicon.svg.j2",
        "app/static/main.css.j2",
        "app/static/main.js.j2",
        "app/static/images.gitkeep.j2",
    }


def test_app_init_static_api_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "portal.example.com", "--template", "static-api", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "app_init"
    assert payload["hostname"] == "portal.example.com"
    assert payload["template"] == "static-api"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][-1].endswith("/portal.example.com/api/app/main.py")
    templates = {entry["template"] for entry in payload["rendered_templates"]}
    assert templates == {
        "app/static-api/docker-compose.yml.j2",
        "app/static-api/dockerignore.j2",
        "app/static-api/README.md.j2",
        "app/static-api/index.html.j2",
        "app/static-api/favicon.svg.j2",
        "app/static-api/main.css.j2",
        "app/static-api/main.js.j2",
        "app/static-api/images.gitkeep.j2",
        "app/static-api/api.Dockerfile.j2",
        "app/static-api/api.requirements.txt.j2",
        "app/static-api/api.main.py.j2",
    }


def test_app_init_json_output_reports_stack_override_file(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "app",
            "init",
            "notes.example.com",
            "--template",
            "node",
            "--docker-network",
            "edge",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["files"][-1].endswith("/notes.example.com/homesrvctl.yml")
    assert payload["rendered_templates"][-1]["template"] == "stack-config"


def test_app_init_python_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "api.example.com", "--template", "python", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "app_init"
    assert payload["hostname"] == "api.example.com"
    assert payload["template"] == "python"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][-1].endswith("/api.example.com/app/main.py")
    assert payload["rendered_templates"][-1]["template"] == "app/python/app/main.py.j2"


def test_app_init_jekyll_json_output(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "blog.example.com", "--template", "jekyll", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "app_init"
    assert payload["hostname"] == "blog.example.com"
    assert payload["template"] == "jekyll"
    assert payload["dry_run"] is True
    assert payload["ok"] is True
    assert payload["files"][-1].endswith("/blog.example.com/site/index.md")
    templates = {entry["template"] for entry in payload["rendered_templates"]}
    assert templates == {
        "app/jekyll/docker-compose.yml.j2",
        "app/jekyll/dockerignore.j2",
        "app/jekyll/Dockerfile.j2",
        "app/jekyll/README.md.j2",
        "app/jekyll/site.Gemfile.j2",
        "app/jekyll/site._config.yml.j2",
        "app/jekyll/site.index.md.j2",
    }


def test_app_init_node_json_output_lists_expected_templates(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--template", "node", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    templates = {entry["template"] for entry in payload["rendered_templates"]}
    assert templates == {
        "app/node/docker-compose.yml.j2",
        "app/node/env.example.j2",
        "app/node/dockerignore.j2",
        "app/node/Dockerfile.j2",
        "app/node/README.md.j2",
        "app/node/package.json.j2",
        "app/node/src/server.js.j2",
    }


def test_app_init_python_json_output_lists_expected_templates(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "api.example.com", "--template", "python", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    templates = {entry["template"] for entry in payload["rendered_templates"]}
    assert templates == {
        "app/python/docker-compose.yml.j2",
        "app/python/env.example.j2",
        "app/python/dockerignore.j2",
        "app/python/Dockerfile.j2",
        "app/python/README.md.j2",
        "app/python/requirements.txt.j2",
        "app/python/app/main.py.j2",
    }


def test_app_init_json_reports_overwrite_error(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    target_dir = sites_root / "notes.example.com"
    target_dir.mkdir(parents=True)
    (target_dir / "docker-compose.yml").write_text("existing\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["app", "init", "notes.example.com", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "app_init"
    assert payload["ok"] is False
    assert "refusing to overwrite existing file without --force" in payload["error"]


def test_cloudflared_status_json_output(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "load_config",
        lambda: type("Config", (), {"cloudflared_config": Path("/tmp/cloudflared.yml")})(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type(
            "Validation",
            (),
            {
                "ok": True,
                "detail": "Everything OK",
                "command": ["cloudflared", "tunnel", "--config", str(path), "ingress", "validate"],
                "method": "cloudflared",
                "issues": [
                    type(
                        "Issue",
                        (),
                        {
                            "code": "wildcard-precedence-risk",
                            "severity": "advisory",
                            "blocking": False,
                            "detail": (
                                "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for "
                                "later wildcard *.example.com at ingress index 1"
                            ),
                            "hint": (
                                "move the narrower wildcard *.example.com above *.com, or narrow/remove the broader "
                                "wildcard if it is no longer needed"
                            ),
                            "render": lambda self: (
                                "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for "
                                "later wildcard *.example.com at ingress index 1. Hint: move the narrower wildcard "
                                "*.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed"
                            ),
                        },
                    )()
                ],
                "warnings": [
                    "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard *.example.com at ingress index 1. "
                    "Hint: move the narrower wildcard *.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed"
                ],
            },
        )(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "inspect_cloudflared_setup",
        lambda path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": True,
                "mode": "docker",
                "systemd_managed": False,
                "active": True,
                "configured_path": str(path),
                "configured_exists": True,
                "configured_writable": True,
                "runtime_path": None,
                "runtime_exists": None,
                "runtime_readable": None,
                "paths_aligned": None,
                "ingress_mutation_available": True,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
                "issues": [],
                "next_commands": [],
                "override_path": None,
                "override_content": None,
                "notes": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["mode"] == "docker"
    assert payload["restart_command"] == ["docker", "restart", "cloudflared"]
    assert payload["reload_command"] is None
    assert payload["config_validation"]["ok"] is True
    assert payload["config_validation"]["issues"][0]["severity"] == "advisory"
    assert payload["config_validation"]["warnings"] == [
        "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard *.example.com at ingress index 1. "
        "Hint: move the narrower wildcard *.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed"
    ]
    assert payload["config_validation"]["has_warnings"] is True
    assert payload["config_validation"]["has_blocking_issues"] is False
    assert payload["config_validation"]["max_severity"] == "advisory"
    assert payload["config_validation"]["warning_policy"] == "non-fatal"


def test_cloudflared_status_text_reports_warning_policy(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "load_config",
        lambda: type("Config", (), {"cloudflared_config": Path("/tmp/cloudflared.yml")})(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type(
            "Validation",
            (),
            {
                "ok": True,
                "detail": "Everything OK",
                "command": None,
                "method": "structural",
                "issues": [
                    type(
                        "Issue",
                        (),
                        {
                            "code": "wildcard-precedence-risk",
                            "severity": "advisory",
                            "blocking": False,
                            "detail": (
                                "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for "
                                "later wildcard *.example.com at ingress index 1"
                            ),
                            "hint": (
                                "move the narrower wildcard *.example.com above *.com, or narrow/remove the broader "
                                "wildcard if it is no longer needed"
                            ),
                            "render": lambda self: (
                                "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for "
                                "later wildcard *.example.com at ingress index 1. Hint: move the narrower wildcard "
                                "*.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed"
                            ),
                        },
                    )()
                ],
                "warnings": [
                    "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard *.example.com at ingress index 1. "
                    "Hint: move the narrower wildcard *.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed"
                ],
            },
        )(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "inspect_cloudflared_setup",
        lambda path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": True,
                "mode": "docker",
                "systemd_managed": False,
                "active": True,
                "configured_path": str(path),
                "configured_exists": True,
                "configured_writable": True,
                "runtime_path": None,
                "runtime_exists": None,
                "runtime_readable": None,
                "paths_aligned": None,
                "ingress_mutation_available": True,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
                "issues": [],
                "next_commands": [],
                "override_path": None,
                "override_content": None,
                "notes": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "status"])

    assert result.exit_code == 0, result.output
    assert (
        "config warnings are advisory; cloudflared status remains healthy while the config stays valid"
        in result.output
    )


def test_cloudflared_status_json_reports_setup_alignment(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "load_config",
        lambda: type("Config", (), {"cloudflared_config": Path("/srv/homesrvctl/cloudflared/config.yml")})(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type("Validation", (), {"ok": True, "detail": "Everything OK", "command": None, "method": "structural", "issues": [], "warnings": []})(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "inspect_cloudflared_setup",
        lambda path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": False,
                "setup_state": "misaligned",
                "mode": "systemd",
                "systemd_managed": True,
                "active": True,
                "configured_path": str(path),
                "configured_exists": False,
                "configured_writable": False,
                "configured_credentials_path": "/etc/cloudflared/example.json",
                "configured_credentials_exists": True,
                "configured_credentials_readable": False,
                "configured_credentials_group_readable": False,
                "configured_credentials_owner": "root",
                "configured_credentials_group": "root",
                "configured_credentials_mode": "600",
                "runtime_path": "/etc/cloudflared/config.yml",
                "runtime_exists": True,
                "runtime_readable": True,
                "paths_aligned": False,
                "ingress_mutation_available": False,
                "account_inspection_available": False,
                "service_user": "root",
                "service_group": "root",
                "shared_group": "homesrvctl",
                "detail": "systemd cloudflared service uses /etc/cloudflared/config.yml, but homesrvctl is configured for /srv/homesrvctl/cloudflared/config.yml",
                "issues": ["configured cloudflared config is missing: /srv/homesrvctl/cloudflared/config.yml"],
                "next_commands": ["sudo systemctl daemon-reload"],
                "override_path": "/etc/systemd/system/cloudflared.service.d/override.conf",
                "override_content": "[Service]\nGroup=homesrvctl\nExecStart=\nExecStart=/usr/bin/cloudflared --no-autoupdate --config /srv/homesrvctl/cloudflared/config.yml tunnel run",
                "notes": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "status", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["setup"]["paths_aligned"] is False
    assert payload["setup"]["ingress_mutation_available"] is False
    assert payload["setup"]["runtime_path"] == "/etc/cloudflared/config.yml"


def test_cloudflared_setup_json_reports_commands(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "load_config",
        lambda: type("Config", (), {"cloudflared_config": Path("/srv/homesrvctl/cloudflared/config.yml")})(),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "inspect_cloudflared_setup",
        lambda path, runtime=None, quiet=False: type(
            "Setup",
            (),
            {
                "ok": False,
                "setup_state": "misaligned",
                "mode": "systemd",
                "systemd_managed": True,
                "active": True,
                "configured_path": str(path),
                "configured_exists": False,
                "configured_writable": False,
                "configured_credentials_path": "/etc/cloudflared/example.json",
                "configured_credentials_exists": True,
                "configured_credentials_readable": False,
                "configured_credentials_group_readable": False,
                "configured_credentials_owner": "root",
                "configured_credentials_group": "root",
                "configured_credentials_mode": "600",
                "runtime_path": "/etc/cloudflared/config.yml",
                "runtime_exists": True,
                "runtime_readable": True,
                "paths_aligned": False,
                "ingress_mutation_available": False,
                "account_inspection_available": False,
                "service_user": "root",
                "service_group": "root",
                "shared_group": "homesrvctl",
                "detail": "setup mismatch",
                "issues": ["configured path missing"],
                "next_commands": ["sudo groupadd -f homesrvctl"],
                "override_path": "/etc/systemd/system/cloudflared.service.d/override.conf",
                "override_content": "[Service]\nGroup=homesrvctl\nExecStart=\nExecStart=/usr/bin/cloudflared --no-autoupdate --config /srv/homesrvctl/cloudflared/config.yml tunnel run",
                "notes": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "setup", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is False
    assert payload["setup_state"] == "misaligned"
    assert payload["shared_group"] == "homesrvctl"
    assert payload["next_commands"] == ["sudo groupadd -f homesrvctl"]
    assert payload["override_path"] == "/etc/systemd/system/cloudflared.service.d/override.conf"


def test_cloudflared_status_json_failure(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="absent",
            active=False,
            detail="cloudflared not detected via systemd, docker, or process scan",
            restart_command=None,
            reload_command=None,
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
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output
    assert "Dry-run complete for cloudflared restart via systemd" in result.output


def test_cloudflared_restart_reports_unmanaged_process(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

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
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["dry_run"] is True


def test_cloudflared_logs_reports_systemd_command(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
            logs_command=["journalctl", "-u", "cloudflared", "-n", "100", "--no-pager"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "logs", "--follow"])

    assert result.exit_code == 0, result.output
    assert "journalctl -u cloudflared -n 100 --no-pager -f" in result.output


def test_cloudflared_logs_json_reports_unmanaged_process(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="process",
            active=True,
            detail="process present: 123 cloudflared",
            restart_command=None,
            reload_command=None,
            logs_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "logs", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["mode"] == "process"
    assert payload["logs_command"] is None


def test_cloudflared_config_test_reports_cli_validation(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import cloudflared_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type(
            "Validation",
            (),
            {
                "ok": True,
                "detail": "Everything OK",
                "command": ["cloudflared", "tunnel", "--config", str(path), "ingress", "validate"],
                "method": "cloudflared",
                "issues": [],
                "warnings": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "config-test"])

    assert result.exit_code == 0, result.output
    assert "$ cloudflared tunnel --config" in result.output
    assert "Everything OK" in result.output


def test_cloudflared_config_test_json_reports_structural_fallback(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import cloudflared_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type(
            "Validation",
            (),
            {
                "ok": True,
                "detail": "fallback service http_status:404",
                "command": None,
                "method": "structural",
                "issues": [],
                "warnings": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "config-test", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["method"] == "structural"
    assert payload["command"] is None
    assert payload["detail"] == "fallback service http_status:404"
    assert payload["issues"] == []
    assert payload["warnings"] == []


def test_cloudflared_config_test_reports_shadowing_warning(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import cloudflared_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        cloudflared_cmd,
        "test_cloudflared_config",
        lambda path: type(
            "Validation",
            (),
            {
                "ok": False,
                "detail": (
                    "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
                    "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                ),
                "command": None,
                "method": "structural",
                "issues": [
                    type(
                        "Issue",
                        (),
                        {
                            "code": "wildcard-shadows-hostname",
                            "severity": "blocking",
                            "blocking": True,
                            "detail": (
                                "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1"
                            ),
                            "hint": (
                                "move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                            ),
                            "render": lambda self: (
                                "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
                                "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                            ),
                        },
                    )()
                ],
                "warnings": [],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "config-test"])

    assert result.exit_code == 1, result.output
    assert (
        "blocking issue: earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
        in result.output
    )


def test_cloudflared_restart_json_failure(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="process",
            active=True,
            detail="process present: 123 cloudflared",
            restart_command=None,
            reload_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert payload["mode"] == "process"


def test_cloudflared_restart_json_failure_runtime_fields(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "restart_cloudflared_service",
        lambda: (_ for _ in ()).throw(cloudflared_cmd.CloudflaredServiceError("docker restart failed: permission denied")),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "restart", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["dry_run"] is False
    assert payload["mode"] == "docker"
    assert payload["active"] is True
    assert payload["restart_command"] == ["docker", "restart", "cloudflared"]


def test_cloudflared_reload_dry_run(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "reload", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl reload cloudflared" in result.output
    assert "Dry-run complete for cloudflared reload via systemd" in result.output


def test_cloudflared_reload_json_failure_when_unsupported(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="docker",
            active=True,
            detail="running container(s): cloudflared",
            restart_command=["docker", "restart", "cloudflared"],
            reload_command=None,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "reload", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert payload["mode"] == "docker"
    assert payload["reload_command"] is None


def test_cloudflared_reload_json_success(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "reload_cloudflared_service",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
            logs_command=["journalctl", "-u", "cloudflared", "-n", "100", "--no-pager"],
        ),
    )
    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
            logs_command=["journalctl", "-u", "cloudflared", "-n", "100", "--no-pager"],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "reload", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert payload["reload_command"] == ["systemctl", "reload", "cloudflared"]


def test_tunnel_status_json_uses_credentials_api_lookup(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import tunnel_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    credentials_path = tmp_path / "example.json"
    credentials_path.write_text('{"AccountTag":"account-456"}', encoding="utf-8")
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "homesrvctl-tunnel",
                "credentials-file": str(credentials_path),
                "ingress": [{"service": "http_status:404"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        tunnel_cmd,
        "inspect_configured_tunnel",
        lambda config: type(
            "Inspection",
            (),
            {
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "credentials+api",
                "account_id": "account-456",
                "api_available": True,
                "api_status": type(
                    "Tunnel",
                    (),
                    {
                        "id": "11111111-2222-4333-8444-555555555555",
                        "name": "homesrvctl-tunnel",
                        "status": "healthy",
                    },
                )(),
                "api_error": None,
                "resolution_error": None,
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["tunnel", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["resolved_tunnel_id"] == "11111111-2222-4333-8444-555555555555"
    assert payload["resolution_source"] == "credentials+api"
    assert payload["api_status"]["status"] == "healthy"


def test_tunnel_status_text_reports_missing_api_context(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import tunnel_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        tunnel_cmd,
        "inspect_configured_tunnel",
        lambda config: type(
            "Inspection",
            (),
            {
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "config:tunnel_name",
                "account_id": None,
                "api_available": False,
                "api_status": None,
                "api_error": None,
                "resolution_error": None,
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["tunnel", "status"])

    assert result.exit_code == 0, result.output
    assert "configured tunnel: homesrvctl-tunnel" in result.output
    assert "resolved tunnel id: 11111111-2222-4333-8444-555555555555" in result.output
    assert "api note: account-scoped tunnel inspection unavailable from local cloudflared credentials" in result.output


def test_tunnel_status_text_downgrades_credentials_permission_denied(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import tunnel_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        tunnel_cmd,
        "inspect_configured_tunnel",
        lambda config: type(
            "Inspection",
            (),
            {
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555",
                "resolution_source": "cloudflared-config:tunnel",
                "account_id": None,
                "api_available": False,
                "api_status": None,
                "api_error": "unable to read cloudflared credentials file /etc/cloudflared/example.json: [Errno 13] Permission denied",
                "resolution_error": None,
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["tunnel", "status"])

    assert result.exit_code == 0, result.output
    assert "configured tunnel: homesrvctl-tunnel" in result.output
    assert (
        "api note: account inspection unavailable: cloudflared credentials are not readable by the current user "
        "(run `homesrvctl cloudflared setup` for shared-group guidance)"
    ) in result.output
    assert "Permission denied" not in result.output


def test_tunnel_status_json_fails_when_unresolved(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import tunnel_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(
        tunnel_cmd,
        "inspect_configured_tunnel",
        lambda config: type(
            "Inspection",
            (),
            {
                "configured_tunnel": "homesrvctl-tunnel",
                "resolved_tunnel_id": None,
                "resolution_source": None,
                "account_id": "account-456",
                "api_available": True,
                "api_status": None,
                "api_error": "Cloudflare tunnel not found in account for homesrvctl-tunnel",
                "resolution_error": "Cloudflare tunnel not found in account for homesrvctl-tunnel",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["tunnel", "status", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is False
    assert payload["detail"] == "Cloudflare tunnel not found in account for homesrvctl-tunnel"


def test_domain_add_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] create DNS CNAME example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create DNS CNAME *.example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create ingress example.com -> http://localhost:8081" in result.output
    assert "[dry-run] create ingress *.example.com -> http://localhost:8081" in result.output


def test_domain_add_dry_run_uses_api_tunnel_lookup_when_local_uuid_missing(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "homesrvctl-tunnel",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [{"service": "http_status:404"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, object]:
            assert zone_name == "example.com"
            return {"id": "zone-123", "account": {"id": "account-456"}}

        def get_tunnel(self, account_id: str, tunnel_ref: str):  # noqa: ANN202
            assert account_id == "account-456"
            assert tunnel_ref == "homesrvctl-tunnel"
            return type(
                "Tunnel",
                (),
                {"id": "11111111-2222-4333-8444-555555555555", "name": tunnel_ref, "status": "healthy"},
            )()

        def plan_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            assert zone_id == "zone-123"
            assert content == "11111111-2222-4333-8444-555555555555.cfargotunnel.com"
            return type("Plan", (), {"action": "create", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] create DNS CNAME example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output


def test_domain_add_dry_run_prints_restart_command(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


def test_domain_add_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--dry-run", "--json", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "add"
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["dns"][0]["record_name"] == "example.com"
    assert payload["ingress"][1]["hostname"] == "*.example.com"
    assert payload["restart"]["restart_command"] == ["systemctl", "restart", "cloudflared"]


def test_domain_add_updates_cloudflared_ingress(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
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


def test_domain_add_uses_effective_service_for_mixed_stacks(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    default_dir = sites_root / "default.com"
    default_dir.mkdir(parents=True)
    override_dir = sites_root / "override.com"
    override_dir.mkdir(parents=True)
    (override_dir / "homesrvctl.yml").write_text(
        yaml.safe_dump({"profile": "edge", "traefik_url": "http://localhost:9001"}, sort_keys=False),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            return {"id": f"zone-{zone_name}"}

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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
            reload_command=["systemctl", "reload", "cloudflared"],
        ),
    )

    runner = CliRunner()
    default_result = runner.invoke(app, ["domain", "add", "default.com"])
    assert default_result.exit_code == 0, default_result.output
    updated = yaml.safe_load(cloudflared_config.read_text(encoding="utf-8"))
    assert updated["ingress"][:2] == [
        {"hostname": "default.com", "service": "http://localhost:8081"},
        {"hostname": "*.default.com", "service": "http://localhost:8081"},
    ]

    override_result = runner.invoke(app, ["domain", "add", "override.com"])
    assert override_result.exit_code == 0, override_result.output
    updated = yaml.safe_load(cloudflared_config.read_text(encoding="utf-8"))
    assert updated["ingress"][:4] == [
        {"hostname": "default.com", "service": "http://localhost:8081"},
        {"hostname": "*.default.com", "service": "http://localhost:8081"},
        {"hostname": "override.com", "service": "http://localhost:9001"},
        {"hostname": "*.override.com", "service": "http://localhost:9001"},
    ]


def test_domain_add_restarts_cloudflared_when_requested(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
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
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "add", "example.com", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "Restarted cloudflared via systemd" in result.output


def test_domain_repair_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "detect_cloudflared_runtime",
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--dry-run", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] update DNS CNAME example.com -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com" in result.output
    assert "[dry-run] create ingress *.example.com -> http://localhost:8081" in result.output
    assert "[dry-run] systemctl restart cloudflared" in result.output


def test_domain_repair_reports_repaired(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    monkeypatch.setattr(
        domain_cmd,
        "_build_domain_ingress_statuses",
        lambda config_path, domain, expected_service: [
            {
                "hostname": domain,
                "probe_hostname": domain,
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": domain,
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
            {
                "hostname": f"*.{domain}",
                "probe_hostname": f"_homesrvctl-probe.{domain}",
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": f"*.{domain}",
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 0, result.output
    assert "Repaired domain routing for example.com" in result.output


def test_domain_repair_refuses_partial_write_when_cloudflared_setup_is_not_ready(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    calls: list[str] = []

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, str]:
            calls.append(f"get_zone:{zone_name}")
            return {"id": "zone-123"}

        def apply_dns_record(self, zone_id: str, record_name: str, content: str):  # noqa: ANN202
            calls.append(f"apply_dns:{record_name}")
            return type("Plan", (), {"action": "update", "record_type": "CNAME", "record_name": record_name, "content": content})()

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": False,
                "systemd_managed": True,
                "paths_aligned": False,
                "detail": "systemd cloudflared service uses /etc/cloudflared/config.yml, but homesrvctl is configured for /srv/homesrvctl/cloudflared/config.yml",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 1, result.output
    assert "Run `homesrvctl cloudflared setup`" in result.output
    assert calls == []


def test_domain_repair_json_error(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    monkeypatch.setattr(
        domain_cmd,
        "_build_domain_ingress_statuses",
        lambda config_path, domain, expected_service: [
            {
                "hostname": domain,
                "probe_hostname": domain,
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": domain,
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
            {
                "hostname": f"*.{domain}",
                "probe_hostname": f"_homesrvctl-probe.{domain}",
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": f"*.{domain}",
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "repair"
    assert payload["ok"] is False
    assert "duplicate ingress hostname entry found: example.com" in payload["error"]


def test_domain_repair_reports_cloudflared_write_permission_error(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            return type(
                "Plan",
                (),
                {"action": "update", "record_type": "CNAME", "record_name": record_name, "content": content},
            )()

    original_write_text = Path.write_text

    def fake_write_text(self: Path, data: str, encoding: str | None = None, errors: str | None = None, newline: str | None = None) -> int:  # noqa: ANN001,E501
        if self == cloudflared_config:
            raise PermissionError(13, "Permission denied", str(self))
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )
    quiet_calls: list[bool] = []
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: (
            quiet_calls.append(quiet)
            or type(
                "Setup",
                (),
                {
                    "ingress_mutation_available": True,
                    "systemd_managed": False,
                    "paths_aligned": None,
                    "detail": "configured cloudflared path is ready for homesrvctl mutations",
                },
            )()
        ),
    )
    monkeypatch.setattr(Path, "write_text", fake_write_text)

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 1, result.output
    assert quiet_calls == [False]
    assert "unable to write cloudflared config" in result.output
    assert "Permission denied" in result.output
    assert "point homesrvctl and the cloudflared service at a writable config path" in result.output
    assert "Traceback" not in result.output


def test_domain_repair_json_preflight_uses_quiet_setup_inspection(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    quiet_calls: list[bool] = []

    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: (
            quiet_calls.append(quiet)
            or type(
                "Setup",
                (),
                {
                    "ingress_mutation_available": False,
                    "systemd_managed": False,
                    "paths_aligned": None,
                    "detail": "configured cloudflared path is not writable by the current user",
                },
            )()
        ),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "repair"
    assert payload["ok"] is False
    assert quiet_calls == [True]


def test_domain_remove_dry_run_prints_commands(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
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
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
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
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
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
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
        lambda quiet=False: CloudflaredRuntime(
            mode="systemd",
            active=True,
            detail="systemd service is active",
            restart_command=["systemctl", "restart", "cloudflared"],
        ),
    )
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
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
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    monkeypatch.setattr(
        domain_cmd,
        "inspect_cloudflared_setup",
        lambda path, quiet=False: type(
            "Setup",
            (),
            {
                "ingress_mutation_available": True,
                "systemd_managed": False,
                "paths_aligned": None,
                "detail": "configured cloudflared path is ready for homesrvctl mutations",
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "remove", "example.com", "--restart-cloudflared"])

    assert result.exit_code == 0, result.output
    assert "Restarted cloudflared via systemd" in result.output


def test_domain_status_reports_ok(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    monkeypatch.setattr(
        domain_cmd,
        "_build_domain_ingress_statuses",
        lambda config_path, domain, expected_service: [
            {
                "hostname": domain,
                "probe_hostname": domain,
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": domain,
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
            {
                "hostname": f"*.{domain}",
                "probe_hostname": f"_homesrvctl-probe.{domain}",
                "exists": True,
                "duplicate": False,
                "service": expected_service,
                "matches_expected": True,
                "effective_hostname": f"*.{domain}",
                "effective_service": expected_service,
                "shadowed": False,
                "detail": expected_service,
            },
        ],
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 0, result.output
    assert "PASS DNS example.com: CNAME -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)" in result.output
    assert "PASS ingress *.example.com: http://localhost:8081" in result.output
    assert "Overall status for example.com: ok" in result.output


def test_domain_status_reports_partial(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    assert "FAIL ingress *.example.com: exact entry missing" in result.output
    assert "Overall status for example.com: partial" in result.output
    assert "DNS coverage is apex-only; wildcard DNS is missing" in result.output
    assert "Ingress coverage is apex-only; wildcard ingress is missing" in result.output
    assert "Repairable by homesrvctl: yes" in result.output
    assert "Suggested command: homesrvctl domain repair example.com" in result.output


def test_domain_status_reports_misconfigured(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
                    "detail": (
                        "wrong target CNAME -> wrong-target.example.com (proxied); expected CNAME -> "
                        "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
                        if record_name == "example.com"
                        else f"CNAME -> {expected_content} (proxied)"
                    ),
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
    assert (
        "FAIL DNS example.com: wrong target CNAME -> wrong-target.example.com (proxied); expected CNAME -> "
        "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
    ) in result.output
    assert "FAIL ingress example.com: wrong target http://localhost:9000; expected http://localhost:8081" in result.output
    assert "Overall status for example.com: misconfigured" in result.output
    assert "Repairable by homesrvctl: yes" in result.output


def test_domain_status_reports_multiple_dns_records_as_manual_fix(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            if record_name == "example.com":
                return type(
                    "Status",
                    (),
                    {
                        "record_name": record_name,
                        "exists": True,
                        "record_type": "multiple",
                        "content": "",
                        "proxied": True,
                        "matches_expected": False,
                        "multiple_records": True,
                        "record_count": 2,
                        "detail": "multiple conflicting records exist: CNAME -> wrong-target.example.com (proxied), A -> 192.0.2.10",
                        "records": [
                            {"type": "CNAME", "content": "wrong-target.example.com", "proxied": True},
                            {"type": "A", "content": "192.0.2.10", "proxied": False},
                        ],
                    },
                )()
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
    assert "FAIL DNS example.com: multiple conflicting records exist:" in result.output
    assert "Repairable by homesrvctl: no; manual cleanup is likely required first" in result.output


def test_domain_status_allows_expected_cname_with_mail_records(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    class FakeClient:
        def __init__(self, api_token: str) -> None:
            assert api_token == "test-token"

        def get_zone(self, zone_name: str) -> dict[str, object]:
            return {"id": "zone-123", "account": {"id": "account-123"}}

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
                        "multiple_records": False,
                        "record_count": 3,
                        "detail": "CNAME -> 11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied); ancillary records present: MX -> route1.mx.cloudflare.net, TXT -> \"v=spf1 include:_spf.mx.cloudflare.net ~all\"",
                        "records": [
                            {"type": "CNAME", "content": expected_content, "proxied": True},
                            {"type": "MX", "content": "route1.mx.cloudflare.net", "proxied": False},
                            {"type": "TXT", "content": "\"v=spf1 include:_spf.mx.cloudflare.net ~all\"", "proxied": False},
                        ],
                    },
                )()
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
                    "multiple_records": False,
                    "record_count": 1,
                    "detail": f"CNAME -> {expected_content} (proxied)",
                    "records": [{"type": "CNAME", "content": expected_content, "proxied": True}],
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

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "partial"
    assert payload["dns"][0]["matches_expected"] is True
    assert payload["dns"][0]["multiple_records"] is False


def test_domain_status_reports_wrong_dns_type_with_explicit_detail(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            if record_name == "example.com":
                return type(
                    "Status",
                    (),
                    {
                        "record_name": record_name,
                        "exists": True,
                        "record_type": "A",
                        "content": "192.0.2.10",
                        "proxied": True,
                        "matches_expected": False,
                        "detail": (
                            "wrong type A -> 192.0.2.10 (proxied); expected CNAME -> "
                            "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
                        ),
                    },
                )()
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
    assert (
        "FAIL DNS example.com: wrong type A -> 192.0.2.10 (proxied); expected CNAME -> "
        "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
    ) in result.output


def test_domain_status_json_reports_wrong_dns_type(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            if record_name == "example.com":
                return type(
                    "Status",
                    (),
                    {
                        "record_name": record_name,
                        "exists": True,
                        "record_type": "A",
                        "content": "192.0.2.10",
                        "proxied": True,
                        "matches_expected": False,
                        "detail": (
                            "wrong type A -> 192.0.2.10 (proxied); expected CNAME -> "
                            "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
                        ),
                    },
                )()
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

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "misconfigured"
    assert payload["repairable"] is True
    assert payload["manual_fix_required"] is False
    assert payload["ingress_mutation_available"] is True
    assert payload["dns"][0]["record_type"] == "A"
    assert (
        payload["dns"][0]["detail"] == "wrong type A -> 192.0.2.10 (proxied); expected CNAME -> "
        "11111111-2222-4333-8444-555555555555.cfargotunnel.com (proxied)"
    )
    assert payload["dns"][0]["multiple_records"] is False


def test_domain_status_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    _assert_schema_version(payload)
    assert payload["domain"] == "example.com"
    assert payload["ok"] is True
    assert payload["overall"] == "ok"
    assert payload["repairable"] is False
    assert payload["manual_fix_required"] is False
    assert payload["suggested_command"] is None
    assert payload["routing"]["default"]["traefik_url"] == "http://localhost:8081"
    assert payload["routing"]["effective"]["traefik_url"] == "http://localhost:8081"
    assert payload["routing"]["effective_sources"]["traefik_url"] == "global-file"
    assert payload["dns"][0]["record_name"] == "example.com"
    assert payload["ingress"][1]["hostname"] == "*.example.com"


def test_domain_status_json_reports_repairable(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    result = runner.invoke(app, ["domain", "status", "example.com", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "partial"
    assert payload["repairable"] is True
    assert payload["manual_fix_required"] is False
    assert payload["suggested_command"] == "homesrvctl domain repair example.com"
    assert payload["coverage_issues"] == [
        "DNS coverage is apex-only; wildcard DNS is missing",
        "Ingress coverage is apex-only; wildcard ingress is missing",
    ]


def test_domain_status_uses_stack_override_ingress_service(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    stack_dir = sites_root / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "homesrvctl.yml").write_text(
        yaml.safe_dump({"traefik_url": "http://localhost:9000"}, sort_keys=False),
        encoding="utf-8",
    )
    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:9000"},
                    {"hostname": "*.example.com", "service": "http://localhost:9000"},
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
    assert payload["expected_ingress_service"] == "http://localhost:9000"
    assert payload["routing"]["default"]["traefik_url"] == "http://localhost:8081"
    assert payload["routing"]["effective"]["traefik_url"] == "http://localhost:9000"
    assert payload["routing"]["effective_sources"]["traefik_url"] == "stack-local"
    assert payload["ingress"][0]["service"] == "http://localhost:9000"


def test_domain_status_reports_profile_backed_ingress_service(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(
        home,
        sites_root,
        profiles={
            "edge": {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            }
        },
    )
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["cloudflared_config"] = str(cloudflared_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    stack_dir = sites_root / "example.com"
    stack_dir.mkdir(parents=True)
    (stack_dir / "homesrvctl.yml").write_text("profile: edge\n", encoding="utf-8")
    cloudflared_config.write_text(
        yaml.safe_dump(
            {
                "tunnel": "11111111-2222-4333-8444-555555555555",
                "credentials-file": "/etc/cloudflared/example.json",
                "ingress": [
                    {"hostname": "example.com", "service": "http://localhost:9000"},
                    {"hostname": "*.example.com", "service": "http://localhost:9000"},
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
    assert payload["expected_ingress_service"] == "http://localhost:9000"
    assert payload["routing"]["profile"] == "edge"
    assert payload["routing"]["default"]["traefik_url"] == "http://localhost:8081"
    assert payload["routing"]["effective"]["traefik_url"] == "http://localhost:9000"
    assert payload["routing"]["effective_sources"]["traefik_url"] == "profile:edge"


def test_domain_status_json_reports_wildcard_only_coverage(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            if record_name == "*.example.com":
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
                    "detail": "record missing",
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

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "partial"
    assert payload["repairable"] is True
    assert payload["coverage_issues"] == [
        "DNS coverage is wildcard-only; apex DNS is missing",
        "Ingress coverage is wildcard-only; apex ingress is missing",
    ]


def test_domain_status_reports_shadowed_ingress_as_manual_fix(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
                    {"hostname": "*.com", "service": "http://localhost:9000"},
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
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert "shadowed by earlier rule *.com -> http://localhost:9000" in result.output
    assert "Repairable by homesrvctl: no; manual cleanup is likely required first" in result.output


def test_domain_status_json_reports_shadowed_ingress_as_manual_fix(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
                    {"hostname": "*.com", "service": "http://localhost:9000"},
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

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "misconfigured"
    assert payload["repairable"] is False
    assert payload["manual_fix_required"] is True
    assert payload["suggested_command"] is None
    assert payload["ingress_warnings"] == [
        "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard *.example.com at ingress index 2. "
        "Hint: move the narrower wildcard *.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed",
    ]
    assert payload["ingress_issues"][0]["severity"] == "blocking"
    assert payload["ingress_issues"][0]["code"] == "wildcard-shadows-hostname"
    assert payload["ingress_issues"][1]["severity"] == "advisory"
    assert payload["ingress"][0]["shadowed"] is True
    assert payload["ingress"][0]["effective_hostname"] == "*.com"
    assert payload["ingress"][1]["shadowed"] is True


def test_domain_status_reports_duplicate_ingress_entries_as_manual_fix(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert "FAIL ingress example.com: duplicate exact ingress entries configured:" in result.output
    assert "Repairable by homesrvctl: no; manual cleanup is likely required first" in result.output


def test_domain_status_json_reports_duplicate_ingress_entries_as_manual_fix(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["overall"] == "misconfigured"
    assert payload["repairable"] is False
    assert payload["manual_fix_required"] is True
    assert payload["ingress"][0]["exists"] is True
    assert payload["ingress"][0]["duplicate"] is True
    assert payload["ingress"][0]["detail"].startswith("duplicate exact ingress entries configured:")
def test_domain_repair_reports_duplicate_ingress_hint(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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


def test_domain_repair_reports_dns_conflict_with_manual_cleanup_hint(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
            raise domain_cmd.CloudflareApiError(
                "multiple DNS records exist for example.com; clean them up manually before retrying"
            )

    monkeypatch.setattr(domain_cmd, "CloudflareApiClient", FakeClient)
    monkeypatch.setattr(
        domain_cmd,
        "tunnel_cname_target",
        lambda config: "11111111-2222-4333-8444-555555555555.cfargotunnel.com",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 1, result.output
    assert (
        "DNS conflict for example.com: multiple conflicting records exist; clean them up manually before retrying"
        in result.output
    )


def test_domain_status_reports_fallback_order_hint(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
    _assert_schema_version(up_payload)
    _assert_schema_version(down_payload)
    _assert_schema_version(restart_payload)

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
    from homesrvctl.commands import validate_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    checks = [
        validate_cmd.CheckResult("cloudflared binary", True, "found in PATH"),
        validate_cmd.CheckResult("docker binary", True, "found in PATH"),
    ]
    monkeypatch.setattr(validate_cmd, "build_validate_report", lambda config, quiet=False: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "cloudflared binary"


def test_bootstrap_assess_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        bootstrap_cmd,
        "assess_bootstrap",
        lambda path=None, quiet=False: type(
            "Assessment",
            (),
            {
                "ok": True,
                "bootstrap_state": "partial",
                "bootstrap_ready": False,
                "host_supported": True,
                "detail": "host is partially provisioned relative to the current bootstrap target",
                "config_path": str(home / ".config" / "homesrvctl" / "config.yml"),
                "os": {
                    "id": "debian",
                    "version_id": "12",
                    "pretty_name": "Debian GNU/Linux 12",
                    "supported": True,
                    "detail": "Debian-family host detected",
                },
                "systemd": {"present": True, "detail": "systemd detected"},
                "packages": {
                    "docker": True,
                    "docker_detail": "found in PATH",
                    "docker_compose": False,
                    "docker_compose_detail": "docker compose unavailable",
                    "cloudflared": True,
                    "cloudflared_detail": "found in PATH",
                },
                "services": {
                    "traefik_running": False,
                    "traefik_detail": "no running container matched filter name=traefik",
                    "cloudflared_active": False,
                    "cloudflared_mode": "absent",
                    "cloudflared_detail": "cloudflared not detected",
                },
                "config": {
                    "path": str(home / ".config" / "homesrvctl" / "config.yml"),
                    "exists": False,
                    "valid": False,
                    "detail": "config file not found",
                    "docker_network": "web",
                    "cloudflared_config": "/srv/homesrvctl/cloudflared/config.yml",
                    "token_present": False,
                    "token_source": "missing",
                },
                "network": {"name": "web", "exists": False, "detail": "docker network not found"},
                "cloudflare": {
                    "token_present": False,
                    "token_source": "missing",
                    "api_reachable": None,
                    "detail": "Cloudflare API token is not configured",
                },
                "issues": ["Traefik is not running", "Cloudflare API token is missing"],
                "next_steps": ["Install or start the baseline Traefik runtime expected by homesrvctl."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "assess", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_assess"
    assert payload["bootstrap_state"] == "partial"
    assert payload["host_supported"] is True
    assert payload["packages"]["docker_compose"] is False
    assert payload["cloudflare"]["token_present"] is False


def test_bootstrap_assess_fails_for_unsupported_host(monkeypatch) -> None:
    from homesrvctl.commands import bootstrap_cmd

    monkeypatch.setattr(
        bootstrap_cmd,
        "assess_bootstrap",
        lambda path=None, quiet=False: type(
            "Assessment",
            (),
            {
                "ok": False,
                "bootstrap_state": "unsupported",
                "bootstrap_ready": False,
                "host_supported": False,
                "detail": "host is outside the current bootstrap target",
                "config_path": "/home/test/.config/homesrvctl/config.yml",
                "os": {
                    "id": "fedora",
                    "version_id": "41",
                    "pretty_name": "Fedora Linux 41",
                    "supported": False,
                    "detail": "unsupported OS family: fedora",
                },
                "systemd": {"present": True, "detail": "systemd detected"},
                "packages": {
                    "docker": False,
                    "docker_detail": "missing from PATH",
                    "docker_compose": False,
                    "docker_compose_detail": "docker binary missing",
                    "cloudflared": False,
                    "cloudflared_detail": "missing from PATH",
                },
                "services": {
                    "traefik_running": False,
                    "traefik_detail": "docker binary missing",
                    "cloudflared_active": False,
                    "cloudflared_mode": "absent",
                    "cloudflared_detail": "cloudflared not detected",
                },
                "config": {
                    "path": "/home/test/.config/homesrvctl/config.yml",
                    "exists": False,
                    "valid": False,
                    "detail": "config file not found",
                    "docker_network": "web",
                    "cloudflared_config": "/srv/homesrvctl/cloudflared/config.yml",
                    "token_present": False,
                    "token_source": "missing",
                },
                "network": {"name": "web", "exists": None, "detail": "docker binary missing"},
                "cloudflare": {
                    "token_present": False,
                    "token_source": "missing",
                    "api_reachable": None,
                    "detail": "Cloudflare API token is not configured",
                },
                "issues": ["host is not in the first supported bootstrap target: Debian-family Linux with systemd"],
                "next_steps": ["Use a Debian-family Raspberry Pi OS host with systemd for the first bootstrap target."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "assess"])

    assert result.exit_code == 1, result.output
    assert "bootstrap state: unsupported" in result.output
    assert "host supported: no" in result.output


def test_bootstrap_validate_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    monkeypatch.setattr(
        bootstrap_cmd,
        "validate_bootstrap",
        lambda path=None, quiet=False: type(
            "Validation",
            (),
            {
                "ok": True,
                "validation_state": "ready",
                "bootstrap_ready": True,
                "detail": "bootstrap baseline is ready for stack creation and domain onboarding",
                "config_path": str(config_path),
                "assessment": type(
                    "Assessment",
                    (),
                    {
                        "ok": True,
                        "bootstrap_state": "ready",
                        "bootstrap_ready": True,
                        "host_supported": True,
                        "detail": "host matches the current shipped bootstrap baseline",
                        "config_path": str(config_path),
                        "os": {"pretty_name": "Debian GNU/Linux 12", "supported": True},
                        "systemd": {"present": True},
                        "packages": {"docker": True, "docker_compose": True, "cloudflared": True},
                        "services": {"traefik_running": True, "cloudflared_active": True},
                        "config": {"exists": True, "valid": True},
                        "network": {"name": "web", "exists": True},
                        "cloudflare": {"token_present": True, "api_reachable": True},
                        "issues": [],
                        "next_steps": ["Host baseline is ready for stack operations and domain onboarding."],
                    },
                )(),
                "validate_ok": True,
                "validate_blocking_failures": 0,
                "validate_advisories": 1,
                "validate_checks": [
                    {"name": "cloudflared binary", "ok": True, "detail": "found in PATH", "severity": "pass"}
                ],
                "tunnel": {"ok": True, "resolved_tunnel_id": "11111111-2222-4333-8444-555555555555"},
                "cloudflared_setup": {"ok": True, "setup_state": "ready", "detail": "shared-group cloudflared setup is ready"},
                "issues": [],
                "next_steps": ["Host baseline is ready for stack operations and domain onboarding."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "validate", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_validate"
    assert payload["validation_state"] == "ready"
    assert payload["bootstrap_ready"] is True
    assert payload["validate"]["blocking_failures"] == 0
    assert payload["cloudflared_setup"]["setup_state"] == "ready"


def test_bootstrap_validate_fails_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    monkeypatch.setattr(
        bootstrap_cmd,
        "validate_bootstrap",
        lambda path=None, quiet=False: type(
            "Validation",
            (),
            {
                "ok": False,
                "validation_state": "not_ready",
                "bootstrap_ready": False,
                "detail": "bootstrap baseline is not ready yet",
                "config_path": str(config_path),
                "assessment": type(
                    "Assessment",
                    (),
                    {
                        "ok": True,
                        "bootstrap_state": "partial",
                        "bootstrap_ready": False,
                        "host_supported": True,
                        "detail": "host is partially provisioned relative to the current bootstrap target",
                        "config_path": str(config_path),
                        "os": {"pretty_name": "Debian GNU/Linux 12", "supported": True},
                        "systemd": {"present": True},
                        "packages": {"docker": True, "docker_compose": True, "cloudflared": True},
                        "services": {"traefik_running": True, "cloudflared_active": False},
                        "config": {"exists": True, "valid": True},
                        "network": {"name": "web", "exists": True},
                        "cloudflare": {"token_present": True, "api_reachable": True},
                        "issues": ["cloudflared is not active"],
                        "next_steps": ["Install or start the cloudflared service for the shared host tunnel."],
                    },
                )(),
                "validate_ok": False,
                "validate_blocking_failures": 2,
                "validate_advisories": 0,
                "validate_checks": [
                    {"name": "cloudflared service", "ok": False, "detail": "service not active", "severity": "blocking"}
                ],
                "tunnel": {"ok": False, "detail": "configured tunnel could not be resolved"},
                "cloudflared_setup": {
                    "ok": True,
                    "setup_state": "partial",
                    "detail": "ingress mutations are ready, but account inspection is unavailable from the current user",
                },
                "issues": ["cloudflared is not active", "tunnel status: configured tunnel could not be resolved"],
                "next_steps": ["Run `homesrvctl bootstrap tunnel --account-id <cloudflare-account-id>`."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "validate"])

    assert result.exit_code == 1, result.output
    assert "validation state: not_ready" in result.output
    assert "bootstrap ready: no" in result.output


def test_bootstrap_tunnel_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    monkeypatch.setattr(
        bootstrap_cmd,
        "provision_bootstrap_tunnel",
        lambda path, account_id=None, tunnel_name=None, force=False: type(
            "Provisioned",
            (),
            {
                "ok": True,
                "created": True,
                "reused": False,
                "detail": "created Cloudflare tunnel homesrvctl-tunnel (11111111-2222-4333-8444-555555555555)",
                "config_path": str(config_path),
                "account_id": "account-123",
                "requested_tunnel": "homesrvctl-tunnel",
                "tunnel_id": "11111111-2222-4333-8444-555555555555",
                "tunnel_name": "homesrvctl-tunnel",
                "config_src": "local",
                "status": "inactive",
                "credentials_path": "/srv/homesrvctl/cloudflared/11111111-2222-4333-8444-555555555555.json",
                "cloudflared_config_path": "/srv/homesrvctl/cloudflared/config.yml",
                "config_updated": True,
                "credentials_written": True,
                "cloudflared_config_written": True,
                "next_steps": ["Run `homesrvctl tunnel status --json` to confirm tunnel resolution."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "tunnel", "--account-id", "account-123", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_tunnel"
    assert payload["created"] is True
    assert payload["tunnel"]["config_src"] == "local"
    assert payload["account_id"] == "account-123"


def test_bootstrap_tunnel_json_failure(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    def fail(path, account_id=None, tunnel_name=None, force=False):  # noqa: ANN001,ANN202
        raise typer.BadParameter("missing Cloudflare account ID for tunnel provisioning")

    monkeypatch.setattr(bootstrap_cmd, "provision_bootstrap_tunnel", fail)

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "tunnel", "--json", "--path", str(config_path)])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_tunnel"
    assert payload["ok"] is False
    assert "missing Cloudflare account ID" in payload["error"]


def test_bootstrap_runtime_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    monkeypatch.setattr(
        bootstrap_cmd,
        "provision_bootstrap_runtime",
        lambda path, operator_user=None, force=False, dry_run=False: type(
            "Provisioned",
            (),
            {
                "ok": True,
                "dry_run": dry_run,
                "detail": "host runtime baseline converged for the current bootstrap target",
                "operator_user": "broda",
                "config_path": str(config_path),
                "docker_network": "web",
                "homesrvctl_group": "homesrvctl",
                "package_commands": [["apt-get", "update"]],
                "directories": [{"path": "/srv/homesrvctl/sites", "mode": "0o2775", "existed": False}],
                "groups": [{"group": "homesrvctl", "created": True}],
                "network": {"name": "web", "created": True, "detail": "created"},
                "traefik": {
                    "compose_path": "/srv/homesrvctl/traefik/docker-compose.yml",
                    "written": True,
                    "started": True,
                },
                "next_steps": ["Run `homesrvctl validate`."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "runtime", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_runtime"
    assert payload["ok"] is True
    assert payload["traefik"]["started"] is True


def test_bootstrap_runtime_json_failure(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    def fail(path, operator_user=None, force=False, dry_run=False):  # noqa: ANN001,ANN202
        raise typer.BadParameter("bootstrap runtime requires root privileges")

    monkeypatch.setattr(bootstrap_cmd, "provision_bootstrap_runtime", fail)

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "runtime", "--json", "--path", str(config_path)])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_runtime"
    assert payload["ok"] is False
    assert "root privileges" in payload["error"]


def test_bootstrap_wiring_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"
    monkeypatch.setattr(
        bootstrap_cmd,
        "provision_bootstrap_wiring",
        lambda path, dry_run=False, force=False: type(
            "Provisioned",
            (),
            {
                "ok": True,
                "dry_run": dry_run,
                "detail": "cloudflared config and systemd wiring converged for the shared-group bootstrap model",
                "config_path": str(config_path),
                "config_created": False,
                "config_updated": True,
                "cloudflared_config_path": "/srv/homesrvctl/cloudflared/config.yml",
                "credentials_path": "/srv/homesrvctl/cloudflared/tunnel.json",
                "cloudflared_config_written": True,
                "credentials_written": True,
                "systemd_mode": "override",
                "systemd_path": "/etc/systemd/system/cloudflared.service.d/override.conf",
                "systemd_written": True,
                "service_enabled": True,
                "next_steps": ["Run `homesrvctl cloudflared status`."],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "wiring", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_wiring"
    assert payload["systemd"]["mode"] == "override"
    assert payload["service_enabled"] is True


def test_bootstrap_wiring_json_failure(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import bootstrap_cmd

    config_path = tmp_path / "home" / ".config" / "homesrvctl" / "config.yml"

    def fail(path, dry_run=False, force=False):  # noqa: ANN001,ANN202
        raise typer.BadParameter("bootstrap wiring could not find cloudflared tunnel credentials")

    monkeypatch.setattr(bootstrap_cmd, "provision_bootstrap_wiring", fail)

    runner = CliRunner()
    result = runner.invoke(app, ["bootstrap", "wiring", "--json", "--path", str(config_path)])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["action"] == "bootstrap_wiring"
    assert payload["ok"] is False
    assert "cloudflared tunnel credentials" in payload["error"]


def test_doctor_json_output(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import validate_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    checks = [
        validate_cmd.CheckResult("hostname directory", True, "/tmp/example.com"),
        validate_cmd.CheckResult("host-header request", True, "example.com returned HTTP 200"),
    ]
    monkeypatch.setattr(
        validate_cmd,
        "build_hostname_doctor_report",
        lambda config, hostname, global_sources=None, quiet=False: checks,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["hostname"] == "example.com"
    assert payload["ok"] is True
    assert payload["checks"][1]["name"] == "host-header request"
    assert payload["checks"][1]["severity"] == "pass"


def test_doctor_json_output_includes_routing_context(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import validate_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    monkeypatch.setenv("HOME", str(home))

    checks = [
        validate_cmd.CheckResult("hostname directory", True, "/tmp/example.com"),
        validate_cmd.CheckResult("routing profile", True, "edge"),
        validate_cmd.CheckResult("default ingress target", True, "http://localhost:8081"),
        validate_cmd.CheckResult("effective ingress target", True, "http://localhost:9000 (profile:edge)"),
        validate_cmd.CheckResult("host-header request", True, "example.com returned HTTP 200"),
    ]
    monkeypatch.setattr(
        validate_cmd,
        "build_hostname_doctor_report",
        lambda config, hostname, global_sources=None, quiet=False: checks,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    details = {item["name"]: item["detail"] for item in payload["checks"]}
    severities = {item["name"]: item["severity"] for item in payload["checks"]}
    assert details["routing profile"] == "edge"
    assert details["default ingress target"] == "http://localhost:8081"
    assert details["effective ingress target"] == "http://localhost:9000 (profile:edge)"
    assert severities["host-header request"] == "pass"


def test_domain_status_reports_ingress_warnings(monkeypatch, tmp_path: Path) -> None:
    from homesrvctl.commands import domain_cmd

    home = tmp_path / "home"
    sites_root = tmp_path / "sites"
    _write_config(home, sites_root)
    cloudflared_config = tmp_path / "cloudflared.yml"
    _write_cloudflared_config(cloudflared_config)
    config_path = home / ".config" / "homesrvctl" / "config.yml"
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
                    {"hostname": "*.com", "service": "http://localhost:9000"},
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
    result = runner.invoke(app, ["domain", "status", "example.com"])

    assert result.exit_code == 1, result.output
    assert (
        "Ingress blocking issue: earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
        in result.output
    )


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
    _assert_schema_version(payload)
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
