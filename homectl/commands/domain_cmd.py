from __future__ import annotations

import json

import typer

from homectl.cloudflare import CloudflareApiClient, CloudflareApiError, tunnel_cname_target
from homectl.cloudflared import (
    CloudflaredConfigError,
    apply_domain_ingress,
    apply_domain_ingress_removal,
    describe_cloudflared_config_error,
    find_exact_hostname_route,
    plan_domain_ingress,
    plan_domain_ingress_removal,
)
from homectl.cloudflared_service import (
    CloudflaredServiceError,
    detect_cloudflared_runtime,
    restart_cloudflared_service,
)
from homectl.config import load_config
from homectl.utils import bullet_report, info, success, validate_bare_domain, warn

domain_cli = typer.Typer(help="Manage domain-level Cloudflare Tunnel DNS routing.")


@domain_cli.command("add")
def domain_add(
    domain: str = typer.Argument(..., help="Bare domain to route through the existing Cloudflare Tunnel."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without making changes."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    restart_cloudflared: bool = typer.Option(
        False,
        "--restart-cloudflared",
        help="Restart cloudflared after ingress changes are written.",
    ),
) -> None:
    """Create apex and wildcard tunnel DNS routes for a domain."""
    _upsert_domain_routing(domain, dry_run, json_output, restart_cloudflared, verb="Added", action="add")


@domain_cli.command("repair")
def domain_repair(
    domain: str = typer.Argument(..., help="Bare domain to reconcile against the expected tunnel and ingress state."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without making changes."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    restart_cloudflared: bool = typer.Option(
        False,
        "--restart-cloudflared",
        help="Restart cloudflared after ingress changes are written.",
    ),
) -> None:
    """Repair apex and wildcard tunnel DNS routes and ingress entries for a domain."""
    _upsert_domain_routing(domain, dry_run, json_output, restart_cloudflared, verb="Repaired", action="repair")


@domain_cli.command("remove")
def domain_remove(
    domain: str = typer.Argument(..., help="Bare domain to remove from the existing Cloudflare Tunnel setup."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without making changes."),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON."),
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
    dns_results: list[dict[str, object]] = []
    ingress_results: list[dict[str, object]] = []
    restart_result: dict[str, object] | None = None
    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        records = [bare_domain, f"*.{bare_domain}"]

        for record_name in records:
            if dry_run:
                plan = client.plan_dns_record_removal(zone_id, record_name)
                dns_results.append(_dns_result_to_dict(plan))
                if not json_output:
                    info(f"[dry-run] {plan.action} DNS {plan.record_type} {plan.record_name}")
                continue

            result = client.apply_dns_record_removal(zone_id, record_name)
            dns_results.append(_dns_result_to_dict(result))
            action_label = {
                "delete": "deleted",
                "noop": "already absent",
            }.get(result.action, result.action)
            if not json_output:
                info(f"{action_label} DNS {result.record_type} {result.record_name}")

        ingress_changes = (
            plan_domain_ingress_removal(config.cloudflared_config, bare_domain)
            if dry_run
            else apply_domain_ingress_removal(config.cloudflared_config, bare_domain)
        )
        ingress_changed = any(change.action != "noop" for change in ingress_changes)
        for change in ingress_changes:
            ingress_results.append(_ingress_result_to_dict(change))
            prefix = "[dry-run] " if dry_run else ""
            action_label = {
                "delete": "delete",
                "noop": "already absent",
            }.get(change.action, change.action)
            if not json_output:
                info(f"{prefix}{action_label} ingress {change.hostname}")
    except (CloudflareApiError, typer.BadParameter) as exc:
        message = _format_domain_error(exc)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action="remove",
                        domain=bare_domain,
                        dry_run=dry_run,
                        ok=False,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                        error=message,
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(message)) from exc
    except CloudflaredConfigError as exc:
        message = _format_domain_error(exc)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action="remove",
                        domain=bare_domain,
                        dry_run=dry_run,
                        ok=False,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                        error=message,
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(message)) from exc

    if dry_run:
        if restart_cloudflared and ingress_changed:
            restart_result = _plan_cloudflared_restart(json_output=json_output)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action="remove",
                        domain=bare_domain,
                        dry_run=True,
                        ok=True,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                    ),
                    indent=2,
                )
            )
            return
        success(f"Dry-run complete for domain {bare_domain}")
    else:
        if ingress_changed:
            if restart_cloudflared:
                restart_result = _restart_cloudflared(json_output=json_output)
            else:
                restart_result = _warn_cloudflared_restart(json_output=json_output)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action="remove",
                        domain=bare_domain,
                        dry_run=False,
                        ok=True,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                    ),
                    indent=2,
                )
            )
            return
        success(f"Removed domain routing for {bare_domain}")


