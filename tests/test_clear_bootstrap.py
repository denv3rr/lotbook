from __future__ import annotations

import subprocess
import re
from pathlib import Path

import clear_bootstrap


def _direct_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "==" not in text:
            continue
        package, version = text.split("==", 1)
        pins[package.lower()] = version.split(";", 1)[0].strip()
    return pins


def test_missing_dependencies_respect_no_install(monkeypatch) -> None:
    monkeypatch.setattr(clear_bootstrap, "missing_runtime_modules", lambda: ["fastapi"])
    called = {"value": False}

    def fake_check_call(*_args, **_kwargs) -> None:
        called["value"] = True

    monkeypatch.setattr(clear_bootstrap.subprocess, "check_call", fake_check_call)

    assert clear_bootstrap.ensure_runtime_dependencies(auto_install=False) is False
    assert called["value"] is False


def test_runtime_install_uses_hashed_lock(monkeypatch, tmp_path: Path) -> None:
    lock = tmp_path / "requirements-web.lock"
    lock.write_text(
        "fastapi==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    checks = iter((["fastapi"], []))
    captured: dict[str, object] = {}

    monkeypatch.setattr(clear_bootstrap, "RUNTIME_LOCK", lock)
    monkeypatch.setattr(clear_bootstrap, "missing_runtime_modules", lambda: next(checks))

    def fake_check_call(command, cwd=None) -> None:
        captured["command"] = command
        captured["cwd"] = cwd

    monkeypatch.setattr(clear_bootstrap.subprocess, "check_call", fake_check_call)

    assert clear_bootstrap.ensure_runtime_dependencies(auto_install=True) is True
    command = captured["command"]
    assert isinstance(command, list)
    assert "--require-hashes" in command
    assert command[-1] == str(lock)
    assert captured["cwd"] == clear_bootstrap.REPO_ROOT


def test_failed_runtime_install_is_reported(monkeypatch, tmp_path: Path) -> None:
    lock = tmp_path / "requirements-web.lock"
    lock.write_text(
        "fastapi==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(clear_bootstrap, "RUNTIME_LOCK", lock)
    monkeypatch.setattr(clear_bootstrap, "missing_runtime_modules", lambda: ["fastapi"])

    def fail_install(*_args, **_kwargs) -> None:
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(clear_bootstrap.subprocess, "check_call", fail_install)

    assert clear_bootstrap.ensure_runtime_dependencies(auto_install=True) is False


def test_runtime_input_and_lock_match_primary_requirements() -> None:
    source_pins = _direct_pins(clear_bootstrap.REPO_ROOT / "requirements-web.in")
    primary_pins = _direct_pins(clear_bootstrap.REPO_ROOT / "requirements.txt")
    lock_text = clear_bootstrap.RUNTIME_LOCK.read_text(encoding="utf-8")

    assert source_pins
    assert clear_bootstrap._lock_has_hashes()
    for package, version in source_pins.items():
        assert primary_pins.get(package) == version
        assert re.search(rf"(?mi)^{re.escape(package)}=={re.escape(version)}(?:\s|$)", lock_text)
