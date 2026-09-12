import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_inspect():
    spec = importlib.util.spec_from_file_location(
        "clear_inspect_repo", ROOT / "scripts" / "inspect_repo.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


inspect_mod = _load_inspect()


def test_corpus_files_exist_and_hash():
    records = inspect_mod.verify_corpus()
    listed = json.loads((ROOT / "docs" / "inspection" / "corpus.json").read_text(encoding="utf-8"))
    assert [item["path"] for item in records] == listed["files"]
    assert all(len(item["sha256"]) == 64 for item in records)


def test_all_inspection_roles_have_checklists():
    for role in inspect_mod.ROLE_IDS:
        checklist = inspect_mod.load_role_checklist(role)
        assert checklist, role


def test_diff_scan_ignores_context_and_removal_but_preserves_added_claims():
    claim = "Ship a general " + "multi-agent reasoning framework."
    unchanged = "@@ -1,2 +1,2 @@\n " + claim + "\n-Old title\n+Advisory title"
    assert inspect_mod.scan_artifact(inspect_mod.diff_added_text(unchanged)) == []
    removed = "@@ -1 +1 @@\n-" + claim + "\n+Advisory title"
    assert inspect_mod.scan_artifact(inspect_mod.diff_added_text(removed)) == []
    introduced = "@@ -1 +1 @@\n-Old title\n+" + claim
    assert inspect_mod.scan_artifact(inspect_mod.diff_added_text(introduced))


def test_verify_rejects_fabricated_plan(tmp_path):
    plan = tmp_path / "bad-plan.md"
    plan.write_text("Implement a demo mode with fabricated success payloads.\n", encoding="utf-8")
    hits = inspect_mod.scan_artifact(plan.read_text(encoding="utf-8"))
    assert any(item["rule"] == "fabricated_positive_path" for item in hits)


def test_verify_rejects_multi_agent_framework_claim(tmp_path):
    trace = tmp_path / "trace.txt"
    trace.write_text(
        "Ship a general multi-agent reasoning framework in this change.\n",
        encoding="utf-8",
    )
    hits = inspect_mod.scan_artifact(trace.read_text(encoding="utf-8"))
    assert any(item["rule"] == "multi_agent_framework" for item in hits)


def test_isolated_harness_does_not_touch_operator_db(tmp_path, request):
    from tests.harness import cleanup_sqlite_files, isolated_sqlite_path

    operator_db = ROOT / "data" / "lotbook.db"
    legacy_db = ROOT / "data" / "clear.db"
    existed = operator_db.exists()
    legacy_existed = legacy_db.exists()
    mtime = operator_db.stat().st_mtime if existed else None
    legacy_mtime = legacy_db.stat().st_mtime if legacy_existed else None
    db_path = isolated_sqlite_path(request, "probe.db", runtime_dir=tmp_path)
    assert db_path.parent.exists()
    cleanup_sqlite_files(db_path, remove_dir=True)
    if existed:
        assert operator_db.stat().st_mtime == mtime
    else:
        assert not operator_db.exists()
    if legacy_existed:
        assert legacy_db.stat().st_mtime == legacy_mtime
    else:
        assert not legacy_db.exists()
