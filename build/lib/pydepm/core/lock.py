"""
Lock file management - generates, parses, and validates .lock files.
Supports both TOML and binary formats for flexibility and performance.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import hashlib

import tomlkit
from .resolver import ResolvedDependency, ResolutionResult


@dataclass
class LockFileMetadata:
    """Metadata for lock file."""
    
    version: str = "1.0"
    created_at: str = ""
    created_by: str = "pydepm"
    python_version: str = "3.11"
    platform: str = ""
    pyproject_hash: str = ""  # Hash of pyproject.toml for cache busting


class LockFile:
    """
    Manages .lock files in TOML format.
    Format:
    
    [metadata]
    version = "1.0"
    created_at = "2024-01-01T00:00:00Z"
    python_version = "3.11"
    
    [dependencies.package_name]
    version = "1.0.0"
    specifier = ">=1.0,<2.0"
    url = "https://..."
    sha256 = "..."
    requires = ["dep1>=1.0", "dep2"]
    """
    
    LOCK_FILENAME = "pydepm.lock"
    
    @staticmethod
    def from_resolution(
        resolution: ResolutionResult,
        pyproject_path: Optional[Path] = None,
        python_version: str = "3.11",
    ) -> LockFile:
        """Create lock file from a resolution result."""
        
        lock = LockFile()
        
        # Set metadata
        lock.metadata.created_at = datetime.utcnow().isoformat() + "Z"
        lock.metadata.python_version = python_version
        
        # Calculate pyproject.toml hash if provided
        if pyproject_path and pyproject_path.exists():
            content = pyproject_path.read_bytes()
            lock.metadata.pyproject_hash = hashlib.sha256(content).hexdigest()
        
        # Add resolved dependencies
        for name, dep in resolution.resolved.items():
            lock.dependencies[name] = dep
        
        # Store warnings and errors
        lock.warnings.extend(resolution.warnings)
        if resolution.errors:
            lock.errors.extend(resolution.errors)
        
        return lock
    
    def __init__(self):
        self.metadata = LockFileMetadata()
        self.dependencies: Dict[str, ResolvedDependency] = {}
        self.warnings: List[str] = []
        self.errors: List[str] = []
    
    def add_dependency(self, dep: ResolvedDependency) -> None:
        """Add a resolved dependency to the lock file."""
        normalized = dep.name.lower().replace("_", "-")
        self.dependencies[normalized] = dep
    
    def get_dependency(self, name: str) -> Optional[ResolvedDependency]:
        """Get a dependency from the lock file."""
        normalized = name.lower().replace("_", "-")
        return self.dependencies.get(normalized)
    
    def to_toml(self) -> str:
        """Serialize lock file to TOML format."""
        
        doc = tomlkit.document()
        
        # Add metadata section
        meta_dict = {
            'version': self.metadata.version,
            'created_at': self.metadata.created_at,
            'created_by': self.metadata.created_by,
            'python_version': self.metadata.python_version,
        }
        if self.metadata.platform:
            meta_dict['platform'] = self.metadata.platform
        if self.metadata.pyproject_hash:
            meta_dict['pyproject_hash'] = self.metadata.pyproject_hash
        
        doc['metadata'] = meta_dict
        
        # Add dependencies section
        deps_table = tomlkit.table()
        
        for name, dep in sorted(self.dependencies.items()):
            dep_table = tomlkit.table()
            dep_table['version'] = dep.version
            dep_table['specifier'] = dep.specifier
            
            if dep.url:
                dep_table['url'] = dep.url
            if dep.sha256:
                dep_table['sha256'] = dep.sha256
            if dep.markers:
                dep_table['markers'] = dep.markers
            
            if dep.requires:
                dep_table['requires'] = dep.requires
            
            deps_table[name] = dep_table
        
        doc['dependencies'] = deps_table
        
        # Add any warnings
        if self.warnings:
            doc['warnings'] = self.warnings
        
        return tomlkit.dumps(doc)
    
    def to_json(self) -> str:
        """Serialize lock file to JSON format (for binary mode compatibility)."""
        
        data = {
            'metadata': asdict(self.metadata),
            'dependencies': {},
            'warnings': self.warnings,
            'errors': self.errors,
        }
        
        for name, dep in self.dependencies.items():
            data['dependencies'][name] = {
                'name': dep.name,
                'version': dep.version,
                'specifier': dep.specifier,
                'url': dep.url,
                'sha256': dep.sha256,
                'requires': dep.requires,
                'markers': dep.markers,
            }
        
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_toml(cls, toml_content: str) -> LockFile:
        """Parse lock file from TOML content."""
        
        doc = tomlkit.parse(toml_content)
        lock = cls()
        
        # Parse metadata
        if 'metadata' in doc:
            meta = doc['metadata']
            lock.metadata.version = meta.get('version', '1.0')
            lock.metadata.created_at = meta.get('created_at', '')
            lock.metadata.created_by = meta.get('created_by', 'pydepm')
            lock.metadata.python_version = meta.get('python_version', '3.11')
            lock.metadata.platform = meta.get('platform', '')
            lock.metadata.pyproject_hash = meta.get('pyproject_hash', '')
        
        # Parse dependencies
        if 'dependencies' in doc:
            for name, dep_data in doc['dependencies'].items():
                dep = ResolvedDependency(
                    name=dep_data.get('name', name),
                    version=dep_data.get('version', ''),
                    specifier=dep_data.get('specifier', ''),
                    url=dep_data.get('url', ''),
                    sha256=dep_data.get('sha256', ''),
                    requires=dep_data.get('requires', []),
                    markers=dep_data.get('markers'),
                )
                lock.add_dependency(dep)
        
        # Parse warnings
        if 'warnings' in doc:
            lock.warnings = list(doc['warnings'])
        
        return lock
    
    @classmethod
    def from_json(cls, json_content: str) -> LockFile:
        """Parse lock file from JSON content."""
        
        data = json.loads(json_content)
        lock = cls()
        
        # Parse metadata
        if 'metadata' in data:
            meta = data['metadata']
            lock.metadata.version = meta.get('version', '1.0')
            lock.metadata.created_at = meta.get('created_at', '')
            lock.metadata.created_by = meta.get('created_by', 'pydepm')
            lock.metadata.python_version = meta.get('python_version', '3.11')
            lock.metadata.platform = meta.get('platform', '')
            lock.metadata.pyproject_hash = meta.get('pyproject_hash', '')
        
        # Parse dependencies
        if 'dependencies' in data:
            for name, dep_data in data['dependencies'].items():
                dep = ResolvedDependency(
                    name=dep_data.get('name', name),
                    version=dep_data.get('version', ''),
                    specifier=dep_data.get('specifier', ''),
                    url=dep_data.get('url', ''),
                    sha256=dep_data.get('sha256', ''),
                    requires=dep_data.get('requires', []),
                    markers=dep_data.get('markers'),
                )
                lock.add_dependency(dep)
        
        # Parse metadata
        lock.warnings = data.get('warnings', [])
        lock.errors = data.get('errors', [])
        
        return lock
    
    def save(self, path: Path, format: str = 'toml') -> None:
        """Save lock file to disk."""
        
        content = self.to_toml() if format == 'toml' else self.to_json()
        path.write_text(content, encoding='utf-8')
    
    @classmethod
    def load(cls, path: Path, format: str = 'toml') -> LockFile:
        """Load lock file from disk."""
        
        if not path.exists():
            raise FileNotFoundError(f"Lock file not found: {path}")
        
        content = path.read_text(encoding='utf-8')
        
        return cls.from_toml(content) if format == 'toml' else cls.from_json(content)
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate lock file integrity and consistency.
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check metadata
        if not self.metadata.created_at:
            issues.append("Missing created_at in metadata")
        
        if not self.metadata.python_version:
            issues.append("Missing python_version in metadata")
        
        # Check for circular dependencies
        checked = set()
        for name, dep in self.dependencies.items():
            if self._has_cycle(name, set(), checked):
                issues.append(f"Circular dependency detected: {name}")
        
        # Check for missing transitive dependencies
        all_names = set(self.dependencies.keys())
        for name, dep in self.dependencies.items():
            for req in dep.requires:
                # Extract package name from requirement spec
                req_name = req.split('>=')[0].split('<')[0].split('=')[0].split('!')[0].strip()
                req_name_normalized = req_name.lower().replace('_', '-')
                
                if req_name_normalized not in all_names:
                    issues.append(
                        f"Missing transitive dependency: {name} requires {req_name} "
                        f"but it's not in the lock file"
                    )
        
        return len(issues) == 0, issues
    
    def _has_cycle(self, node: str, visiting: set, visited: set) -> bool:
        """Check for cycles in dependency graph."""
        
        if node in visited:
            return False
        
        if node in visiting:
            return True
        
        visiting.add(node)
        
        dep = self.dependencies.get(node)
        if dep:
            for req in dep.requires:
                req_name = req.split('>=')[0].split('<')[0].split('=')[0].split('!')[0].strip()
                req_name_normalized = req_name.lower().replace('_', '-')
                
                if self._has_cycle(req_name_normalized, visiting, visited):
                    return True
        
        visiting.remove(node)
        visited.add(node)
        return False
    
    def get_dependency_tree(self, package_name: str, indent: int = 0) -> str:
        """Get a tree view of dependencies for a package."""
        
        normalized = package_name.lower().replace('_', '-')
        dep = self.dependencies.get(normalized)
        
        if not dep:
            return f"{package_name} not found in lock file"
        
        lines = [f"{' ' * indent}{dep.name}=={dep.version}"]
        
        for req in dep.requires:
            req_name = req.split('>=')[0].split('<')[0].split('=')[0].split('!')[0].strip()
            sub_tree = self.get_dependency_tree(req_name, indent + 2)
            lines.append(sub_tree)
        
        return '\n'.join(lines)


__all__ = [
    'LockFile',
    'LockFileMetadata',
]
