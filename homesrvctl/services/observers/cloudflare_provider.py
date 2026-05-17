from __future__ import annotations

from dataclasses import asdict
from typing import Callable

import typer

from homesrvctl.cloudflare import (
    CloudflareApiClient,
    CloudflareApiError,
    DnsRecordStatus,
    account_id_from_zone,
    inspect_configured_tunnel,
    local_tunnel_cname_target,
    tunnel_cname_target_for_account,
)
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.services.stacks import iter_stack_dirs

CLOUDFLARE_PROVIDER_OBSERVER = "cloudflare_provider"


def observe_cloudflare_provider(
    config: HomesrvctlConfig,
    *,
    client_factory: Callable[[str], object] = CloudflareApiClient,
) -> ObserverResult:
    started_at = utc_now_iso()
    token_configured = bool(config.cloudflare_api_token.strip())
    hostnames = _stack_hostnames(config)
    issues: list[str] = []
    next_steps: list[str] = []

    data: dict[str, object] = {
        "token_configured": token_configured,
        "configured_tunnel": config.tunnel_name,
        "targets": hostnames,
        "target_count": len(hostnames),
        "zones_found": [],
        "zone_lookups_attempted": [],
        "dns_records_checked": 0,
        "records_missing": [],
        "records_wrong_target": [],
        "records_duplicate_or_ambiguous": [],
        "tunnel_target_known": False,
        "tunnel": None,
        "next_steps": next_steps,
    }

    if not token_configured:
        issues.append("Cloudflare API token is not configured")
        next_steps.append("Set cloudflare_api_token in homesrvctl config or CLOUDFLARE_API_TOKEN")
        return _result(started_at, "blocked", "Cloudflare token missing", data, issues)

    if not hostnames:
        data["status"] = "unknown"
        data["summary"] = "no stack hostnames found for Cloudflare observation"
        return _result(started_at, "unknown", "no stack hostnames found", data, issues)

    try:
        client = client_factory(config.cloudflare_api_token)
    except typer.BadParameter as exc:
        issues.append(str(exc))
        next_steps.append("Set a valid Cloudflare API token")
        return _result(started_at, "blocked", "Cloudflare token unavailable", data, issues)

    tunnel_inspection = inspect_configured_tunnel(config)
    data["tunnel"] = _tunnel_payload(tunnel_inspection)
    if tunnel_inspection.resolved_tunnel_id:
        data["tunnel_target_known"] = True
        expected_target = f"{tunnel_inspection.resolved_tunnel_id}.cfargotunnel.com"
    else:
        local_target = local_tunnel_cname_target(config)
        expected_target = local_target
        data["tunnel_target_known"] = local_target is not None
        if local_target is None:
            issues.append(tunnel_inspection.resolution_error or "could not resolve tunnel target")
            next_steps.append("Run `homesrvctl tunnel status` and ensure cloudflared config or API access can resolve the tunnel")

    zones: dict[str, dict[str, object]] = {}
    domain_results: list[dict[str, object]] = []
    for hostname in hostnames:
        zone_result = _resolve_zone_for_hostname(client, hostname)
        data["zone_lookups_attempted"].extend(zone_result["attempted"])
        if zone_result["error"]:
            issue = f"{hostname}: {zone_result['error']}"
            issues.append(issue)
            next_steps.append(f"Ensure the Cloudflare token can read the zone for {hostname}")
            domain_results.append({
                "hostname": hostname,
                "zone_name": None,
                "zone_id": None,
                "status": "zone_error",
                "issue": zone_result["error"],
                "dns": None,
            })
            continue

        zone = zone_result["zone"]
        assert isinstance(zone, dict)
        zone_name = str(zone.get("name") or zone_result["zone_name"])
        zone_id = str(zone.get("id", ""))
        zones[zone_name] = {"name": zone_name, "id": zone_id}
        if expected_target is None:
            try:
                expected_target = tunnel_cname_target_for_account(
                    config,
                    account_id=account_id_from_zone(zone),
                    api_client=client,  # type: ignore[arg-type]
                )
            except (CloudflareApiError, typer.BadParameter) as exc:
                issues.append(f"{hostname}: could not resolve tunnel target from Cloudflare account: {exc}")
                next_steps.append("Ensure the token can read the configured Cloudflare Tunnel")
                domain_results.append({
                    "hostname": hostname,
                    "zone_name": zone_name,
                    "zone_id": zone_id,
                    "status": "tunnel_error",
                    "issue": str(exc),
                    "dns": None,
                })
                continue
            data["tunnel_target_known"] = True

        try:
            dns_status = client.get_dns_record_status(zone_id, hostname, expected_target)  # type: ignore[attr-defined]
        except CloudflareApiError as exc:
            issue = f"{hostname}: {exc}"
            issues.append(issue)
            next_steps.append(f"Check Cloudflare DNS read permissions for {hostname}")
            domain_results.append({
                "hostname": hostname,
                "zone_name": zone_name,
                "zone_id": zone_id,
                "status": "dns_error",
                "issue": str(exc),
                "dns": None,
            })
            continue

        data["dns_records_checked"] = int(data["dns_records_checked"]) + 1
        dns_payload = _dns_status_payload(dns_status)
        if not dns_status.exists:
            data["records_missing"].append(hostname)  # type: ignore[union-attr]
            issues.append(f"{hostname}: DNS record missing")
            next_steps.append(f"Run `homesrvctl domain repair {hostname}` if this hostname should be routed")
        elif getattr(dns_status, "multiple_records", False):
            data["records_duplicate_or_ambiguous"].append(hostname)  # type: ignore[union-attr]
            issues.append(f"{hostname}: {dns_status.detail}")
            next_steps.append(f"Clean up ambiguous Cloudflare DNS records for {hostname}")
        elif not dns_status.matches_expected:
            data["records_wrong_target"].append(hostname)  # type: ignore[union-attr]
            issues.append(f"{hostname}: {dns_status.detail}")
            next_steps.append(f"Run `homesrvctl domain repair {hostname}` or fix DNS manually")

        domain_results.append({
            "hostname": hostname,
            "zone_name": zone_name,
            "zone_id": zone_id,
            "status": "ready" if dns_status.matches_expected else "dns_issue",
            "expected_tunnel_target": expected_target,
            "dns": dns_payload,
        })

    data["zones_found"] = list(zones.values())
    data["domain_results"] = domain_results
    status = _overall_status(data, issues)
    summary = _summary(status, data)
    return _result(started_at, status, summary, data, issues)


