import argparse
import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser

from clear_bootstrap import REPO_ROOT, ensure_runtime_dependencies

os.chdir(REPO_ROOT)
if __name__ == "__main__" and not ensure_runtime_dependencies(
    auto_install="--no-install" not in sys.argv[1:]
):
    raise SystemExit(1)

import httpx
from utils.stack_control import prepare_control, record_process, shutdown_requested

LOGGER = logging.getLogger("clear.run_web")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    LOGGER.warning("python-dotenv is not installed; skipping .env load")
except OSError:
    LOGGER.exception("Failed to load .env")

from utils.launcher import (
    RUNTIME_DIR,
    ensure_runtime_dirs,
    filter_matching_pids,
    find_pids_by_port,
    install_windows_console_handler,
    process_alive,
    read_pid,
    terminate_pid,
    terminate_pids_by_port,
    wait_for_port_release,
    wait_for_port,
    write_pid,
)

API_PID = RUNTIME_DIR / "api.pid"
WEB_PID = RUNTIME_DIR / "web.pid"


def _health_check() -> bool:
    try:
        headers = {}
        api_key = os.getenv("CLEAR_WEB_API_KEY", "")
        if api_key:
            headers["X-API-Key"] = api_key
        response = httpx.get(
            "http://127.0.0.1:8000/api/health",
            timeout=2.0,
            trust_env=False,
            headers=headers,
        )
        return response.status_code == 200
    except Exception:
        return False


def _wait_for_api(timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _health_check():
            return True
        time.sleep(0.4)
    return False


def _print_header() -> None:
    print(">> • CLEAR Web Launcher\n>> • Copyright © 2025 Seperet LLC • https://seperet.com/\n>>")


def _prompt_yes_no(message: str) -> bool:
    return False


def _python_deps_ready(auto_yes: bool) -> bool:
    return ensure_runtime_dependencies(auto_install=auto_yes)


def _candidate_paths() -> list[str]:
    candidates: list[str] = []
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    exts = [".cmd", ".exe", ""]
    for entry in path_entries:
        entry = entry.strip('"')
        if not entry:
            continue
        for ext in exts:
            candidates.append(os.path.join(entry, f"npm{ext}"))
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        candidates.append(os.path.join(user_profile, "scoop", "shims", "npm.cmd"))
        candidates.append(os.path.join(user_profile, "scoop", "apps", "nodejs-lts", "current", "bin", "npm.cmd"))
    candidates.append(os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "nodejs", "npm.cmd"))
    return candidates


def _find_npm() -> str | None:
    direct = shutil.which("npm") or shutil.which("npm.cmd") or shutil.which("npm.exe")
    if direct:
        return direct
    for candidate in _candidate_paths():
        if os.path.isfile(candidate):
            return candidate
    return None


def _npm_available() -> str | None:
    npm_path = _find_npm()
    if not npm_path:
        return None
    try:
        subprocess.check_output([npm_path, "--version"], stderr=subprocess.STDOUT)
    except Exception:
        return None
    return npm_path


def _ensure_node_modules(web_dir: str, npm_path: str, auto_yes: bool) -> bool:
    lockfile = os.path.join(web_dir, "package-lock.json")
    if not os.path.isfile(lockfile):
        print(">> package-lock.json missing. Refusing unverified npm install.")
        return False
    if os.path.isdir(os.path.join(web_dir, "node_modules")):
        required = ["react-markdown", "remark-gfm"]
        missing = [
            pkg for pkg in required if not os.path.isdir(os.path.join(web_dir, "node_modules", pkg))
        ]
        if not missing:
            return True
        print(">> Web dependencies missing:", ", ".join(missing))
        if auto_yes:
            try:
                subprocess.check_call([npm_path, "ci"], cwd=web_dir)
                return True
            except FileNotFoundError:
                print(">> npm not found. Install Node.js (includes npm) and retry.")
            except subprocess.CalledProcessError:
                print(">> npm install failed. Fix npm/node setup and retry.")
            return False
        print(">> Aborted. Run npm install and retry.")
        return False
    print(">> Web dependencies not installed (node_modules missing).")
    if auto_yes:
        try:
            subprocess.check_call([npm_path, "ci"], cwd=web_dir)
            return True
        except FileNotFoundError:
            print(">> npm not found. Install Node.js (includes npm) and retry.")
        except subprocess.CalledProcessError:
            print(">> npm install failed. Fix npm/node setup and retry.")
        return False
    print(">> Aborted. Run npm install and retry.")
    return False


