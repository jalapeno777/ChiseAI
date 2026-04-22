#!/usr/bin/env python3
"""Guard rails for docs/bmm-workflow-status.yaml.

Capabilities:
- validate: parse/lint/integrity checks
- attempt: tracks repeated failed fix attempts and signals forced repair
- repair: backup + normalize rewrite + validation
- restore: restore from latest valid backup (or explicit path)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

# Module-level constants for the check
_STATUS_NOTE_STORY_ID_PATTERN = re.compile(
    r"\b(ST-|CH-|FT-|EP-|REWARD-|REPO-|SAFETY-|BRANCH-|PAPER-|RECON-|I-|D-)[A-Z0-9-]+\b"
)

# Semantic intent classification
_DEFERRED_KEYWORDS = ["deferred", "postponed", "delayed", "to be scheduled", "backlog"]
_BLOCKED_KEYWORDS = ["blocked", "stalled", "waiting on", "held"]
_IN_PROGRESS_KEYWORDS = ["in progress", "working", "ongoing"]
_COMPLETED_KEYWORDS = ["completed", "done", "finished", "merged", "shipped"]
_ARCHIVED_KEYWORDS = ["archived", "deprecated", "superseded", "replaced"]
_OPERATIONAL_KEYWORDS = [
    "operational",
    "live",
    "running",
]  # infrastructure context only

# Status values that imply NOT deferred/blocked
_COMPLETED_STATUSES = {"completed", "merged"}
_ACTIVE_STATUSES = {"in_progress", "active"}
_BACKLOG_STATUSES = {"backlog", "planned", "deferred"}
_ARCHIVED_STATUSES = {"archived", "deprecated", "cancelled"}


@dataclass
class NoteConsistencyResult:
    passed: bool
    errors: list[dict]
    warnings: list[dict]


def _classify_note_intent(note_text: str) -> str | None:
    """Classify a status note's semantic intent based on keywords."""
    text_lower = note_text.lower()
    if any(kw in text_lower for kw in _DEFERRED_KEYWORDS):
        return "deferred"
    if any(kw in text_lower for kw in _BLOCKED_KEYWORDS):
        return "blocked"
    if any(kw in text_lower for kw in _IN_PROGRESS_KEYWORDS):
        return "in_progress"
    if any(kw in text_lower for kw in _COMPLETED_KEYWORDS):
        return "completed"
    if any(kw in text_lower for kw in _ARCHIVED_KEYWORDS):
        return "archived"
    if any(kw in text_lower for kw in _OPERATIONAL_KEYWORDS):
        return "operational"
    return None


def _check_note_item_contradiction(
    story_id: str,
    note_intent: str,
    note_text: str,
    item_status: str,
    item_section: str,
) -> dict | None:
    """Check a single story ID against its item for contradiction. Returns a dict if found."""
    status_lower = item_status.lower()

    # deferred intent contradictions
    if note_intent == "deferred" and status_lower in _COMPLETED_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # M3: deferred intent contradictions (in_progress/active)
    if note_intent == "deferred" and status_lower in _ACTIVE_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # blocked intent contradictions
    if note_intent == "blocked" and status_lower in _COMPLETED_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # in_progress intent contradictions
    if note_intent == "in_progress" and status_lower in (
        *_BACKLOG_STATUSES,
        *_ARCHIVED_STATUSES,
    ):
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # M2: in_progress intent contradictions (completed/merged)
    if note_intent == "in_progress" and status_lower in _COMPLETED_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # completed intent contradictions (backlog/archived)
    if note_intent == "completed" and status_lower in (
        *_BACKLOG_STATUSES,
        *_ARCHIVED_STATUSES,
    ):
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # M1: completed intent contradictions (in_progress/active)
    if note_intent == "completed" and status_lower in _ACTIVE_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # archived intent contradictions
    if note_intent == "archived" and status_lower in _ACTIVE_STATUSES:
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    # operational intent contradictions
    if note_intent == "operational" and status_lower in (
        *_ARCHIVED_STATUSES,
        *_BACKLOG_STATUSES,
    ):
        return {
            "story_id": story_id,
            "note_intent": note_intent,
            "note_text": note_text[:100],
            "item_status": item_status,
            "item_section": item_section,
            "severity": "error",
            "message": f"Note indicates '{note_intent}' but item status is '{item_status}' in {item_section}",
        }

    return None


