from __future__ import annotations

import argparse
import atexit
import importlib.util
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import httpx
import psutil
from utils.stack_control import prepare_control, record_process, shutdown_requested

from utils.launcher import (
    LOG_DIR,
    RUNTIME_DIR,
    ensure_runtime_dirs,
    filter_existing,
    filter_matching_pids,
    find_pids_by_port,
    install_windows_console_handler,
    pid_cmdline,
    port_in_use,
    process_alive,
    redact_log_line,
    read_pid,
    rotate_log,
    safe_sleep,
    tail_lines,
    terminate_pid,
    wait_for_exit,
    wait_for_port,
    wait_for_port_release,
    write_pid,
)

LOGGER = logging.getLogger("clear.clearctl")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    LOGGER.warning("python-dotenv is not installed; skipping .env load")
except OSError:
    LOGGER.exception("Failed to load .env")

API_PID = RUNTIME_DIR / "api.pid"
WEB_PID = RUNTIME_DIR / "web.pid"
API_LOG = LOG_DIR / "api.log"
WEB_LOG = LOG_DIR / "web.log"

def _load_settings() -> dict:
    settings_path = Path("config/settings.json")
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text())
    except Exception:
        return {}

SETTINGS = _load_settings()
DEFAULT_API_PORT = SETTINGS.get("api_port", 8000)
DEFAULT_UI_PORT = SETTINGS.get("ui_port", 5173)
_ACTIVE_ARGS: argparse.Namespace | None = None
_STOPPING = False


def _print_header() -> None:
    print(">> Clear")
    print(">> Seperet LLC | https://seperet.com/")


def _python_deps_ready(auto_yes: bool) -> bool:
    missing = []
    for pkg in ("fastapi", "uvicorn", "httpx"):
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    if not missing:
        return True
    print(">> Missing Python dependencies:", ", ".join(missing))
    if not auto_yes:
        print(">> Aborted. Install dependencies then retry.")
        return False
    requirements = Path("requirements.txt")
    if not requirements.exists():
        print(">> requirements.txt missing. Refusing unverified install.")
        return False
    has_hashes = False
    for line in requirements.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "--hash=" in text:
            has_hashes = True
            break
    if not has_hashes:
        print(">> requirements.txt missing hashes. Refusing unverified install.")
        print(">> Provide hashes (pip-compile --generate-hashes) before auto-install.")
        return False
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "-r",
                "requirements.txt",
            ]
        )
        return True
    except Exception:
        print(">> Python dependency install failed. Fix pip setup and retry.")
        return False


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
    return _find_npm()


def _module_path(web_dir: Path, module: str) -> Path:
    parts = module.split("/")
    return web_dir / "node_modules" / Path(*parts)


def _node_modules_ready(web_dir: Path) -> tuple[bool, list[str]]:
    node_modules = web_dir / "node_modules"
    if not node_modules.is_dir():
        return False, ["node_modules"]
    required = [
        "@tailwindcss/postcss",
        "autoprefixer",
        "tailwindcss",
        "vite",
        "@vitejs/plugin-react",
    ]
    missing = [name for name in required if not _module_path(web_dir, name).exists()]
    return not missing, missing


def _ensure_node_modules(web_dir: Path, npm_path: str, auto_yes: bool) -> bool:
    ready, missing = _node_modules_ready(web_dir)
    if ready:
        return True
    lockfile = web_dir / "package-lock.json"
    if not lockfile.exists():
        print(">> package-lock.json missing. Refusing unverified npm install.")
        return False
    if missing == ["node_modules"]:
        print(">> Web dependencies not installed (node_modules missing).")
    else:
        print(">> Web dependencies out of date:", ", ".join(missing))
    if not auto_yes:
        print(">> Automatic dependency installation is disabled. Run again without --no-install.")
        return False
    try:
        subprocess.check_call([npm_path, "ci"], cwd=str(web_dir))
        return True
    except Exception:
        print(">> npm install failed. Fix npm/node setup and retry.")
        return False


def _spawn_process(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    detach: bool = True,
    log_path: Path | None = None,
) -> subprocess.Popen:
    kwargs: dict = {}
    if cwd:
        kwargs["cwd"] = str(cwd)
    if env:
        kwargs["env"] = env
    if log_path:
        rotate_log(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="ascii", errors="ignore")
        kwargs["stdout"] = log_handle
        kwargs["stderr"] = subprocess.STDOUT
    if detach:
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _playwright_installed(npm_path: str, web_dir: Path) -> bool:
    try:
        subprocess.check_output(
            [npm_path, "exec", "--", "playwright", "install", "--check"],
            cwd=str(web_dir),
            stderr=subprocess.STDOUT,
        )
        return True
    except Exception:
        return False


