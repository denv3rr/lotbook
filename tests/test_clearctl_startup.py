from pathlib import Path

import clearctl


def test_no_arguments_defaults_to_one_command_start() -> None:
    args = clearctl._parse_args([])

    assert args.command == "start"
    assert args.yes is True
    assert args.foreground is True
    assert args.no_open is False


def test_explicit_launcher_command_is_preserved() -> None:
    args = clearctl._parse_args(["status"])

    assert args.command == "status"


def test_start_flags_work_without_repeating_start() -> None:
    args = clearctl._parse_args(["--no-open", "--detach"])

    assert args.command == "start"
    assert args.no_open is True
    assert args.foreground is False
    assert args.yes is True


def test_start_can_disable_automatic_dependency_install() -> None:
    args = clearctl._parse_args(["start", "--no-install"])

    assert args.yes is False


def test_missing_web_dependencies_respect_no_install(monkeypatch, tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    called = {"value": False}

    def fake_check_call(*_args, **_kwargs):
        called["value"] = True

    monkeypatch.setattr(clearctl.subprocess, "check_call", fake_check_call)

    assert clearctl._ensure_node_modules(web_dir, "npm", auto_yes=False) is False
    assert called["value"] is False


def test_cleanup_existing_processes_removes_pidfiles(monkeypatch, tmp_path: Path) -> None:
    api_pid = tmp_path / "api.pid"
    web_pid = tmp_path / "web.pid"
    api_pid.write_text("123", encoding="ascii")
    web_pid.write_text("456", encoding="ascii")

    monkeypatch.setattr(clearctl, "API_PID", api_pid)
    monkeypatch.setattr(clearctl, "WEB_PID", web_pid)

    called = []

    def fake_alive(pid: int) -> bool:
        return True

    def fake_terminate(pid: int, **_kwargs) -> bool:
        called.append(pid)
        return True

    monkeypatch.setattr(clearctl, "process_alive", fake_alive)
    monkeypatch.setattr(clearctl, "terminate_pid", fake_terminate)

    clearctl._cleanup_existing_processes()

    assert called == [123, 456]
    assert not api_pid.exists()
    assert not web_pid.exists()


def test_terminate_port_processes_auto_yes(monkeypatch) -> None:
    killed: list[int] = []

    def fake_find_pids(port: int) -> list[int]:
        return [222, 333]

    def fake_terminate(pid: int, **_kwargs) -> bool:
        killed.append(pid)
        return True

    monkeypatch.setattr(clearctl, "find_pids_by_port", fake_find_pids)
    monkeypatch.setattr(clearctl, "filter_matching_pids", lambda pids, _tokens: pids)
    monkeypatch.setattr(clearctl, "process_alive", lambda _pid: True)
    monkeypatch.setattr(clearctl, "terminate_pid", fake_terminate)
    monkeypatch.setattr(clearctl, "wait_for_port_release", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "port_in_use", lambda *_args, **_kwargs: False)

    assert clearctl._terminate_port_processes(8000, "API", tokens=["uvicorn"]) is True
    assert killed == [222, 333]


def test_start_forwards_api_key_to_ui_env(monkeypatch, tmp_path: Path) -> None:
    # Unit-only process argument check; actual shutdown is integration-tested.
    monkeypatch.setattr(clearctl, "prepare_control", lambda _port: tmp_path / "control.json")
    monkeypatch.setattr(clearctl, "record_process", lambda *_args: None)
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "secret-key")
    monkeypatch.setattr(clearctl, "API_PID", tmp_path / "api.pid")
    monkeypatch.setattr(clearctl, "WEB_PID", tmp_path / "web.pid")
    monkeypatch.setattr(clearctl, "API_LOG", tmp_path / "api.log")
    monkeypatch.setattr(clearctl, "WEB_LOG", tmp_path / "web.log")
    monkeypatch.setattr(clearctl, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(clearctl, "_cleanup_existing_processes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(clearctl, "_python_deps_ready", lambda _auto: True)
    monkeypatch.setattr(clearctl, "_terminate_port_processes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "_wait_for_api", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "_npm_available", lambda: "npm")
    monkeypatch.setattr(clearctl, "_ensure_node_modules", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "port_in_use", lambda *_args, **_kwargs: False)

    captured_env = {}

    class DummyProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_spawn(cmd, cwd=None, env=None, detach=True, log_path=None):
        if env is not None:
            captured_env.update(env)
        return DummyProc(123)

    monkeypatch.setattr(clearctl, "_spawn_process", fake_spawn)

    args = type(
        "Args",
        (),
        dict(
            api_port=8000,
            ui_port=5173,
            no_web=False,
            no_open=True,
            foreground=False,
            reload=False,
            yes=True,
        ),
    )()

    assert clearctl._start(args) == 0
    assert captured_env.get("VITE_API_KEY") == "secret-key"


def test_start_stops_when_ui_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(clearctl, "prepare_control", lambda _port: tmp_path / "control.json")
    monkeypatch.setattr(clearctl, "record_process", lambda *_args: None)
    monkeypatch.setattr(clearctl, "API_PID", tmp_path / "api.pid")
    monkeypatch.setattr(clearctl, "WEB_PID", tmp_path / "web.pid")
    monkeypatch.setattr(clearctl, "API_LOG", tmp_path / "api.log")
    monkeypatch.setattr(clearctl, "WEB_LOG", tmp_path / "web.log")
    monkeypatch.setattr(clearctl, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(clearctl, "_cleanup_existing_processes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(clearctl, "_python_deps_ready", lambda _auto: True)
    monkeypatch.setattr(clearctl, "_terminate_port_processes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "_wait_for_api", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "_npm_available", lambda: "npm")
    monkeypatch.setattr(clearctl, "_ensure_node_modules", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(clearctl, "wait_for_port", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(clearctl, "port_in_use", lambda *_args, **_kwargs: False)

    stop_called = {"value": False}

    def fake_stop(_args):
        stop_called["value"] = True
        return 1

    monkeypatch.setattr(clearctl, "_stop", fake_stop)

    class DummyProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_spawn(cmd, cwd=None, env=None, detach=True, log_path=None):
        return DummyProc(123)

    monkeypatch.setattr(clearctl, "_spawn_process", fake_spawn)

    args = type(
        "Args",
        (),
        dict(
            api_port=8000,
            ui_port=5173,
            no_web=False,
            no_open=True,
            foreground=False,
            reload=False,
            yes=True,
        ),
    )()

    assert clearctl._start(args) == 1
    assert stop_called["value"] is True


def test_stop_returns_failure_when_pid_lingers(monkeypatch, tmp_path: Path) -> None:
    api_pid = tmp_path / "api.pid"
    web_pid = tmp_path / "web.pid"
    api_pid.write_text("111", encoding="ascii")
    web_pid.write_text("222", encoding="ascii")

    monkeypatch.setattr(clearctl, "API_PID", api_pid)
    monkeypatch.setattr(clearctl, "WEB_PID", web_pid)
    monkeypatch.setattr(clearctl, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(clearctl, "process_alive", lambda pid: True)
    monkeypatch.setattr(clearctl, "terminate_pid", lambda pid, **_kwargs: True)
    monkeypatch.setattr(clearctl, "wait_for_exit", lambda pid, timeout=5.0: False)
    monkeypatch.setattr(clearctl, "port_in_use", lambda port: True)
    monkeypatch.setattr(clearctl, "_terminate_port_processes", lambda *_args, **_kwargs: True)

    args = type("Args", (), dict(yes=True))()
    assert clearctl._stop(args) == 1
