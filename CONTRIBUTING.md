# Contributing to PyDepm

Thank you for your interest in contributing to PyDepm! This document provides guidelines and instructions for contributing.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Making Changes](#making-changes)
5. [Testing](#testing)
6. [Documentation](#documentation)
7. [Submitting Changes](#submitting-changes)
8. [Code Standards](#code-standards)

---

## Code of Conduct

We are committed to providing a welcoming and inspiring community for all. Please read and follow our Code of Conduct:

- Be respectful and inclusive
- Welcome different perspectives and experiences
- Provide constructive feedback
- Focus on what's best for the community
- Report unacceptable behavior

---

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Basic familiarity with dependency management and packaging

### Types of Contributions

We welcome contributions in several areas:

1. **Bug Fixes** - Fix identified issues
2. **Feature Development** - Implement new features from the roadmap
3. **Documentation** - Improve guides, examples, and API docs
4. **Performance** - Optimize speed and memory usage
5. **Testing** - Expand test coverage
6. **Quality** - Improve code standards and maintainability

---

## Development Setup

### 1. Fork and Clone

```bash
# Fork on GitHub, then:
git clone https://github.com/ZMDev/pydepm.git
cd pydepm
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install in development mode with all dependencies
pydep install --with dev,test,docs
# Or if pydep isn't installed yet:
pip install -e .[dev,test,docs]
```

### 3. Verify Setup

```bash
# Run tests
pydep run test

# Run linting
pydep run lint

# Run type checking
pydep run type-check
```

---

## Making Changes

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or for bug fixes:
git checkout -b fix/issue-description
```

Branch naming conventions:

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation improvements
- `test/` - Test additions
- `perf/` - Performance improvements
- `refactor/` - Code refactoring

### 2. Make Your Changes

Follow these guidelines:

- **One feature per PR** - Keep changes focused
- **Work incrementally** - Small, reviewable commits
- **Update tests** - Add tests for new functionality
- **Update docs** - Document new features and changes
- **Run linting** - Keep code style consistent

### 3. Project Structure

```
pydepm/
├── src/pydepm/
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py          # CLI commands
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pypi.py          # PyPI client (NEW)
│   │   ├── resolver.py      # Dependency resolver (NEW)
│   │   ├── lock.py          # Lock file system (NEW)
│   │   ├── config.py        # Configuration management
│   │   ├── envs.py          # Environment management
│   │   ├── build.py         # Building
│   │   ├── deps.py          # Dependency utilities
│   │   └── proc.py          # Process utilities
│   └── __init__.py
├── tests/
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── docs/                    # Documentation
├── pyproject.toml           # Project configuration
├── CHANGELOG.md            # Version history
├── CONTRIBUTING.md         # This file
└── LICENSE                 # MIT License
```

### 4. Key Areas

**Core Resolution** (`src/pydepm/core/`)

- `pypi.py` - PyPI API client
- `resolver.py` - Dependency resolution algorithm
- `lock.py` - Lock file management

**CLI** (`src/pydepm/cli/`)

- `main.py` - Command definitions and handlers

**Configuration** (`src/pydepm/core/`)

- `config.py` - Configuration file handling

---

## Testing

### Running Tests

```bash
# Run all tests
pydep run test

# Run specific test file
pytest tests/unit/test_resolver.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run tests in watch mode
pydep run test-watch
```

### Writing Tests

Create tests in the appropriate directory:

- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests for workflows
- `tests/e2e/` - End-to-end tests for complete scenarios

**Test template:**

```python
import pytest
from pydepm.core.resolver import DependencyResolver

class TestDependencyResolver:
    def test_resolve_simple_requirement(self):
        resolver = DependencyResolver()
        result = resolver.resolve(["requests>=2.28"])
        assert result.success
        assert "requests" in result.resolved

    def test_resolve_with_conflict(self):
        resolver = DependencyResolver()
        result = resolver.resolve([
            "package-a>=2.0",
            "package-b>=1.0"  # requires package-a<2.0
        ])
        assert not result.success
        assert len(result.errors) > 0
```

### Test Coverage

- Aim for > 80% code coverage
- Focus on critical paths
- Include edge cases and error scenarios

---

## Documentation

### Updating Documentation

Documentation updates should include:

- Examples of new features
- CLI reference updates
- Configuration guide additions
- Architecture notes if relevant

### Documentation Files

- `docs/INDEX.md` - Documentation index
- `docs/CLI_REFERENCE.md` - Command reference
- `docs/CONFIGURATION.md` - Configuration guide
- `docs/LOCK_FILE_FORMAT.md` - Lock file specification
- `docs/ARCHITECTURE.md` - System design
- `docs/EXAMPLES.md` - Usage examples

### Documentation Style

- Use clear, concise language
- Include practical examples
- Provide context and background
- Link to related sections
- Keep examples up-to-date

---

## Code Standards

### Coding Style

```bash
# Format code
pydep run format

# Check style
pydep run lint

# Type checking
pydep run type-check
```

**Configuration in pyproject.toml:**

- Black: line length 88
- Ruff: Python 3.11+
- isort: Black profile
- mypy: strict mode enabled

### Code Quality Guidelines

1. **Type Hints**

   ```python
   from typing import Dict, List, Optional
   from pathlib import Path

   def resolve_package(
       name: str,
       specifier: str,
       resolved: Dict[str, object],
   ) -> bool:
       """Resolve a package and its dependencies."""
       ...
   ```

2. **Docstrings**

   ```python
   def resolve(
       self,
       requirements: List[str],
   ) -> ResolutionResult:
       """
       Resolve a list of requirements to a dependency tree.

       Args:
           requirements: List of PEP 508 requirement specifiers

       Returns:
           ResolutionResult with resolved dependencies or errors

       Raises:
           ResolutionError: If resolution cannot complete
       """
   ```

3. **Error Handling**

   ```python
   try:
       result = resolver.resolve(requirements)
       if not result.success:
           for error in result.errors:
               logger.error(f"Resolution failed: {error}")
           return
   except ResolutionError as e:
       logger.error(f"Critical error: {e}")
       raise
   ```

4. **Testing**
   ```python
   # Every public function should have tests
   # Test both happy path and error cases
   # Include edge cases
   ```

---

## Submitting Changes

### 1. Local Verification

Before submitting, verify everything works:

```bash
# Format code
pydep run format

# Run linting
pydep run lint

# Type checking
pydep run type-check

# Run tests
pydep run test

# Build documentation
pydep run docs
```

### 2. Commit Message Guidelines

Write clear, descriptive commit messages:

```
[type] brief description

Longer explanation of why this change is needed and what it does.
Reference issue #123 if applicable.

[type] can be:
- feat: New feature
- fix: Bug fix
- docs: Documentation
- test: Test additions
- perf: Performance improvement
- refactor: Code refactoring
- chore: Tooling/configuration
```

Example:

```
feat: add parallel dependency resolution

Implement ThreadPoolExecutor-based parallel resolution for faster
dependency tree building. This provides 2-3x speedup for projects
with many independent dependencies.

Resolves issue #42
```

### 3. Push and Create PR

```bash
# Push your branch
git push origin your-branch-name

# Go to GitHub and create a Pull Request
# Include:
# - Description of changes
# - Motivation/context
# - Testing done
# - Link to related issue
```

### 4. PR Template

```markdown
## Description

Brief description of changes

## Motivation

Why is this change needed?

## Testing

How was this tested?

## Documentation

What documentation was updated?

## Related Issue

Fixes #123
```

---

## Review Process

### What to Expect

1. **Automated Checks**
   - GitHub Actions runs tests, linting, coverage
   - All checks must pass

2. **Code Review**
   - Team reviews code changes
   - Suggestions for improvements
   - Discussion of design decisions

3. **Approval and Merge**
   - After approval, changes are merged
   - Contributor credited in changelog

### Tips for Better PRs

- Keep PRs focused and reasonably sized
- Include tests for new functionality
- Update documentation
- Respond to feedback constructively
- Be patient with review process

---

## Build System & Tools

### Build Commands

```bash
# Build wheel and sdist
pydep build

# Run tests during build
pydep build --test

# Clean build artifacts
pydep build --clean
```

### Tool Configuration

All tools configured in `pyproject.toml`:

- pytest - Testing framework
- black - Code formatting
- isort - Import sorting
- ruff - Linting
- mypy - Type checking

---

## Reporting Issues

Found a bug? Have a suggestion?

1. **Check existing issues** - Avoid duplicates
2. **Create detailed report** - Include:
   - Python version
   - PyDepm version
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Traceback/error message

**Issue template:**

```markdown
## Description

What is the issue?

## Steps to Reproduce

1. ...
2. ...
3. ...

## Expected Behavior

What should happen?

## Actual Behavior

What actually happened?

## Environment

- Python: 3.11.0
- PyDepm: 1.0.0
- OS: Windows 11
```

---

## Performance Considerations

When contributing performance-critical code:

1. **Profile Before Optimizing**
   - Use cProfile or similar tools
   - Measure impact of changes

2. **Avoid Premature Optimization**
   - Focus on readability first
   - Optimize hot paths only

3. **Benchmark Results**
   - Include before/after metrics
   - Document performance changes

4. **Example Benchmarks**

   ```python
   import time

   start = time.time()
   # Code to benchmark
   elapsed = time.time() - start
   print(f"Time: {elapsed:.3f}s")
   ```

---

## Documentation Contribution

Improving documentation is highly valued!

1. **Fix Typos** - Always welcome
2. **Clarify Examples** - Help others understand
3. **Add Sections** - Cover missing topics
4. **Improve Examples** - Make them more practical
5. **Translate** - Translate to other languages (future)

To contribute docs:

```bash
# Edit files in docs/
vim docs/CLI_REFERENCE.md

# Preview locally (requires sphinx)
pydep run docs

# Submit PR with documentation changes
```

---

## Questions?

- Check existing [issues](https://github.com/yourusername/pydepm/issues)
- Ask in [discussions](https://github.com/yourusername/pydepm/discussions)
- Read the [documentation](docs/)
- Review [architecture](docs/ARCHITECTURE.md)

---

## Community

- **Respectful communication** - We value all opinions
- **Inclusive environment** - Welcome contributors from all backgrounds
- **Collaborative spirit** - Help each other succeed
- **Shared vision** - Building the best Python package manager

---

## Resources

- [PEP 508 - Dependency Specification](https://www.python.org/dev/peps/pep-0508/)
- [PEP 621 - Project Metadata](https://www.python.org/dev/peps/pep-0621/)
- [PyPI JSON API](https://warehouse.pypa.io/api-reference/json.html)
- [Python Packaging Guide](https://packaging.python.org/)
- [Semantic Versioning](https://semver.org/)

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to PyDepm! Your efforts make Python packaging better for everyone. 🚀
