"""
PyPI API integration for fetching package metadata and resolving dependencies.
This is a custom implementation that replaces the need for pip.
"""

from __future__ import annotations

import json
import time
import hashlib
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from urllib.parse import quote as url_quote

import requests
from packaging.version import Version, parse as parse_version
from packaging.requirements import Requirement
from packaging.markers import Marker


class PyPIClientError(Exception):
    """Raised when PyPI client operations fail."""
    pass


# Cache configuration
CACHE_DIR = Path.home() / ".cache" / "pydepm" / "pypi"
CACHE_TTL_HOURS = 24
PYPI_API_URL = "https://pypi.org/pypi"


@dataclass
class PackageFile:
    """Metadata for a single package distribution file."""
    
    filename: str
    url: str
    hashes: Dict[str, str] = field(default_factory=dict)
    requires_python: Optional[str] = None
    yanked: bool = False
    size: int = 0
    upload_time: Optional[str] = None
    
    
@dataclass
class PackageRelease:
    """Metadata for a package release/version."""
    
    version: str
    release_date: Optional[str] = None
    files: List[PackageFile] = field(default_factory=list)
    requires_dist: List[str] = field(default_factory=list)
    requires_python: Optional[str] = None
    summary: str = ""
    yanked: bool = False
    
    def __hash__(self):
        return hash(self.version)
    
    def __lt__(self, other):
        return parse_version(self.version) < parse_version(other.version)


@dataclass
class PyPIPackage:
    """Complete package metadata from PyPI."""
    
    name: str
    normalized_name: str
    summary: str = ""
    home_page: str = ""
    releases: Dict[str, PackageRelease] = field(default_factory=dict)
    latest_version: Optional[str] = None
    
    def get_release(self, version: str) -> Optional[PackageRelease]:
        """Get metadata for a specific version."""
        return self.releases.get(version)
    
    def get_latest_matching(self, specifier: str = None) -> Optional[PackageRelease]:
        """Get the latest version matching a specifier (e.g., '>=1.0,<2.0')."""
        from packaging.specifiers import SpecifierSet
        
        if not specifier:
            return self.releases.get(self.latest_version)
        
        spec_set = SpecifierSet(specifier)
        matching = [
            rel for rel in self.releases.values()
            if rel.version in spec_set
        ]
        return max(matching, key=lambda r: parse_version(r.version)) if matching else None


