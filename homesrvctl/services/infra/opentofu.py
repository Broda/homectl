from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Callable

from homesrvctl.shell import CommandResult, run_command

TOFU_BINARY = "tofu"


@dataclass(slots=True)
class TofuCommandResult:
    command: list[str]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "command": self.command,
            "cwd": str(self.cwd),
            "returncode": self.returncode,
            "stdout": _truncate(self.stdout),
            "stderr": _truncate(self.stderr),
        }


@dataclass(slots=True)
class TofuStatus:
    available: bool
    path: str | None
    version: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.available and not self.issues

    def to_dict(self) -> dict[str, object]:
        return {
            "tofu_available": self.available,
            "tofu_path": self.path,
            "tofu_version": self.version,
            "issues": self.issues,
        }


Runner = Callable[..., CommandResult]
Which = Callable[[str], str | None]


def inspect_tofu(
    *,
    binary: str = TOFU_BINARY,
    which: Which = shutil.which,
    runner: Runner = run_command,
) -> TofuStatus:
    path = which(binary)
    if path is None:
        return TofuStatus(
            available=False,
            path=None,
            version=None,
            issues=["OpenTofu binary `tofu` not found; install OpenTofu and retry"],
        )

    result = runner([path, "version"], quiet=True)
    version = _first_line(result.stdout or result.stderr)
    issues: list[str] = []
    if not result.ok:
        issues.append(result.stderr or result.stdout or "`tofu version` failed")
    return TofuStatus(available=True, path=path, version=version, issues=issues)


def run_tofu_init(
    workspace_path: Path,
    *,
    tofu_path: str = TOFU_BINARY,
    runner: Runner = run_command,
) -> TofuCommandResult:
    return _run_tofu([tofu_path, "init", "-input=false", "-no-color"], workspace_path, runner=runner)


def run_tofu_plan(
    workspace_path: Path,
    *,
    tofu_path: str = TOFU_BINARY,
    runner: Runner = run_command,
) -> TofuCommandResult:
    return _run_tofu(
        [tofu_path, "plan", "-detailed-exitcode", "-input=false", "-no-color"],
        workspace_path,
        runner=runner,
    )


def _run_tofu(command: list[str], cwd: Path, *, runner: Runner) -> TofuCommandResult:
    result = runner(command, cwd=cwd, quiet=True)
    return TofuCommandResult(
        command=result.command,
        cwd=cwd,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _first_line(value: str) -> str | None:
    for line in value.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _truncate(value: str, *, limit: int = 8000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[truncated]"

