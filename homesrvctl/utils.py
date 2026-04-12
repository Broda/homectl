from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import typer


HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-zA-Z0-9-]{1,63}\.)+[A-Za-z]{2,63}$"
)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-zA-Z0-9-]{1,63}\.)+[A-Za-z]{2,63}$"
)

COMMON_SECOND_LEVEL_SUFFIXES = {"co", "com", "net", "org", "gov", "ac"}
JSON_SCHEMA_VERSION = "1"


def info(message: str) -> None:
    typer.secho(message, fg=typer.colors.CYAN)


def success(message: str) -> None:
    typer.secho(message, fg=typer.colors.GREEN)


def warn(message: str) -> None:
    typer.secho(message, fg=typer.colors.YELLOW)


def error(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)


def bullet_report(symbol: str, label: str, detail: str, ok: bool) -> None:
    color = typer.colors.GREEN if ok else typer.colors.RED
    typer.secho(f"{symbol} {label}: {detail}", fg=color)


def hostname_to_safe_name(hostname: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", hostname.strip().lower())
    safe = safe.strip("-")
    return safe or "host"


def validate_hostname(hostname: str) -> str:
    candidate = hostname.strip().lower()
    if "/" in candidate or "://" in candidate or "*" in candidate:
        raise typer.BadParameter("hostname must be a plain hostname without scheme, path, or wildcard")
    if not HOSTNAME_RE.match(candidate):
        raise typer.BadParameter(f"invalid hostname: {hostname}")
    return candidate


def validate_bare_domain(domain: str) -> str:
    candidate = validate_hostname(domain)
    labels = candidate.split(".")
    if len(labels) == 2:
        return candidate
    if len(labels) == 3 and labels[-2] in COMMON_SECOND_LEVEL_SUFFIXES and len(labels[-1]) == 2:
        return candidate
    raise typer.BadParameter(
        "domain must look like a bare registrable domain, not a subdomain; examples: example.com, example.co.uk"
    )


def traefik_host_rule(hostname: str) -> str:
    valid_hostname = validate_hostname(hostname)
    try:
        apex = validate_bare_domain(valid_hostname)
    except typer.BadParameter:
        return f"Host(`{valid_hostname}`)"
    return f"Host(`{apex}`) || Host(`www.{apex}`)"


def ensure_directory(path: Path, dry_run: bool = False, quiet: bool = False) -> None:
    if dry_run:
        if not quiet:
            info(f"[dry-run] mkdir -p {path}")
        return
    path.mkdir(parents=True, exist_ok=True)


def write_text_file(path: Path, content: str, force: bool, dry_run: bool = False, quiet: bool = False) -> None:
    if path.exists() and not force:
        raise typer.BadParameter(f"refusing to overwrite existing file without --force: {path}")
    if dry_run:
        if not quiet:
            info(f"[dry-run] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def print_commands(commands: Iterable[list[str]]) -> None:
    for command in commands:
        info(f"$ {' '.join(command)}")


def with_json_schema(payload: dict[str, object]) -> dict[str, object]:
    return {"schema_version": JSON_SCHEMA_VERSION, **payload}
