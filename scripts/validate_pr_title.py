#!/usr/bin/env python3
"""
Fail CI for pull request builds if the PR title is missing or lacks a story ID.

Rationale: Autonomous development relies on strict traceability. We enforce story
IDs at the PR/title layer so that manual PRs can't bypass labeling.

Behavior:
- If not a PR build: exit 0.
- If PR build and title missing/blank: exit 1.
- If PR build and title does not contain a recognized story id: exit 1.
"""

from __future__ import annotations

import os
import re
import sys

STORY_ID_RE = re.compile(r"\b(?:ST|CH|FT|REWARD)-[A-Z0-9]+-\d+(?:-\d+)?\b")


def _is_pr_build(env: dict[str, str]) -> bool:
    for k in ("CI_BUILD_EVENT", "WOODPECKER_BUILD_EVENT", "WOODPECKER_EVENT"):
        v = env.get(k, "").strip().lower()
        if v in {"pull_request", "pull-request", "pr"}:
            return True
    # Woodpecker commonly sets CI_PULL_REQUEST to an integer on PR builds.
    if env.get("CI_PULL_REQUEST", "").strip():
        return True
    return bool(env.get("WOODPECKER_PULL_REQUEST", "").strip())


def _get_pr_title(env: dict[str, str]) -> str:
    for k in (
        "CI_PULL_REQUEST_TITLE",
        "WOODPECKER_PULL_REQUEST_TITLE",
        "WOODPECKER_PR_TITLE",
    ):
        v = env.get(k)
        if v:
            return v.strip()
    return ""


def main() -> int:
    env = dict(os.environ)
    if not _is_pr_build(env):
        print("validate_pr_title: non-PR build; skipping")
        return 0

    title = _get_pr_title(env)
    if not title:
        print(
            "ERROR: PR title is missing in CI environment. "
            "Ensure PR builds expose CI_PULL_REQUEST_TITLE (or use the standard "
            "automerge workflow which prefixes the title with the story id).",
            file=sys.stderr,
        )
        return 1

    if not STORY_ID_RE.search(title):
        print(
            f"ERROR: PR title must contain a story id like ST-NS-001 or CH-FOO-001. "
            f"Got: {title!r}",
            file=sys.stderr,
        )
        return 1

    print(f"validate_pr_title: OK ({title!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
