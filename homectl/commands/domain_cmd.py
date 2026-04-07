from __future__ import annotations

import typer

from homectl.cloudflare import CloudflareApiClient, CloudflareApiError, tunnel_cname_target
from homectl.cloudflared import (
    CloudflaredConfigError,
    apply_domain_ingress,
    plan_domain_ingress,
)
from homectl.config import load_config
from homectl.shell import command_exists, run_command
from homectl.utils import info, success, validate_bare_domain, warn

domain_cli = typer.Typer(help="Manage domain-level Cloudflare Tunnel DNS routing.")


@domain_cli.command("add")
def domain_add(
    domain: str = typer.Argument(..., help="Bare domain to route through the existing Cloudflare Tunnel."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without making changes."),
    restart_cloudflared: bool = typer.Option(
        False,
        "--restart-cloudflared",
        help="Restart cloudflared after ingress changes are written.",
    ),
) -> None:
    """Create apex and wildcard tunnel DNS routes for a domain."""
    config = load_config()
    bare_domain = validate_bare_domain(domain)
    client = CloudflareApiClient(config.cloudflare_api_token)

    ingress_changed = False
    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        target = tunnel_cname_target(config)
        records = [bare_domain, f"*.{bare_domain}"]

        for record_name in records:
            if dry_run:
                plan = client.plan_dns_record(zone_id, record_name, target)
                info(
                    f"[dry-run] {plan.action} DNS {plan.record_type} {plan.record_name} -> {plan.content}"
                )
                continue

            result = client.apply_dns_record(zone_id, record_name, target)
            action_label = {
                "create": "created",
                "update": "updated",
                "noop": "verified",
            }.get(result.action, result.action)
            info(f"{action_label} DNS {result.record_type} {result.record_name} -> {result.content}")

        ingress_changes = (
            plan_domain_ingress(config.cloudflared_config, bare_domain, config.traefik_url)
            if dry_run
            else apply_domain_ingress(config.cloudflared_config, bare_domain, config.traefik_url)
        )
        ingress_changed = any(change.action != "noop" for change in ingress_changes)
        for change in ingress_changes:
            prefix = "[dry-run] " if dry_run else ""
            action_label = {
                "create": "create",
                "update": "update",
                "noop": "verify",
            }.get(change.action, change.action)
            info(f"{prefix}{action_label} ingress {change.hostname} -> {change.service}")
    except (CloudflareApiError, typer.BadParameter) as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    except CloudflaredConfigError as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc

    if dry_run:
        success(f"Dry-run complete for domain {bare_domain}")
        if restart_cloudflared and ingress_changed:
            info("[dry-run] systemctl restart cloudflared")
    else:
        success(f"Added domain routing for {bare_domain}")
        if ingress_changed:
            if restart_cloudflared:
                _restart_cloudflared()
            else:
                warn("Restart cloudflared to apply ingress changes: sudo systemctl restart cloudflared")


def _restart_cloudflared() -> None:
    if not command_exists("systemctl"):
        warn("Ingress changed, but systemctl is not available; restart cloudflared manually")
        return

    result = run_command(["systemctl", "restart", "cloudflared"])
    if result.ok:
        success("Restarted cloudflared")
        return

    detail = result.stderr or result.stdout or "command failed"
    warn(f"Ingress changed, but cloudflared restart failed: {detail}")
    warn("Restart cloudflared manually: sudo systemctl restart cloudflared")


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1
