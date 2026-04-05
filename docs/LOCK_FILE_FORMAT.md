# Lock File Format

Complete specification of the PyDepm lock file format.

## Overview

Lock files ensure reproducible builds by recording the exact versions and hashes of all resolved dependencies. PyDepm supports both TOML (human-readable) and JSON (compatible) formats.

- **TOML Format:** `pydepm.lock` (recommended)
- **JSON Format:** `pydepm.lock.json` (alternative)

---

## TOML Format Specification

### File Structure

```toml
[metadata]
version = "1.0"
created_at = "2024-01-15T10:30:00Z"
created_by = "pydepm"
python_version = "3.11"
platform = "win32"
pyproject_hash = "abc123def456..."

[dependencies.package_name]
version = "1.0.0"
specifier = ">=1.0,<2.0"
url = "https://files.pythonhosted.org/..."
sha256 = "abc123..."
requires = ["dependency1>=1.0", "dependency2"]
markers = "python_version >= '3.11'"

[dependencies.package_name2]
# ... more dependencies
```

### Metadata Section

#### `[metadata]`

**Required Fields:**

| Field            | Type   | Description                                    |
| ---------------- | ------ | ---------------------------------------------- |
| `version`        | string | Lock file format version (e.g., "1.0")         |
| `created_at`     | string | ISO 8601 timestamp when lock was created       |
| `python_version` | string | Python version the lock was created for        |
| `created_by`     | string | Tool that created the lock (default: "pydepm") |

**Optional Fields:**

| Field            | Type   | Description                                            |
| ---------------- | ------ | ------------------------------------------------------ |
| `platform`       | string | Platform (e.g., "linux", "darwin", "win32")            |
| `pyproject_hash` | string | SHA256 hash of `pyproject.toml` (for cache validation) |
| `machine`        | string | CPU architecture (e.g., "x86_64", "aarch64")           |

**Example:**

```toml
[metadata]
version = "1.0"
created_at = "2024-01-15T10:30:45Z"
created_by = "pydepm"
python_version = "3.11"
platform = "win32"
pyproject_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

---

### Dependencies Section

#### `[dependencies.PACKAGE_NAME]`

Each dependency is a table with the package name (normalized: lowercase, hyphens instead of underscores).

**Required Fields:**

| Field       | Type   | Description                                     |
| ----------- | ------ | ----------------------------------------------- |
| `version`   | string | Exact resolved version (e.g., "1.0.0")          |
| `specifier` | string | Original version specifier (e.g., ">=1.0,<2.0") |

**Optional Fields:**

| Field       | Type    | Description                                                   |
| ----------- | ------- | ------------------------------------------------------------- |
| `url`       | string  | URL to download the package                                   |
| `sha256`    | string  | SHA256 hash of package file for verification                  |
| `requires`  | array   | List of dependencies this package requires                    |
| `markers`   | string  | Environment markers (e.g., "python_version >= '3.11'")        |
| `extras`    | array   | Python package extras installed (e.g., ["security", "async"]) |
| `yanked`    | boolean | Whether this version is yanked on PyPI                        |
| `wheelname` | string  | Wheel filename (if available)                                 |
| `editable`  | boolean | Whether this is an editable/local dependency                  |
| `git`       | table   | Git repository info (if from git)                             |

**Example - Simple Dependency:**

```toml
[dependencies.requests]
version = "2.31.0"
specifier = ">=2.28,<3.0"
url = "https://files.pythonhosted.org/packages/requests-2.31.0-py3-none-any.whl"
sha256 = "942c5a758f98d790eaa1694a3651cff7ee0044e"
requires = ["charset-encoding>=2.0.4", "urllib3>=1.21.1,<3"]
```

**Example - Conditional Dependency:**

```toml
[dependencies.tomli]
version = "2.0.1"
specifier = ">=2.0"
url = "https://files.pythonhosted.org/packages/tomli-2.0.1-py3-none-any.whl"
sha256 = "de526c12914f0c550d15924c62d72abc48d6fe7364aa87328337a31007fe8a4f"
requires = []
markers = "python_version < '3.11'"
```

**Example - Git Dependency:**

```toml
[dependencies.mylib]
version = "0.1.0+git.abc1234"
specifier = "@main"
git = { url = "https://github.com/user/mylib.git", ref = "main" }
requires = ["requests>=2.28"]
```

**Example - Editable/Local Dependency:**

```toml
[dependencies.local-lib]
version = "0.1.0"
specifier = "file:../local-lib"
editable = true
requires = []
```

---

### Resolved Dependencies Example

```toml
[metadata]
version = "1.0"
created_at = "2024-01-15T10:30:45Z"
created_by = "pydepm"
python_version = "3.11"

[dependencies.requests]
version = "2.31.0"
specifier = ">=2.28,<3.0"
url = "https://files.pythonhosted.org/packages/..."
sha256 = "abc123..."
requires = [
    "charset-encoding>=2.0.4",
    "idna>=2.5,<4",
    "urllib3>=1.21.1,<3",
    "certifi>=2017.4.17",
]

[dependencies.charset-encoding]
version = "2.1.0"
specifier = ">=2.0.4"
url = "https://files.pythonhosted.org/packages/..."
sha256 = "def456..."
requires = []

[dependencies.urllib3]
version = "2.1.0"
specifier = ">=1.21.1,<3"
url = "https://files.pythonhosted.org/packages/..."
sha256 = "ghi789..."
requires = ["pysocks"]
markers = "python_version < '3.10' or sys_platform != 'win32'"

