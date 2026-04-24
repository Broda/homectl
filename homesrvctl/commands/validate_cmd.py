from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import typer
import yaml

from homesrvctl import __version__
from homesrvctl.cloudflare import (
    CloudflareApiClient,
    CloudflareApiError,
    account_id_from_cloudflared_config,
)
from homesrvctl.cloudflared import (
    CloudflaredConfigError,
    find_hostname_route,
    describe_cloudflared_config_error,
    inspect_cloudflared_config_issues,
    test_cloudflared_config,
)
from homesrvctl.cloudflared_service import detect_cloudflared_runtime
from homesrvctl.config import load_config, load_stack_settings, stack_routing_context
from homesrvctl.models import CheckResult, HomesrvctlConfig
from homesrvctl.shell import command_exists, run_command
from homesrvctl.utils import bullet_report, validate_hostname, with_json_schema


def validate() -> None:
    """Validate the local hosting environment."""
    validate_with_format()


def validate_with_format(
    json_output: bool = typer.Option(False, "--json", help="Print the validation report as JSON."),
) -> None:
    """Validate the local hosting environment."""
    config = load_config()
    checks = build_validate_report(config, quiet=json_output)
    if json_output:
        payload = with_json_schema({
            "ok": not any(_check_is_blocking_failure(check) for check in checks),
            "checks": [_check_to_dict(check) for check in checks],
        })
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_report(checks)
    if any(_check_is_blocking_failure(check) for check in checks):
        raise typer.Exit(code=1)


def build_validate_report(config: HomesrvctlConfig, quiet: bool = False) -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.append(CheckResult("cloudflared binary", command_exists("cloudflared"), _binary_detail("cloudflared")))
    checks.append(CheckResult("docker binary", command_exists("docker"), _binary_detail("docker")))

    compose_result = run_command(["docker", "compose", "version"], quiet=quiet)
    checks.append(_result_to_check("docker compose", compose_result, success_detail=compose_result.stdout or "available"))

    checks.append(_check_tunnel_reference(config))

    network_result = run_command(
        ["docker", "network", "inspect", config.docker_network, "--format", "{{json .Name}}"],
        quiet=quiet,
    )
    checks.append(
        _result_to_check(
            "docker network",
            network_result,
            success_detail=f"found network {config.docker_network}",
        )
    )

    traefik_result = run_command(
        ["docker", "ps", "--filter", "name=traefik", "--filter", "status=running", "--format", "{{.Names}}"],
        quiet=quiet,
    )
    checks.append(
        CheckResult(
            "Traefik container",
            bool(traefik_result.stdout.strip()),
            traefik_result.stdout or "no running container matched filter name=traefik",
        )
    )

    cloudflared_service = _check_cloudflared_service(quiet=quiet)
    checks.append(cloudflared_service)

    checks.append(_check_traefik_http(config))
    checks.append(
        CheckResult(
            "cloudflared config path",
            config.cloudflared_config.exists(),
            str(config.cloudflared_config),
        )
    )
    checks.append(_check_cloudflared_ingress_config(config))
    return checks


