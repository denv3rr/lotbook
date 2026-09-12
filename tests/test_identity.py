from utils.identity import WEB_API_KEY_ENV, getenv


def test_getenv_prefers_lotbook_name(monkeypatch):
    monkeypatch.setenv(WEB_API_KEY_ENV, "current-key")
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "legacy-key")
    assert getenv(WEB_API_KEY_ENV) == "current-key"


def test_getenv_falls_back_to_legacy_clear_name(monkeypatch):
    monkeypatch.delenv(WEB_API_KEY_ENV, raising=False)
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "legacy-key")
    assert getenv(WEB_API_KEY_ENV) == "legacy-key"
