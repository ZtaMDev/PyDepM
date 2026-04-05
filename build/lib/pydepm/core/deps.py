from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
import tomllib
from packaging.requirements import Requirement
import tomlkit
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class DependencyChange:
    """Result of a dependency mutation operation."""

    added: List[str]
    removed: List[str]
    updated: List[str]


class DependencyError(Exception):
    """Raised when dependency operations cannot be completed."""


class PipError(Exception):
    """Raised when pip operations fail at the low-level API."""


def normalize_package_name(name: str) -> str:
    return name.lower().replace("_", "-")


def parse_requirement_name(spec: str) -> Optional[str]:
    try:
        return Requirement(spec).name
    except Exception:
        return None


def _load_toml(path: Path):
    """Load TOML document preserving structure and comments.

    We use tomlkit for round-tripping. Callers can treat the result as a
    mapping (TomlDocument behaves like a dict).
    """

    text = path.read_text(encoding="utf-8")
    return tomlkit.parse(text)


def _dump_toml(data) -> str:
    """Serialize TOML document using tomlkit, preserving formatting.

    ``data`` is expected to be a TomlDocument (or compatible mapping) created
    by ``_load_toml``. tomlkit will keep most comments and layout intact while
    applying our changes.
    """

    return tomlkit.dumps(data)


def _ensure_project_sections(data: dict) -> dict:
    """Ensure top-level sections exist without forcing empty subsections.

    We only guarantee that the [project] table exists; the presence of
    "dependencies", "optional-dependencies" or "dev-dependencies" is driven
    by actual content so we don't create empty tables in the user's file.
    """

    data.setdefault("project", {})
    data.setdefault("tool", {}).setdefault("pydepm", {})
    return data


def _find_requirement_index(requirements: List[str], name: str) -> Optional[int]:
    name_lower = name.lower().replace("_", "-")
    for i, raw in enumerate(requirements):
        try:
            req = Requirement(raw)
        except Exception:
            continue
        if req.name.lower().replace("_", "-") == name_lower:
            return i
    return None


def load_dependencies(pyproject_path: Path) -> dict:
    """Load dependency-related sections from pyproject.toml.

    Returns a dict with keys:
    - project_dependencies: List[str]
    - optional_dependencies: Dict[str, List[str]]
    - dev_dependencies: List[str]
    """

    data = _load_toml(pyproject_path)
    project = data.get("project", {})
    tool = data.get("tool", {})
    pydepm = tool.get("pydepm", {})

    return {
        "project_dependencies": list(project.get("dependencies", [])),
        "optional_dependencies": dict(project.get("optional-dependencies", {})),
        "dev_dependencies": list(
            pydepm.get("dev-dependencies") or pydepm.get("dev_dependencies") or []
        ),
    }


def collect_requirement_specs(
    pyproject_path: Path,
    *,
    include_dev: bool = False,
    optional_groups: Optional[List[str]] = None,
) -> List[str]:
    """Collect requirement spec strings from pyproject.toml.

    - Always includes [project].dependencies
    - If include_dev=True includes [tool.pydepm].dev-dependencies
    - If optional_groups is provided, includes matching groups from
      [project.optional-dependencies]
    """

    deps = load_dependencies(pyproject_path)
    specs: List[str] = []
    specs.extend(deps.get("project_dependencies", []))

    if include_dev:
        specs.extend(deps.get("dev_dependencies", []))

    if optional_groups:
        opt: Dict[str, List[str]] = deps.get("optional_dependencies", {})
        for group in optional_groups:
            specs.extend(opt.get(group, []))

    return specs


