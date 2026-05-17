from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Callable

from homesrvctl.cloudflare import CloudflareApiClient, CloudflareApiError
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.services.observers.models import ObservationRecord, ObserverResult
from homesrvctl.services.refresh import utc_now_iso
from homesrvctl.services.stacks import iter_stack_dirs

SES_PROVIDER_OBSERVER = "ses_provider"
SES_DOMAIN_ENV = "HOMESRVCTL_SES_DOMAINS"


@dataclass(slots=True)
class SesObserverSetupError(RuntimeError):
    message: str
    reason: str

    def __str__(self) -> str:
        return self.message


class Boto3SesClient:
    def __init__(self, region: str) -> None:
        try:
            boto3 = importlib.import_module("boto3")
        except ImportError as exc:
            raise SesObserverSetupError(
                "AWS SES observer requires boto3; install `homesrvctl[aws]` or inject boto3 into the environment",
                "missing_boto3",
            ) from exc
        self.region = region
        self._client = boto3.client("ses", region_name=region)

    def get_account(self) -> dict[str, object]:
        account: dict[str, object] = {}
        account["sending_enabled"] = bool(self._client.get_account_sending_enabled().get("Enabled", False))
        try:
            quota = self._client.get_send_quota()
        except Exception:
            quota = {}
        if quota:
            account["quota"] = {
                "max_24_hour_send": quota.get("Max24HourSend"),
                "max_send_rate": quota.get("MaxSendRate"),
                "sent_last_24_hours": quota.get("SentLast24Hours"),
            }
        return account

    def list_domain_identities(self) -> list[str]:
        identities: list[str] = []
        next_token: str | None = None
        while True:
            kwargs: dict[str, object] = {"IdentityType": "Domain"}
            if next_token:
                kwargs["NextToken"] = next_token
            payload = self._client.list_identities(**kwargs)
            identities.extend(str(identity) for identity in payload.get("Identities", []))
            next_token = payload.get("NextToken")
            if not next_token:
                return identities

    def get_verification_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return self._client.get_identity_verification_attributes(Identities=domains).get("VerificationAttributes", {})

    def get_dkim_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return self._client.get_identity_dkim_attributes(Identities=domains).get("DkimAttributes", {})

    def get_mail_from_attributes(self, domains: list[str]) -> dict[str, dict[str, object]]:
        return self._client.get_identity_mail_from_domain_attributes(Identities=domains).get("MailFromDomainAttributes", {})


