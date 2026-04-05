<h1 align="center">PyDepM</h1>

<p align="center">
  <img src="./pydepm.svg" alt="PydepM Logo" width="300" />
</p>

<p align="center">
  <strong>Simple, fast, and modern Python project manager.</strong><br/>
  Initialize projects, manage dependencies, build distributions, and publish to PyPI—all from one command.
</p>

<p align="center">
  <a href="https://pypi.org/project/pydepm/">
    <img src="https://img.shields.io/pypi/v/pydepm.svg" alt="PyPI version" />
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" />
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+" />
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/status-beta-orange.svg" alt="Status: Beta" />
  </a>
</p>

---

## Features

- **Initialize Projects** — Create modules or apps with automatic environment setup
- **Manage Dependencies** — Add, remove, update, with dev and optional groups
- **Lock Files** — Auto-generate `pydepm.lock` for reproducible builds (TOML format)
- **Install** — Install dependencies, dev-dependencies, and optional groups
- **Exact Versions** — Automatically save exact versions (e.g., `==1.2.3`) for reproducibility
- **Smart Updates** — Check for outdated packages before updating, batch update with confirmation
- **Build** — Create wheels, sdist, or PyInstaller apps
- **Audit** — Check for dependency issues and security vulnerabilities
- **Publish** — Upload to PyPI or TestPyPI with automated token management
- **Custom Scripts** — Define and run scripts from `pyproject.toml`
- **Beautiful CLI** — Progress bars, colors, interactive prompts, versioning

---

## 🚀 Quick Start

### 1. Install

```bash
pip install pydepm
```

Check version:

```bash
pydep -v
# or
pydep --version
```

### 2. Create a Project

```bash
pydep init my_project --type module --env venv
cd my_project
```

### 3. Add Dependencies

```bash
pydep add requests              # Add to project
pydep add -D pytest             # Add to dev (-D = --save-dev)
pydep add -G docs sphinx        # Add to group (-G = --group)
pydep add -F unknown-pkg        # Force add even if not found (skip checks)
```

Each `add` command:

- Shows progress for each package
- Automatically detects and saves exact versions
- Updates `pydepm.lock` with installed versions
- With `-F/--force`: Ignores if already declared, forces update

### 4. Remove Dependencies

```bash
pydep remove requests           # Remove from project
pydep remove -D pytest          # Remove from dev
pydep remove -F old-package     # Force remove even if not found
```

With `-F/--force`: Attempts uninstall even if not in pyproject.toml

### 5. Install & Lock

```bash
pydep install                   # Install all dependencies
# Automatically updates pydepm.lock with exact versions
```

### 6. Update Dependencies

**Update single dependency:**

```bash
pydep update requests           # Updates to latest, saves exact version
pydep update -F requests>=2.0   # Force update, adds if not present
```

**Update all outdated dependencies:**

```bash
pydep update                    # Checks for outdated, shows list, asks for confirmation
pydep update -y                 # Skip confirmation
pydep update -F                 # Force update all (skip outdated check)
pydep update -F -y              # Force update all without confirmation
```

### 7. Build & Publish

```bash
pydep build                     # Create distributions
pydep publish                   # Upload to PyPI
```

---

## All Commands

| Command                       | Purpose                         |
| ----------------------------- | ------------------------------- |
| `pydep -v / --version`        | Show version                    |
| `pydep init`                  | Create new project              |
| `pydep add <pkg>`             | Add dependency                  |
| `pydep remove <pkg>`          | Remove dependency               |
| `pydep update [<spec>]`       | Update one or all dependencies  |
| `pydep list [-D] [-G <x>]`    | List dependencies               |
| `pydep install [-D] [-G <x>]` | Install all (auto-updates lock) |
| `pydep lock [-D] [-G <x>]`    | Generate lock file manually     |
| `pydep build`                 | Build wheel/sdist               |
| `pydep run <script>`          | Run custom script               |
| `pydep audit`                 | Check for issues                |
| `pydep security-audit`        | Scan for CVE                    |
| `pydep fix`                   | Fix conflicts                   |
| `pydep publish`               | Upload to PyPI                  |

**Shorthand flags** (work with most commands):

- `-D` = `--save-dev` (dev dependencies)
- `-G` = `--group` (optional groups)
- `-g` = `--global` (use system Python)
- `-F` = `--force` (skip confirmations and checks)
- `-y` = `--yes` (skip confirmation prompts)

**Command-specific flags:**

- `update` uses `-F` to skip outdated check or force update non-declared deps
- `add` uses `-F` to force-add even if already declared
- `remove` uses `-F` to force-remove even if not found

See [Full Reference](docs/CLI_REFERENCE.md) for all options and examples.

---

## Lock Files

PyDepm automatically manages `pydepm.lock` files:

- **Auto-create/update**: Every `install`, `add`, and `update` command updates the lock file
- **Reproducible builds**: Lock file contains exact versions for all dependencies
- **Format**: TOML with metadata (Python version, creation time, pyproject.toml hash)
- **Group support**: Maintains proper placement of dependencies in their groups

```toml
[metadata]
version = "1.0"
created_at = "2024-04-04T10:30:00Z"
python_version = "3.11"
pyproject_hash = "abc123..."

[dependencies.requests]
version = "2.31.0"
specifier = "==2.31.0"

[dependencies.pytest]
version = "7.4.0"
specifier = "==7.4.0"
```

---

## Version Pinning

PyDepm automatically saves **exact versions** to `pyproject.toml`:

```toml
[project]
dependencies = [
    "requests==2.31.0",  # Exact version saved
    "rich==13.5.2",
]

[tool.pydepm]
dev-dependencies = [
    "pytest==7.4.0",
    "black==23.9.1",
]
```

This ensures:

- ✅ Reproducible builds across environments
- ✅ No surprises from auto-updating transitive dependencies
- ✅ Easy to spot version changes in git diffs

---

## Configuration

All settings in `pyproject.toml`:

```toml
[project]
name = "my-project"
version = "0.1.0"
description = "My project"
requires-python = ">=3.11"

[tool.pydepm]
type = "module"     # or "app"
python-version = "3.11"

[tool.pydepm.env]
type = "venv"           # "venv", "conda", or "global"

[tool.pydepm.scripts]
test = "pytest -v"
lint = "ruff check ."

[project.dependencies]
requests = ">=2.28.0"

[project.optional-dependencies]
dev = ["pytest>=7.0", "black"]
docs = ["sphinx"]
```

See [Configuration Guide](docs/CONFIGURATION.md) for all options.

---

## Lock Files

`pydepm.lock` stores exact versions:

```toml
[metadata]
version = "1.0"
created-at = "2024-04-04T10:30:00Z"
python-version = "3.11"

[resolved]
requests = "2.31.0"
urllib3 = "2.1.0"
```

Generate with: `pydep lock`

---

## Project Structure

After `pydep init my_project`:

```
my_project/
├── pyproject.toml
├── .gitignore
├── src/my_project/
│   ├── __init__.py
│   └── module.py
├── tests/
│   └── __init__.py
└── .venv/
```

---

## Common Usage

### Create a Library

```bash
pydep init mylib --type module
cd mylib
pydep add requests
pydep add pytest -D
pydep build
```

### Create an Application

```bash
pydep init myapp --type app
cd myapp
pydep add click rich
pydep build      # Creates executable via PyInstaller
```

### Manage Multiple Dependency Groups

```bash
pydep add sphinx -G docs
pydep add pytest -G test
pydep install -G test,docs
```

### Run in CI/CD

```bash
# Developer: lock versions
pydep lock
git add pydepm.lock

# CI: install exact versions
pydep install
```

---

## Documentation

| Document                                | Purpose              |
| --------------------------------------- | -------------------- |
| [CLI Reference](docs/CLI_REFERENCE.md)  | All commands & flags |
| [Configuration](docs/CONFIGURATION.md)  | pyproject.toml spec  |
| [Lock Format](docs/LOCK_FILE_FORMAT.md) | Lock file structure  |
| [Architecture](docs/ARCHITECTURE.md)    | How it works         |
| [Examples](docs/EXAMPLES.md)            | Real-world recipes   |
| [Contributing](docs/CONTRIBUTING.md)    | Contribute to PyDepm |

---

## Custom Scripts

Define scripts in `pyproject.toml`:

```toml
[tool.pydepm.scripts]
test = "pytest -v"
lint = "ruff check ."
format = "black . && ruff --fix ."
docs = "sphinx-build docs/ build/docs"
```

Run with:

```bash
pydep run test
pydep run lint
```

---

## Security

```bash
pydep audit              # Check for issues
pydep security-audit     # Scan for CVE vulnerabilities
pydep fix                # Fix conflicts
pydep fix --force        # Aggressive fixing
```

---

## 📦 Installation

### From PyPI (Recommended)

```bash
pip install pydepm
```

### Development

```bash
git clone https://github.com/ZtaMDev/pydepm.git
cd pydepm
pip install -e .
```

### Verify

```bash
python scripts/quick_validation.py
```

---

## Why PyDepm?

| Feature               | Poetry | Pipenv | Pydepm |
| --------------------- | ------ | ------ | ------ |
| Dependency management | ✅     | ✅     | ✅     |
| Easy init             | ✅     | ❌     | ✅     |
| Lock files            | ✅     | ✅     | ✅     |
| App bundling          | ❌     | ❌     | ✅     |
| Simple & fast         | ⚠️     | ⚠️     | ✅     |

---

## 🤝 Contributing

Contributions welcome! See [Contributing Guide](CONTRIBUTING.md).

---

## License

MIT License — See [LICENSE](LICENSE)

---

** Ready?** Run: `pydep init my_first_project`