def collect_requirement_names(specs: List[str]) -> List[str]:
    """Extract normalized package names from requirement specs."""

    names: List[str] = []
    for spec in specs:
        parsed = parse_requirement_name(spec)
        if parsed:
            names.append(normalize_package_name(parsed))
    # de-dup while preserving order
    out: List[str] = []
    seen = set()
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def get_declared_spec(
    pyproject_path: Path,
    name: str,
    *,
    group: Optional[str] = None,
    dev: bool = False,
) -> Optional[str]:
    """Return the currently declared requirement spec for a package name.

    This is used by higher-level commands to decide whether a change to
    pyproject.toml is actually necessary.
    """

    data = _load_toml(pyproject_path)
    project = data.get("project", {})
    tool = data.get("tool", {})
    pydepm = tool.get("pydepm", {})

    if dev:
        container = list(pydepm.get("dev-dependencies") or pydepm.get("dev_dependencies") or [])
    elif group is not None:
        opt = dict(project.get("optional-dependencies", {}) or {})
        container = list(opt.get(group, []) or [])
    else:
        container = list(project.get("dependencies", []) or [])

    idx = _find_requirement_index(container, name)
    if idx is None:
        return None
    return container[idx]


def add_dependency(
    pyproject_path: Path,
    spec: str,
    group: Optional[str] = None,
    dev: bool = False,
) -> DependencyChange:
    """Add a dependency to pyproject.toml.

    - If dev=True -> goes to tool.pydepm.dev-dependencies.
    - If group is not None -> goes to project.optional-dependencies[group].
    - Else -> goes to project.dependencies.
    """

    data = _load_toml(pyproject_path)
    data = _ensure_project_sections(data)

    project = data["project"]
    tool = data["tool"]
    pydepm = tool["pydepm"]

    added: List[str] = []

    if dev:
        dev_deps: List[str] = list(pydepm.get("dev-dependencies") or [])
        if spec not in dev_deps:
            dev_deps.append(spec)
            pydepm["dev-dependencies"] = dev_deps
            added.append(spec)
    elif group is not None:
        opt_deps: Dict[str, List[str]] = dict(project.get("optional-dependencies") or {})
        group_list = opt_deps.setdefault(group, [])
        if spec not in group_list:
            group_list.append(spec)
            opt_deps[group] = group_list
            project["optional-dependencies"] = opt_deps
            added.append(spec)
    else:
        proj_deps: List[str] = project.get("dependencies") or []
        if spec not in proj_deps:
            proj_deps.append(spec)
            project["dependencies"] = proj_deps
            added.append(spec)

    # Persist simplified view back to disk
    rendered = _dump_toml(data)
    pyproject_path.write_text(rendered, encoding="utf-8")

    return DependencyChange(added=added, removed=[], updated=[])


def remove_dependency(
    pyproject_path: Path,
    name: str,
    group: Optional[str] = None,
    dev: bool = False,
) -> DependencyChange:
    """Remove a dependency by name from the selected scope."""

    data = _load_toml(pyproject_path)
    data = _ensure_project_sections(data)

    project = data["project"]
    tool = data["tool"]
    pydepm = tool["pydepm"]

    removed: List[str] = []

    if dev:
        dev_deps: List[str] = list(pydepm.get("dev-dependencies") or [])
        idx = _find_requirement_index(dev_deps, name)
        if idx is not None:
            removed.append(dev_deps.pop(idx))
            if dev_deps:
                pydepm["dev-dependencies"] = dev_deps
            else:
                # Drop the key entirely when empty to avoid clutter.
                pydepm.pop("dev-dependencies", None)
    elif group is not None:
        opt_deps: Dict[str, List[str]] = dict(project.get("optional-dependencies") or {})
        group_list = list(opt_deps.get(group) or [])
        idx = _find_requirement_index(group_list, name)
        if idx is not None:
            removed.append(group_list.pop(idx))
            if group_list:
                opt_deps[group] = group_list
            else:
                opt_deps.pop(group, None)

            if opt_deps:
                project["optional-dependencies"] = opt_deps
            else:
                project.pop("optional-dependencies", None)
    else:
        proj_deps: List[str] = project.get("dependencies") or []
        idx = _find_requirement_index(proj_deps, name)
        if idx is not None:
            removed.append(proj_deps.pop(idx))
            project["dependencies"] = proj_deps

    rendered = _dump_toml(data)
    pyproject_path.write_text(rendered, encoding="utf-8")

    return DependencyChange(added=[], removed=removed, updated=[])


