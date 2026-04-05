from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional
import sys

import tomllib


PYDEPM_TOOL_SECTION = "tool.pydepm"


@dataclass
class ProjectConfig:
    """Project configuration relevant for pydepm (phase 1)."""

    name: str
    project_type: str  # "module" or "app"
    env_type: str  # "venv", "conda" or "global"
    python_version: str
    dist_dir: str = "dist"
    scripts: Dict[str, str] = field(default_factory=dict)


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_project_config(project_dir: Path) -> Optional[ProjectConfig]:
    """Load project configuration from pyproject.toml.

    Returns None if the file does not exist or has no pydepm section.
    """

    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    data = _load_toml(pyproject_path)

    project = data.get("project", {})
    tool = data.get("tool", {})
    pydepm_cfg = tool.get("pydepm", {})

    name = project.get("name") or pydepm_cfg.get("name")
    if not name:
        return None

    project_type = pydepm_cfg.get("type", "module")
    env_type = pydepm_cfg.get("env", {}).get("type", "venv")
    python_version = pydepm_cfg.get("python-version") or f"{sys.version_info.major}.{sys.version_info.minor}"
    dist_dir = pydepm_cfg.get("dist-dir", "dist")
    scripts = pydepm_cfg.get("scripts", {})

    return ProjectConfig(
        name=name,
        project_type=project_type,
        env_type=env_type,
        python_version=python_version,
        dist_dir=dist_dir,
        scripts=scripts,
    )


def bootstrap_project(
    target_dir: Path,
    project_name: str,
    project_type: str,
    env_type: str,
    python_version: str,
) -> None:
    """Create basic pyproject.toml, directory structure, and .gitignore.

    Creates src/project_name/, tests/ directories and generates pyproject.toml
    and .gitignore if they do not exist.
    """

    target_dir.mkdir(parents=True, exist_ok=True)

    pyproject_path = target_dir / "pyproject.toml"
    gitignore_path = target_dir / ".gitignore"

    if not pyproject_path.exists():
        content = _default_pyproject_content(
            name=project_name,
            project_type=project_type,
            env_type=env_type,
            python_version=python_version,
        )
        pyproject_path.write_text(content, encoding="utf-8")

    if not gitignore_path.exists():
        gitignore_path.write_text(_default_gitignore_content(), encoding="utf-8")

    # Create src/project_name/ directory with __init__.py
    src_dir = target_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    src_init = src_dir / "__init__.py"
    if not src_init.exists():
        src_init.write_text('# Namespace package root for source packages\n', encoding="utf-8")

    package_dir = src_dir / project_name.replace("-", "_")
    package_dir.mkdir(parents=True, exist_ok=True)
    
    init_py = package_dir / "__init__.py"
    if not init_py.exists():
        init_py.write_text(
            f'"""Package {project_name}."""\n\n__version__ = "0.1.0"\n',
            encoding="utf-8",
        )

    # Create tests/ directory
    tests_dir = target_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    
    test_init = tests_dir / "__init__.py"
    if not test_init.exists():
        test_init.write_text('"""Tests for the project."""\n', encoding="utf-8")
    
    # Create a basic test file
    package_import = f"src.{project_name.replace('-', '_')}"
    test_file = tests_dir / "test_basic.py"
    if not test_file.exists():
        test_file.write_text(f'''"""Basic tests for {project_name}."""

def test_import():
    """Test that package can be imported."""
    import {package_import}
    assert hasattr({package_import}, "__version__")


def test_version():
    """Test version is set."""
    import {package_import}
    assert {package_import}.__version__ == "0.1.0"
''', encoding="utf-8")


def _default_pyproject_content(name: str, project_type: str, env_type: str, python_version: str) -> str:
    """Return the default pyproject.toml content for a new project.

    For ``project_type = "module"`` we generate a simple dev script using
    ``python -c``. For ``project_type = "app"`` we generate a main.py oriented
    layout with a PyInstaller configuration section.
    """

    base = f"""[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"

"""

    tool_section = f"""[tool.pydepm]
name = "{name}"
type = "{project_type}"
python-version = "{python_version}"

"""

    env_section = f"""[tool.pydepm.env]
type = "{env_type}"

"""

    publishing_section = """[tool.pydepm.publishing]
repository = "pypi"
# repository can be: "pypi" or "testpypi"

"""

    if project_type == "app":
        pyinstaller_section = '''[tool.pydepm.pyinstaller]
entry = "main.py"
onefile = true
# icon = "path/to/icon.ico"

'''

        scripts_section = '''[tool.pydepm.scripts]
dev = "python ./main.py"
'''

        return base + tool_section + env_section + publishing_section + pyinstaller_section + scripts_section

    # Default for modules
    scripts_section = '''[tool.pydepm.scripts]
dev = "python ./main.py"
'''

    return base + tool_section + env_section + publishing_section + scripts_section


def _default_gitignore_content() -> str:
    return """# Pydepm / Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.env
.venv
venv/
.build/
.dist/
.pytest_cache/
.mypy_cache/
.idea/
.vscode/
.DS_Store
"""
