"""Shutdown boundary unit tests plus real child process ownership checks."""
import os
import subprocess
import sys

import psutil
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.stack_control import own_control, prepare_control, record_process, stop_owned_process
from web_api.routes.application import router


def test_control_replacement_keeps_previous_marker_readable_until_commit(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from utils.stack_control import shutdown_requested, write_control
    control = tmp_path / "stack-test.json"
    write_control(control, {"shutdown_requested": True})
    original_replace = Path.replace
    def check_old_state(temporary, target):
        assert shutdown_requested(control)
        assert "shutdown_result" not in json.loads(control.read_text())
        return original_replace(temporary, target)
    monkeypatch.setattr(Path, "replace", check_old_state)
    write_control(control, {"shutdown_requested": True, "shutdown_result": "stopped"})
    assert json.loads(control.read_text())["shutdown_result"] == "stopped"
    assert not list(tmp_path.glob("*.tmp"))


def test_shutdown_requires_key_loopback_confirmation_header_and_origin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "unit-shutdown-key")
    control = prepare_control(5173)
    record_process(control, "api", os.getpid())
    # This tests routing only; the callback never terminates any process.
    record_process(control, "web", os.getpid())
    monkeypatch.setenv("CLEAR_STACK_CONTROL", str(control))
    calls = []
    app = FastAPI()
    app.include_router(router)
    app.state.request_shutdown = lambda: calls.append("requested")
    with TestClient(app, client=("127.0.0.1", 40001), headers={"X-API-Key": "unit-shutdown-key"}) as client:
        assert client.get("/api/application/status").json()["shutdown_available"]
        assert client.post("/api/application/shutdown", json={"confirm": True}).status_code == 403
        headers = {"X-Clear-Shutdown": "confirm", "Origin": "http://127.0.0.1:5173"}
        assert client.post("/api/application/shutdown", headers=headers, json={"confirm": False}).status_code == 400
        assert client.post("/api/application/shutdown", headers=headers, json={"confirm": "true"}).status_code == 422
        assert client.post("/api/application/shutdown", headers={**headers, "Origin": "https://untrusted.example"}, json={"confirm": True}).status_code == 403
        assert not calls
        assert client.post("/api/application/shutdown", headers=headers, json={"confirm": True}).status_code == 202
        assert calls == ["requested"]
        assert client.post("/api/application/shutdown", headers={**headers, "X-API-Key": "wrong"}, json={"confirm": True}).status_code == 401
    with TestClient(app, client=("192.0.2.10", 40001), headers={"X-API-Key": "unit-shutdown-key", "X-Clear-Shutdown": "confirm"}) as client:
        assert client.post("/api/application/shutdown", json={"confirm": True}).status_code == 403
    monkeypatch.delenv("CLEAR_STACK_CONTROL")
    assert own_control() is None


def test_reused_pid_identity_cannot_stop_a_real_process():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    identity = {"pid": process.pid, "created": psutil.Process(process.pid).create_time()}
    try:
        assert not stop_owned_process({**identity, "created": identity["created"] - 1})
        assert process.poll() is None
        assert stop_owned_process(identity)
        assert process.wait(timeout=5) is not None
    finally:
        if process.poll() is None:
            stop_owned_process(identity)


def test_orphan_recorded_child_is_stopped_when_parent_no_longer_exists():
    parent = subprocess.Popen([sys.executable, "-c", "pass"])
    parent.wait(timeout=10)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    identity = {"pid": child.pid, "created": psutil.Process(child.pid).create_time()}
    try:
        assert stop_owned_process({"pid": parent.pid, "created": 0, "children": [identity]})
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            stop_owned_process(identity)
