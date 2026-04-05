"""
PyDepm CLI commands - Integration with custom resolver, PyPI client, and lock file system.
This module implements all documented CLI commands with full support for:
- Custom dependency resolution (no pip)
- Lock file generation and validation
- Comprehensive project management
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer
import questionary
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
import tomllib

# Import our custom modules
from pydepm.core.pypi import PyPIClient
from pydepm.core.resolver import DependencyResolver, ResolutionError
from pydepm.core.lock import LockFile
from pydepm.core import config as core_config
from pydepm.core import envs as core_envs
from pydepm.core import build as core_build
from pydepm.core import deps as core_deps

app = typer.Typer(
    help="pydep - Modern Python dependency and project manager with custom resolver and lock files",
    add_completion=False,
)
console = Console()

# Questionary styling
from prompt_toolkit.styles import Style as PTStyle
questionary_style = PTStyle.from_dict({
    "questionmark": "bold fg:cyan",
    "selected": "bold fg:green",
    "pointer": "bold fg:cyan",
    "answer": "bold fg:magenta",
})


# ============================================================================
# Helper Functions
# ============================================================================

def _make_progress() -> Progress:
    """Create a standard progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def _run_resolver(requirements: List[str], python_version: str = "3.11") -> Tuple[bool, dict, List[str]]:
    """Run the custom resolver and return (success, resolved_deps, errors)."""
    resolver = DependencyResolver(python_version=python_version)
    result = resolver.resolve(requirements)
    
    if result.success:
        return True, result.resolved, result.warnings
    else:
        return False, {}, result.errors


def _load_pyproject(path: Path) -> dict:
    """Load and parse pyproject.toml."""
    if not path.exists():
        raise FileNotFoundError(f"pyproject.toml not found: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _get_python_executable(project_dir: Path, use_global: bool = False) -> Tuple[str, dict]:
    """Get Python executable path and environment variables."""
    env_vars = os.environ.copy()
    
    if use_global:
        return sys.executable, env_vars
    
    cfg = core_config.load_project_config(project_dir)
    if cfg is None:
        return sys.executable, env_vars
    
    env_path = core_envs.get_env_path(project_dir, cfg.env_type)
    if env_path is None:
        return sys.executable, env_vars
    
    bin_dir = core_envs.get_env_bin_dir(env_path)
    env_vars["VIRTUAL_ENV"] = str(env_path)
    env_vars["PATH"] = f"{bin_dir}{os.pathsep}" + env_vars.get("PATH", "")
    return str(bin_dir / "python"), env_vars


# ============================================================================
# Core Commands
# ============================================================================

@app.command()
def init(
    name: Optional[str] = typer.Argument(None, help="Project name or path"),
    project_type: Optional[str] = typer.Option(None, "--type", help="Project type: module or app"),
    env_type: Optional[str] = typer.Option(None, "--env", help="Environment: venv, conda, or global"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Accept all defaults"),
) -> None:
    """Initialize a new Python project."""
    
    cwd = Path.cwd()
    target_dir = cwd / name if name and name not in {".", "./"} else cwd
    
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    
    # Get project name
    project_name = name or target_dir.name
    if not yes:
        project_name = Prompt.ask("Project name", default=project_name)
    
    # Get project type
    proj_type = project_type or "module"
    if not yes and not project_type:
        proj_type = questionary.select(
            "Project type:",
            choices=["module", "app"],
            default="module",
            style=questionary_style,
        ).ask() or "module"
    
    # Get environment type
    env = env_type or "venv"
    if not yes and not env_type:
        env = questionary.select(
            "Environment:",
            choices=["venv", "conda", "global"],
            default="venv",
            style=questionary_style,
        ).ask() or "venv"
    
    console.print(f"[bold]Initializing project[/bold] [green]{project_name}[/green]")
    
    # Create environment
    if env != "global":
        try:
            core_envs.create_environment(target_dir, env)
            console.print(f"[green]✓[/green] Environment created")
        except Exception as e:
            console.print(f"[red]✗[/red] Environment creation failed: {e}")
            raise typer.Exit(code=1)
    
    # Create pyproject.toml
    core_config.bootstrap_project(target_dir, project_name, proj_type, env)
    console.print(f"[green]✓[/green] Configuration created")
    
    # Create template files
    src_dir = target_dir / "src" / project_name
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "__init__.py").write_text('"""' + project_name + ' package."""\n\n__version__ = "0.1.0"\n')
    
    tests_dir = target_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "__init__.py").write_text("")
    
    console.print(f"[bold green]✓ Project initialized[/bold green]")


