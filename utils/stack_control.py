"""Per-launch ownership records for application-requested shutdown.

Only recorded process identities are eligible; ports are never kill targets.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psutil


def prepare_control(ui_port: int) -> Path:
    directory = Path("data/runtime").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"stack-{uuid4().hex}.json"
    launcher = psutil.Process()
    path.write_text(json.dumps({"ui_origin": f"http://127.0.0.1:{ui_port}", "processes": {"launcher": {"pid": launcher.pid, "created": launcher.create_time()}}}), encoding="utf-8")
    return path


def write_control(path: Path, payload: dict) -> None:
    """Readers see either complete prior state or complete replacement state."""
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record_process(path: Path, name: str, pid: int) -> None:
    process = psutil.Process(pid)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["processes"][name] = {"pid": pid, "created": process.create_time(), "children": [{"pid": child.pid, "created": child.create_time()} for child in process.children(recursive=True)]}
    write_control(path, payload)


def own_control() -> tuple[Path, dict] | None:
    raw = os.environ.get("CLEAR_STACK_CONTROL")
    if not raw:
        return None
    path = Path(raw).resolve()
    if path.parent != Path("data/runtime").resolve() or not path.name.startswith("stack-") or path.suffix != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        api = payload["processes"]["api"]
        current = psutil.Process()
        if api["pid"] != current.pid or api["created"] != current.create_time():
            return None
        return path, payload
    except (OSError, ValueError, KeyError, TypeError, psutil.Error):
        return None


def stop_owned_process(identity: dict) -> bool:
    children_ok = all([stop_owned_process(child) for child in identity.get("children", [])])
    try:
        process = psutil.Process(identity["pid"])
        if process.create_time() != identity["created"]:
            return False
        targets = process.children(recursive=True) + [process]
        for target in targets:
            try:
                target.terminate()
            except psutil.NoSuchProcess:
                continue
        _, alive = psutil.wait_procs(targets, timeout=5)
        for target in alive:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                continue
        _, remaining = psutil.wait_procs(alive, timeout=5)
        return not remaining and children_ok
    except psutil.NoSuchProcess:
        return children_ok
    except (psutil.AccessDenied, KeyError, TypeError):
        return False


def shutdown_requested(path: Path) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("shutdown_requested") is True
    except (OSError, ValueError, TypeError):
        return False


def mark_shutdown_requested() -> None:
    control = own_control()
    if control:
        path, payload = control
        payload["shutdown_requested"] = True
        write_control(path, payload)


def finish_shutdown() -> bool:
    control = own_control()
    if control is None:
        return True
    path, payload = control
    web = payload["processes"].get("web")
    succeeded = stop_owned_process(web) if web else True
    payload["shutdown_result"] = "stopped" if succeeded else "failed"
    write_control(path, payload)
    if succeeded:
        for name, identity in payload["processes"].items():
            pid_path = path.parent / f"{name}.pid"
            if pid_path.exists() and pid_path.read_text(encoding="ascii").strip() == str(identity["pid"]):
                pid_path.unlink()
    return succeeded