def _stack_hostnames(config: HomesrvctlConfig) -> list[str]:
    if not config.sites_root.exists():
        return []
    return [path.name for path in iter_stack_dirs(config)]


def _resolve_zone_for_hostname(client: object, hostname: str) -> dict[str, object]:
    labels = hostname.split(".")
    attempted: list[str] = []
    last_error: str | None = None
    for index in range(max(0, len(labels) - 1)):
        candidate = ".".join(labels[index:])
        if not candidate:
            continue
        attempted.append(candidate)
        try:
            zone = client.get_zone(candidate)  # type: ignore[attr-defined]
        except CloudflareApiError as exc:
            last_error = str(exc)
            continue
        return {"zone": zone, "zone_name": candidate, "attempted": attempted, "error": None}
    return {
        "zone": None,
        "zone_name": None,
        "attempted": attempted,
        "error": last_error or f"Cloudflare zone not found or not accessible for {hostname}",
    }


def _result(
    started_at: str,
    status: str,
    summary: str,
    data: dict[str, object],
    issues: list[str],
) -> ObserverResult:
    finished_at = utc_now_iso()
    data["status"] = status
    data["summary"] = summary
    return ObserverResult(
        observer_name=CLOUDFLARE_PROVIDER_OBSERVER,
        ok=status == "ready" or (status == "unknown" and not issues),
        started_at=started_at,
        finished_at=finished_at,
        target_type="provider",
        target="cloudflare",
        status=status,
        summary=summary,
        observations=[
            ObservationRecord(
                source=CLOUDFLARE_PROVIDER_OBSERVER,
                target_type="provider",
                target="cloudflare",
                status=status,
                detail=summary,
                data=data,
            )
        ],
        issues=issues,
    )


def _overall_status(data: dict[str, object], issues: list[str]) -> str:
    if not data.get("token_configured"):
        return "blocked"
    if not data.get("tunnel_target_known"):
        return "blocked"
    if issues:
        return "degraded"
    if int(data.get("dns_records_checked", 0)) == 0:
        return "unknown"
    return "ready"


def _summary(status: str, data: dict[str, object]) -> str:
    if status == "ready":
        return f"Cloudflare DNS ready for {data.get('dns_records_checked', 0)} hostnames"
    if status == "unknown":
        return "Cloudflare observer has no domain targets"
    return (
        "Cloudflare provider issues found: "
        f"missing={len(data.get('records_missing', []))} "
        f"wrong={len(data.get('records_wrong_target', []))} "
        f"ambiguous={len(data.get('records_duplicate_or_ambiguous', []))}"
    )


def _dns_status_payload(status: DnsRecordStatus) -> dict[str, object]:
    return {
        "record_name": status.record_name,
        "exists": status.exists,
        "record_type": status.record_type,
        "content": status.content,
        "proxied": status.proxied,
        "matches_expected": status.matches_expected,
        "multiple_records": getattr(status, "multiple_records", False),
        "record_count": getattr(status, "record_count", 1 if status.exists else 0),
        "detail": status.detail,
        "records": getattr(status, "records", []),
    }


def _tunnel_payload(inspection) -> dict[str, object]:  # noqa: ANN001
    payload = asdict(inspection)
    if inspection.api_status is not None:
        payload["api_status"] = asdict(inspection.api_status)
    return payload