@domain_cli.command("status")
def domain_status(
    domain: str = typer.Argument(..., help="Bare domain to inspect in Cloudflare DNS and cloudflared ingress."),
    json_output: bool = typer.Option(False, "--json", help="Print the domain status report as JSON."),
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
        raise typer.Exit(code=_exit_with_error(_format_domain_error(exc))) from exc
    except CloudflaredConfigError as exc:
        raise typer.Exit(code=_exit_with_error(_format_domain_error(exc))) from exc

    overall = _overall_domain_status(dns_statuses, ingress_statuses, config.traefik_url)
    repairable = _domain_status_repairability(overall)
    suggested_command = f"homectl domain repair {bare_domain}" if repairable else None
    if json_output:
        payload = {
            "domain": bare_domain,
            "expected_tunnel_target": target,
            "expected_ingress_service": config.traefik_url,
            "overall": overall,
            "ok": overall == "ok",
            "repairable": repairable,
            "manual_fix_required": not repairable and overall != "ok",
            "suggested_command": suggested_command,
            "dns": [
                {
                    "record_name": status.record_name,
                    "exists": status.exists,
                    "record_type": status.record_type,
                    "content": status.content,
                    "proxied": status.proxied,
                    "matches_expected": status.matches_expected,
                }
                for status in dns_statuses
            ],
            "ingress": [
                {
                    "hostname": hostname,
                    "exists": service is not None,
                    "service": service,
                    "matches_expected": service == config.traefik_url,
                }
                for hostname, service in ingress_statuses
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        info(f"Expected tunnel target: {target}")
        info(f"Expected ingress service: {config.traefik_url}")

        for status in dns_statuses:
            if not status.exists:
                bullet_report("FAIL", f"DNS {status.record_name}", "record missing", False)
                continue

            detail = f"{status.record_type} -> {status.content}"
            if status.proxied:
                detail += " (proxied)"
            ok = status.matches_expected
            bullet_report("PASS" if ok else "FAIL", f"DNS {status.record_name}", detail, ok)

        for hostname, service in ingress_statuses:
            if service is None:
                bullet_report("FAIL", f"ingress {hostname}", "entry missing", False)
                continue

            ok = service == config.traefik_url
            bullet_report(
                "PASS" if ok else "FAIL",
                f"ingress {hostname}",
                service,
                ok,
            )

    if overall == "ok":
        if not json_output:
            success(f"Overall status for {bare_domain}: ok")
        return

    if not json_output:
        warn(f"Overall status for {bare_domain}: {overall}")
        if repairable:
            info(f"Repairable by homectl: yes")
            info(f"Suggested command: {suggested_command}")
        else:
            warn("Repairable by homectl: no; manual cleanup is likely required first")
    raise typer.Exit(code=1)


def _upsert_domain_routing(
    domain: str,
    dry_run: bool,
    json_output: bool,
    restart_cloudflared: bool,
    verb: str,
    action: str,
) -> None:
    config = load_config()
    bare_domain = validate_bare_domain(domain)
    client = CloudflareApiClient(config.cloudflare_api_token)

    ingress_changed = False
    dns_results: list[dict[str, object]] = []
    ingress_results: list[dict[str, object]] = []
    restart_result: dict[str, object] | None = None
    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        target = tunnel_cname_target(config)
        records = [bare_domain, f"*.{bare_domain}"]

        for record_name in records:
            if dry_run:
                plan = client.plan_dns_record(zone_id, record_name, target)
                dns_results.append(_dns_result_to_dict(plan))
                if not json_output:
                    info(
                        f"[dry-run] {plan.action} DNS {plan.record_type} {plan.record_name} -> {plan.content}"
                    )
                continue

            result = client.apply_dns_record(zone_id, record_name, target)
            dns_results.append(_dns_result_to_dict(result))
            action_label = {
                "create": "created",
                "update": "updated",
                "noop": "verified",
            }.get(result.action, result.action)
            if not json_output:
                info(f"{action_label} DNS {result.record_type} {result.record_name} -> {result.content}")

        ingress_changes = (
            plan_domain_ingress(config.cloudflared_config, bare_domain, config.traefik_url)
            if dry_run
            else apply_domain_ingress(config.cloudflared_config, bare_domain, config.traefik_url)
        )
        ingress_changed = any(change.action != "noop" for change in ingress_changes)
        for change in ingress_changes:
            ingress_results.append(_ingress_result_to_dict(change))
            prefix = "[dry-run] " if dry_run else ""
            action_label = {
                "create": "create",
                "update": "update",
                "noop": "verify",
            }.get(change.action, change.action)
            if not json_output:
                info(f"{prefix}{action_label} ingress {change.hostname} -> {change.service}")
    except (CloudflareApiError, typer.BadParameter) as exc:
        message = _format_domain_error(exc)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action=action,
                        domain=bare_domain,
                        dry_run=dry_run,
                        ok=False,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                        error=message,
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(message)) from exc
    except CloudflaredConfigError as exc:
        message = _format_domain_error(exc)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action=action,
                        domain=bare_domain,
                        dry_run=dry_run,
                        ok=False,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                        error=message,
                    ),
                    indent=2,
                )
            )
            raise typer.Exit(code=1) from exc
        raise typer.Exit(code=_exit_with_error(message)) from exc

    if dry_run:
        if restart_cloudflared and ingress_changed:
            restart_result = _plan_cloudflared_restart(json_output=json_output)
        if json_output:
            typer.echo(
                json.dumps(
                    _domain_mutation_payload(
                        action=action,
                        domain=bare_domain,
                        dry_run=True,
                        ok=True,
                        dns=dns_results,
                        ingress=ingress_results,
                        restart=restart_result,
                    ),
                    indent=2,
                )
            )
            return
        success(f"Dry-run complete for domain {bare_domain}")
        return

    if ingress_changed:
        if restart_cloudflared:
            restart_result = _restart_cloudflared(json_output=json_output)
        else:
            restart_result = _warn_cloudflared_restart(json_output=json_output)
    if json_output:
        typer.echo(
            json.dumps(
                _domain_mutation_payload(
                    action=action,
                    domain=bare_domain,
                    dry_run=False,
                    ok=True,
                    dns=dns_results,
                    ingress=ingress_results,
                    restart=restart_result,
                ),
                indent=2,
            )
        )
        return
    success(f"{verb} domain routing for {bare_domain}")


