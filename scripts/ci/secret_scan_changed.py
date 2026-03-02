#!/usr/bin/env python3
"""Lightweight secret scanner for changed files only."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "discord_webhook",
        re.compile(r"https://(?:discord(?:app)?\.com)/api/webhooks/[\w\-]+/[\w\-]+"),
    ),
    (
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_\-]+"),
    ),
    (
        "generic_credential_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"][^'\"]{16,}['\"]"
        ),
    ),
]

ALLOW_MARKERS = ("# nosec", "allow-secret", "example", "dummy", "sample")


def _changed_files() -> list[Path]:
    env_files = __import__("os").environ.get("CI_PIPELINE_FILES", "").strip()
    files: list[str] = []
    if env_files:
        try:
            parsed = json.loads(env_files)
            if isinstance(parsed, list):
                files = [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass

    if not files:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    result: list[Path] = []
    for f in files:
        p = Path(f)
        if p.exists() and p.is_file():
            result.append(p)
    return result


def main() -> int:
    hits: list[str] = []
    for path in _changed_files():
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            low = line.lower()
            if any(marker in low for marker in ALLOW_MARKERS):
                continue
            for name, pattern in PATTERNS:
                if pattern.search(line):
                    hits.append(f"{path}:{i}: {name}")

    if not hits:
        print("secret-scan: OK (no suspicious secrets in changed files)")
        return 0

    print("secret-scan: FAIL", file=sys.stderr)
    for hit in hits[:100]:
        print(f"  - {hit}", file=sys.stderr)
    if len(hits) > 100:
        print(f"  ... and {len(hits)-100} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
