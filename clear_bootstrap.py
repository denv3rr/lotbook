from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
RUNTIME_LOCK = REPO_ROOT / "requirements-web.lock"
REQUIRED_RUNTIME_MODULES = (
    "cryptography",
    "dotenv",
    "fastapi",
    "finnhub",
    "httpx",
    "numpy",
    "pandas",
    "psutil",
    "requests",
    "rich",
    "sqlalchemy",
    "uvicorn",
    "yfinance",
)


def missing_runtime_modules() -> list[str]:
    return [name for name in REQUIRED_RUNTIME_MODULES if importlib.util.find_spec(name) is None]


def _lock_has_hashes(path: Path | None = None) -> bool:
    path = path or RUNTIME_LOCK
    if not path.is_file():
        return False
    return any(
        "--hash=" in line
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def ensure_runtime_dependencies(*, auto_install: bool) -> bool:
    missing = missing_runtime_modules()
    if not missing:
        return True

    print(">> Missing Python runtime dependencies:", ", ".join(missing))
    if not auto_install:
        print(">> Automatic install is disabled. Install requirements-web.lock and retry.")
        return False
    if not _lock_has_hashes():
        print(">> requirements-web.lock is missing or unhashed. Refusing unverified install.")
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
                str(RUNTIME_LOCK),
            ],
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.CalledProcessError):
        print(">> Python dependency install failed. Review pip output and retry.")
        return False

    importlib.invalidate_caches()
    remaining = missing_runtime_modules()
    if remaining:
        print(">> Python runtime is still incomplete:", ", ".join(remaining))
        return False
    return True


def main() -> int:
    os.chdir(REPO_ROOT)
    if not ensure_runtime_dependencies(auto_install="--no-install" not in sys.argv[1:]):
        return 1

    import clearctl

    return clearctl.main()


if __name__ == "__main__":
    raise SystemExit(main())
