#!/usr/bin/env python3
"""Create or update a rolling Gitea issue for cron/main CI failures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

ISSUE_MARKER_PREFIX = "<!-- CHISEAI_CRON_CI_FAILURE:"
MAX_BODY = 60000


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _repo_owner_name() -> tuple[str, str]:
    owner = _env("CI_REPO_OWNER")
    repo = _env("CI_REPO_NAME")
    if owner and repo:
        return owner, repo
    ci_repo = _env("CI_REPO")
    if "/" in ci_repo:
        a, b = ci_repo.split("/", 1)
        return a, b
    return "craig", "ChiseAI"


def _forge_url() -> str:
    return (
        _env("CI_FORGE_URL")
        or _env("GITEA_BASE_URL")
        or "http://host.docker.internal:3000"
    ).rstrip("/")


def _api(owner: str, repo: str) -> str:
    return f"{_forge_url()}/api/v1/repos/{owner}/{repo}"


def _collect_summary(pipeline: str) -> str:
    triage = Path("scripts/ci/woodpecker_triage.py")
    if not triage.exists():
        return "root-cause summary unavailable (missing triage script)"
    cmd = [
        sys.executable,
        str(triage),
        "diagnose",
        "--pipeline",
        pipeline,
        "--format",
        "human",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip()
    if out:
        return out
    err = (proc.stderr or "").strip()
    if err:
        return f"root-cause summary unavailable: {err}"
    return "root-cause summary unavailable (no output)"


def _truncate(text: str) -> str:
    if len(text) <= MAX_BODY:
        return text
    return text[: (MAX_BODY - 32)] + "\n\n(truncated)"


def _session() -> requests.Session | None:
    token = _env("GITEA_TOKEN")
    if not token:
        print("post_ci_failure_issue: GITEA_TOKEN not set; skipping", file=sys.stderr)
        return None
    s = requests.Session()
    s.headers.update(
        {"Authorization": f"token {token}", "Content-Type": "application/json"}
    )
    return s


def _find_open_issue_with_marker(
    s: requests.Session, api: str, marker: str
) -> dict | None:
    page = 1
    while True:
        r = s.get(
            f"{api}/issues",
            params={"state": "open", "page": page, "limit": 50},
            timeout=30,
        )
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list) or not items:
            return None
        for it in items:
            if not isinstance(it, dict):
                continue
            body = str(it.get("body", "") or "")
            if marker in body:
                return it
        page += 1


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    pipeline = _env("CI_PIPELINE_NUMBER") or "unknown"
    repo = _env("CI_REPO", "craig/ChiseAI")
    branch = _env("CI_COMMIT_BRANCH") or _env("WOODPECKER_COMMIT_BRANCH")
    if branch != "main":
        print(
            f"post_ci_failure_issue: branch={branch!r}; only main cron failures are tracked"
        )
        return 0

    owner, repo_name = _repo_owner_name()
    api = _api(owner, repo_name)
    marker = f"{ISSUE_MARKER_PREFIX}{branch} -->"
    build_url = _env("CI_BUILD_LINK")
    summary = _collect_summary(pipeline)
    title = f"CI cron failures on {branch} require swarm follow-up"
    body = _truncate(
        f"{marker}\n\n"
        f"Auto-maintained issue for recurring cron CI failures on `{repo}` / `{branch}`.\n\n"
        f"Latest failure pipeline: `{pipeline}`\n"
        f"{('Build URL: ' + build_url + chr(10)) if build_url else ''}"
        "Expected action: run `.opencode/command/chise-ci-root-cause.md`, generate a failure bundle, and push fix PR(s).\n\n"
        f"{summary}"
    )

    s = _session()
    if s is None:
        return 0

    try:
        existing = _find_open_issue_with_marker(s, api, marker)
        if existing:
            issue_num = int(existing["number"])
            s.patch(
                f"{api}/issues/{issue_num}",
                data=json.dumps({"title": title, "body": body}),
                timeout=30,
            ).raise_for_status()
            comment = (
                f"Cron CI failed again on `{branch}`.\n"
                f"Pipeline: `{pipeline}`\n"
                f"{('Build URL: ' + build_url) if build_url else ''}"
            )
            s.post(
                f"{api}/issues/{issue_num}/comments",
                data=json.dumps({"body": comment}),
                timeout=30,
            ).raise_for_status()
            print(f"post_ci_failure_issue: updated issue #{issue_num}")
            return 0

        resp = s.post(
            f"{api}/issues",
            data=json.dumps({"title": title, "body": body}),
            timeout=30,
        )
        resp.raise_for_status()
        issue = resp.json()
        print(f"post_ci_failure_issue: created issue #{issue.get('number')}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"post_ci_failure_issue: failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
