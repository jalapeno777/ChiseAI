#!/usr/bin/env python3
"""Fail-fast guard for story session context.

This script enforces that command execution is bound to the expected
worktree/session/branch tuple before running tests, lint, or git actions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _git_branch(cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Unable to determine git branch")
    return proc.stdout.strip()


def _is_subpath(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert swarm session context")
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--worktree-path", required=True)
    parser.add_argument(
        "--cwd",
        default=".",
        help="Directory to validate; defaults to current working directory.",
    )
    args = parser.parse_args()

    expected_worktree = Path(args.worktree_path).resolve()
    actual_cwd = Path(args.cwd).resolve()
    session_path = expected_worktree / ".swarm-session.json"

    if not expected_worktree.exists():
        print(
            f"ERROR: worktree path does not exist: {expected_worktree}",
            file=sys.stderr,
        )
        return 2

    if not session_path.exists():
        print(
            f"ERROR: missing session file: {session_path}",
            file=sys.stderr,
        )
        return 2

    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid session json: {exc}", file=sys.stderr)
        return 2

    session_story = str(session.get("story_id", "")).strip()
    session_branch = str(session.get("branch", "")).strip()
    session_worktree = Path(str(session.get("worktree_path", "")).strip()).resolve()

    if session_story != args.story_id:
        print(
            f"ERROR: story mismatch: session={session_story!r} expected={args.story_id!r}",
            file=sys.stderr,
        )
        return 2

    if session_branch != args.branch:
        print(
            f"ERROR: session branch mismatch: session={session_branch!r} expected={args.branch!r}",
            file=sys.stderr,
        )
        return 2

    if session_worktree != expected_worktree:
        print(
            "ERROR: session worktree mismatch: "
            f"session={session_worktree} expected={expected_worktree}",
            file=sys.stderr,
        )
        return 2

    if not _is_subpath(actual_cwd, expected_worktree):
        print(
            f"ERROR: cwd {actual_cwd} is not inside worktree {expected_worktree}",
            file=sys.stderr,
        )
        return 2

    actual_branch = _git_branch(actual_cwd)
    if actual_branch != args.branch:
        print(
            f"ERROR: current branch mismatch: current={actual_branch!r} expected={args.branch!r}",
            file=sys.stderr,
        )
        return 2

    print("assert_session_context: OK")
    print(f"- story: {args.story_id}")
    print(f"- branch: {args.branch}")
    print(f"- worktree: {expected_worktree}")
    print(f"- cwd: {actual_cwd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
