#!/usr/bin/env python3
"""Validate CI swarm context invariants.

Phase 1 checks:
- Branch/ref context must look sane for push/PR events.
- Non-main push branches must use feature/* or safety/*.
- Canonical status file edits are reported in logs, but no longer hard-fail CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

CANONICAL_FILES = {
    "docs/bmm-workflow-status.yaml",
    "docs/validation/validation-registry.yaml",
}


def _event(env: dict[str, str]) -> str:
    for key in ("CI_BUILD_EVENT", "WOODPECKER_BUILD_EVENT", "WOODPECKER_EVENT"):
        value = env.get(key, "").strip().lower()
        if value:
            return value
    return ""


def _is_pr(env: dict[str, str]) -> bool:
    event = _event(env)
    if event in {"pull_request", "pull-request", "pr"}:
        return True
    commit_ref = _first_non_empty(env, ("CI_COMMIT_REF", "WOODPECKER_COMMIT_REF"))
    if commit_ref.startswith("refs/pull/"):
        return True
    return bool(
        env.get("CI_PULL_REQUEST", "").strip()
        or env.get("WOODPECKER_PULL_REQUEST", "").strip()
    )


def _first_non_empty(env: dict[str, str], keys: Iterable[str]) -> str:
    for key in keys:
        val = env.get(key, "").strip()
        if val:
            return val
    return ""


def _git_stdout(*cmd: str) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            f"{' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def _changed_files_head() -> set[str]:
    out = _git_stdout("git", "show", "--pretty=", "--name-only", "HEAD")
    return {line.strip() for line in out.splitlines() if line.strip()}


def _changed_files_working_tree() -> set[str]:
    staged = _git_stdout("git", "diff", "--name-only", "--cached")
    unstaged = _git_stdout("git", "diff", "--name-only")
    files: set[str] = set()
    files.update(line.strip() for line in staged.splitlines() if line.strip())
    files.update(line.strip() for line in unstaged.splitlines() if line.strip())
    return files


def _changed_files_ci_pr(env: dict[str, str]) -> set[str]:
    """Return changed files for a PR build using merge-base diff when possible."""
    target = _first_non_empty(
        env,
        (
            "CI_COMMIT_TARGET_BRANCH",
            "WOODPECKER_PULL_REQUEST_TARGET_BRANCH",
            "CI_PULL_REQUEST_TARGET_BRANCH",
        ),
    )
    if not target:
        target = "main"

    candidates = (
        f"origin/{target}",
        f"gitea/{target}",
        target,
    )
    for base in candidates:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return {line.strip() for line in proc.stdout.splitlines() if line.strip()}

    # Fallback to HEAD-only behavior when merge-base diff is unavailable.
    return _changed_files_head()


def _is_allowed_work_branch(branch: str) -> bool:
    return bool(re.match(r"^(feature|safety|consolidation)/", branch))


def main() -> int:
    bootstrap(load_env=True)
    env = dict(os.environ)
    ev = _event(env)
    pr_build = _is_pr(env)
    ci_mode = bool(
        env.get("CI", "").strip()
        or ev
        or env.get("CI_COMMIT_SHA", "").strip()
        or env.get("CI_COMMIT_REF", "").strip()
        or env.get("WOODPECKER_REPO", "").strip()
    )

    commit_ref = _first_non_empty(
        env,
        (
            "CI_COMMIT_REF",
            "WOODPECKER_COMMIT_REF",
        ),
    )
    branch = _first_non_empty(
        env,
        (
            "CI_COMMIT_SOURCE_BRANCH",
            "WOODPECKER_PULL_REQUEST_SOURCE_BRANCH",
            "CI_PULL_REQUEST_SOURCE_BRANCH",
            "CI_COMMIT_BRANCH",
            "WOODPECKER_COMMIT_BRANCH",
        ),
    )
    if not branch:
        branch = _git_stdout("git", "rev-parse", "--abbrev-ref", "HEAD")

    errors: list[str] = []

    if ci_mode:
        if pr_build:
            if commit_ref and not (
                commit_ref.startswith("refs/pull/")
                or commit_ref.startswith("refs/heads/")
                or (branch and commit_ref == branch)
            ):
                errors.append(
                    "PR build expected CI_COMMIT_REF to be a PR or branch ref "
                    f"(or source branch name), got {commit_ref!r}"
                )
        elif (
            ev in {"push", "manual", ""}
            and commit_ref
            and not (
                commit_ref.startswith("refs/heads/")
                or (branch and commit_ref == branch)
            )
        ):
            errors.append(
                "Push/manual build expected refs/heads/* or branch name, "
                f"got {commit_ref!r}"
            )

    if branch and branch != "main" and not _is_allowed_work_branch(branch):
        errors.append(
            "Non-main branch must follow feature/*, safety/*, or "
            f"consolidation/* naming. Got {branch!r}"
        )

    if ci_mode and pr_build:
        changed = _changed_files_ci_pr(env)
    elif ci_mode:
        changed = _changed_files_head()
    else:
        changed = _changed_files_working_tree()
    touches_canonical = bool(changed.intersection(CANONICAL_FILES))

    print(
        "validate_swarm_context: "
        f"event={ev or '<unknown>'} "
        f"pr={str(pr_build).lower()} "
        f"branch={branch or '<unknown>'} "
        f"ref={commit_ref or '<unknown>'} "
        f"canonical_changed={str(touches_canonical).lower()}"
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("validate_swarm_context: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
