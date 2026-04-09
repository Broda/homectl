from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
import yaml
from homesrvctl.shell import command_exists, run_command


class CloudflaredConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class IngressChange:
    action: str
    hostname: str
    service: str


@dataclass(slots=True)
class IngressRouteMatch:
    hostname: str
    service: str


@dataclass(slots=True)
class CloudflaredConfigValidation:
    ok: bool
    detail: str
    command: list[str] | None = None
    method: str = "structural"
    warnings: list[str] | None = None


@dataclass(slots=True)
class CloudflaredConfigWarning:
    code: str
    detail: str
    hint: str | None = None

    def render(self) -> str:
        if not self.hint:
            return self.detail
        return f"{self.detail}. Hint: {self.hint}"


def describe_cloudflared_config_error(error: CloudflaredConfigError | typer.BadParameter) -> str:
    message = str(error)
    hint = _cloudflared_config_hint(message)
    if not hint:
        return message
    return f"{message}. Hint: {hint}"


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


def test_cloudflared_config(config_path: Path) -> CloudflaredConfigValidation:
    if command_exists("cloudflared"):
        command = ["cloudflared", "tunnel", "--config", str(config_path), "ingress", "validate"]
        result = run_command(command, quiet=True)
        if result.ok:
            detail = result.stdout or result.stderr or f"cloudflared ingress validate passed for {config_path}"
            return CloudflaredConfigValidation(
                ok=True,
                detail=detail,
                command=command,
                method="cloudflared",
                warnings=collect_cloudflared_config_warnings(config_path),
            )
        detail = result.stderr or result.stdout or "cloudflared ingress validate failed"
        return CloudflaredConfigValidation(ok=False, detail=detail, command=command, method="cloudflared")

    try:
        fallback = validate_ingress_config(config_path)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        return CloudflaredConfigValidation(
            ok=False,
            detail=describe_cloudflared_config_error(exc),
            command=None,
            method="structural",
        )
    return CloudflaredConfigValidation(
        ok=True,
        detail=f"fallback service {fallback}",
        command=None,
        method="structural",
        warnings=collect_cloudflared_config_warnings(config_path),
    )


def collect_cloudflared_config_warnings(config_path: Path) -> list[str]:
    return [warning.render() for warning in inspect_cloudflared_config_warnings(config_path)]


def inspect_cloudflared_config_warnings(config_path: Path) -> list[CloudflaredConfigWarning]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    warnings: list[CloudflaredConfigWarning] = []
    host_entries = [
        (index, str(entry.get("hostname", "")).strip().lower(), str(entry.get("service", "")).strip())
        for index, entry in enumerate(ingress[:-1])
        if str(entry.get("hostname", "")).strip()
    ]
    for index, hostname, service in host_entries:
        for later_index, later_hostname, _later_service in host_entries[index + 1 :]:
            if hostname == later_hostname:
                continue
            if _wildcard_precedence_risk(hostname, later_hostname):
                warnings.append(
                    CloudflaredConfigWarning(
                        code="wildcard-precedence-risk",
                        detail=(
                            "earlier wildcard rule "
                            f"{hostname} -> {service} may capture hosts intended for later wildcard {later_hostname} "
                            f"at ingress index {later_index}"
                        ),
                        hint=(
                            f"move the narrower wildcard {later_hostname} above {hostname}, "
                            "or narrow/remove the broader wildcard if it is no longer needed"
                        ),
                    )
                )
                continue
            if _hostname_matches(hostname, later_hostname):
                warnings.append(
                    CloudflaredConfigWarning(
                        code="wildcard-shadows-hostname",
                        detail=(
                            "earlier ingress rule "
                            f"{hostname} -> {service} may shadow later hostname {later_hostname} at ingress index "
                            f"{later_index}"
                        ),
                        hint=(
                            f"move {later_hostname} above {hostname}, "
                            "or narrow/remove the earlier rule so the specific hostname matches first"
                        ),
                    )
                )
    return warnings


def find_hostname_route(config_path: Path, hostname: str) -> str | None:
    match = inspect_hostname_route(config_path, hostname)
    return match.service if match else None


def inspect_hostname_route(config_path: Path, hostname: str) -> IngressRouteMatch | None:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    wanted = hostname.strip().lower()
    for entry in ingress[:-1]:
        entry_hostname = str(entry.get("hostname", "")).strip().lower()
        if not entry_hostname or not _hostname_matches(entry_hostname, wanted):
            continue
        return IngressRouteMatch(
            hostname=entry_hostname,
            service=str(entry.get("service", "")).strip(),
        )
    return None


def find_exact_hostname_route(config_path: Path, hostname: str) -> str | None:
    routes = list_exact_hostname_routes(config_path, hostname)
    return routes[0].service if routes else None


def list_exact_hostname_routes(config_path: Path, hostname: str) -> list[IngressRouteMatch]:
    parsed = _load_config(config_path)
    ingress = _normalize_ingress(parsed, config_path)
    wanted = hostname.strip().lower()
    matches: list[IngressRouteMatch] = []

    for entry in ingress[:-1]:
        entry_hostname = str(entry.get("hostname", "")).strip().lower()
        if entry_hostname == wanted:
            matches.append(
                IngressRouteMatch(
                    hostname=entry_hostname,
                    service=str(entry.get("service", "")).strip(),
                )
            )
    return matches


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


def _hostname_matches(pattern: str, hostname: str) -> bool:
    if pattern == hostname:
        return True
    if not pattern.startswith("*."):
        return False

    suffix = pattern[2:]
    if not suffix or not hostname.endswith(f".{suffix}"):
        return False

    return hostname.count(".") > suffix.count(".")


def _wildcard_precedence_risk(pattern: str, later_hostname: str) -> bool:
    if not pattern.startswith("*.") or not later_hostname.startswith("*."):
        return False

    pattern_suffix = pattern[2:]
    later_suffix = later_hostname[2:]
    if not pattern_suffix or not later_suffix or pattern_suffix == later_suffix:
        return False

    return later_suffix.endswith(f".{pattern_suffix}")


def _cloudflared_config_hint(message: str) -> str | None:
    if "duplicate ingress hostname entry found:" in message:
        hostname = message.rsplit(":", 1)[-1].strip()
        return f"remove the duplicate '{hostname}' ingress entry so the hostname appears only once"
    if "fallback service must be the last ingress entry" in message:
        return "move the hostname-less fallback service to the end of the ingress list"
    if "must contain exactly one fallback service" in message:
        return "keep exactly one hostname-less fallback service entry in the ingress list"
    if "missing a fallback service" in message:
        return "add one hostname-less fallback service entry, usually service: http_status:404, at the end"
    if "entries must be mappings" in message:
        return "rewrite each ingress entry as a YAML mapping with keys like hostname and service"
    if "must be a non-empty list" in message:
        return "define ingress as a YAML list with hostname routes followed by one fallback service"
    if "config file missing" in message:
        return "create the configured cloudflared YAML file or point homesrvctl at the correct path"
    if "invalid cloudflared config YAML" in message:
        return "fix the YAML syntax before retrying"
    return None
