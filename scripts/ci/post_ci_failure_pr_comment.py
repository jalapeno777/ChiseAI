#!/usr/bin/env python3
"""Post or update a single CI failure comment on a Gitea PR.

This is intended to give the agent swarm a stable, visible surface for CI logs.

Required env vars (Woodpecker/Drone-compatible):
- CI_FORGE_URL
- CI_REPO_OWNER
- CI_REPO_NAME
- CI_COMMIT_PULL_REQUEST (PR number)
- CI_PIPELINE_URL
- CI_PIPELINE_NUMBER
- GITEA_TOKEN (recommended injected from a Woodpecker secret)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal, cast, overload

import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

COMMENT_MARKER = "<!-- CHISEAI_CI_FAILURE -->"
MAX_COMMENT_LENGTH = 20000  # Gitea limit


@overload
def _getenv(name: str, required: Literal[True] = True) -> str: ...


@overload
def _getenv(name: str, required: Literal[False]) -> str | None: ...


def _getenv(name: str, required: bool = True) -> str | None:
    v = os.environ.get(name)
    if required and not v:
        print(f"Missing required env var: {name}", file=sys.stderr)
        raise SystemExit(2)
    return v


def _api_base(forge_url: str, owner: str, repo: str) -> str:
    return f"{forge_url.rstrip('/')}/api/v1/repos/{owner}/{repo}"


def _list_comments(api_base: str, pr_number: str, token: str) -> list[dict[str, Any]]:
    url = f"{api_base}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        return cast(list[dict[str, Any]], data)
    except requests.RequestException as e:
        print(f"Warning: list comments failed: {e}", file=sys.stderr)
        return []


def _find_marker(comments: list[dict[str, Any]], marker: str) -> int | None:
    for c in comments:
        if marker in (c.get("body", "") or ""):
            comment_id = c.get("id")
            return comment_id if isinstance(comment_id, int) else None
    return None


def _update_comment(api_base: str, comment_id: int, body: str, token: str) -> bool:
    url = f"{api_base}/issues/comments/{comment_id}"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    try:
        r = requests.patch(url, headers=headers, json={"body": body}, timeout=30)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Warning: update comment failed: {e}", file=sys.stderr)
        return False


def _create_comment(api_base: str, pr_number: str, body: str, token: str) -> bool:
    url = f"{api_base}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={"body": body}, timeout=30)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Warning: create comment failed: {e}", file=sys.stderr)
        return False


def _failure_summary() -> str:
    triage_path = os.path.join(os.path.dirname(__file__), "woodpecker_triage.py")
    scan_path = os.path.join(os.path.dirname(__file__), "scan_failure_logs.py")
    pr_number = os.environ.get("CI_COMMIT_PULL_REQUEST", "").strip()
    pipeline = os.environ.get("CI_PIPELINE_NUMBER", "").strip()

    triage_cmd = [
        sys.executable,
        triage_path,
        "diagnose",
        "--write-artifacts",
        "--format",
        "human",
    ]
    if pr_number:
        triage_cmd.extend(["--pr", pr_number])
    elif pipeline:
        triage_cmd.extend(["--pipeline", pipeline])
    else:
        triage_cmd.extend(["--from-local-dir", "_bmad-output/ci"])

    try:
        triage = subprocess.run(
            triage_cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if triage.stdout.strip():
            return triage.stdout.strip()
    except Exception:  # noqa: BLE001
        pass

    try:
        scan = subprocess.run(
            [sys.executable, scan_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Always return stdout (even if scan returns non-zero).
        return (scan.stdout or "").strip()
    except Exception as e:  # noqa: BLE001
        return f"Failed to generate failure summary: {e}"


def _truncate(body: str, marker: str) -> str:
    if len(body) <= MAX_COMMENT_LENGTH:
        return body
    reserve = len(marker) + 200
    keep = max(0, MAX_COMMENT_LENGTH - reserve)
    truncated = body[:keep]
    # Avoid leaving an unterminated code fence near the end.
    last_fence = truncated.rfind("```")
    if last_fence > keep - 10:
        truncated = truncated[:last_fence]
    return f"{truncated}\n\n(truncated)\n\n{marker}"


def _build_body(
    marker: str, summary: str, pipeline_url: str, pipeline_number: str
) -> str:
    parts: list[str] = []
    parts.append(marker)
    parts.append("")
    parts.append(f"CI Failure - Build #{pipeline_number}")
    parts.append("")
    parts.append(summary or "_No failure summary available._")
    parts.append("")
    parts.append("---")
    parts.append(f"Pipeline: {pipeline_url}")
    parts.append("")
    parts.append("Local reproduction:")
    parts.append("```bash")
    parts.append("bash scripts/local-ci-checks.sh")
    parts.append("```")
    return _truncate("\n".join(parts), marker)


def main() -> int:
    bootstrap(load_env=True)
    forge_url = _getenv("CI_FORGE_URL")
    owner = _getenv("CI_REPO_OWNER")
    repo = _getenv("CI_REPO_NAME")
    pr_number = _getenv("CI_COMMIT_PULL_REQUEST")
    pipeline_url = _getenv("CI_PIPELINE_URL")
    pipeline_number = _getenv("CI_PIPELINE_NUMBER")
    token = _getenv("GITEA_TOKEN")

    api_base = _api_base(forge_url, owner, repo)
    summary = _failure_summary()
    body = _build_body(COMMENT_MARKER, summary, pipeline_url, pipeline_number)

    comments = _list_comments(api_base, pr_number, token)
    existing_id = _find_marker(comments, COMMENT_MARKER)

    ok = False
    if existing_id:
        ok = _update_comment(api_base, int(existing_id), body, token)
    if not ok:
        ok = _create_comment(api_base, pr_number, body, token)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