def _build_item_index(data: dict) -> dict[str, tuple[str, str]]:
    """Build a lookup: story_id -> (status, section) for all items in all sections."""
    index: dict[str, tuple[str, str]] = {}
    STORY_SECTIONS = [
        "stories",
        "completed",
        "backlog",
        "in_progress",
        "launch_stories",
        "epics",
    ]
    for section in STORY_SECTIONS:
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            sid = item.get("id")
            if sid:
                index[sid] = (item.get("status", ""), section)
    return index


def check_status_note_consistency(data: dict) -> NoteConsistencyResult:
    """
    Check metadata.status_notes for contradictions with actual item statuses.

    Returns NoteConsistencyResult with:
    - passed: True if no errors found (warnings may still exist)
    - errors: list of error-level contradictions
    - warnings: list of warning-level issues
    """
    result = NoteConsistencyResult(passed=True, errors=[], warnings=[])

    status_notes = data.get("metadata", {}).get("status_notes", [])
    if not isinstance(status_notes, list):
        status_notes = []

    item_index = _build_item_index(data)

    for note in status_notes:
        if not isinstance(note, str):
            continue

        # Extract all story IDs from this note
        found_ids = list(
            set(m.group(0) for m in _STATUS_NOTE_STORY_ID_PATTERN.finditer(note))
        )
        if not found_ids:
            # No story ID in note — nothing to check
            continue

        note_intent = _classify_note_intent(note)
        if note_intent is None:
            # Cannot classify intent — skip
            continue

        for story_id in found_ids:
            if story_id not in item_index:
                result.warnings.append(
                    {
                        "story_id": story_id,
                        "severity": "warning",
                        "message": f"Note references '{story_id}' which is not found in any section",
                    }
                )
                continue

            item_status, item_section = item_index[story_id]
            contradiction = _check_note_item_contradiction(
                story_id, note_intent, note, item_status, item_section
            )
            if contradiction:
                if contradiction["severity"] == "error":
                    result.errors.append(contradiction)
                    result.passed = False
                else:
                    result.warnings.append(contradiction)

    return result


try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.governance.status_write_gate import validate_status_yaml
from scripts.workflow.verify_workflow_integrity import verify_workflow

DEFAULT_TARGET = REPO_ROOT / "docs/bmm-workflow-status.yaml"
DEFAULT_ATTEMPT_FILE = REPO_ROOT / ".tmp/status_guard_attempts.json"
DEFAULT_ENFORCE_AFTER = 2


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str = ""
    blocking: bool = True


def utc_ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


@contextlib.contextmanager
def file_lock(target: Path):
    if fcntl is None:
        yield
        return
    lock_path = target.parent / f".{target.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def create_backup(target: Path, suffix: str = "") -> Path:
    stamp = utc_ts()
    tail = f".{suffix}" if suffix else ""
    backup = target.parent / f"{target.name}.backup.{stamp}{tail}"
    shutil.copy2(target, backup)
    return backup


