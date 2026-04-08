from __future__ import annotations

import json
from pathlib import Path

import typer

from homesrvctl.config import (
    default_config_path,
    init_config,
    load_config_details,
    load_stack_config_data,
    load_stack_settings,
    stack_settings_sources,
)
from homesrvctl.utils import info, success, with_json_schema

config_cli = typer.Typer(help="Manage homesrvctl configuration.")


@config_cli.command("init")
def config_init(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Write config to a custom path instead of the default user config location.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config file."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Write a starter config file."""
    target_path = path or default_config_path()
    existed = target_path.exists()
    try:
        written = init_config(path=target_path, force=force)
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema(
                        {
                            "action": "config_init",
                            "config_path": str(target_path),
                            "ok": False,
                            "created": False,
                            "overwrote": False,
                            "error": str(exc),
                        }
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise

    if json_output:
        typer.echo(
            json.dumps(
                with_json_schema(
                    {
                        "action": "config_init",
                        "config_path": str(written),
                        "ok": True,
                        "created": not existed,
                        "overwrote": existed,
                    }
                ),
                indent=2,
            )
        )
        return

    success(f"Wrote config to {written}")


@config_cli.command("show")
def config_show(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Read config from a custom path instead of the default user config location.",
    ),
    stack: str | None = typer.Option(
        None,
        "--stack",
        help="Show effective config for a specific hostname stack, including stack-local overrides.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Show global config and effective stack-local overrides."""
    target_path = path or default_config_path()
    try:
        config, global_sources = load_config_details(target_path)
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema(
                        {
                            "action": "config_show",
                            "config_path": str(target_path),
                            "ok": False,
                            "error": str(exc),
                        }
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise

    global_payload = {
        "tunnel_name": config.tunnel_name,
        "sites_root": str(config.sites_root),
        "docker_network": config.docker_network,
        "traefik_url": config.traefik_url,
        "cloudflared_config": str(config.cloudflared_config),
        "cloudflare_api_token_present": bool(config.cloudflare_api_token),
        "profiles": {
            name: {
                "docker_network": profile.docker_network,
                "traefik_url": profile.traefik_url,
            }
            for name, profile in sorted(config.profiles.items())
        },
    }
    payload: dict[str, object] = {
        "action": "config_show",
        "config_path": str(target_path),
        "ok": True,
        "global": global_payload,
        "global_sources": global_sources,
    }

    if stack:
        try:
            settings = load_stack_settings(config, stack)
        except typer.BadParameter as exc:
            if json_output:
                typer.echo(
                    json.dumps(
                        with_json_schema(
                            {
                                "action": "config_show",
                                "config_path": str(target_path),
                                "ok": False,
                                "global": global_payload,
                                "global_sources": global_sources,
                                "error": str(exc),
                            }
                        ),
                        indent=2,
                    )
                )
                raise typer.Exit(code=1) from exc
            raise
        local_overrides = load_stack_config_data(settings.stack_dir)
        payload["stack"] = {
            "hostname": stack,
            "stack_dir": str(settings.stack_dir),
            "stack_config_path": str(settings.config_path),
            "has_local_config": settings.has_local_config,
            "profile": settings.profile,
            "local_overrides": local_overrides,
            "effective": {
                "docker_network": settings.docker_network,
                "traefik_url": settings.traefik_url,
            },
            "effective_sources": stack_settings_sources(
                config,
                settings,
                {
                    "docker_network": f"global-{global_sources['docker_network']}",
                    "traefik_url": f"global-{global_sources['traefik_url']}",
                },
            ),
        }

    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        return

    info(f"Config path: {target_path}")
    info("Global configuration:")
    typer.echo(f"  tunnel_name: {config.tunnel_name}")
    typer.echo(f"  sites_root: {config.sites_root}")
    typer.echo(f"  docker_network: {config.docker_network}")
    typer.echo(f"  traefik_url: {config.traefik_url}")
    typer.echo(f"  cloudflared_config: {config.cloudflared_config}")
    typer.echo(f"  cloudflare_api_token_present: {bool(config.cloudflare_api_token)}")

    if not stack:
        return

    settings = load_stack_settings(config, stack)
    sources = stack_settings_sources(
        config,
        settings,
        {
            "docker_network": f"global-{global_sources['docker_network']}",
            "traefik_url": f"global-{global_sources['traefik_url']}",
        },
    )
    info(f"Stack configuration for {stack}:")
    typer.echo(f"  stack_dir: {settings.stack_dir}")
    typer.echo(f"  stack_config_path: {settings.config_path}")
    typer.echo(f"  has_local_config: {settings.has_local_config}")
    typer.echo(f"  profile: {settings.profile}")
    typer.echo("  effective:")
    typer.echo(f"    docker_network: {settings.docker_network} ({sources['docker_network']})")
    typer.echo(f"    traefik_url: {settings.traefik_url} ({sources['traefik_url']})")
