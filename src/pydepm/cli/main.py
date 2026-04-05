from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

import typer
import questionary
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table
from rich.text import Text
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydepm import __version__
from pydepm.core.proc import run_with_ticks

from pydepm.core import config as core_config
from pydepm.core import envs as core_envs
from pydepm.core import build as core_build
from pydepm.core import deps as core_deps
from pydepm.core import python_sniffer
from pydepm.core import integration
from pydepm.core import lock as core_lock

app = typer.Typer(
    help="pydep - All-in-one Python dependency and project manager",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()

# Estilos para questionary prompts usando prompt_toolkit Style
from prompt_toolkit.styles import Style as PTStyle
questionary_style = PTStyle.from_dict({
    "questionmark": "bold fg:cyan",
    "selected": "bold fg:green",
    "pointer": "bold fg:cyan",
    "answer": "bold fg:magenta",
})


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def _run_steps_with_progress(steps: list[tuple[str, callable]]) -> None:
    """Run sequential steps showing a progress bar with real step completion."""

    progress = _make_progress()
    task_id = progress.add_task("Working...", total=len(steps))
    with progress:
        for description, fn in steps:
            progress.update(task_id, description=description)
            fn()
            progress.advance(task_id)


def _run_callable_with_smooth_progress(*, description: str, fn: callable) -> None:
    """Run a Python callable while showing a smooth progress bar.

    This is for operations where we cannot observe real progress, but we still
    want a bar that doesn't jump from 0% to 100%.
    """

    import threading
    import time

    progress = _make_progress()
    task_id = progress.add_task(description, total=100)
    done = threading.Event()
    error: dict = {}

    def _runner() -> None:
        try:
            fn()
        except BaseException as exc:  # pragma: no cover
            error["exc"] = exc
        finally:
            done.set()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()

    start = time.time()
    current = 0.0
    with progress:
        while not done.is_set():
            # Ease-out toward 95%: fast at start, slow near the end.
            # Uses exponential decay to approach 95.
            elapsed = time.time() - start
            target = 95.0 * (1.0 - pow(0.78, elapsed / 0.25))
            if target > current:
                current = min(95.0, target)
                progress.update(task_id, completed=current)
            time.sleep(0.1)

        progress.update(task_id, completed=100)

        # Avoid "blink" for very fast operations.
        elapsed = time.time() - start
        if elapsed < 0.4:
            time.sleep(0.4 - elapsed)

    t.join()
    if "exc" in error:
        raise error["exc"]


def _run_command_with_smooth_progress(
    *,
    description: str,
    args: list[str],
    cwd: str | None = None,
    env: dict | None = None,
) -> tuple[int, str, str]:
    """Run a command while a progress bar advances smoothly.

    Since most external tools don't provide progress, we advance up to 95%
    while the process is running, then finish to 100% when it exits.
    """

    import time

    progress = _make_progress()

    task_id = progress.add_task(description, total=100)
    start = time.time()
    current = {"value": 0.0}

    def _tick() -> None:
        # Ease-out toward 95% while process is running.
        elapsed = time.time() - start
        target = 95.0 * (1.0 - pow(0.78, elapsed / 0.25))
        if target > current["value"]:
            current["value"] = min(95.0, target)
            progress.update(task_id, completed=current["value"])

    with progress:
        result = run_with_ticks(
            args,
            cwd=cwd,
            env=env,
            tick=_tick,
            tick_interval_seconds=0.1,
        )
        progress.update(task_id, completed=100)

        # Avoid "blink" for very fast operations.
        elapsed = time.time() - start
        if elapsed < 0.4:
            time.sleep(0.4 - elapsed)

    return result.returncode, result.stdout, result.stderr


def _fetch_pypi_metadata_progress(names: list[str], max_workers: int = 8) -> dict:
    """Fetch PyPI metadata in parallel with a progress bar."""

    results: dict = {}
    unique = []
    seen = set()
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)

    progress = _make_progress()
    task_id = progress.add_task("Fetching PyPI metadata...", total=len(unique))

    with progress, ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(core_deps.fetch_pypi_metadata, name): name for name in unique}
        for fut in as_completed(future_map):
            name = future_map[fut]
            try:
                results[name] = fut.result()
            except core_deps.DependencyError:
                pass
            progress.advance(task_id)

    return results


def _load_env_file(path: Path) -> dict:
    env: dict = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _save_env_file(path: Path, env: dict) -> None:
    lines = []
    for key, value in env.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_python_for_deps_ops(project_dir: Path, use_global: bool) -> tuple[str, dict]:
    """Return (python_executable, env_vars) for pip/twine operations."""

    env_vars = os.environ.copy()
    python_executable = os.sys.executable

    if use_global:
        return python_executable, env_vars

    cfg = core_config.load_project_config(project_dir)
    if cfg is None:
        return python_executable, env_vars

    env_path = core_envs.get_env_path(project_dir, cfg.env_type)
    if env_path is None:
        if cfg.env_type == "venv":
            console.print(
                "[yellow]Warning:[/] your project is configured to use a venv environment in [tool.pydepm.env].type,"
            )
            console.print(
                "[yellow]Warning:[/] but the .venv directory is not present in your project root."
            )
            create_venv = Confirm.ask(
                "Would you like pydep to create the missing .venv now?",
                default=True,
            )
            if create_venv:
                try:
                    _run_steps_with_progress(
                        [("Creating environment...", lambda: core_envs.create_environment(project_dir, cfg.env_type))]
                    )
                except core_envs.EnvCreationError as exc:  # type: ignore[attr-defined]
                    console.print(f"[red bold]Environment creation failed:[/] {exc}")
                    raise typer.Exit(code=1)
                env_path = core_envs.get_env_path(project_dir, cfg.env_type)
                if env_path is None:
                    console.print("[red bold]Error:[/] .venv was not created.")
                    raise typer.Exit(code=1)
            else:
                console.print(
                    "[yellow]Skipping dependency operation.[/] You can create the venv later, or change [tool.pydepm.env].type to 'global'."
                )
                raise typer.Exit(code=0)
        else:
            return python_executable, env_vars

    bin_dir = core_envs.get_env_bin_dir(env_path)
    env_vars["VIRTUAL_ENV"] = str(env_path)
    env_vars["PATH"] = f"{bin_dir}{os.pathsep}" + env_vars.get("PATH", "")
    python_executable = str(bin_dir / "python")
    return python_executable, env_vars

CORE_DEPENDENCY_PROTECTION = {
    "typer",
    "rich",
    "build",
    "packaging",
    "requests",
    "tomlkit",
    "questionary",
}


def _is_protected_core_dependency(name: str) -> bool:
    parsed = core_deps.parse_requirement_name(name) or name
    normalized = parsed.lower().replace("_", "-")
    return normalized in CORE_DEPENDENCY_PROTECTION


def _print_main_help() -> None:
    """Render a rich, colorful help message for the pydep CLI."""

    console.print("[bold magenta]>> pydep[/bold magenta] - All-in-one Python dependency and project manager")
    console.print()
    console.print("[bold]Usage[/bold]")
    console.print("  [green]pydep[/green] [cyan]COMMAND[/cyan] [dim][OPTIONS][/dim]")
    console.print()

    console.print("[bold]Commands[/bold]")
    console.print("  [green]init[/green]     Initialize a new pydep-managed project (pyproject.toml, .gitignore, env)")
    console.print("  [green]run[/green]      Run a script defined under [tool.pydepm.scripts]")
    console.print("  [green]build[/green]    Build project artifacts (modules via python -m build, apps via PyInstaller)")
    console.print("  [green]add[/green]      Add a dependency to pyproject.toml and install it")
    console.print("  [green]remove[/green]   Remove a dependency from pyproject.toml and uninstall it")
    console.print("  [green]update[/green]   Update (or add) a dependency and install the new spec")
    console.print("  [green]install[/green]  Install all project dependencies (optionally include dev/optional groups)")
    console.print("  [green]deps[/green]     List all project dependencies by group")
    console.print("  [green]publish[/green]  Build and upload distributions to PyPI or TestPyPI")
    console.print("  [green]audit[/green]    Audit dependencies (missing/outdated/conflicts via pip check)")
    console.print("  [green]fix[/green]      Fix dependency issues (pip install + pip check, use --force for aggressive)")
    console.print("  [green]lock[/green]     Generate pydep.lock with resolved dependency versions")
    console.print()

    console.print("[bold]Global options[/bold]")
    console.print("  [cyan]-h[/cyan], [cyan]--help[/cyan]       Show this help message and exit")
    console.print("  [cyan]-v[/cyan], [cyan]--version[/cyan]   Show version and exit")
    console.print()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        is_eager=True,
    ),
    help: bool = typer.Option(  # noqa: A002 - follow Typer naming
        False,
        "--help",
        "-h",
        help="Show this message and exit.",
        is_eager=True,
    ),
) -> None:
    """Main entrypoint for the pydep CLI.

    We override the default Typer help to provide a richer overview when pydep
    is invoked without a command or with --help/-h at the top level.
    """

    if version:
        console.print(f"[bold]pydep[/bold] version [green]{__version__}[/green]")
        raise typer.Exit()
    
    if help or ctx.invoked_subcommand is None:
        _print_main_help()
        raise typer.Exit()