def _spawn_process(cmd: list[str], cwd: str | None = None, env: dict | None = None, detach: bool = False) -> subprocess.Popen:
    kwargs: dict = {}
    if cwd:
        kwargs["cwd"] = cwd
    if env:
        kwargs["env"] = env
    if detach:
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _terminate_port_processes(
    port: int,
    label: str,
    tokens: list[str],
    auto_yes: bool,
) -> bool:
    pids = find_pids_by_port(port)
    if not pids:
        return True
    safe_pids = filter_matching_pids(pids, tokens)
    if safe_pids:
        pid_list = ", ".join(str(pid) for pid in safe_pids)
        print(f">> {label} port {port} in use by Clear process(es) {pid_list}. Terminating.")
        for pid in safe_pids:
            terminate_pid(pid)
        wait_for_port_release(port, timeout=8.0)
    remaining = [pid for pid in find_pids_by_port(port) if pid not in safe_pids]
    if remaining:
        pid_list = ", ".join(str(pid) for pid in remaining)
        print(f">> {label} port {port} in use by non-Clear process(es) {pid_list}. Refusing to terminate.")
        return False
    return True


def _force_release_ports(api_tokens: list[str], ui_tokens: list[str]) -> None:
    for port in (8000, 5173):
        pids = find_pids_by_port(port)
        tokens = api_tokens if port == 8000 else ui_tokens
        safe_pids = filter_matching_pids(pids, tokens)
        for pid in safe_pids:
            terminate_pid(pid, timeout=8.0)
        wait_for_port_release(port, timeout=10.0)


def _cleanup_existing_processes() -> None:
    for label, pid_path in (("API", API_PID), ("Web", WEB_PID)):
        pid = read_pid(pid_path)
        if pid and process_alive(pid):
            terminate_pid(pid, timeout=8.0)
            print(f">> Stopped {label} (pid {pid}).")
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)
    wait_for_port_release(8000, timeout=10.0)
    wait_for_port_release(5173, timeout=10.0)


