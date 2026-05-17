from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import typer

from homesrvctl.config import load_stack_config_data, load_stack_settings, stack_config_path
from homesrvctl.models import HomesrvctlConfig
from homesrvctl.state.models import StackSnapshot
from homesrvctl.state.store import StateStore
from homesrvctl.utils import validate_hostname


@dataclass(slots=True)
class StackListItem:
    hostname: str
    compose: bool
    stack_dir: Path | None = None
    compose_file: Path | None = None
    has_stack_config: bool | None = None
    scaffold_kind: str | None = None
    scaffold_template: str | None = None
    profile: str | None = None
    docker_network: str | None = None
    traefik_url: str | None = None
    updated_at: str | None = None

    def to_dict(self, *, include_metadata: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "hostname": self.hostname,
            "compose": self.compose,
        }
        if not include_metadata:
            return payload
        payload.update(
            {
                "stack_dir": str(self.stack_dir) if self.stack_dir else None,
                "compose_file": str(self.compose_file) if self.compose_file else None,
                "has_stack_config": self.has_stack_config,
                "scaffold_kind": self.scaffold_kind,
                "scaffold_template": self.scaffold_template,
                "profile": self.profile,
                "docker_network": self.docker_network,
                "traefik_url": self.traefik_url,
                "updated_at": self.updated_at,
            }
        )
        return payload


@dataclass(slots=True)
class StackListResult:
    ok: bool
    source: str
    sites_root: Path | None
    sites: list[StackListItem]
    cache_available: bool
    last_refresh_at: str | None
    generated_at: str
    db_path: Path | None = None
    error: str | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self, *, include_site_metadata: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "source": self.source,
            "sites_root": str(self.sites_root) if self.sites_root else None,
            "sites": [site.to_dict(include_metadata=include_site_metadata) for site in self.sites],
            "cache_available": self.cache_available,
            "last_refresh_at": self.last_refresh_at,
            "generated_at": self.generated_at,
            "db_path": str(self.db_path) if self.db_path else None,
            "issues": self.issues,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iter_stack_dirs(config: HomesrvctlConfig) -> list[Path]:
    if not config.sites_root.exists():
        return []
    return sorted(path for path in config.sites_root.iterdir() if path.is_dir())


def list_stacks_live(config: HomesrvctlConfig) -> StackListResult:
    if not config.sites_root.exists():
        return StackListResult(
            ok=False,
            source="live",
            sites_root=config.sites_root,
            sites=[],
            cache_available=False,
            last_refresh_at=None,
            generated_at=_generated_at(),
            error=f"Sites root does not exist: {config.sites_root}",
        )
    sites = [
        StackListItem(
            hostname=child.name,
            compose=(child / "docker-compose.yml").exists(),
            stack_dir=child,
            compose_file=(child / "docker-compose.yml") if (child / "docker-compose.yml").exists() else None,
        )
        for child in iter_stack_dirs(config)
    ]
    return StackListResult(
        ok=True,
        source="live",
        sites_root=config.sites_root,
        sites=sites,
        cache_available=False,
        last_refresh_at=None,
        generated_at=_generated_at(),
    )