@app.command()
def add(
    packages: List[str] = typer.Argument(..., help="Package specs to add (e.g., 'requests', 'pytest>=7.0')"),
    group: str = typer.Option("dependencies", "--group", "-g", help="Dependency group"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmations"),
) -> None:
    """Add dependencies to the project with resolution."""
    
    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    
    if not pyproject_path.exists():
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    console.print(f"[bold]Resolving dependencies[/bold] {packages}")
    
    # Resolve dependencies
    progress = _make_progress()
    with progress:
        task_id = progress.add_task("Resolving...", total=100)
        success, resolved, errors = _run_resolver(packages)
        progress.update(task_id, completed=100)
    
    if not success:
        console.print("[red]Resolution failed:[/red]")
        for error in errors:
            console.print(f"  [red]•[/red] {error}")
        raise typer.Exit(code=1)
    
    # Show resolved packages
    console.print("\n[bold]Resolved dependencies:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Package")
    table.add_column("Version", style="green")
    table.add_column("Dependencies", style="dim")
    
    for name, dep in resolved.items():
        table.add_row(
            name,
            dep.version,
            ", ".join(dep.requires[:2]) if dep.requires else "-"
        )
    
    console.print(table)
    
    # Confirm
    if not yes and not Confirm.ask("Add these packages?"):
        raise typer.Abort()
    
    # Write to pyproject.toml
    try:
        for pkg in packages:
            core_deps.add_dependency(pyproject_path, pkg, group=group if group != "dependencies" else None)
        console.print("[green]✓ Dependencies added to pyproject.toml[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    
    # Install packages
    if Confirm.ask("Install now?"):
        python_exe, env_vars = _get_python_executable(project_dir)
        for pkg_spec in packages:
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", pkg_spec],
                env=env_vars,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                console.print(f"[red]Installation failed: {result.stderr}[/red]")
                raise typer.Exit(code=1)
        console.print("[green]✓ Packages installed[/green]")


@app.command()
def remove(
    packages: List[str] = typer.Argument(..., help="Package names to remove"),
    group: str = typer.Option("dependencies", "--group", "-g", help="Dependency group"),
) -> None:
    """Remove dependencies from the project."""
    
    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    
    if not pyproject_path.exists():
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    console.print(f"[bold]Removing packages:[/bold] {', '.join(packages)}")
    
    # Remove from config
    for pkg in packages:
        try:
            core_deps.remove_dependency(
                pyproject_path,
                pkg,
                group=group if group != "dependencies" else None
            )
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] {e}")
    
    console.print("[green]✓ Dependencies removed from pyproject.toml[/green]")
    
    # Uninstall
    python_exe, env_vars = _get_python_executable(project_dir)
    for pkg in packages:
        result = subprocess.run(
            [python_exe, "-m", "pip", "uninstall", "-y", pkg],
            env=env_vars,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            console.print(f"[yellow]Warning: Could not uninstall {pkg}[/yellow]")
    
    console.print("[green]✓ Packages uninstalled[/green]")


@app.command()
def install(
    with_groups: Optional[str] = typer.Option(None, "--with", help="Install specific groups (comma-separated)"),
    only_groups: Optional[str] = typer.Option(None, "--only", help="Install ONLY these groups"),
) -> None:
    """Install all project dependencies."""
    
    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    
    if not pyproject_path.exists():
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    # Load dependencies
    try:
        data = _load_pyproject(pyproject_path)
        project = data.get("project", {})
        deps = project.get("dependencies", [])
        optional = project.get("optional-dependencies", {})
    except Exception as e:
        console.print(f"[red]Error reading pyproject.toml: {e}[/red]")
        raise typer.Exit(code=1)
    
    # Build package list
    packages = deps.copy() if deps else []
    
    if only_groups:
        packages = []
        for group in only_groups.split(","):
            group = group.strip()
            if group in optional:
                packages.extend(optional[group])
    else:
        if with_groups:
            for group in with_groups.split(","):
                group = group.strip()
                if group in optional:
                    packages.extend(optional[group])
    
    if not packages:
        console.print("[yellow]No packages to install[/yellow]")
        return
    
    console.print(f"[bold]Installing {len(packages)} packages[/bold]")
    
    # Install
    python_exe, env_vars = _get_python_executable(project_dir)
    progress = _make_progress()
    
    with progress:
        task_id = progress.add_task("Installing...", total=len(packages))
        
        for pkg in packages:
            progress.update(task_id, description=f"Installing {pkg}")
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", pkg],
                env=env_vars,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                console.print(f"[red]Failed to install {pkg}: {result.stderr}[/red]")
                raise typer.Exit(code=1)
            progress.advance(task_id)
    
    console.print("[green]✓ All packages installed[/green]")


@app.command()
def lock(
    update: bool = typer.Option(False, "--update", help="Force update lock file"),
    freeze: bool = typer.Option(False, "--freeze", help="Create immutable lock (exact versions)"),
) -> None:
    """Generate or update lock file with resolved dependencies."""
    
    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    lock_path = project_dir / "pydepm.lock"
    
    if not pyproject_path.exists():
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    console.print("[bold]Generating lock file[/bold]")
    
    # Load dependencies
    try:
        data = _load_pyproject(pyproject_path)
        project = data.get("project", {})
        deps = project.get("dependencies", [])
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    
    # Resolve
    progress = _make_progress()
    with progress:
        task_id = progress.add_task("Resolving dependencies...", total=100)
        success, resolved, errors = _run_resolver(deps)
        progress.update(task_id, completed=100)
    
    if not success:
        console.print("[red]Resolution failed:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        raise typer.Exit(code=1)
    
    # Create lock file
    try:
        from pydepm.core.resolver import ResolutionResult
        
        # Create a result object
        result = ResolutionResult(success=True, resolved=resolved)
        lock = LockFile.from_resolution(result, pyproject_path)
        
        # Save lock file
        lock.save(lock_path, format="toml")
        console.print(f"[green]✓ Lock file created: {lock_path}[/green]")
        
        # Show stats
        console.print(f"[dim]Locked {len(resolved)} packages[/dim]")
    except Exception as e:
        console.print(f"[red]Error creating lock file: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def list_deps(
    tree: bool = typer.Option(False, "--tree", "-t", help="Show dependency tree"),
    outdated: bool = typer.Option(False, "--outdated", "-o", help="Show outdated packages"),
    group: str = typer.Option("", "--group", "-g", help="Show specific group"),
) -> None:
    """List project dependencies."""
    
    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    
    if not pyproject_path.exists():
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    try:
        data = _load_pyproject(pyproject_path)
        project = data.get("project", {})
        deps_dict = {
            "dependencies": project.get("dependencies", []),
            **project.get("optional-dependencies", {})
        }
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    
    # Show dependencies
    table = Table(show_header=True, header_style="bold cyan", title="Project Dependencies")
    table.add_column("Package", style="green")
    table.add_column("Specifier", style="yellow")
    
    for group_name, packages in deps_dict.items():
        if group and group != group_name:
            continue
        
        if packages:
            table.add_row(f"[bold]{group_name}[/bold]", "", style="dim")
            for pkg_spec in packages:
                # Parse package name and version
                for sep in [">=", "<=", "==", "!=", "~=", ">"]:
                    if sep in pkg_spec:
                        name, version = pkg_spec.split(sep, 1)
                        table.add_row(f"  {name.strip()}", f"{sep}{version}")
                        break
                else:
                    table.add_row(f"  {pkg_spec}", "")
    
    console.print(table)


@app.command()
def audit(
    security: bool = typer.Option(False, "--security", "-S", help="Check for CVE vulnerabilities"),
    conflicts: bool = typer.Option(False, "--conflicts", "-C", help="Check for version conflicts"),
) -> None:
    """Audit project dependencies for issues."""
    
    project_dir = Path.cwd()
    python_exe, env_vars = _get_python_executable(project_dir)
    
    console.print("[bold]Running dependency audit[/bold]")
    
    # Check for conflicts
    if not security or conflicts:
        console.print("\n[bold cyan]Checking for conflicts...[/bold cyan]")
        result = subprocess.run(
            [python_exe, "-m", "pip", "check"],
            env=env_vars,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            console.print("[green]✓ No conflicts found[/green]")
        else:
            console.print("[red]✗ Conflicts detected:[/red]")
            console.print(result.stdout)
    
    # Check for security issues
    if security:
        console.print("\n[bold cyan]Checking for security issues...[/bold cyan]")
        result = subprocess.run(
            [python_exe, "-m", "pip_audit"],
            env=env_vars,
            capture_output=True,
            text=True
        )
        
        if "No known security vulnerabilities found" in result.stdout or result.returncode == 0:
            console.print("[green]✓ No security issues found[/green]")
        else:
            console.print("[yellow]Security issues found:[/yellow]")
            console.print(result.stdout)


@app.command()
def build(
    wheel: bool = typer.Option(False, "-w", "--wheel", help="Build wheel only"),
    sdist: bool = typer.Option(False, "-s", "--sdist", help="Build sdist only"),
) -> None:
    """Build project distributions."""
    
    project_dir = Path.cwd()
    cfg = core_config.load_project_config(project_dir)
    
    if cfg is None:
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    console.print(f"[bold]Building {cfg.project_type} project[/bold]")
    
    try:
        if cfg.project_type == "module":
            dist_dir = core_build.build_module(project_dir, cfg)
        else:
            dist_dir = core_build.build_app(project_dir, cfg)
        
        console.print(f"[green]✓ Build complete[/green]")
        console.print(f"[dim]Artifacts: {dist_dir}[/dim]")
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def run(
    script: Optional[str] = typer.Argument(None, help="Script name to run"),
) -> None:
    """Run a project script."""
    
    project_dir = Path.cwd()
    cfg = core_config.load_project_config(project_dir)
    
    if cfg is None:
        console.print("[red]Error: No pyproject.toml found[/red]")
        raise typer.Exit(code=1)
    
    if not cfg.scripts:
        console.print("[yellow]No scripts defined[/yellow]")
        raise typer.Exit(code=0)
    
    if script is None:
        script = questionary.select(
            "Select a script:",
            choices=list(cfg.scripts.keys()),
            style=questionary_style,
        ).ask()
        
        if script is None:
            raise typer.Abort()
    
    if script not in cfg.scripts:
        console.print(f"[red]Script '{script}' not found[/red]")
        raise typer.Exit(code=1)
    
    cmd = cfg.scripts[script]
    console.print(f"[dim]Running: {cmd}[/dim]")
    
    env_vars = os.environ.copy()
    python_exe, venv_env = _get_python_executable(project_dir)
    env_vars.update(venv_env)
    
    try:
        result = subprocess.run(cmd, shell=True, env=env_vars)
        raise typer.Exit(code=result.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        raise typer.Exit(code=130)


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    app()
