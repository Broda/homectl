from __future__ import annotations

import json
import urllib.error
import urllib.request

import typer
import yaml

from homectl.cloudflared import (
    CloudflaredConfigError,
    describe_cloudflared_config_error,
    find_hostname_route,
    validate_ingress_config,
)
from homectl.cloudflared_service import detect_cloudflared_runtime
from homectl.config import load_config
from homectl.models import CheckResult, HomectlConfig
from homectl.shell import command_exists, run_command
from homectl.utils import bullet_report, validate_hostname


def validate() -> None:
    """Validate the local hosting environment."""
    validate_with_format()


def validate_with_format(
    json_output: bool = typer.Option(False, "--json", help="Print the validation report as JSON."),
) -> None:
    """Validate the local hosting environment."""
    config = load_config()
    checks = build_validate_report(config)
    if json_output:
        payload = {
            "ok": all(check.ok for check in checks),
            "checks": [_check_to_dict(check) for check in checks],
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_report(checks)
    if any(not check.ok for check in checks):
        raise typer.Exit(code=1)


def build_validate_report(config: HomectlConfig) -> list[CheckResult]:
    checks: list[CheckResult] = []
    checks.append(CheckResult("cloudflared binary", command_exists("cloudflared"), _binary_detail("cloudflared")))
    checks.append(CheckResult("docker binary", command_exists("docker"), _binary_detail("docker")))

    compose_result = run_command(["docker", "compose", "version"])
    checks.append(_result_to_check("docker compose", compose_result, success_detail=compose_result.stdout or "available"))

    checks.append(_check_tunnel_reference(config))

    network_result = run_command(
        ["docker", "network", "inspect", config.docker_network, "--format", "{{json .Name}}"]
    )
    checks.append(
        _result_to_check(
            "docker network",
            network_result,
            success_detail=f"found network {config.docker_network}",
        )
    )

    traefik_result = run_command(
        ["docker", "ps", "--filter", "name=traefik", "--filter", "status=running", "--format", "{{.Names}}"]
    )
    checks.append(
        CheckResult(
            "Traefik container",
            bool(traefik_result.stdout.strip()),
            traefik_result.stdout or "no running container matched filter name=traefik",
        )
    )

    cloudflared_service = _check_cloudflared_service()
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


def build_hostname_doctor_report(config: HomectlConfig, hostname: str) -> list[CheckResult]:
    valid_hostname = validate_hostname(hostname)
    stack_dir = config.hostname_dir(valid_hostname)
    compose_file = stack_dir / "docker-compose.yml"

    checks = [
        CheckResult("hostname directory", stack_dir.exists(), str(stack_dir)),
        CheckResult("docker-compose.yml", compose_file.exists(), str(compose_file)),
    ]

    if compose_file.exists():
        ps_result = run_command(["docker", "compose", "ps", "--format", "json"], cwd=stack_dir)
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
    checks.append(_check_host_header(config, valid_hostname))
    return checks


def _binary_detail(binary: str) -> str:
    return "found in PATH" if command_exists(binary) else "missing from PATH"


def _result_to_check(name: str, result, success_detail: str) -> CheckResult:
    detail = success_detail if result.ok else (result.stderr or result.stdout or "command failed")
    return CheckResult(name, result.ok, detail)


def _check_cloudflared_service() -> CheckResult:
    runtime = detect_cloudflared_runtime()
    return CheckResult("cloudflared service", runtime.active, runtime.detail)


def _check_traefik_http(config: HomectlConfig) -> CheckResult:
    request = urllib.request.Request(config.traefik_url, headers={"User-Agent": "homectl/0.1.0"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return CheckResult("Traefik URL", True, f"{config.traefik_url} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        return CheckResult("Traefik URL", True, f"{config.traefik_url} returned HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return CheckResult("Traefik URL", False, f"{config.traefik_url} unreachable: {exc}")


def _check_cloudflared_ingress_config(config: HomectlConfig) -> CheckResult:
    if not config.cloudflared_config.exists():
        return CheckResult("cloudflared ingress config", False, f"missing file: {config.cloudflared_config}")
    try:
        fallback = validate_ingress_config(config.cloudflared_config)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        return CheckResult("cloudflared ingress config", False, describe_cloudflared_config_error(exc))
    return CheckResult("cloudflared ingress config", True, f"fallback service {fallback}")


def _check_host_header(config: HomectlConfig, hostname: str) -> CheckResult:
    request = urllib.request.Request(
        config.traefik_url,
        headers={"Host": hostname, "User-Agent": "homectl/0.1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return CheckResult("host-header request", True, f"{hostname} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        return CheckResult("host-header request", True, f"{hostname} returned HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return CheckResult("host-header request", False, f"request failed: {exc}")


def _check_cloudflared_hostname(config: HomectlConfig, hostname: str) -> CheckResult:
    if not config.cloudflared_config.exists():
        return CheckResult("cloudflared ingress hostname", False, f"missing file: {config.cloudflared_config}")
    try:
        service = find_hostname_route(config.cloudflared_config, hostname)
    except (CloudflaredConfigError, typer.BadParameter) as exc:
        return CheckResult("cloudflared ingress hostname", False, describe_cloudflared_config_error(exc))
    if not service:
        return CheckResult("cloudflared ingress hostname", False, f"no ingress entry for {hostname}")
    return CheckResult("cloudflared ingress hostname", True, f"{hostname} routes to {service}")


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


def _check_tunnel_reference(config: HomectlConfig) -> CheckResult:
    tunnel_result = run_command(
        [
            "cloudflared",
            "--config",
            str(config.cloudflared_config),
            "tunnel",
            "info",
            config.tunnel_name,
        ]
    )
    if tunnel_result.ok:
        return CheckResult(
            "configured tunnel",
            True,
            tunnel_result.stdout or f"tunnel reachable via cloudflared: {config.tunnel_name}",
        )

    if not config.cloudflared_config.exists():
        return CheckResult(
            "configured tunnel",
            False,
            tunnel_result.stderr or f"cloudflared config file missing: {config.cloudflared_config}",
        )

    try:
        parsed = yaml.safe_load(config.cloudflared_config.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return CheckResult("configured tunnel", False, f"invalid cloudflared config YAML: {exc}")

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
            f"cloudflared config references tunnel {tunnel_value}; configured homectl tunnel_name is {config.tunnel_name}",
        )

    raw_text = config.cloudflared_config.read_text(encoding="utf-8")
    if config.tunnel_name in raw_text:
        return CheckResult(
            "configured tunnel",
            True,
            f"tunnel name {config.tunnel_name} found in {config.cloudflared_config}",
        )

    return CheckResult(
        "configured tunnel",
        False,
        tunnel_result.stderr or f"tunnel {config.tunnel_name} not found in cloudflared config",
    )


def _print_report(checks: list[CheckResult]) -> None:
    for check in checks:
        bullet_report("PASS" if check.ok else "FAIL", check.name, check.detail, check.ok)


def _check_to_dict(check: CheckResult) -> dict[str, object]:
    return {"name": check.name, "ok": check.ok, "detail": check.detail}
