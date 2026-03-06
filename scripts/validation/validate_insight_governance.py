#!/usr/bin/env python3
"""
Validate insight-governance conformance in iterlog markdown artifacts.

Purpose:
- Ensure INSIGHT_PACKET / ARIA_DECISION structure is present and complete.
- Enforce no-silent-scope-drift fields in ARIA_DECISION.
- Verify fallback sections exist for markdown-mode operation.
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

REQUIRED_INSIGHT_FIELDS = {
    "insight_packet_id:",
    "story_id:",
    "detected_at_utc:",
    "context:",
}

REQUIRED_ISSUE_FIELDS = {
    "issue:",
    "impact_if_ignored:",
    "suggested_improvement:",
    "reason:",
    "urgency:",
    "confidence:",
    "evidence:",
    "evidence_signature:",
}

REQUIRED_DECISION_FIELDS = {
    "aria_decision_id:",
    "decision:",
    "scope_update:",
    "scope_impact:",
    "prd_scope_change:",
    "craig_approval_required:",
    "rationale:",
    "expected_outcome:",
    "follow_up_actions:",
}

FALLBACK_SECTIONS = {
    "## Insights Sent To Aria",
    "## Aria Decisions",
    "## Rejected Insight Signatures",
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


def _extract_blocks(body: str, tag: str) -> list[str]:
    pattern = rf"```text\s*({tag}.*?)(?:```)"
    return re.findall(pattern, body, flags=re.DOTALL)


def _validate_insight_packet(block: str, path: Path, idx: int, result: Result) -> None:
    for field in REQUIRED_INSIGHT_FIELDS:
        if field not in block:
            result.err(f"{path}: INSIGHT_PACKET #{idx} missing field {field}")
    for field in REQUIRED_ISSUE_FIELDS:
        if field not in block:
            result.err(f"{path}: INSIGHT_PACKET #{idx} missing issue field {field}")


def _validate_aria_decision(block: str, path: Path, idx: int, result: Result) -> None:
    for field in REQUIRED_DECISION_FIELDS:
        if field not in block:
            result.err(f"{path}: ARIA_DECISION #{idx} missing field {field}")

    scope_impact_match = re.search(r"scope_impact:\s*([A-Z]+)", block)
    if scope_impact_match and scope_impact_match.group(1) not in {"NONE", "MINOR", "MAJOR"}:
        result.err(
            f"{path}: ARIA_DECISION #{idx} invalid scope_impact={scope_impact_match.group(1)!r}"
        )

    prd_change_match = re.search(r"prd_scope_change:\s*(true|false)", block, flags=re.IGNORECASE)
    if not prd_change_match:
        result.err(f"{path}: ARIA_DECISION #{idx} missing/invalid prd_scope_change boolean")


def _validate_file(
    path: Path, require_for_completed: bool, strict: bool, result: Result
) -> None:
    fm = _read_frontmatter(path)
    status = str(fm.get("status", "")).strip()
    body = _read_body(path)

    should_require = status == "completed" if require_for_completed else True

    if should_require:
        for section in FALLBACK_SECTIONS:
            if section not in body:
                msg = f"{path}: missing fallback section {section}"
                if strict:
                    result.err(msg)
                else:
                    result.warn(msg)

    insight_blocks = _extract_blocks(body, "INSIGHT_PACKET")
    decision_blocks = _extract_blocks(body, "ARIA_DECISION")

    if should_require and not insight_blocks:
        msg = f"{path}: no INSIGHT_PACKET blocks found"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)
    if should_require and not decision_blocks:
        msg = f"{path}: no ARIA_DECISION blocks found"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)

    for i, block in enumerate(insight_blocks, start=1):
        _validate_insight_packet(block, path, i, result)
    for i, block in enumerate(decision_blocks, start=1):
        _validate_aria_decision(block, path, i, result)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate insight-governance conformance")
    ap.add_argument("--story-id", help="Validate only iterlog for this story id")
    ap.add_argument(
        "--require-for-completed-only",
        action="store_true",
        help="Require sections/fields only for iterlogs with status=completed",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing sections/blocks as errors (CI gate mode)",
    )
    args = ap.parse_args()

    paths = sorted(ITERLOG_DIR.glob(ITERLOG_GLOB))
    if args.story_id:
        paths = [p for p in paths if args.story_id in p.name]

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
