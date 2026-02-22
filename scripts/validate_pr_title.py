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
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# Bootstrap environment first (must be before any env access)
bootstrap(load_env=True)

try:
    from scripts.story_id import contains_valid_story_id, extract_story_ids
except ModuleNotFoundError:
    # Allow execution as `python scripts/validate_pr_title.py`.
    from story_id import contains_valid_story_id, extract_story_ids


def _contains_valid_story_id(text: str) -> bool:
    return contains_valid_story_id(text)


def _is_pr_build(env: dict[str, str]) -> bool:
    for k in (
        "CI_BUILD_EVENT",
        "WOODPECKER_BUILD_EVENT",
        "WOODPECKER_EVENT",
        "CI_PIPELINE_EVENT",
    ):
        v = env.get(k, "").strip().lower()
        if v in {"pull_request", "pull-request", "pr"}:
            return True
    # Woodpecker commonly sets CI_PULL_REQUEST to an integer on PR builds.
    if env.get("CI_PULL_REQUEST", "").strip():
        return True
    if env.get("WOODPECKER_PULL_REQUEST", "").strip():
        return True
    # Woodpecker 2.8+ uses CI_COMMIT_PULL_REQUEST for PR number
    if env.get("CI_COMMIT_PULL_REQUEST", "").strip():
        return True
    return False


def _get_pr_title(env: dict[str, str]) -> str:
    # Try direct environment variables first (some CI systems provide these)
    for k in (
        "CI_PULL_REQUEST_TITLE",
        "WOODPECKER_PULL_REQUEST_TITLE",
        "WOODPECKER_PR_TITLE",
        "CI_PIPELINE_TITLE",
        "CI_COMMIT_TITLE",
        "WOODPECKER_COMMIT_TITLE",
        "CI_COMMIT_MESSAGE",
        "WOODPECKER_COMMIT_MESSAGE",
    ):
        v = env.get(k)
        if v:
            return v.strip()

    # Woodpecker 2.8+ doesn't expose PR title directly; fetch from Gitea API
    # Get PR number from any available CI env var
    pr_number = (
        env.get("CI_COMMIT_PULL_REQUEST", "").strip()
        or env.get("CI_PULL_REQUEST", "").strip()
        or env.get("WOODPECKER_PULL_REQUEST", "").strip()
    )
    if pr_number:
        import json
        import urllib.request

        forge_url = env.get("CI_FORGE_URL", "").rstrip("/")
        repo = env.get("CI_REPO", "")
        token = env.get("GITEA_TOKEN", "")

        if forge_url and repo and token:
            api_url = f"{forge_url}/api/v1/repos/{repo}/pulls/{pr_number}"
            req = urllib.request.Request(
                api_url, headers={"Authorization": f"token {token}"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    title = data.get("title", "").strip()
                    if title:
                        return title
            except Exception as e:
                print(f"WARN: Failed to fetch PR title from API: {e}", file=sys.stderr)

    # Fallback: query Woodpecker pipeline metadata for title, if available.
    pipeline_number = env.get("CI_PIPELINE_NUMBER", "").strip()
    woodpecker_token = env.get("WOODPECKER_TOKEN", "").strip()
    if pipeline_number and woodpecker_token:
        import json
        import urllib.request

        base_url = env.get(
            "WOODPECKER_BASE_URL", "http://woodpecker-server:8000"
        ).rstrip("/")
        repo = env.get("CI_REPO", "")
        if "/" in repo:
            owner, repo_name = repo.split("/", 1)
            api_url = (
                f"{base_url}/api/repos/{owner}/{repo_name}/pipelines/{pipeline_number}"
            )
            req = urllib.request.Request(
                api_url, headers={"X-WOODPECKER-TOKEN": woodpecker_token}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    title = str(data.get("title", "")).strip()
                    if title:
                        return title
            except Exception as e:
                print(
                    f"WARN: Failed to fetch pipeline title from Woodpecker API: {e}",
                    file=sys.stderr,
                )

    # Fallback: try to get story ID from branch name
    branch = (
        env.get("CI_COMMIT_BRANCH", "").strip()
        or env.get("WOODPECKER_COMMIT_BRANCH", "").strip()
    )
    if branch:
        branch_ids = extract_story_ids(branch)
        if branch_ids:
            print(
                f"validate_pr_title: Using story ID from branch name: {branch_ids[0]}",
                file=sys.stderr,
            )
            return branch  # Return branch name which contains story ID

    return ""


def main() -> int:
    bootstrap(load_env=True)

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

    if not _contains_valid_story_id(title):
        print(
            "ERROR: PR title must contain a story id like "
            "ST-NS-001, ST-CI-HEALTH-20260215F, CH-CI-103, or PAPER-LOOP-001. "
            f"Got: {title!r}",
            file=sys.stderr,
        )
        return 1

    print(f"validate_pr_title: OK ({title!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
