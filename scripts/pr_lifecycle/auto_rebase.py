#!/usr/bin/env python3
"""Auto Rebase CLI - Entry point for PR auto-rebase operations.

This module provides the main CLI for detecting stale PRs and automatically
rebasing them onto main to maintain mergeability.

Usage:
    python3 scripts/pr_lifecycle/auto_rebase.py detect-and-rebase
    python3 scripts/pr_lifecycle/auto_rebase.py check-branch --branch feature/xyz
    python3 scripts/pr_lifecycle/auto_rebase.py status --pr-number 123
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Import PR lifecycle modules
from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine
from scripts.pr_lifecycle.stale_detector import GiteaAPI, StaleDetector

# Configuration
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
    "/"
)
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_OWNER = os.getenv("GITEA_OWNER", "craig")
GITEA_REPO = os.getenv("GITEA_REPO", "ChiseAI")

# Rate limiting
MAX_REBASES_PER_WINDOW = int(os.getenv("CHISE_PR_MAX_REBASES_PER_WINDOW", "3"))
REBASE_WINDOW_SEC = int(os.getenv("CHISE_PR_REBASE_WINDOW_SEC", "300"))

REBASE_BUDGET_KEY = "bmad:chiseai:pr:rebase:budget"


def _utc_now() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redis_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a redis-cli command."""
    host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
    port = int(os.getenv("CHISE_REDIS_PORT", "6380"))
    db = int(os.getenv("CHISE_REDIS_DB", "0"))

    return subprocess.run(  # nosec B607
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def get_rate_limit_status() -> dict[str, Any]:
    """Get current rate limit status.

    Returns:
        Dict with remaining budget and window info.
    """
    budget_key = f"{REBASE_BUDGET_KEY}:{int(time.time() // REBASE_WINDOW_SEC)}"
    result = _redis_cli("GET", budget_key)

    current_count = 0
    if result.returncode == 0 and result.stdout.strip():
        try:
            current_count = int(result.stdout.strip())
        except ValueError:
            current_count = 0

    remaining = max(0, MAX_REBASES_PER_WINDOW - current_count)
    window_start = int(time.time() // REBASE_WINDOW_SEC) * REBASE_WINDOW_SEC
    window_end = window_start + REBASE_WINDOW_SEC

    return {
        "remaining": remaining,
        "used": current_count,
        "max": MAX_REBASES_PER_WINDOW,
        "window_start_utc": datetime.utcfromtimestamp(window_start).isoformat() + "Z",
        "window_end_utc": datetime.utcfromtimestamp(window_end).isoformat() + "Z",
    }


def detect_and_rebase(
    dry_run: bool = False, discord_alerts: bool = False
) -> dict[str, Any]:
    """Detect stale PRs and attempt to rebase them.

    Args:
        dry_run: If True, only detect without rebasing.
        discord_alerts: If True, send Discord alerts for stale PRs.

    Returns:
        Dict with results summary.
    """
    stale_detector = StaleDetector()
    gitea = GiteaAPI(GITEA_BASE_URL, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO)
    rebase_engine = AutoRebaseEngine()

    # Get rate limit status
    rate_status = get_rate_limit_status()

    results: dict[str, Any] = {
        "timestamp": _utc_now(),
        "dry_run": dry_run,
        "rate_limit": rate_status,
        "stale_prs_detected": 0,
        "rebase_attempts": 0,
        "rebase_successes": 0,
        "rebase_failures": 0,
        "skipped": [],
        "rebased": [],
        "failures": [],
    }

    # List open PRs from Gitea
    open_prs = gitea.list_open_prs()
    print(f"Checking {len(open_prs)} open PRs for staleness...")

    stale_prs = []

    for pr in open_prs:
        pr_number = pr.get("number")
        if not pr_number:
            continue

        branch = pr.get("head", {}).get("ref", "")
        is_draft = pr.get("draft", False)

        # Skip non-feature branches
        if not stale_detector.check_branch_is_feature(branch):
            continue

        # Check if behind main
        is_behind, commits_behind = stale_detector.is_behind_main(branch)

        if is_behind:
            stale_prs.append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "commits_behind": commits_behind,
                    "is_draft": is_draft,
                    "mergeable": pr.get("mergeable"),
                }
            )

            # Track in Redis
            stale_detector.track_stale_pr(pr_number, is_behind, commits_behind)

            # Discord alert if requested
            if discord_alerts:
                stale_detector.alert_discord_stale_pr(pr_number, branch, commits_behind)

            print(
                f"  Stale PR #{pr_number}: {branch} ({commits_behind} commits behind main)"
            )

    results["stale_prs_detected"] = len(stale_prs)

    if not stale_prs:
        print("No stale PRs detected.")
        return results

    # Process stale PRs within rate limits
    remaining_budget = rate_status["remaining"]

    for stale_info in stale_prs:
        pr_number = stale_info["pr_number"]
        branch = stale_info["branch"]

        # Check cooldown
        if stale_detector.is_in_rebase_cooldown(pr_number):
            results["skipped"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "reason": "in_rebase_cooldown",
                }
            )
            print(f"  SKIP PR #{pr_number}: In rebase cooldown period")
            continue

        # Check rate limit budget
        if remaining_budget <= 0:
            results["skipped"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "reason": "rate_limit_exceeded",
                }
            )
            print(f"  SKIP PR #{pr_number}: Rate limit exceeded")
            continue

        # Skip draft PRs
        if stale_info["is_draft"]:
            results["skipped"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "reason": "draft_pr",
                }
            )
            print(f"  SKIP PR #{pr_number}: Draft PR")
            continue

        if dry_run:
            print(f"  DRY RUN: Would rebase PR #{pr_number}")
            results["skipped"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "reason": "dry_run",
                }
            )
            continue

        # Attempt rebase
        print(f"  Rebasing PR #{pr_number}...")
        results["rebase_attempts"] += 1

        mergeable = stale_info.get("mergeable")
        result = rebase_engine.rebase_pr(
            pr_number=pr_number,
            branch=branch,
            mergeable=mergeable if mergeable is not None else None,
            is_draft=stale_info["is_draft"],
        )

        if result.success:
            remaining_budget -= 1
            results["rebase_successes"] += 1
            results["rebased"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "metadata": result.metadata,
                }
            )
            print(f"    SUCCESS: {result.message}")
        else:
            results["rebase_failures"] += 1
            results["failures"].append(
                {
                    "pr_number": pr_number,
                    "branch": branch,
                    "action": result.action,
                    "message": result.message,
                }
            )
            print(f"    FAILED: {result.action} - {result.message}")

    # Update rate limit in results
    results["rate_limit"]["remaining"] = remaining_budget

    return results


