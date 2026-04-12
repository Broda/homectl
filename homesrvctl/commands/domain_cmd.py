from __future__ import annotations

import json

import typer

from homesrvctl.cloudflare import (
    CloudflareApiClient,
    CloudflareApiError,
    account_id_from_zone,
    local_tunnel_cname_target,
    tunnel_cname_target,
    tunnel_cname_target_for_account,
)
from homesrvctl.cloudflared import (
    CloudflaredConfigError,
    apply_domain_ingress,
    apply_domain_ingress_removal,
    describe_cloudflared_config_error,
    inspect_cloudflared_config_issues,
    inspect_hostname_route,
    list_exact_hostname_routes,
    plan_domain_ingress,
    plan_domain_ingress_removal,
)
from homesrvctl.cloudflared_service import (
    CloudflaredServiceError,
    detect_cloudflared_runtime,
    inspect_cloudflared_setup,
    restart_cloudflared_service,
)
from homesrvctl.config import load_config, load_config_details, load_stack_settings, stack_routing_context
from homesrvctl.utils import bullet_report, info, success, validate_bare_domain, warn, with_json_schema

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
        if not dry_run:
            _require_cloudflared_ingress_mutation_ready(config, quiet=json_output)
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
    config, global_sources = load_config_details()
    bare_domain = validate_bare_domain(domain)
    stack_settings = load_stack_settings(config, bare_domain)
    routing = stack_routing_context(config, bare_domain, global_sources)
    client = CloudflareApiClient(config.cloudflare_api_token)

    try:
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        target = _resolve_domain_tunnel_target(config, zone, client)
        records = [bare_domain, f"*.{bare_domain}"]

        dns_statuses = [client.get_dns_record_status(zone_id, record_name, target) for record_name in records]
        dns_warnings = _common_subdomain_dns_warnings(client, zone_id, bare_domain, target)
        ingress_statuses = _build_domain_ingress_statuses(
            config.cloudflared_config,
            bare_domain,
            stack_settings.traefik_url,
        )
        ingress_issues = inspect_cloudflared_config_issues(config.cloudflared_config)
        setup = inspect_cloudflared_setup(config.cloudflared_config, quiet=json_output)
    except (CloudflareApiError, typer.BadParameter) as exc:
        raise typer.Exit(code=_exit_with_error(_format_domain_error(exc))) from exc
    except CloudflaredConfigError as exc:
        raise typer.Exit(code=_exit_with_error(_format_domain_error(exc))) from exc

    overall = _overall_domain_status(dns_statuses, ingress_statuses, config.traefik_url)
    repairable = _domain_status_repairability(overall, dns_statuses, ingress_statuses)
    suggested_command = f"homesrvctl domain repair {bare_domain}" if repairable else None
    coverage_issues = _coverage_issues(dns_statuses, ingress_statuses)
    if json_output:
        payload = with_json_schema({
            "domain": bare_domain,
            "expected_tunnel_target": target,
            "expected_ingress_service": stack_settings.traefik_url,
            "routing": routing,
            "overall": overall,
            "ok": overall == "ok",
            "repairable": repairable,
            "manual_fix_required": not repairable and overall != "ok",
            "suggested_command": suggested_command,
            "coverage_issues": coverage_issues,
            "dns_warnings": dns_warnings,
            "ingress_warnings": [issue.render() for issue in ingress_issues if issue.severity == "advisory"],
            "ingress_issues": [_ingress_issue_to_dict(issue) for issue in ingress_issues],
            "ingress_mutation_available": setup.ingress_mutation_available,
            "ingress_mutation_detail": setup.detail,
            "configured_cloudflared_config": setup.configured_path,
            "runtime_cloudflared_config": setup.runtime_path,
            "cloudflared_paths_aligned": setup.paths_aligned,
            "dns": [
                {
                    "record_name": status.record_name,
                    "exists": status.exists,
                    "record_type": status.record_type,
                    "content": status.content,
                    "proxied": status.proxied,
                    "matches_expected": status.matches_expected,
                    "multiple_records": getattr(status, "multiple_records", False),
                    "record_count": getattr(status, "record_count", 1 if status.exists else 0),
                    "detail": _dns_status_detail(status),
                    "records": getattr(status, "records", []),
                }
                for status in dns_statuses
            ],
            "ingress": [
                {
                    "hostname": status["hostname"],
                    "probe_hostname": status["probe_hostname"],
                    "exists": status["exists"],
                    "duplicate": status["duplicate"],
                    "service": status["service"],
                    "matches_expected": status["matches_expected"],
                    "effective_hostname": status["effective_hostname"],
                    "effective_service": status["effective_service"],
                    "shadowed": status["shadowed"],
                    "detail": status["detail"],
                }
                for status in ingress_statuses
            ],
        })
        typer.echo(json.dumps(payload, indent=2))
    else:
        info(f"Expected tunnel target: {target}")
        info(f"Default ingress service: {routing['default']['traefik_url']}")
        info(f"Effective ingress service: {routing['effective']['traefik_url']}")
        info(
            "Routing source: "
            f"{routing['effective_sources']['traefik_url']}"
            + (f" (profile={routing['profile']})" if routing["profile"] else "")
        )

        for status in dns_statuses:
            if not status.exists:
                bullet_report("FAIL", f"DNS {status.record_name}", "record missing", False)
                continue

            bullet_report(
                "PASS" if status.matches_expected else "FAIL",
                f"DNS {status.record_name}",
                _dns_status_detail(status),
                status.matches_expected,
            )

        for status in ingress_statuses:
            ok = status["matches_expected"]
            bullet_report(
                "PASS" if ok else "FAIL",
                f"ingress {status['hostname']}",
                str(status["detail"]),
                ok,
            )
        for warning_message in dns_warnings:
            warn(f"DNS warning: {warning_message}")
        for issue in ingress_issues:
            prefix = "Ingress advisory" if issue.severity == "advisory" else "Ingress blocking issue"
            warn(f"{prefix}: {issue.render()}")
        if setup.ingress_mutation_available:
            info("Ingress mutations from homesrvctl: yes")
        else:
            warn(f"Ingress mutations from homesrvctl: no; {setup.detail}")

    if overall == "ok":
        if not json_output:
            success(f"Overall status for {bare_domain}: ok")
        return

    if not json_output:
        warn(f"Overall status for {bare_domain}: {overall}")
        for issue in coverage_issues:
            warn(issue)
        if repairable:
            info(f"Repairable by homesrvctl: yes")
            info(f"Suggested command: {suggested_command}")
        else:
            warn("Repairable by homesrvctl: no; manual cleanup is likely required first")
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
    stack_settings = load_stack_settings(config, bare_domain)
    client = CloudflareApiClient(config.cloudflare_api_token)

    ingress_changed = False
    dns_results: list[dict[str, object]] = []
    ingress_results: list[dict[str, object]] = []
    restart_result: dict[str, object] | None = None
    try:
        if not dry_run:
            _require_cloudflared_ingress_mutation_ready(config, quiet=json_output)
        zone = client.get_zone(bare_domain)
        zone_id = str(zone["id"])
        target = _resolve_domain_tunnel_target(config, zone, client)
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
            plan_domain_ingress(config.cloudflared_config, bare_domain, stack_settings.traefik_url)
            if dry_run
            else apply_domain_ingress(config.cloudflared_config, bare_domain, stack_settings.traefik_url)
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
    runtime = detect_cloudflared_runtime(quiet=json_output)
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
    runtime = detect_cloudflared_runtime(quiet=json_output)
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