def build_hostname_doctor_report(
    config: HomesrvctlConfig,
    hostname: str,
    global_sources: dict[str, str] | None = None,
    quiet: bool = False,
) -> list[CheckResult]:
    valid_hostname = validate_hostname(hostname)
    stack_dir = config.hostname_dir(valid_hostname)
    compose_file = stack_dir / "docker-compose.yml"
    stack_settings = load_stack_settings(config, valid_hostname)
    routing = stack_routing_context(config, valid_hostname, global_sources)

    checks = [
        CheckResult("hostname directory", stack_dir.exists(), str(stack_dir)),
        CheckResult("docker-compose.yml", compose_file.exists(), str(compose_file)),
        CheckResult("routing profile", True, str(routing["profile"] or "none")),
        CheckResult("default ingress target", True, str(routing["default"]["traefik_url"])),
        CheckResult(
            "effective ingress target",
            True,
            f"{routing['effective']['traefik_url']} ({routing['effective_sources']['traefik_url']})",
        ),
    ]

    if compose_file.exists():
        ps_result = run_command(["docker", "compose", "ps", "--format", "json"], cwd=stack_dir, quiet=quiet)
        checks.append(
            CheckResult(
                "docker compose ps",
                ps_result.ok,
                _compose_ps_detail(ps_result),
            )
        )
    else:
        checks.append(CheckResult("docker compose ps", False, "skipped because docker-compose.yml is missing"))

    checks.append(_check_cloudflared_hostname(config, valid_hostname))
    checks.extend(_check_cloudflared_ingress_warnings(config))
    checks.append(_check_ingress_target_entrypoint(stack_settings.traefik_url))
    checks.append(_check_host_header(stack_settings.traefik_url, valid_hostname))
    return checks


def _binary_detail(binary: str) -> str:
    return "found in PATH" if command_exists(binary) else "missing from PATH"


def _result_to_check(name: str, result, success_detail: str) -> CheckResult:
    detail = success_detail if result.ok else (result.stderr or result.stdout or "command failed")
    return CheckResult(name, result.ok, detail)


def _check_cloudflared_service(quiet: bool = False) -> CheckResult:
    runtime = detect_cloudflared_runtime(quiet=quiet)
    return CheckResult("cloudflared service", runtime.active, runtime.detail)


