#!/usr/bin/env python3
"""Whole-repo guardrail scanner for docs/us_gov_standards.md.

This is deterministic static analysis, not a pentest and not a substitute
for the independent inspection roles in docs/inspection_verification.md.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "guardrail_baseline.json"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "playwright-report",
    "test-results",
    "test_runtime",
    "data",
    ".codex",
    "agents",
}

RUNTIME_PYTHON_ROOTS = (
    "modules",
    "web_api",
    "core",
    "interfaces",
    "utils",
    "scripts",
)
RUNTIME_PYTHON_FILES = {
    "run.py",
    "run_web.py",
    "run_cli.py",
    "lotbookctl.py",
}
RUNTIME_WEB_ROOTS = ("web/src",)

SCANNER_SELF = {
    "scripts/check_guardrails.py",
    "scripts/inspect_repo.py",
    "tests/test_guardrail_scan.py",
    "tests/test_inspect.py",
}

FABRICATED_PATTERNS = (
    ("fabricated_runtime", re.compile(r"\bfake_ts\b")),
    ("fabricated_runtime", re.compile(r"\bdemo_mode\b")),
    ("fabricated_runtime", re.compile(r"[?&]demo=")),
    ("fabricated_runtime", re.compile(r"\buseDemoData\b")),
    ("fabricated_runtime", re.compile(r"\bmock_path\b")),
    ("query_api_key", re.compile(r"[?&]api_key=")),
    ("demo_query", re.compile(r"[?&]demo=")),
)

CONFIDENCE_LITERAL = re.compile(
    r"""confidence\s*=\s*['"](?:Low|Medium|High|high|medium|low)['"]"""
)
RANDOM_CALL = re.compile(r"\b(?:random\.|np\.random\.|numpy\.random\.)")

ANALYTICS_RANDOM_PATHS = {
    "modules/client_mgr/calculations.py",
    "modules/client_mgr/regime.py",
    "modules/client_mgr/valuation.py",
    "modules/client_mgr/patterns.py",
    "modules/client_mgr/risk_views.py",
    "utils/report_synth.py",
    "web_api/summarizer.py",
}


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    detail: str
    occurrence: int = 1

    @property
    def finding_id(self) -> str:
        # Line numbers are recorded for humans but omitted from the id so
        # inserting code above an existing handler is not a new finding.
        payload = f"{self.rule}|{self.path}|{self.detail.strip()}|{self.occurrence}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        return f"{self.rule}:{self.path}:{digest}"


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _iter_files() -> Iterator[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def _is_runtime_python(rel: str) -> bool:
    if rel in RUNTIME_PYTHON_FILES:
        return True
    return any(rel == root or rel.startswith(root + "/") for root in RUNTIME_PYTHON_ROOTS)


def _is_runtime_web(rel: str) -> bool:
    return any(rel == root or rel.startswith(root + "/") for root in RUNTIME_WEB_ROOTS)


def _is_test_python(rel: str) -> bool:
    return rel.startswith("tests/") and rel.endswith(".py")


def _strip_line_comment(line: str, kind: str) -> str:
    stripped = line.strip()
    if kind == "python":
        if stripped.startswith("#"):
            return ""
        if " #" in line:
            return line.split(" #", 1)[0]
        return line
    if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
        return ""
    if " //" in line:
        return line.split(" //", 1)[0]
    return line


def _is_broad_exception(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name) and node.id in {"Exception", "BaseException"}:
        return True
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception(elt) for elt in node.elts)
    return False


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name_of(node.value) + "." + node.attr
    return ""


LOGGING_NAMES = {
    "logging",
    "logger",
    "LOGGER",
    "log",
    "console",
    "print",
}


def _calls_logger(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func).lower()
            if any(token in name for token in ("log", "logger", "exception", "warning", "error", "print", "console")):
                return True
    return False


def _is_silent(body: list[ast.stmt]) -> bool:
    if not body:
        return True
    meaningful = [stmt for stmt in body if not isinstance(stmt, ast.Pass)]
    if not meaningful:
        return True
    if all(isinstance(stmt, (ast.Pass, ast.Continue, ast.Expr)) and not _calls_logger(stmt) for stmt in body):
        if all(isinstance(stmt, (ast.Pass, ast.Continue)) or (
            isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
        ) for stmt in body):
            return True
    if len(body) == 1 and isinstance(body[0], ast.Continue):
        return True
    return False


