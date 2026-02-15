#!/usr/bin/env python3
"""Classify CI change scope for non-intrusive gating decisions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DOC_ONLY_PREFIXES = (
    "docs/",
    ".opencode/",
    "_bmad-output/",
)
DOC_ONLY_FILES = {
    "AGENTS.md",
    "README.md",
}


def _run_git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def _resolve_base_ref(explicit: str | None) -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(
        [
            "refs/remotes/gitea/main",
            "gitea/main",
            "refs/remotes/origin/main",
            "origin/main",
            "main",
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        rc, _ = _run_git("rev-parse", "--verify", candidate)
        if rc == 0:
            return candidate
    raise RuntimeError("Unable to resolve base ref for change-scope detection")


def changed_files(base_ref: str | None) -> list[str]:
    base = _resolve_base_ref(base_ref)
    rc, merge_base = _run_git("merge-base", "HEAD", base)
    diff_base = merge_base if rc == 0 and merge_base else base
    rc, out = _run_git("diff", "--name-only", f"{diff_base}...HEAD")
    if rc != 0:
        raise RuntimeError("Failed to compute changed files")
    files = [line.strip() for line in out.splitlines() if line.strip()]
    if files:
        return files
    rc, out = _run_git("diff", "--name-only", "HEAD~1..HEAD")
    if rc == 0:
        return [line.strip() for line in out.splitlines() if line.strip()]
    return []


def is_docs_only(paths: list[str]) -> bool:
    if not paths:
        return False
    for path in paths:
        if path in DOC_ONLY_FILES:
            continue
        if path.endswith(".md") and "/" not in path:
            continue
        if path.startswith(DOC_ONLY_PREFIXES):
            continue
        return False
    return True


def changed_python(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".py") and Path(p).exists()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CI change scope helper")
    p.add_argument("--base-ref", default=None)
    p.add_argument(
        "--mode",
        choices=("summary", "docs-only", "changed-python"),
        default="summary",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    paths = changed_files(args.base_ref)
    docs_only = is_docs_only(paths)
    py_files = changed_python(paths)

    if args.mode == "summary":
        print(
            json.dumps(
                {
                    "changed_files": paths,
                    "docs_only": docs_only,
                    "changed_python": py_files,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.mode == "docs-only":
        print("true" if docs_only else "false")
        return 0 if docs_only else 1

    for path in py_files:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
