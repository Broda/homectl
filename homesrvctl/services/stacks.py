from __future__ import annotations

from pathlib import Path

import typer

from homesrvctl.config import load_stack_config_data, load_stack_settings, stack_config_path
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.state.models import StackSnapshot
from homesrvctl.utils import validate_hostname


def iter_stack_dirs(config: HomesrvctlConfig) -> list[Path]:
    if not config.sites_root.exists():
        return []
    return sorted(path for path in config.sites_root.iterdir() if path.is_dir())


def inspect_stack(config: HomesrvctlConfig, hostname: str) -> tuple[StackSnapshot, list[str]]:
    valid_hostname = validate_hostname(hostname)
    stack_dir = config.hostname_dir(valid_hostname)
    if not stack_dir.exists() or not stack_dir.is_dir():
        raise typer.BadParameter(f"hostname directory does not exist: {stack_dir}")

    issues: list[str] = []
    compose_file = stack_dir / "docker-compose.yml"
    has_stack_config = stack_config_path(stack_dir).exists()
    local_data = load_stack_config_data(stack_dir)
    scaffold = local_data.get("scaffold", {})
    if not isinstance(scaffold, dict):
        scaffold = {}

    profile = str(local_data["profile"]).strip() if local_data.get("profile") else None
    docker_network = None
    traefik_url = None
    try:
        settings = load_stack_settings(config, valid_hostname)
        profile = settings.profile
        docker_network = settings.docker_network
        traefik_url = settings.traefik_url
    except typer.BadParameter as exc:
        issues.append(str(exc))
        docker_network = str(local_data["docker_network"]) if local_data.get("docker_network") else None
        traefik_url = str(local_data["traefik_url"]) if local_data.get("traefik_url") else None

    snapshot = StackSnapshot(
        hostname=valid_hostname,
        stack_dir=stack_dir,
        compose_file=compose_file if compose_file.exists() else None,
        has_compose=compose_file.exists(),
        has_stack_config=has_stack_config,
        scaffold_kind=str(scaffold["kind"]) if scaffold.get("kind") else None,
        scaffold_template=(
            str(scaffold.get("template") or scaffold.get("family"))
            if (scaffold.get("template") or scaffold.get("family"))
            else None
        ),
        profile=profile,
        docker_network=docker_network,
        traefik_url=traefik_url,
    )
    return snapshot, issues
