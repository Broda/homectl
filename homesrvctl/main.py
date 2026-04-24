from __future__ import annotations

import typer

from homesrvctl.commands.app_cmd import app_cli
from homesrvctl.commands.bootstrap_cmd import bootstrap_cli
from homesrvctl.commands.cloudflared_cmd import cloudflared_cli
from homesrvctl.commands.config_cmd import config_cli
from homesrvctl.commands.deploy_cmd import doctor, down, list_sites_with_format, restart, up
from homesrvctl.commands.domain_cmd import domain_cli
from homesrvctl.commands.ports_cmd import ports_cli
from homesrvctl.commands.site_cmd import site_cli
from homesrvctl.commands.tunnel_cmd import tunnel_cli
from homesrvctl.commands.tui_cmd import launch_tui, tui
from homesrvctl.commands.validate_cmd import validate_with_format

app = typer.Typer(
    name="homesrvctl",
    help="Manage home-server domains, site scaffolds, Compose stacks, and environment validation.",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)

app.add_typer(config_cli, name="config")
app.add_typer(bootstrap_cli, name="bootstrap")
app.add_typer(cloudflared_cli, name="cloudflared")
app.add_typer(domain_cli, name="domain")
app.add_typer(tunnel_cli, name="tunnel")
app.add_typer(ports_cli, name="ports")
app.add_typer(site_cli, name="site")
app.add_typer(app_cli, name="app")

app.command("up")(up)
app.command("down")(down)
app.command("restart")(restart)
app.command("list")(list_sites_with_format)
app.command("validate")(validate_with_format)
app.command("doctor")(doctor)
app.command("tui")(tui)


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        launch_tui()


def run() -> None:
    app()


if __name__ == "__main__":
    run()
