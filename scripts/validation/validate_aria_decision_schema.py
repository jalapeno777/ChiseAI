#!/usr/bin/env python3
"""Validate ARIA_DECISION packet field name alignment.

Canonical ARIA_DECISION fields (per governance spec):
- aria_decision_id
- decision
- scope_update
- scope_impact
- prd_scope_change
- craig_approval_required
- rationale          (NOT decision_rationale)
- expected_outcome
- follow_up_actions

This script scans Python files under scripts/validation/ for any
references to ``decision_rationale`` (deprecated) and confirms that
``rationale`` is used instead.  Exit 0 on clean, exit 1 if issues found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEPRECATED_FIELD = "decision_rationale"
CANONICAL_FIELD = "rationale"
SELF_PATH = Path(__file__).resolve()

SCOPE_DIR = SELF_PATH.parent
INCLUDE_PATTERNS = {"*.py"}


def scan_for_deprecated_field(root: Path) -> list[tuple[Path, int, str]]:
    """Return list of (file, line_no, line) for deprecated field references."""
    hits: list[tuple[Path, int, str]] = []
    for pattern in INCLUDE_PATTERNS:
        for filepath in sorted(root.rglob(pattern)):
            # Skip this script itself to avoid docstring/constant false positives
            if filepath.resolve() == SELF_PATH:
                continue
            for i, line in enumerate(
                filepath.read_text(encoding="utf-8").splitlines(), 1
            ):
                if DEPRECATED_FIELD in line and not line.strip().startswith("#"):
                    hits.append((filepath, i, line.strip()))
    return hits


def scan_for_canonical_field(root: Path) -> list[tuple[Path, int, str]]:
    """Return list of (file, line_no, line) for canonical field references."""
    hits: list[tuple[Path, int, str]] = []
    for pattern in INCLUDE_PATTERNS:
        for filepath in sorted(root.rglob(pattern)):
            if filepath.resolve() == SELF_PATH:
                continue
            for i, line in enumerate(
                filepath.read_text(encoding="utf-8").splitlines(), 1
            ):
                # Match standalone field references (e.g. "rationale:", .rationale, "rationale")
                if re.search(rf"\b{re.escape(CANONICAL_FIELD)}\b", line):
                    hits.append((filepath, i, line.strip()))
    return hits


def main() -> int:
    deprecated = scan_for_deprecated_field(SCOPE_DIR)
    canonical = scan_for_canonical_field(SCOPE_DIR)

    if deprecated:
        print(
            f"ERROR: Found {len(deprecated)} reference(s) to deprecated field '{DEPRECATED_FIELD}':"
        )
        for filepath, line_no, line in deprecated:
            print(f"  {filepath}:{line_no}: {line}")
        print(f"\n  Replace '{DEPRECATED_FIELD}' with '{CANONICAL_FIELD}'")
        return 1

    print(f"OK: No references to deprecated field '{DEPRECATED_FIELD}' found.")
    print(
        f"OK: Found {len(canonical)} reference(s) to canonical field '{CANONICAL_FIELD}'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