def list_stacks_cached(store: StateStore, sites_root: Path | None = None) -> StackListResult:
    status = store.status()
    cache_error = (
        "No cached stack state found. Run `homesrvctl refresh`, "
        "`homesrvctl db rebuild`, or use `homesrvctl list --live`."
    )
    if not status.initialized:
        return StackListResult(
            ok=False,
            source="cache",
            sites_root=sites_root,
            sites=[],
            cache_available=False,
            last_refresh_at=status.last_refresh_at,
            generated_at=_generated_at(),
            db_path=store.path,
            error=cache_error,
            issues=status.issues,
        )
    snapshots = store.list_stack_snapshots()
    cache_available = bool(snapshots)
    if not cache_available:
        return StackListResult(
            ok=False,
            source="cache",
            sites_root=sites_root,
            sites=[],
            cache_available=False,
            last_refresh_at=status.last_refresh_at,
            generated_at=_generated_at(),
            db_path=store.path,
            error=cache_error,
        )
    sites = [
        StackListItem(
            hostname=snapshot.hostname,
            compose=snapshot.has_compose,
            stack_dir=snapshot.stack_dir,
            compose_file=snapshot.compose_file,
            has_stack_config=snapshot.has_stack_config,
            scaffold_kind=snapshot.scaffold_kind,
            scaffold_template=snapshot.scaffold_template,
            profile=snapshot.profile,
            docker_network=snapshot.docker_network,
            traefik_url=snapshot.traefik_url,
            updated_at=snapshot.updated_at,
        )
        for snapshot in snapshots
    ]
    return StackListResult(
        ok=True,
        source="cache",
        sites_root=sites_root,
        sites=sites,
        cache_available=True,
        last_refresh_at=status.last_refresh_at,
        generated_at=_generated_at(),
        db_path=store.path,
    )


def list_stacks(
    config: HomesrvctlConfig,
    store: StateStore,
    *,
    source: str = "live",
    refresh: bool = False,
) -> StackListResult:
    if refresh:
        from homesrvctl.services.refresh import refresh_local_stack_state

        refresh_result = refresh_local_stack_state(db_path=store.path, config=config)
        if not refresh_result.ok:
            return StackListResult(
                ok=False,
                source="cache",
                sites_root=config.sites_root,
                sites=[],
                cache_available=store.has_cached_stack_data(),
                last_refresh_at=store.last_stack_refresh_at(),
                generated_at=_generated_at(),
                db_path=store.path,
                error="refresh failed",
                issues=refresh_result.issues,
            )
        return list_stacks_cached(store, config.sites_root)
    if source == "cache":
        return list_stacks_cached(store, config.sites_root)
    if source == "auto":
        cached = list_stacks_cached(store, config.sites_root)
        return cached if cached.ok else list_stacks_live(config)
    return list_stacks_live(config)


def inspect_stack(config: HomesrvctlConfig, hostname: str) -> tuple[StackSnapshot, list[str]]:
    valid_hostname = validate_hostname(hostname)
    stack_dir = config.hostname_dir(valid_hostname)
    if not stack_dir.exists() or not stack_dir.is_dir():
        raise typer.BadParameter(f"hostname directory does not exist: {stack_dir}")

    issues: list[str] = []
    compose_file = stack_dir / "docker-compose.yml"
    has_stack_config = stack_config_path(stack_dir).exists()
    local_data = load_stack_config_data(stack_dir)
    scaffold = local_data.get("scaffold", {})
    if not isinstance(scaffold, dict):
        scaffold = {}

    profile = str(local_data["profile"]).strip() if local_data.get("profile") else None
    docker_network = None
    traefik_url = None
    try:
        settings = load_stack_settings(config, valid_hostname)
        profile = settings.profile
        docker_network = settings.docker_network
        traefik_url = settings.traefik_url
    except typer.BadParameter as exc:
        issues.append(str(exc))
        docker_network = str(local_data["docker_network"]) if local_data.get("docker_network") else None
        traefik_url = str(local_data["traefik_url"]) if local_data.get("traefik_url") else None

    snapshot = StackSnapshot(
        hostname=valid_hostname,
        stack_dir=stack_dir,
        compose_file=compose_file if compose_file.exists() else None,
        has_compose=compose_file.exists(),
        has_stack_config=has_stack_config,
        scaffold_kind=str(scaffold["kind"]) if scaffold.get("kind") else None,
        scaffold_template=(
            str(scaffold.get("template") or scaffold.get("family"))
            if (scaffold.get("template") or scaffold.get("family"))
            else None
        ),
        profile=profile,
        docker_network=docker_network,
        traefik_url=traefik_url,
    )
    return snapshot, issues
