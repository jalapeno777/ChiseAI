#!/usr/bin/env python3
"""Detect likely-stuck Woodpecker pipelines and emit actionable diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Add src to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap


def _req_json(base_url: str, token: str, path: str) -> object:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {path}: {body}") from exc


def _repo_id(base_url: str, token: str, full_repo: str) -> int:
    q = urllib.parse.urlencode({"per_page": "200"})
    repos = _req_json(base_url, token, f"/api/user/repos?{q}")
    if not isinstance(repos, list):
        raise RuntimeError("Unexpected /api/user/repos response")
    for repo in repos:
        if isinstance(repo, dict) and repo.get("full_name") == full_repo:
            return int(repo["id"])
    raise RuntimeError(f"Repo not found in Woodpecker user repos: {full_repo}")


def _pipeline_stuck(pipeline: dict, now: int, max_running_seconds: int) -> bool:
    status = str(pipeline.get("status", "")).lower()
    if status not in {"running", "pending"}:
        return False
    started = int(pipeline.get("started") or 0)
    if started <= 0:
        return False
    if (now - started) < max_running_seconds:
        return False

    steps = pipeline.get("steps")
    if not isinstance(steps, list) or not steps:
        return True
    active = {
        str(step.get("status", "")).lower() for step in steps if isinstance(step, dict)
    }
    # If pipeline is running/pending but no step is active, it is likely stuck.
    return "running" not in active and "pending" not in active


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Woodpecker stuck pipeline watchdog")
    p.add_argument(
        "--base-url",
        default=os.getenv("WOODPECKER_BASE_URL", "http://host.docker.internal:8012"),
    )
    p.add_argument("--token", default=os.getenv("WOODPECKER_TOKEN", ""))
    p.add_argument("--repo", default=os.getenv("CI_REPO", "craig/ChiseAI"))
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--max-running-seconds", type=int, default=1800)
    p.add_argument("--fail-on-stuck", action="store_true")
    return p


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
    args = build_parser().parse_args()
    token = args.token.strip()
    if not token:
        print("watchdog: WOODPECKER_TOKEN missing; skipping")
        return 0

    repo_id = _repo_id(args.base_url, token, args.repo)
    q = urllib.parse.urlencode({"per_page": str(args.limit)})
    raw = _req_json(args.base_url, token, f"/api/repos/{repo_id}/pipelines?{q}")
    if not isinstance(raw, list):
        print("watchdog: unexpected pipelines payload; skipping")
        return 0

    now = int(time.time())
    stuck_numbers: list[int] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        number = int(item.get("number") or 0)
        detail = _req_json(
            args.base_url, token, f"/api/repos/{repo_id}/pipelines/{number}"
        )
        if isinstance(detail, dict) and _pipeline_stuck(
            detail, now=now, max_running_seconds=args.max_running_seconds
        ):
            stuck_numbers.append(number)

    if not stuck_numbers:
        print("watchdog: OK (no likely-stuck pipelines detected)")
        return 0

    print(
        "watchdog: detected likely-stuck pipelines:",
        ", ".join(str(n) for n in stuck_numbers),
    )
    if args.fail_on_stuck:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