def _check_traefik_http(config: HomesrvctlConfig) -> CheckResult:
    request = urllib.request.Request(config.traefik_url, headers={"User-Agent": f"homesrvctl/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return CheckResult("Traefik URL", True, f"{config.traefik_url} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        return CheckResult("Traefik URL", True, f"{config.traefik_url} returned HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return CheckResult("Traefik URL", False, f"{config.traefik_url} unreachable: {exc}")


def _check_cloudflared_ingress_config(config: HomesrvctlConfig) -> CheckResult:
    result = test_cloudflared_config(config.cloudflared_config)
    if result.command:
        detail = f"{' '.join(result.command)}: {result.detail}"
    else:
        detail = result.detail
    return CheckResult("cloudflared ingress config", result.ok, detail)


def _check_host_header(traefik_url: str, hostname: str) -> CheckResult:
    request = urllib.request.Request(
        traefik_url,
        headers={"Host": hostname, "User-Agent": f"homesrvctl/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return CheckResult("host-header request", True, f"{hostname} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        return CheckResult("host-header request", True, f"{hostname} returned HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return CheckResult("host-header request", False, f"request failed: {exc}")


def _check_ingress_target_entrypoint(traefik_url: str) -> CheckResult:
    parsed = urllib.parse.urlparse(traefik_url)
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.port == 8081:
        return CheckResult(
            "ingress target entrypoint",
            False,
            f"{traefik_url} looks like the bootstrap Traefik dashboard/API port; use http://localhost:80 for tunnel ingress",
            "advisory",
        )
    return CheckResult("ingress target entrypoint", True, f"{traefik_url} looks like an application entrypoint")


def _check_cloudflared_hostname(config: HomesrvctlConfig, hostname: str) -> CheckResult:
    if not config.cloudflared_config.exists():
        return CheckResult("cloudflared ingress hostname", False, f"missing file: {config.cloudflared_config}")
    try:
        service = find_hostname_route(config.cloudflared_config, hostname)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        return CheckResult("cloudflared ingress hostname", False, describe_cloudflared_config_error(exc))
    if not service:
        return CheckResult("cloudflared ingress hostname", False, f"no ingress entry for {hostname}")
    return CheckResult("cloudflared ingress hostname", True, f"{hostname} routes to {service}")


def _check_cloudflared_ingress_warnings(config: HomesrvctlConfig) -> list[CheckResult]:
    try:
        issues = inspect_cloudflared_config_issues(config.cloudflared_config)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        return [CheckResult("cloudflared ingress issues", False, describe_cloudflared_config_error(exc))]
    if not issues:
        return [CheckResult("cloudflared ingress issues", True, "no ingress issues detected")]
    checks: list[CheckResult] = []
    for issue in issues:
        checks.append(
            CheckResult(
                "cloudflared ingress issue",
                not issue.blocking,
                issue.render(),
                severity="blocking" if issue.blocking else "advisory",
            )
        )
    return checks


def _compose_ps_detail(result) -> str:
    if not result.ok:
        return result.stderr or result.stdout or "docker compose ps failed"
    raw = result.stdout.strip()
    if not raw:
        return "no containers in stack"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, list):
        return f"{len(parsed)} container(s) reported"
    return "compose returned container state"


def _check_tunnel_reference(config: HomesrvctlConfig) -> CheckResult:
    if not config.cloudflared_config.exists():
        return CheckResult(
            "configured tunnel",
            False,
            f"cloudflared config file missing: {config.cloudflared_config}",
        )

    try:
        parsed = yaml.safe_load(config.cloudflared_config.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        return CheckResult("configured tunnel", False, f"unable to read cloudflared config: {exc}")
    except yaml.YAMLError as exc:
        return CheckResult("configured tunnel", False, f"invalid cloudflared config YAML: {exc}")

    try:
        account_id = account_id_from_cloudflared_config(config.cloudflared_config)
        tunnel = CloudflareApiClient(config.cloudflare_api_token).get_tunnel(account_id, config.tunnel_name)
        return CheckResult(
            "configured tunnel",
            True,
            f"Cloudflare tunnel {tunnel.name or config.tunnel_name} resolved to {tunnel.id} via API",
        )
    except (CloudflareApiError, typer.BadParameter):
        pass

    tunnel_value = str(parsed.get("tunnel", "")).strip()
    if tunnel_value == config.tunnel_name:
        return CheckResult(
            "configured tunnel",
            True,
            f"tunnel name {config.tunnel_name} referenced in {config.cloudflared_config}",
        )
    if tunnel_value:
        return CheckResult(
            "configured tunnel",
            True,
            f"cloudflared config references tunnel {tunnel_value}; configured homesrvctl tunnel_name is {config.tunnel_name}",
        )

    raw_text = config.cloudflared_config.read_text(encoding="utf-8")
    if config.tunnel_name in raw_text:
        return CheckResult(
            "configured tunnel",
            True,
            f"tunnel name {config.tunnel_name} found in {config.cloudflared_config}",
        )

    tunnel_result = run_command(
        [
            "cloudflared",
            "--config",
            str(config.cloudflared_config),
            "tunnel",
            "info",
            config.tunnel_name,
        ],
        quiet=True,
    )
    if tunnel_result.ok:
        return CheckResult(
            "configured tunnel",
            True,
            tunnel_result.stdout or f"tunnel reachable via cloudflared: {config.tunnel_name}",
        )

    return CheckResult(
        "configured tunnel",
        False,
        tunnel_result.stderr or f"tunnel {config.tunnel_name} not found in cloudflared config",
    )


def _print_report(checks: list[CheckResult]) -> None:
    for check in checks:
        severity = _check_severity(check)
        if severity == "advisory":
            bullet_report("WARN", check.name, check.detail, False)
            continue
        bullet_report("PASS" if check.ok else "FAIL", check.name, check.detail, check.ok)


def _check_to_dict(check: CheckResult) -> dict[str, object]:
    return {"name": check.name, "ok": check.ok, "detail": check.detail, "severity": _check_severity(check)}


def _check_severity(check: CheckResult) -> str:
    if check.severity:
        return check.severity
    return "pass" if check.ok else "blocking"


def _check_is_blocking_failure(check: CheckResult) -> bool:
    return not check.ok and _check_severity(check) != "advisory"
