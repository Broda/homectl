from __future__ import annotations

from pathlib import Path
import pytest
import typer

import yaml

from homesrvctl.config import (
    config_sources,
    init_config,
    load_config,
    load_stack_settings,
    stack_config_path,
    stack_settings_sources,
)


def test_init_and_load_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    written = init_config(config_path)

    assert written == config_path
    assert config_path.exists()

    config = load_config(config_path)
    assert config.tunnel_name == "homesrvctl-tunnel"
    assert str(config.sites_root) == "/srv/homesrvctl/sites"
    assert config.cloudflare_api_token == ""


def test_init_config_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    init_config(config_path)

    with pytest.raises(typer.BadParameter):
        init_config(config_path)


def test_load_config_uses_cloudflare_api_token_env_fallback(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    init_config(config_path)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-token")

    config = load_config(config_path)

    assert config.cloudflare_api_token == "env-token"


def test_load_stack_settings_uses_local_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    init_config(config_path)
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_data["sites_root"] = str(tmp_path / "sites")
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
    config = load_config(config_path)
    stack_dir = config.hostname_dir("example.com")
    stack_dir.mkdir(parents=True)
    stack_config_path(stack_dir).write_text(
        yaml.safe_dump(
            {
                "docker_network": "edge",
                "traefik_url": "http://localhost:9000",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    settings = load_stack_settings(config, "example.com")

    assert settings.has_local_config is True
    assert settings.docker_network == "edge"
    assert settings.traefik_url == "http://localhost:9000"


def test_stack_settings_sources_reflect_stack_local_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    init_config(config_path)
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_data["sites_root"] = str(tmp_path / "sites")
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
    config = load_config(config_path)
    stack_dir = config.hostname_dir("example.com")
    stack_dir.mkdir(parents=True)
    stack_config_path(stack_dir).write_text("traefik_url: http://localhost:9000\n", encoding="utf-8")

    settings = load_stack_settings(config, "example.com")
    sources = stack_settings_sources(config, settings)

    assert sources == {
        "docker_network": "global-config",
        "traefik_url": "stack-local",
    }


def test_config_sources_report_empty_api_token_source(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    init_config(config_path)

    config = load_config(config_path)

    assert config_sources(config)["cloudflare_api_token"] == "environment-or-empty"