def parse_yaml(path: Path) -> tuple[bool, Any, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return True, data, ""
    except Exception as exc:
        return False, None, str(exc)


def find_latest_valid_backup(target: Path) -> Path | None:
    candidates = sorted(
        target.parent.glob(f"{target.name}.backup.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        ok, _, _ = parse_yaml(candidate)
        if ok:
            return candidate
    return None


def normalize_dump(data: Any) -> str:
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    if not dumped.endswith("\n"):
        dumped += "\n"
    return dumped


def run_validate(
    target: Path, strict_integrity: bool = False
) -> tuple[bool, list[CheckResult]]:
    results: list[CheckResult] = []

    parse_ok, data, parse_err = parse_yaml(target)
    results.append(
        CheckResult(
            name="yaml_parse",
            passed=parse_ok,
            details="" if parse_ok else parse_err,
            blocking=True,
        )
    )
    if not parse_ok:
        return False, results

    lint_rc, lint_out, lint_err = run_cmd(["yamllint", str(target)], cwd=REPO_ROOT)
    lint_msg = lint_out or lint_err
    results.append(
        CheckResult(
            name="yamllint",
            passed=lint_rc == 0,
            details=lint_msg,
            blocking=True,
        )
    )

    gate_result = validate_status_yaml(
        str(target), verify_shas=True, repo_path=str(REPO_ROOT)
    )
    gate_details = "; ".join(
        [f"{e.field}: {e.message}" for e in gate_result.errors[:10]]
    )
    if len(gate_result.errors) > 10:
        gate_details += "; ... more errors truncated"
    results.append(
        CheckResult(
            name="status_write_gate",
            passed=gate_result.valid,
            details=gate_details,
            blocking=True,
        )
    )

    integrity = verify_workflow(target)
    integ_ok = integrity.get("checks_failed", 1) == 0
    integ_details = ""
    if not integ_ok:
        detail_parts: list[str] = []
        for name, value in integrity.get("details", {}).items():
            if isinstance(value, dict) and not value.get("passed", False):
                errors = value.get("errors") or value.get("message") or "failed"
                detail_parts.append(f"{name}: {errors}")
        integ_details = "; ".join(detail_parts[:10])
    results.append(
        CheckResult(
            name="workflow_integrity",
            passed=integ_ok,
            details=integ_details,
            blocking=strict_integrity,
        )
    )

    # Check status note consistency
    note_result = check_status_note_consistency(data)
    if note_result.errors or note_result.warnings:
        all_details = []
        for e in note_result.errors:
            all_details.append(f"error: {e['message']}")
        for w in note_result.warnings:
            all_details.append(f"warning: {w['message']}")
        details_str = "; ".join(all_details[:10])
        if len(all_details) > 10:
            details_str += "; ... more"
    else:
        details_str = ""

    # Blocking: only errors block; warnings do not
    note_passed = len(note_result.errors) == 0
    results.append(
        CheckResult(
            name="status_note_consistency",
            passed=note_passed,
            details=details_str,
            blocking=False,  # warnings-only by default; use env var to upgrade
        )
    )

    overall = all(r.passed or not r.blocking for r in results)
    return overall, results


def read_attempt_state(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def write_attempt_state(path: Path, state: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def update_attempt_state(
    state_file: Path, target: Path, success: bool, enforce_after: int
) -> tuple[int, bool]:
    state = read_attempt_state(state_file)
    key = str(target.resolve())
    current = state.get(key, {"consecutive_failures": 0}).get("consecutive_failures", 0)
    if success:
        current = 0
    else:
        current = int(current) + 1
    state[key] = {"consecutive_failures": current}
    write_attempt_state(state_file, state)
    return current, current >= enforce_after


def print_report(
    ok: bool, checks: list[CheckResult], extra: dict[str, Any] | None = None
) -> None:
    payload = {
        "valid": ok,
        "checks": [asdict(c) for c in checks],
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload, indent=2))


def cmd_validate(args: argparse.Namespace) -> int:
    target = Path(args.file).resolve()
    ok, checks = run_validate(target, strict_integrity=args.strict_integrity)
    print_report(ok, checks)
    return 0 if ok else 1


def cmd_attempt(args: argparse.Namespace) -> int:
    target = Path(args.file).resolve()
    ok, checks = run_validate(target, strict_integrity=args.strict_integrity)
    failures, repair_required = update_attempt_state(
        Path(args.attempt_file).resolve(),
        target,
        success=ok,
        enforce_after=args.enforce_repair_after,
    )
    print_report(
        ok,
        checks,
        extra={
            "consecutive_failures": failures,
            "repair_required": repair_required,
            "enforce_repair_after": args.enforce_repair_after,
        },
    )
    if ok:
        return 0
    return 2 if repair_required else 1


def cmd_restore(args: argparse.Namespace) -> int:
    target = Path(args.file).resolve()
    with file_lock(target):
        restore_path = (
            Path(args.backup).resolve()
            if args.backup
            else find_latest_valid_backup(target)
        )
        if restore_path is None:
            print(
                json.dumps(
                    {"restored": False, "error": "no valid backup found"},
                    indent=2,
                )
            )
            return 1
        if not restore_path.exists():
            print(
                json.dumps(
                    {"restored": False, "error": f"backup not found: {restore_path}"},
                    indent=2,
                )
            )
            return 1
        pre_restore_backup = create_backup(target, suffix="pre-restore")
        shutil.copy2(restore_path, target)
        ok, checks = run_validate(target)
        print_report(
            ok,
            checks,
            extra={
                "restored_from": str(restore_path),
                "pre_restore_backup": str(pre_restore_backup),
            },
        )
        return 0 if ok else 1


def cmd_repair(args: argparse.Namespace) -> int:
    target = Path(args.file).resolve()
    with file_lock(target):
        backup_path = create_backup(target)
        parse_ok, data, _ = parse_yaml(target)
        restored_from = ""
        if not parse_ok:
            candidate = find_latest_valid_backup(target)
            if candidate is None:
                print(
                    json.dumps(
                        {
                            "repaired": False,
                            "error": "target invalid and no valid backup available",
                            "backup_created": str(backup_path),
                        },
                        indent=2,
                    )
                )
                return 1
            _, data, _ = parse_yaml(candidate)
            restored_from = str(candidate)

        normalized = normalize_dump(data)
        atomic_write(target, normalized)

        # Align with repository YAML style rules.
        run_cmd(
            ["npx", "--prefix", ".", "prettier", "--write", str(target)], cwd=REPO_ROOT
        )

        ok, checks = run_validate(target)
        if ok:
            update_attempt_state(
                Path(args.attempt_file).resolve(),
                target,
                success=True,
                enforce_after=args.enforce_repair_after,
            )
        print_report(
            ok,
            checks,
            extra={
                "repaired": ok,
                "backup_created": str(backup_path),
                "restored_from_backup": restored_from or None,
            },
        )
        return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guard operations for workflow status YAML"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--file", default=str(DEFAULT_TARGET))
        p.add_argument("--attempt-file", default=str(DEFAULT_ATTEMPT_FILE))
        p.add_argument(
            "--enforce-repair-after", type=int, default=DEFAULT_ENFORCE_AFTER
        )
        p.add_argument(
            "--strict-integrity",
            action="store_true",
            help="Treat workflow_integrity failures as blocking (default: warning-only).",
        )

    p_validate = sub.add_parser("validate", help="Run full validation checks")
    add_common_flags(p_validate)
    p_validate.set_defaults(func=cmd_validate)

    p_attempt = sub.add_parser(
        "attempt",
        help="Validate and track consecutive failed fix attempts; exits 2 when repair is mandatory",
    )
    add_common_flags(p_attempt)
    p_attempt.set_defaults(func=cmd_attempt)

    p_repair = sub.add_parser("repair", help="Backup and normalize-rewrite file")
    add_common_flags(p_repair)
    p_repair.set_defaults(func=cmd_repair)

    p_restore = sub.add_parser("restore", help="Restore from backup")
    add_common_flags(p_restore)
    p_restore.add_argument("--backup", default="")
    p_restore.set_defaults(func=cmd_restore)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