def observe_ses_provider(
    config: HomesrvctlConfig,
    *,
    client_factory: Callable[[str], object] = Boto3SesClient,
    cloudflare_client_factory: Callable[[str], object] = CloudflareApiClient,
    env: dict[str, str] | None = None,
) -> ObserverResult:
    started_at = utc_now_iso()
    effective_env = env if env is not None else os.environ
    region = _aws_region(effective_env)
    targets = _candidate_domains(config, effective_env)
    issues: list[str] = []
    next_steps: list[str] = []
    data: dict[str, object] = {
        "boto3_available": None,
        "aws_region": region,
        "credentials_available": "unknown",
        "targets": targets,
        "target_count": len(targets),
        "account_status": None,
        "sending_enabled": None,
        "identities_checked": 0,
        "domain_results": [],
        "required_dns_records": [],
        "dns_check_provider": "none",
        "dns_records_checked": 0,
        "next_steps": next_steps,
    }

    if not region:
        data["boto3_available"] = "unknown"
        issues.append("AWS region is not configured")
        next_steps.append("Set AWS_REGION or AWS_DEFAULT_REGION before running SES observation")
        return _result(started_at, "blocked", "AWS region missing", data, issues)

    try:
        client = client_factory(region)
    except SesObserverSetupError as exc:
        data["boto3_available"] = exc.reason != "missing_boto3"
        data["credentials_available"] = "unknown"
        issues.append(str(exc))
        if exc.reason == "missing_boto3":
            next_steps.append("Install the optional AWS SDK support with `pipx inject homesrvctl boto3` or `pipx install 'homesrvctl[aws]'`")
        return _result(started_at, "blocked", "AWS SES observer unavailable", data, issues)
    except Exception as exc:
        data["boto3_available"] = True
        issue = _aws_error_message(exc)
        issues.append(issue)
        next_steps.append("Check AWS credentials and SES permissions for read-only identity/account inspection")
        return _result(started_at, "blocked", "AWS SES client unavailable", data, issues)

    data["boto3_available"] = True
    try:
        account = client.get_account()  # type: ignore[attr-defined]
        identities = client.list_domain_identities()  # type: ignore[attr-defined]
    except Exception as exc:
        data["credentials_available"] = False
        issue = _aws_error_message(exc)
        issues.append(issue)
        next_steps.append("Configure AWS credentials with read-only SES permissions")
        return _result(started_at, "blocked", "AWS SES account inspection failed", data, issues)

    data["credentials_available"] = True
    data["account_status"] = account
    data["sending_enabled"] = account.get("sending_enabled")
    if account.get("sending_enabled") is False:
        issues.append("SES account sending is disabled or still in sandbox for this region")
        next_steps.append("Check SES account sending status and production access in AWS")

    if not targets:
        return _result(started_at, "unknown", "SES observer has no domain targets", data, issues)

    data["identities_checked"] = len(targets)
    try:
        verification = client.get_verification_attributes(targets)  # type: ignore[attr-defined]
        dkim = client.get_dkim_attributes(targets)  # type: ignore[attr-defined]
        mail_from = client.get_mail_from_attributes(targets)  # type: ignore[attr-defined]
    except Exception as exc:
        issue = _aws_error_message(exc)
        issues.append(issue)
        next_steps.append("Check SES identity read permissions")
        return _result(started_at, "blocked", "AWS SES identity inspection failed", data, issues)

    identity_set = set(str(identity) for identity in identities)
    domain_results: list[dict[str, object]] = []
    required_records: list[dict[str, object]] = []
    for domain in targets:
        domain_result = _domain_result(
            domain,
            region=region,
            identity_exists=domain in identity_set or domain in verification,
            verification=verification.get(domain, {}),
            dkim=dkim.get(domain, {}),
            mail_from=mail_from.get(domain, {}),
        )
        domain_results.append(domain_result)
        required_records.extend(domain_result["required_dns_records"])  # type: ignore[arg-type]
        for issue in domain_result["issues"]:  # type: ignore[index]
            issues.append(f"{domain}: {issue}")
        for step in domain_result["next_steps"]:  # type: ignore[index]
            next_steps.append(str(step))

    data["domain_results"] = domain_results
    data["required_dns_records"] = required_records
    _maybe_check_cloudflare_dns(
        config,
        data,
        required_records,
        cloudflare_client_factory=cloudflare_client_factory,
        issues=issues,
        next_steps=next_steps,
    )
    status = _overall_status(data, issues)
    return _result(started_at, status, _summary(status, data), data, issues)


def _aws_region(env: dict[str, str]) -> str | None:
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    return region.strip() if region and region.strip() else None


def _candidate_domains(config: HomesrvctlConfig, env: dict[str, str]) -> list[str]:
    env_domains = env.get(SES_DOMAIN_ENV, "")
    if env_domains.strip():
        return sorted({domain.strip().lower().rstrip(".") for domain in env_domains.split(",") if domain.strip()})
    if not config.sites_root.exists():
        return []
    domains: set[str] = set()
    for stack_dir in iter_stack_dirs(config):
        labels = stack_dir.name.lower().rstrip(".").split(".")
        if len(labels) >= 2:
            domains.add(".".join(labels[-2:]))
    return sorted(domains)