def _ensure_playwright(npm_path: str, web_dir: Path, auto_yes: bool) -> bool:
    if _playwright_installed(npm_path, web_dir):
        print(">> Playwright browsers installed.")
        return True
    print(">> Playwright browsers not installed.")
    try:
        subprocess.check_call([npm_path, "exec", "--", "playwright", "install"], cwd=str(web_dir))
        if _playwright_installed(npm_path, web_dir):
            print(">> Playwright browsers installed.")
            return True
        print(">> Playwright install completed but browsers not detected.")
        return True
    except Exception:
        print(">> Playwright install failed. Run: npx playwright install")
        return False


def _health_check(api_port: int) -> bool:
    url = f"http://127.0.0.1:{api_port}/api/health"
    headers = {}
    api_key = os.getenv("CLEAR_WEB_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        response = httpx.get(url, timeout=2.0, trust_env=False, headers=headers)
        return response.status_code == 200
    except Exception:
        return False


def _terminate_port_processes(
    port: int,
    label: str,
    attempts: int = 3,
    wait_timeout: float = 6.0,
    tokens: Optional[Iterable[str]] = None,
) -> bool:
    for _ in range(max(1, attempts)):
        pids = find_pids_by_port(port)
        if not pids:
            return True
        safe_pids = filter_matching_pids(pids, tokens or [])
        if not safe_pids:
            pid_list = ", ".join(str(pid) for pid in pids)
            print(f">> {label} port {port} in use by non-Clear process(es) {pid_list}. Refusing to terminate.")
            return False
        alive = [pid for pid in safe_pids if process_alive(pid)]
        target = alive or safe_pids
        pid_list = ", ".join(str(pid) for pid in target)
        print(f">> {label} port {port} in use by Clear process(es) {pid_list}. Terminating.")
        for pid in target:
            terminate_pid(pid, timeout=8.0)
        wait_for_port_release(port, timeout=wait_timeout)
        if not port_in_use(port):
            return True
    print(f">> {label} port {port} still in use after termination attempts.")
    return False


def _cleanup_existing_processes(
    api_port: int = DEFAULT_API_PORT,
    ui_port: int = DEFAULT_UI_PORT,
) -> None:
    for label, pid_path in (("API", API_PID), ("Web", WEB_PID)):
        pid = read_pid(pid_path)
        if pid and process_alive(pid):
            terminate_pid(pid, timeout=8.0)
            print(f">> Stopped {label} (pid {pid}).")
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)
    wait_for_port_release(api_port, timeout=10.0)
    wait_for_port_release(ui_port, timeout=10.0)


