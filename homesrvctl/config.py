from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
import yaml

from homesrvctl.models import HomesrvctlConfig, StackSettings


DEFAULT_CONFIG = HomesrvctlConfig()
STACK_CONFIG_FILENAME = "homesrvctl.yml"


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


def load_config(path: Path | None = None) -> HomesrvctlConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        raise typer.BadParameter(
            f"config file not found: {config_path}. Run `homesrvctl config init` first."
        )

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    merged = {**default_config_data(), **data}
    api_token = str(merged["cloudflare_api_token"]).strip() or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    return HomesrvctlConfig(
        tunnel_name=str(merged["tunnel_name"]),
        sites_root=Path(str(merged["sites_root"])),
        docker_network=str(merged["docker_network"]),
        traefik_url=str(merged["traefik_url"]),
        cloudflared_config=Path(str(merged["cloudflared_config"])),
        cloudflare_api_token=api_token,
    )


def stack_config_path(stack_dir: Path) -> Path:
    return stack_dir / STACK_CONFIG_FILENAME


def load_stack_settings(config: HomesrvctlConfig, hostname: str) -> StackSettings:
    stack_dir = config.hostname_dir(hostname)
    path = stack_config_path(stack_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
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


def config_sources(config: HomesrvctlConfig) -> dict[str, str]:
    return {
        "tunnel_name": "config",
        "sites_root": "config",
        "docker_network": "config",
        "traefik_url": "config",
        "cloudflared_config": "config",
        "cloudflare_api_token": "config" if config.cloudflare_api_token else "environment-or-empty",
    }


def stack_settings_sources(config: HomesrvctlConfig, settings: StackSettings) -> dict[str, str]:
    if not settings.has_local_config:
        return {
            "docker_network": "global-config",
            "traefik_url": "global-config",
        }
    return {
        "docker_network": "stack-local" if settings.docker_network != config.docker_network else "global-config",
        "traefik_url": "stack-local" if settings.traefik_url != config.traefik_url else "global-config",
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