def _scan_python_exceptions(path: Path, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not _is_broad_exception(handler.type):
                continue
            rule = "bare_except" if handler.type is None else "broad_except"
            silent = _is_silent(handler.body)
            if silent:
                rule = "silent_except"
            elif rule == "bare_except":
                pass
            else:
                rule = "logged_broad_except"
            detail = ast.get_source_segment(source, handler) or "except"
            first_line = detail.strip().splitlines()[0][:160]
            findings.append(
                Finding(rule=rule, path=rel, line=handler.lineno, detail=first_line)
            )
    return findings


def _scan_text_patterns(path: Path, rel: str, kind: str, rules: Iterable[tuple[str, re.Pattern[str]]]) -> list[Finding]:
    findings: list[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return findings
    for index, line in enumerate(lines, start=1):
        code = _strip_line_comment(line, kind)
        if not code.strip():
            continue
        for rule, pattern in rules:
            if pattern.search(code):
                findings.append(
                    Finding(rule=rule, path=rel, line=index, detail=code.strip()[:160])
                )
    return findings


def collect_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files():
        rel = _rel(path)
        if rel in SCANNER_SELF:
            continue
        suffix = path.suffix.lower()
        if _is_runtime_python(rel) and suffix == ".py":
            findings.extend(_scan_python_exceptions(path, rel))
            findings.extend(
                _scan_text_patterns(path, rel, "python", FABRICATED_PATTERNS)
            )
            if rel in ANALYTICS_RANDOM_PATHS:
                findings.extend(
                    _scan_text_patterns(
                        path, rel, "python", (("analytics_random", RANDOM_CALL),)
                    )
                )
        if _is_runtime_web(rel) and suffix in {".ts", ".tsx", ".js", ".jsx"}:
            findings.extend(
                _scan_text_patterns(path, rel, "js", FABRICATED_PATTERNS)
            )
        if _is_test_python(rel):
            findings.extend(
                _scan_text_patterns(
                    path,
                    rel,
                    "python",
                    (("invented_confidence", CONFIDENCE_LITERAL),),
                )
            )
    findings.sort(key=lambda item: (item.rule, item.path, item.line, item.detail))
    numbered: list[Finding] = []
    seen: dict[tuple[str, str, str], int] = {}
    for item in findings:
        key = (item.rule, item.path, item.detail.strip())
        seen[key] = seen.get(key, 0) + 1
        numbered.append(
            Finding(
                rule=item.rule,
                path=item.path,
                line=item.line,
                detail=item.detail,
                occurrence=seen[key],
            )
        )
    return numbered


def findings_payload(findings: list[Finding]) -> dict[str, object]:
    return {
        "version": 1,
        "count": len(findings),
        "findings": [
            {
                "id": item.finding_id,
                **asdict(item),
            }
            for item in findings
        ],
    }


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "findings": []}
    return json.loads(path.read_text(encoding="utf-8"))


def compare_to_baseline(findings: list[Finding], baseline: dict[str, object]) -> tuple[list[str], list[str]]:
    current_ids = {item.finding_id for item in findings}
    baseline_ids = {entry["id"] for entry in baseline.get("findings", [])}
    new_ids = sorted(current_ids - baseline_ids)
    missing_ids = sorted(baseline_ids - current_ids)
    return new_ids, missing_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the repo for documented guardrail classes.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable findings.")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite tests/guardrail_baseline.json from the current scan.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when findings are not exactly the committed baseline.",
    )
    args = parser.parse_args(argv)

    findings = collect_findings()
    payload = findings_payload(findings)
    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    if args.strict:
        new_ids, missing_ids = compare_to_baseline(findings, load_baseline())
        if new_ids or missing_ids:
            if new_ids:
                sys.stderr.write("New guardrail findings:\n")
                for finding_id in new_ids:
                    sys.stderr.write(f"  {finding_id}\n")
            if missing_ids:
                sys.stderr.write("Baseline findings no longer present; shrink tests/guardrail_baseline.json:\n")
                for finding_id in missing_ids:
                    sys.stderr.write(f"  {finding_id}\n")
            return 1
        if not args.json:
            sys.stdout.write(f"{len(findings)} finding(s) match baseline\n")
        return 0
    if not args.json:
        for item in findings:
            sys.stdout.write(f"{item.finding_id} {item.path}:{item.line} {item.detail}\n")
        sys.stdout.write(f"{len(findings)} finding(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