def _wait_for_api(api_port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _health_check(api_port):
            return True
        safe_sleep(0.4)
    return False


def _install_shutdown_handlers(args: argparse.Namespace) -> None:
    global _ACTIVE_ARGS
    _ACTIVE_ARGS = args

    def _handle_signal(signum: int, _frame: object) -> None:
        _stop(args)
        raise SystemExit(1)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            continue
    atexit.register(lambda: _stop(args) if _ACTIVE_ARGS is args else None)
    install_windows_console_handler(lambda: _stop(args))





def _start(args: argparse.Namespace) -> int:
    global _STOPPING, _ACTIVE_ARGS
    _STOPPING = False
    ensure_runtime_dirs()
    if args.foreground:
        _install_shutdown_handlers(args)
    if not _python_deps_ready(args.yes):
        return 1
    _cleanup_existing_processes(args.api_port, args.ui_port)
    api_tokens = ["uvicorn", "web_api.app"]
    web_dir = Path("web").resolve()
    ui_tokens = ["vite", str(web_dir).lower()]
    if not _terminate_port_processes(args.api_port, "API", tokens=api_tokens):
        return 1

    api_pid = read_pid(API_PID)
    if api_pid and process_alive(api_pid):
        print(">> API is already running.")
    elif port_in_use(args.api_port):
        wait_for_port_release(args.api_port, timeout=6.0)
        if port_in_use(args.api_port):
            print(f">> API port {args.api_port} already in use by another process.")
            return 1

    if not (api_pid and process_alive(api_pid)):
        api_cmd = [sys.executable, "-m", "web_api.server"]
        control_path = prepare_control(args.ui_port)
        api_env = os.environ.copy()
        api_env["CLEAR_STACK_CONTROL"] = str(control_path)
        if args.reload:
            api_cmd = [sys.executable, "-m", "uvicorn", "web_api.app:app", "--reload"]
        api_cmd.extend(["--port", str(args.api_port)])
        api_proc = _spawn_process(api_cmd, env=api_env, detach=not args.foreground, log_path=API_LOG)
        write_pid(API_PID, api_proc.pid)
        record_process(control_path, "api", api_proc.pid)

        try:
            if not _wait_for_api(args.api_port):
                print(f">> API failed to start on port {args.api_port}. Check logs: {API_LOG}")
                return _stop(args)
        except KeyboardInterrupt:
            print("\n>> Startup interrupted before API was ready.")
            return _stop(args)

    web_dir = Path("web").resolve()
    if args.no_web or not web_dir.exists():
        print(">> API started.")
        if args.foreground:
            wait_for_exit(api_proc.pid)
        return 0

    web_pid = read_pid(WEB_PID)
    if web_pid and process_alive(web_pid):
        print(">> Web UI is already running.")
    elif port_in_use(args.ui_port):
        wait_for_port_release(args.ui_port, timeout=6.0)
        if port_in_use(args.ui_port):
            print(f">> UI port {args.ui_port} already in use by another process.")
            return 1
    
    if not (web_pid and process_alive(web_pid)):
        npm_path = _npm_available()
        if not npm_path:
            print(">> npm not found. Install Node.js (includes npm) and retry.")
            return 1
        if not _terminate_port_processes(args.ui_port, "UI", tokens=ui_tokens):
            return 1
        if not _ensure_node_modules(web_dir, npm_path, args.yes):
            return 1

        ui_env = os.environ.copy()
        ui_env.setdefault("VITE_API_BASE", f"http://127.0.0.1:{args.api_port}")
        api_key = os.environ.get("CLEAR_WEB_API_KEY")
        if api_key:
            ui_env.setdefault("VITE_API_KEY", api_key)
        ui_cmd = [npm_path, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.ui_port)]
        ui_proc = _spawn_process(ui_cmd, cwd=web_dir, env=ui_env, detach=not args.foreground, log_path=WEB_LOG)
        write_pid(WEB_PID, ui_proc.pid)
        record_process(control_path, "web", ui_proc.pid)
        if not wait_for_port(args.ui_port, timeout=6.0):
            print(f">> Web UI failed to start on port {args.ui_port}. Check logs: {WEB_LOG}")
            return _stop(args)
        record_process(control_path, "web", ui_proc.pid)

    print(f">> Web UI: http://127.0.0.1:{args.ui_port}")
    print(f">> API: http://127.0.0.1:{args.api_port}")
    if not args.no_open:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{args.ui_port}/")
    if args.foreground:
        print(">> Application is running in the foreground. Press Ctrl+C to stop.")
        try:
            while True:
                safe_sleep(0.5)
                if api_proc.poll() is not None or ui_proc.poll() is not None:
                    if shutdown_requested(control_path):
                        # The managed API owns app-requested cleanup. Do not kill
                        # it while it drains work and finalizes its control record.
                        if api_proc.poll() is None:
                            continue
                        _ACTIVE_ARGS = None
                        return api_proc.returncode or 0
                    print(">> Detected process exit; shutting down stack.")
                    return _stop(args)
        except KeyboardInterrupt:
            return _stop(args)
    return 0


def _stop(args: argparse.Namespace) -> int:
    global _STOPPING, _ACTIVE_ARGS
    if _STOPPING:
        return 0
    _STOPPING = True
    _ACTIVE_ARGS = None
    ensure_runtime_dirs()
    stopped = False
    failed = False
    api_port = getattr(args, "api_port", DEFAULT_API_PORT)
    ui_port = getattr(args, "ui_port", DEFAULT_UI_PORT)
    api_tokens = ["uvicorn", "web_api.app"]
    web_dir = Path("web").resolve()
    ui_tokens = ["vite", str(web_dir).lower()]
    for label, pid_path in (("API", API_PID), ("Web", WEB_PID)):
        pid = read_pid(pid_path)
        if pid and process_alive(pid):
            terminate_pid(pid, timeout=4.0)
            stopped = True
            if wait_for_exit(pid, timeout=4.0):
                print(f">> Stopped {label} (pid {pid}).")
            else:
                failed = True
                print(f">> {label} process (pid {pid}) did not exit cleanly.")
        if pid_path.exists():
            pid_path.unlink(missing_ok=True)

    if port_in_use(api_port):
        if not _terminate_port_processes(api_port, "API", tokens=api_tokens):
            failed = True
    if port_in_use(ui_port):
        if not _terminate_port_processes(ui_port, "UI", tokens=ui_tokens):
            failed = True
    wait_for_port_release(api_port, timeout=6.0)
    wait_for_port_release(ui_port, timeout=6.0)

    if not stopped:
        print(">> No running services detected.")
    _STOPPING = False
    return 1 if failed else 0