def check_branch(branch: str) -> dict[str, Any]:
    """Check if a specific branch is behind main.

    Args:
        branch: The branch name to check.

    Returns:
        Dict with branch status.
    """
    detector = StaleDetector()

    is_behind, commits_behind = detector.is_behind_main(branch)
    ahead_behind = detector.get_ahead_behind(branch)

    result: dict[str, Any] = {
        "branch": branch,
        "is_behind": is_behind,
        "commits_behind": commits_behind,
        "is_feature_branch": detector.check_branch_is_feature(branch),
        "ahead": ahead_behind.get("ahead", 0),
        "behind": ahead_behind.get("behind", 0),
    }

    return result


def show_pr_status(pr_number: int) -> dict[str, Any]:
    """Show status of a specific PR including rebase info.

    Args:
        pr_number: The PR number.

    Returns:
        Dict with PR status.
    """
    detector = StaleDetector()
    gitea = GiteaAPI(GITEA_BASE_URL, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO)

    # Get PR info from Gitea
    pr_data = gitea.get_pr(pr_number)
    if not pr_data:
        return {"error": f"PR #{pr_number} not found"}

    branch = pr_data.get("head", {}).get("ref", "")
    is_draft = pr_data.get("draft", False)
    mergeable = pr_data.get("mergeable")

    # Check if behind main
    is_behind, commits_behind = detector.is_behind_main(branch)

    # Check cooldown
    in_cooldown = detector.is_in_rebase_cooldown(pr_number)

    # Get stale state
    stale_state = detector.get_stale_pr_state(pr_number)

    # Get rebase history
    rebase_log_key = f"bmad:chiseai:pr:rebase:log:{pr_number}"
    log_result = _redis_cli("LRANGE", rebase_log_key, "0", "9")
    rebase_history = []
    if log_result.returncode == 0 and log_result.stdout.strip():
        for line in log_result.stdout.strip().split("\n"):
            if line.strip():
                with suppress(json.JSONDecodeError):
                    rebase_history.append(json.loads(line.strip()))

    result: dict[str, Any] = {
        "pr_number": pr_number,
        "branch": branch,
        "is_draft": is_draft,
        "mergeable": mergeable,
        "is_behind": is_behind,
        "commits_behind": commits_behind,
        "in_rebase_cooldown": in_cooldown,
        "stale_state": stale_state,
        "rebase_history": rebase_history,
    }

    return result


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PR Auto-Rebase Engine - Detect and rebase stale PRs"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # detect-and-rebase command
    detect = sub.add_parser(
        "detect-and-rebase",
        help="Detect stale PRs and attempt to rebase them",
    )
    detect.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect stale PRs but don't rebase",
    )
    detect.add_argument(
        "--discord",
        action="store_true",
        help="Send Discord alerts for stale PRs",
    )

    # check-branch command
    check = sub.add_parser(
        "check-branch",
        help="Check if a specific branch is behind main",
    )
    check.add_argument("--branch", required=True, help="Branch name to check")

    # status command
    status = sub.add_parser(
        "status",
        help="Show detailed status of a PR including rebase info",
    )
    status.add_argument("--pr-number", type=int, required=True, help="PR number")

    # rate-limit command
    sub.add_parser(
        "rate-limit",
        help="Show current rebase rate limit status",
    )

    args = parser.parse_args()

    if args.cmd == "detect-and-rebase":
        results = detect_and_rebase(
            dry_run=args.dry_run,
            discord_alerts=args.discord,
        )
        print("\n" + "=" * 60)
        print("Auto-Rebase Results")
        print("=" * 60)
        print(f"Stale PRs detected: {results['stale_prs_detected']}")
        print(f"Rebase attempts: {results['rebase_attempts']}")
        print(f"Successes: {results['rebase_successes']}")
        print(f"Failures: {results['rebase_failures']}")
        print(f"Skipped: {len(results['skipped'])}")
        print(
            f"Rate limit remaining: {results['rate_limit']['remaining']}/{results['rate_limit']['max']}"
        )
        print("=" * 60)
        return 0

    elif args.cmd == "check-branch":
        result = check_branch(args.branch)
        print(json.dumps(result, indent=2))
        return 0

    elif args.cmd == "status":
        result = show_pr_status(args.pr_number)
        print(json.dumps(result, indent=2))
        return 0

    elif args.cmd == "rate-limit":
        result = get_rate_limit_status()
        print(json.dumps(result, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
