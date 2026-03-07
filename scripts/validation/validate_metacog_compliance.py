#!/usr/bin/env python3
"""
Validate metacognition compliance in iterlog markdown artifacts.

Purpose:
- Ensure metacognition sections are present for completed stories.
- Ensure each section has minimum required fields.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ITERLOG_DIR = Path("docs/tempmemories")
ITERLOG_GLOB = "iterlog-*.md"

SECTION_PRED = "## Metacognitive Predictions"
SECTION_OUT = "## Metacognitive Outcomes"
SECTION_CAL = "## Metacognitive Calibration"

REQ_PRED_FIELDS = {
    "predicted_outcome",
    "predicted_risks",
    "confidence",
    "verification_plan",
    "expected_metrics",
}

REQ_OUT_FIELDS = {
    "actual_outcome",
    "actual_metrics",
    "wins",
    "misses",
    "new_prevention_rules",
}

REQ_CAL_FIELDS = {
    "predicted_confidence",
    "observed_result",
    "calibration_delta",
    "confidence_adjustment_recommendation",
}


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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_frontmatter(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    raw_yaml = text[4:end]
    data = yaml.safe_load(raw_yaml) or {}
    return data if isinstance(data, dict) else {}


def _read_body(path: Path) -> str:
    text = _read_text(path)
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + 5 :]


def _section_text(body: str, heading: str) -> str | None:
    pattern = rf"(?ms)^({re.escape(heading)}\n.*?)(?=^## |\Z)"
    match = re.search(pattern, body)
    if not match:
        return None
    return match.group(1)


def _contains_field(section_text: str, field: str) -> bool:
    # Require key-like structure (`field:` or field:) to avoid prose-only false passes.
    pattern = rf"(?im)^\s*(?:[-*]\s*)?`?{re.escape(field)}`?\s*:"
    return re.search(pattern, section_text) is not None


def _check_fields(
    section_text: str, fields: set[str], path: Path, section: str, result: Result
) -> None:
    for field in fields:
        if not _contains_field(section_text, field):
            result.err(f"{path}: {section} missing field {field}")


def _extract_story_id(path: Path, fm: dict[str, Any], body: str) -> str:
    if "story_id" in fm:
        return str(fm.get("story_id", "")).strip()

    # Fallback filename convention: iterlog-<story_id>.md
    stem = path.stem
    if stem.startswith("iterlog-"):
        return stem.replace("iterlog-", "", 1)

    # Fallback parse from body if present.
    match = re.search(r"(?im)^\s*story_id\s*:\s*([A-Za-z0-9_-]+)\s*$", body)
    if match:
        return match.group(1).strip()
    return ""


def _extract_status(fm: dict[str, Any], body: str) -> str:
    status = str(fm.get("status", "")).strip().lower()
    if status:
        return status
    match = re.search(r"(?im)^\s*status\s*:\s*([A-Za-z0-9_-]+)\s*$", body)
    if match:
        return match.group(1).strip().lower()
    return ""


def _validate_file(path: Path, require_for_completed: bool, strict: bool, result: Result) -> None:
    fm = _read_frontmatter(path)
    body = _read_body(path)
    status = _extract_status(fm, body)

    should_require = status in {"completed", "complete", "done"} if require_for_completed else True
    if not should_require:
        return

    sections = [SECTION_PRED, SECTION_OUT, SECTION_CAL]
    for section in sections:
        if section not in body:
            msg = f"{path}: missing section {section}"
            if strict:
                result.err(msg)
            else:
                result.warn(msg)

    pred_text = _section_text(body, SECTION_PRED)
    out_text = _section_text(body, SECTION_OUT)
    cal_text = _section_text(body, SECTION_CAL)

    if pred_text:
        _check_fields(pred_text, REQ_PRED_FIELDS, path, SECTION_PRED, result)
    if out_text:
        _check_fields(out_text, REQ_OUT_FIELDS, path, SECTION_OUT, result)
    if cal_text:
        _check_fields(cal_text, REQ_CAL_FIELDS, path, SECTION_CAL, result)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate metacognition compliance")
    ap.add_argument("--story-id", help="Validate only iterlog for this story id")
    ap.add_argument(
        "--require-for-completed-only",
        action="store_true",
        help="Require sections/fields only for iterlogs with status=completed",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing sections/fields as errors",
    )
    args = ap.parse_args()

    paths = sorted(ITERLOG_DIR.glob(ITERLOG_GLOB))
    if args.story_id:
        filtered: list[Path] = []
        for path in paths:
            fm = _read_frontmatter(path)
            body = _read_body(path)
            story_id = _extract_story_id(path, fm, body)
            if story_id == args.story_id:
                filtered.append(path)
        paths = filtered

    result = Result()
    if not paths:
        result.err(f"No iterlog files found in {ITERLOG_DIR}/")
    else:
        for path in paths:
            _validate_file(path, args.require_for_completed_only, args.strict, result)

    for w in result.warnings:
        print(w)
    for e in result.errors:
        print(e, file=sys.stderr)

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