def _run_cli(_: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "run_cli.py"])


def _status(_: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    api_pid = read_pid(API_PID)
    web_pid = read_pid(WEB_PID)
    api_alive = api_pid is not None and process_alive(api_pid)
    web_alive = web_pid is not None and process_alive(web_pid)
    print(f">> API: {'running' if api_alive else 'stopped'}" + (f" (pid {api_pid})" if api_pid else ""))
    print(f">> Web: {'running' if web_alive else 'stopped'}" + (f" (pid {web_pid})" if web_pid else ""))
    if api_alive:
        healthy = _health_check(DEFAULT_API_PORT)
        print(f">> Health: {'ok' if healthy else 'unreachable'}")
    return 0


def _logs(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    targets = []
    if args.api or not (args.api or args.web):
        targets.append(API_LOG)
    if args.web or not (args.api or args.web):
        targets.append(WEB_LOG)
    for path in filter_existing(targets):
        print(f"\n>> {path}")
        for line in tail_lines(path, limit=args.lines):
            print(redact_log_line(line))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    ok = True
    if not _python_deps_ready(args.yes):
        ok = False
    npm_path = _npm_available()
    if not args.no_web:
        if not npm_path:
            print(">> npm missing.")
            ok = False
        else:
            if not _ensure_node_modules(Path("web"), npm_path, args.yes):
                ok = False
            if args.web_tests and not _ensure_playwright(npm_path, Path("web"), args.yes):
                ok = False
    if port_in_use(args.api_port):
        print(f">> API port {args.api_port} in use.")
    if not args.no_web and port_in_use(args.ui_port):
        print(f">> UI port {args.ui_port} in use.")
    if _health_check(args.api_port):
        print(">> API health: ok")
    else:
        print(">> API health: not running (start it with `python clearctl.py start`).")
    return 0 if ok else 1


def _add_start_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    parser.add_argument("--no-web", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.set_defaults(foreground=True, yes=True)
    parser.add_argument("--foreground", action="store_true", dest="foreground", help="Run in foreground (default).")
    parser.add_argument("--detach", action="store_false", dest="foreground", help="Run API/UI in the background.")
    parser.add_argument("--reload", action="store_true", help="Reload the API on code changes.")
    parser.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-install",
        action="store_false",
        dest="yes",
        help="Do not install approved dependencies when they are missing.",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear multi-platform launcher.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start API and web UI.")
    _add_start_args(start)

    stop = sub.add_parser("stop", help="Stop API and web UI.")
    stop.add_argument("--yes", action="store_true")

    cli = sub.add_parser("cli", help="Launch the CLI.")

    status = sub.add_parser("status", help="Show service status.")
    status.add_argument("--yes", action="store_true")

    logs = sub.add_parser("logs", help="Show service logs.")
    logs.add_argument("--api", action="store_true")
    logs.add_argument("--web", action="store_true")
    logs.add_argument("--lines", type=int, default=200)

    doctor = sub.add_parser("doctor", help="Run health and dependency checks.")
    doctor.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    doctor.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    doctor.add_argument("--no-web", action="store_true")
    doctor.add_argument("--web-tests", action="store_true", help="Also validate Playwright browsers.")
    doctor.add_argument("--yes", action="store_true")

    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if not effective_argv:
        effective_argv = ["start"]
    elif effective_argv[0].startswith("-") and effective_argv[0] not in {"-h", "--help"}:
        effective_argv.insert(0, "start")
    return parser.parse_args(effective_argv)


def main() -> int:
    _print_header()
    args = _parse_args()
    if args.command == "start":
        return _start(args)
    if args.command == "stop":
        return _stop(args)
    if args.command == "cli":
        return _run_cli(args)
    if args.command == "status":
        return _status(args)
    if args.command == "logs":
        return _logs(args)
    if args.command == "doctor":
        return _doctor(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
