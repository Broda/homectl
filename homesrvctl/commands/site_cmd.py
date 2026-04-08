from __future__ import annotations

import json

import typer

from homesrvctl.config import load_config, render_stack_settings, stack_config_path
from homesrvctl.models import RenderContext
from homesrvctl.templates import render_template
from homesrvctl.utils import (
    ensure_directory,
    hostname_to_safe_name,
    success,
    validate_hostname,
    with_json_schema,
    write_text_file,
)

site_cli = typer.Typer(help="Scaffold static sites.")


@site_cli.command("init")
def site_init(
    hostname: str = typer.Argument(..., help="Hostname to scaffold."),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files if they already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned file operations without writing files."),
    json_output: bool = typer.Option(False, "--json", help="Print the scaffold result as JSON."),
    docker_network: str | None = typer.Option(None, "--docker-network", help="Override the docker network for this stack."),
    traefik_url: str | None = typer.Option(None, "--traefik-url", help="Override the ingress target for this stack."),
) -> None:
    """Scaffold a static site using nginx and Traefik labels."""
    config = load_config()
    valid_hostname = validate_hostname(hostname)
    safe_name = hostname_to_safe_name(valid_hostname)
    target_dir = config.hostname_dir(valid_hostname)
    html_dir = target_dir / "html"
    effective_docker_network = docker_network or config.docker_network
    effective_traefik_url = traefik_url or config.traefik_url

    files = [
        str(target_dir / "docker-compose.yml"),
        str(html_dir / "index.html"),
    ]
    rendered_templates = [
        {"output": str(target_dir / "docker-compose.yml"), "template": "static/docker-compose.yml.j2"},
        {"output": str(html_dir / "index.html"), "template": "static/index.html.j2"},
    ]
    stack_settings_content = render_stack_settings(config, effective_docker_network, effective_traefik_url)
    if stack_settings_content.strip():
        files.append(str(stack_config_path(target_dir)))
        rendered_templates.append({"output": str(stack_config_path(target_dir)), "template": "stack-config"})

    try:
        ensure_directory(target_dir, dry_run=dry_run, quiet=json_output)
        ensure_directory(html_dir, dry_run=dry_run, quiet=json_output)

        context = RenderContext(
            hostname=valid_hostname,
            safe_name=safe_name,
            docker_network=effective_docker_network,
        )

        compose_content = render_template("static/docker-compose.yml.j2", context)
        index_content = render_template("static/index.html.j2", context)

        write_text_file(
            target_dir / "docker-compose.yml",
            compose_content,
            force=force,
            dry_run=dry_run,
            quiet=json_output,
        )
        write_text_file(
            html_dir / "index.html",
            index_content,
            force=force,
            dry_run=dry_run,
            quiet=json_output,
        )
        if stack_settings_content.strip():
            write_text_file(
                stack_config_path(target_dir),
                stack_settings_content,
                force=force,
                dry_run=dry_run,
                quiet=json_output,
            )
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema({
                        "action": "site_init",
                        "hostname": valid_hostname,
                        "target_dir": str(target_dir),
                        "template": "static",
                        "dry_run": dry_run,
                        "ok": False,
                        "files": files,
                        "rendered_templates": rendered_templates,
                        "error": str(exc),
                    }),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise

    if json_output:
        typer.echo(
            json.dumps(
                with_json_schema({
                    "action": "site_init",
                    "hostname": valid_hostname,
                    "target_dir": str(target_dir),
                    "template": "static",
                    "dry_run": dry_run,
                    "ok": True,
                    "files": files,
                    "rendered_templates": rendered_templates,
                }),
                indent=2,
            )
        )
        return

    if dry_run:
        success(f"Dry-run complete for site {valid_hostname}")
    else:
        success(f"Scaffolded static site in {target_dir}")