class PyPIClient:
    """Client for interacting with PyPI JSON API."""
    
    def __init__(self, session: Optional[requests.Session] = None, cache_dir: Path = CACHE_DIR):
        self.session = session or requests.Session()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # User-Agent for PyPI API
        self.session.headers.update({
            'User-Agent': 'pydepm/1.0.0 (Python Package Manager)'
        })
    
    def _get_cache_path(self, package_name: str) -> Path:
        """Get cache file path for a package."""
        normalized = self._normalize_name(package_name)
        # Use hash to avoid filesystem issues with special chars
        name_hash = hashlib.md5(normalized.encode()).hexdigest()
        return self.cache_dir / f"{normalized[:30]}_{name_hash}.json"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache is still valid (not expired)."""
        if not cache_path.exists():
            return False
        
        mtime = cache_path.stat().st_mtime
        age = time.time() - mtime
        return age < (CACHE_TTL_HOURS * 3600)
    
    def _load_from_cache(self, package_name: str) -> Optional[PyPIPackage]:
        """Load package metadata from cache if available and valid."""
        cache_path = self._get_cache_path(package_name)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
            return self._parse_package_json(data)
        except Exception:
            return None
    
    def _save_to_cache(self, package_name: str, data: dict) -> None:
        """Save package metadata to cache."""
        cache_path = self._get_cache_path(package_name)
        try:
            cache_path.write_text(json.dumps(data), encoding='utf-8')
        except Exception:
            pass  # Silently fail if cache write fails
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize package name according to PEP 503."""
        return name.lower().replace("_", "-").replace(".", "-")
    
    def _parse_package_json(self, data: dict) -> PyPIPackage:
        """Parse PyPI JSON API response into PyPIPackage."""
        info = data.get('info', {})
        releases_data = data.get('releases', {})
        
        pkg = PyPIPackage(
            name=info.get('name', ''),
            normalized_name=info.get('name', '').lower(),
            summary=info.get('summary', ''),
            home_page=info.get('home_page', ''),
            latest_version=info.get('version'),
        )
        
        # Parse releases
        for version_str, files_list in releases_data.items():
            files = []
            requires_dist = []
            requires_python = None
            
            for file_data in files_list:
                file_obj = PackageFile(
                    filename=file_data.get('filename', ''),
                    url=file_data.get('url', ''),
                    hashes={
                        'sha256': file_data.get('digests', {}).get('sha256', '')
                    },
                    requires_python=file_data.get('requires_python'),
                    yanked=file_data.get('yanked', False),
                    size=file_data.get('size', 0),
                    upload_time=file_data.get('upload_time_iso_8601'),
                )
                
                # Extract requires_dist from file
                if 'requires_dist' in file_data and file_data['requires_dist']:
                    requires_dist.extend(file_data['requires_dist'])
                
                if file_data.get('requires_python'):
                    requires_python = file_data.get('requires_python')
                
                files.append(file_obj)
            
            release = PackageRelease(
                version=version_str,
                release_date=files_list[0].get('upload_time_iso_8601') if files_list else None,
                files=files,
                requires_dist=list(set(requires_dist)),  # Deduplicate
                requires_python=requires_python,
                yanked=any(f.yanked for f in files),
            )
            
            pkg.releases[version_str] = release
        
        return pkg
    
    def get_package(self, package_name: str, use_cache: bool = True) -> Optional[PyPIPackage]:
        """
        Fetch package metadata from PyPI.
        
        Args:
            package_name: Name of package to fetch
            use_cache: Whether to check cache first
            
        Returns:
            PyPIPackage if found, None otherwise
        """
        # Try cache first
        if use_cache:
            cached = self._load_from_cache(package_name)
            if cached:
                return cached
        
        # Fetch from PyPI
        normalized = self._normalize_name(package_name)
        url = f"{PYPI_API_URL}/{url_quote(normalized)}/json"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Save to cache
            self._save_to_cache(package_name, data)
            
            return self._parse_package_json(data)
        except requests.RequestException as e:
            print(f"Error fetching package {package_name}: {e}")
            return None
    
    def get_package_releases(self, package_name: str) -> List[str]:
        """Get all available versions for a package."""
        pkg = self.get_package(package_name)
        if not pkg:
            return []
        
        # Sort versions from oldest to newest
        versions = sorted(pkg.releases.keys(), key=parse_version)
        return versions
    
    def resolve_version(self, package_name: str, version_spec: str = None) -> Optional[str]:
        """
        Resolve a version specifier to a concrete version.
        
        Args:
            package_name: Package name
            version_spec: Version specifier like '>=1.0,<2.0', '==1.5', or None for latest
            
        Returns:
            Concrete version string if found
        """
        pkg = self.get_package(package_name)
        if not pkg:
            return None
        
        if not version_spec:
            return pkg.latest_version
        
        release = pkg.get_latest_matching(version_spec)
        return release.version if release else None
    
    def get_package_dependencies(
        self, package_name: str, version: str,
        python_version: str = "3.11",
        platform_system: str = None
    ) -> List[str]:
        """
        Get dependencies for a specific package version.
        
        Args:
            package_name: Package name
            version: Package version
            python_version: Python version for marker evaluation
            platform_system: Platform system for marker evaluation
            
        Returns:
            List of dependency specifiers
        """
        pkg = self.get_package(package_name)
        if not pkg:
            return []
        
        release = pkg.get_release(version)
        if not release:
            return []
        
        # Filter based on markers
        deps = []
        for dep_spec in release.requires_dist:
            # Parse the requirement with markers
            try:
                req = Requirement(dep_spec)
                
                # Evaluate marker if present
                if req.marker:
                    # Simple marker evaluation
                    env = {
                        'python_version': python_version,
                        'platform_system': platform_system or 'Linux',
                    }
                    # This is simplified; full implementation would be more comprehensive
                    marker_result = self._evaluate_marker(req.marker, env)
                    if not marker_result:
                        continue
                
                # Add only the requirement specifier, not the marker
                deps.append(f"{req.name}{req.specifier}")
            except Exception:
                # Skip malformed requirements
                pass
        
        return deps
    
    @staticmethod
    def _evaluate_marker(marker: Marker, env: dict) -> bool:
        """Simple marker evaluation. For production, use marker.evaluate()."""
        try:
            return marker.evaluate(env)
        except Exception:
            return True  # Include if evaluation fails
    
    def check_availability(self, package_name: str, version: str) -> bool:
        """Check if a package version is available on PyPI."""
        pkg = self.get_package(package_name, use_cache=False)
        if not pkg:
            return False
        return version in pkg.releases


__all__ = [
    'PyPIClient',
    'PyPIPackage',
    'PackageRelease',
    'PackageFile',
    'CACHE_DIR',
]