[dependencies.pysocks]
version = "1.7.1"
specifier = ""
url = "https://files.pythonhosted.org/packages/..."
sha256 = "jkl012..."
requires = []
markers = "python_version < '3.10' or sys_platform != 'win32'"

[dependencies.certifi]
version = "2024.2.2"
specifier = ">=2017.4.17"
url = "https://files.pythonhosted.org/packages/..."
sha256 = "mno345..."
requires = []

[dependencies.idna]
version = "3.6"
specifier = ">=2.5,<4"
url = "https://files.pythonhosted.org/packages/..."
sha256 = "pqr678..."
requires = []
```

---

## JSON Format Specification

For programmatic use, equivalent JSON format:

```json
{
  "metadata": {
    "version": "1.0",
    "created_at": "2024-01-15T10:30:45Z",
    "created_by": "pydepm",
    "python_version": "3.11",
    "platform": "win32",
    "pyproject_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "dependencies": {
    "requests": {
      "name": "requests",
      "version": "2.31.0",
      "specifier": ">=2.28,<3.0",
      "url": "https://files.pythonhosted.org/packages/requests-2.31.0-py3-none-any.whl",
      "sha256": "abc123...",
      "requires": ["charset-encoding>=2.0.4", "urllib3>=1.21.1,<3"],
      "markers": null,
      "extras": []
    }
  },
  "warnings": [],
  "errors": []
}
```

---

## Generation and Usage

### Generate Lock File

```bash
# Create new lock file
pydep lock

# Include development dependencies
pydep lock --include-dev (-D)

# Lock specific dependency groups
pydep lock --groups test,docs (-G)

# Use global Python environment
pydep lock --global (-g)

# Combine options
pydep lock --include-dev --groups test
```

### Inspect Lock File

```bash
# View lock file
cat pydepm.lock

# Check dependencies
pydep list -t        # Show dependency tree
pydep audit          # Check for conflicts
```

### Install from Lock File

```bash
# Install exact versions from lock
pydep install

# Sync environment to match lock
pydep sync
```

### Update Lock File

```bash
# Update a specific dependency
pydep update requests>=2.28

# Lock file is automatically updated
pydep lock
```

---

## Validation Rules

A valid lock file must satisfy:

1. **Metadata Validation**
   - `version` field present and valid
   - `created_at` is valid ISO 8601 timestamp
   - `python_version` is a valid Python version

2. **Dependency Validation**
   - All dependencies have required fields (`version`, `specifier`)
   - Package names are normalized (lowercase, hyphens only)
   - Versions are valid semantic versions
   - SHA256 hashes are valid hex strings

3. **Completeness Validation**
   - All transitive dependencies present
   - No missing required packages
   - All `requires` entries exist in dependencies

4. **Graph Validation**
   - No circular dependencies
   - All requirement specifiers are satisfiable
   - Markers don't create impossible constraints

### Validation Example

```bash
$ pydep audit
Dependency Audit
✓ Metadata valid
✓ All dependencies installed
✓ No circular dependencies
✓ No conflicts detected
✓ Ready to develop
```

---

## Caching and Performance

Lock files enable:

1. **Reproducible Installs**
   - Same exact versions every time
   - Identical across machines

2. **Faster Installation**
   - No need to resolve dependencies
   - Direct download of pinned versions

3. **Offline Installation**
   - Can use pre-downloaded wheels
   - Lock contains full URLs and hashes

4. **Security**
   - SHA256 hashes verify file integrity
   - Detect tampering or corruption

---

## Migration and Compatibility

### From Poetry (poetry.lock)

```bash
# Convert Poetry lock to PyDepm format
pydep migrate poetry --input poetry.lock
```

Incompatibilities:

- Poetry uses slightly different version constraints
- Some metadata may not transfer exactly

### Backward Compatibility

- Format version `1.0` is stable
- Future versions indicated by metadata version
- PyDepm will attempt to read older formats

---

## Lock File in Version Control

### Recommended

Include lock file in version control:

```bash
# Add to git
git add pydepm.lock
git commit -m "Update dependencies"
```

**Benefits:**

- Identical reproduction across team
- CI/CD consistency
- Better security auditing

### .gitignore Note

DO NOT ignore lock file:

```bash
# ❌ DON'T do this:
# pydepm.lock

# ✓ DO include lock file in git:
git add pydepm.lock
```

---

## Troubleshooting

### "Lock file is outdated"

```bash
# Regenerate
pydep lock

# Reinstall from lock
pydep sync
```

### "Lock validation issues"

```bash
# Audit dependencies for conflicts
pydep audit

# Reinstall clean environment
pydep install --force
```

### "Hash mismatch during install"

```bash
# Verify dependencies
pydep audit --security

# Regenerate lock and reinstall
pydep lock
pydep sync --force
```

---

## Performance Notes

Lock files with:

- **< 50 packages:** Negligible performance difference
- **50-200 packages:** 2-5x faster installation
- **> 200 packages:** 10-50x faster installation

Typical install times:

- First install (no lock): 30-60s
- Install with lock: 5-10s (just download and unpack)

---

## Further Reading

- [CLI Reference - Lock Commands](CLI_REFERENCE.md#4-lock-file-management)
- [Configuration Guide](CONFIGURATION.md)
- [Dependency Resolution Details](RESOLVER.md)
