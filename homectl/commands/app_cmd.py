from __future__ import annotations

import json
from typing import Literal

import typer

from homectl.config import load_config
from homectl.models import RenderContext
from homectl.templates import render_template
from homectl.utils import (
    ensure_directory,
    hostname_to_safe_name,
    success,
    validate_hostname,
    write_text_file,
)

app_cli = typer.Typer(help="Scaffold application service directories.")
TemplateName = Literal["static", "placeholder", "node"]


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
) -> None:
    """Scaffold an application directory with Compose and environment templates."""
    config = load_config()
    valid_hostname = validate_hostname(hostname)
    safe_name = hostname_to_safe_name(valid_hostname)
    target_dir = config.hostname_dir(valid_hostname)

    files = [
        str(target_dir / "docker-compose.yml"),
        str(target_dir / ".env.example"),
    ]
    if template == "node":
        files.append(str(target_dir / "README.node-template.md"))

    try:
        ensure_directory(target_dir, dry_run=dry_run, quiet=json_output)

        context = RenderContext(
            hostname=valid_hostname,
            safe_name=safe_name,
            docker_network=config.docker_network,
        )

        compose_template = _compose_template_for(template)
        compose_content = render_template(compose_template, context)
        env_content = render_template("app/env.example.j2", {"hostname": valid_hostname, "template": template})

        write_text_file(
            target_dir / "docker-compose.yml",
            compose_content,
            force=force,
            dry_run=dry_run,
            quiet=json_output,
        )
        write_text_file(
            target_dir / ".env.example",
            env_content,
            force=force,
            dry_run=dry_run,
            quiet=json_output,
        )

        if template == "node":
            placeholder = render_template("app/node.README.md.j2", {"hostname": valid_hostname})
            write_text_file(
                target_dir / "README.node-template.md",
                placeholder,
                force=force,
                dry_run=dry_run,
                quiet=json_output,
            )
    except typer.BadParameter as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "action": "app_init",
                        "hostname": valid_hostname,
                        "template": template,
                        "target_dir": str(target_dir),
                        "dry_run": dry_run,
                        "ok": False,
                        "files": files,
                        "error": str(exc),
                    },
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "action": "app_init",
                    "hostname": valid_hostname,
                    "template": template,
                    "target_dir": str(target_dir),
                    "dry_run": dry_run,
                    "ok": True,
                    "files": files,
                },
                indent=2,
            )
        )
        return

    if dry_run:
        success(f"Dry-run complete for app {valid_hostname}")
    else:
        success(f"Scaffolded app template '{template}' in {target_dir}")


def _compose_template_for(template: TemplateName) -> str:
    if template == "static":
        return "static/docker-compose.yml.j2"
    if template == "node":
        return "app/node-docker-compose.yml.j2"
    return "app/docker-compose.yml.j2"
