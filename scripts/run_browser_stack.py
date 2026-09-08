"""Run the actual foreground launcher with disposable local data for acceptance."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    for port in (18080, 15173):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Acceptance port {port} is occupied; nothing was stopped.")
    runtime_root = ROOT / "test_runtime"
    runtime_root.mkdir(exist_ok=True)
    run_id = os.environ.get("CLEAR_ACCEPTANCE_RUN_ID", "manual")
    if not all(character.isalnum() or character == "-" for character in run_id):
        raise ValueError("Invalid acceptance run identifier.")
    runtime = Path(tempfile.mkdtemp(prefix=f"advisory-browser-{run_id}-", dir=runtime_root))
    web = runtime / "web"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(web), str(ROOT / "web")], check=True, capture_output=True)
    else:
        web.symlink_to(ROOT / "web", target_is_directory=True)
    os.chdir(runtime)
    os.environ.update({"PYTHONPATH": str(ROOT), "CLEAR_WEB_API_KEY": "isolated-browser-verification", "VITE_API_BASE": "http://127.0.0.1:18080", "VITE_API_KEY": "isolated-browser-verification"})
    from clearctl import _parse_args, _start
    # The supported launcher normalizes cwd on import. Restore isolated data
    # paths before invoking it; never launch acceptance against operator data.
    os.chdir(runtime)
    if Path.cwd().resolve() != runtime.resolve():
        raise RuntimeError("Unable to establish isolated acceptance data paths.")
    return _start(_parse_args(["start", "--api-port", "18080", "--ui-port", "15173", "--no-open", "--no-install"]))


if __name__ == "__main__":
    raise SystemExit(main())
