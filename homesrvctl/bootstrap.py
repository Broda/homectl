from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import typer

from homesrvctl import __version__
from homesrvctl.cloudflared_service import detect_cloudflared_runtime
from homesrvctl.config import default_config_path, load_config_details
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.shell import command_exists, run_command


@dataclass(slots=True)
class BootstrapAssessment:
    ok: bool
    bootstrap_state: str
    bootstrap_ready: bool
    host_supported: bool
    detail: str
    config_path: str
    os: dict[str, object]
    systemd: dict[str, object]
    packages: dict[str, object]
    services: dict[str, object]
    config: dict[str, object]
    network: dict[str, object]
    cloudflare: dict[str, object]
    issues: list[str]
    next_steps: list[str]


def assess_bootstrap(config_path: Path | None = None, *, quiet: bool = False) -> BootstrapAssessment:
    target_path = config_path or default_config_path()
    os_info = _os_assessment()
    systemd_info = _systemd_assessment()
    host_supported = bool(os_info["supported"]) and bool(systemd_info["present"])

    config_info, config = _config_assessment(target_path)
    packages_info = _packages_assessment(quiet=quiet)
    services_info = _services_assessment(packages_info=packages_info, quiet=quiet)
    network_info = _network_assessment(config.docker_network, packages_info=packages_info, quiet=quiet)
    cloudflare_info = _cloudflare_assessment(
        api_token=config.cloudflare_api_token,
        token_source=str(config_info["token_source"]),
    )

    issues: list[str] = []
    if not host_supported:
        issues.append("host is not in the first supported bootstrap target: Debian-family Linux with systemd")
    if not packages_info["docker"]:
        issues.append("docker binary is missing")
    if not packages_info["docker_compose"]:
        issues.append("docker compose is unavailable")
    if not packages_info["cloudflared"]:
        issues.append("cloudflared binary is missing")
    if not bool(services_info["traefik_running"]):
        issues.append("Traefik is not running")
    if not bool(services_info["cloudflared_active"]):
        issues.append("cloudflared is not active")
    if network_info["exists"] is False:
        issues.append(f"docker network `{config.docker_network}` is missing")
    if not bool(config_info["exists"]):
        issues.append(f"homesrvctl config is missing: {target_path}")
    elif not bool(config_info["valid"]):
        issues.append(str(config_info["detail"]))
    if not bool(cloudflare_info["token_present"]):
        issues.append("Cloudflare API token is missing")
    elif cloudflare_info["api_reachable"] is False:
        issues.append(str(cloudflare_info["detail"]))

    bootstrap_ready = host_supported and not issues
    if not host_supported:
        bootstrap_state = "unsupported"
    elif (
        not bool(config_info["exists"])
        and not packages_info["docker"]
        and not packages_info["docker_compose"]
        and not packages_info["cloudflared"]
        and not bool(services_info["traefik_running"])
        and not bool(services_info["cloudflared_active"])
    ):
        bootstrap_state = "fresh"
    elif bootstrap_ready:
        bootstrap_state = "ready"
    else:
        bootstrap_state = "partial"

    next_steps = _next_steps(
        bootstrap_state=bootstrap_state,
        host_supported=host_supported,
        config_info=config_info,
        packages_info=packages_info,
        services_info=services_info,
        network_info=network_info,
        cloudflare_info=cloudflare_info,
        docker_network=config.docker_network,
    )

    if bootstrap_state == "ready":
        detail = "host matches the current bootstrap target and appears ready for the next bootstrap slice"
    elif bootstrap_state == "fresh":
        detail = "host looks mostly fresh relative to the current bootstrap target"
    elif bootstrap_state == "unsupported":
        detail = "host is outside the current bootstrap target"
    else:
        detail = "host is partially provisioned relative to the current bootstrap target"

    return BootstrapAssessment(
        ok=host_supported,
        bootstrap_state=bootstrap_state,
        bootstrap_ready=bootstrap_ready,
        host_supported=host_supported,
        detail=detail,
        config_path=str(target_path),
        os=os_info,
        systemd=systemd_info,
        packages=packages_info,
        services=services_info,
        config=config_info,
        network=network_info,
        cloudflare=cloudflare_info,
        issues=issues,
        next_steps=next_steps,
    )


