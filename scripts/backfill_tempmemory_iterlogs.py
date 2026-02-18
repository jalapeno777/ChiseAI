#!/usr/bin/env python3
"""
Backfill docs/tempmemories iterlog files with standard sections.

Why: older iterlog markdown files may be missing sections that newer workflows
assume exist (Incidents, Scope Ownership).

This script is idempotent and only inserts missing headings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.bootstrap import bootstrap

ITERLOG_DIR = Path("docs/tempmemories")
GLOB = "iterlog-*.md"

REQUIRED_SECTIONS = [
    ("## Scope Ownership", "- TBD\n"),
    ("## Incidents", "- TBD\n"),
]


def _ensure_sections(text: str) -> tuple[str, bool]:
    changed = False
    if not text.endswith("\n"):
        text += "\n"
        changed = True

    for heading, scaffold in REQUIRED_SECTIONS:
        if heading in text:
            continue
        changed = True
        # Prefer to insert before Evidence if present, else append at end.
        anchor = "## Evidence"
        if anchor in text:
            before, after = text.split(anchor, 1)
            insertion = f"{heading}\n\n{scaffold}\n"
            text = before.rstrip("\n") + "\n\n" + insertion + "\n" + anchor + after
        else:
            text = text.rstrip("\n") + f"\n\n{heading}\n\n{scaffold}"

    return text, changed


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)

    ap = argparse.ArgumentParser(description="Backfill tempmemory iterlog sections")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if changes needed",
    )
    args = ap.parse_args()

    paths = sorted(ITERLOG_DIR.glob(GLOB)) if ITERLOG_DIR.exists() else []
    needs_change: list[Path] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        new_text, changed = _ensure_sections(text)
        if changed:
            needs_change.append(p)
            if not args.check:
                p.write_text(new_text, encoding="utf-8")

    if args.check and needs_change:
        for p in needs_change:
            print(p)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
