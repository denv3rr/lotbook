import os
import subprocess
from pathlib import Path
from typing import Callable, Optional, Tuple

VENV_DIR = Path(".venv_gui")
REQ_FILE = Path("requirements.txt")


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _is_gui_ready(python_exe: Path) -> bool:
    if not python_exe.exists():
        return False
    cmd = [
        str(python_exe),
        "-c",
        "import PySide6, PySide6.QtWebEngineWidgets",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def _emit(status_hook: Optional[Callable[[str], None]], message: str) -> None:
    if status_hook:
        status_hook(message)
    else:
        print(message)


def _create_venv(status_hook: Optional[Callable[[str], None]]) -> Optional[str]:
    commands = [
        ["py", "-3.13", "-m", "venv", str(VENV_DIR)],
        ["py", "-3.12", "-m", "venv", str(VENV_DIR)],
        ["python3.13", "-m", "venv", str(VENV_DIR)],
        ["python3.12", "-m", "venv", str(VENV_DIR)],
    ]
    for cmd in commands:
        try:
            _emit(status_hook, f">> GUI setup: creating venv with {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            return None
    return "Unable to locate Python 3.12 or 3.13 to create the GUI venv."


def _install_requirements(python_exe: Path, status_hook: Optional[Callable[[str], None]]) -> Optional[str]:
    _emit(status_hook, ">> GUI setup: installing GUI dependencies")
    cmd = [str(python_exe), "-m", "pip", "install", "-r", str(REQ_FILE)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return None
    return result.stderr.strip() or "Failed to install GUI dependencies."


def ensure_gui_venv(status_hook: Optional[Callable[[str], None]] = None) -> Tuple[Optional[Path], Optional[str]]:
    python_exe = _venv_python()
    _emit(status_hook, ">> GUI setup: checking existing GUI environment")
    if _is_gui_ready(python_exe):
        return python_exe, None
    if not VENV_DIR.exists():
        err = _create_venv(status_hook)
        if err:
            return None, err
    python_exe = _venv_python()
    if not python_exe.exists():
        return None, "GUI venv creation failed."
    err = _install_requirements(python_exe, status_hook)
    if err:
        return None, err
    if not _is_gui_ready(python_exe):
        return None, "GUI dependencies installed but PySide6 import still failed."
    return python_exe, None


def launch_gui_in_venv(
    refresh_seconds: int = 10,
    status_hook: Optional[Callable[[str], None]] = None,
    start_paused: bool = False,
) -> Optional[str]:
    python_exe, err = ensure_gui_venv(status_hook=status_hook)
    if err or not python_exe:
        return err
    _emit(status_hook, ">> GUI setup: launching tracker window")
    cmd = [str(python_exe), "-m", "utils.gui_launcher"]
    env = os.environ.copy()
    env["LOTBOOK_GUI_REFRESH"] = str(refresh_seconds)
    env["LOTBOOK_GUI_PAUSED"] = "1" if start_paused else "0"
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        return "GUI process exited with an error."
    return None
