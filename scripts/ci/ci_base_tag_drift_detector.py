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
BASE_IMAGE_RE = re.compile(r"^FROM\s+chiseai-ci-tools:py311-(\d{8})\s*$")
TAG_RE = re.compile(r"chiseai-ci-tools:py311-(\d{8})")


def find_latest_ci_tools_tag() -> str | None:
    """Find the latest chiseai-ci-tools tag across all .woodpecker/*.yaml files."""
    latest: str | None = None
    for yaml_file in WOODPECKER_DIR.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        for match in TAG_RE.finditer(content):
            tag = match.group(0)  # e.g. "chiseai-ci-tools:py311-20260423"
            date_part = match.group(1)
            # latest_tag format: chiseai-ci-tools:py311-YYYYMMDD (31 chars total)
            # date part at index 23-31 gives YYYYMMDD (8 chars)
            latest_date = latest[23:31] if latest else None
            if latest is None or date_part > latest_date:
                latest = tag
    return latest


def find_stale_dockerfiles(latest_tag: str) -> list[dict]:
    """Find Dockerfile.ci-* files with stale FROM tags."""
    stale = []
    latest_date = latest_tag[23:31]  # e.g. "20260423"
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

    latest_tag = find_latest_ci_tools_tag()
    if latest_tag is None:
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
