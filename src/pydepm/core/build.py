from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import tomllib

from .config import ProjectConfig
from .proc import run_with_ticks


@dataclass
class BuildError(Exception):
    """Error raised when a build process fails."""

    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def build_module(project_dir: Path, cfg: ProjectConfig, tick=None) -> Path:
    """Build a module project (sdist + wheel) into the configured dist directory.

    Uses ``python -m build`` under the hood. Requires the ``build`` package to be
    installed in the environment running pydep.
    """

    dist_dir = project_dir / cfg.dist_dir
    dist_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        os.sys.executable,
        "-m",
        "build",
        "--sdist",
        "--wheel",
        "--outdir",
        str(dist_dir),
    ]

    result = run_with_ticks(cmd, cwd=str(project_dir), tick=tick)
    if result.returncode != 0:
        stderr = result.stderr or ""
        if "No module named" in stderr and "build" in stderr:
            raise BuildError(
                "The 'build' package is not installed in this Python environment. "
                "Install it with 'pip install build'."
            )
        raise BuildError(
            f"python -m build failed with exit code {result.returncode}.\n{stderr.strip()}"
        )

    return dist_dir


def _load_pyinstaller_config(project_dir: Path) -> Dict[str, Any]:
    """Load minimal PyInstaller-related configuration from pyproject.toml.

    Expected structure:

    [tool.pydepm.pyinstaller]
    entry = "path/to/main.py"  # default: "main.py"
    onefile = true              # default: true
    icon = "path/to/icon.ico"  # optional
    """

    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return {}

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    tool = data.get("tool", {})
    pydepm_cfg = tool.get("pydepm", {})
    return pydepm_cfg.get("pyinstaller", {})


def build_app(project_dir: Path, cfg: ProjectConfig, tick=None) -> Path:
    """Build an app project using PyInstaller.

    Uses the following configuration from [tool.pydepm.pyinstaller]:
    - entry: entry script path (default: "main.py")
    - onefile: whether to build a one-file executable (default: true)
    - icon: optional icon file path
    """

    dist_dir = project_dir / cfg.dist_dir
    dist_dir.mkdir(parents=True, exist_ok=True)

    pyinst_cfg = _load_pyinstaller_config(project_dir)

    entry = pyinst_cfg.get("entry", "main.py")
    onefile = bool(pyinst_cfg.get("onefile", True))
    icon = pyinst_cfg.get("icon")

    entry_path = project_dir / entry
    if not entry_path.exists():
        raise BuildError(
            f"PyInstaller entry script '{entry}' does not exist in project directory."
        )

    cmd = [
        "pyinstaller",
        "--name",
        cfg.name,
        "--distpath",
        str(dist_dir),
    ]

    if onefile:
        cmd.append("--onefile")

    if icon:
        cmd.extend(["--icon", icon])

    # Optional common flags from config
    windowed = pyinst_cfg.get("windowed")
    if isinstance(windowed, bool) and windowed:
        cmd.append("--windowed")

    console = pyinst_cfg.get("console")
    if isinstance(console, bool):
        # PyInstaller defaults to console on; allow explicit override.
        cmd.append("--console" if console else "--noconsole")

    # add-data / add-binary can be a string or list of strings
    add_data = pyinst_cfg.get("add-data") or pyinst_cfg.get("add_data")
    if isinstance(add_data, str):
        add_data = [add_data]
    if isinstance(add_data, list):
        for item in add_data:
            cmd.extend(["--add-data", str(item)])

    add_binary = pyinst_cfg.get("add-binary") or pyinst_cfg.get("add_binary")
    if isinstance(add_binary, str):
        add_binary = [add_binary]
    if isinstance(add_binary, list):
        for item in add_binary:
            cmd.extend(["--add-binary", str(item)])

    hidden_imports = (
        pyinst_cfg.get("hidden-imports")
        or pyinst_cfg.get("hidden_imports")
        or []
    )
    if isinstance(hidden_imports, str):
        hidden_imports = [hidden_imports]
    if isinstance(hidden_imports, list):
        for name in hidden_imports:
            cmd.extend(["--hidden-import", str(name)])

    paths = pyinst_cfg.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    if isinstance(paths, list):
        for p in paths:
            cmd.extend(["--paths", str(p)])

    if bool(pyinst_cfg.get("noupx", False)):
        cmd.append("--noupx")

    if bool(pyinst_cfg.get("clean", False)):
        cmd.append("--clean")

    debug = pyinst_cfg.get("debug")
    if isinstance(debug, bool) and debug:
        cmd.extend(["--debug", "all"])
    elif isinstance(debug, str) and debug:
        cmd.extend(["--debug", debug])

    if bool(pyinst_cfg.get("strip", False)):
        cmd.append("--strip")

    upx_exclude = (
        pyinst_cfg.get("upx-exclude")
        or pyinst_cfg.get("upx_exclude")
        or []
    )
    if isinstance(upx_exclude, str):
        upx_exclude = [upx_exclude]
    if isinstance(upx_exclude, list):
        for name in upx_exclude:
            cmd.extend(["--upx-exclude", str(name)])

    # raw-args: passthrough list of additional arguments directly to PyInstaller
    raw_args = pyinst_cfg.get("raw-args") or pyinst_cfg.get("raw_args") or []
    if isinstance(raw_args, str):
        raw_args = [raw_args]
    if isinstance(raw_args, list):
        cmd.extend(str(a) for a in raw_args)

    # Finally add the entry script path
    cmd.append(str(entry_path))

    try:
        result = run_with_ticks(cmd, cwd=str(project_dir), tick=tick)
    except FileNotFoundError as exc:  # pragma: no cover - depends on user setup
        raise BuildError(
            "PyInstaller is not installed or not available on PATH. "
            "Install it with 'pip install pyinstaller'."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr or ""
        raise BuildError(
            f"pyinstaller failed with exit code {result.returncode}.\n{stderr.strip()}"
        )

    return dist_dir
