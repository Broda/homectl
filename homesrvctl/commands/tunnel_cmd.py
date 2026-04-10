from __future__ import annotations

import json

import typer

from homesrvctl.cloudflare import CloudflareApiError, inspect_configured_tunnel
from homesrvctl.config import load_config
from homesrvctl.utils import info, success, warn, with_json_schema

tunnel_cli = typer.Typer(help="Inspect the configured Cloudflare Tunnel reference.")


@tunnel_cli.command("status")
def tunnel_status(
    json_output: bool = typer.Option(False, "--json", help="Print the tunnel status as JSON."),
) -> None:
    """Show the configured tunnel reference, resolved UUID, and API status when available."""
    try:
        config = load_config()
        inspection = inspect_configured_tunnel(config)
    except (CloudflareApiError, typer.BadParameter) as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    with_json_schema({
                        "ok": False,
                        "configured_tunnel": "",
                        "resolved_tunnel_id": None,
                        "resolution_source": None,
                        "account_id": None,
                        "api_available": False,
                        "api_status": None,
                        "api_error": None,
                        "detail": str(exc),
                    }),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc

    ok = inspection.resolved_tunnel_id is not None
    payload = with_json_schema({
        "ok": ok,
        "configured_tunnel": inspection.configured_tunnel,
        "resolved_tunnel_id": inspection.resolved_tunnel_id,
        "resolution_source": inspection.resolution_source,
        "account_id": inspection.account_id,
        "api_available": inspection.api_available,
        "api_status": (
            None
            if inspection.api_status is None
            else {
                "id": inspection.api_status.id,
                "name": inspection.api_status.name,
                "status": inspection.api_status.status,
            }
        ),
        "api_error": inspection.api_error,
        "detail": inspection.resolution_error if not ok else None,
    })

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        if ok:
            success(f"configured tunnel: {inspection.configured_tunnel}")
            info(f"resolved tunnel id: {inspection.resolved_tunnel_id}")
            info(f"resolution source: {inspection.resolution_source}")
        else:
            warn(f"configured tunnel: {inspection.configured_tunnel}")
            warn(inspection.resolution_error or "could not resolve tunnel ID")
        if inspection.account_id:
            info(f"account id: {inspection.account_id}")
        if inspection.api_status is not None:
            api_name = inspection.api_status.name or inspection.configured_tunnel
            info(f"api status: {inspection.api_status.status or 'unknown'} ({api_name})")
        elif inspection.api_error:
            warn(f"api detail: {inspection.api_error}")
        elif not inspection.api_available:
            warn("api detail: account-scoped tunnel inspection unavailable from local cloudflared credentials")

    if not ok:
        raise typer.Exit(code=1)


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1
