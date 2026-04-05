# PyDepm Examples & Quick Start Guide

Practical examples and recipes for common PyDepm workflows.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Common Workflows](#common-workflows)
3. [Project Templates](#project-templates)
4. [Advanced Recipes](#advanced-recipes)
5. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Installation

```bash
pip install pydepm
```

Verify installation:

```bash
pydep --version
# pydep version 1.0.0
```

---

### Create Your First Project

```bash
# Create a new project
pydep init myproject

# Interactive prompts:
# ? Project name: myproject
# ? Project type: (module|app) module
# ? Environment type: (venv|conda|global) venv
# ? Python version: Python 3.12.0
#   (Press enter to select, or use arrow keys to browse)

cd myproject
```

**Generated Project Structure:**

```
myproject/
├── pyproject.toml              # Project config with dependencies
├── .gitignore                  # Python gitignore
├── .venv/                      # Virtual environment
├── src/
│   └── myproject/
│       ├── __init__.py         # Package init with version
│       └── (your code here)
├── tests/
│   ├── __init__.py
│   └── test_basic.py           # Basic test example
└── main.py                     # Entry point (app projects only)
```

**Quick Start:**

```bash
# Install dependencies
pydep install

# Run a script
pydep run dev

# Add a dependency
pydep add requests

# Run tests
pytest tests/
```

---

## Project Type Differences

    ├── __init__.py
    └── test_main.py

````

---

### Add Dependencies

```bash
# Add a simple dependency
pydep add requests

# Add with version constraint
pydep add 'django>=4.0,<5.0'

# Add development dependencies
pydep add pytest --group dev
pydep add black --group dev

# Add documentation tools
pydep add sphinx --group docs
````

Check what was installed:

```bash
pydep list
```

---

### Install Dependencies

```bash
# Install all dependencies
pydep install

# Install with specific groups
pydep install --with dev,docs

# Install only dev dependencies
pydep install --only dev
```

---

### Generate Lock File

```bash
# Generate lock file
pydep lock

# This creates pydepm.lock with exact versions and hashes
# Commit this to version control for reproducibility
```

---

### Update Dependencies

```bash
# Check for outdated packages
pydep list --outdated

# Update all dependencies
pydep update --all

# Update specific package
pydep update requests

# Dry run before updating
pydep update --all --dry-run
```

---

## Common Workflows

### Workflow 1: Library Development

**Scenario:** Creating a reusable Python library to publish on PyPI

**Setup:**

```bash
pydep init mylib
cd mylib

# Add core dependencies
pydep add requests
pydep add pydantic

# Add dev dependencies
pydep add pytest pytest-cov --group dev
pydep add black ruff isort --group dev
pydep add sphinx sphinx-rtd-theme --group docs
```

**pyproject.toml configuration:**

```toml
[project]
name = "mylib"
version = "0.1.0"
description = "My awesome library"
requires-python = ">=3.11"
authors = [{ name = "You", email = "you@example.com" }]

dependencies = [
    "requests>=2.28",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "ruff>=0.1",
]

docs = [
    "sphinx>=6.0",
    "sphinx-rtd-theme>=1.2",
]

[tool.pydepm.scripts]
test = "pytest tests/ --cov=src --cov-report=html"
format = "black . && isort . && ruff check --fix ."
lint = "ruff check . && black --check ."
docs = "cd docs && make html"
```

**Development workflow:**

```bash
# Install with all dev tools
pydep install --with dev,docs

# Run tests
pydep run test

# Format code
pydep run format

# Check for issues
pydep audit --security

# Build documentation
pydep run docs

# Build distributions
pydep build

# Publish to TestPyPI first
pydep publish --test

# Publish to PyPI
pydep publish
```

---

### Workflow 2: Web Application

**Scenario:** Building a FastAPI web application

**Setup:**

```bash
pydep init myapp --type app
cd myapp

# Add web framework
pydep add fastapi uvicorn

# Add database
pydep add sqlalchemy psycopg2-binary

# Add validation
pydep add pydantic pydantic-settings

# Dev tools
pydep add pytest pytest-asyncio --group dev
pydep add httpx --group dev
```

**pyproject.toml:**

```toml
[project]
name = "myapp"
version = "1.0.0"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "sqlalchemy>=2.0",
    "psycopg2-binary>=2.9",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "httpx>=0.24"]

[tool.pydepm]
type = "app"

[tool.pydepm.scripts]
dev = "uvicorn myapp.main:app --reload --host 0.0.0.0 --port 8000"
prod = "uvicorn myapp.main:app --host 0.0.0.0 --port 8000 --workers 4"
migrate = "alembic upgrade head"
test = "pytest tests/ -v"
format = "black . && isort ."
```

**Running:**

```bash
# Install dependencies
pydep install

# Run development server
pydep run dev

# In another terminal, run tests
pydep run test

# Build distributions
pydep build

# Deploy to production
```

---

### Workflow 3: Data Science Project

**Scenario:** ML/data analysis project

**Setup:**

```bash
pydep init data-analysis
cd data-analysis

# Data science stack
pydep add numpy pandas scikit-learn

# Data visualization
pydep add matplotlib seaborn plotly

# Jupyter notebooks
pydep add jupyter jupyterlab

# ML
pydep add tensorflow torch --group ml

# Dev
pydep add pytest pytest-cov --group test
pydep add black isort ruff --group dev
```

**pyproject.toml:**

```toml
[project]
name = "data-analysis"
requires-python = ">=3.11"

dependencies = [
    "numpy>=1.24",
    "pandas>=2.0",
    "scikit-learn>=1.3",
    "matplotlib>=3.7",
    "seaborn>=0.12",
    "plotly>=5.17",
    "jupyter>=1.0",
]

[project.optional-dependencies]
ml = ["tensorflow>=2.13", "torch>=2.0"]
dev = ["black>=23.0", "isort>=5.12", "ruff>=0.1"]
test = ["pytest>=7.0", "pytest-cov>=4.0"]

[tool.pydepm.scripts]
jupyter = "jupyter lab"
notebook = "jupyter notebook"
test = "pytest notebooks/ -v"
```

**Usage:**

```bash
# Install data science stack
pydep install

# Start Jupyter Lab
pydep run jupyter

# Add ML tools later
pydep add --group ml tensorflow

# Update all packages
pydep update --all
```

---

## Project Templates

### Minimal Library

```toml
[project]
name = "minimal-lib"
version = "0.1.0"
description = "Minimal Python library"
requires-python = ">=3.11"

dependencies = []

[project.optional-dependencies]
dev = ["pytest", "black"]

[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
```

### FastAPI API

```toml
[project]
name = "api-app"
version = "1.0.0"
description = "FastAPI application"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.104",
    "uvicorn>=0.24",
    "sqlalchemy>=2.0",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "httpx", "black", "ruff"]

[tool.pydepm]
type = "app"

[tool.pydepm.scripts]
dev = "uvicorn app:app --reload"
prod = "uvicorn app:app"
```

### Django Project

```toml
[project]
name = "django-app"
requires-python = ">=3.11"

dependencies = [
    "django>=4.2",
    "psycopg2-binary>=2.9",
    "django-environ>=0.10",
]

[project.optional-dependencies]
dev = ["black", "ruff", "pytest", "pytest-django"]

[tool.pydepm.scripts]
migrate = "python manage.py migrate"
test = "pytest"
serve = "python manage.py runserver"
```

---

## Advanced Recipes

### Recipe 1: Local Path Dependencies

**Scenario:** Multiple local packages working together

```bash
# Main project
pydep init main-app
cd main-app

# Add package from PyPI
pydep add requests
```

### Recipe 2: Optional Groups

**Scenario:** Organizing dependencies in groups

```bash
# Add to testing group
pydep add -G test pytest pytest-cov

# Add to docs group
pydep add -G docs sphinx sphinx-rtd-theme

# Install with specific groups
pydep install -G test
pydep install -G docs
pydep install -G test,docs
```

### Recipe 3: Version Constraints

**Scenario:** Managing package versions

```bash
# Pin to specific range
pydep add "django>=4.2,<5.0"
pydep add "requests>=2.28"
pydep add "pytest==7.4.0"

# Update with new constraint
pydep update "requests>=3.0"
```

# Multiple packages with extras

pydep add pillow[imaging]
pydep add sqlalchemy[asyncio]

````

**pyproject.toml:**

```toml
dependencies = [
    "requests[security,socks]>=2.28",
    "pillow[imaging]",
    "sqlalchemy[asyncio]",
]
````

### Recipe 4: Conditional Dependencies

**Scenario:** Different dependencies for different platforms

```toml
dependencies = [
    # For all platforms
    "requests>=2.28",
    # Windows only
    "pywin32>=300;sys_platform=='win32'",
    # macOS only
    "py2app>=0.28;sys_platform=='darwin'",
    # Python < 3.11 only
    "tomli>=2.0;python_version<'3.11'",
]
```

### Recipe 5: Pre-commit Integration

**Scenario:** Automated code quality checks before commit

**Setup:**

```bash
pydep add pre-commit --group dev

# Configure linting tools
pydep add black ruff isort mypy --group dev
```

**.pre-commit-config.yaml:**

```yaml
repos:
  - repo: https://github.com/python/black
    rev: 23.12.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/PyCQA/isort
    rev: 5.13.2
    hooks:
      - id: isort

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
```

**pyproject.toml script:**

```toml
[tool.pydepm.scripts]
pre-commit-setup = "pre-commit install"
pre-commit-run = "pre-commit run --all-files"
```

### Recipe 6: CI/CD Integration

**GitHub Actions:**

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install PyDepm
        run: pip install pydepm

      - name: Install dependencies
        run: pydep install --with dev

      - name: Lint
        run: pydep run lint

      - name: Test
        run: pydep run test

      - name: Security audit
        run: pydep audit --security
```

---

## Troubleshooting

### Problem: "PyPI timeout"

```bash
# Increase timeout
pydep add requests --timeout 30

# Or in pyproject.toml:
[tool.pydepm.resolver]
pypi-timeout = 30
```

### Problem: "Dependency conflict"

```bash
# Check what's conflicting
pydep list --tree requests

# Show detailed dependency tree
pydep list --tree

# Check audit for issues
pydep audit --conflicts
```

### Problem: "Virtual environment path issues"

```bash
# Recreate environment
pydep env-recreate

# Or manually
rm -rf .venv
pydep install  # Will create new venv
```

### Problem: "Lock file out of date"

```bash
# Regenerate lock
pydep lock

# Sync environment to lock
pydep sync

# Or reinstall
pydep install --force
```

### Problem: "Can't find package on PyPI"

```bash
# Check package name (case-sensitive)
pydep add Package-Name

# Search PyPI
pydep search requests

# Check if it's renamed
pydep search old-package-name
```

### Problem: "Version not available"

```bash
# Add with compatible version constraint
pydep add 'requests>=2.28,<3.0'

# Or use update to check latest
pydep update requests
```

---

## Performance Tips

### Tip 1: Use Lock Files

```bash
# After creating lock file
pydep lock

# Installs are now 10-50x faster
pydep install

# Use lock file for faster installs
pydep install
```

### Tip 2: Checking Installations

```bash
# See what's installed
pydep list

# Check for conflicts
pydep audit

# Check for vulnerabilities
pydep security-audit
```

### Tip 3: Use Parallel Resolution (Future)

```toml
[tool.pydepm]
# When parallel resolution arrives
parallel-workers = 4
```

### Tip 4: Minimal Dependencies

```toml
# Good - minimal, specific
dependencies = [
    "requests>=2.28,<3.0",
    "pydantic>=2.0",
]

# Bad - too many, loose versions
dependencies = [
    "requests",  # No version!
    "pydantic",
    "dataclasses-json",
    "httpx",
    "aiohttp",
]
```

---

## Integration Examples

### With Poetry Projects

```bash
# Migrate from Poetry
pydep migrate poetry --input poetry.lock

# Then use PyDepm normally
pydep install
pydep add new-package
pydep lock
```

### With Pipenv Projects

```bash
# Convert Pipfile
pydep migrate pipenv --input Pipfile

# Transform to pyproject.toml
pydep install
```

### With Flit

```bash
# Flit projects work with PyDepm
# Just use PyDepm for dependency management
pydep add requests
pydep lock
```

---

## Further Reading

- [CLI Reference](CLI_REFERENCE.md)
- [Configuration Guide](CONFIGURATION.md)
- [Lock File Format](LOCK_FILE_FORMAT.md)
- [Architecture Document](ARCHITECTURE.md)
