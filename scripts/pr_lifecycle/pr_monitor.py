#!/usr/bin/env python3
"""PR Monitor - Polls and monitors PR status from creation to terminal state.

This module provides continuous monitoring of PRs, detecting state changes
and triggering appropriate recovery actions when failures occur.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Import PR state manager
from pr_state_manager import PRState, PRStateManager, _utc_now

# Default configuration
DEFAULT_POLL_INTERVAL_SEC = int(os.getenv("CHISE_PR_POLL_INTERVAL_SEC", "30"))
DEFAULT_HEALTH_SCAN_INTERVAL_SEC = int(
    os.getenv("CHISE_PR_HEALTH_SCAN_INTERVAL_SEC", "300")
)
DEFAULT_STUCK_THRESHOLD_MIN = int(os.getenv("CHISE_PR_STUCK_THRESHOLD_MIN", "30"))

# Gitea configuration
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://host.docker.internal:3000").rstrip(
    "/"
)
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_OWNER = os.getenv("GITEA_OWNER", "craig")
GITEA_REPO = os.getenv("GITEA_REPO", "ChiseAI")

# Required CI context
REQUIRED_CONTEXT = os.getenv("CHISE_REQUIRED_CONTEXT", "ci/woodpecker/pr/ci")


class GiteaAPI:
    """Simple Gitea API client."""

    def __init__(self, base_url: str, token: str, owner: str, repo: str):
        self.base_url = base_url
        self.token = token
        self.owner = owner
        self.repo = repo

    def _req_json(
        self, method: str, path: str, body: dict | None = None
    ) -> dict | None:
        """Make a request to the Gitea API."""
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {self.token}",
        }

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            print(f"API Error: {method} {url} - HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Request Error: {method} {url} - {e}", file=sys.stderr)
            return None

    def get_pr(self, pr_number: int) -> dict | None:
        """Get PR details."""
        return self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}",
        )

    def get_commit_status(self, sha: str) -> dict | None:
        """Get commit status."""
        return self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/commits/{sha}/status",
        )

    def get_pr_reviews(self, pr_number: int) -> list[dict] | None:
        """Get PR reviews."""
        result = self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews",
        )
        return result if isinstance(result, list) else None


class PRMonitor:
    """Monitors PRs and triggers recovery actions."""

    def __init__(
        self,
        poll_interval_sec: int = DEFAULT_POLL_INTERVAL_SEC,
        stuck_threshold_min: int = DEFAULT_STUCK_THRESHOLD_MIN,
    ):
        self.state_mgr = PRStateManager()
        self.gitea = GiteaAPI(GITEA_BASE_URL, GITEA_TOKEN, GITEA_OWNER, GITEA_REPO)
        self.poll_interval = poll_interval_sec
        self.stuck_threshold_min = stuck_threshold_min
        self._running = False

    def check_pr_status(self, pr_number: int) -> dict[str, Any]:
        """Check current status of a PR from Gitea."""
        pr_data = self.gitea.get_pr(pr_number)
        if not pr_data:
            return {"error": "Failed to fetch PR data"}

        # Extract key info
        state = str(pr_data.get("state", "")).lower()
        merged = bool(pr_data.get("merged", False))
        mergeable = pr_data.get("mergeable")
        head_sha = str((pr_data.get("head") or {}).get("sha", ""))

        result = {
            "pr_number": pr_number,
            "state": state,
            "merged": merged,
            "mergeable": mergeable,
            "head_sha": head_sha,
        }

        # Check CI status
        if head_sha:
            ci_status = self.gitea.get_commit_status(head_sha)
            if ci_status:
                result["ci_state"] = ci_status.get("state", "unknown")
                result["ci_statuses"] = ci_status.get("statuses", [])

                # Find required context
                for status in result["ci_statuses"]:
                    if status.get("context") == REQUIRED_CONTEXT:
                        result["required_context_state"] = status.get(
                            "state", "unknown"
                        )
                        break

        # Check approvals
        reviews = self.gitea.get_pr_reviews(pr_number)
        if reviews:
            approvals = [r for r in reviews if r.get("state") == "APPROVED"]
            result["approval_count"] = len(approvals)
            result["has_approval"] = len(approvals) > 0
        else:
            result["approval_count"] = 0
            result["has_approval"] = False

        return result

    def determine_target_state(
        self, status: dict[str, Any], current_state: str
    ) -> str | None:
        """Determine what state the PR should transition to based on current status."""

        # Terminal states
        if status.get("merged"):
            return "merged"

        if status.get("state") == "closed":
            return "closed_unmerged"

        # Check for merge conflicts
        if status.get("mergeable") is False:
            return "conflict_detected"

        # Check CI status
        required_ctx = status.get("required_context_state", "unknown")
        ci_state = status.get("ci_state", "unknown")

        if required_ctx == "failure" or ci_state == "failure":
            return "ci_failed"

        if required_ctx == "pending" or ci_state == "pending":
            if current_state in {"created", "pending_ci"}:
                return "running_ci"
            return None  # Stay in current state

        if required_ctx == "success" or ci_state == "success":
            # CI passed, check approval
            if status.get("has_approval"):
                if status.get("mergeable") is True:
                    return "mergeable"
                return "ci_passed"  # Waiting for merge
            return "needs_approval"

        return None  # No state change needed

    def is_pr_stuck(self, state: PRState) -> tuple[bool, str]:
        """Check if a PR appears to be stuck."""
        from datetime import datetime

        if state.is_terminal():
            return False, ""

        # Parse last update time
        try:
            last_update = datetime.fromisoformat(
                state.last_updated_at.replace("Z", "+00:00")
            )
            now = datetime.now(UTC)
            minutes_since_update = (now - last_update).total_seconds() / 60
        except (ValueError, AttributeError):
            return False, ""

        # Check if stuck based on state
        if minutes_since_update > self.stuck_threshold_min:
            return True, f"No activity for {minutes_since_update:.0f} minutes"

        # State-specific stuck detection
        stuck_criteria = {
            "running_ci": 45,  # CI running too long
            "mergeable": 15,  # Ready to merge but not merging
            "pending_ci": 30,  # CI not starting
        }

        if state.current_state in stuck_criteria:
            threshold = stuck_criteria[state.current_state]
            if minutes_since_update > threshold:
                return (
                    True,
                    f"{state.current_state} for {minutes_since_update:.0f} minutes",
                )

        return False, ""

    def process_pr(self, pr_number: int) -> dict[str, Any]:
        """Process a single PR - check status and update state."""
        # Get current state
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return {"error": "PR not found in state manager"}

        if state.is_terminal():
            return {"status": "terminal", "state": state.current_state}

        # Check if stuck
        is_stuck, stuck_reason = self.is_pr_stuck(state)
        if is_stuck:
            # Log stuck incident
            self.state_mgr.log_failure(
                pr_number,
                failure_type="stuck_pr",
                message=stuck_reason,
                evidence={"last_state": state.current_state, "minutes": stuck_reason},
            )
            return {"status": "stuck", "reason": stuck_reason}

        # Fetch current status from Gitea
        status = self.check_pr_status(pr_number)
        if "error" in status:
            return {"error": status["error"]}

        # Check for SHA changes (new commits)
        if status.get("head_sha") and status["head_sha"] != state.head_sha:
            # New commits pushed
            self.state_mgr.transition_state(
                pr_number,
                to_state="pending_ci",
                triggered_by="new_commits",
                metadata={"old_sha": state.head_sha, "new_sha": status["head_sha"]},
            )
            # Update SHA in state
            state.head_sha = status["head_sha"]
            self.state_mgr.update_pr(state)
            return {"status": "sha_changed", "new_sha": status["head_sha"]}

        # Determine target state
        target_state = self.determine_target_state(status, state.current_state)

        if target_state and target_state != state.current_state:
            # Transition to new state
            self.state_mgr.transition_state(
                pr_number,
                to_state=target_state,
                triggered_by="poll",
                metadata={"gitea_status": status},
            )
            return {
                "status": "transitioned",
                "from": state.current_state,
                "to": target_state,
            }

        return {"status": "no_change", "state": state.current_state}

    def monitor_single_pr(
        self, pr_number: int, timeout_sec: int = 3600
    ) -> dict[str, Any]:
        """Monitor a single PR until it reaches terminal state or timeout."""
        start_time = time.time()
        deadline = start_time + timeout_sec

        print(f"Starting monitoring for PR #{pr_number}")

        while time.time() < deadline:
            result = self.process_pr(pr_number)

            if "error" in result:
                print(f"Error processing PR #{pr_number}: {result['error']}")
                time.sleep(self.poll_interval)
                continue

            if result.get("status") == "terminal":
                print(f"PR #{pr_number} reached terminal state: {result.get('state')}")
                return result

            if result.get("status") in {"transitioned", "sha_changed"}:
                print(f"PR #{pr_number}: {result}")

            time.sleep(self.poll_interval)

        return {
            "status": "timeout",
            "message": f"Monitoring timed out after {timeout_sec}s",
        }

    def monitor_all_active(self) -> list[dict[str, Any]]:
        """Process all active PRs once."""
        active_prs = self.state_mgr.get_active_prs()
        results = []

        print(f"Processing {len(active_prs)} active PRs...")

        for pr_number in active_prs:
            result = self.process_pr(pr_number)
            result["pr_number"] = pr_number
            results.append(result)

            if result.get("status") in {"transitioned", "stuck", "sha_changed"}:
                print(f"PR #{pr_number}: {result}")

        return results

    def run_health_scan(self) -> dict[str, Any]:
        """Run a comprehensive health scan of all PRs."""
        print("Running PR health scan...")

        results = {
            "scanned_at": _utc_now(),
            "total_active": 0,
            "by_state": {},
            "stuck_prs": [],
            "escalated_prs": [],
            "errors": [],
        }

        # Get all active PRs
        active_prs = self.state_mgr.get_active_prs()
        results["total_active"] = len(active_prs)

        for pr_number in active_prs:
            state = self.state_mgr.get_pr(pr_number)
            if not state:
                results["errors"].append(
                    f"PR #{pr_number} in active set but no state found"
                )
                continue

            # Count by state
            results["by_state"][state.current_state] = (
                results["by_state"].get(state.current_state, 0) + 1
            )

            # Check if stuck
            is_stuck, stuck_reason = self.is_pr_stuck(state)
            if is_stuck:
                results["stuck_prs"].append(
                    {
                        "pr_number": pr_number,
                        "state": state.current_state,
                        "reason": stuck_reason,
                    }
                )

            # Check if escalated
            if state.escalated:
                results["escalated_prs"].append(
                    {
                        "pr_number": pr_number,
                        "reason": state.escalation_reason,
                        "escalated_at": state.escalated_at,
                    }
                )

        # Store scan results
        self._store_scan_results(results)

        return results

    def _store_scan_results(self, results: dict[str, Any]) -> None:
        """Store scan results in Redis."""
        from datetime import datetime

        scan_key = (
            f"bmad:chiseai:pr:health:scan:{datetime.now(UTC).strftime('%Y-%m-%d-%H%M')}"
        )

        # Store as JSON
        _redis_cli = subprocess.run(
            [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "-n",
                "0",
                "SET",
                scan_key,
                json.dumps(results),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        # Update last scan timestamp
        subprocess.run(
            [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "-n",
                "0",
                "SET",
                "bmad:chiseai:pr:health:last_scan",
                results["scanned_at"],
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def start_continuous_monitoring(self) -> None:
        """Start continuous monitoring loop (runs indefinitely)."""
        self._running = True
        last_health_scan = 0

        print("Starting continuous PR monitoring...")

        while self._running:
            try:
                # Process all active PRs
                self.monitor_all_active()

                # Run health scan periodically
                current_time = time.time()
                if current_time - last_health_scan > DEFAULT_HEALTH_SCAN_INTERVAL_SEC:
                    self.run_health_scan()
                    last_health_scan = current_time

                # Sleep until next poll
                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")
                self._running = False
            except Exception as e:
                print(f"Error in monitoring loop: {e}", file=sys.stderr)
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop continuous monitoring."""
        self._running = False


