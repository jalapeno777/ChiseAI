#!/usr/bin/env python3
"""Enforce changed-lines coverage threshold for src/*.py files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _changed_line_map() -> dict[str, set[int]]:
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--unified=0",
            "origin/main...HEAD",
            "--",
            "src/**/*.py",
            "src/*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # Fallback when glob expansion differs across environments
    if not proc.stdout:
        proc = subprocess.run(
            ["git", "diff", "--unified=0", "origin/main...HEAD", "--", "src"],
            capture_output=True,
            text=True,
            check=False,
        )

    line_map: dict[str, set[int]] = {}
    current: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            if not current.endswith(".py") or not current.startswith("src/"):
                current = None
            continue
        if current is None:
            continue
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            continue
        start = int(m.group(1))
        length = int(m.group(2) or "1")
        if length <= 0:
            continue
        line_map.setdefault(current, set()).update(range(start, start + length))
    return line_map


def _load_coverage(path: Path) -> dict[str, dict[str, list[int]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    out: dict[str, dict[str, list[int]]] = {}
    for raw_name, record in files.items():
        rel = str(Path(raw_name)).replace("\\", "/")
        if "/src/" in rel:
            rel = rel[rel.index("src/") :]
        out[rel] = {
            "executed": record.get("executed_lines", []) or [],
            "missing": record.get("missing_lines", []) or [],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", default="_bmad-output/ci/coverage.json")
    parser.add_argument("--threshold", type=float, default=80.0)
    args = parser.parse_args()

    changed = _changed_line_map()
    if not changed:
        print("changed-lines-coverage: no src/*.py line changes; skipping")
        return 0

    cov_path = Path(args.coverage_json)
    if not cov_path.exists():
        print(
            f"changed-lines-coverage: FAIL (coverage file missing: {cov_path})",
            file=sys.stderr,
        )
        return 1

    coverage = _load_coverage(cov_path)

    total_exec = 0
    total_covered = 0
    missing_files: list[str] = []

    for file, lines in sorted(changed.items()):
        rec = coverage.get(file)
        if rec is None:
            missing_files.append(file)
            continue
        executed = set(rec["executed"])
        missing = set(rec["missing"])
        measurable = executed | missing
        changed_exec = lines & measurable
        if not changed_exec:
            continue
        covered = changed_exec - missing
        total_exec += len(changed_exec)
        total_covered += len(covered)

    if missing_files:
        print("changed-lines-coverage: files changed without coverage records:")
        for f in missing_files:
            print(f"  - {f}")

    if total_exec == 0:
        print("changed-lines-coverage: no executable changed lines detected; skipping")
        return 0

    pct = (total_covered / total_exec) * 100.0
    print(
        f"changed-lines-coverage: covered {total_covered}/{total_exec} "
        f"({pct:.2f}%), threshold={args.threshold:.2f}%"
    )
    if pct + 1e-9 < args.threshold:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
