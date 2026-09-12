from core.database import adopt_legacy_database


def test_adopt_legacy_does_not_rename_under_pytest(tmp_path):
    current = tmp_path / "lotbook.db"
    legacy = tmp_path / "clear.db"
    legacy.write_bytes(b"sqlite")
    result = adopt_legacy_database(current, legacy)
    assert result == current
    assert legacy.exists()
    assert not current.exists()