def _os_assessment() -> dict[str, object]:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return {
            "id": "unknown",
            "version_id": "",
            "pretty_name": "unknown",
            "supported": False,
            "detail": "missing /etc/os-release",
        }

    parsed: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip().strip('"')

    os_id = parsed.get("ID", "unknown").strip().lower()
    id_like = {item.strip().lower() for item in parsed.get("ID_LIKE", "").split() if item.strip()}
    supported = os_id in {"debian", "raspbian"} or "debian" in id_like
    detail = "Debian-family host detected" if supported else f"unsupported OS family: {os_id or 'unknown'}"
    return {
        "id": os_id or "unknown",
        "version_id": parsed.get("VERSION_ID", "").strip(),
        "pretty_name": parsed.get("PRETTY_NAME", "unknown").strip(),
        "supported": supported,
        "detail": detail,
    }


def _systemd_assessment() -> dict[str, object]:
    present = command_exists("systemctl") and Path("/run/systemd/system").exists()
    return {
        "present": present,
        "detail": "systemd detected" if present else "systemd not detected",
    }


def _config_assessment(config_path: Path) -> tuple[dict[str, object], HomesrvctlConfig]:
    env_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    fallback_config = HomesrvctlConfig(cloudflare_api_token=env_api_token)
    if not config_path.exists():
        return (
            {
                "path": str(config_path),
                "exists": False,
                "valid": False,
                "detail": f"config file not found: {config_path}",
                "docker_network": fallback_config.docker_network,
                "cloudflared_config": str(fallback_config.cloudflared_config),
                "token_present": bool(env_api_token),
                "token_source": "environment" if env_api_token else "missing",
            },
            fallback_config,
        )

    try:
        config, sources = load_config_details(config_path)
    except typer.BadParameter as exc:
        return (
            {
                "path": str(config_path),
                "exists": True,
                "valid": False,
                "detail": str(exc),
                "docker_network": fallback_config.docker_network,
                "cloudflared_config": str(fallback_config.cloudflared_config),
                "token_present": bool(env_api_token),
                "token_source": "environment" if env_api_token else "missing",
            },
            fallback_config,
        )

    return (
        {
            "path": str(config_path),
            "exists": True,
            "valid": True,
            "detail": "config file loaded successfully",
            "docker_network": config.docker_network,
            "cloudflared_config": str(config.cloudflared_config),
            "token_present": bool(config.cloudflare_api_token),
            "token_source": sources["cloudflare_api_token"],
        },
        config,
    )


def _packages_assessment(*, quiet: bool) -> dict[str, object]:
    docker_binary = command_exists("docker")
    cloudflared_binary = command_exists("cloudflared")
    compose_available = False
    compose_detail = "docker binary missing"
    if docker_binary:
        compose_result = run_command(["docker", "compose", "version"], quiet=quiet)
        compose_available = compose_result.ok
        compose_detail = compose_result.stdout or compose_result.stderr or "docker compose unavailable"
    return {
        "docker": docker_binary,
        "docker_detail": "found in PATH" if docker_binary else "missing from PATH",
        "docker_compose": compose_available,
        "docker_compose_detail": compose_detail,
        "cloudflared": cloudflared_binary,
        "cloudflared_detail": "found in PATH" if cloudflared_binary else "missing from PATH",
    }


