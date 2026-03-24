#!/usr/bin/env python3
"""Validate Opencode skill markdown structure.

Checks frontmatter presence and required section headers.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REQUIRED_SECTIONS = [
    "## Goal",
    "## When To Use",
    "## When Not To Use",
    "## Exit Conditions",
    "## Troubleshooting/Safety",
    "## Related Skills",
    "## Related Commands",
]


def validate_skill(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Missing file: {path}"]

    text = path.read_text(encoding="utf-8", errors="replace")

    # Basic frontmatter check
    if not text.startswith("---\n"):
        errors.append("Missing YAML frontmatter start marker '---'")
    else:
        parts = text.split("\n---\n", 1)
        if len(parts) < 2:
            errors.append("Missing YAML frontmatter end marker '---'")
        else:
            frontmatter = parts[0]
            for required_field in ["name:", "description:", "metadata:"]:
                if required_field not in frontmatter:
                    errors.append(
                        f"Frontmatter missing required field: {required_field}"
                    )

    # Required sections
    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"Missing required section: {section}")

    # Basic metadata date format check
    if "metadata:" in text:
        date_match = re.search(r"last_updated:\s*\"?(\d{4}-\d{2}-\d{2})\"?", text)
        if not date_match:
            errors.append("metadata.last_updated missing or not in YYYY-MM-DD format")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SKILL.md structure")
    parser.add_argument("skill_file", type=Path, help="Path to SKILL.md")
    args = parser.parse_args()

    errors = validate_skill(args.skill_file)
    if errors:
        print(f"FAIL: {args.skill_file}")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"PASS: {args.skill_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
