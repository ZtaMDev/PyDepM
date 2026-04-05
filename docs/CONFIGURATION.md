# PyDepm Configuration Guide

Complete guide to configuring `pyproject.toml` for use with PyDepm.

## Table of Contents

1. [Project Metadata](#project-metadata)
2. [Dependencies](#dependencies)
3. [PyDepm-Specific Settings](#pydepm-specific-settings)
4. [Build System](#build-system)
5. [Tool Configurations](#tool-configurations)
6. [Examples](#examples)

---

## Project Metadata

Standard PEP 621 metadata section. All fields are optional unless noted.

### Basic Project Information

```toml
[project]
name = "myproject"
version = "0.1.0"
description = "Short description"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"

authors = [
    { name = "Your Name", email = "your.email@example.com" }
]

maintainers = [
    { name = "Maintainer Name", email = "maintainer@example.com" }
]

keywords = ["keyword1", "keyword2"]

classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "License :: OSI Approved :: MIT License",
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
]

homepage = "https://github.com/user/myproject"
repository = "https://github.com/user/myproject"
documentation = "https://myproject.readthedocs.io"
```

### Dependency Specifications

Dependencies in `pyproject.toml` use PEP 508 specification format:

```toml
[project]
dependencies = [
    "requests>=2.28,<3.0",
    "typer>=0.9",
    "tomli>=2.0;python_version<'3.11'",  # Conditional dependency
]
```

#### Version Specifiers

- `>=1.0` - Greater than or equal
- `<=2.0` - Less than or equal
- `==1.5` - Exact version
- `!=1.0` - Not equal
- `~=1.4.5` - Compatible release (>=1.4.5, ==1.4.\*)
- `>=1.0,<2.0` - Complex range (comma-separated)

#### Conditional Dependencies (Markers)

```toml
dependencies = [
    "typing-extensions>=4.0;python_version<'3.10'",
    "pywin32;sys_platform=='win32'",
    "colorama;sys_platform=='win32'",
]
```

Common markers:

- `python_version` - Python version (e.g., '3.11')
- `sys_platform` - Platform (win32, linux, darwin)
- `platform_system` - System type (Windows, Linux, Darwin)

---

## Dependencies

### Regular Dependencies

```toml
[project]
dependencies = [
    "requests>=2.28",
    "httpx>=0.24",
    "pydantic>=2.0",
]
```

### Optional Dependency Groups

Groups allow users to install additional dependencies for specific use cases:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "isort>=5.12",
    "ruff>=0.1",
]

docs = [
    "sphinx>=6.0",
    "sphinx-rtd-theme>=1.2",
    "myst-parser>=1.0",
]

test = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-mock>=3.10",
]

performance = [
    "numpy>=1.24",
    "numba>=0.57",
]
```

**Install groups:**

```bash
pydep install --with dev,docs
pydep install --only test
```

### Development Dependencies (Legacy)

Alternative to groups (not recommended with PyDepm):

```toml
[tool.pydepm.groups]
dev = [
    "pytest>=7.0",
    "black>=23.0",
]
```

---

## PyDepm-Specific Settings

### Tool Configuration

```toml
[tool.pydepm]
# Project type: "module" or "app"
type = "module"

# Project name
name = "myproject"

# Cache PyPI metadata
cache-pypi = true
cache-ttl-hours = 24

# Environment configuration
[tool.pydepm.env]
type = "venv"  # "venv", "conda", or "global"

# Publishing configuration
[tool.pydepm.publishing]
repository = "pypi"  # "pypi" or "testpypi"

# Scripts
[tool.pydepm.scripts]
dev = "python ./main.py"
test = "pytest tests/"
```

````

### Scripts

Define custom scripts that can be run with `pydep run`:

```toml
[tool.pydepm.scripts]
# Development
dev = "uvicorn app:app --reload"
format = "black . && isort ."
lint = "ruff check . && pylint src/"
type-check = "mypy src/"

# Testing
test = "pytest tests/ -v"
test-cov = "pytest tests/ --cov=src --cov-report=html"
test-watch = "pytest-watch tests/"

# Building
build = "pydep build"
publish = "pydep publish"

# Maintenance
audit = "pydep audit --security"
update = "pydep update --all"
````

**Usage:**

```bash
pydep run test
pydep run format
pydep run dev
```

### Package Metadata for Distribution

```toml
[tool.pydepm.package]
# Module or main entry point (for apps)
module = "myproject"

# For app projects - main entry point
main = "myproject.cli:main"

# Include additional files in distribution
include = [
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
]

# Exclude files from distribution
exclude = [
    "*.pyc",
    "__pycache__",
    ".git",
]

# Package data files
package-data = {
    "myproject" = ["data/*.json", "templates/*.html"]
}
```

### Build Settings

```toml
[tool.pydepm.build]
# Build type: "wheel", "sdist", or "both"
build-type = "both"

# Generate type stubs
generate-stubs = true

# Include tests in sdist
include-tests = false

# Minimal Python version in wheels
abi-tag = "cp311"
```

### App Bundling (PyInstaller)

```toml
[tool.pydepm.bundle]
# One-file or one-folder
mode = "one-file"  # or "one-folder"

# Application icon
icon = "app.ico"

# Hidden imports
hidden-imports = [
    "lxml._elementree",
    "sklearn",
]

# Data files to include
data-files = [
    ("./config", "config"),
    ("./data", "data"),
]

# Strip debug symbols
strip = false

# Upx compression (if installed)
upx = false

# Console window
console = false  # Hide console window on Windows
```

### Publishing Configuration

```toml
[tool.pydepm.publish]
# Default repository
repository = "https://upload.pypi.org/legacy/"

# Test repository
test-repository = "https://test.pypi.org/legacy/"

# Skip existing versions
skip-existing = false

# Distributions to publish
distributions = ["wheel", "sdist"]
```

### Groups and Sections

```toml
[tool.pydepm.groups]
# Define custom groups with specific settings
dev = {
    install-by-default = true,
    dependencies = ["pytest", "black"]
}

docs = {
    install-by-default = false,
    dependencies = ["sphinx"]
}
```

---

## Build System

Standard build system configuration:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
```

Or with Poetry-compatible backend:

```toml
[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
```

---

## Tool Configurations

### PyTest

```toml
[tool.pytest.ini_options]
addopts = "--verbose --strict-markers"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
filterwarnings = [
    "error",
    "ignore::UserWarning",
]
```

### Black

```toml
[tool.black]
line-length = 88
target-version = ["py311"]
exclude = '''
/(
    \.git
  | \.venv
  | build
  | dist
)/
'''
```

### isort

```toml
[tool.isort]
profile = "black"
line_length = 88
py_version = 311
```

### Ruff

```toml
[tool.ruff]
target-version = "py311"
line-length = 88
select = ["E", "F", "I"]
ignore = ["E501"]
exclude = [".git", ".venv", "build", "dist"]
```

### MyPy

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
disallow_incomplete_defs = false
check_untyped_defs = true
```

---

## Examples

### Minimal Configuration

```toml
[project]
name = "mylib"
version = "0.1.0"
description = "My library"
requires-python = ">=3.11"
dependencies = ["requests"]

[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
```

### Library with Development Tools

```toml
[project]
name = "mylib"
version = "0.1.0"
description = "My library"
requires-python = ">=3.11"
authors = [{ name = "Your Name", email = "you@example.com" }]
readme = "README.md"
license = { text = "MIT" }
keywords = ["mylib", "example"]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
]

dependencies = [
    "requests>=2.28,<3.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "isort>=5.12",
    "ruff>=0.1",
    "mypy>=1.0",
]

docs = [
    "sphinx>=6.0",
    "sphinx-rtd-theme>=1.2",
    "myst-parser>=1.0",
]

[tool.pydepm]
type = "module"
python-version = "3.11"

[tool.pydepm.scripts]
test = "pytest tests/ -v --cov=src"
format = "black . && isort ."
lint = "ruff check . && mypy src/"
dev = "pytest-watch tests/"

[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src --cov-report=html"

[tool.black]
line-length = 88
target-version = ["py311"]

[tool.isort]
profile = "black"
```

### Web App Configuration

```toml
[project]
name = "myapp"
version = "1.0.0"
description = "Web application"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "httpx", "black", "ruff"]
docs = ["mkdocs", "mkdocs-material"]

[tool.pydepm]
type = "app"
python-version = "3.11"

[tool.pydepm.scripts]
dev = "uvicorn myapp.main:app --reload --host 0.0.0.0 --port 8000"
prod = "uvicorn myapp.main:app --host 0.0.0.0 --port 8000"
test = "pytest tests/ -v"
migrate = "alembic upgrade head"
format = "black . && isort ."

[tool.pydepm.bundle]
mode = "one-file"
console = true

[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
```

---

## Configuration Priority

PyDepm reads configuration from (in order):

1. `pyproject.toml` - Main configuration
2. `.env` - Environment variables (for tokens, secrets)
3. Command-line flags - Override all

---

## Migration from Poetry

If migrating from Poetry:

**Poetry config:**

```toml
[tool.poetry]
name = "mylib"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.28"
```

**PyDepm equivalent:**

```toml
[project]
name = "mylib"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.28,<3.0"]
```

Use: `pydep migrate poetry` to convert automatically.

---

## Further Reading

- [CLI Reference](CLI_REFERENCE.md)
- [Lock File Format](LOCK_FILE_FORMAT.md)
- [PEP 621 Specification](https://www.python.org/dev/peps/pep-0621/)
- [PEP 508 Dependency Specification](https://www.python.org/dev/peps/pep-0508/)
