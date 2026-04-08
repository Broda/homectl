from __future__ import annotations

from pathlib import Path

import json
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
    assert (app_dir / "README.md").exists()
    assert (app_dir / "html" / "index.html").exists()
    assert (app_dir / "html" / "favicon.svg").exists()
    assert (app_dir / "html" / "assets" / "css" / "main.css").exists()
    assert (app_dir / "html" / "assets" / "js" / "main.js").exists()
    assert (app_dir / "api" / "Dockerfile").exists()
    assert (app_dir / "api" / "requirements.txt").exists()
    assert (app_dir / "api" / "app" / "main.py").exists()
    compose = (app_dir / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (app_dir / "README.md").read_text(encoding="utf-8")
    index_html = (app_dir / "html" / "index.html").read_text(encoding="utf-8")
    main_js = (app_dir / "html" / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    api_main = (app_dir / "api" / "app" / "main.py").read_text(encoding="utf-8")
    assert "site:" in compose
    assert "api:" in compose
    assert "PathPrefix(`/api`)" in compose
    assert "priority=100" in compose
    assert "docker compose up --build" in readme
    assert "/api/status" in readme
    assert "portal.example.com" in index_html
    assert "/api/status" in main_js
    assert 'self.path == "/api/status"' in api_main
    assert 'self.path == "/healthz"' in api_main


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
        lambda: CloudflaredRuntime(
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
                "warnings": [
                    "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
                    "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                ],
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
    assert payload["config_validation"]["warnings"] == [
        "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
    ]
    assert payload["config_validation"]["has_warnings"] is True
    assert payload["config_validation"]["warning_policy"] == "non-fatal"


def test_cloudflared_status_text_reports_warning_policy(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
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
                "warnings": [
                    "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
                    "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                ],
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


def test_cloudflared_status_json_failure(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
                "ok": True,
                "detail": "fallback service http_status:404",
                "command": None,
                "method": "structural",
                "warnings": [
                    "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
                    "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
                ],
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["cloudflared", "config-test"])

    assert result.exit_code == 0, result.output
    assert (
        "warning: earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first"
        in result.output
    )


def test_cloudflared_restart_json_failure(monkeypatch) -> None:
    from homesrvctl.commands import cloudflared_cmd

    monkeypatch.setattr(
        cloudflared_cmd,
        "detect_cloudflared_runtime",
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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
        lambda: CloudflaredRuntime(
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

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com"])

    assert result.exit_code == 0, result.output
    assert "Repaired domain routing for example.com" in result.output


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

    runner = CliRunner()
    result = runner.invoke(app, ["domain", "repair", "example.com", "--dry-run", "--json"])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "repair"
    assert payload["ok"] is False
    assert "duplicate ingress hostname entry found: example.com" in payload["error"]


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
    assert "FAIL ingress *.example.com: entry missing" in result.output
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
                        "detail": "multiple DNS records exist: CNAME -> wrong-target.example.com (proxied), A -> 192.0.2.10",
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
    assert "FAIL DNS example.com: multiple DNS records exist:" in result.output
    assert "Repairable by homesrvctl: no; manual cleanup is likely required first" in result.output


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
                        "detail": "A -> 192.0.2.10 (proxied)",
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
    assert payload["dns"][0]["record_type"] == "A"
    assert payload["dns"][0]["detail"] == "A -> 192.0.2.10 (proxied)"
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
        "earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
        "Hint: move example.com above *.com, or narrow/remove the earlier rule so the specific hostname matches first",
        "earlier wildcard rule *.com -> http://localhost:9000 may capture hosts intended for later wildcard *.example.com at ingress index 2. "
        "Hint: move the narrower wildcard *.example.com above *.com, or narrow/remove the broader wildcard if it is no longer needed",
    ]
    assert payload["ingress"][0]["shadowed"] is True
    assert payload["ingress"][0]["effective_hostname"] == "*.com"
    assert payload["ingress"][1]["shadowed"] is True
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
    monkeypatch.setattr(validate_cmd, "build_validate_report", lambda config: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "cloudflared binary"


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
    monkeypatch.setattr(validate_cmd, "build_hostname_doctor_report", lambda config, hostname, global_sources=None: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    _assert_schema_version(payload)
    assert payload["hostname"] == "example.com"
    assert payload["ok"] is True
    assert payload["checks"][1]["name"] == "host-header request"


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
    monkeypatch.setattr(validate_cmd, "build_hostname_doctor_report", lambda config, hostname, global_sources=None: checks)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "example.com", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    details = {item["name"]: item["detail"] for item in payload["checks"]}
    assert details["routing profile"] == "edge"
    assert details["default ingress target"] == "http://localhost:8081"
    assert details["effective ingress target"] == "http://localhost:9000 (profile:edge)"


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
        "Ingress warning: earlier ingress rule *.com -> http://localhost:9000 may shadow later hostname example.com at ingress index 1. "
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
