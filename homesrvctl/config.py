from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
import yaml

from homesrvctl.models import HomesrvctlConfig, StackSettings


DEFAULT_CONFIG = HomesrvctlConfig()
STACK_CONFIG_FILENAME = "homesrvctl.yml"
CONFIG_FIELDS = (
    "tunnel_name",
    "sites_root",
    "docker_network",
    "traefik_url",
    "cloudflared_config",
    "cloudflare_api_token",
)


def default_config_path() -> Path:
    return Path.home() / ".config" / "homesrvctl" / "config.yml"


def default_config_data() -> dict[str, Any]:
    return {
        "tunnel_name": DEFAULT_CONFIG.tunnel_name,
        "sites_root": str(DEFAULT_CONFIG.sites_root),
        "docker_network": DEFAULT_CONFIG.docker_network,
        "traefik_url": DEFAULT_CONFIG.traefik_url,
        "cloudflared_config": str(DEFAULT_CONFIG.cloudflared_config),
        "cloudflare_api_token": DEFAULT_CONFIG.cloudflare_api_token,
    }


def _read_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise typer.BadParameter(
            f"config file not found: {path}. Run `homesrvctl config init` first."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config_details(path: Path | None = None) -> tuple[HomesrvctlConfig, dict[str, str]]:
    config_path = path or default_config_path()
    data = _read_yaml_file(config_path)
    merged = {**default_config_data(), **data}
    env_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    file_api_token = str(merged["cloudflare_api_token"]).strip()
    api_token = file_api_token or env_api_token
    config = HomesrvctlConfig(
        tunnel_name=str(merged["tunnel_name"]),
        sites_root=Path(str(merged["sites_root"])),
        docker_network=str(merged["docker_network"]),
        traefik_url=str(merged["traefik_url"]),
        cloudflared_config=Path(str(merged["cloudflared_config"])),
        cloudflare_api_token=api_token,
    )
    sources = {field: ("file" if field in data else "default") for field in CONFIG_FIELDS}
    if file_api_token:
        sources["cloudflare_api_token"] = "file"
    elif env_api_token:
        sources["cloudflare_api_token"] = "environment"
    elif "cloudflare_api_token" in data:
        sources["cloudflare_api_token"] = "file-empty"
    else:
        sources["cloudflare_api_token"] = "default-empty"
    return config, sources


def load_config(path: Path | None = None) -> HomesrvctlConfig:
    config, _ = load_config_details(path)
    return config


def stack_config_path(stack_dir: Path) -> Path:
    return stack_dir / STACK_CONFIG_FILENAME


def load_stack_config_data(stack_dir: Path) -> dict[str, Any]:
    path = stack_config_path(stack_dir)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_stack_settings(config: HomesrvctlConfig, hostname: str) -> StackSettings:
    stack_dir = config.hostname_dir(hostname)
    path = stack_config_path(stack_dir)
    data = load_stack_config_data(stack_dir)
    merged = {
        "docker_network": config.docker_network,
        "traefik_url": config.traefik_url,
        **(data or {}),
    }
    return StackSettings(
        hostname=hostname,
        stack_dir=stack_dir,
        config_path=path,
        docker_network=str(merged["docker_network"]),
        traefik_url=str(merged["traefik_url"]),
        has_local_config=path.exists(),
    )


def config_sources(path: Path | None = None) -> dict[str, str]:
    _, sources = load_config_details(path)
    return sources


def stack_settings_sources(
    config: HomesrvctlConfig,
    settings: StackSettings,
    global_sources: dict[str, str] | None = None,
) -> dict[str, str]:
    data = load_stack_config_data(settings.stack_dir)
    inherited_sources = global_sources or {
        "docker_network": "global-default",
        "traefik_url": "global-default",
    }
    if not settings.has_local_config:
        return {
            "docker_network": inherited_sources["docker_network"],
            "traefik_url": inherited_sources["traefik_url"],
        }
    return {
        "docker_network": "stack-local" if "docker_network" in data else inherited_sources["docker_network"],
        "traefik_url": "stack-local" if "traefik_url" in data else inherited_sources["traefik_url"],
    }


def render_stack_settings(config: HomesrvctlConfig, docker_network: str, traefik_url: str) -> str:
    overrides: dict[str, str] = {}
    if docker_network != config.docker_network:
        overrides["docker_network"] = docker_network
    if traefik_url != config.traefik_url:
        overrides["traefik_url"] = traefik_url
    if not overrides:
        return ""
    return yaml.safe_dump(overrides, sort_keys=False)


def init_config(path: Path | None = None, force: bool = False) -> Path:
    config_path = path or default_config_path()
    if config_path.exists() and not force:
        raise typer.BadParameter(
            f"config already exists: {config_path}. Use --force to overwrite."
        )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(default_config_data(), sort_keys=False),
        encoding="utf-8",
    )
    return config_path
