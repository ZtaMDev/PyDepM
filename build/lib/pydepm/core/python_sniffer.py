"""Python version detection and sniffer module.

Detects available Python versions on the system.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Optional


def get_python_versions() -> List[Tuple[str, Path]]:
    """Detect available Python versions on the system.
    
    Returns list of tuples (version_string, executable_path) sorted by version.
    Searches common installation paths on Windows, Linux, macOS.
    
    Returns:
        List of (version, path) tuples, sorted by version (newest first)
    """
    versions: dict[str, Path] = {}
    
    # Current Python
    try:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        versions[version] = Path(sys.executable)
    except Exception:
        pass
    
    # Common installation paths to search
    search_paths = [
        Path("C:/Python311") if sys.platform == "win32" else Path("/usr/bin"),
        Path("C:/Python310") if sys.platform == "win32" else Path("/usr/local/bin"),
        Path("C:/Python312") if sys.platform == "win32" else Path("/opt/python"),
        Path("C:/Program Files/Python311"),
        Path("C:/Program Files/Python310"),
        Path("C:/Program Files/Python312"),
    ]
    
    # Search for python executables
    for base_path in search_paths:
        if not base_path.exists():
            continue
            
        # Direct python executable
        for exe_name in ["python.exe", "python", "python3"]:
            exe_path = base_path / exe_name
            if exe_path.exists() and exe_path.is_file():
                try:
                    result = subprocess.run(
                        [str(exe_path), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        version_str = result.stdout.strip().replace("Python ", "")
                        versions[version_str] = exe_path
                except Exception:
                    pass
    
    # On Windows, also check registry (Pythoninstallers use this)
    if sys.platform == "win32":
        try:
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Python\PythonCore")
                i = 0
                while True:
                    try:
                        version = winreg.EnumKey(key, i)
                        try:
                            subkey = winreg.OpenKey(key, f"{version}\\InstallPath")
                            path, _ = winreg.QueryValueEx(subkey, "")
                            exe_path = Path(path) / "python.exe"
                            if exe_path.exists():
                                versions[version] = exe_path
                        except Exception:
                            pass
                        i += 1
                    except WindowsError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass
        except ImportError:
            pass
    
    # Sort by version (newest first)
    sorted_versions = sorted(versions.items(), key=lambda x: _parse_version(x[0]), reverse=True)
    return sorted_versions


def _parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse version string like '3.11.5' into tuple of ints."""
    try:
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 0, 0)


def get_best_python_version() -> Optional[Tuple[str, Path]]:
    """Get the best (newest) available Python version.
    
    Returns:
        Tuple of (version, path) or None if not found
    """
    versions = get_python_versions()
    return versions[0] if versions else None


def python_version_to_string(version: str) -> str:
    """Format version string for display.
    
    Examples:
        '3.11.5' -> 'Python 3.11.5'
        '3.11' -> 'Python 3.11'
    """
    return f"Python {version}"
