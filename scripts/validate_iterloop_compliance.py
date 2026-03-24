#!/usr/bin/env python3
"""
Validate ChiseAI iteration-loop compliance using repo-checkable artifacts.

Why: CI cannot reliably access Redis/Qdrant. We therefore require a fallback
iterlog file under docs/tempmemories/ that captures the required fields.

Rules enforced:
- Each iterlog file must have YAML frontmatter with required fields.
- If --story-id is provided, that story must have an iterlog file.
- If --require-structured-issues, completed iterlogs must have structured issues.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

ITERLOG_GLOB = "iterlog-*.md"
ITERLOG_DIR = Path("docs/tempmemories")
LEGACY_EXEMPTIONS_PATH = Path("docs/governance/legacy-exemptions.yaml")

REQUIRED_FIELDS = {"story_id", "story_title", "phase", "status", "started_at"}
VALID_PHASES = {"analysis", "planning", "solutioning", "implementation", "testing"}
VALID_STATUSES = {"planned", "in_progress", "blocked", "completed", "deprecated"}

# Structured issues schema
REQUIRED_ISSUE_FIELDS = {
    "issue_type",
    "root_cause",
    "fix_applied",
    "time_lost_minutes",
    "recurrence_hint",
    "impact_area",
    "resolved",
}
VALID_IMPACT_AREAS = {"throughput", "efficiency", "accuracy", "reliability"}


@dataclass
class Result:
    errors: list[str]
    warnings: list[str]

    def __init__(self) -> None:
        self.errors = []
        self.warnings = []

    def err(self, msg: str) -> None:
        self.errors.append(f"ERROR: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"WARNING: {msg}")

    def exit_code(self) -> int:
        if self.errors:
            return 1
        return 0


def _read_frontmatter(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter start '---'")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("missing YAML frontmatter end '---'")
    raw_yaml = text[4:end]
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return data


def _read_body(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return ""
    return text[end + 5 :]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_legacy_exempt(path: Path, fm: dict[str, Any], include_archived: bool) -> bool:
    if _to_bool(fm.get("legacy_exempt")):
        return True
    if str(fm.get("compliance_mode", "")).strip().lower() == "legacy_exempt":
        return True
    return bool(
        include_archived
        and "docs/tempmemories/archived/" in str(path).replace("\\", "/")
    )


def _load_legacy_exemptions() -> set[str]:
    if not LEGACY_EXEMPTIONS_PATH.exists():
        return set()
    try:
        data = yaml.safe_load(LEGACY_EXEMPTIONS_PATH.read_text(encoding="utf-8")) or {}
        story_ids = data.get("iterlog_story_ids", [])
        if not isinstance(story_ids, list):
            return set()
        return {str(s).strip() for s in story_ids if str(s).strip()}
    except Exception:
        return set()


def _story_id_for_filter(path: Path, fm: dict[str, Any]) -> str:
    sid = str(fm.get("story_id", "")).strip()
    if sid:
        return sid
    stem = path.stem
    if stem.startswith("iterlog-"):
        return stem.replace("iterlog-", "", 1).strip()
    return ""


def _extract_structured_issues(body: str) -> tuple[list[dict[str, Any]] | None, str]:
    """
    Extract structured issues from the iterlog body.

    Returns:
        tuple: (issues_list or None if not found, error_message or "")
    """
    # Look for "## Structured Issues" section
    pattern = r"##\s+Structured\s+Issues\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, "missing '## Structured Issues' section"

    section_content = match.group(1).strip()
    if not section_content:
        return None, "structured issues section is empty"

    # Try to parse the YAML content
    try:
        # Find the 'issues:' key and parse the list
        yaml_match = re.search(r"issues:\s*\n(.*)", section_content, re.DOTALL)
        if not yaml_match:
            # Check for empty sentinel: "issues: []"
            if re.search(r"issues:\s*\[\s*\]", section_content):
                return [], ""
            return None, "no 'issues:' key found in structured issues section"

        yaml_content = "issues:\n" + yaml_match.group(1)
        parsed = yaml.safe_load(yaml_content)
        if not isinstance(parsed, dict) or "issues" not in parsed:
            return None, "invalid YAML structure in structured issues section"

        issues = parsed["issues"]
        if issues is None:
            return [], ""
        if not isinstance(issues, list):
            return None, "'issues' must be a list or empty array"

        return issues, ""
    except yaml.YAMLError as e:
        return None, f"YAML parse error in structured issues: {e}"


def _validate_single_issue(
    issue: dict[str, Any], index: int, path: Path, result: Result
) -> bool:
    """Validate a single issue entry. Returns True if valid."""
    if not isinstance(issue, dict):
        result.err(
            f"{path}: issue #{index + 1} must be a mapping, got {type(issue).__name__}"
        )
        return False

    is_valid = True
    missing = sorted(REQUIRED_ISSUE_FIELDS - set(issue.keys()))
    if missing:
        result.err(
            f"{path}: issue #{index + 1} missing required fields: {', '.join(missing)}"
        )
        is_valid = False

    # Validate impact_area enum
    impact_area = issue.get("impact_area")
    if impact_area and impact_area not in VALID_IMPACT_AREAS:
        result.err(
            f"{path}: issue #{index + 1} impact_area must be one of "
            f"{sorted(VALID_IMPACT_AREAS)} (got {impact_area!r})"
        )
        is_valid = False

    # Validate time_lost_minutes is an integer
    time_lost = issue.get("time_lost_minutes")
    if time_lost is not None and not isinstance(time_lost, int):
        result.err(
            f"{path}: issue #{index + 1} time_lost_minutes must be an integer, "
            f"got {type(time_lost).__name__}"
        )
        is_valid = False

    # Validate resolved is a boolean
    resolved = issue.get("resolved")
    if resolved is not None and not isinstance(resolved, bool):
        result.err(
            f"{path}: issue #{index + 1} resolved must be a boolean, "
            f"got {type(resolved).__name__}"
        )
        is_valid = False

    return is_valid


def _validate_structured_issues(
    body: str, path: Path, result: Result, require_structured_issues: bool
) -> None:
    """Validate structured issues section in the iterlog body."""
    issues, error = _extract_structured_issues(body)

    if issues is None:
        if require_structured_issues:
            result.err(f"{path}: {error}")
        else:
            result.warn(f"{path}: {error}")
        return

    # Validate each issue entry
    for i, issue in enumerate(issues):
        _validate_single_issue(issue, i, path, result)


def _validate_iterlog_file(
    path: Path, result: Result, require_structured_issues: bool = True
) -> dict[str, Any] | None:
    try:
        fm = _read_frontmatter(path)
    except Exception as e:  # noqa: BLE001
        result.err(f"{path}: {e}")
        return None

    missing = sorted(REQUIRED_FIELDS - set(fm.keys()))
    if missing:
        result.err(f"{path}: missing required fields: {', '.join(missing)}")

    phase = fm.get("phase")
    if phase not in VALID_PHASES:
        result.err(
            f"{path}: phase must be one of {sorted(VALID_PHASES)} (got {phase!r})"
        )

    status = fm.get("status")
    if status not in VALID_STATUSES:
        result.err(
            f"{path}: status must be one of {sorted(VALID_STATUSES)} (got {status!r})"
        )

    if status == "completed" and "completed_at" not in fm:
        result.warn(f"{path}: status=completed but completed_at missing")

    # Content-level guardrails for fallback iterlogs (CI cannot see Redis/Qdrant).
    body = _read_body(path)
    if "## Incidents" not in body:
        result.warn(
            f"{path}: missing '## Incidents' section (required fallback sink "
            "when Redis is unavailable)"
        )
    if "## Scope Ownership" not in body:
        result.warn(
            f"{path}: missing '## Scope Ownership' section (recommended for parallel "
            "safety when Redis is unavailable)"
        )

    # Validate structured issues (required for completed stories)
    if status == "completed":
        _validate_structured_issues(body, path, result, require_structured_issues)
    elif require_structured_issues:
        # For non-completed stories, just warn if section is missing
        issues, error = _extract_structured_issues(body)
        if issues is None:
            result.warn(f"{path}: {error} (recommended for tracking issues early)")

    return fm


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ChiseAI iterloop compliance")
    parser.add_argument("--story-id", help="Require iterlog for this story id")
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help=(
            "Treat warnings as failures (exit non-zero). Default: warnings do not fail."
        ),
    )
    parser.add_argument(
        "--require-structured-issues",
        action="store_true",
        default=True,
        help=(
            "Require structured issues section for completed iterlogs. "
            "Default: True. Use --no-require-structured-issues to disable."
        ),
    )
    parser.add_argument(
        "--no-require-structured-issues",
        dest="require_structured_issues",
        action="store_false",
        help="Disable structured issues requirement (for backward compatibility).",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Include legacy-exempt iterlogs (default: skip legacy-exempt files).",
    )
    parser.add_argument(
        "--legacy-archive-exempt",
        action="store_true",
        default=True,
        help="Treat docs/tempmemories/archived/* iterlogs as legacy-exempt (default: true).",
    )
    parser.add_argument(
        "--no-legacy-archive-exempt",
        dest="legacy_archive_exempt",
        action="store_false",
        help="Do not auto-exempt archived iterlogs.",
    )
    args = parser.parse_args()

    result = Result()
    paths = sorted(ITERLOG_DIR.glob(ITERLOG_GLOB)) if ITERLOG_DIR.exists() else []
    exempt_story_ids = _load_legacy_exemptions()
    skipped_legacy = 0
    if not args.include_legacy:
        filtered_paths: list[Path] = []
        for p in paths:
            try:
                fm = _read_frontmatter(p)
            except Exception:
                fm = {}
            story_id = _story_id_for_filter(p, fm)
            if story_id in exempt_story_ids:
                skipped_legacy += 1
                continue
            if _is_legacy_exempt(p, fm, include_archived=args.legacy_archive_exempt):
                skipped_legacy += 1
                continue
            filtered_paths.append(p)
        paths = filtered_paths
    if not paths:
        result.warn(
            f"No iterlog files found under {ITERLOG_DIR}/. "
            "Assuming Redis/Qdrant are currently available and no fallback artifacts "
            "are needed."
        )
    frontmatters: list[dict[str, Any]] = []
    for p in paths:
        fm = _validate_iterlog_file(p, result, args.require_structured_issues)
        if fm:
            frontmatters.append(fm)

    if args.story_id:
        wanted = args.story_id.strip()
        if not any(fm.get("story_id") == wanted for fm in frontmatters):
            result.err(
                f"Missing iterlog for story_id={wanted}. "
                f"Create docs/tempmemories/iterlog-{wanted}.md"
            )

    for msg in result.errors:
        print(msg, file=sys.stderr)
    for msg in result.warnings:
        print(msg)
    if skipped_legacy:
        print(
            f"INFO: skipped {skipped_legacy} legacy-exempt iterlog file(s) "
            "(use --include-legacy to include)"
        )

    exit_code = result.exit_code()
    if args.fail_on_warn and result.warnings and exit_code == 0:
        exit_code = 2

    if exit_code == 0:
        print("✅ Iteration-loop compliance checks passed")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