@app.command()
def init(
    name: Optional[str] = typer.Argument(
        None,
        help="Project name or path. Use ./ for the current directory.",
    ),
    type: Optional[str] = typer.Option(
        None,
        "--type",
        case_sensitive=False,
        help="Project type: module or app.",
    ),
    env: Optional[str] = typer.Option(
        None,
        "--env",
        case_sensitive=False,
        help="Environment type: venv, conda or global. If omitted, you will be asked.",
    ),
    global_deps: bool = typer.Option(
        False,
        "--global-deps",
        help="Do not create an environment; use the global Python.",
    ),
    yes: bool = typer.Option(
        False,
        "-y",
        "--yes",
        help="Accept all defaults without prompting.",
    ),
) -> None:
    """Initialize a new project managed by pydep."""

    cwd = Path.cwd()

    # Determine target directory
    if name is None or name in {".", "./"}:
        target_dir = cwd
    else:
        target_dir = cwd / name

    project_exists = target_dir.exists() and any(target_dir.iterdir())
    if target_dir != cwd and not target_dir.exists():
        console.print(f"[bold cyan]Creating directory[/bold cyan] [blue]{target_dir}[/blue]")
        target_dir.mkdir(parents=True, exist_ok=True)
    elif project_exists:
        console.print(
            f"[yellow bold]![/yellow bold] [yellow]Warning:[/] directory [blue]{target_dir}[/blue] is not empty."
        )
        if not yes and not Confirm.ask(
            "Continue anyway?", default=False
        ):
            raise typer.Abort()

    # Project name
    if target_dir == cwd:
        default_name = cwd.name
    else:
        default_name = target_dir.name

    if yes:
        project_name = default_name
    else:
        project_name = Prompt.ask(
            "Project name", default=default_name
        )

    # Normalize options
    if type is None and not yes:
        proj_type_choice = questionary.select(
            "Project type:",
            choices=["module", "app"],
            default="module",
            style=questionary_style,
        ).ask()
        if proj_type_choice is None:
            raise typer.Abort()
        proj_type = proj_type_choice.lower()
    else:
        proj_type = (type or "module").lower()

    if global_deps:
        env_type = "global"
    else:
        if env is None and not yes:
            # Ask interactively for environment type
            env_type = questionary.select(
                "Environment type:",
                choices=["venv", "conda", "global"],
                default="venv",
                style=questionary_style,
            ).ask()
            if env_type is None:
                raise typer.Abort()
        else:
            env_type = (env or "venv").lower()

    # Python version selection
    python_version = None
    if not yes:
        available_versions = python_sniffer.get_python_versions()
        if available_versions:
            version_choices = [f"Python {v[0]}" for v in available_versions]
            selected_version = questionary.select(
                "Python version:",
                choices=version_choices,
                default=version_choices[0] if version_choices else None,
                style=questionary_style,
            ).ask()
            if selected_version:
                # Extract version string from "Python X.Y.Z"
                python_version = selected_version.replace("Python ", "").strip()
        else:
            console.print("[yellow]No Python versions detected on system. Using current Python.[/yellow]")
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    else:
        # Default to current Python when --yes
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    if proj_type not in {"module", "app"}:
        console.print("[red bold]Error:[/] --type must be 'module' or 'app'.")
        raise typer.Exit(code=1)

    if env_type not in {"venv", "conda", "global"}:
        console.print("[red bold]Error:[/] --env must be 'venv', 'conda' or 'global'.")
        raise typer.Exit(code=1)

    console.print(
        f"[bold]Initializing project[/bold] [green]{project_name}[/green] (Python {python_version}) in [blue]{target_dir}[/blue]"
    )

    # Create environment if needed (before writing project files)
    if env_type != "global":
        try:
            _run_callable_with_smooth_progress(
                description="Creating environment...",
                fn=lambda: core_envs.create_environment(target_dir, env_type),
            )
        except core_envs.EnvCreationError as exc:  # type: ignore[attr-defined]
            console.print(f"[red bold]Environment creation failed:[/] {exc}")
            raise typer.Exit(code=1)

    # Create/update pyproject.toml and .gitignore only after env is ready
    core_config.bootstrap_project(
        target_dir=target_dir,
        project_name=project_name,
        project_type=proj_type,
        env_type=env_type,
        python_version=python_version,
    )

    # Create main.py entry point (both module and app projects need it)
    main_py = target_dir / "main.py"
    if not main_py.exists():
        if proj_type == "app":
            main_py.write_text("""#!/usr/bin/env python3
\"\"\"Main entry point for the application.\"\"\"

def main():
    print("Hello from your pydep app!")

if __name__ == "__main__":
    main()
""", encoding="utf-8")
        else:
            # Module project - create a simple dev script
            main_py.write_text(f"""#!/usr/bin/env python3
\"\"\"Development entry point for {project_name}.\"\"\"

from src.{project_name.replace('-', '_')} import __version__

def main():
    print(f"Hello from {{__version__}}")

if __name__ == "__main__":
    main()
""", encoding="utf-8")
        console.print(f"[green]Created [blue]main.py[/blue] entry point.[/green]")

    console.print(
        "[bold green]>> Project initialized successfully![/bold green]"
    )
    console.print(f"[dim]Created:[/]")
    console.print(f"  [cyan]pyproject.toml[/cyan]")
    console.print(f"  [cyan].gitignore[/cyan]")
    console.print(f"  [cyan]src/{project_name.replace('-', '_')}/[/cyan] - Package directory")
    console.print(f"  [cyan]tests/[/cyan] - Test directory with basic test")
    console.print(f"  [cyan]main.py[/cyan] - Entry point")
    if env_type != "global":
        env_path = ".venv" if env_type == "venv" else "conda environment"
        console.print(f"  [cyan]{env_path}[/cyan] - {env_type.capitalize()} environment")


@app.command()
def run(
    script: Optional[str] = typer.Argument(
        None, help="Script name defined under [tool.pydepm.scripts].",
    ),
) -> None:
    """Run a script defined in the project configuration."""

    project_dir = Path.cwd()
    cfg = core_config.load_project_config(project_dir)

    if cfg is None:
        console.print(
            "[red bold]Error:[/] No pyproject.toml with [tool.pydepm] section was found."
        )
        raise typer.Exit(code=1)

    if not cfg.scripts:
        console.print(
            "[yellow]No scripts defined under [tool.pydepm.scripts].[/yellow]"
        )
        raise typer.Exit(code=0)

    if script is None:
        console.print("[bold cyan]Available scripts:[/bold cyan]")
        script_choices = list(cfg.scripts.keys())
        selected_script = questionary.select(
            "Select a script to run:",
            choices=script_choices,
            style=questionary_style,
        ).ask()
        if selected_script is None:
            raise typer.Abort()
        script = selected_script

    if script not in cfg.scripts:
        console.print(
            f"[red bold]Error:[/] script '[white]{script}[/white]' is not defined."
        )
        raise typer.Exit(code=1)

    cmd = cfg.scripts[script]
    console.print(
        f"[bold]Running script[/bold] [green]{script}[/green]: [dim]{cmd}[/dim]"
    )

    env_path = core_envs.get_env_path(project_dir, cfg.env_type)
    env_vars = os.environ.copy()
    if env_path is not None:
        # Ajustar PATH y VIRTUAL_ENV para usar el entorno
        bin_dir = core_envs.get_env_bin_dir(env_path)
        env_vars["VIRTUAL_ENV"] = str(env_path)
        env_vars["PATH"] = f"{bin_dir}{os.pathsep}" + env_vars.get("PATH", "")

    try:
        subprocess.run(cmd, shell=True, check=True, env=env_vars)
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[red bold]Error:[/] script '[white]{script}[/white]' exited with code {exc.returncode}."
        )
        raise typer.Exit(code=exc.returncode)