def _restart_cloudflared(json_output: bool = False) -> dict[str, object]:
    try:
        runtime = restart_cloudflared_service()
    except CloudflaredServiceError as exc:
        if not json_output:
            warn(f"Ingress changed, but {exc}")
        return {"ok": False, "detail": str(exc)}
    if not json_output:
        success(f"Restarted cloudflared via {runtime.mode}")
    return {
        "ok": True,
        "mode": runtime.mode,
        "detail": runtime.detail,
        "restart_command": runtime.restart_command,
    }


def _plan_cloudflared_restart(json_output: bool = False) -> dict[str, object]:
    runtime = detect_cloudflared_runtime()
    if runtime.restart_command:
        if not json_output:
            info(f"[dry-run] {' '.join(runtime.restart_command)}")
        return {
            "ok": True,
            "dry_run": True,
            "mode": runtime.mode,
            "detail": runtime.detail,
            "restart_command": runtime.restart_command,
        }
    if not json_output:
        warn(f"[dry-run] {runtime.detail}")
    return {
        "ok": False,
        "dry_run": True,
        "mode": runtime.mode,
        "detail": runtime.detail,
        "restart_command": runtime.restart_command,
    }


def _warn_cloudflared_restart(json_output: bool = False) -> dict[str, object]:
    runtime = detect_cloudflared_runtime()
    if runtime.restart_command:
        if not json_output:
            warn(f"Restart cloudflared to apply ingress changes: {' '.join(runtime.restart_command)}")
        return {
            "ok": True,
            "detail": runtime.detail,
            "restart_command": runtime.restart_command,
        }
    if not json_output:
        warn(f"Ingress changed; {runtime.detail}")
    return {"ok": False, "detail": runtime.detail, "restart_command": runtime.restart_command}


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


def _format_domain_error(error: Exception) -> str:
    if isinstance(error, (CloudflaredConfigError, typer.BadParameter)):
        return describe_cloudflared_config_error(error)
    return str(error)


def _domain_status_repairability(overall: str) -> bool:
    return overall in {"partial", "misconfigured"}


def _dns_result_to_dict(result) -> dict[str, object]:
    return {
        "action": result.action,
        "record_name": result.record_name,
        "record_type": result.record_type,
        "content": result.content,
    }


def _ingress_result_to_dict(change) -> dict[str, object]:
    return {
        "action": change.action,
        "hostname": change.hostname,
        "service": change.service,
    }


def _domain_mutation_payload(
    action: str,
    domain: str,
    dry_run: bool,
    ok: bool,
    dns: list[dict[str, object]],
    ingress: list[dict[str, object]],
    restart: dict[str, object] | None,
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": action,
        "domain": domain,
        "dry_run": dry_run,
        "ok": ok,
        "dns": dns,
        "ingress": ingress,
        "restart": restart,
    }
    if error:
        payload["error"] = error
    return payload