def update_dependency(
    pyproject_path: Path,
    spec: str,
    group: Optional[str] = None,
    dev: bool = False,
) -> DependencyChange:
    """Update or add a dependency, returning what changed."""

    data = _load_toml(pyproject_path)
    data = _ensure_project_sections(data)

    project = data["project"]
    tool = data["tool"]
    pydepm = tool["pydepm"]

    updated: List[str] = []
    added: List[str] = []

    try:
        req = Requirement(spec)
    except Exception as exc:  # pragma: no cover - relies on user input
        raise DependencyError(f"Invalid requirement spec: {spec}") from exc

    def _upsert(container: List[str]) -> None:
        nonlocal updated, added
        idx = _find_requirement_index(container, req.name)
        if idx is None:
            container.append(spec)
            added.append(spec)
        else:
            if container[idx] != spec:
                container[idx] = spec
                updated.append(spec)

    if dev:
        dev_deps: List[str] = pydepm.get("dev-dependencies") or []
        _upsert(dev_deps)
        pydepm["dev-dependencies"] = dev_deps
    elif group is not None:
        opt_deps: Dict[str, List[str]] = project.get("optional-dependencies") or {}
        group_list = opt_deps.setdefault(group, [])
        _upsert(group_list)
        opt_deps[group] = group_list
        project["optional-dependencies"] = opt_deps
    else:
        proj_deps: List[str] = project.get("dependencies") or []
        _upsert(proj_deps)
        project["dependencies"] = proj_deps

    rendered = _dump_toml(data)
    pyproject_path.write_text(rendered, encoding="utf-8")

    return DependencyChange(added=added, removed=[], updated=updated)


# --- Low-level pip / PyPI helpers -----------------------------------------------------------


def build_pip_install_args(requirements: List[str]) -> List[str]:
    """Build argument list for ``pip install``.

    This does not execute pip; it only prepares the arguments so that the
    caller (higher-level service or CLI) can run them using subprocess with
    the appropriate environment (venv/conda/global).
    """

    return ["-m", "pip", "install", *requirements]


def build_pip_uninstall_args(packages: List[str], yes: bool = True) -> List[str]:
    """Build argument list for ``pip uninstall``."""

    args = ["-m", "pip", "uninstall"]
    if yes:
        args.append("-y")
    args.extend(packages)
    return args


def fetch_pypi_metadata(name: str) -> Dict[str, object]:
    """Fetch basic package metadata from PyPI.

    Returns a JSON-like dict with at least keys ``info`` and ``releases`` if
    the package exists. Raises ``DependencyError`` if the package cannot be
    found or PyPI is not reachable.
    """

    url = f"https://pypi.org/pypi/{name}/json"
    try:
        resp = requests.get(url, timeout=5)
    except requests.RequestException as exc:  # pragma: no cover - network
        raise DependencyError(f"Failed to contact PyPI for '{name}': {exc}") from exc

    if resp.status_code == 404:
        raise DependencyError(f"Package '{name}' not found on PyPI.")

    if not resp.ok:
        raise DependencyError(
            f"PyPI returned unexpected status {resp.status_code} for '{name}'."
        )

    try:
        return resp.json()
    except ValueError as exc:  # pragma: no cover
        raise DependencyError("Failed to decode PyPI response as JSON.") from exc


def fetch_many_pypi_metadata(names: List[str], max_workers: int = 8) -> Dict[str, Dict[str, object]]:
    """Fetch PyPI metadata for many package names in parallel.

    Returns a mapping name -> metadata dict. Packages that fail will be
    omitted from the result; the caller can decide how to handle missing
    entries when implementing audit/resolve/fix.
    """

    results: Dict[str, Dict[str, object]] = {}

    def _worker(pkg: str) -> Optional[Dict[str, object]]:
        try:
            return fetch_pypi_metadata(pkg)
        except DependencyError:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_worker, name): name for name in names}
        for future in as_completed(future_map):
            pkg_name = future_map[future]
            meta = future.result()
            if meta is not None:
                results[pkg_name] = meta

    return results
