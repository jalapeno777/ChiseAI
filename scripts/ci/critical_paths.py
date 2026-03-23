#!/usr/bin/env python3
"""Critical paths definition and checker for CI decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Critical test path patterns - tests in these directories are always run
CRITICAL_PATH_PATTERNS = [
    "tests/test_execution/",
    "tests/test_ml/",
    "tests/test_risk/",
    "tests/test_venue_enforcement/",
    "tests/test_kill_switch/",
    "tests/test_reconciliation/",
    "tests/test_paper/",
]


def list_critical_paths():
    """Print current critical paths."""
    print("Critical Path Patterns:")
    for pattern in CRITICAL_PATH_PATTERNS:
        print(f"  - {pattern}")
    return 0


def check_changed_files(changed_files: list[str]) -> int:
    """Check if any changed files match critical paths.

    Returns:
        0 if no critical paths matched
        1 if critical paths were matched
    """
    matched = []
    for file_path in changed_files:
        for pattern in CRITICAL_PATH_PATTERNS:
            if pattern.replace("tests/", "") in file_path or pattern in file_path:
                matched.append(file_path)
                break

    if matched:
        print(f"Critical paths matched ({len(matched)} files):")
        for f in matched:
            print(f"  - {f}")
        return 1

    print("No critical paths matched")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Critical paths checker")
    parser.add_argument("--list", action="store_true", help="List all critical paths")
    parser.add_argument(
        "--check", nargs="+", help="Check if changed files match critical paths"
    )
    args = parser.parse_args()

    if args.list:
        return list_critical_paths()
    elif args.check:
        return check_changed_files(args.check)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
