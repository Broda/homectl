from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re

import typer

from homesrvctl.services.infra.opentofu import (
    Runner,
    TofuCommandResult,
    Which,
    inspect_tofu,
    run_tofu_init,
    run_tofu_plan,
)
from homesrvctl.utils import validate_bare_domain

VALID_DMARC_POLICIES = {"none", "quarantine", "reject"}
SUBDOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


@dataclass(slots=True)
class WorkspaceFile:
    path: Path
    content: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "bytes": len(self.content.encode("utf-8")),
        }


@dataclass(slots=True)
class MailWorkspaceConfig:
    domain: str
    region: str
    mail_from_subdomain: str = "mail"
    dmarc_policy: str = "none"
    rua: str | None = None
    cloudflare_zone_id: str | None = None
    manage_domain_spf: bool = False
    manage_dmarc: bool = True

    @property
    def mail_from_domain(self) -> str:
        return f"{self.mail_from_subdomain}.{self.domain}"

    @property
    def dmarc_rua(self) -> str:
        if not self.rua:
            return ""
        value = self.rua.strip()
        if not value:
            return ""
        return value if value.startswith("mailto:") else f"mailto:{value}"

    def to_tfvars(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "aws_region": self.region,
            "mail_from_subdomain": self.mail_from_subdomain,
            "dmarc_policy": self.dmarc_policy,
            "dmarc_rua": self.dmarc_rua,
            "cloudflare_zone_id": self.cloudflare_zone_id or "",
            "manage_domain_spf": self.manage_domain_spf,
            "manage_dmarc": self.manage_dmarc,
        }


@dataclass(slots=True)
class InfraWorkspaceResult:
    ok: bool
    domain: str
    workspace_path: Path
    dry_run: bool
    files: list[WorkspaceFile]
    wrote_files: bool
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "ok": self.ok,
            "domain": self.domain,
            "workspace_path": str(self.workspace_path),
            "dry_run": self.dry_run,
            "files": [file.to_dict() for file in self.files],
            "wrote_files": self.wrote_files,
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class InfraPlanResult:
    ok: bool
    domain: str
    workspace_path: Path
    tofu_available: bool
    init_result: TofuCommandResult | None
    plan_result: TofuCommandResult | None
    has_changes: bool | None
    render_result: InfraWorkspaceResult | None = None
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "domain": self.domain,
            "workspace_path": str(self.workspace_path),
            "tofu_available": self.tofu_available,
            "init": self.init_result.to_dict() if self.init_result else None,
            "plan": self._plan_payload(),
            "has_changes": self.has_changes,
            "issues": self.issues,
        }
        if self.render_result:
            payload["render"] = self.render_result.to_dict()
        if self.error:
            payload["error"] = self.error
        return payload

    def _plan_payload(self) -> dict[str, object] | None:
        if not self.plan_result:
            return None
        payload = self.plan_result.to_dict()
        payload["detailed_exitcode"] = self.plan_result.returncode
        payload["has_changes"] = self.has_changes
        payload["ok"] = self.plan_result.returncode in {0, 2}
        return payload


def default_workspace_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return root / "homesrvctl" / "infra" / "workspaces" / "mail"


def default_mail_workspace_path(domain: str) -> Path:
    return default_workspace_root() / normalize_domain(domain)


def normalize_domain(domain: str) -> str:
    valid = validate_bare_domain(domain)
    if "/" in valid or "\\" in valid or valid in {".", ".."}:
        raise typer.BadParameter("domain must not contain path separators")
    return valid


def build_mail_workspace_config(
    domain: str,
    *,
    region: str | None,
    mail_from_subdomain: str = "mail",
    dmarc_policy: str = "none",
    rua: str | None = None,
    cloudflare_zone_id: str | None = None,
    manage_domain_spf: bool = False,
    manage_dmarc: bool = True,
    env: dict[str, str] | None = None,
) -> MailWorkspaceConfig:
    effective_env = env if env is not None else os.environ
    normalized_domain = normalize_domain(domain)
    selected_region = (
        region
        or effective_env.get("AWS_REGION")
        or effective_env.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    ).strip()
    if not selected_region:
        selected_region = "us-east-1"
    subdomain = mail_from_subdomain.strip().lower()
    if not SUBDOMAIN_RE.match(subdomain):
        raise typer.BadParameter("MAIL FROM subdomain must be a single DNS label")
    policy = dmarc_policy.strip().lower()
    if policy not in VALID_DMARC_POLICIES:
        raise typer.BadParameter("DMARC policy must be one of: none, quarantine, reject")
    return MailWorkspaceConfig(
        domain=normalized_domain,
        region=selected_region,
        mail_from_subdomain=subdomain,
        dmarc_policy=policy,
        rua=rua,
        cloudflare_zone_id=cloudflare_zone_id.strip() if cloudflare_zone_id and cloudflare_zone_id.strip() else None,
        manage_domain_spf=manage_domain_spf,
        manage_dmarc=manage_dmarc,
    )


