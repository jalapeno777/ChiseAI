#!/usr/bin/env python3
"""
Validate ChiseAI iteration-loop compliance using repo-checkable artifacts.

Why: CI cannot reliably access Redis/Qdrant. We therefore require a fallback
iterlog file under docs/tempmemories/ that captures the required fields.

Rules enforced:
- Each iterlog file must have YAML frontmatter with required fields.
- If --story-id is provided, that story must have an iterlog file.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ITERLOG_GLOB = "iterlog-*.md"
ITERLOG_DIR = Path("docs/tempmemories")

REQUIRED_FIELDS = {"story_id", "story_title", "phase", "status", "started_at"}
VALID_PHASES = {"analysis", "planning", "solutioning", "implementation", "testing"}
VALID_STATUSES = {"planned", "in_progress", "blocked", "completed", "deprecated"}


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


def _validate_iterlog_file(path: Path, result: Result) -> dict[str, Any] | None:
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

    return fm


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ChiseAI iterloop compliance")
    parser.add_argument("--story-id", help="Require iterlog for this story id")
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help=(
            "Treat warnings as failures (exit non-zero). Default: warnings do not "
            "fail."
        ),
    )
    args = parser.parse_args()

    result = Result()
    paths = sorted(ITERLOG_DIR.glob(ITERLOG_GLOB)) if ITERLOG_DIR.exists() else []
    if not paths:
        result.err(
            f"No iterlog files found under {ITERLOG_DIR}/. "
            "Expected at least one docs/tempmemories/iterlog-<STORY_ID>.md"
        )
    frontmatters: list[dict[str, Any]] = []
    for p in paths:
        fm = _validate_iterlog_file(p, result)
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

    exit_code = result.exit_code()
    if args.fail_on_warn and result.warnings and exit_code == 0:
        exit_code = 2

    if exit_code == 0:
        print("✅ Iteration-loop compliance checks passed")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
