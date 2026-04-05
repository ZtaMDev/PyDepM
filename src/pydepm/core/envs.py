from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from .proc import run_with_ticks


class EnvType(str, Enum):
    VENV = "venv"
    CONDA = "conda"
    GLOBAL = "global"


@dataclass
class EnvCreationError(Exception):
    """Error raised when an environment cannot be created."""

    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def create_environment(project_dir: Path, env_type: str, tick: Optional[Callable[[], None]] = None) -> None:
    """Create a project environment according to the given type.

    For phase 1 only basic creation is implemented:
    - venv: create .venv with ``python -m venv``.
    - conda: try to create an environment with ``conda create`` (simple for now).
    - global: do nothing.
    """

    et = EnvType(env_type)

    if et is EnvType.GLOBAL:
        return

    if et is EnvType.VENV:
        env_path = project_dir / ".venv"
        if env_path.exists():
            return
        try:
            result = run_with_ticks(
                [os.sys.executable, "-m", "venv", str(env_path)],
                tick=tick,
            )
            if result.returncode != 0:
                raise EnvCreationError(
                    f"venv creation failed with exit code {result.returncode}."
                )
        except FileNotFoundError as exc:  # pragma: no cover - system-dependent
            raise EnvCreationError(
                "Python executable not found while creating venv."
            ) from exc
    elif et is EnvType.CONDA:
        env_name = project_dir.name
        # Note: this assumes that ``conda`` is on PATH.
        try:
            result = run_with_ticks(
                [
                    "conda",
                    "create",
                    "-y",
                    "-n",
                    env_name,
                    f"python={os.sys.version_info.major}.{os.sys.version_info.minor}",
                ],
                tick=tick,
            )
            if result.returncode != 0:
                raise EnvCreationError(
                    f"conda environment creation failed with exit code {result.returncode}."
                )
        except FileNotFoundError as exc:  # pragma: no cover - depends on user setup
            raise EnvCreationError(
                "conda is not installed or not available on PATH."
            ) from exc


def get_env_path(project_dir: Path, env_type: str) -> Optional[Path]:
    et = EnvType(env_type)

    if et is EnvType.GLOBAL:
        return None

    if et is EnvType.VENV:
        env_path = project_dir / ".venv"
        return env_path if env_path.exists() else None

    if et is EnvType.CONDA:
        # In phase 1 we don't resolve the exact path; just return None.
        # Future: integrate with ``conda info --envs``.
        return None

    return None


def get_env_bin_dir(env_path: Path) -> Path:
    """Return the binaries directory for a venv-like environment (Windows/Linux)."""

    if os.name == "nt":
        return env_path / "Scripts"
    return env_path / "bin"
