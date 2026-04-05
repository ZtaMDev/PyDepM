# PyDepm Architecture & Design

Complete overview of PyDepm's architecture, design decisions, and internal systems.

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Components](#core-components)
3. [Dependency Resolution](#dependency-resolution)
4. [Lock File System](#lock-file-system)
5. [CLI Architecture](#cli-architecture)
6. [Data Flow](#data-flow)
7. [Performance Optimizations](#performance-optimizations)

---

## System Overview

PyDepm is designed as a modular, composable system with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer (main.py)                   │
│                  Commands & User Interface               │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│                   Core Services Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Resolver    │  │  Lock File   │  │  Config Mgmt  │  │
│  │              │  │  System      │  │               │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│                  Integration Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ PyPI Client  │  │ Environment  │  │ File System   │  │
│  │              │  │ Management   │  │               │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                              ↓
                    External APIs & Resources
                    (PyPI, pip, venv, etc.)
```

---

## Core Components

### 1. PyPI Client (`pypi.py`)

**Purpose:** Direct interaction with PyPI JSON API, removing pip dependency

**Key Classes:**

- **`PyPIPackage`** - Represents complete package metadata
  - Versions and releases
  - Dependencies
  - Distribution files with hashes
- **`PyPIClient`** - HTTP client for PyPI
  - Caches metadata locally (24h TTL)
  - Rate-limiting awareness
  - Error recovery
  - Handles markers and conditionals

**Features:**

- Direct JSON API access (no pip subprocess)
- Metadata caching with TTL
- Parallel requests support (ThreadPoolExecutor ready)
- Marker evaluation for conditional dependencies

**Example Usage:**

```python
from pydepm.core.pypi import PyPIClient

client = PyPIClient()
pkg = client.get_package("requests")
latest = pkg.get_latest_matching(">=2.28,<3.0")
deps = client.get_package_dependencies("requests", "2.31.0")
```

---

### 2. Dependency Resolver (`resolver.py`)

**Purpose:** Resolve dependency trees completely, without pip

**Algorithm:** Backtracking resolution with depth limiting

**Key Classes:**

- **`DependencyResolver`** - Main resolver engine
  - Backtracking algorithm
  - Version selection
  - Conflict detection
  - Circular dependency prevention

- **`ResolvedDependency`** - Represents a resolved dependency
  - Version, specifier, URL, hash
  - Transitive dependencies
  - Environment markers

- **`ResolutionResult`** - Result of resolution
  - Success/failure status
  - Resolved dependencies
  - Errors and warnings
  - Resolution timing

**Resolution Algorithm:**

```
resolve(requirements):
    resolved = {}
    for each requirement:
        if resolve_package(requirement, resolved):
            continue
        else:
            return FAIL
    return resolved

resolve_package(name, specifier, resolved):
    if already_resolved(name, specifier):
        return TRUE

    versions = find_matching_versions(name, specifier)
    for each version (best-first):
        if try_resolve_dependencies(name, version):
            resolved[name] = version
            return TRUE

    return FALSE
```

**Features:**

- Recursive dependency resolution
- Version selection (prefer latest non-pre-release)
- Yanked version handling
- Circular dependency detection
- Depth limiting (prevent infinite recursion)

**Example Usage:**

```python
from pydepm.core.resolver import DependencyResolver

resolver = DependencyResolver()
result = resolver.resolve([
    "requests>=2.28",
    "pytest>=7.0"
])

if result.success:
    for name, dep in result.resolved.items():
        print(f"{name}=={dep.version}")
else:
    for error in result.errors:
        print(f"ERROR: {error}")
```

---

### 3. Lock File System (`lock.py`)

**Purpose:** Generate, parse, and manage lock files for reproducibility

**Key Classes:**

- **`LockFile`** - TOML/JSON lock file handler
  - Serialization (TOML and JSON)
  - Validation
  - Dependency tree queries
  - Cycle detection

- **`LockFileMetadata`** - Lock file metadata
  - Version, creation timestamp
  - Python version
  - Platform info
  - pyproject.toml hash (for cache validation)

**Features:**

- TOML format (human-readable)
- JSON format (programmatic)
- Full validation with cycle detection
- Dependency tree visualization
- Metadata tracking and verification

**Example Usage:**

```python
from pydepm.core.lock import LockFile
from pydepm.core.resolver import DependencyResolver

# Create from resolution
resolver = DependencyResolver()
result = resolver.resolve(["requests>=2.28"])

lock = LockFile.from_resolution(
    result,
    pyproject_path=Path("pyproject.toml"),
    python_version="3.11"
)

# Save to disk
lock.save(Path("pydepm.lock"), format="toml")

# Load and validate
lock = LockFile.load(Path("pydepm.lock"))
is_valid, issues = lock.validate()

# Query dependencies
dep_tree = lock.get_dependency_tree("requests")
```

---

## Dependency Resolution

### Resolution Flow

```
User runs: pydep add requests

    ↓

CLI (main.py):
    - Parse requirement "requests"
    - Load current dependencies

    ↓

Resolver.resolve():
    1. Parse requirement specifier
    2. Query PyPI for package info
    3. Find best matching version
    4. Get dependencies of that version
    5. Recursively resolve each dependency
    6. Check for conflicts
    7. Build complete dependency tree

    ↓

LockFile.from_resolution():
    - Create lock file from resolution
    - Calculate hashes
    - Validate completeness

    ↓

Install:
    - Download packages (using URLs from lock)
    - Verify SHA256 hashes
    - Install to environment

    ↓

Update pyproject.toml:
    - Add/update dependency specification
    - Update lock file
```

### Version Selection Strategy

1. **Latest Non-Prerelease**

   ```
   Available: 1.0.0, 2.0.0rc1, 2.0.0, 2.1.0b1
   Selected: 2.0.0
   ```

2. **Respect Constraints**

   ```
   Constraint: >=2.0,<2.1
   Available: 1.9.0, 2.0.0, 2.0.5, 2.1.0
   Selected: 2.0.5
   ```

3. **Skip Yanked Versions**

   ```
   Constraint: >=2.0
   Available: 2.0.0 (yanked), 2.0.1, 2.0.2
   Selected: 2.0.1
   ```

4. **Fallback Strategies**
   - Include pre-releases if no stable version
   - Allow yanked if no other version available
   - Fail with clear error message

### Conflict Resolution

When conflicts occur:

```python
# Conflict Example:
# Requirement 1: "requests>=2.28,<3.0"
# Package A requires: "requests>=2.30"
# Package B requires: "requests<2.32"
# Result: 2.30.x matches all constraints

# Unresolvable conflict:
# Requirement 1: "django>=3.2,<4.0"
# Requirement 2: "django>=4.0,<5.0"
# Result: ERROR - Incompatible versions
```

---

## Lock File System

### Lock File Format Evolution

**Version 1.0 (Current)**

```toml
[metadata]
version = "1.0"
created_at = "2024-01-15T10:30:00Z"
python_version = "3.11"

[dependencies.package]
version = "1.0.0"
specifier = ">=1.0,<2.0"
sha256 = "..."
requires = ["dep1", "dep2"]
```

Future considerations:

- Binary format (msgpack) for speed
- Incremental updates
- Platform-specific locks

### Validation Pipeline

```
Lock file on disk
        ↓
Parse TOML/JSON
        ↓
Validate metadata:
    - Version number
    - Timestamp format
    - Python version
        ↓
Validate dependencies:
    - Required fields present
    - Valid version numbers
    - Valid SHA256 hashes
        ↓
Graph analysis:
    - Detect cycles
    - Verify transitive closure
    - Check marker consistency
        ↓
Result: Valid or Issues list
```

---

## CLI Architecture

### Command Structure

```
pydep
├── init          (Project initialization)
├── add/remove    (Dependency management)
├── list          (Show dependencies)
├── update        (Update dependencies)
├── install       (Install from lock)
├── lock          (Generate lock file)
├── build         (Build distributions)
├── publish       (Publish to PyPI)
├── audit         (Check for issues)
└── run           (Execute scripts)
```

### Command Implementation Pattern

```python
@app.command()
def add(
    packages: List[str],
    group: str = "dependencies",
    yes: bool = False,
    verbose: bool = False,
):
    """Add dependencies to project."""

    # 1. Load configuration
    config = Config.load()

    # 2. Validate inputs
    validated_packages = validate_package_specs(packages)

    # 3. Resolve dependencies
    resolver = DependencyResolver()
    result = resolver.resolve(validated_packages)

    if not result.success:
        console.print_error(result.errors)
        return

    # 4. Generate lock file
    lock = LockFile.from_resolution(result)

    # 5. Update configuration
    config.add_dependencies(validated_packages, group)
    config.save()
    lock.save()

    # 6. Install if requested
    if yes or confirm("Install now?"):
        install_dependencies(lock)

    console.print_success("Added dependencies")
```

---

## Data Flow

### Complete Add → Lock → Install Flow

```
┌──────────────────────────────────────────────────────┐
│ 1. User Input: pydep add requests pytest            │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 2. CLI Parsing (main.py)                            │
│    - Parse command and arguments                    │
│    - Load current pyproject.toml                    │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 3. Dependency Resolution (resolver.py)              │
│    - Fetch package metadata from PyPI               │
│    - For each package:                              │
│      ├─ Find best matching version                  │
│      ├─ Get its dependencies                        │
│      └─ Recursively resolve those                   │
│    - Build complete tree                           │
│    - Detect conflicts                              │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 4. Lock File Generation (lock.py)                   │
│    - Create LockFile from resolved deps             │
│    - Add metadata (timestamp, py version)           │
│    - Record URLs and hashes                         │
│    - Validate completeness                         │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 5. Configuration Update (config.py)                 │
│    - Update pyproject.toml                          │
│    - Add dependencies section                       │
│    - Preserve formatting and comments              │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 6. Installation (envs.py)                           │
│    - Download packages using URLs from lock         │
│    - Verify SHA256 hashes                           │
│    - Extract and install to venv                    │
└─────────────────────────────────┬────────────────────┘

┌──────────────────────────────────────────────────────┐
│ 7. User Feedback                                     │
│    - Success message with installed packages        │
│    - Generation time                                │
│    - Lock file summary                              │
└──────────────────────────────────────────────────────┘
```

---

## Performance Optimizations

### 1. Caching Strategy

**PyPI Metadata Cache:**

- Directory: `~/.cache/pydepm/pypi/`
- Format: JSON
- TTL: 24 hours
- Size: Typically 5-50MB per project

```python
# Cache hit
pydep add requests  # 100ms (cached)

# Cache miss
pydep add requests  # 5000ms (network)
```

**Lock File Cache:**

- Cache: Don't regenerate if pyproject.toml unchanged
- Validation: Compare pyproject hash

### 2. Parallel Resolution

Future optimization: Resolve multiple packages in parallel

```python
# Current (sequential):
for package in packages:
    resolve(package)

# Future (parallel):
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(resolve, p) for p in packages]
    results = [f.result() for f in futures]
```

### 3. Binary Format Option

Future: msgpack serialization for lock files

```
Current TOML: ~2-5 seconds to parse 1000 packages
Binary msgpack: ~100-500ms

Trade-off: Human-readability vs speed
```

### 4. Lazy Loading

- Load only required metadata
- Don't fetch all package versions upfront
- Fetch dependency info only when needed

---

## Error Handling

### Resolution Errors

```python
# Package not found
ERROR: Package 'requests-typo' not found on PyPI
    Did you mean: 'requests'?

# Version conflict
ERROR: Incompatible version constraints:
    - pytest requires: 'pluggy<2.0'
    - Other packages require: 'pluggy>=2.0'

# Circular dependency
ERROR: Circular dependency detected:
    - package-a depends on package-b
    - package-b depends on package-a

# Yanked version
WARNING: Version 2.0.0 is yanked by package author
```

### Recovery Mechanisms

1. **Fallback versions** - Try next compatible version
2. **User guidance** - Suggest alternatives
3. **Detailed errors** - Show dependency chain leading to error
4. **Repair tools** - `pydep lock --repair`

---

## Testing

### Test Coverage Areas

1. **Unit Tests**
   - Version specifier parsing
   - Marker evaluation
   - TOML serialization
   - Hash verification

2. **Integration Tests**
   - Full resolution workflow
   - Lock file generation
   - CLI commands
   - PyPI integration (with mocking)

3. **End-to-End Tests**
   - Create project
   - Add dependencies
   - Install
   - Run scripts
   - Build and publish

---

## Security Considerations

1. **Hash Verification**
   - SHA256 of all downloaded packages
   - Prevent tampering or corruption
   - Fail fast if mismatch

2. **Marker Evaluation**
   - Prevent code injection
   - Safe serialization/deserialization

3. **API Token Security**
   - Store in `.env` (excluded from git)
   - Never commit tokens
   - Support environment variables

4. **Dependency Auditing**
   - Check for known CVEs
   - Security advisories integration
   - Automated notifications

---

## Future Enhancements

1. **Binary Lock Format** - msgpack for speed
2. **Parallel Resolution** - Thread/async resolution
3. **Incremental Updates** - Only update changed deps
4. **Local Index** - Optional private PyPI support
5. **Workspace Support** - Monorepo management
6. **Plugin System** - Extend functionality
7. **Offline Mode** - Cache-only operation
8. **Version Presets** - Popular version combinations

---

## Performance Metrics

Current performance (typical):

- **First resolution** (no cache): 5-15 seconds
- **Cached resolution**: 100-500ms
- **Install from lock**: 2-5 seconds
- **CLI startup**: 50-100ms
- **Lock parsing**: 10-100ms (TOML)

Goals for 1.0+:

- First resolution: 2-5 seconds (parallel)
- Cached: < 100ms
- Install: 1-2 seconds
- CLI startup: < 50ms
- Lock parsing: < 10ms (binary format)

---

## Further Reading

- [CLI Reference](CLI_REFERENCE.md)
- [Configuration Guide](CONFIGURATION.md)
- [Lock File Format](LOCK_FILE_FORMAT.md)
