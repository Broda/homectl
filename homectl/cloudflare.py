from __future__ import annotations

import json
import re
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import typer
import yaml

from homectl.models import HomectlConfig
from homectl.shell import run_command


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


class CloudflareApiClient:
    def __init__(self, api_token: str) -> None:
        token = api_token.strip()
        if not token:
            raise typer.BadParameter(
                "missing Cloudflare API token; set cloudflare_api_token in homectl config or CLOUDFLARE_API_TOKEN"
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

    def plan_dns_record(self, zone_id: str, record_name: str, content: str) -> ApiPlan:
        existing = self._list_dns_records(zone_id, record_name)
        if not existing:
            return ApiPlan("create", record_name, "CNAME", content)
        if len(existing) > 1:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )

        record = existing[0]
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

        if len(existing) > 1:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )

        record = existing[0]
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
        if len(existing) > 1:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )

        record = existing[0]
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
        if len(existing) > 1:
            raise CloudflareApiError(
                f"multiple DNS records exist for {record_name}; clean them up manually before retrying"
            )

        record = existing[0]
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
        if len(existing) > 1:
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
                detail=f"multiple DNS records exist: {', '.join(rendered_records)}",
                records=_records_to_status_records(existing),
            )

        record = existing[0]
        record_type = str(record.get("type", "")).strip()
        content = str(record.get("content", "")).strip()
        proxied = bool(record.get("proxied"))
        matches_expected = record_type == "CNAME" and content == expected_content and proxied
        detail = f"{record_type} -> {content}"
        if proxied:
            detail += " (proxied)"
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
                "User-Agent": "homectl/0.1.0",
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


def tunnel_cname_target(config: HomectlConfig) -> str:
    tunnel_id = _resolve_tunnel_id(config)
    return f"{tunnel_id}.cfargotunnel.com"


def _resolve_tunnel_id(config: HomectlConfig) -> str:
    if UUID_RE.match(config.tunnel_name):
        return config.tunnel_name.lower()

    if config.cloudflared_config.exists():
        parsed = yaml.safe_load(config.cloudflared_config.read_text(encoding="utf-8")) or {}
        tunnel_value = str(parsed.get("tunnel", "")).strip()
        if UUID_RE.match(tunnel_value):
            return tunnel_value.lower()
        if tunnel_value and UUID_RE.match(config.tunnel_name):
            return config.tunnel_name.lower()

    result = run_command(["cloudflared", "tunnel", "info", config.tunnel_name])
    if not result.ok:
        detail = result.stderr or result.stdout or "no output"
        raise typer.BadParameter(f"could not resolve tunnel ID for {config.tunnel_name}: {detail}")

    for line in result.stdout.splitlines():
        if line.startswith("ID:"):
            tunnel_id = line.split(":", 1)[1].strip()
            if UUID_RE.match(tunnel_id):
                return tunnel_id.lower()

    raise typer.BadParameter(f"could not parse tunnel ID from cloudflared tunnel info for {config.tunnel_name}")


def _render_dns_record(record: dict[str, object]) -> str:
    record_type = str(record.get("type", "")).strip() or "DNS"
    content = str(record.get("content", "")).strip()
    detail = f"{record_type} -> {content}"
    if bool(record.get("proxied")):
        detail += " (proxied)"
    return detail


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