def _domain_result(
    domain: str,
    *,
    region: str,
    identity_exists: bool,
    verification: dict[str, object],
    dkim: dict[str, object],
    mail_from: dict[str, object],
) -> dict[str, object]:
    issues: list[str] = []
    next_steps: list[str] = []
    records: list[dict[str, object]] = []
    verification_status = str(verification.get("VerificationStatus", "missing" if not identity_exists else "unknown"))
    verification_token = _optional_str(verification.get("VerificationToken"))
    if not identity_exists:
        issues.append("SES domain identity is missing")
        next_steps.append(f"Create and verify the SES domain identity for {domain}")
    elif not _is_success(verification_status):
        issues.append(f"SES domain identity verification is {verification_status}")
        next_steps.append(f"Publish the SES verification DNS record for {domain}")
    if verification_token:
        records.append(_record("_amazonses." + domain, "TXT", verification_token, "ses_identity_verification"))

    dkim_enabled = bool(dkim.get("DkimEnabled", False))
    dkim_status = str(dkim.get("DkimVerificationStatus", "unknown"))
    dkim_tokens = [str(token) for token in dkim.get("DkimTokens", []) if str(token).strip()]
    if identity_exists and not dkim_enabled:
        issues.append("DKIM is not enabled for the SES identity")
        next_steps.append(f"Enable DKIM for {domain} in SES")
    elif identity_exists and dkim_status != "unknown" and not _is_success(dkim_status):
        issues.append(f"DKIM verification is {dkim_status}")
        next_steps.append(f"Publish the SES DKIM CNAME records for {domain}")
    for token in dkim_tokens:
        records.append(_record(f"{token}._domainkey.{domain}", "CNAME", f"{token}.dkim.amazonses.com", "ses_dkim"))

    mail_from_domain = _optional_str(mail_from.get("MailFromDomain"))
    mail_from_status = str(mail_from.get("MailFromDomainStatus", "not_configured" if not mail_from_domain else "unknown"))
    if mail_from_domain:
        if not _is_success(mail_from_status):
            issues.append(f"custom MAIL FROM verification is {mail_from_status}")
            next_steps.append(f"Publish MX and SPF records for custom MAIL FROM domain {mail_from_domain}")
        records.append(_record(mail_from_domain, "MX", f"10 feedback-smtp.{region}.amazonses.com", "ses_mail_from_mx"))
        records.append(_record(mail_from_domain, "TXT", "v=spf1 include:amazonses.com ~all", "ses_mail_from_spf"))
    else:
        next_steps.append(f"Configure a custom MAIL FROM domain for {domain} if SPF alignment is required")

    records.append(_record(domain, "TXT", "v=spf1 include:amazonses.com ~all", "ses_spf_guidance", recommended=True))
    records.append(_record(f"_dmarc.{domain}", "TXT", None, "dmarc_guidance", recommended=True))
    status = "ready" if identity_exists and not issues else "degraded"
    return {
        "domain": domain,
        "status": status,
        "identity_exists": identity_exists,
        "identity_type": "domain" if identity_exists else None,
        "verification_status": verification_status,
        "dkim_enabled": dkim_enabled,
        "dkim_status": dkim_status,
        "dkim_tokens": dkim_tokens,
        "mail_from_domain": mail_from_domain,
        "mail_from_status": mail_from_status,
        "required_dns_records": records,
        "issues": issues,
        "next_steps": next_steps,
    }


def _maybe_check_cloudflare_dns(
    config: HomesrvctlConfig,
    data: dict[str, object],
    required_records: list[dict[str, object]],
    *,
    cloudflare_client_factory: Callable[[str], object],
    issues: list[str],
    next_steps: list[str],
) -> None:
    token = config.cloudflare_api_token.strip()
    if not token:
        return
    comparable = [record for record in required_records if record.get("content")]
    if not comparable:
        return
    try:
        client = cloudflare_client_factory(token)
    except Exception as exc:
        data["dns_check_provider"] = "cloudflare"
        issues.append(f"Cloudflare DNS comparison unavailable: {exc}")
        next_steps.append("Check Cloudflare token availability if DNS comparison is desired")
        return

    data["dns_check_provider"] = "cloudflare"
    dns_results: list[dict[str, object]] = []
    for record in comparable:
        dns_result = _check_cloudflare_record(client, record)
        dns_results.append(dns_result)
        data["dns_records_checked"] = int(data.get("dns_records_checked", 0)) + 1
        if dns_result["status"] in {"missing", "wrong", "ambiguous", "error"}:
            issues.append(f"{record['name']}: DNS {dns_result['status']}")
            next_steps.append(f"Publish or fix {record['type']} record {record['name']}")
    data["dns_results"] = dns_results