def _services_assessment(*, packages_info: dict[str, object], quiet: bool) -> dict[str, object]:
    traefik_running = False
    traefik_detail = "docker binary missing"
    if packages_info["docker"]:
        traefik_result = run_command(
            ["docker", "ps", "--filter", "name=traefik", "--filter", "status=running", "--format", "{{.Names}}"],
            quiet=quiet,
        )
        traefik_running = bool(traefik_result.stdout.strip())
        traefik_detail = (
            traefik_result.stdout
            or traefik_result.stderr
            or "no running container matched filter name=traefik"
        )

    runtime = detect_cloudflared_runtime(quiet=quiet)
    return {
        "traefik_running": traefik_running,
        "traefik_detail": traefik_detail,
        "cloudflared_active": runtime.active,
        "cloudflared_mode": runtime.mode,
        "cloudflared_detail": runtime.detail,
    }


def _network_assessment(docker_network: str, *, packages_info: dict[str, object], quiet: bool) -> dict[str, object]:
    if not packages_info["docker"]:
        return {
            "name": docker_network,
            "exists": None,
            "detail": "docker binary missing",
        }
    result = run_command(
        ["docker", "network", "inspect", docker_network, "--format", "{{json .Name}}"],
        quiet=quiet,
    )
    return {
        "name": docker_network,
        "exists": result.ok,
        "detail": result.stdout or result.stderr or "docker network not found",
    }


def _cloudflare_assessment(*, api_token: str, token_source: str) -> dict[str, object]:
    token = api_token.strip()
    if not token:
        return {
            "token_present": False,
            "token_source": token_source,
            "api_reachable": None,
            "detail": "Cloudflare API token is not configured",
        }

    try:
        request = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": f"homesrvctl/{__version__}",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "token_present": True,
            "token_source": token_source,
            "api_reachable": False,
            "detail": f"Cloudflare token verification failed: HTTP {exc.code}: {detail}",
        }
    except urllib.error.URLError as exc:
        return {
            "token_present": True,
            "token_source": token_source,
            "api_reachable": False,
            "detail": f"Cloudflare API verification failed: {exc}",
        }

    if payload.get("success", False):
        status = payload.get("result", {})
        token_status = status.get("status", "unknown") if isinstance(status, dict) else "unknown"
        return {
            "token_present": True,
            "token_source": token_source,
            "api_reachable": True,
            "detail": f"Cloudflare token verified ({token_status})",
        }
    return {
        "token_present": True,
        "token_source": token_source,
        "api_reachable": False,
        "detail": f"Cloudflare token verification failed: {payload.get('errors', [])}",
    }


def _next_steps(
    *,
    bootstrap_state: str,
    host_supported: bool,
    config_info: dict[str, object],
    packages_info: dict[str, object],
    services_info: dict[str, object],
    network_info: dict[str, object],
    cloudflare_info: dict[str, object],
    docker_network: str,
) -> list[str]:
    if bootstrap_state == "ready":
        return ["Host baseline is ready for the next bootstrap slice."]

    steps: list[str] = []
    if not host_supported:
        steps.append("Use a Debian-family Raspberry Pi OS host with systemd for the first bootstrap target.")
    if not packages_info["docker"] or not packages_info["docker_compose"]:
        steps.append("Install Docker Engine plus the Docker Compose plugin.")
    if not packages_info["cloudflared"]:
        steps.append("Install cloudflared on the host.")
    if config_info["exists"] is False:
        steps.append("Run `homesrvctl config init` to create the starter config.")
    if not services_info["traefik_running"]:
        steps.append("Install or start the baseline Traefik runtime expected by homesrvctl.")
    if not services_info["cloudflared_active"]:
        steps.append("Install or start the cloudflared service for the shared host tunnel.")
    if network_info["exists"] is False:
        steps.append(f"Create the shared Docker network `{docker_network}`.")
    if not cloudflare_info["token_present"]:
        steps.append("Configure `cloudflare_api_token` or `CLOUDFLARE_API_TOKEN` for Cloudflare API access.")
    elif cloudflare_info["api_reachable"] is False:
        steps.append("Fix Cloudflare API token reachability before attempting future bootstrap flows.")
    steps.append("`homesrvctl bootstrap apply` is not shipped yet; use this assessment to prepare the host manually.")
    return steps
