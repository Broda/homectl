from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


PORT_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([0-9]+))?\}")
TRAEFIK_PORT_RE = re.compile(r"loadbalancer\.server\.port=([0-9]+)")
HEALTHCHECK_PORT_RE = re.compile(r"127\.0\.0\.1:(?:([0-9]+)|\$\{([A-Z0-9_]+)(?::-([0-9]+))?\})")
EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+([0-9]+)\s*$")


def _load_compose(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _resolve_port_value(raw: object, env: dict[str, str]) -> int | None:
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if stripped.isdigit():
        return int(stripped)
    match = PORT_REF_RE.fullmatch(stripped)
    if not match:
        return None
    env_name, default = match.groups()
    if env_name in env and env[env_name].isdigit():
        return int(env[env_name])
    if default and default.isdigit():
        return int(default)
    return None


def _service_environment(service: dict[str, Any]) -> list[tuple[str, object]]:
    raw = service.get("environment")
    if isinstance(raw, dict):
        return [(str(key), value) for key, value in raw.items()]
    if isinstance(raw, list):
        entries: list[tuple[str, object]] = []
        for item in raw:
            if isinstance(item, str) and "=" in item:
                key, value = item.split("=", 1)
                entries.append((key, value))
        return entries
    return []


def _service_labels(service: dict[str, Any]) -> list[str]:
    raw = service.get("labels")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, dict):
        return [f"{key}={value}" for key, value in raw.items()]
    return []


def _dockerfile_ports(stack_dir: Path, dockerfile_path: str | None) -> list[int]:
    if not dockerfile_path:
        return []
    path = stack_dir / dockerfile_path
    if not path.exists():
        return []
    ports: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = EXPOSE_RE.match(line)
        if match:
            ports.append(int(match.group(1)))
    return ports


def inspect_stack_ports(stack_dir: Path) -> list[dict[str, object]]:
    compose_path = stack_dir / "docker-compose.yml"
    if not compose_path.exists():
        return []

    compose = _load_compose(compose_path)
    services = compose.get("services")
    if not isinstance(services, dict):
        return []

    env = _load_dotenv(stack_dir / ".env")
    discovered: list[dict[str, object]] = []

    for service_name, raw_service in services.items():
        if not isinstance(raw_service, dict):
            continue

        ports_by_value: dict[int, set[str]] = {}

        for key, value in _service_environment(raw_service):
            port = _resolve_port_value(value, env)
            if port is not None and (key.endswith("_PORT") or key == "PORT"):
                ports_by_value.setdefault(port, set()).add(f"environment {key}")

        for label in _service_labels(raw_service):
            match = TRAEFIK_PORT_RE.search(label)
            if match:
                ports_by_value.setdefault(int(match.group(1)), set()).add("traefik loadbalancer")

        healthcheck = raw_service.get("healthcheck")
        if isinstance(healthcheck, dict):
            test = healthcheck.get("test")
            if isinstance(test, list):
                joined = " ".join(str(item) for item in test)
            else:
                joined = str(test)
            for port_match in HEALTHCHECK_PORT_RE.finditer(joined):
                direct_port, env_name, default_port = port_match.groups()
                if direct_port and direct_port.isdigit():
                    ports_by_value.setdefault(int(direct_port), set()).add("healthcheck")
                    continue
                if env_name and env_name in env and env[env_name].isdigit():
                    ports_by_value.setdefault(int(env[env_name]), set()).add("healthcheck")
                    continue
                if default_port and default_port.isdigit():
                    ports_by_value.setdefault(int(default_port), set()).add("healthcheck")

        build = raw_service.get("build")
        dockerfile = None
        if isinstance(build, dict):
            raw_dockerfile = build.get("dockerfile")
            dockerfile = str(raw_dockerfile) if raw_dockerfile else None
        for port in _dockerfile_ports(stack_dir, dockerfile):
            ports_by_value.setdefault(port, set()).add("Dockerfile EXPOSE")

        if "image" in raw_service and str(raw_service.get("image", "")).startswith("postgres:"):
            ports_by_value.setdefault(5432, set()).add("postgres image default")
            command = raw_service.get("command")
            if isinstance(command, list):
                try:
                    index = command.index("-p")
                except ValueError:
                    index = -1
                if index >= 0 and index + 1 < len(command):
                    value = str(command[index + 1])
                    if value.isdigit():
                        ports_by_value.pop(5432, None)
                        ports_by_value.setdefault(int(value), set()).add("postgres command port")

        if ports_by_value:
            discovered.append(
                {
                    "service": str(service_name),
                    "ports": [
                        {
                            "port": port,
                            "sources": sorted(sources),
                        }
                        for port, sources in sorted(ports_by_value.items())
                    ],
                }
            )

    return discovered
