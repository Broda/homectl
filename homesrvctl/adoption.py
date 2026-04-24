from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SourceDetection:
    family: str
    confidence: str
    evidence: tuple[str, ...]
    issues: tuple[str, ...]
    next_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_source(source_path: Path) -> SourceDetection:
    path = source_path.expanduser()
    issues: list[str] = []
    if not path.exists():
        return SourceDetection(
            family="unknown",
            confidence="none",
            evidence=(),
            issues=(f"source path does not exist: {path}",),
            next_steps=("Provide an existing application or site directory.",),
        )
    if not path.is_dir():
        return SourceDetection(
            family="unknown",
            confidence="none",
            evidence=(f"source path is not a directory: {path}",),
            issues=("source must be a directory",),
            next_steps=("Provide a directory containing the application source.",),
        )

    evidence = _source_evidence(path)
    family, confidence = _select_family(evidence)
    next_steps = _next_steps(family)
    if family == "unknown":
        issues.append("no supported source markers were found")

    return SourceDetection(
        family=family,
        confidence=confidence,
        evidence=tuple(evidence),
        issues=tuple(issues),
        next_steps=tuple(next_steps),
    )


def _source_evidence(path: Path) -> list[str]:
    evidence: list[str] = []
    if (path / "docker-compose.yml").exists() or (path / "compose.yml").exists() or (path / "compose.yaml").exists():
        evidence.append("compose-file")
    if (path / "Dockerfile").exists():
        evidence.append("dockerfile")
    if (path / "package.json").exists():
        evidence.append("package-json")
        package = _read_json(path / "package.json")
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        deps = _merged_dependencies(package)
        if "vite" in deps:
            evidence.append("node-vite")
        if "next" in deps:
            evidence.append("node-next")
        if "start" in scripts:
            evidence.append("node-start-script")
    if (path / "requirements.txt").exists():
        evidence.append("python-requirements")
    if (path / "pyproject.toml").exists():
        evidence.append("python-pyproject")
    if (path / "app.py").exists() or (path / "main.py").exists() or (path / "app" / "main.py").exists():
        evidence.append("python-entrypoint")
    if (path / "_config.yml").exists() or (path / "_config.yaml").exists():
        evidence.append("jekyll-config")
    if (path / "Gemfile").exists() and "jekyll" in _read_text(path / "Gemfile").lower():
        evidence.append("jekyll-gemfile")
    for candidate in ("index.html", "public/index.html", "html/index.html", "_site/index.html"):
        if (path / candidate).exists():
            evidence.append(f"static-index:{candidate}")
            break
    return evidence


def _select_family(evidence: list[str]) -> tuple[str, str]:
    evidence_set = set(evidence)
    if {"jekyll-config", "jekyll-gemfile"} & evidence_set:
        return ("jekyll", "high")
    if "package-json" in evidence_set:
        return ("node", "high")
    if {"python-requirements", "python-pyproject", "python-entrypoint"} & evidence_set:
        return ("python", "medium" if "dockerfile" not in evidence_set else "high")
    if any(item.startswith("static-index:") for item in evidence):
        return ("static", "high")
    if "dockerfile" in evidence_set:
        return ("dockerfile", "medium")
    if "compose-file" in evidence_set:
        return ("compose", "medium")
    return ("unknown", "none")


def _next_steps(family: str) -> list[str]:
    if family == "static":
        return ["Use `homesrvctl app wrap HOST --source PATH --family static` to generate an nginx hosting wrapper."]
    if family in {"node", "python", "dockerfile"}:
        return [
            "Use `homesrvctl app wrap HOST --source PATH --family dockerfile --service-port PORT` when the source already has a Dockerfile."
        ]
    if family == "jekyll":
        return [
            "Use `homesrvctl app init HOST --template jekyll` for a managed scaffold, then copy the existing Jekyll source into the generated `site/` directory."
        ]
    if family == "compose":
        return ["Existing Compose adoption is not mutating yet; inspect the file and add homesrvctl routing labels manually for now."]
    return ["Choose a wrapper family explicitly once you know how the app should be served."]


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _merged_dependencies(package: dict[str, object]) -> set[str]:
    dependencies: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        raw = package.get(key, {})
        if isinstance(raw, dict):
            dependencies.update(str(name) for name in raw)
    return dependencies
