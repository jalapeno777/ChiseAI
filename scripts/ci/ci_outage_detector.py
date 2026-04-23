#!/usr/bin/env python3
"""Detect CI outage conditions via consecutive Woodpecker pipeline failures."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Allow direct script execution from any worktree by exposing repo root + src.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config.bootstrap import bootstrap
except ModuleNotFoundError:
    from src.config.bootstrap import bootstrap

FAILED_STATUSES = {"failure", "failed", "error", "killed", "blocked"}
WINDOW_HOURS = 1
ALERT_THRESHOLD = 3  # >3 consecutive failures
RUNBOOK_POINTER = "docs/runbooks/ci-outage-response.md"
INCIDENT_SIGNAL = "ops-team"


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


def _is_failed_status(status: str) -> bool:
    s = str(status).lower().strip()
    if s in FAILED_STATUSES:
        return True
    if s in {"success", "passing", "passed", "complete", "skipped"}:
        return False
    return s not in {"", "unknown", "running", "pending"}


def _normalize_pipeline(data: dict[str, Any]) -> dict[str, Any]:
    number = data.get("number") or data.get("id") or data.get("build_number")
    status = (
        str(data.get("status") or data.get("state") or data.get("result") or "unknown")
        .strip()
        .lower()
    )
    started = data.get("started") or data.get("started_at") or data.get("start_time")
    created = data.get("created") or data.get("created_at")
    return {
        "number": number,
        "id": data.get("id"),
        "status": status,
        "started_at": started,
        "created": created,
        "event": data.get("event") or data.get("hook_event"),
        "ref": data.get("ref") or data.get("commit") or data.get("branch"),
        "title": data.get("title") or data.get("message") or "",
        "author": data.get("author") or data.get("sender") or "",
        "raw": data,
    }


def _list_pipelines(
    base_url: str, token: str, repo_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"per_page": limit})
    data = _req_json(base_url, token, f"/api/repos/{repo_id}/pipelines?{q}")
    if not isinstance(data, list):
        raise RuntimeError("Unexpected pipelines response")
    return [_normalize_pipeline(item) for item in data if isinstance(item, dict)]


def _consecutive_failures_in_window(
    pipelines: list[dict[str, Any]],
    window_hours: int = WINDOW_HOURS,
    threshold: int = ALERT_THRESHOLD,
) -> tuple[bool, int, list[dict[str, Any]]]:
    """Return (alert_triggered, consecutive_count, failed_pipelines_in_streak)."""
    cutoff = int(time.time()) - (window_hours * 3600)
    consecutive = 0
    streak: list[dict[str, Any]] = []

    for p in pipelines:
        if not isinstance(p, dict):
            continue
        started = int(p.get("started_at") or 0)
        # Skip pipelines outside the time window
        if started > 0 and started < cutoff:
            continue
        if _is_failed_status(p.get("status", "")):
            consecutive += 1
            streak.append(p)
        else:
            # Non-failed status breaks the consecutive streak
            break

    alert = consecutive > threshold
    return alert, consecutive, streak


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CI Outage Early Warning Detector")
    p.add_argument(
        "--base-url",
        default=os.getenv("WOODPECKER_BASE_URL", "http://host.docker.internal:8012"),
    )
    p.add_argument("--token", default=os.getenv("WOODPECKER_TOKEN", ""))
    p.add_argument("--repo", default=os.getenv("CI_REPO", "craig/ChiseAI"))
    p.add_argument("--limit", type=int, default=50)
    p.add_argument(
        "--window-hours",
        type=int,
        default=WINDOW_HOURS,
        help="Time window in hours to look back for consecutive failures",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=ALERT_THRESHOLD,
        help="Number of consecutive failures that triggers alert (default: >3)",
    )
    return p


def main() -> int:
    bootstrap(load_env=True)
    args = build_parser().parse_args()
    token = args.token.strip()
    if not token:
        print(
            json.dumps(
                {
                    "alert": False,
                    "consecutive_failures": 0,
                    "window_hours": args.window_hours,
                    "runbook_pointer": RUNBOOK_POINTER,
                    "incident_signal": INCIDENT_SIGNAL,
                    "detected_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "pipelines": [],
                    "error": "WOODPECKER_TOKEN missing; skipping",
                }
            )
        )
        return 0

    try:
        repo_id = _repo_id(args.base_url, token, args.repo)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "alert": False,
                    "consecutive_failures": 0,
                    "window_hours": args.window_hours,
                    "runbook_pointer": RUNBOOK_POINTER,
                    "incident_signal": INCIDENT_SIGNAL,
                    "detected_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "pipelines": [],
                    "error": f"Failed to resolve repo: {exc}",
                }
            )
        )
        return 0

    try:
        pipelines = _list_pipelines(args.base_url, token, repo_id, args.limit)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "alert": False,
                    "consecutive_failures": 0,
                    "window_hours": args.window_hours,
                    "runbook_pointer": RUNBOOK_POINTER,
                    "incident_signal": INCIDENT_SIGNAL,
                    "detected_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "pipelines": [],
                    "error": f"Failed to list pipelines: {exc}",
                }
            )
        )
        return 0

    alert, consecutive, streak = _consecutive_failures_in_window(
        pipelines, window_hours=args.window_hours, threshold=args.threshold
    )

    streak_data = []
    for p in streak:
        started_at = p.get("started_at")
        if started_at:
            try:
                ts = (
                    datetime.fromtimestamp(int(started_at), tz=UTC)
                    .replace(microsecond=0)
                    .isoformat()
                )
            except (ValueError, OSError):
                ts = str(started_at)
        else:
            ts = None
        streak_data.append(
            {
                "number": p.get("number"),
                "status": p.get("status"),
                "started_at": ts,
            }
        )

    result = {
        "alert": alert,
        "consecutive_failures": consecutive,
        "window_hours": args.window_hours,
        "runbook_pointer": RUNBOOK_POINTER,
        "incident_signal": INCIDENT_SIGNAL,
        "detected_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "pipelines": streak_data,
    }

    print(json.dumps(result, indent=2))
    return 1 if alert else 0


if __name__ == "__main__":
    raise SystemExit(main())
