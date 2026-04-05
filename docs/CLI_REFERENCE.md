# PyDepm CLI Reference

Complete reference for all `pydep` commands.

**Status**: Accurate as of v1.0.0 - Lists ONLY features that actually exist in code

---

## All Commands

| Command          | Purpose                       |
| ---------------- | ----------------------------- |
| `init`           | Initialize new Python project |
| `add`            | Add dependency                |
| `remove`         | Remove dependency             |
| `update`         | Update dependency             |
| `list`           | List dependencies             |
| `install`        | Install all dependencies      |
| `lock`           | Generate lock file            |
| `build`          | Build distributions           |
| `run`            | Run custom script             |
| `audit`          | Audit for issues              |
| `security-audit` | Check for CVE vulnerabilities |
| `fix`            | Fix dependency issues         |
| `publish`        | Publish to PyPI               |

---

## Shorthand Flags (Available on all commands that support them)

```
-D            --save-dev           (Dev dependencies)
-G VALUE      --group VALUE        (Optional group name)
-g            --global             (Use system Python)
-y            --yes                (Skip prompts)
-t            --tree               (Tree view)
-A            --all-groups         (Show all groups)
```

---

## Commands

### `pydep init`

Initialize a new Python project with directory structure, virtual environment, and configuration.

**Usage:**

```bash
pydep init                         # Interactive setup with prompts
pydep init myproject               # Create new project in myproject/
pydep init . --type app -y         # Setup current directory, app type, no prompts
pydep init myapp --env conda       # Use conda environment
pydep init myapp --global-deps     # Use global Python (no virtual environment)
```

**Options:**

| Option          | Short | Default | Values              | Description                      |
| --------------- | ----- | ------- | ------------------- | -------------------------------- |
| `--type`        | -     | module  | module, app         | Project type                     |
| `--env`         | -     | venv    | venv, conda, global | Environment type                 |
| `--global-deps` | -     | -       | -                   | Use global Python instead of env |
| `--yes`         | `-y`  | -       | -                   | Skip all prompts (use defaults)  |

**Interactive Prompts:**

When run without `--yes`, you will be prompted for:

- Project name
- Project type (module or app)
- Environment type (venv, conda, or global)
- Python version (auto-detects available versions on system)

**Creates:**

- `pyproject.toml` - Project configuration with dependencies and scripts
- `.gitignore` - Python gitignore file
- `src/project_name/` - Python package directory with `__init__.py`
- `tests/` - Test directory with `__init__.py` and `test_basic.py`
- `main.py` - Entry point (for app projects only)
- Virtual environment at `.venv` or conda environment (unless `--global-deps`)

**Python Version Detection:**

`pydep init` automatically detects available Python versions on your system:

- Searches standard Python installation paths
- On Windows: Checks registry for installed versions
- Displays newest versions first
- Defaults to currently running Python if none detected

---

### `pydep add`

Add a dependency to your project.

**Usage:**

```bash
pydep add requests               # Add to dependencies
pydep add -D pytest              # Add to dev-dependencies
pydep add -G docs sphinx         # Add to docs group
pydep add "requests>=2.28"       # With version constraint
```

**Flags:**

| Flag            | Short      | Purpose                 |
| --------------- | ---------- | ----------------------- |
| `--save-dev`    | `-D`       | Add to dev-dependencies |
| `--group GROUP` | `-G GROUP` | Add to specific group   |
| `--global`      | `-g`       | Use system Python       |

**What it does:**

1. Validates package exists on PyPI
2. Resolves all dependencies
3. Updates `pyproject.toml`
4. Installs to .venv (or system with -g)
5. Runs `pip check` to verify

---

### `pydep remove`

Remove a dependency.

**Usage:**

```bash
pydep remove requests           # From dependencies
pydep remove -D pytest          # From dev-dependencies
pydep remove -G docs sphinx     # From docs group
```

**Flags:**

| Flag            | Short      | Purpose                      |
| --------------- | ---------- | ---------------------------- |
| `--save-dev`    | `-D`       | Remove from dev-dependencies |
| `--group GROUP` | `-G GROUP` | From specific group          |
| `--global`      | `-g`       | Use system Python            |

---

### `pydep update`

Update a dependency to a new version.

**Usage:**

```bash
pydep update requests           # Update to latest stable
pydep update "requests>=2.30"   # Update with constraint
pydep update -D pytest          # Update dev dependency
```

**Flags:**

| Flag            | Short      | Purpose                    |
| --------------- | ---------- | -------------------------- |
| `--save-dev`    | `-D`       | Update in dev-dependencies |
| `--group GROUP` | `-G GROUP` | Update in specific group   |
| `--global`      | `-g`       | Use system Python          |

---

### `pydep list`

List all project dependencies.

**Usage:**

```bash
pydep list                      # All dependencies
pydep list -t                   # Tree view (shows dependency tree)
pydep list -D                   # Include dev-dependencies
pydep list -G docs              # Only docs group
pydep list -A                   # All groups
```

**Flags:**

| Flag            | Short      | Purpose                  |
| --------------- | ---------- | ------------------------ |
| `--tree`        | `-t`       | Show dependency tree     |
| `--all-groups`  | `-A`       | Show all optional groups |
| `--group GROUP` | `-G GROUP` | Show specific group      |
| `--include-dev` | `-D`       | Include dev-dependencies |

**Output:** Table with package names and versions.

---

### `pydep install`