def _build_domain_ingress_statuses(config_path, domain: str, expected_service: str) -> list[dict[str, object]]:  # noqa: ANN001
    statuses: list[dict[str, object]] = []
    wildcard_probe = _wildcard_probe_hostname(domain)

    for target_hostname, probe_hostname in (
        (domain, domain),
        (f"*.{domain}", wildcard_probe),
    ):
        exact_routes = list_exact_hostname_routes(config_path, target_hostname)
        duplicate = len(exact_routes) > 1
        configured_service = exact_routes[0].service if exact_routes else None
        effective_match = inspect_hostname_route(config_path, probe_hostname)
        effective_hostname = effective_match.hostname if effective_match else None
        effective_service = effective_match.service if effective_match else None
        shadowed = effective_match is not None and effective_hostname != target_hostname
        exact_exists = bool(exact_routes)

        if duplicate:
            detail = (
                "duplicate exact ingress entries configured: "
                + ", ".join(f"{route.hostname} -> {route.service}" for route in exact_routes)
            )
        elif configured_service is None:
            if shadowed:
                detail = f"exact entry missing; shadowed by earlier rule {effective_hostname} -> {effective_service}"
            else:
                detail = "exact entry missing"
        elif shadowed:
            detail = f"shadowed by earlier rule {effective_hostname} -> {effective_service}"
        elif configured_service != expected_service:
            detail = f"wrong target {configured_service}; expected {expected_service}"
        else:
            detail = configured_service

        matches_expected = (
            not duplicate
            and configured_service == expected_service
            and effective_hostname == target_hostname
            and effective_service == expected_service
        )
        statuses.append(
            {
                "hostname": target_hostname,
                "probe_hostname": probe_hostname,
                "exists": exact_exists,
                "duplicate": duplicate,
                "service": configured_service,
                "matches_expected": matches_expected,
                "effective_hostname": effective_hostname,
                "effective_service": effective_service,
                "shadowed": shadowed,
                "detail": detail,
            }
        )
    return statuses


