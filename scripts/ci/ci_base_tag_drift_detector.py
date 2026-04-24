#!/usr/bin/env python3
"""Detect stale CI base image tags in Dockerfile.ci-* files.

Compares the latest chiseai-ci-tools tag from .woodpecker/*.yaml files
against the FROM tags used in infrastructure/docker/Dockerfile.ci-* files.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
WOODPECKER_DIR = REPO_ROOT / ".woodpecker"
DOCKER_DIR = REPO_ROOT / "infrastructure" / "docker"
BASE_IMAGE_RE = re.compile(
    r"^FROM\s+chiseai-ci-tools:py311-(\d{8})(?:\s+AS\s+\S+)?\s*$", re.IGNORECASE
)
TAG_RE = re.compile(r"chiseai-ci-tools:py311-(\d{8})")


def find_latest_ci_tools_tag() -> str | None:
    """Find the latest chiseai-ci-tools tag across all .woodpecker/*.yaml files."""
    latest: str | None = None
    latest_date: str | None = None
    for yaml_file in WOODPECKER_DIR.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        for match in TAG_RE.finditer(content):
            tag = match.group(0)  # e.g. "chiseai-ci-tools:py311-20260423"
            date_part = match.group(1)
            if latest is None or date_part > latest_date:
                latest = tag
                latest_date = date_part
    return latest


def find_stale_dockerfiles(latest_tag: str) -> list[dict]:
    """Find Dockerfile.ci-* files with stale FROM tags."""
    stale = []
    latest_match = TAG_RE.search(latest_tag)
    latest_date = latest_match.group(1) if latest_match else None  # e.g. "20260423"
    for dockerfile in DOCKER_DIR.glob("Dockerfile.ci-*"):
        content = dockerfile.read_text(encoding="utf-8")
        for line in content.splitlines():
            m = BASE_IMAGE_RE.match(line.strip())
            if m:
                from_date = m.group(1)
                from_tag = m.group(0)
                if from_date < latest_date:
                    stale.append(
                        {
                            "file": str(dockerfile.relative_to(REPO_ROOT)),
                            "from_tag": from_tag,
                            "from_date": from_date,
                            "latest_tag": latest_tag,
                            "latest_date": latest_date,
                        }
                    )
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect stale CI base image tags in Dockerfile.ci-* files."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all files checked (not just stale ones).",
    )
    args = parser.parse_args()

    if args.json and args.verbose:
        import json

        print(
            json.dumps(
                {
                    "error": "incompatible flags: --json and --verbose cannot be used together",
                    "exit_code": 2,
                },
                indent=2,
            )
        )
        return 2

    latest_tag = find_latest_ci_tools_tag()
    if latest_tag is None:
        if args.json:
            import json

            print(
                json.dumps(
                    {
                        "error": "No chiseai-ci-tools tag found in .woodpecker/*.yaml files.",
                        "latest_tag": None,
                        "stale": [],
                        "count": 0,
                        "passed": False,
                    },
                    indent=2,
                )
            )
        else:
            print("ERROR: No chiseai-ci-tools tag found in .woodpecker/*.yaml files.")
        return 1

    stale = find_stale_dockerfiles(latest_tag)

    if args.json:
        import json

        output = {
            "latest_tag": latest_tag,
            "stale": stale,
            "count": len(stale),
            "passed": len(stale) == 0,
        }
        print(json.dumps(output, indent=2))
        return 1 if stale else 0
    elif stale:
        print(f"STALE: {len(stale)} Dockerfile(s) using old chiseai-ci-tools tag")
        print(f"Latest tag in .woodpecker: {latest_tag}")
        print()
        for item in stale:
            print(
                f"  - {item['file']}: FROM {item['from_tag']} (expected: {latest_tag})"
            )
        return 1
    else:
        if args.verbose:
            print(f"Latest tag in .woodpecker: {latest_tag}")
        print("OK: All Dockerfile.ci-* files are up to date")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