@app.command()
def build() -> None:
    """Build project artifacts (modules or apps)."""

    project_dir = Path.cwd()
    cfg = core_config.load_project_config(project_dir)

    if cfg is None:
        console.print(
            "[red bold]Error:[/] No pyproject.toml with [tool.pydepm] section was found."
        )
        raise typer.Exit(code=1)

    if cfg.project_type == "module":
        console.print(
            f"[bold]Building module project[/bold] [green]{cfg.name}[/green] in [blue]{project_dir}[/blue]"
        )

        try:
            dist_dir = None

            def _do_build() -> None:
                nonlocal dist_dir
                dist_dir = core_build.build_module(project_dir, cfg)

            _run_callable_with_smooth_progress(
                description="Building distributions (sdist, wheel)...",
                fn=_do_build,
            )
            dist_dir = dist_dir  # type: ignore[assignment]
        except core_build.BuildError as exc:  # type: ignore[attr-defined]
            console.print(
                f"[red bold]Build failed:[/] {exc}"
            )
            raise typer.Exit(code=1)

        console.print(
            f"[bold green]✔ Build completed.[/bold green] Artifacts written to [blue]{dist_dir}[/blue]"
        )

    elif cfg.project_type == "app":
        console.print(
            f"[bold]Building app project[/bold] [green]{cfg.name}[/green] in [blue]{project_dir}[/blue]"
        )

        try:
            dist_dir = None

            def _do_build_app() -> None:
                nonlocal dist_dir
                dist_dir = core_build.build_app(project_dir, cfg)

            _run_callable_with_smooth_progress(
                description="Running PyInstaller build...",
                fn=_do_build_app,
            )
            dist_dir = dist_dir  # type: ignore[assignment]
        except core_build.BuildError as exc:  # type: ignore[attr-defined]
            console.print(
                f"[red bold]Build failed:[/] {exc}"
            )
            raise typer.Exit(code=1)

        console.print(
            f"[bold green]✔ App build completed.[/bold green] Artifacts written to [blue]{dist_dir}[/blue]"
        )
    else:
        console.print(
            f"[red bold]Error:[/] Unsupported project_type='{cfg.project_type}'. Expected 'module' or 'app'."
        )
        raise typer.Exit(code=1)


