#!/usr/bin/env python3
"""Independent inspection runner bound to the documentation corpus.

This is a verifier, not a general multi-agent reasoning framework.
See docs/inspection_verification.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "docs" / "inspection" / "corpus.json"
ROLES_PATH = ROOT / "docs" / "inspection" / "roles.md"
CHECK_GUARDRAILS = ROOT / "scripts" / "check_guardrails.py"

ROLE_IDS = (
    "standards-lead",
    "data-provenance",
    "backend-safety",
    "frontend-accessibility",
    "browser-verification",
    "analytics-integrity",
    "visual-systems",
)

FORBIDDEN_PLAN_PATTERNS = (
    ("fabricated_positive_path", re.compile(r"\b(demo mode|synthetic positive|fabricated success|fake_ts)\b", re.I)),
    ("phase2_bypass", re.compile(r"\b(start|land|implement)\b.{0,40}\b(reliefweb|eonet|firms|phase 2 globe)\b", re.I)),
    ("multi_agent_framework", re.compile(r"\b(general multi-agent|multiagent reasoning framework|autonomous agent mesh)\b", re.I)),
    ("invented_confidence", re.compile(r"\bconfidence\b.{0,20}\b(high|medium|low)\b", re.I)),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def verify_corpus() -> list[dict[str, str]]:
    corpus = load_corpus()
    records = []
    missing = []
    for rel in corpus["files"]:
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        records.append({"path": rel, "sha256": _sha256(path)})
    if missing:
        raise FileNotFoundError("Missing corpus files: " + ", ".join(missing))
    return records


def load_role_checklist(role: str) -> list[str]:
    text = ROLES_PATH.read_text(encoding="utf-8")
    heading = f"## {role}"
    if heading not in text:
        raise KeyError(f"Unknown inspection role {role!r}")
    section = text.split(heading, 1)[1]
    next_heading = section.find("\n## ")
    if next_heading != -1:
        section = section[:next_heading]
    return [line[6:].strip() for line in section.splitlines() if line.startswith("- [ ]")]


def scan_artifact(text: str) -> list[dict[str, str]]:
    hits = []
    for rule, pattern in FORBIDDEN_PLAN_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append({"rule": rule, "match": match.group(0)})
    return hits


def run_guardrail_scan() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(CHECK_GUARDRAILS), "--json", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip() else {"count": 0, "findings": []}
    payload["exit_code"] = completed.returncode
    payload["stderr"] = completed.stderr.strip()
    return payload


def _read_diff(git_range: str) -> str:
    completed = subprocess.run(
        ["git", "diff", git_range],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git diff {git_range} failed")
    return completed.stdout


def diff_added_text(text: str) -> str:
    """Artifact rules judge additions, not removed lines or unchanged context.

    Whole-repository guardrail scanning and human diff review still cover the
    resulting tree. A diff-context phrase is not an introduced artifact claim.
    """
    return "\n".join(line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++"))


def build_record(args: argparse.Namespace) -> dict[str, object]:
    corpus = verify_corpus()
    roles = ROLE_IDS if args.role == "all" else (args.role,)
    artifacts = []
    combined_text = ""
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.is_file():
            plan_path = ROOT / args.plan
        text = plan_path.read_text(encoding="utf-8")
        artifacts.append({"kind": "plan", "path": str(plan_path)})
        combined_text += text + "\n"
    if args.code:
        code_path = Path(args.code)
        if not code_path.is_file():
            code_path = ROOT / args.code
        text = code_path.read_text(encoding="utf-8")
        artifacts.append({"kind": "code", "path": str(code_path)})
        combined_text += text + "\n"
    if args.trace:
        trace_path = Path(args.trace)
        if not trace_path.is_file():
            trace_path = ROOT / args.trace
        text = trace_path.read_text(encoding="utf-8")
        artifacts.append({"kind": "trace", "path": str(trace_path)})
        combined_text += text + "\n"
    if args.diff:
        text = _read_diff(args.diff)
        artifacts.append({"kind": "diff", "range": args.diff})
        combined_text += diff_added_text(text) + "\n"

    artifact_hits = scan_artifact(combined_text) if combined_text else []
    guardrails = run_guardrail_scan()
    role_records = [
        {"role": role, "checklist": load_role_checklist(role)}
        for role in roles
    ]
    status = "pass"
    if artifact_hits or guardrails.get("exit_code") not in (0, None):
        status = "fail"
    if not artifacts:
        status = "incomplete"
    return {
        "inspector": "clear.inspection/1",
        "status": status,
        "independent": True,
        "product": "local-first portfolio/analytics/OSINT with assistant surface",
        "not": "general multi-agent reasoning framework",
        "corpus": corpus,
        "roles": role_records,
        "artifacts": artifacts,
        "artifact_hits": artifact_hits,
        "guardrail_scan": {
            "count": guardrails.get("count"),
            "exit_code": guardrails.get("exit_code"),
            "stderr": guardrails.get("stderr"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run corpus-bound independent inspection.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("corpus", help="Verify the documentation corpus is present.")
    sub.add_parser("scan", help="Run the whole-repo guardrail scanner in strict mode.")
    sub.add_parser("roles", help="List inspection roles and checklists.")

    verify = sub.add_parser("verify", help="Independently verify a plan, diff, code path, or trace.")
    verify.add_argument("--role", required=True, choices=(*ROLE_IDS, "all"))
    verify.add_argument("--plan", help="Path to a plan or design note.")
    verify.add_argument("--code", help="Path to generated or authored code.")
    verify.add_argument("--trace", help="Path to a reasoning trace.")
    verify.add_argument("--diff", help="Git diff range, for example origin/main...HEAD.")

    args = parser.parse_args(argv)
    if args.command == "corpus":
        for record in verify_corpus():
            print(f"{record['sha256']}  {record['path']}")
        return 0
    if args.command == "scan":
        return subprocess.call([sys.executable, str(CHECK_GUARDRAILS), "--strict"], cwd=ROOT)
    if args.command == "roles":
        for role in ROLE_IDS:
            print(role)
            for item in load_role_checklist(role):
                print(f"  - {item}")
        return 0
    record = build_record(args)
    json.dump(record, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if record["status"] == "fail":
        return 1
    if record["status"] == "incomplete":
        sys.stderr.write("Inspection incomplete: provide --plan, --code, --diff, or --trace.\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