def render_mail_workspace(
    config: MailWorkspaceConfig,
    *,
    workspace_path: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> InfraWorkspaceResult:
    workspace = (workspace_path or default_mail_workspace_path(config.domain)).expanduser()
    files = _workspace_files(config, workspace)
    if workspace.exists() and any(workspace.iterdir()) and not force:
        return InfraWorkspaceResult(
            ok=False,
            domain=config.domain,
            workspace_path=workspace,
            dry_run=dry_run,
            files=files,
            wrote_files=False,
            error=f"workspace already exists; use --force to overwrite generated files: {workspace}",
        )
    if dry_run:
        return InfraWorkspaceResult(
            ok=True,
            domain=config.domain,
            workspace_path=workspace,
            dry_run=True,
            files=files,
            wrote_files=False,
        )
    workspace.mkdir(parents=True, exist_ok=True)
    for file in files:
        file.path.parent.mkdir(parents=True, exist_ok=True)
        file.path.write_text(file.content, encoding="utf-8")
    return InfraWorkspaceResult(
        ok=True,
        domain=config.domain,
        workspace_path=workspace,
        dry_run=False,
        files=files,
        wrote_files=True,
    )


def plan_mail_workspace(
    config: MailWorkspaceConfig,
    *,
    workspace_path: Path | None = None,
    refresh_render: bool = False,
    force_render: bool = False,
    which: Which,
    runner: Runner,
) -> InfraPlanResult:
    workspace = (workspace_path or default_mail_workspace_path(config.domain)).expanduser()
    tofu_status = inspect_tofu(which=which, runner=runner)
    if not tofu_status.available:
        return InfraPlanResult(
            ok=False,
            domain=config.domain,
            workspace_path=workspace,
            tofu_available=False,
            init_result=None,
            plan_result=None,
            has_changes=None,
            issues=tofu_status.issues,
            error=tofu_status.issues[0] if tofu_status.issues else "OpenTofu unavailable",
        )

    render_result = None
    if refresh_render or not workspace.exists():
        render_result = render_mail_workspace(
            config,
            workspace_path=workspace,
            force=force_render or refresh_render,
        )
        if not render_result.ok:
            return InfraPlanResult(
                ok=False,
                domain=config.domain,
                workspace_path=workspace,
                tofu_available=True,
                init_result=None,
                plan_result=None,
                has_changes=None,
                render_result=render_result,
                issues=render_result.issues,
                error=render_result.error,
            )

    assert tofu_status.path is not None
    init_result = run_tofu_init(workspace, tofu_path=tofu_status.path, runner=runner)
    if not init_result.ok:
        return InfraPlanResult(
            ok=False,
            domain=config.domain,
            workspace_path=workspace,
            tofu_available=True,
            init_result=init_result,
            plan_result=None,
            has_changes=None,
            render_result=render_result,
            error=init_result.stderr or init_result.stdout or "OpenTofu init failed",
        )

    plan_result = run_tofu_plan(workspace, tofu_path=tofu_status.path, runner=runner)
    has_changes = plan_result.returncode == 2
    plan_ok = plan_result.returncode in {0, 2}
    return InfraPlanResult(
        ok=plan_ok,
        domain=config.domain,
        workspace_path=workspace,
        tofu_available=True,
        init_result=init_result,
        plan_result=plan_result,
        has_changes=has_changes if plan_ok else None,
        render_result=render_result,
        error=None if plan_ok else plan_result.stderr or plan_result.stdout or "OpenTofu plan failed",
    )


def _workspace_files(config: MailWorkspaceConfig, workspace: Path) -> list[WorkspaceFile]:
    return [
        WorkspaceFile(workspace / "main.tf", _main_tf()),
        WorkspaceFile(workspace / "variables.tf", _variables_tf()),
        WorkspaceFile(workspace / "outputs.tf", _outputs_tf()),
        WorkspaceFile(workspace / "terraform.tfvars.json", json.dumps(config.to_tfvars(), indent=2, sort_keys=True) + "\n"),
        WorkspaceFile(workspace / "README.md", _readme_md(config)),
    ]


def _main_tf() -> str:
    return """terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "cloudflare" {}

data "cloudflare_zones" "selected" {
  count = var.cloudflare_zone_id == "" ? 1 : 0
  name  = var.domain
}

locals {
  cloudflare_zone_id = var.cloudflare_zone_id != "" ? var.cloudflare_zone_id : data.cloudflare_zones.selected[0].result[0].id
  mail_from_domain   = "${var.mail_from_subdomain}.${var.domain}"
  dmarc_value        = var.dmarc_rua == "" ? "v=DMARC1; p=${var.dmarc_policy};" : "v=DMARC1; p=${var.dmarc_policy}; rua=${var.dmarc_rua};"
}

resource "aws_ses_domain_identity" "mail" {
  domain = var.domain
}

resource "aws_ses_domain_dkim" "mail" {
  domain = aws_ses_domain_identity.mail.domain
}

resource "aws_ses_domain_mail_from" "mail" {
  domain           = aws_ses_domain_identity.mail.domain
  mail_from_domain = local.mail_from_domain
}

resource "cloudflare_dns_record" "ses_identity" {
  zone_id = local.cloudflare_zone_id
  name    = "_amazonses.${var.domain}"
  type    = "TXT"
  content = aws_ses_domain_identity.mail.verification_token
  ttl     = 600
}

resource "cloudflare_dns_record" "ses_dkim" {
  for_each = toset(aws_ses_domain_dkim.mail.dkim_tokens)

  zone_id = local.cloudflare_zone_id
  name    = "${each.value}._domainkey.${var.domain}"
  type    = "CNAME"
  content = "${each.value}.dkim.amazonses.com"
  ttl     = 600
  proxied = false
}

resource "cloudflare_dns_record" "mail_from_mx" {
  zone_id  = local.cloudflare_zone_id
  name     = local.mail_from_domain
  type     = "MX"
  content  = "feedback-smtp.${var.aws_region}.amazonses.com"
  priority = 10
  ttl      = 600
}

resource "cloudflare_dns_record" "mail_from_spf" {
  zone_id = local.cloudflare_zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  content = "v=spf1 include:amazonses.com ~all"
  ttl     = 600
}

resource "cloudflare_dns_record" "domain_spf" {
  count = var.manage_domain_spf ? 1 : 0

  zone_id = local.cloudflare_zone_id
  name    = var.domain
  type    = "TXT"
  content = "v=spf1 include:amazonses.com ~all"
  ttl     = 600
}

resource "cloudflare_dns_record" "dmarc" {
  count = var.manage_dmarc ? 1 : 0

  zone_id = local.cloudflare_zone_id
  name    = "_dmarc.${var.domain}"
  type    = "TXT"
  content = local.dmarc_value
  ttl     = 600
}
"""


def _variables_tf() -> str:
    return """variable "domain" {
  description = "Bare domain to configure for SES outbound mail."
  type        = string
}

variable "aws_region" {
  description = "AWS region where SES resources are planned."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID. Leave empty to let the provider look up the zone by domain."
  type        = string
  default     = ""
}

variable "mail_from_subdomain" {
  description = "Subdomain used for SES custom MAIL FROM."
  type        = string
  default     = "mail"
}

variable "dmarc_policy" {
  description = "DMARC policy for the generated _dmarc TXT record."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "quarantine", "reject"], var.dmarc_policy)
    error_message = "dmarc_policy must be none, quarantine, or reject."
  }
}

variable "dmarc_rua" {
  description = "Optional DMARC aggregate report URI, usually mailto:postmaster@example.com."
  type        = string
  default     = ""
}

variable "manage_domain_spf" {
  description = "Whether to manage an apex SPF TXT record for SES. Disabled by default to avoid clobbering existing SPF ownership."
  type        = bool
  default     = false
}

variable "manage_dmarc" {
  description = "Whether to manage the _dmarc TXT record."
  type        = bool
  default     = true
}
"""


def _outputs_tf() -> str:
    return """output "domain" {
  value = var.domain
}

output "ses_identity_verification_record" {
  value = {
    name  = cloudflare_dns_record.ses_identity.name
    type  = cloudflare_dns_record.ses_identity.type
    value = cloudflare_dns_record.ses_identity.content
  }
}

output "ses_dkim_record_names" {
  value = [for record in cloudflare_dns_record.ses_dkim : record.name]
}

output "mail_from_domain" {
  value = local.mail_from_domain
}
"""


def _readme_md(config: MailWorkspaceConfig) -> str:
    return f"""# homesrvctl generated OpenTofu workspace

This workspace was generated by `homesrvctl infra render mail`.

Current homesrvctl OpenTofu support is plan-only. Use `homesrvctl infra plan mail {config.domain}` to run
`tofu init` and `tofu plan`; homesrvctl does not run `tofu apply` or `tofu destroy` in this slice.

Do not put secrets in this workspace. Provider authentication is read from standard environment/provider
configuration, including:

- AWS standard credential chain, `AWS_PROFILE`, `AWS_REGION`, or `AWS_DEFAULT_REGION`
- `CLOUDFLARE_API_TOKEN`

Planned scope:

- AWS SES domain identity for `{config.domain}`
- SES DKIM tokens
- SES custom MAIL FROM domain `{config.mail_from_domain}`
- Cloudflare DNS records for SES verification, DKIM, MAIL FROM MX/SPF, and optional DMARC/SPF records
"""
