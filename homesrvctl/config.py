from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
import yaml

from homesrvctl.models import HomesrvctlConfig, RoutingProfile, StackSettings


DEFAULT_CONFIG = HomesrvctlConfig()
STACK_CONFIG_FILENAME = "homesrvctl.yml"
CONFIG_FIELDS = (
    "tunnel_name",
    "sites_root",
    "docker_network",
    "traefik_url",
    "cloudflared_config",
    "cloudflare_api_token",
    "profiles",
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
        "profiles": {},
    }


def _read_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise typer.BadParameter(
            f"config file not found: {path}. Run `homesrvctl config init` first."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_profiles(data: Any) -> dict[str, RoutingProfile]:
    if not data:
        return {}
    if not isinstance(data, dict):
        raise typer.BadParameter("config field `profiles` must be a mapping of profile names to settings")
    profiles: dict[str, RoutingProfile] = {}
    for name, raw in data.items():
        if not isinstance(raw, dict):
            raise typer.BadParameter(f"config profile `{name}` must be a mapping")
        if "docker_network" not in raw or "traefik_url" not in raw:
            raise typer.BadParameter(
                f"config profile `{name}` must define both `docker_network` and `traefik_url`"
            )
        profiles[str(name)] = RoutingProfile(
            docker_network=str(raw["docker_network"]),
            traefik_url=str(raw["traefik_url"]),
        )
    return profiles


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
        profiles=_parse_profiles(merged.get("profiles", {})),
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
    profile_name = str(data["profile"]).strip() if "profile" in data and data["profile"] else None
    if profile_name and profile_name not in config.profiles:
        raise typer.BadParameter(
            f"unknown routing profile `{profile_name}` for {hostname}. "
            f"Configure it under `profiles` in the main config or remove the stack-local profile setting."
        )
    profile = config.profiles.get(profile_name) if profile_name else None
    merged = {
        "docker_network": config.docker_network,
        "traefik_url": config.traefik_url,
    }
    if profile:
        merged.update(
            {
                "docker_network": profile.docker_network,
                "traefik_url": profile.traefik_url,
            }
        )
    merged.update({key: value for key, value in (data or {}).items() if key in {"docker_network", "traefik_url"}})
    return StackSettings(
        hostname=hostname,
        stack_dir=stack_dir,
        config_path=path,
        profile=profile_name,
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
    if settings.profile:
        inherited_sources = {
            "docker_network": f"profile:{settings.profile}",
            "traefik_url": f"profile:{settings.profile}",
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


def render_stack_settings(
    config: HomesrvctlConfig,
    docker_network: str,
    traefik_url: str,
    profile: str | None = None,
) -> str:
    overrides: dict[str, str] = {}
    base_docker_network = config.docker_network
    base_traefik_url = config.traefik_url
    if profile:
        if profile not in config.profiles:
            raise typer.BadParameter(
                f"unknown routing profile `{profile}`. Configure it under `profiles` in the main config first."
            )
        overrides["profile"] = profile
        profile_settings = config.profiles[profile]
        base_docker_network = profile_settings.docker_network
        base_traefik_url = profile_settings.traefik_url
    if docker_network != base_docker_network:
        overrides["docker_network"] = docker_network
    if traefik_url != base_traefik_url:
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
