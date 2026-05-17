from __future__ import annotations

import json
from pathlib import Path
import shutil

import typer

from homesrvctl.services.infra.mail_workspace import (
    build_mail_workspace_config,
    default_mail_workspace_path,
    default_workspace_root,
    plan_mail_workspace,
    render_mail_workspace,
)
from homesrvctl.services.infra.opentofu import inspect_tofu
from homesrvctl.shell import run_command
from homesrvctl.utils import success, warn, with_json_schema

infra_cli = typer.Typer(help="Render and plan optional OpenTofu infrastructure workspaces.")
render_cli = typer.Typer(help="Render OpenTofu workspaces without running OpenTofu.")
plan_cli = typer.Typer(help="Run plan-only OpenTofu workflows.")
infra_cli.add_typer(render_cli, name="render")
infra_cli.add_typer(plan_cli, name="plan")


@infra_cli.command("status")
def infra_status(
    domain: str | None = typer.Option(None, "--domain", help="Inspect workspace status for a mail domain."),
    workspace: Path | None = typer.Option(None, "--workspace", help="Inspect a custom workspace path."),
    json_output: bool = typer.Option(False, "--json", help="Print infrastructure status as JSON."),
) -> None:
    """Report OpenTofu availability and generated workspace status."""
    tofu = inspect_tofu(which=shutil.which, runner=run_command)
    workspace_path = None
    workspace_exists = False
    if workspace is not None:
        workspace_path = workspace.expanduser()
        workspace_exists = workspace_path.exists()
    elif domain:
        workspace_path = default_mail_workspace_path(domain)
        workspace_exists = workspace_path.exists()

    payload = {
        "action": "infra_status",
        "ok": tofu.ok,
        **tofu.to_dict(),
        "workspace_root": str(default_workspace_root()),
        "domain": domain,
        "workspace_path": str(workspace_path) if workspace_path else None,
        "workspace_exists": workspace_exists,
    }
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        return

    if tofu.available:
        success(f"OpenTofu available: {tofu.path} ({tofu.version or 'version unknown'})")
    else:
        warn("OpenTofu unavailable")
    typer.echo(f"workspace_root: {default_workspace_root()}")
    if workspace_path:
        typer.echo(f"workspace: {workspace_path} exists={'yes' if workspace_exists else 'no'}")
    for issue in tofu.issues:
        typer.echo(f"- {issue}")


@render_cli.command("mail")
def infra_render_mail(
    domain: str = typer.Argument(..., help="Bare domain to render SES/Cloudflare mail infrastructure for."),
    provider: str = typer.Option("ses", "--provider", help="Mail provider to render. Only `ses` is supported."),
    region: str | None = typer.Option(None, "--region", help="AWS region for SES resources."),
    mail_from_subdomain: str = typer.Option("mail", "--mail-from-subdomain", help="Custom MAIL FROM subdomain."),
    dmarc_policy: str = typer.Option("none", "--dmarc-policy", help="DMARC policy: none, quarantine, or reject."),
    rua: str | None = typer.Option(None, "--rua", help="Optional DMARC aggregate report email or mailto URI."),
    cloudflare_zone_id: str | None = typer.Option(None, "--cloudflare-zone-id", help="Cloudflare zone ID to use instead of provider lookup."),
    manage_domain_spf: bool = typer.Option(False, "--manage-domain-spf/--no-manage-domain-spf", help="Render an apex SPF record for SES."),
    manage_dmarc: bool = typer.Option(True, "--manage-dmarc/--no-manage-dmarc", help="Render a _dmarc TXT record."),
    workspace: Path | None = typer.Option(None, "--workspace", help="Render into a custom workspace path."),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files in an existing workspace."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report planned files without writing them."),
    json_output: bool = typer.Option(False, "--json", help="Print render result as JSON."),
) -> None:
    """Render a plan-only SES/Cloudflare DNS OpenTofu workspace."""
    if provider != "ses":
        raise typer.BadParameter("only --provider ses is supported")
    config = build_mail_workspace_config(
        domain,
        region=region,
        mail_from_subdomain=mail_from_subdomain,
        dmarc_policy=dmarc_policy,
        rua=rua,
        cloudflare_zone_id=cloudflare_zone_id,
        manage_domain_spf=manage_domain_spf,
        manage_dmarc=manage_dmarc,
    )
    result = render_mail_workspace(config, workspace_path=workspace, force=force, dry_run=dry_run)
    payload = {"action": "infra_render", "kind": "mail", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.ok:
        verb = "Would render" if result.dry_run else "Rendered"
        success(f"{verb} OpenTofu mail workspace: {result.workspace_path}")
        for file in result.files:
            typer.echo(f"- {file.path.name}")
        return
    warn(result.error or "workspace render failed")
    raise typer.Exit(code=1)


@plan_cli.command("mail")
def infra_plan_mail(
    domain: str = typer.Argument(..., help="Bare domain to plan SES/Cloudflare mail infrastructure for."),
    provider: str = typer.Option("ses", "--provider", help="Mail provider to plan. Only `ses` is supported."),
    region: str | None = typer.Option(None, "--region", help="AWS region for SES resources."),
    mail_from_subdomain: str = typer.Option("mail", "--mail-from-subdomain", help="Custom MAIL FROM subdomain."),
    dmarc_policy: str = typer.Option("none", "--dmarc-policy", help="DMARC policy: none, quarantine, or reject."),
    rua: str | None = typer.Option(None, "--rua", help="Optional DMARC aggregate report email or mailto URI."),
    cloudflare_zone_id: str | None = typer.Option(None, "--cloudflare-zone-id", help="Cloudflare zone ID to use instead of provider lookup."),
    manage_domain_spf: bool = typer.Option(False, "--manage-domain-spf/--no-manage-domain-spf", help="Plan an apex SPF record for SES."),
    manage_dmarc: bool = typer.Option(True, "--manage-dmarc/--no-manage-dmarc", help="Plan a _dmarc TXT record."),
    workspace: Path | None = typer.Option(None, "--workspace", help="Use a custom workspace path."),
    refresh_render: bool = typer.Option(False, "--refresh-render", help="Render workspace files before planning."),
    force_render: bool = typer.Option(False, "--force-render", help="Overwrite generated files when rendering."),
    json_output: bool = typer.Option(False, "--json", help="Print plan result as JSON."),
) -> None:
    """Render if needed, then run `tofu init` and `tofu plan -detailed-exitcode`."""
    if provider != "ses":
        raise typer.BadParameter("only --provider ses is supported")
    config = build_mail_workspace_config(
        domain,
        region=region,
        mail_from_subdomain=mail_from_subdomain,
        dmarc_policy=dmarc_policy,
        rua=rua,
        cloudflare_zone_id=cloudflare_zone_id,
        manage_domain_spf=manage_domain_spf,
        manage_dmarc=manage_dmarc,
    )
    result = plan_mail_workspace(
        config,
        workspace_path=workspace,
        refresh_render=refresh_render,
        force_render=force_render,
        which=shutil.which,
        runner=run_command,
    )
    payload = {"action": "infra_plan", **result.to_dict()}
    if json_output:
        typer.echo(json.dumps(with_json_schema(payload), indent=2))
        if not result.ok:
            raise typer.Exit(code=1)
        return
    if result.init_result and result.init_result.ok:
        success(f"OpenTofu initialized workspace: {result.workspace_path}")
    if result.ok:
        success(f"Plan completed: {'changes present' if result.has_changes else 'no changes'}")
        return
    warn(f"Plan failed: {result.error or 'OpenTofu plan failed'}")
    raise typer.Exit(code=1)
