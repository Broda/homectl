from __future__ import annotations

import typer

from homectl.cloudflare import CloudflareApiClient, CloudflareApiError, tunnel_cname_target
from homectl.cloudflared import (
    CloudflaredConfigError,
    apply_domain_ingress,
    apply_domain_ingress_removal,
    find_exact_hostname_route,
    plan_domain_ingress,
    plan_domain_ingress_removal,
)
from homectl.config import load_config
from homectl.shell import command_exists, run_command
from homectl.utils import bullet_report, info, success, validate_bare_domain, warn

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


@domain_cli.command("remove")
def domain_remove(
    domain: str = typer.Argument(..., help="Bare domain to remove from the existing Cloudflare Tunnel setup."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without making changes."),
    restart_cloudflared: bool = typer.Option(
        False,
        "--restart-cloudflared",
        help="Restart cloudflared after ingress changes are written.",
    ),
) -> None:
    """Remove apex and wildcard tunnel DNS routes for a domain."""
    config = load_config()
    bare_domain = validate_bare_domain(domain)
    client = CloudflareApiClient(config.cloudflare_api_token)

    ingress_changed = False
    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        records = [bare_domain, f"*.{bare_domain}"]

        for record_name in records:
            if dry_run:
                plan = client.plan_dns_record_removal(zone_id, record_name)
                info(f"[dry-run] {plan.action} DNS {plan.record_type} {plan.record_name}")
                continue

            result = client.apply_dns_record_removal(zone_id, record_name)
            action_label = {
                "delete": "deleted",
                "noop": "already absent",
            }.get(result.action, result.action)
            info(f"{action_label} DNS {result.record_type} {result.record_name}")

        ingress_changes = (
            plan_domain_ingress_removal(config.cloudflared_config, bare_domain)
            if dry_run
            else apply_domain_ingress_removal(config.cloudflared_config, bare_domain)
        )
        ingress_changed = any(change.action != "noop" for change in ingress_changes)
        for change in ingress_changes:
            prefix = "[dry-run] " if dry_run else ""
            action_label = {
                "delete": "delete",
                "noop": "already absent",
            }.get(change.action, change.action)
            info(f"{prefix}{action_label} ingress {change.hostname}")
    except (CloudflareApiError, typer.BadParameter) as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    except CloudflaredConfigError as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc

    if dry_run:
        success(f"Dry-run complete for domain {bare_domain}")
        if restart_cloudflared and ingress_changed:
            info("[dry-run] systemctl restart cloudflared")
    else:
        success(f"Removed domain routing for {bare_domain}")
        if ingress_changed:
            if restart_cloudflared:
                _restart_cloudflared()
            else:
                warn("Restart cloudflared to apply ingress changes: sudo systemctl restart cloudflared")


@domain_cli.command("status")
def domain_status(
    domain: str = typer.Argument(..., help="Bare domain to inspect in Cloudflare DNS and cloudflared ingress."),
) -> None:
    """Report whether a domain is fully wired to the configured tunnel and local ingress."""
    config = load_config()
    bare_domain = validate_bare_domain(domain)
    client = CloudflareApiClient(config.cloudflare_api_token)

    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        target = tunnel_cname_target(config)
        records = [bare_domain, f"*.{bare_domain}"]

        dns_statuses = [client.get_dns_record_status(zone_id, record_name, target) for record_name in records]
        ingress_statuses = [
            (record_name, find_exact_hostname_route(config.cloudflared_config, record_name))
            for record_name in records
        ]
    except (CloudflareApiError, typer.BadParameter) as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc
    except CloudflaredConfigError as exc:
        raise typer.Exit(code=_exit_with_error(str(exc))) from exc

    info(f"Expected tunnel target: {target}")
    info(f"Expected ingress service: {config.traefik_url}")

    all_dns_ok = True
    for status in dns_statuses:
        if not status.exists:
            bullet_report("FAIL", f"DNS {status.record_name}", "record missing", False)
            all_dns_ok = False
            continue

        detail = f"{status.record_type} -> {status.content}"
        if status.proxied:
            detail += " (proxied)"
        ok = status.matches_expected
        bullet_report("PASS" if ok else "FAIL", f"DNS {status.record_name}", detail, ok)
        all_dns_ok = all_dns_ok and ok

    all_ingress_ok = True
    for hostname, service in ingress_statuses:
        if service is None:
            bullet_report("FAIL", f"ingress {hostname}", "entry missing", False)
            all_ingress_ok = False
            continue

        ok = service == config.traefik_url
        bullet_report(
            "PASS" if ok else "FAIL",
            f"ingress {hostname}",
            service,
            ok,
        )
        all_ingress_ok = all_ingress_ok and ok

    overall = _overall_domain_status(dns_statuses, ingress_statuses, config.traefik_url)
    if overall == "ok":
        success(f"Overall status for {bare_domain}: ok")
        return

    warn(f"Overall status for {bare_domain}: {overall}")
    raise typer.Exit(code=1)


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


def _overall_domain_status(dns_statuses, ingress_statuses, expected_service: str) -> str:  # noqa: ANN001
    dns_exists = [status.exists for status in dns_statuses]
    dns_matches = [status.matches_expected for status in dns_statuses]
    ingress_exists = [service is not None for _, service in ingress_statuses]
    ingress_matches = [service == expected_service for _, service in ingress_statuses]
    dns_wrong = [status.exists and not status.matches_expected for status in dns_statuses]
    ingress_wrong = [service is not None and service != expected_service for _, service in ingress_statuses]

    if all(dns_matches) and all(ingress_matches):
        return "ok"
    if any(dns_wrong) or any(ingress_wrong):
        return "misconfigured"
    if any(dns_exists) or any(ingress_exists):
        return "partial"
    return "partial"


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1