@app.command()
def add(
    spec: str = typer.Argument(
        ..., help="Dependency spec, e.g. 'requests>=2.0' or 'rich'.",
    ),
    save_dev: bool = typer.Option(
        False,
        "-D",
        "--save-dev",
        help="Add to dev-dependencies instead of project.dependencies.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use the global Python/pip instead of the project environment.",
    ),
    group: str = typer.Option(
        "",
        "-G",
        "--group",
        help="Optional-dependencies group name (PEP 621).",
    ),
    force: bool = typer.Option(
        False,
        "-F",
        "--force",
        help="Force add even if already declared in pyproject.toml.",
    ),
) -> None:
    """Add a dependency to pyproject.toml and install it."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    req_name = core_deps.parse_requirement_name(spec) or spec
    
    changed = False
    if not force:
        declared = core_deps.get_declared_spec(
            pyproject_path,
            str(req_name),
            group=group or None,
            dev=save_dev,
        )

        if declared is None:
            try:
                change = core_deps.add_dependency(
                    pyproject_path,
                    spec,
                    group=group or None,
                    dev=save_dev,
                )
            except core_deps.DependencyError as exc:  # type: ignore[attr-defined]
                console.print(f"[red bold]✗ Error updating pyproject.toml:[/] {exc}")
                raise typer.Exit(code=1)
            changed = bool(change.added)
            section_name = "[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]")
            if changed:
                console.print(f"[bold green]>> Added[/bold green] [green]{spec}[/green] to {section_name}")
        elif core_deps.should_update_spec(declared, spec):
            try:
                change = core_deps.update_dependency(
                    pyproject_path,
                    spec,
                    group=group or None,
                    dev=save_dev,
                )
            except core_deps.DependencyError as exc:  # type: ignore[attr-defined]
                console.print(f"[red bold]!! Error updating pyproject.toml:[/] {exc}")
                raise typer.Exit(code=1)
            changed = bool(change.added or change.updated)
            if changed:
                section_name = "[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]")
                console.print(f"[bold green]>> Updated[/bold green] {section_name}: [green]{declared}[/green] -> [green]{spec}[/green]")
        else:
            # Already declared without needing changes - nothing to do
            section_name = "[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]")
            console.print(f"[cyan]ℹ[/cyan] Dependency [green]{declared}[/green] already in {section_name}")
            raise typer.Exit(code=0)
    else:
        # Force mode: directly add/update without checking
        try:
            change = core_deps.add_dependency(
                pyproject_path,
                spec,
                group=group or None,
                dev=save_dev,
            )
            if not (change.added or change.updated):
                change = core_deps.update_dependency(
                    pyproject_path,
                    spec,
                    group=group or None,
                    dev=save_dev,
                )
            changed = True
            section_name = "[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]")
            action = "added" if change.added else "updated"
            console.print(f"[bold green]{action.capitalize()}[/bold green] [green]{spec}[/green] in {section_name}")
        except core_deps.DependencyError as exc:  # type: ignore[attr-defined]
            console.print(f"[red bold]✗ Error updating pyproject.toml:[/] {exc}")
            raise typer.Exit(code=1)

    if not changed and not use_global and not force:
        raise typer.Exit(code=0)

    # Install in the appropriate environment
    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    env_vars["PIPAPI_PYTHON_LOCATION"] = python_executable

    # Get Python version for resolver
    try:
        version_result = subprocess.run(
            [python_executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_str = version_result.stdout.strip().replace("Python ", "")
        python_version = ".".join(version_str.split(".")[:2])
    except Exception:
        python_version = "3.11"

    try:
        # Resolve using custom resolver
        with console.status(f"[bold cyan]Resolving {spec}...[/bold cyan]", spinner="dots"):
            resolution = integration.resolve_requirements([spec], python_version=python_version)

        if not resolution.success:
            console.print("[red bold]✗ Resolution failed[/red bold]")
            for error in resolution.errors:
                console.print(f"  [red]{error}[/red]")
            raise typer.Exit(code=1)

        # Show resolved version
        if resolution.resolved:
            resolved_pkg = next(iter(resolution.resolved.values()))
            console.print(f"[cyan]→[/cyan] Resolved to version [green]{resolved_pkg.version}[/green]")

        # Install using new progress function
        pip_args = core_deps.build_pip_install_args([spec])
        if not _install_specs_with_progress([spec], python_executable, env_vars):
            raise typer.Exit(code=1)

        # Verify environment
        check_rc, check_out = _pip_check(python_executable, env_vars)
        if check_rc != 0:
            console.print("[yellow]⚠ Environment check warnings:[/yellow]")
            console.print(check_out)

        # Get exact installed version and save to pyproject.toml
        installed_version = _get_installed_version(str(req_name), python_executable, env_vars)
        if installed_version:
            exact_spec = _make_exact_spec(str(req_name), installed_version)
            try:
                core_deps.update_dependency(
                    pyproject_path,
                    exact_spec,
                    group=group or None,
                    dev=save_dev,
                )
                console.print(f"[cyan]→[/cyan] Saved exact version: [green]{exact_spec}[/green]")
            except Exception:
                pass

        # Update lock file
        _update_lockfile_with_installed(project_dir, pyproject_path, python_executable, env_vars)
        
        console.print(f"[bold green]✔ Dependency {req_name} installed successfully![/bold green]")

    except subprocess.CalledProcessError as exc:
        console.print(f"[red bold]✗ Installation failed[/red bold] (exit code {exc.returncode})")
        raise typer.Exit(code=exc.returncode)


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Package name to remove (not full spec).",
    ),
    save_dev: bool = typer.Option(
        False,
        "-D",
        "--save-dev",
        help="Remove from dev-dependencies instead of project.dependencies.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use the global Python/pip instead of the project environment.",
    ),
    group: str = typer.Option(
        "",
        "-G",
        "--group",
        help="Optional-dependencies group name (PEP 621).",
    ),
    force: bool = typer.Option(
        False,
        "-F",
        "--force",
        help="Force remove even if not declared in pyproject.toml.",
    ),
) -> None:
    """Remove a dependency from pyproject.toml and uninstall it with pip."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    cfg = core_config.load_project_config(project_dir)
    using_global_env = use_global or (cfg is not None and cfg.env_type == "global")

    if using_global_env and _is_protected_core_dependency(name):
        console.print(
            f"[red bold]Error:[/] Removing '{name}' is blocked in a global/shared environment because it is required by pydep itself."
        )
        console.print(
            "[yellow]Tip:[/] Use a venv or conda environment, or set [tool.pydepm.env].type to 'venv' or 'conda'."
        )
        raise typer.Exit(code=1)

    if not force:
        change = core_deps.remove_dependency(
            pyproject_path,
            name,
            group=group or None,
            dev=save_dev,
        )

        if not change.removed:
            console.print("[yellow]No matching dependency found to remove.[/yellow]")
            raise typer.Exit(code=0)

        console.print(
            f"[bold]Removed dependency[/bold] [red]{', '.join(change.removed)}[/red] from "
            + ("[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]"))
        )
    else:
        # Force mode: attempt remove regardless, but don't fail if not found
        try:
            change = core_deps.remove_dependency(
                pyproject_path,
                name,
                group=group or None,
                dev=save_dev,
            )
            if change.removed:
                console.print(
                    f"[bold]Force removed[/bold] [red]{', '.join(change.removed)}[/red] from "
                    + ("[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]"))
                )
            else:
                console.print("[cyan]ℹ[/cyan] Package not found in pyproject.toml, proceeding with uninstall...")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] {e}")
            console.print("[cyan]ℹ[/cyan] Proceeding with uninstall...")

    # Uninstall with pip in the appropriate environment
    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    env_vars["PIPAPI_PYTHON_LOCATION"] = python_executable

    pip_args = core_deps.build_pip_uninstall_args([name])

    def _pip_uninstall() -> None:
        code, out, err = _run_command_with_smooth_progress(
            description="pip uninstall",
            args=[python_executable, *pip_args],
            env=env_vars,
        )
        if code != 0:
            raise subprocess.CalledProcessError(code, [python_executable, *pip_args], output=out, stderr=err)

    def _pip_verify() -> None:
        check_rc, check_out = _pip_check(python_executable, env_vars)
        if check_rc != 0:
            raise subprocess.CalledProcessError(check_rc, [python_executable, "-m", "pip", "check"], output=check_out, stderr="")

    try:
        _run_steps_with_progress(
            [
                ("Uninstalling dependency...", _pip_uninstall),
                ("Verifying environment (pip check)...", _pip_verify),
            ]
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        out = (exc.output or "").strip() if isinstance(exc.output, str) else ""
        console.print(
            f"[red bold]Dependency uninstall failed[/red bold] (exit code {exc.returncode})."
        )
        if stderr:
            console.print("[red]--- stderr ---[/red]")
            console.print(stderr)
        elif out:
            console.print("[red]--- output ---[/red]")
            console.print(out)
        raise typer.Exit(code=exc.returncode)

    console.print("[bold green]✔ Dependency uninstalled successfully.[/bold green]")


@app.command()
def update(
    spec: Optional[str] = typer.Argument(
        None, help="Updated dependency spec, e.g. 'requests>=2.3'. Omit to update all dependencies.",
    ),
    save_dev: bool = typer.Option(
        False,
        "-D",
        "--save-dev",
        help="Operate on dev-dependencies instead of project.dependencies.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use the global Python/pip instead of the project environment.",
    ),
    group: str = typer.Option(
        "",
        "-G",
        "--group",
        help="Optional-dependencies group name (PEP 621).",
    ),
    yes: bool = typer.Option(
        False,
        "-y",
        "--yes",
        help="Skip confirmation when updating all dependencies.",
    ),
    force: bool = typer.Option(
        False,
        "-F",
        "--force",
        help="Force update even if not declared or skip outdated check.",
    ),
) -> None:
    """Update (or add) a dependency and run pip install for the new spec.
    
    If no spec is provided, updates all dependencies to their latest versions.
    """

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    # If no spec provided, update all dependencies
    if spec is None:
        _update_all_dependencies(
            project_dir=project_dir,
            pyproject_path=pyproject_path,
            use_global=use_global,
            save_dev=save_dev,
            group=group,
            skip_confirmation=yes,
            skip_outdated_check=force,
        )
        return

    # Single dependency update (existing logic)
    pkg_name = core_deps.parse_requirement_name(spec) or spec
    
    # First check if spec is already declared
    declared = core_deps.get_declared_spec(
        pyproject_path,
        str(pkg_name),
        group=group or None,
        dev=save_dev,
    )
    
    # If already declared with same spec and not in force mode, exit
    if declared and not core_deps.should_update_spec(declared, spec) and not force:
        console.print(f"[yellow]ℹ Dependency [green]{declared}[/green] already matches spec - no changes needed.[/yellow]")
        raise typer.Exit(code=0)
    
    # Now update or add in pyproject.toml
    change = None
    try:
        change = core_deps.update_dependency(
            pyproject_path,
            spec,
            group=group or None,
            dev=save_dev,
        )
        if not (change.added or change.updated) and not force:
            # update_dependency returned no changes
            change.added = False
            change.updated = False
    except core_deps.DependencyError as exc:  # type: ignore[attr-defined]
        if not force:
            console.print(f"[red bold]Error updating pyproject.toml:[/] {exc}")
            raise typer.Exit(code=1)
        else:
            # In force mode, try to add even if update fails
            try:
                change = core_deps.add_dependency(
                    pyproject_path,
                    spec,
                    group=group or None,
                    dev=save_dev,
                )
            except core_deps.DependencyError as exc2:
                console.print(f"[red bold]Error:[/] {exc2}")
                raise typer.Exit(code=1)

    if change and (change.added or change.updated or force):
        action = "added" if change.added else "updated"
        console.print(
            f"[bold]{action.capitalize()} dependency[/bold] [green]{spec}[/green] in "
            + ("[cyan]dev-dependencies[/cyan]" if save_dev else (f"group [cyan]{group}[/cyan]" if group else "[cyan]dependencies[/cyan]"))
        )

    # Install updated spec with pip in the appropriate environment
    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    env_vars["PIPAPI_PYTHON_LOCATION"] = python_executable

    # Install using new progress function with --upgrade flag
    if not _install_specs_with_progress([spec], python_executable, env_vars, upgrade=True):
        raise typer.Exit(code=1)

    # Verify environment
    check_rc, check_out = _pip_check(python_executable, env_vars)
    if check_rc != 0:
        console.print("[yellow]⚠ Environment check warnings:[/yellow]")
        console.print(check_out)

    # Get exact installed version and save to pyproject.toml
    pkg_name = core_deps.parse_requirement_name(spec) or spec
    installed_version = _get_installed_version(str(pkg_name), python_executable, env_vars)
    if installed_version:
        exact_spec = _make_exact_spec(str(pkg_name), installed_version)
        try:
            core_deps.update_dependency(
                pyproject_path,
                exact_spec,
                group=group or None,
                dev=save_dev,
            )
            console.print(f"[cyan]→[/cyan] Saved exact version: [green]{exact_spec}[/green]")
        except Exception:
            pass

    # Update lock file
    _update_lockfile_with_installed(project_dir, pyproject_path, python_executable, env_vars)
    
    console.print("[bold green]✔ Dependency updated successfully.[/bold green]")


@app.command()
def deps(
    tree: bool = typer.Option(
        False,
        "--tree",
        "-t",
        help="Show dependency tree structure.",
    ),
    all_groups: bool = typer.Option(
        False,
        "--all-groups",
        "-A",
        help="Include all optional-dependencies groups.",
    ),
    group: str = typer.Option(
        "",
        "--group",
        "-G",
        help="Show specific optional-dependencies group.",
    ),
    include_dev: bool = typer.Option(
        False,
        "--include-dev",
        "-D",
        help="Include dev-dependencies.",
    ),
) -> None:
    """List project dependencies from pyproject.toml."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        console.print(f"[red bold]Error reading pyproject.toml:[/] {e}")
        raise typer.Exit(code=1)

    project = data.get("project", {})
    tool_pydepm = data.get("tool", {}).get("pydepm", {})

    # Collect dependencies
    deps_map: dict[str, list[str]] = {}
    
    # Main dependencies
    main_deps = project.get("dependencies", [])
    if main_deps:
        deps_map["dependencies"] = main_deps

    # Dev dependencies (from tool.pydepm)
    if include_dev:
        dev_deps = tool_pydepm.get("dev-dependencies", [])
        if dev_deps:
            deps_map["dev-dependencies"] = dev_deps

    # Optional dependencies
    optional_deps = project.get("optional-dependencies", {})
    if optional_deps:
        if all_groups:
            deps_map.update(optional_deps)
        elif group:
            if group in optional_deps:
                deps_map[group] = optional_deps[group]
            else:
                console.print(f"[yellow]Group '{group}' not found.[/yellow]")
        else:
            deps_map.update(optional_deps)

    if not deps_map:
        console.print("[yellow]No dependencies found.[/yellow]")
        raise typer.Exit(code=0)

    # Display as table
    table = Table(title="Project Dependencies", show_lines=False)
    table.add_column("Group", style="bold cyan")
    table.add_column("Package", style="green")
    table.add_column("Version Spec", style="yellow")

    for group_name in sorted(deps_map.keys()):
        packages = deps_map[group_name]
        is_first = True
        for pkg_spec in packages:
            # Parse package name and version spec
            name = pkg_spec
            version_spec = ""
            for sep in [">=", "<=", "==", "!=", "~=", ">", "<"]:
                if sep in pkg_spec:
                    parts = pkg_spec.split(sep, 1)
                    name = parts[0].strip()
                    version_spec = sep + parts[1].strip()
                    break

            if is_first:
                table.add_row(group_name, name, version_spec)
                is_first = False
            else:
                table.add_row("", name, version_spec)

    console.print(table)

    # Show summary
    total = sum(len(pkgs) for pkgs in deps_map.values())
    console.print(f"\n[dim]Total:[/dim] [bold]{total}[/bold] packages in {len(deps_map)} group(s)")


@app.command()
def publish(
    repository: str = typer.Option(
        "",
        "--repository",
        help="Override repository (pypi or testpypi). If omitted, use tool.pydepm.publishing.repository or default to 'pypi'.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use the global Python for building and twine upload instead of the project environment.",
    ),
) -> None:
    """Build and publish distributions to PyPI or TestPyPI using twine.

    Requires an API token stored in .env (PYPI_API_TOKEN or TESTPYPI_API_TOKEN).
    """

    project_dir = Path.cwd()
    cfg = core_config.load_project_config(project_dir)
    if cfg is None:
        console.print(
            "[red bold]Error:[/] No pyproject.toml with [tool.pydepm] section was found."
        )
        raise typer.Exit(code=1)

    # Determine repository (pypi or testpypi)
    repo = repository.strip()
    if not repo:
        pyproject_path = project_dir / "pyproject.toml"
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            repo = (
                data.get("tool", {})
                .get("pydepm", {})
                .get("publishing", {})
                .get("repository", "")
            )
        except Exception:
            repo = ""
    if not repo:
        repo = questionary.select(
            "Select repository:",
            choices=["pypi", "testpypi"],
            default="pypi",
            style=questionary_style,
        ).ask()
        if repo is None:
            raise typer.Abort()
    repo = repo.strip().lower()

    if repo not in {"pypi", "testpypi"}:
        console.print(
            "[red bold]Error:[/] repository must be 'pypi' or 'testpypi'."
        )
        raise typer.Exit(code=1)

    # Build distributions using existing build logic
    console.print(
        f"[bold]Building project[/bold] [green]{cfg.name}[/green] for repository [cyan]{repo}[/cyan]"
    )

    try:
        def _do_build() -> None:
            nonlocal dist_dir
            if cfg.project_type == "module":
                dist_dir = core_build.build_module(project_dir, cfg)
            elif cfg.project_type == "app":
                dist_dir = core_build.build_app(project_dir, cfg)
            else:
                raise core_build.BuildError(
                    f"Unsupported project_type='{cfg.project_type}'. Expected 'module' or 'app'."
                )

        dist_dir = None
        _run_steps_with_progress(
            [("Building distributions...", _do_build)]
        )
        if dist_dir is None:
            raise core_build.BuildError("Build did not produce dist_dir")
    except core_build.BuildError as exc:  # type: ignore[attr-defined]
        console.print(f"[red bold]Build failed:[/] {exc}")
        raise typer.Exit(code=1)

    # Ensure there is something to upload
    dist_files = list(dist_dir.glob("*"))
    if not dist_files:
        console.print(
            f"[red bold]Error:[/] No distribution files found in [blue]{dist_dir}[/blue]."
        )
        raise typer.Exit(code=1)

    # Handle .env and API tokens
    env_file = project_dir / ".env"
    env_data = _load_env_file(env_file)

    token_key = "PYPI_API_TOKEN" if repo == "pypi" else "TESTPYPI_API_TOKEN"
    token = env_data.get(token_key, "").strip()

    # If token is not found, ask once for it
    if not token:
        # Create .env if it doesn't exist
        if not env_file.exists():
            if not Confirm.ask(
                "No .env file found. Create one to store API tokens?",
                default=True,
            ):
                console.print("[red]Aborting publish because no credentials are configured.[/red]")
                raise typer.Exit(code=1)
            env_file.touch()

        # Ask for token once
        console.print(
            f"[yellow]No {token_key} found in .env. Create an API token in your {repo} account settings.[/yellow]"
        )
        token = Prompt.ask(f"Enter {token_key}", default="", password=True).strip()

        if not token:
            console.print("[red]Aborting: no API token provided.[/red]")
            raise typer.Exit(code=1)

        # Save to .env
        env_data[token_key] = token
        _save_env_file(env_file, env_data)
        console.print(f"[green]✔ Saved {token_key} to .env[/green]")

    # Prepare environment for twine
    env_vars = os.environ.copy()
    env_vars["TWINE_USERNAME"] = "__token__"
    env_vars["TWINE_PASSWORD"] = token

    python_executable, env_vars_for_tools = _get_python_for_deps_ops(project_dir, use_global)
    env_vars.update(env_vars_for_tools)

    # Ensure twine is installed in the selected Python environment
    twine_check = subprocess.run(
        [python_executable, "-m", "twine", "--version"],
        capture_output=True,
        text=True,
        env=env_vars,
    )
    if twine_check.returncode != 0:
        stderr = (twine_check.stderr or "").strip()
        if "No module named" in stderr and "twine" in stderr:
            if not Confirm.ask(
                "twine is not installed. Install it now?",
                default=True,
            ):
                console.print("[red]Aborting publish.[/red]")
                raise typer.Exit(code=1)

            try:
                code, out, err = _run_command_with_smooth_progress(
                    description="Installing twine...",
                    args=[python_executable, "-m", "pip", "install", "twine"],
                    env=env_vars,
                )
                if code != 0:
                    raise subprocess.CalledProcessError(code, [python_executable, "-m", "pip", "install", "twine"], output=out, stderr=err)
            except subprocess.CalledProcessError as exc:
                pip_stderr = (exc.stderr or "").strip()
                console.print(
                    f"[red bold]Failed to install twine[/red bold] (exit code {exc.returncode})."
                )
                if pip_stderr:
                    console.print("[red]--- pip stderr ---[/red]")
                    console.print(pip_stderr)
                raise typer.Exit(code=1)
        else:
            console.print(
                "[red bold]Error:[/] Unable to run twine in the selected Python environment."
            )
            if stderr:
                console.print("[red]--- twine stderr ---[/red]")
                console.print(stderr)
            raise typer.Exit(code=1)

    # Build twine command
    cmd = [
        python_executable,
        "-m",
        "twine",
        "upload",
        "--non-interactive",
    ]
    if repo == "testpypi":
        cmd.extend(["--repository", "testpypi"])

    cmd.extend(str(p) for p in dist_files)

    console.print(
        f"[bold]Publishing[/bold] [green]{cfg.name}[/green] to [cyan]{repo}[/cyan] from [blue]{dist_dir}[/blue]"
    )

    def _upload() -> None:
        code, out, err = _run_command_with_smooth_progress(
            description="twine upload",
            args=cmd,
            env=env_vars,
        )
        if code != 0:
            raise subprocess.CalledProcessError(code, cmd, output=out, stderr=err)

    try:
        _run_steps_with_progress(
            [
                ("Uploading distributions...", _upload),
            ]
        )
    except FileNotFoundError as exc:
        console.print(
            "[red bold]Publish failed:[/red bold] twine is not installed in the selected Python environment. "
            "Install it with 'pip install twine'."
        )
        raise typer.Exit(code=1) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        console.print(
            f"[red bold]Publish failed:[/red bold] twine exited with code {exc.returncode}."
        )
        if stderr.strip():
            console.print("[red]--- twine stderr ---[/red]")
            console.print(stderr.strip())
        raise typer.Exit(code=exc.returncode)

    console.print("[bold green]✔ Publish completed successfully.[/bold green]")


@app.command()
def install(
    no_dev: bool = typer.Option(
        False,
        "--no-dev",
        help="Do not install dev-dependencies.",
    ),
    groups: str = typer.Option(
        "",
        "--groups",
        help="Comma-separated optional-dependencies groups to install (e.g. 'docs,test').",
    ),
    all_groups: bool = typer.Option(
        False,
        "--all-groups",
        help="Install all optional-dependencies groups.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use the global Python/pip instead of the project environment.",
    ),
) -> None:
    """Install all dependencies declared in pyproject.toml using optimized resolver.

    By default, this installs:
    - [project].dependencies
    - [tool.pydepm].dev-dependencies

    Uses the custom Python dependency resolver for faster resolution.
    """

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    deps_info = core_deps.load_dependencies(pyproject_path)
    optional_map = deps_info.get("optional_dependencies", {})
    selected_groups: list[str] | None = None

    if all_groups and groups.strip():
        console.print("[red bold]Error:[/] Use either --groups or --all-groups, not both.")
        raise typer.Exit(code=1)

    if groups.strip():
        selected_groups = [g.strip() for g in groups.split(",") if g.strip()]
    elif all_groups:
        selected_groups = list(optional_map.keys())
    else:
        if optional_map:
            available = list(optional_map.keys())
            console.print(f"[bold cyan]Optional dependency groups found:[/bold cyan] {', '.join(available)}")
            selected_groups = questionary.checkbox(
                "Select groups to install:",
                choices=available,
                style=questionary_style,
            ).ask()
            if selected_groups is None:
                raise typer.Abort()
        else:
            selected_groups = None
    
    include_dev = not no_dev
    specs_with_groups = _collect_specs_with_groups(
        pyproject_path,
        include_dev=include_dev,
        optional_groups=selected_groups,
    )
    specs = [spec for spec, _, _ in specs_with_groups.values()]

    if not specs:
        console.print("[yellow]No dependency specs found to install.[/yellow]")
        raise typer.Exit(code=0)

    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    
    # Get Python version for resolver
    try:
        version_result = subprocess.run(
            [python_executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_str = version_result.stdout.strip().replace("Python ", "")
        python_version = ".".join(version_str.split(".")[:2])  # e.g., "3.11"
    except Exception:
        python_version = "3.11"

    def _resolve_and_install() -> dict:
        # Resolve dependencies using custom resolver
        with console.status("[bold cyan]Resolving dependencies...[/bold cyan]", spinner="dots"):
            resolution = integration.resolve_requirements(specs, python_version=python_version)
        
        if not resolution.success:
            console.print("[red bold]✗ Dependency resolution failed[/red bold]")
            for error in resolution.errors:
                console.print(f"  [red]{error}[/red]")
            raise typer.Exit(code=1)
        
        if resolution.warnings:
            console.print("[yellow]⚠ Resolution warnings:[/yellow]")
            for warning in resolution.warnings:
                console.print(f"  [yellow]{warning}[/yellow]")

        console.print(f"[bold green]✓ Resolved {len(resolution.resolved)} dependencies[/bold green]")
        
        # Extract package list for pip install
        resolved_specs = []
        for pkg_name, resolved_dep in resolution.resolved.items():
            spec = f"{pkg_name}=={resolved_dep.version}"
            resolved_specs.append(spec)
        
        if not resolved_specs:
            console.print("[yellow]No packages to install.[/yellow]")
            return {}

        # Install using pip with progress per dependency
        if not _install_specs_with_progress(resolved_specs, python_executable, env_vars):
            raise typer.Exit(code=1)
        
        # Return the resolved specs for updating pyproject.toml
        return {pkg_name: f"{pkg_name}=={resolved_dep.version}" 
                for pkg_name, resolved_dep in resolution.resolved.items()}

    try:
        resolved_map = _resolve_and_install()
        
        # Save exact versions to pyproject.toml, preserving group information
        if resolved_map:
            console.print("[cyan]→[/cyan] Saving exact versions to pyproject.toml...")
            for pkg_name, exact_spec in resolved_map.items():
                # Find the original group/dev status for this package
                group = None
                is_dev = False
                for orig_pkg, (orig_spec, orig_group, orig_dev) in specs_with_groups.items():
                    if core_deps.normalize_package_name(orig_pkg) == core_deps.normalize_package_name(pkg_name):
                        group = orig_group
                        is_dev = orig_dev
                        break
                
                try:
                    core_deps.update_dependency(pyproject_path, exact_spec, group=group, dev=is_dev)
                except Exception:
                    pass
            console.print(f"[cyan]→[/cyan] Updated [green]{len(resolved_map)}[/green] dependencies with exact versions")
        
        # Update lock file
        _update_lockfile_with_installed(project_dir, pyproject_path, python_executable, env_vars)
        
        console.print("[bold green]✔ All dependencies installed successfully![/bold green]")
    except Exception as exc:
        if not isinstance(exc, typer.Exit):
            console.print(f"[red bold]✗ Error:[/red bold] {exc}")
            raise typer.Exit(code=1)
        raise


def _pip_list_installed(python_executable: str, env_vars: dict) -> dict:
    result = subprocess.run(
        [python_executable, "-m", "pip", "list", "--format", "json"],
        capture_output=True,
        text=True,
        env=env_vars,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
    data = json.loads(result.stdout or "[]")
    installed = {}
    for row in data:
        name = str(row.get("name", "")).lower().replace("_", "-")
        installed[name] = str(row.get("version", ""))
    return installed


def _pip_check(python_executable: str, env_vars: dict) -> tuple[int, str]:
    result = subprocess.run(
        [python_executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        env=env_vars,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def _get_installed_version(package_name: str, python_executable: str, env_vars: dict) -> Optional[str]:
    """Get the exact installed version of a package via pip show."""
    
    try:
        result = subprocess.run(
            [python_executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    return line.split(':', 1)[1].strip()
    except Exception:
        pass
    return None


def _make_exact_spec(package_name: str, version: Optional[str]) -> str:
    """Create an exact spec like 'package==1.2.3' from name and version."""
    
    if version:
        return f"{package_name}=={version}"
    return package_name


def _update_lockfile_with_installed(
    project_dir: Path,
    pyproject_path: Path,
    python_executable: str,
    env_vars: dict,
) -> None:
    """Update pydepm.lock with currently installed versions."""
    try:
        # Get current installed versions
        installed_map = _pip_list_installed(python_executable, env_vars)
        
        lock_path = project_dir / "pydepm.lock"
        
        # Create or update lock file
        if lock_path.exists():
            lock_file = core_lock.LockFile.load(lock_path, format="toml")
        else:
            lock_file = core_lock.LockFile()
        
        # Get Python version
        try:
            version_result = subprocess.run(
                [python_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version_str = version_result.stdout.strip().replace("Python ", "")
            python_version = ".".join(version_str.split(".")[:2])
        except Exception:
            python_version = "3.11"
        
        lock_file.metadata.python_version = python_version
        
        # Update dependencies
        for pkg_name_lower, version in installed_map.items():
            from pydepm.core.resolver import ResolvedDependency
            dep = ResolvedDependency(
                name=pkg_name_lower,
                version=version,
                specifier=f"=={version}",
            )
            lock_file.add_dependency(dep)
        
        # Update pyproject hash
        if pyproject_path.exists():
            import hashlib
            content = pyproject_path.read_bytes()
            lock_file.metadata.pyproject_hash = hashlib.sha256(content).hexdigest()
        
        # Save lock file
        lock_file.save(lock_path, format="toml")
    except Exception as e:
        # Don't fail if lockfile update fails
        pass


def _collect_specs_with_groups(
    pyproject_path: Path,
    include_dev: bool = False,
    optional_groups: Optional[list[str]] = None,
) -> dict[str, tuple[str, Optional[str], bool]]:
    """Collect specs and track which group/section each came from.
    
    Returns: {pkg_name: (spec, group_name_or_none, is_dev)}
    """
    deps_info = core_deps.load_dependencies(pyproject_path)
    result = {}
    
    # Project dependencies
    for spec in deps_info.get("project_dependencies", []):
        pkg_name = core_deps.parse_requirement_name(spec) or spec
        result[pkg_name] = (spec, None, False)
    
    # Dev dependencies
    if include_dev:
        for spec in deps_info.get("dev_dependencies", []):
            pkg_name = core_deps.parse_requirement_name(spec) or spec
            result[pkg_name] = (spec, None, True)
    
    # Optional groups
    if optional_groups:
        opt_deps = deps_info.get("optional_dependencies", {})
        for group in optional_groups:
            for spec in opt_deps.get(group, []):
                pkg_name = core_deps.parse_requirement_name(spec) or spec
                result[pkg_name] = (spec, group, False)
    
    return result


def _install_specs_with_progress(
    specs: list[str],
    python_executable: str,
    env_vars: dict,
    upgrade: bool = False,
) -> bool:
    """Install specs with clean progress bar for each dependency."""
    if not specs:
        return True
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Installing dependencies",
            total=len(specs),
        )
        
        for idx, spec in enumerate(specs, 1):
            pkg_name = core_deps.parse_requirement_name(spec) or spec
            progress.update(
                task,
                description=f"[{idx:>2}/{len(specs)}] {pkg_name:<30}",
            )
            
            # Build pip install command
            pip_cmd = [python_executable, "-m", "pip", "install", "--quiet"]
            if upgrade:
                pip_cmd.append("--upgrade")
            pip_cmd.append(spec)
            
            # Run pip install silently
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                env=env_vars,
                timeout=300,
            )
            
            if result.returncode != 0:
                progress.stop()
                console.print(f"[red]✗ Failed to install {pkg_name}[/red]")
                if result.stderr:
                    console.print(f"[red]{result.stderr.strip()}[/red]")
                return False
            
            progress.advance(task)
        
        progress.update(task, description="[green]✓ Installation complete[/green]")
    
    return True


def _update_all_dependencies(
    project_dir: Path,
    pyproject_path: Path,
    use_global: bool,
    save_dev: bool,
    group: str,
    skip_confirmation: bool,
    skip_outdated_check: bool = False,
) -> None:
    """Update all dependencies to latest versions with optional confirmation.
    
    Args:
        skip_outdated_check: If True, update all deps without checking if outdated first.
    """

    # Collect all specs with group information
    include_dev = not save_dev  # If save_dev is True, update only dev; if False, include dev
    if save_dev:
        specs_with_groups = _collect_specs_with_groups(pyproject_path, include_dev=True)
        # Filter to only dev dependencies
        specs_with_groups = {k: v for k, v in specs_with_groups.items() if v[2]}  # Filter by is_dev
    elif group:
        specs_with_groups = _collect_specs_with_groups(pyproject_path, include_dev=False, optional_groups=[group])
        # Filter to only this group
        specs_with_groups = {k: v for k, v in specs_with_groups.items() if v[1] == group}
    else:
        # Update all: project dependencies + dev dependencies + all optional groups
        deps_info = core_deps.load_dependencies(pyproject_path)
        all_groups = list(deps_info.get("optional_dependencies", {}).keys())
        specs_with_groups = _collect_specs_with_groups(
            pyproject_path,
            include_dev=True,
            optional_groups=all_groups if all_groups else None
        )
    
    specs = [spec for spec, _, _ in specs_with_groups.values()]
    
    if not specs:
        console.print("[yellow]No dependencies found to update.[/yellow]")
        return
    
    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    env_vars["PIPAPI_PYTHON_LOCATION"] = python_executable
    
    # Check which packages are actually outdated (unless skip_outdated_check=True)
    if not skip_outdated_check:
        with console.status("[bold cyan]Checking for outdated packages...[/bold cyan]", spinner="dots"):
            try:
                result = subprocess.run(
                    [python_executable, "-m", "pip", "list", "--outdated", "--format", "json"],
                    capture_output=True,
                    text=True,
                    env=env_vars,
                    timeout=30,
                )
                outdated_data = json.loads(result.stdout or "[]") if result.returncode == 0 else []
                
                # Create a map of outdated packages
                outdated_map = {}
                for row in outdated_data:
                    name = str(row.get("name", "")).lower().replace("_", "-")
                    outdated_map[name] = {
                        "current": str(row.get("version", "")),
                        "latest": str(row.get("latest_version", "")),
                    }
            except Exception:
                outdated_map = {}
        
        # Filter to only outdated packages
        outdated_specs_with_groups = {}
        outdated_pkg_names = []
        for pkg_name, (spec, group_name, is_dev) in specs_with_groups.items():
            pkg_name_lower = core_deps.normalize_package_name(pkg_name)
            if pkg_name_lower in outdated_map:
                outdated_specs_with_groups[pkg_name] = (spec, group_name, is_dev)
                outdated_pkg_names.append(pkg_name)
        
        if not outdated_specs_with_groups:
            console.print("[green]✓ All dependencies are up to date![/green]")
            return
        
        # Show what will be updated
        console.print(f"[bold]Found {len(outdated_pkg_names)} outdated dependencies:[/bold]")
        for pkg_name in outdated_pkg_names:
            pkg_name_lower = core_deps.normalize_package_name(pkg_name)
            if pkg_name_lower in outdated_map:
                info = outdated_map[pkg_name_lower]
                console.print(f"  [cyan]•[/cyan] {pkg_name} {info['current']} → [green]{info['latest']}[/green]")
    else:
        # Force mode: update all specs without checking
        outdated_specs_with_groups = specs_with_groups
        outdated_pkg_names = list(specs_with_groups.keys())
        outdated_map = {}
        
        if not outdated_pkg_names:
            console.print("[yellow]No dependencies found to update.[/yellow]")
            return
        
        console.print(f"[bold cyan]Force updating {len(outdated_pkg_names)} dependencies:[/bold cyan]")
        for pkg_name in outdated_pkg_names:
            console.print(f"  [cyan]•[/cyan] {pkg_name}")
    
    # Ask for confirmation unless -y flag is provided
    if not skip_confirmation:
        console.print()
        if not Confirm.ask("[bold yellow]Update these dependencies?[/bold yellow]", console=console):
            console.print("[yellow]Update cancelled.[/yellow]")
            raise typer.Exit(code=0)
    
    # Install with --upgrade flag to get latest versions
    if not _install_specs_with_progress(outdated_pkg_names, python_executable, env_vars, upgrade=True):
        raise typer.Exit(code=1)
    
    # Verify environment
    check_rc, check_out = _pip_check(python_executable, env_vars)
    if check_rc != 0:
        console.print("[yellow]⚠ Environment check warnings:[/yellow]")
        console.print(check_out)
    
    # Save exact versions to pyproject.toml, preserving group information
    console.print("[bold]Saving exact versions...[/bold]")
    for pkg_name in outdated_pkg_names:
        installed_version = _get_installed_version(pkg_name, python_executable, env_vars)
        if installed_version:
            exact_spec = _make_exact_spec(pkg_name, installed_version)
            
            # Find original group/dev status
            orig_group = None
            orig_dev = False
            for orig_pkg, (orig_spec, orig_group_name, orig_is_dev) in outdated_specs_with_groups.items():
                if core_deps.normalize_package_name(orig_pkg) == core_deps.normalize_package_name(pkg_name):
                    orig_group = orig_group_name
                    orig_dev = orig_is_dev
                    break
            
            try:
                core_deps.update_dependency(
                    pyproject_path,
                    exact_spec,
                    group=orig_group,
                    dev=orig_dev,
                )
                console.print(f"  [cyan]→[/cyan] {pkg_name}: [green]{exact_spec}[/green]")
            except Exception as e:
                console.print(f"  [yellow]! {pkg_name}: Failed to save exact version ({e})[/yellow]")
    
    # Update lock file
    _update_lockfile_with_installed(project_dir, pyproject_path, python_executable, env_vars)
    
    console.print("[bold green]✔ All dependencies updated successfully.[/bold green]")


def _ensure_tool_installed(
    *,
    python_executable: str,
    env_vars: dict,
    module: str,
    package: str,
    prompt: str,
) -> None:
    """Ensure a Python module is importable in the selected environment.

    If missing, ask the user for confirmation and install it via pip.
    """

    check = subprocess.run(
        [python_executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        env=env_vars,
    )
    if check.returncode == 0:
        return

    if not Confirm.ask(prompt, default=True):
        console.print("[red]Aborting.[/red]")
        raise typer.Exit(code=1)

    try:
        _run_steps_with_progress(
            [(f"Installing {package}...", lambda: None)]
        )
        subprocess.run(
            [python_executable, "-m", "pip", "install", package],
            check=True,
            capture_output=True,
            text=True,
            env=env_vars,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        console.print(
            f"[red bold]Failed to install {package}[/red bold] (exit code {exc.returncode})."
        )
        if stderr:
            console.print("[red]--- pip stderr ---[/red]")
            console.print(stderr)
        raise typer.Exit(code=1)


@app.command("security-audit")
def security_audit(
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use global Python/pip for the security audit.",
    ),
) -> None:
    """Security audit using pip-audit.

    This checks installed packages in the selected environment and reports
    known vulnerabilities.
    """

    project_dir = Path.cwd()
    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)

    _ensure_tool_installed(
        python_executable=python_executable,
        env_vars=env_vars,
        module="pip_audit",
        package="pip-audit",
        prompt="pip-audit is not installed. Install it now?",
    )

    cmd = [
        python_executable,
        "-m",
        "pip_audit",
        "--format",
        "json",
    ]

    code, out, err = _run_command_with_smooth_progress(
        description="Running security audit (pip-audit)...",
        args=cmd,
        env=env_vars,
    )
    result = subprocess.CompletedProcess(cmd, code, stdout=out, stderr=err)

    # pip-audit uses exit code 1 when vulnerabilities are found.
    if result.returncode not in {0, 1}:
        stderr = (result.stderr or "").strip()
        console.print(
            f"[red bold]Security audit failed[/red bold] (exit code {result.returncode})."
        )
        if stderr:
            console.print("[red]--- pip-audit stderr ---[/red]")
            console.print(stderr)
        raise typer.Exit(code=result.returncode)

    try:
        findings = json.loads(result.stdout or "[]")
    except Exception:
        stderr = (result.stderr or "").strip()
        console.print("[red bold]Error:[/] pip-audit returned invalid JSON.")
        if stderr:
            console.print("[red]--- pip-audit stderr ---[/red]")
            console.print(stderr)
        raise typer.Exit(code=1)

    # pip-audit may return either a list of findings or a dict with
    # {"dependencies": [...], "fixes": [...]}
    try:
        if hasattr(findings, "get") and callable(getattr(findings, "get")):
            findings = findings.get("dependencies", [])
        if not isinstance(findings, (list, tuple)):
            console.print("[red bold]Error:[/] Unexpected pip-audit JSON format.")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red bold]Error:[/] Failed to parse pip-audit results: {e}")
        raise typer.Exit(code=1)

    if not findings:
        console.print("[bold green]✔ Security audit completed: no vulnerabilities found.[/bold green]")
        raise typer.Exit(code=0)

    rows: list[tuple[str, str, str, str]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        pkg = str(item.get("name", ""))
        ver = str(item.get("version", ""))
        vulns = item.get("vulns", []) or []
        if not isinstance(vulns, list) or not vulns:
            continue
        for v in vulns:
            if not isinstance(v, dict):
                continue
            vuln_id = str(v.get("id", ""))
            fix_versions = v.get("fix_versions", []) or []
            fix_text = ", ".join(str(x) for x in fix_versions) if isinstance(fix_versions, list) else ""
            rows.append((pkg, ver, vuln_id, fix_text or "-"))

    if not rows:
        console.print("[bold green]✔ Security audit completed: no vulnerabilities found.[/bold green]")
        raise typer.Exit(code=0)

    table = Table(title="Security Audit (pip-audit)")
    table.add_column("Package", style="cyan")
    table.add_column("Installed", style="magenta")
    table.add_column("Vulnerability", style="red")
    table.add_column("Fix Versions", style="green")
    for pkg, ver, vuln_id, fix_text in rows:
        table.add_row(pkg, ver, vuln_id, fix_text)

    console.print(table)
    console.print("[yellow]Security audit completed with findings.[/yellow]")
    raise typer.Exit(code=1)


@app.command()
def audit(
    include_dev: bool = typer.Option(
        False,
        "--include-dev",
        help="Include tool.pydepm.dev-dependencies in the audit.",
    ),
    groups: str = typer.Option(
        "",
        "--groups",
        help="Comma-separated optional-dependencies groups to include (e.g. 'docs,test').",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use global Python/pip to inspect installed packages.",
    ),
) -> None:
    """Audit dependencies: missing packages, outdated versions and conflicts (pip check)."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)

    group_list = [g.strip() for g in groups.split(",") if g.strip()] or None

    specs = core_deps.collect_requirement_specs(
        pyproject_path,
        include_dev=include_dev,
        optional_groups=group_list,
    )

    if not specs:
        console.print("[yellow]No dependency specs found to audit.[/yellow]")
        raise typer.Exit(code=0)

    installed = _pip_list_installed(python_executable, env_vars)

    # Fetch PyPI metadata in parallel to get latest version (with progress)
    names = core_deps.collect_requirement_names(specs)
    meta = _fetch_pypi_metadata_progress(names)

    table = Table(title="Dependency Audit", show_lines=False)
    table.add_column("Package", style="cyan")
    table.add_column("Specified", style="white")
    table.add_column("Installed", style="magenta")
    table.add_column("Latest", style="green")
    table.add_column("Status", style="bold")

    any_missing = False
    any_outdated = False

    for spec in specs:
        req_name = core_deps.parse_requirement_name(spec) or spec
        pkg = core_deps.normalize_package_name(str(req_name))
        installed_ver = installed.get(pkg, "")
        latest_ver = ""
        status = Text("OK", style="green")

        if not installed_ver:
            any_missing = True
            status = Text("MISSING", style="red")
        else:
            meta_entry = meta.get(pkg, {})
            info = meta_entry.get("info", {}) if hasattr(meta_entry, "get") else {}
            if hasattr(info, "get"):
                latest_ver = str(info.get("version", "") or "")
            if latest_ver and latest_ver != installed_ver:
                any_outdated = True
                status = Text("OUTDATED", style="yellow")

        table.add_row(
            pkg,
            spec,
            installed_ver or "-",
            latest_ver or "-",
            status,
        )

    console.print(table)

    check_rc, check_out = _pip_check(python_executable, env_vars)
    if check_rc != 0:
        console.print("[red bold]pip check found dependency conflicts:[/red bold]")
        if check_out.strip():
            console.print(check_out.strip())
        raise typer.Exit(code=1)

    if any_missing or any_outdated:
        console.print("[yellow]Audit completed with warnings.[/yellow]")
    else:
        console.print("[bold green]✔ Audit completed: no issues found.[/bold green]")


@app.command()
def fix(
    include_dev: bool = typer.Option(
        False,
        "--include-dev",
        help="Include tool.pydepm.dev-dependencies when fixing.",
    ),
    groups: str = typer.Option(
        "",
        "--groups",
        help="Comma-separated optional-dependencies groups to include.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force reinstall/upgrade the dependency set (more aggressive).",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use global Python/pip for installs.",
    ),
) -> None:
    """Attempt to fix dependency issues by installing/upgrading the declared specs and running pip check."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    group_list = [g.strip() for g in groups.split(",") if g.strip()] or None

    specs = core_deps.collect_requirement_specs(
        pyproject_path,
        include_dev=include_dev,
        optional_groups=group_list,
    )

    if not specs:
        console.print("[yellow]No dependency specs found to fix.[/yellow]")
        raise typer.Exit(code=0)

    pip_cmd = [python_executable, "-m", "pip", "install"]
    if force:
        pip_cmd.extend(["--upgrade", "--force-reinstall"])
    else:
        pip_cmd.append("--upgrade")

    pip_cmd.extend(specs)

    if not Confirm.ask(
        "Apply dependency fixes now? This will run pip install.",
        default=True,
    ):
        raise typer.Abort()

    try:
        code, out, err = _run_command_with_smooth_progress(
            description="Applying fixes with pip...",
            args=pip_cmd,
            env=env_vars,
        )
        if code != 0:
            raise subprocess.CalledProcessError(code, pip_cmd, output=out, stderr=err)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        console.print(
            f"[red bold]pip install failed[/red bold] with exit code {exc.returncode}."
        )
        if stderr:
            console.print("[red]--- pip stderr ---[/red]")
            console.print(stderr)
        raise typer.Exit(code=exc.returncode)

    check_rc, check_out = _pip_check(python_executable, env_vars)
    if check_rc != 0:
        console.print("[red bold]Fix completed but pip check still reports conflicts:[/red bold]")
        if check_out.strip():
            console.print(check_out.strip())
        raise typer.Exit(code=1)

    console.print("[bold green]✔ Fix completed successfully.[/bold green]")


@app.command()
def lock(
    include_dev: bool = typer.Option(
        False,
        "--include-dev",
        help="Include tool.pydepm.dev-dependencies in the lock.",
    ),
    groups: str = typer.Option(
        "",
        "--groups",
        help="Comma-separated optional-dependencies groups to include.",
    ),
    use_global: bool = typer.Option(
        False,
        "-g",
        "--global",
        help="Use global Python/pip for locking.",
    ),
) -> None:
    """Generate a pydep.lock file with resolved dependency versions."""

    project_dir = Path.cwd()
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        console.print("[red bold]Error:[/] No pyproject.toml found in current directory.")
        raise typer.Exit(code=1)

    python_executable, env_vars = _get_python_for_deps_ops(project_dir, use_global)
    group_list = [g.strip() for g in groups.split(",") if g.strip()] or None

    specs = core_deps.collect_requirement_specs(
        pyproject_path,
        include_dev=include_dev,
        optional_groups=group_list,
    )

    if not specs:
        console.print("[yellow]No dependency specs found to lock.[/yellow]")
        raise typer.Exit(code=0)

    # Install dependencies to resolve versions
    try:
        _run_steps_with_progress(
            [
                ("Installing dependencies to resolve versions...", lambda: None),
                ("Generating lock file...", lambda: None),
            ]
        )
        subprocess.run(
            [python_executable, "-m", "pip", "install", "--dry-run", "--quiet", *specs],
            check=True,
            capture_output=True,
            text=True,
            env=env_vars,
        )
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[red bold]Failed to resolve dependencies[/red bold] (exit code {exc.returncode})."
        )
        raise typer.Exit(code=exc.returncode)

    # Get installed versions
    installed = _pip_list_installed(python_executable, env_vars)

    # Create lock data
    lock_data = {
        "version": "1.0",
        "python": python_executable,
        "dependencies": installed,
    }

    lock_path = project_dir / "pydep.lock"
    with lock_path.open("w", encoding="utf-8") as f:
        json.dump(lock_data, f, indent=2)

    console.print(f"[bold green]✔ Lock file generated:[/bold green] [blue]{lock_path}[/blue]")


if __name__ == "__main__":  # pragma: no cover
    app()
