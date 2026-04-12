from __future__ import annotations

import json
import re
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import typer
import yaml

from homesrvctl import __version__
from homesrvctl.models import HomesrvctlConfig
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class CloudflareApiError(RuntimeError):
    pass


@dataclass(slots=True)
class ApiPlan:
    action: str
    record_name: str
    record_type: str
    content: str


@dataclass(slots=True)
class DnsRecordStatus:
    record_name: str
    exists: bool
    record_type: str
    content: str
    proxied: bool
    matches_expected: bool
    multiple_records: bool = False
    record_count: int = 0
    detail: str = ""
    records: list[dict[str, object]] = field(default_factory=list)


@dataclass(slots=True)
class TunnelStatus:
    id: str
    name: str
    status: str


@dataclass(slots=True)
class TunnelInspection:
    configured_tunnel: str
    resolved_tunnel_id: str | None
    resolution_source: str | None
    account_id: str | None
    api_available: bool
    api_status: TunnelStatus | None = None
    api_error: str | None = None
    resolution_error: str | None = None


def summarize_tunnel_api_detail(
    *,
    resolved_tunnel_id: str | None,
    api_available: bool,
    api_status: TunnelStatus | None,
    api_error: str | None,
) -> tuple[str | None, bool]:
    """Return operator-facing API inspection detail plus whether it is warning-grade.

    Some local environments intentionally keep the cloudflared credentials file
    unreadable to the current user. If the tunnel ID is already resolved through
    local config, that should not look like a tunnel failure in the CLI or TUI.
    """

    if api_status is not None:
        return None, False
    if api_error:
        normalized = api_error.lower()
        if (
            resolved_tunnel_id is not None
            and "unable to read cloudflared credentials file" in normalized
            and "permission denied" in normalized
        ):
            return "account-scoped tunnel inspection unavailable from current user permissions", False
        return api_error, True
    if not api_available:
        return "account-scoped tunnel inspection unavailable from local cloudflared credentials", False
    return None, False