def main() -> int:
    """CLI for PR monitoring."""
    p = argparse.ArgumentParser(description="PR Monitor")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Monitor single PR
    single = sub.add_parser("monitor", help="Monitor a single PR until terminal")
    single.add_argument("--pr-number", type=int, required=True)
    single.add_argument("--timeout-sec", type=int, default=3600)
    single.add_argument("--poll-sec", type=int, default=DEFAULT_POLL_INTERVAL_SEC)

    # Process all once
    sub.add_parser("process-all", help="Process all active PRs once")

    # Health scan
    sub.add_parser("health-scan", help="Run comprehensive health scan")

    # Continuous monitoring
    continuous = sub.add_parser("continuous", help="Start continuous monitoring")
    continuous.add_argument("--poll-sec", type=int, default=DEFAULT_POLL_INTERVAL_SEC)

    # Check status
    check = sub.add_parser("check", help="Check PR status once")
    check.add_argument("--pr-number", type=int, required=True)

    args = p.parse_args()

    monitor = PRMonitor(
        poll_interval_sec=getattr(args, "poll_sec", DEFAULT_POLL_INTERVAL_SEC)
    )

    if args.cmd == "monitor":
        result = monitor.monitor_single_pr(args.pr_number, args.timeout_sec)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "terminal" else 1

    elif args.cmd == "process-all":
        results = monitor.monitor_all_active()
        print(json.dumps(results, indent=2))
        return 0

    elif args.cmd == "health-scan":
        results = monitor.run_health_scan()
        print(json.dumps(results, indent=2))
        return 0

    elif args.cmd == "continuous":
        monitor.start_continuous_monitoring()
        return 0

    elif args.cmd == "check":
        status = monitor.check_pr_status(args.pr_number)
        print(json.dumps(status, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
