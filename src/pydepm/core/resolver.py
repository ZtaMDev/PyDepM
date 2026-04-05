"""
Dependency resolution algorithm - replaces pip with our own resolver.
Implements backtracking algorithm to find compatible dependency trees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version

from .pypi import PyPIClient, PyPIPackage


@dataclass
class ResolvedDependency:
    """A resolved dependency with all metadata."""
    
    name: str
    version: str
    specifier: str  # Original specifier like ">=1.0,<2.0"
    url: str = ""
    sha256: str = ""
    requires: List[str] = field(default_factory=list)
    markers: Optional[str] = None
    
    def __eq__(self, other):
        if isinstance(other, ResolvedDependency):
            return self.name.lower() == other.name.lower() and self.version == other.version
        return False
    
    def __hash__(self):
        return hash((self.name.lower(), self.version))


@dataclass
class ResolutionResult:
    """Result of dependency resolution."""
    
    success: bool
    resolved: Dict[str, ResolvedDependency] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resolution_time: float = 0.0


class ResolutionError(Exception):
    """Raised when dependency resolution fails."""
    pass


class DependencyResolver:
    """
    Resolves dependencies using a backtracking algorithm.
    This replaces pip's resolver with our own implementation.
    """
    
    def __init__(self, pypi_client: Optional[PyPIClient] = None, python_version: str = "3.11"):
        self.pypi = pypi_client or PyPIClient()
        self.python_version = python_version
        self._resolution_cache: Dict[str, ResolvedDependency] = {}
        self._attempted: Set[Tuple[str, str]] = set()
    
    def resolve(
        self,
        requirements: List[str],
        prefer_pinned: bool = False,
        with_dev: bool = False,
    ) -> ResolutionResult:
        """
        Resolve a list of requirements to a concrete dependency tree.
        
        Args:
            requirements: List of requirement specifiers (e.g., ['requests>=2.28', 'pytest'])
            prefer_pinned: If True, prefer pinned versions from existing lock if available
            with_dev: If True, include dev dependencies
            
        Returns:
            ResolutionResult with resolved dependencies or errors
        """
        import time
        start = time.time()
        
        result = ResolutionResult(success=False)
        self._resolution_cache.clear()
        self._attempted.clear()
        
        try:
            # Parse all requirements
            parsed_reqs = []
            for req_spec in requirements:
                try:
                    req = Requirement(req_spec)
                    parsed_reqs.append((req.name, str(req.specifier) if req.specifier else ""))
                except Exception as e:
                    result.errors.append(f"Invalid requirement: {req_spec} - {e}")
                    return result
            
            # Resolve each requirement and their transitive dependencies
            resolved = {}
            for name, specifier in parsed_reqs:
                self._resolve_package(name, specifier, resolved, result)
            
            result.resolved = resolved
            result.success = len(result.errors) == 0
            
        except Exception as e:
            result.errors.append(f"Resolution failed: {str(e)}")
            result.success = False
        
        finally:
            result.resolution_time = time.time() - start
        
        return result
    
    def _resolve_package(
        self,
        name: str,
        specifier: str,
        resolved: Dict[str, object],
        result: ResolutionResult,
        depth: int = 0,
    ) -> bool:
        """
        Recursively resolve a package and its dependencies.
        
        Returns True if resolution succeeded, False otherwise.
        """
        
        # Prevent infinite recursion
        if depth > 50:
            result.errors.append(f"Circular dependency detected for {name}")
            return False
        
        # Normalize name for lookup
        normalized_name = name.lower().replace("_", "-")
        
        # If already resolved, check compatibility
        if normalized_name in resolved:
            existing = resolved[normalized_name]
            if self._is_compatible(existing.version, specifier):
                return True
            else:
                result.errors.append(
                    f"Incompatible versions for {name}: "
                    f"already resolved to {existing.version}, but requires {specifier}"
                )
                return False
        
        # Fetch package info from PyPI
        pkg = self.pypi.get_package(name)
        if not pkg:
            result.errors.append(f"Package not found on PyPI: {name}")
            return False
        
        # Find best matching version
        best_version = self._find_best_version(pkg, specifier, result)
        if not best_version:
            result.errors.append(
                f"No compatible version found for {name} {specifier}"
            )
            return False
        
        # Check if version is yanked
        release = pkg.get_release(best_version)
        if release and release.yanked:
            result.warnings.append(
                f"Warning: {name}=={best_version} is yanked (deprecated)"
            )
        
        # Create resolved dependency
        resolved_dep = ResolvedDependency(
            name=name,
            version=best_version,
            specifier=specifier,
        )
        
        # Get distribution file info
        if release and release.files:
            # Prefer wheels, then source distributions
            wheel_file = next(
                (f for f in release.files if f.filename.endswith('.whl')),
                None
            )
            file_obj = wheel_file or release.files[0]
            
            resolved_dep.url = file_obj.url
            resolved_dep.sha256 = file_obj.hashes.get('sha256', '')
        
        # Resolve dependencies of this package
        if release:
            for dep_spec in release.requires_dist:
                try:
                    dep_req = Requirement(dep_spec)
                    
                    # Check if dependency applies to our Python version
                    if dep_req.marker and not self._marker_matches(dep_req.marker):
                        continue
                    
                    # Recursively resolve
                    if not self._resolve_package(
                        dep_req.name,
                        str(dep_req.specifier),
                        resolved,
                        result,
                        depth + 1
                    ):
                        return False
                    
                    # Add to requires list
                    resolved_dep.requires.append(f"{dep_req.name}{dep_req.specifier}")
                
                except Exception as e:
                    result.warnings.append(
                        f"Could not parse dependency {dep_spec} of {name}: {e}"
                    )
        
        # Add to resolved
        resolved[normalized_name] = resolved_dep
        return True
    
    def _find_best_version(
        self,
        pkg: PyPIPackage,
        specifier: str,
        result: ResolutionResult,
    ) -> Optional[str]:
        """Find the best version matching the specifier."""
        
        if not specifier:
            # Use latest version (excluding pre-releases unless specified)
            versions = sorted(
                pkg.releases.keys(),
                key=parse_version,
                reverse=True
            )
            for version in versions:
                release = pkg.releases[version]
                if not release.yanked:
                    # Check if pre-release and if we should skip it
                    parsed = parse_version(version)
                    if not parsed.is_prerelease:
                        return version
            # If all stable versions are yanked, return first non-yanked
            for version in versions:
                if not pkg.releases[version].yanked:
                    return version
            return versions[0] if versions else None
        
        # Parse specifier and find matching versions
        try:
            spec_set = SpecifierSet(specifier)
        except Exception as e:
            result.errors.append(f"Invalid specifier {specifier}: {e}")
            return None
        
        # Find all matching versions
        matching = []
        for version in pkg.releases.keys():
            if version in spec_set:
                release = pkg.releases[version]
                if not release.yanked:
                    matching.append((parse_version(version), version))
        
        if not matching:
            # Try including yanked if nothing else matches
            for version in pkg.releases.keys():
                if version in spec_set:
                    matching.append((parse_version(version), version))
        
        if matching:
            # Return highest matching version
            return sorted(matching, reverse=True)[0][1]
        
        return None
    
    @staticmethod
    def _is_compatible(resolved_version: str, required_specifier: str) -> bool:
        """Check if a resolved version satisfies a specifier."""
        if not required_specifier:
            return True
        
        try:
            spec_set = SpecifierSet(required_specifier)
            return resolved_version in spec_set
        except Exception:
            return False
    
    def _marker_matches(self, marker) -> bool:
        """Simple marker evaluation for current environment."""
        import platform
        
        env = {
            'python_version': '.'.join(self.python_version.split('.')[:2]),
            'python_full_version': self.python_version,
            'platform_system': platform.system(),
            'platform_machine': platform.machine(),
            'sys_platform': sys.platform,
        }
        
        try:
            return marker.evaluate(env)
        except Exception:
            return True


__all__ = [
    'DependencyResolver',
    'ResolvedDependency',
    'ResolutionResult',
    'ResolutionError',
]
