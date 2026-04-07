from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
import yaml


class CloudflaredConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class IngressChange:
    action: str
    hostname: str
    service: str


def plan_domain_ingress(config_path: Path, domain: str, service_url: str) -> list[IngressChange]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    return _reconcile_ingress(ingress, domain, service_url)


def apply_domain_ingress(config_path: Path, domain: str, service_url: str) -> list[IngressChange]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    changes = _reconcile_ingress(ingress, domain, service_url)
    if all(change.action == "noop" for change in changes):
        return changes

    non_target_entries = [
        entry for entry in ingress[:-1] if str(entry.get("hostname", "")).strip().lower() not in _target_hostnames(domain)
    ]
    target_entries = [_build_entry(hostname, service_url) for hostname in _target_hostnames(domain)]
    parsed["ingress"] = non_target_entries + target_entries + [ingress[-1]]
    config_path.write_text(yaml.safe_dump(parsed, sort_keys=False), encoding="utf-8")
    return changes


def plan_domain_ingress_removal(config_path: Path, domain: str) -> list[IngressChange]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    return _plan_ingress_removal(ingress, domain)


def apply_domain_ingress_removal(config_path: Path, domain: str) -> list[IngressChange]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    changes = _plan_ingress_removal(ingress, domain)
    if all(change.action == "noop" for change in changes):
        return changes

    parsed["ingress"] = [
        entry for entry in ingress[:-1] if str(entry.get("hostname", "")).strip().lower() not in _target_hostnames(domain)
    ] + [ingress[-1]]
    config_path.write_text(yaml.safe_dump(parsed, sort_keys=False), encoding="utf-8")
    return changes


def validate_ingress_config(config_path: Path) -> str:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    fallback = ingress[-1]
    return str(fallback.get("service", "")).strip()


def find_hostname_route(config_path: Path, hostname: str) -> str | None:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    entries = ingress[:-1]
    wanted = hostname.strip().lower()
    wildcard = _wildcard_for(wanted)

    for entry in entries:
        entry_hostname = str(entry.get("hostname", "")).strip().lower()
        if entry_hostname == wanted:
            return str(entry.get("service", "")).strip()

    if wildcard is None:
        return None

    for entry in entries:
        entry_hostname = str(entry.get("hostname", "")).strip().lower()
        if entry_hostname == wildcard:
            return str(entry.get("service", "")).strip()
    return None


def find_exact_hostname_route(config_path: Path, hostname: str) -> str | None:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    wanted = hostname.strip().lower()

    for entry in ingress[:-1]:
        entry_hostname = str(entry.get("hostname", "")).strip().lower()
        if entry_hostname == wanted:
            return str(entry.get("service", "")).strip()
    return None


def _reconcile_ingress(ingress: list[dict[str, object]], domain: str, service_url: str) -> list[IngressChange]:
    targets = _target_hostnames(domain)
    existing_by_hostname: dict[str, dict[str, object]] = {}

    for entry in ingress[:-1]:
        hostname = str(entry.get("hostname", "")).strip().lower()
        if not hostname:
            continue
        if hostname in targets:
            if hostname in existing_by_hostname:
                raise CloudflaredConfigError(f"duplicate ingress hostname entry found: {hostname}")
            existing_by_hostname[hostname] = entry

    changes: list[IngressChange] = []
    for hostname in targets:
        existing = existing_by_hostname.get(hostname)
        if existing is None:
            changes.append(IngressChange("create", hostname, service_url))
            continue

        current_service = str(existing.get("service", "")).strip()
        if current_service == service_url:
            changes.append(IngressChange("noop", hostname, service_url))
        else:
            changes.append(IngressChange("update", hostname, service_url))
    return changes


def _plan_ingress_removal(ingress: list[dict[str, object]], domain: str) -> list[IngressChange]:
    targets = _target_hostnames(domain)
    existing_by_hostname: dict[str, dict[str, object]] = {}

    for entry in ingress[:-1]:
        hostname = str(entry.get("hostname", "")).strip().lower()
        if not hostname:
            continue
        if hostname in targets:
            if hostname in existing_by_hostname:
                raise CloudflaredConfigError(f"duplicate ingress hostname entry found: {hostname}")
            existing_by_hostname[hostname] = entry

    changes: list[IngressChange] = []
    for hostname in targets:
        existing = existing_by_hostname.get(hostname)
        if existing is None:
            changes.append(IngressChange("noop", hostname, ""))
            continue
        changes.append(IngressChange("delete", hostname, str(existing.get("service", "")).strip()))
    return changes


def _load_config(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise typer.BadParameter(f"cloudflared config file missing: {config_path}")

    try:
        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CloudflaredConfigError(f"invalid cloudflared config YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise CloudflaredConfigError(f"cloudflared config must be a YAML mapping: {config_path}")
    return parsed


def _normalize_ingress(parsed: dict[str, object], config_path: Path) -> list[dict[str, object]]:
    ingress = parsed.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise CloudflaredConfigError(f"cloudflared ingress must be a non-empty list: {config_path}")

    normalized: list[dict[str, object]] = []
    fallback_index: int | None = None
    for index, entry in enumerate(ingress):
        if not isinstance(entry, dict):
            raise CloudflaredConfigError(f"cloudflared ingress entries must be mappings: {config_path}")
        normalized.append(entry)
        if "hostname" not in entry:
            if fallback_index is not None:
                raise CloudflaredConfigError(f"cloudflared ingress must contain exactly one fallback service: {config_path}")
            fallback_index = index

    if fallback_index is None:
        raise CloudflaredConfigError(f"cloudflared ingress is missing a fallback service: {config_path}")
    if fallback_index != len(normalized) - 1:
        raise CloudflaredConfigError(
            f"cloudflared fallback service must be the last ingress entry: {config_path}"
        )
    if "service" not in normalized[-1]:
        raise CloudflaredConfigError(f"cloudflared fallback ingress entry must define a service: {config_path}")
    return normalized


def _target_hostnames(domain: str) -> list[str]:
    bare = domain.strip().lower()
    return [bare, f"*.{bare}"]


def _build_entry(hostname: str, service_url: str) -> dict[str, str]:
    return {"hostname": hostname, "service": service_url}


def _wildcard_for(hostname: str) -> str | None:
    labels = hostname.split(".")
    if len(labels) < 3:
        return None
    return f"*.{'.'.join(labels[1:])}"