class CloudflareApiClient:
    def __init__(self, api_token: str) -> None:
        token = api_token.strip()
        if not token:
            raise typer.BadParameter(
                "missing Cloudflare API token; set cloudflare_api_token in homesrvctl config or CLOUDFLARE_API_TOKEN"
            )
        self._api_token = token

    def get_zone(self, zone_name: str) -> dict[str, object]:
        encoded = urllib.parse.quote(zone_name, safe="")
        payload = self._request_json("GET", f"/zones?name={encoded}")
        result = payload.get("result", [])
        if not isinstance(result, list) or not result:
            raise CloudflareApiError(f"Cloudflare zone not found or not accessible: {zone_name}")
        if len(result) > 1:
            raise CloudflareApiError(f"multiple Cloudflare zones matched {zone_name}; refine configuration")
        zone = result[0]
        if not isinstance(zone, dict) or not zone.get("id"):
            raise CloudflareApiError(f"Cloudflare returned an invalid zone response for {zone_name}")
        return zone

    def get_tunnel(self, account_id: str, tunnel_ref: str) -> TunnelStatus:
        candidate = tunnel_ref.strip()
        if not candidate:
            raise CloudflareApiError("missing tunnel reference")

        if UUID_RE.match(candidate):
            payload = self._request_json("GET", f"/accounts/{account_id}/cfd_tunnel/{candidate.lower()}")
            result = payload.get("result")
            return _parse_tunnel_status(result, candidate)

        encoded_name = urllib.parse.quote(candidate, safe="")
        payload = self._request_json("GET", f"/accounts/{account_id}/cfd_tunnel?name={encoded_name}")
        result = payload.get("result", [])
        if not isinstance(result, list):
            raise CloudflareApiError(f"Cloudflare returned an invalid tunnel list for {candidate}")

        matches = [_parse_tunnel_status(item, candidate) for item in result if isinstance(item, dict)]
        exact_matches = [match for match in matches if match.name == candidate]
        if not exact_matches:
            raise CloudflareApiError(f"Cloudflare tunnel not found in account for {candidate}")
        if len(exact_matches) > 1:
            raise CloudflareApiError(f"multiple Cloudflare tunnels matched {candidate}; refine configuration")
        return exact_matches[0]

    def plan_dns_record(self, zone_id: str, record_name: str, content: str) -> ApiPlan:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            return ApiPlan("create", record_name, "CNAME", content)
        classification = _classify_dns_records(existing, expected_content=content)
        if classification["conflicts"]:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )
        if classification["matching_cname"] is not None:
            return ApiPlan("noop", record_name, "CNAME", content)
        record = classification["managed_record"] or existing[0]
        current_type = str(record.get("type", ""))
        current_content = str(record.get("content", ""))
        current_proxied = bool(record.get("proxied"))
        if current_type == "CNAME" and current_content == content and current_proxied:
            return ApiPlan("noop", record_name, "CNAME", content)
        return ApiPlan("update", record_name, "CNAME", content)

    def apply_dns_record(self, zone_id: str, record_name: str, content: str) -> ApiPlan:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            self._request_json(
                "POST",
                f"/zones/{zone_id}/dns_records",
                {
                    "type": "CNAME",
                    "name": record_name,
                    "content": content,
                    "proxied": True,
                    "ttl": 1,
                },
            )
            return ApiPlan("create", record_name, "CNAME", content)

        classification = _classify_dns_records(existing, expected_content=content)
        if classification["conflicts"]:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )
        if classification["matching_cname"] is not None:
            return ApiPlan("noop", record_name, "CNAME", content)
        record = classification["managed_record"] or existing[0]
        record_id = str(record.get("id", "")).strip()
        current_type = str(record.get("type", ""))
        current_content = str(record.get("content", ""))
        current_proxied = bool(record.get("proxied"))
        if current_type == "CNAME" and current_content == content and current_proxied:
            return ApiPlan("noop", record_name, "CNAME", content)

        self._request_json(
            "PUT",
            f"/zones/{zone_id}/dns_records/{record_id}",
            {
                "type": "CNAME",
                "name": record_name,
                "content": content,
                "proxied": True,
                "ttl": 1,
            },
        )
        return ApiPlan("update", record_name, "CNAME", content)

    def plan_dns_record_removal(self, zone_id: str, record_name: str) -> ApiPlan:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            return ApiPlan("noop", record_name, "DNS", "")
        classification = _classify_dns_records(existing)
        if classification["conflicts"]:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )
        record = classification["managed_record"]
        if record is None:
            return ApiPlan("noop", record_name, "DNS", "")
        return ApiPlan(
            "delete",
            record_name,
            str(record.get("type", "")).strip() or "DNS",
            str(record.get("content", "")).strip(),
        )

    def apply_dns_record_removal(self, zone_id: str, record_name: str) -> ApiPlan:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            return ApiPlan("noop", record_name, "DNS", "")
        classification = _classify_dns_records(existing)
        if classification["conflicts"]:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )
        record = classification["managed_record"]
        if record is None:
            return ApiPlan("noop", record_name, "DNS", "")
        record_id = str(record.get("id", "")).strip()
        record_type = str(record.get("type", "")).strip() or "DNS"
        record_content = str(record.get("content", "")).strip()
        self._request_json("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
        return ApiPlan("delete", record_name, record_type, record_content)

    def get_dns_record_status(self, zone_id: str, record_name: str, expected_content: str) -> DnsRecordStatus:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            return DnsRecordStatus(
                record_name=record_name,
                exists=False,
                record_type="",
                content="",
                proxied=False,
                matches_expected=False,
                detail="record missing",
            )
        classification = _classify_dns_records(existing, expected_content=expected_content)
        if classification["conflicts"]:
            rendered_records = [_render_dns_record(record) for record in existing]
            return DnsRecordStatus(
                record_name=record_name,
                exists=True,
                record_type="multiple",
                content="",
                proxied=any(bool(record.get("proxied")) for record in existing),
                matches_expected=False,
                multiple_records=True,
                record_count=len(existing),
                detail=f"multiple conflicting records exist: {', '.join(rendered_records)}",
                records=_records_to_status_records(existing),
            )
        if classification["matching_cname"] is not None:
            ancillary_records = classification["ancillary_records"]
            detail = _describe_single_dns_record("CNAME", expected_content, True)
            if ancillary_records:
                detail += "; ancillary records present: " + ", ".join(_render_dns_record(record) for record in ancillary_records)
            return DnsRecordStatus(
                record_name=record_name,
                exists=True,
                record_type="CNAME",
                content=expected_content,
                proxied=True,
                matches_expected=True,
                record_count=len(existing),
                detail=detail,
                records=_records_to_status_records(existing),
            )

        record = classification["managed_record"] or existing[0]
        record_type = str(record.get("type", "")).strip()
        content = str(record.get("content", "")).strip()
        proxied = bool(record.get("proxied"))
        matches_expected = record_type == "CNAME" and content == expected_content and proxied
        detail = (
            _describe_single_dns_record(record_type, content, proxied)
            if matches_expected
            else _dns_mismatch_detail(record_type, content, proxied, expected_content)
        )
        return DnsRecordStatus(
            record_name=record_name,
            exists=True,
            record_type=record_type,
            content=content,
            proxied=proxied,
            matches_expected=matches_expected,
            record_count=1,
            detail=detail,
            records=_records_to_status_records(existing),
        )

    def _list_dns_records(self, zone_id: str, record_name: str) -> list[dict[str, object]]:
        encoded = urllib.parse.quote(record_name, safe="")
        payload = self._request_json("GET", f"/zones/{zone_id}/dns_records?name={encoded}")
        result = payload.get("result", [])
        if not isinstance(result, list):
            raise CloudflareApiError(f"Cloudflare returned an invalid DNS record list for {record_name}")
        records: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict) and str(item.get("name", "")).lower() == record_name.lower():
                records.append(item)
        return records

    def _request_json(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        url = f"https://api.cloudflare.com/client/v4{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            method=method,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "User-Agent": f"homesrvctl/{__version__}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CloudflareApiError(f"Cloudflare API request failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CloudflareApiError(f"Cloudflare API request failed: {exc}") from exc

        if not payload.get("success", False):
            errors = payload.get("errors", [])
            raise CloudflareApiError(f"Cloudflare API request failed: {errors}")
        return payload


def tunnel_cname_target(config: HomesrvctlConfig) -> str:
    tunnel_id = _resolve_local_tunnel_id(config)
    if tunnel_id is None:
        raise typer.BadParameter(
            f"could not resolve local tunnel ID for {config.tunnel_name}; "
            "configure a tunnel UUID locally or use an account-scoped API lookup"
        )
    return f"{tunnel_id}.cfargotunnel.com"


def inspect_configured_tunnel(config: HomesrvctlConfig) -> TunnelInspection:
    configured_tunnel = config.tunnel_name
    resolved_tunnel_id: str | None = None
    resolution_source: str | None = None

    if UUID_RE.match(config.tunnel_name):
        resolved_tunnel_id = config.tunnel_name.lower()
        resolution_source = "config:tunnel_name"
    else:
        config_tunnel_id = _tunnel_id_from_config_file(config.cloudflared_config)
        if config_tunnel_id is not None:
            resolved_tunnel_id = config_tunnel_id
            resolution_source = "cloudflared-config:tunnel"

    account_id: str | None = None
    api_status: TunnelStatus | None = None
    api_error: str | None = None
    api_available = False

    try:
        account_id = account_id_from_cloudflared_config(config.cloudflared_config)
    except CloudflareApiError as exc:
        api_error = str(exc)
    else:
        api_available = True
        try:
            client = CloudflareApiClient(config.cloudflare_api_token)
        except typer.BadParameter as exc:
            api_error = str(exc)
        else:
            if resolved_tunnel_id is None:
                try:
                    api_status = client.get_tunnel(account_id, configured_tunnel)
                except CloudflareApiError as exc:
                    api_error = str(exc)
                else:
                    resolved_tunnel_id = api_status.id.lower()
                    resolution_source = "credentials+api"
            else:
                try:
                    api_status = client.get_tunnel(account_id, resolved_tunnel_id)
                except CloudflareApiError as exc:
                    api_error = str(exc)

    resolution_error = None
    if resolved_tunnel_id is None:
        resolution_error = api_error or (
            f"could not resolve tunnel ID for {configured_tunnel}: "
            "no local UUID found and account-scoped API lookup unavailable"
        )
    return TunnelInspection(
        configured_tunnel=configured_tunnel,
        resolved_tunnel_id=resolved_tunnel_id,
        resolution_source=resolution_source,
        account_id=account_id,
        api_available=api_available,
        api_status=api_status,
        api_error=api_error,
        resolution_error=resolution_error,
    )


def local_tunnel_cname_target(config: HomesrvctlConfig) -> str | None:
    tunnel_id = _resolve_local_tunnel_id(config)
    if tunnel_id is None:
        return None
    return f"{tunnel_id}.cfargotunnel.com"


def tunnel_cname_target_for_account(
    config: HomesrvctlConfig,
    *,
    account_id: str,
    api_client: CloudflareApiClient,
) -> str:
    tunnel_id = _resolve_tunnel_id_for_account(config, account_id=account_id, api_client=api_client)
    return f"{tunnel_id}.cfargotunnel.com"


def account_id_from_zone(zone: dict[str, object]) -> str:
    account = zone.get("account")
    if not isinstance(account, dict):
        raise CloudflareApiError("Cloudflare zone response did not include account details for tunnel lookup")
    account_id = str(account.get("id", "")).strip()
    if not account_id:
        raise CloudflareApiError("Cloudflare zone response did not include an account ID for tunnel lookup")
    return account_id


def account_id_from_cloudflared_config(config_path: Path) -> str:
    parsed = _load_cloudflared_yaml(config_path)
    credentials_value = str(parsed.get("credentials-file", "")).strip()
    if not credentials_value:
        raise CloudflareApiError(f"cloudflared config missing credentials-file: {config_path}")
    credentials_path = Path(credentials_value)
    if not credentials_path.is_absolute():
        credentials_path = config_path.parent / credentials_path
    if not credentials_path.exists():
        raise CloudflareApiError(f"cloudflared credentials file missing: {credentials_path}")
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CloudflareApiError(f"unable to read cloudflared credentials file {credentials_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CloudflareApiError(f"invalid cloudflared credentials JSON: {credentials_path}: {exc}") from exc
    account_id = str(payload.get("AccountTag", "")).strip()
    if not account_id:
        raise CloudflareApiError(f"cloudflared credentials missing AccountTag: {credentials_path}")
    return account_id
def _resolve_tunnel_id_for_account(
    config: HomesrvctlConfig,
    *,
    account_id: str,
    api_client: CloudflareApiClient,
) -> str:
    tunnel_id = _resolve_local_tunnel_id(config)
    if tunnel_id is not None:
        return tunnel_id

    try:
        tunnel = api_client.get_tunnel(account_id, config.tunnel_name)
    except CloudflareApiError as exc:
        raise typer.BadParameter(f"could not resolve tunnel ID for {config.tunnel_name}: {exc}") from exc
    return tunnel.id.lower()


def _resolve_local_tunnel_id(config: HomesrvctlConfig) -> str | None:
    if UUID_RE.match(config.tunnel_name):
        return config.tunnel_name.lower()

    config_tunnel_id = _tunnel_id_from_config_file(config.cloudflared_config)
    if config_tunnel_id is not None:
        return config_tunnel_id

    return None


def _tunnel_id_from_config_file(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    try:
        parsed = _load_cloudflared_yaml(config_path)
    except CloudflareApiError:
        return None
    tunnel_value = str(parsed.get("tunnel", "")).strip()
    if UUID_RE.match(tunnel_value):
        return tunnel_value.lower()
    return None
def _load_cloudflared_yaml(config_path: Path) -> dict[str, object]:
    try:
        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise CloudflareApiError(f"unable to read cloudflared config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CloudflareApiError(f"invalid cloudflared config YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CloudflareApiError(f"invalid cloudflared config structure: expected mapping in {config_path}")
    return parsed


def _parse_tunnel_status(result: object, tunnel_ref: str) -> TunnelStatus:
    if not isinstance(result, dict):
        raise CloudflareApiError(f"Cloudflare returned an invalid tunnel response for {tunnel_ref}")
    tunnel_id = str(result.get("id", "")).strip()
    if not UUID_RE.match(tunnel_id):
        raise CloudflareApiError(f"Cloudflare returned an invalid tunnel ID for {tunnel_ref}")
    return TunnelStatus(
        id=tunnel_id,
        name=str(result.get("name", "")).strip(),
        status=str(result.get("status", "")).strip(),
    )


def _render_dns_record(record: dict[str, object]) -> str:
    record_type = str(record.get("type", "")).strip() or "DNS"
    content = str(record.get("content", "")).strip()
    detail = f"{record_type} -> {content}"
    if bool(record.get("proxied")):
        detail += " (proxied)"
    return detail


def _describe_single_dns_record(record_type: str, content: str, proxied: bool) -> str:
    detail = f"{record_type} -> {content}"
    if proxied:
        detail += " (proxied)"
    return detail


def _dns_mismatch_detail(record_type: str, content: str, proxied: bool, expected_content: str) -> str:
    current = _describe_single_dns_record(record_type, content, proxied)
    expected = f"CNAME -> {expected_content} (proxied)"
    if record_type != "CNAME":
        return f"wrong type {current}; expected {expected}"
    if content != expected_content:
        return f"wrong target {current}; expected {expected}"
    if not proxied:
        return f"wrong proxy setting {current}; expected {expected}"
    return current


def _records_to_status_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rendered: list[dict[str, object]] = []
    for record in records:
        rendered.append(
            {
                "type": str(record.get("type", "")).strip(),
                "content": str(record.get("content", "")).strip(),
                "proxied": bool(record.get("proxied")),
            }
        )
    return rendered


def _classify_dns_records(
    records: list[dict[str, object]],
    *,
    expected_content: str | None = None,
) -> dict[str, object]:
    routing_types = {"A", "AAAA", "CNAME"}
    ancillary_types = {"MX", "TXT", "CAA"}
    routing_records = [record for record in records if str(record.get("type", "")).strip().upper() in routing_types]
    ancillary_records = [record for record in records if str(record.get("type", "")).strip().upper() in ancillary_types]
    unknown_records = [
        record
        for record in records
        if str(record.get("type", "")).strip().upper() not in routing_types | ancillary_types
    ]
    matching_cname = None
    if expected_content is not None:
        for record in routing_records:
            if (
                str(record.get("type", "")).strip().upper() == "CNAME"
                and str(record.get("content", "")).strip() == expected_content
                and bool(record.get("proxied"))
            ):
                matching_cname = record
                break

    nonmatching_routing_records = [record for record in routing_records if record is not matching_cname]
    conflicts = len(nonmatching_routing_records) > 1 or bool(unknown_records)
    managed_record = matching_cname if matching_cname is not None else (nonmatching_routing_records[0] if nonmatching_routing_records else None)
    return {
        "routing_records": routing_records,
        "ancillary_records": ancillary_records,
        "unknown_records": unknown_records,
        "matching_cname": matching_cname,
        "managed_record": managed_record,
        "conflicts": conflicts,
    }
