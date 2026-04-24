from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import typer

from homesrvctl.adoption import detect_source
from homesrvctl.config import load_config, render_stack_settings, stack_config_path
from homesrvctl.models import RenderContext
from homesrvctl.template_catalog import app_template_spec
from homesrvctl.templates import render_template
from homesrvctl.utils import (
    ensure_directory,
    hostname_to_safe_name,
    success,
    traefik_host_rule,
    validate_hostname,
    with_json_schema,
    write_text_file,
)

app_cli = typer.Typer(help="Scaffold application service directories.")


def _parse_port_overrides(template_name: str, template_ports: dict[str, int], configurable_ports: Iterable[str], raw: list[str]) -> dict[str, int]:
    if not raw:
        return dict(template_ports)

    configurable = set(configurable_ports)
    resolved = dict(template_ports)
    for entry in raw:
        if "=" not in entry:
            raise typer.BadParameter(
                f"invalid --port value `{entry}`. Expected NAME=PORT, for example `--port app=3100`."
            )
        key, raw_value = entry.split("=", 1)
        name = key.strip().lower()
        if name not in template_ports:
            available = ", ".join(sorted(template_ports))
            raise typer.BadParameter(
                f"unknown port name `{name}` for template `{template_name}`. Expected one of: {available}"
            )
        if name not in configurable:
            raise typer.BadParameter(
                f"port `{name}` for template `{template_name}` is fixed and cannot be overridden"
            )
        try:
            port = int(raw_value.strip())
        except ValueError as exc:
            raise typer.BadParameter(f"invalid port value `{raw_value}` for `{name}`") from exc
        if port < 1 or port > 65535:
            raise typer.BadParameter(f"port `{name}` must be between 1 and 65535")
        resolved[name] = port
    return resolved


@app_cli.command("detect")
def app_detect(
    source_path: Path = typer.Argument(..., help="Existing application or site source directory to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print source detection as JSON."),
) -> None:
    """Inspect an existing source directory and report the likely wrapper family."""
    expanded_source = source_path.expanduser()
    detection = detect_source(expanded_source)
    payload = {
        "action": "app_detect",
        "source_path": str(expanded_source),
        "ok": not detection.issues,
        **detection.to_dict(),
    }
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        raise typer.Exit(code=0 if payload["ok"] else 1)

    typer.echo(f"source path: {expanded_source}")
    typer.echo(f"detected family: {detection.family}")
    typer.echo(f"confidence: {detection.confidence}")
    if detection.evidence:
        typer.echo("")
        typer.echo("evidence:")
        for item in detection.evidence:
            typer.echo(f"- {item}")
    if detection.issues:
        typer.echo("")
        typer.echo("issues:")
        for item in detection.issues:
            typer.echo(f"- {item}")
    if detection.next_steps:
        typer.echo("")
        typer.echo("next steps:")
        for item in detection.next_steps:
            typer.echo(f"- {item}")
    raise typer.Exit(code=0 if payload["ok"] else 1)


@app_cli.command("init")
def app_init(
    hostname: str = typer.Argument(..., help="Hostname to scaffold."),
    template: str = typer.Option(
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
    ports: list[str] = typer.Option(
        None,
        "--port",
        help="Override a scaffold port with NAME=PORT. Repeatable for templates that expose configurable ports.",
    ),
) -> None:
    """Scaffold an application directory with Compose and environment templates."""
    config = load_config()
    valid_hostname = validate_hostname(hostname)
    safe_name = hostname_to_safe_name(valid_hostname)
    target_dir = config.hostname_dir(valid_hostname)
    try:
        template_spec = app_template_spec(template)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
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
    outputs = template_spec.render_targets(target_dir)
    files = [str(path) for path, _ in outputs]
    rendered_templates = [{"output": str(path), "template": template_name} for path, template_name in outputs]
    selected_ports = _parse_port_overrides(
        template_spec.name,
        template_spec.port_defaults,
        template_spec.configurable_ports,
        ports,
    )
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
            traefik_host_rule=traefik_host_rule(valid_hostname),
            service_name="app",
        )
        render_context = {
            "hostname": context.hostname,
            "template": template_spec.name,
            "safe_name": context.safe_name,
            "docker_network": context.docker_network,
            "traefik_host_rule": context.traefik_host_rule,
            "service_name": context.service_name,
            "ports": selected_ports,
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
                        "template": template_spec.name,
                        "target_dir": str(target_dir),
                        "profile": profile,
                        "ports": selected_ports,
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
                    "template": template_spec.name,
                    "target_dir": str(target_dir),
                    "profile": profile,
                    "ports": selected_ports,
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
        success(f"Scaffolded app template '{template_spec.name}' in {target_dir}")
