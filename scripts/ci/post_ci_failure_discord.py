#!/usr/bin/env python3
"""Post cron CI failure summary to Discord for swarm handoff."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap


def _pipeline_number(env: dict[str, str]) -> str:
    return env.get("CI_PIPELINE_NUMBER", "").strip() or "unknown"


def _collect_summary(env: dict[str, str]) -> str:
    triage = Path("scripts/ci/woodpecker_triage.py")
    if not triage.exists():
        return (
            "root-cause summary unavailable (missing scripts/ci/woodpecker_triage.py)"
        )

    args = [
        sys.executable,
        str(triage),
        "diagnose",
        "--pipeline",
        _pipeline_number(env),
        "--format",
        "human",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip()
    if out:
        return out
    err = (proc.stderr or "").strip()
    if err:
        return f"root-cause summary unavailable: {err}"
    return "root-cause summary unavailable (no output)"


def _post_discord(webhook_url: str, content: str) -> None:
    payload = {"content": content[:1900]}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15):
        return


def main() -> int:
    bootstrap(load_env=True)
    env = dict(os.environ)
    webhook = env.get("DISCORD_DEV_WEBHOOK_URL", "").strip()
    if not webhook:
        print(
            "post_ci_failure_discord: DISCORD_DEV_WEBHOOK_URL not set; skipping",
            file=sys.stderr,
        )
        return 0

    pipeline = _pipeline_number(env)
    repo = env.get("CI_REPO", "craig/ChiseAI")
    branch = env.get("CI_COMMIT_BRANCH", "") or env.get("WOODPECKER_COMMIT_BRANCH", "")
    build_url = env.get("CI_BUILD_LINK", "").strip()
    summary = _collect_summary(env)

    body = (
        f"CI cron failure detected for `{repo}` on branch `{branch}`.\n"
        f"Pipeline: `{pipeline}`\n"
        f"{('Build URL: ' + build_url + chr(10)) if build_url else ''}"
        "Action requested: run `.opencode/command/chise-ci-root-cause.md` "
        f"for pipeline `{pipeline}` and apply fixes.\n\n"
        f"{summary}"
    )

    try:
        _post_discord(webhook, body)
        print("post_ci_failure_discord: notification sent")
    except Exception as exc:  # noqa: BLE001
        print(
            f"post_ci_failure_discord: failed to send notification: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
