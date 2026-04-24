from __future__ import annotations

import json

import typer

from homesrvctl.config import load_config
from homesrvctl.ports import inspect_stack_ports
from homesrvctl.utils import info, validate_hostname, warn, with_json_schema

ports_cli = typer.Typer(help="Inspect scaffolded stack ports.")


@ports_cli.command("list")
def list_ports(
    stack: str | None = typer.Option(None, "--stack", help="Inspect only one hostname stack."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """List ports discovered from rendered stack files."""
    config = load_config()

    targets = []
    if stack:
        hostname = validate_hostname(stack)
        stack_dir = config.hostname_dir(hostname)
        if not stack_dir.exists():
            raise typer.BadParameter(f"hostname directory does not exist: {stack_dir}")
        targets.append((hostname, stack_dir))
    else:
        if not config.sites_root.exists():
            if json_output:
                typer.echo(
                    json.dumps(
                        with_json_schema(
                            {
                                "action": "ports_list",
                                "ok": False,
                                "sites_root": str(config.sites_root),
                                "error": f"Sites root does not exist: {config.sites_root}",
                            }
                        ),
                        indent=2,
                    )
                )
                raise typer.Exit(code=1)
            warn(f"Sites root does not exist: {config.sites_root}")
            raise typer.Exit(code=1)
        targets = [(child.name, child) for child in sorted(config.sites_root.iterdir()) if child.is_dir()]

    stacks: list[dict[str, object]] = []
    for hostname, stack_dir in targets:
        services = inspect_stack_ports(stack_dir)
        stacks.append(
            {
                "hostname": hostname,
                "stack_dir": str(stack_dir),
                "services": services,
            }
        )

    if json_output:
        typer.echo(
            json.dumps(
                with_json_schema(
                    {
                        "action": "ports_list",
                        "ok": True,
                        "sites_root": str(config.sites_root),
                        "stacks": stacks,
                    }
                ),
                indent=2,
            )
        )
        return

    if not stacks:
        warn(f"No hostnames found under {config.sites_root}")
        return

    for stack_payload in stacks:
        info(str(stack_payload["hostname"]))
        services = stack_payload["services"]
        if not services:
            typer.echo("  no detected service ports")
            continue
        for service in services:
            port_details = ", ".join(
                f"{entry['port']} ({', '.join(entry['sources'])})" for entry in service["ports"]
            )
            typer.echo(f"  {service['service']}: {port_details}")
