from __future__ import annotations

import tomllib
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from homesrvctl import __version__
from homesrvctl.template_catalog import expected_packaged_template_files

EXPECTED_TEMPLATE_FILES = expected_packaged_template_files()


def test_package_version_matches_pyproject_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == __version__


def test_build_artifacts_include_shipped_template_assets(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    outdir = tmp_path / "dist"

    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(outdir)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_path = next(outdir.glob("homesrvctl-*.whl"))
    sdist_path = next(outdir.glob("homesrvctl-*.tar.gz"))

    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_names = set(wheel.namelist())
        wheel.extractall(tmp_path / "wheel")
    missing_from_wheel = EXPECTED_TEMPLATE_FILES - wheel_names
    assert not missing_from_wheel, f"wheel is missing shipped template assets: {sorted(missing_from_wheel)}"
    assert "homesrvctl/templates/__init__.py" in wheel_names
    assert "homesrvctl/templates.py" not in wheel_names

    import_check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import homesrvctl.main; from homesrvctl.templates import render_template; print(render_template.__name__)",
        ],
        cwd=tmp_path,
        env={"PYTHONPATH": str(tmp_path / "wheel")},
        check=True,
        capture_output=True,
        text=True,
    )
    assert import_check.stdout.strip() == "render_template"

    with tarfile.open(sdist_path, "r:gz") as sdist:
        sdist_names = set(sdist.getnames())
    sdist_paths = {name.split("/", 1)[1] for name in sdist_names if "/" in name}
    missing_from_sdist = EXPECTED_TEMPLATE_FILES - sdist_paths
    assert not missing_from_sdist, f"sdist is missing shipped template assets: {sorted(missing_from_sdist)}"