def _launch_processes(
    npm_path: str,
    detach: bool,
    auto_open: bool,
    reload_api: bool,
    auto_yes: bool,
) -> int:
    ensure_runtime_dirs()
    _cleanup_existing_processes()
    web_dir = os.path.join(os.getcwd(), "web")
    web_token = web_dir.lower()
    api_tokens = ["uvicorn", "web_api.app:app"]
    ui_tokens = ["vite", web_token]
    if not _terminate_port_processes(
        8000, "API", api_tokens, auto_yes
    ):
        return 1
    if not _terminate_port_processes(5173, "UI", ui_tokens, auto_yes):
        return 1
    api_cmd = [sys.executable, "-m", "web_api.server"]
    control_path = prepare_control(5173)
    api_env = os.environ.copy()
    api_env["CLEAR_STACK_CONTROL"] = str(control_path)
    if reload_api:
        api_cmd = [sys.executable, "-m", "uvicorn", "web_api.app:app", "--reload"]
    api_cmd.extend(["--port", "8000"])
    ui_cmd = [npm_path, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"]

    api_proc = _spawn_process(api_cmd, env=api_env, detach=detach)
    write_pid(API_PID, api_proc.pid)
    record_process(control_path, "api", api_proc.pid)
    api_port = 8000
    ui_port = 5173
    try:
        if not _wait_for_api():
            print(">> API failed to start on http://127.0.0.1:8000. Check logs/output.")
            if api_proc.poll() is None:
                terminate_pid(api_proc.pid)
            if API_PID.exists():
                API_PID.unlink(missing_ok=True)
            return 1
    except KeyboardInterrupt:
        print("\n>> Startup interrupted before API was ready.")
        if api_proc.poll() is None:
            terminate_pid(api_proc.pid)
        if API_PID.exists():
            API_PID.unlink(missing_ok=True)
        return 1
    ui_env = os.environ.copy()
    ui_env.setdefault("VITE_API_BASE", "http://127.0.0.1:8000")
    api_key = os.environ.get("CLEAR_WEB_API_KEY")
    if api_key:
        ui_env.setdefault("VITE_API_KEY", api_key)
    ui_proc = _spawn_process(ui_cmd, cwd=os.path.realpath(web_dir), env=ui_env, detach=detach)
    write_pid(WEB_PID, ui_proc.pid)
    record_process(control_path, "web", ui_proc.pid)
    if not wait_for_port(ui_port, timeout=6.0):
        print(">> Web UI failed to start on http://127.0.0.1:5173. Check output.")
        terminate_pid(api_proc.pid)
        terminate_pid(ui_proc.pid)
        for pid_path in (API_PID, WEB_PID):
            if pid_path.exists():
                pid_path.unlink(missing_ok=True)
        return 1
    record_process(control_path, "web", ui_proc.pid)
    print(">> Web UI: http://127.0.0.1:5173  |  API: http://127.0.0.1:8000")
    if auto_open:
        webbrowser.open("http://127.0.0.1:5173/")
    if detach:
        print(">> Running in background. Use Task Manager to stop processes.")
        return 0
    print(">> Press CTRL+C to stop.")

    cleaned_up = False
    def _shutdown() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        if shutdown_requested(control_path):
            return
        for proc in (api_proc, ui_proc):
            if proc.poll() is None:
                terminate_pid(proc.pid, timeout=8.0)
        for pid_path in (API_PID, WEB_PID):
            if pid_path.exists():
                pid_path.unlink(missing_ok=True)
        terminate_pids_by_port(api_port, api_tokens, timeout=8.0)
        terminate_pids_by_port(ui_port, ui_tokens, timeout=8.0)
        wait_for_port_release(api_port, timeout=10.0)
        wait_for_port_release(ui_port, timeout=10.0)
        _force_release_ports(api_tokens, ui_tokens)

    def _handle_signal(signum: int, _frame: object) -> None:
        print("\n>> Shutting down web stack...")
        _shutdown()
        raise SystemExit(1)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            continue
    atexit.register(_shutdown)
    install_windows_console_handler(_shutdown)

    try:
        while True:
            if api_proc.poll() is not None:
                _shutdown()
                return api_proc.returncode or 0
            if ui_proc.poll() is not None:
                if shutdown_requested(control_path):
                    time.sleep(0.1)
                    continue
                _shutdown()
                return ui_proc.returncode or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n>> Shutting down web stack...")
    finally:
        _shutdown()
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the CLEAR web stack.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser.")
    parser.add_argument("--detach", action="store_true", help="Run API/UI in background and exit.")
    parser.add_argument("--reload", action="store_true", help="Reload the API on code changes.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-install missing dependencies without prompting.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _print_header()
    if not _python_deps_ready(args.yes):
        return
    npm_path = _npm_available()
    if not npm_path:
        print(">> npm not found. Install Node.js (includes npm) and retry.")
        print("   - Windows (winget): winget install OpenJS.NodeJS.LTS")
        print("   - Windows (scoop): scoop install nodejs-lts")
        print("   - macOS: brew install node")
        print("   - Linux: https://nodejs.org/en/download/package-manager")
        return
    web_dir = os.path.join(os.getcwd(), "web")
    if not os.path.isdir(web_dir):
        print(">> ./web directory missing. Cannot launch web UI.")
        return
    if not _ensure_node_modules(web_dir, npm_path, args.yes):
        return
    exit_code = _launch_processes(
        npm_path,
        args.detach,
        not args.no_open,
        args.reload,
        True,
    )
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