def _overall_domain_status(dns_statuses, ingress_statuses, expected_service: str) -> str:  # noqa: ANN001
    dns_exists = [status.exists for status in dns_statuses]
    dns_matches = [status.matches_expected for status in dns_statuses]
    dns_conflicts = [getattr(status, "multiple_records", False) for status in dns_statuses]
    ingress_exists = [status["exists"] for status in ingress_statuses]
    ingress_matches = [status["matches_expected"] for status in ingress_statuses]
    ingress_conflicts = [status["duplicate"] for status in ingress_statuses]
    dns_wrong = [
        status.exists and not status.matches_expected and not getattr(status, "multiple_records", False)
        for status in dns_statuses
    ]
    ingress_wrong = [
        status["exists"] and not status["matches_expected"] and not status["duplicate"]
        for status in ingress_statuses
    ]

    if all(dns_matches) and all(ingress_matches):
        return "ok"
    if any(dns_conflicts) or any(dns_wrong) or any(ingress_conflicts) or any(ingress_wrong):
        return "misconfigured"
    if any(dns_exists) or any(ingress_exists):
        return "partial"
    return "partial"


def _exit_with_error(message: str) -> int:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return 1


def _format_domain_error(error: Exception) -> str:
    if isinstance(error, CloudflaredConfigError):
        return describe_cloudflared_config_error(error)
    if isinstance(error, typer.BadParameter):
        message = str(error)
        if "cloudflared" in message:
            return describe_cloudflared_config_error(error)
        return message
    if isinstance(error, CloudflareApiError):
        message = str(error)
        if message.startswith("multiple DNS records exist for "):
            record_name = message.removeprefix("multiple DNS records exist for ").split(";", 1)[0].strip()
            return (
                f"DNS conflict for {record_name}: multiple conflicting records exist; "
                "clean them up manually before retrying"
            )
        return message
    return str(error)


def _require_cloudflared_ingress_mutation_ready(config, *, quiet: bool = False) -> None:  # noqa: ANN001
    setup = inspect_cloudflared_setup(config.cloudflared_config, quiet=quiet)
    if setup.ingress_mutation_available:
        return
    detail = setup.detail
    if setup.systemd_managed and setup.paths_aligned is False:
        raise typer.BadParameter(
            f"{detail}. Run `homesrvctl cloudflared setup` to generate the systemd override and migration commands."
        )
    raise typer.BadParameter(f"{detail}. Run `homesrvctl cloudflared setup` for repair guidance.")


def _domain_status_repairability(overall: str, dns_statuses, ingress_statuses) -> bool:  # noqa: ANN001
    if overall not in {"partial", "misconfigured"}:
        return False
    if any(getattr(status, "multiple_records", False) for status in dns_statuses):
        return False
    if any(status["duplicate"] for status in ingress_statuses):
        return False
    return not any(status["shadowed"] for status in ingress_statuses)


def _wildcard_probe_hostname(domain: str) -> str:
    return f"_homesrvctl-probe.{domain}"


def _coverage_issues(dns_statuses, ingress_statuses) -> list[str]:  # noqa: ANN001
    issues: list[str] = []
    apex_dns_exists = dns_statuses[0].exists
    wildcard_dns_exists = dns_statuses[1].exists
    apex_ingress_exists = ingress_statuses[0]["exists"]
    wildcard_ingress_exists = ingress_statuses[1]["exists"]

    if apex_dns_exists and not wildcard_dns_exists:
        issues.append("DNS coverage is apex-only; wildcard DNS is missing")
    if wildcard_dns_exists and not apex_dns_exists:
        issues.append("DNS coverage is wildcard-only; apex DNS is missing")
    if apex_ingress_exists and not wildcard_ingress_exists:
        issues.append("Ingress coverage is apex-only; wildcard ingress is missing")
    if wildcard_ingress_exists and not apex_ingress_exists:
        issues.append("Ingress coverage is wildcard-only; apex ingress is missing")
    return issues


def _common_subdomain_dns_warnings(
    client: CloudflareApiClient,
    zone_id: str,
    domain: str,
    expected_target: str,
) -> list[str]:
    warnings: list[str] = []
    www_status = client.get_dns_record_status(zone_id, f"www.{domain}", expected_target)
    if www_status.exists and not www_status.matches_expected:
        warnings.append(
            f"explicit DNS record www.{domain} overrides the wildcard tunnel route: {www_status.detail}"
        )
    return warnings


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


def _ingress_issue_to_dict(issue) -> dict[str, object]:  # noqa: ANN001
    return {
        "code": issue.code,
        "severity": issue.severity,
        "blocking": issue.blocking,
        "detail": issue.detail,
        "hint": issue.hint,
        "message": issue.render(),
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
    payload: dict[str, object] = with_json_schema({
        "action": action,
        "domain": domain,
        "dry_run": dry_run,
        "ok": ok,
        "dns": dns,
        "ingress": ingress,
        "restart": restart,
    })
    if error:
        payload["error"] = error
    return payload


def _dns_status_detail(status) -> str:  # noqa: ANN001
    detail = getattr(status, "detail", "")
    if detail:
        return detail
    rendered = f"{status.record_type} -> {status.content}"
    if status.proxied:
        rendered += " (proxied)"
    return rendered


def _resolve_domain_tunnel_target(
    config,
    zone: dict[str, object],
    client: CloudflareApiClient,
) -> str:  # noqa: ANN001
    local_target = local_tunnel_cname_target(config)
    if local_target is not None:
        return local_target
    account_id = account_id_from_zone(zone)
    return tunnel_cname_target_for_account(config, account_id=account_id, api_client=client)
