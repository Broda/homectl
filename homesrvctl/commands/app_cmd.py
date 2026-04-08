from __future__ import annotations

import json
from typing import Literal

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

app_cli = typer.Typer(help="Scaffold application service directories.")
TemplateName = Literal["static", "static-api", "placeholder", "node", "python"]


@app_cli.command("init")
def app_init(
    hostname: str = typer.Argument(..., help="Hostname to scaffold."),
    template: TemplateName = typer.Option(
        "placeholder",
        "--template",
        help="Template name to use for the application scaffold.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files if they already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned file operations without writing files."),
    json_output: bool = typer.Option(False, "--json", help="Print the scaffold result as JSON."),
    profile: str | None = typer.Option(None, "--profile", help="Use a named routing profile from the main config."),
    docker_network: str | None = typer.Option(None, "--docker-network", help="Override the docker network for this stack."),
    traefik_url: str | None = typer.Option(None, "--traefik-url", help="Override the ingress target for this stack."),
) -> None:
    """Scaffold an application directory with Compose and environment templates."""
    config = load_config()
    valid_hostname = validate_hostname(hostname)
    safe_name = hostname_to_safe_name(valid_hostname)
    target_dir = config.hostname_dir(valid_hostname)
    profile_settings = None
    if profile:
        profile_settings = config.profiles.get(profile)
        if profile_settings is None:
            raise typer.BadParameter(
                f"unknown routing profile `{profile}`. Configure it under `profiles` in the main config first."
            )
    effective_docker_network = docker_network or (
        profile_settings.docker_network if profile_settings else config.docker_network
    )
    effective_traefik_url = traefik_url or (
        profile_settings.traefik_url if profile_settings else config.traefik_url
    )
    outputs = _template_outputs(target_dir, template)
    files = [str(path) for path, _ in outputs]
    rendered_templates = [{"output": str(path), "template": template_name} for path, template_name in outputs]
    stack_settings_content = render_stack_settings(config, effective_docker_network, effective_traefik_url, profile)
    if stack_settings_content.strip():
        files.append(str(stack_config_path(target_dir)))
        rendered_templates.append({"output": str(stack_config_path(target_dir)), "template": "stack-config"})

    try:
        ensure_directory(target_dir, dry_run=dry_run, quiet=json_output)

        context = RenderContext(
            hostname=valid_hostname,
            safe_name=safe_name,
            docker_network=effective_docker_network,
            service_name="app",
        )
        render_context = {
            "hostname": context.hostname,
            "template": template,
            "safe_name": context.safe_name,
            "docker_network": context.docker_network,
            "service_name": context.service_name,
        }
        for output_path, template_name in outputs:
            content = render_template(template_name, render_context)
            write_text_file(
                output_path,
                content,
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
                        "action": "app_init",
                        "hostname": valid_hostname,
                        "template": template,
                        "target_dir": str(target_dir),
                        "profile": profile,
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
                    "action": "app_init",
                    "hostname": valid_hostname,
                    "template": template,
                    "target_dir": str(target_dir),
                    "profile": profile,
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
        success(f"Dry-run complete for app {valid_hostname}")
    else:
        success(f"Scaffolded app template '{template}' in {target_dir}")


def _template_outputs(target_dir, template: TemplateName) -> list[tuple]:  # noqa: ANN001
    if template == "static":
        return [
            (target_dir / "docker-compose.yml", "app/static/docker-compose.yml.j2"),
            (target_dir / "README.md", "app/static/README.md.j2"),
            (target_dir / "html" / "index.html", "app/static/index.html.j2"),
            (target_dir / "html" / "favicon.svg", "app/static/favicon.svg.j2"),
            (target_dir / "html" / "assets" / "css" / "main.css", "app/static/main.css.j2"),
            (target_dir / "html" / "assets" / "js" / "main.js", "app/static/main.js.j2"),
            (target_dir / "html" / "assets" / "images" / ".gitkeep", "app/static/images.gitkeep.j2"),
        ]
    if template == "static-api":
        return [
            (target_dir / "docker-compose.yml", "app/static-api/docker-compose.yml.j2"),
            (target_dir / "README.md", "app/static-api/README.md.j2"),
            (target_dir / "html" / "index.html", "app/static-api/index.html.j2"),
            (target_dir / "html" / "favicon.svg", "app/static-api/favicon.svg.j2"),
            (target_dir / "html" / "assets" / "css" / "main.css", "app/static-api/main.css.j2"),
            (target_dir / "html" / "assets" / "js" / "main.js", "app/static-api/main.js.j2"),
            (target_dir / "html" / "assets" / "images" / ".gitkeep", "app/static-api/images.gitkeep.j2"),
            (target_dir / "api" / "Dockerfile", "app/static-api/api.Dockerfile.j2"),
            (target_dir / "api" / "requirements.txt", "app/static-api/api.requirements.txt.j2"),
            (target_dir / "api" / "app" / "main.py", "app/static-api/api.main.py.j2"),
        ]
    if template == "node":
        return [
            (target_dir / "docker-compose.yml", "app/node/docker-compose.yml.j2"),
            (target_dir / ".env.example", "app/node/env.example.j2"),
            (target_dir / ".dockerignore", "app/node/dockerignore.j2"),
            (target_dir / "Dockerfile", "app/node/Dockerfile.j2"),
            (target_dir / "README.md", "app/node/README.md.j2"),
            (target_dir / "package.json", "app/node/package.json.j2"),
            (target_dir / "src" / "server.js", "app/node/src/server.js.j2"),
        ]
    if template == "python":
        return [
            (target_dir / "docker-compose.yml", "app/python/docker-compose.yml.j2"),
            (target_dir / ".env.example", "app/python/env.example.j2"),
            (target_dir / ".dockerignore", "app/python/dockerignore.j2"),
            (target_dir / "Dockerfile", "app/python/Dockerfile.j2"),
            (target_dir / "README.md", "app/python/README.md.j2"),
            (target_dir / "requirements.txt", "app/python/requirements.txt.j2"),
            (target_dir / "app" / "main.py", "app/python/app/main.py.j2"),
        ]
    return [
        (target_dir / "docker-compose.yml", "app/placeholder/docker-compose.yml.j2"),
        (target_dir / ".env.example", "app/placeholder/env.example.j2"),
    ]