Install all project dependencies.

**Usage:**

```bash
pydep install                   # All dependencies
pydep install -D                # With dev-dependencies
pydep install -G test,docs      # With specific groups
pydep install -g                # Use system Python
```

**Flags:**

| Flag              | Short | Purpose                  |
| ----------------- | ----- | ------------------------ |
| `--include-dev`   | `-D`  | Include dev-dependencies |
| `--groups GROUPS` | -     | Comma-separated groups   |
| `--all-groups`    | -     | All optional groups      |
| `--global`        | `-g`  | Use system Python        |

**Behavior:**

- Reads from `pyproject.toml`
- Creates/uses `.venv` automatically
- Installs via pip
- Updates `pydepm.lock`

---

### `pydep lock`

Generate lock file with exact versions.

**Usage:**

```bash
pydep lock                      # Lock all dependencies
pydep lock -D                   # Include dev-dependencies
pydep lock -G test,docs         # Include specific groups
```

**Flags:**

| Flag              | Short | Purpose                           |
| ----------------- | ----- | --------------------------------- |
| `--include-dev`   | `-D`  | Include dev-dependencies          |
| `--groups GROUPS` | -     | Specific groups (comma-separated) |
| `--global`        | `-g`  | Use system Python                 |

**Creates:**

`pydepm.lock` (TOML format) with exact package versions and metadata.

---

### `pydep build`

Build project distributions.

**Usage:**

```bash
pydep build                     # Build .whl + .tar.gz
pydep build -g                  # Use system Python
```

**For Modules:**

- Creates `.whl` (wheel) and `.tar.gz` (source) in `dist/`

**For Apps:**

- Uses PyInstaller to create executable

---

### `pydep publish`

Upload distributions to PyPI or TestPyPI.

**Usage:**

```bash
pydep publish                           # Prompts for repository
pydep publish --repository pypi        # Upload to PyPI
pydep publish --repository testpypi    # Upload to TestPyPI
```

**Flags:**

| Flag                | Short | Purpose           |
| ------------------- | ----- | ----------------- |
| `--repository REPO` | -     | pypi or testpypi  |
| `--global`          | `-g`  | Use system Python |

**Requirements:**

- Build first: `pydep build`
- Token in `.env`: `PYPI_API_TOKEN` or `TESTPYPI_API_TOKEN`

---

### `pydep run`

Run custom scripts defined in `pyproject.toml`.

**Usage:**

```bash
pydep run test                  # Run "test" script
pydep run format                # Run "format" script
pydep run                       # Shows all scripts if multiple
```

**Define scripts in `pyproject.toml`:**

```toml
[tool.pydepm.scripts]
test = "pytest -v"
lint = "ruff check ."
format = "black . && ruff --fix ."
```

---

### `pydep audit`

Check dependencies for issues.

**Usage:**

```bash
pydep audit                     # Check all
pydep audit -D                  # Include dev-dependencies
pydep audit -G test,docs        # Check specific groups
```

**Checks:**

- Missing packages
- Conflicts (`pip check`)
- Outdated versions

---

### `pydep security-audit`

Scan for CVE security vulnerabilities.

**Usage:**

```bash
pydep security-audit            # Scan all packages
pydep security-audit -g         # Use system Python
```

**Uses:** `pip-audit` (auto-installed if needed)

---

### `pydep fix`

Fix dependency conflicts and issues.

**Usage:**

```bash
pydep fix                       # Standard fixing
pydep fix --force               # Aggressive (--upgrade --force-reinstall)
pydep fix -D                    # Include dev-dependencies
```

**Flags:**

| Flag              | Short | Purpose                  |
| ----------------- | ----- | ------------------------ |
| `--include-dev`   | `-D`  | Include dev-dependencies |
| `--groups GROUPS` | -     | Specific groups          |
| `--force`         | -     | Aggressive upgrade       |
| `--global`        | `-g`  | Use system Python        |

**Process:**

1. Re-installs dependencies
2. Runs `pip check` to verify
3. Reports conflicts if any remain

---

## Global Flags

| Flag            | Purpose               |
| --------------- | --------------------- |
| `--help` / `-h` | Show help for command |

---

## Common Workflows

### Create and Publish a Library

```bash
pydep init my_lib --type module -y
pydep add requests
pydep add -D pytest black ruff
pydep audit
pydep security-audit
pydep build
pydep publish --repository testpypi
pydep publish --repository pypi
```

### Development Setup

```bash
pydep init my_project --env conda
pydep add -D pytest pytest-cov black ruff
pydep add -G docs sphinx sphinx-rtd-theme
pydep install -D -G docs
pydep run test
```

### Work with Optional Groups

```bash
pydep add -G docs sphinx
pydep add -G test pytest
pydep install                      # Production only
pydep install -D                   # Production + dev
pydep install -G docs              # Single group
pydep install -G test,docs         # Multiple groups
```

### Use System Python (No Venv)

```bash
pydep init my_project --env global
pydep add requests -g
pydep install -g
```

---

## Troubleshooting

### Virtual Environment Not Found

`pydep` automatically creates `.venv` when needed. Use `-g` flag to skip.

### Permission Denied (macOS/Linux)

Use `-g` to install as current user:

```bash
pydep install -g
```

### Fix Conflicts

Use `pydep fix` to resolve issues:

```bash
pydep fix
```

---

**Version:** v1.0.0 | [Back to README](../README.md)
