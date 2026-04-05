"""
Integration module for PyDepm resolver with CLI commands.
Provides wrappers to seamlessly integrate custom Python dependency resolution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

from .pypi import PyPIClient, PyPIClientError
from .resolver import DependencyResolver, ResolutionError, ResolutionResult
from .lock import LockFile


@dataclass
class ResolutionStatus:
    """Result from resolver integration."""
    success: bool
    resolved: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    resolution_time: float


def resolve_requirements(
    requirements: List[str],
    python_version: str = "3.11",
    use_cache: bool = True,
) -> ResolutionStatus:
    """Resolve dependencies using custom resolver.
    
    Args:
        requirements: List of requirement specs (e.g., ['requests>=2.0', 'pytest'])
        python_version: Python version for resolution (default: 3.11)
        use_cache: Whether to use PyPI cache (default: True)
        
    Returns:
        ResolutionStatus with results
    """
    resolver = DependencyResolver(python_version=python_version)
    result = resolver.resolve(requirements)
    
    return ResolutionStatus(
        success=result.success,
        resolved=result.resolved,
        errors=result.errors,
        warnings=result.warnings,
        resolution_time=result.resolution_time,
    )


def validate_lock_file(lock_path: Path) -> Tuple[bool, List[str]]:
    """Validate an existing lock file.
    
    Args:
        lock_path: Path to lock file
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    if not lock_path.exists():
        return False, [f"Lock file not found: {lock_path}"]
    
    try:
        lock = LockFile.load(lock_path)
        errors = lock.validate()
        return not errors, errors
    except Exception as e:
        return False, [str(e)]


def update_lock_file(
    project_dir: Path,
    include_dev: bool = False,
    optional_groups: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Update or create lock file with current dependencies.
    
    Args:
        project_dir: Project root directory
        include_dev: Include dev dependencies
        optional_groups: Optional dependency groups to include
        
    Returns:
        Tuple of (success, message)
    """
    from . import config as core_config
    from . import deps as core_deps
    
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return False, "No pyproject.toml found"
    
    # Collect requirements
    try:
        specs = core_deps.collect_requirement_specs(
            pyproject_path,
            include_dev=include_dev,
            optional_groups=optional_groups,
        )
    except Exception as e:
        return False, f"Error collecting requirements: {e}"
    
    if not specs:
        return False, "No dependencies to lock"
    
    # Resolve
    status = resolve_requirements(specs)
    if not status.success:
        errors = "\n".join(status.errors)
        return False, f"Resolution failed:\n{errors}"
    
    # Create lock file
    try:
        lock = LockFile.from_resolution(
            ResolutionResult(success=True, resolved=status.resolved),
            pyproject_path
        )
        lock_path = project_dir / "pydepm.lock"
        lock.save(lock_path, format="toml")
        return True, f"Lock file created: {lock_path}"
    except Exception as e:
        return False, f"Error creating lock file: {e}"


def get_pypi_package_info(
    package_name: str,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """Get metadata for a package from PyPI.
    
    Args:
        package_name: Package name
        use_cache: Use cache if available
        
    Returns:
        Package metadata or None if not found
    """
    try:
        client = PyPIClient(use_cache=use_cache)
        info = client.get_package_info(package_name)
        if info:
            return {
                "name": info.name,
                "version": info.version,
                "summary": info.summary,
                "requires": info.requires,
            }
    except PyPIClientError:
        pass
    
    return None


def check_resolver_availability() -> Tuple[bool, Optional[str]]:
    """Check if resolver is available and working.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    try:
        resolver = DependencyResolver()
        # Try a simple resolution
        result = resolver.resolve(["pip"])
        if result.success:
            return True, None
        else:
            errors = "\n".join(result.errors) if result.errors else "Unknown error"
            return False, errors
    except Exception as e:
        return False, str(e)
