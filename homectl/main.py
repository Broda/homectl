from __future__ import annotations

import typer

from homectl.commands.app_cmd import app_cli
from homectl.commands.cloudflared_cmd import cloudflared_cli
from homectl.commands.config_cmd import config_cli
from homectl.commands.deploy_cmd import doctor, down, list_sites_with_format, restart, up
from homectl.commands.domain_cmd import domain_cli
from homectl.commands.site_cmd import site_cli
from homectl.commands.validate_cmd import validate_with_format

app = typer.Typer(
    name="homectl",
    help="Manage home-server domains, site scaffolds, Compose stacks, and environment validation.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(config_cli, name="config")
app.add_typer(cloudflared_cli, name="cloudflared")
app.add_typer(domain_cli, name="domain")
app.add_typer(site_cli, name="site")
app.add_typer(app_cli, name="app")

app.command("up")(up)
app.command("down")(down)
app.command("restart")(restart)
app.command("list")(list_sites_with_format)
app.command("validate")(validate_with_format)
app.command("doctor")(doctor)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