def _check_cloudflare_record(client: object, record: dict[str, object]) -> dict[str, object]:
    name = str(record["name"])
    record_type = str(record["type"])
    expected = str(record["content"])
    try:
        zone = _resolve_zone_for_name(client, name)
        zone_id = str(zone.get("id", ""))
        records = _list_cloudflare_records(client, zone_id, name)
    except Exception as exc:
        return {"name": name, "type": record_type, "status": "error", "detail": str(exc)}
    matching_type = [item for item in records if str(item.get("type", "")).upper() == record_type.upper()]
    matching_content = [
        item for item in matching_type if _normalize_dns_content(item, record_type) == _normalize_expected_content(expected, record_type)
    ]
    if not matching_type:
        return {"name": name, "type": record_type, "status": "missing", "record_count": 0}
    if len(matching_type) > 1 and not matching_content:
        return {"name": name, "type": record_type, "status": "ambiguous", "record_count": len(matching_type)}
    if not matching_content:
        return {"name": name, "type": record_type, "status": "wrong", "record_count": len(matching_type)}
    return {"name": name, "type": record_type, "status": "present", "record_count": len(matching_type)}


def _resolve_zone_for_name(client: object, name: str) -> dict[str, object]:
    labels = name.rstrip(".").split(".")
    last_error: str | None = None
    for index in range(max(0, len(labels) - 1)):
        candidate = ".".join(labels[index:])
        try:
            zone = client.get_zone(candidate)  # type: ignore[attr-defined]
        except CloudflareApiError as exc:
            last_error = str(exc)
            continue
        return zone
    raise CloudflareApiError(last_error or f"Cloudflare zone not found or not accessible for {name}")


def _list_cloudflare_records(client: object, zone_id: str, name: str) -> list[dict[str, object]]:
    if hasattr(client, "list_dns_records"):
        return client.list_dns_records(zone_id, name)  # type: ignore[attr-defined]
    if hasattr(client, "_list_dns_records"):
        return client._list_dns_records(zone_id, name)  # type: ignore[attr-defined]
    raise CloudflareApiError("Cloudflare client cannot list DNS records")


def _normalize_dns_content(record: dict[str, object], record_type: str) -> str:
    content = str(record.get("content", "")).strip().strip('"')
    if record_type.upper() == "MX" and record.get("priority") is not None:
        return f"{record.get('priority')} {content}".strip()
    return content


def _normalize_expected_content(content: str, record_type: str) -> str:
    normalized = content.strip().strip('"')
    return " ".join(normalized.split()) if record_type.upper() == "MX" else normalized


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
        observer_name=SES_PROVIDER_OBSERVER,
        ok=status == "ready" or (status == "unknown" and not issues),
        started_at=started_at,
        finished_at=finished_at,
        target_type="provider",
        target="ses",
        status=status,
        summary=summary,
        observations=[
            ObservationRecord(
                source=SES_PROVIDER_OBSERVER,
                target_type="provider",
                target="ses",
                status=status,
                detail=summary,
                data=data,
            )
        ],
        issues=issues,
    )


def _overall_status(data: dict[str, object], issues: list[str]) -> str:
    if data.get("credentials_available") is False or not data.get("aws_region") or data.get("boto3_available") is False:
        return "blocked"
    if not data.get("targets"):
        return "unknown" if not issues else "degraded"
    if issues:
        return "degraded"
    return "ready"


def _summary(status: str, data: dict[str, object]) -> str:
    if status == "ready":
        return f"SES outbound readiness OK for {data.get('identities_checked', 0)} domains"
    if status == "unknown":
        return "SES observer has no domain targets"
    if status == "blocked":
        return "SES provider observation blocked"
    return f"SES provider issues found for {data.get('identities_checked', 0)} domains"


def _record(
    name: str,
    record_type: str,
    content: str | None,
    purpose: str,
    *,
    recommended: bool = False,
) -> dict[str, object]:
    return {
        "name": name,
        "type": record_type,
        "content": content,
        "purpose": purpose,
        "recommended": recommended,
    }


def _is_success(status: str) -> bool:
    return status.lower() in {"success", "verified", "enabled"}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _aws_error_message(exc: Exception) -> str:
    name = exc.__class__.__name__
    message = str(exc)
    if name in {"NoCredentialsError", "PartialCredentialsError", "CredentialRetrievalError"}:
        return f"AWS credentials unavailable: {message}"
    return message or name
