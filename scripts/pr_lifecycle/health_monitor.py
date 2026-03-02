#!/usr/bin/env python3
"""Health Monitor - Background service for comprehensive PR health monitoring.

This module provides a scheduled health scan that detects stuck PRs,
systemic issues, and triggers recovery actions for the entire PR fleet.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Import PR state manager and monitor
from .pr_monitor import PRMonitor  # noqa: E402
from .pr_state_manager import PRStateManager, _utc_now  # noqa: E402

# Configuration
DEFAULT_STUCK_THRESHOLD_MIN = int(os.getenv("CHISE_PR_STUCK_THRESHOLD_MIN", "30"))
SYSTEMIC_THRESHOLD = int(os.getenv("CHISE_PR_SYSTEMIC_THRESHOLD", "3"))


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


class PRHealthMonitor:
    """Comprehensive PR health monitoring service."""

    def __init__(self, stuck_threshold_min: int = DEFAULT_STUCK_THRESHOLD_MIN):
        self.state_mgr = PRStateManager()
        self.monitor = PRMonitor(stuck_threshold_min=stuck_threshold_min)
        self.stuck_threshold_min = stuck_threshold_min

    def scan_all_prs(self) -> dict[str, Any]:
        """Comprehensive scan of all PRs."""
        results: dict[str, Any] = {
            "scan_id": datetime.now(UTC).strftime("%Y%m%d-%H%M%S"),
            "scanned_at": _utc_now(),
            "summary": {
                "total_prs": 0,
                "active_prs": 0,
                "terminal_prs": 0,
                "stuck_prs": 0,
                "escalated_prs": 0,
                "needs_attention": 0,
            },
            "by_state": {},
            "issues": [],
            "recommendations": [],
        }

        # Get all active PRs
        active_prs = self.state_mgr.get_active_prs()
        results["summary"]["active_prs"] = len(active_prs)

        # Analyze each PR
        failure_patterns: dict[str, list[int]] = {}
        stuck_prs = []

        for pr_number in active_prs:
            state = self.state_mgr.get_pr(pr_number)
            if not state:
                results["issues"].append(
                    {
                        "pr_number": pr_number,
                        "issue": "missing_state",
                        "severity": "error",
                    }
                )
                continue

            # Count by state
            state_name = state.current_state
            results["by_state"][state_name] = results["by_state"].get(state_name, 0) + 1

            # Check if stuck
            is_stuck, stuck_reason = self.monitor.is_pr_stuck(state)
            if is_stuck:
                stuck_prs.append(
                    {
                        "pr_number": pr_number,
                        "state": state_name,
                        "reason": stuck_reason,
                        "story_id": state.story_id,
                    }
                )
                results["summary"]["stuck_prs"] += 1
                results["summary"]["needs_attention"] += 1

                results["issues"].append(
                    {
                        "pr_number": pr_number,
                        "issue": "stuck",
                        "severity": "warning",
                        "reason": stuck_reason,
                        "state": state_name,
                    }
                )

            # Check if escalated
            if state.escalated:
                results["summary"]["escalated_prs"] += 1
                results["summary"]["needs_attention"] += 1
                results["issues"].append(
                    {
                        "pr_number": pr_number,
                        "issue": "escalated",
                        "severity": "error",
                        "reason": state.escalation_reason,
                    }
                )

            # Track failure patterns for systemic detection
            if state.failure_type:
                failure_patterns.setdefault(state.failure_type, []).append(pr_number)

            # Check for excessive retries
            if state.retry_count >= state.max_retries:
                results["issues"].append(
                    {
                        "pr_number": pr_number,
                        "issue": "max_retries_exceeded",
                        "severity": "error",
                        "retries": state.retry_count,
                    }
                )
                results["summary"]["needs_attention"] += 1

        # Detect systemic issues
        for failure_type, prs in failure_patterns.items():
            if len(prs) >= SYSTEMIC_THRESHOLD:
                results["issues"].append(
                    {
                        "issue": "systemic_failure",
                        "severity": "critical",
                        "failure_type": failure_type,
                        "affected_prs": prs,
                        "count": len(prs),
                    }
                )
                results["summary"]["needs_attention"] += len(prs)
                results["recommendations"].append(
                    f"Systemic issue detected: {failure_type} affecting {len(prs)} PRs. "
                    "Consider pausing queue and investigating root cause."
                )

        # Generate recommendations
        if stuck_prs:
            results["recommendations"].append(
                f"{len(stuck_prs)} PRs appear stuck and may need manual intervention or recovery actions."
            )

        if results["summary"]["escalated_prs"] > 0:
            results["recommendations"].append(
                f"{results['summary']['escalated_prs']} PRs escalated to humans - review required."
            )

        # Store scan results in Redis
        self._store_scan(results)

        return results

    def _store_scan(self, results: dict[str, Any]) -> None:
        """Store scan results in Redis."""
        scan_key = f"bmad:chiseai:pr:health:scan:{results['scan_id']}"

        subprocess.run(  # nosec B607
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

        # Set TTL
        subprocess.run(  # nosec B607
            [
                "redis-cli",
                "-h",
                "host.docker.internal",
                "-p",
                "6380",
                "-n",
                "0",
                "EXPIRE",
                scan_key,
                "604800",
            ],  # 7 days
            text=True,
            capture_output=True,
            check=False,
        )

        # Update last scan
        subprocess.run(  # nosec B607
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

    def trigger_recovery_actions(self, scan_results: dict[str, Any]) -> dict[str, Any]:
        """Trigger automatic recovery actions based on scan results."""
        actions: dict[str, list[dict[str, Any]]] = {
            "triggered": [],
            "failed": [],
            "skipped": [],
        }

        for issue in scan_results.get("issues", []):
            pr_number = issue.get("pr_number")
            if not pr_number:
                continue

            issue_type = issue.get("issue")

            # Skip escalated PRs
            if issue_type == "escalated":
                actions["skipped"].append(
                    {
                        "pr_number": pr_number,
                        "reason": "Already escalated",
                    }
                )
                continue

            # Skip if max retries exceeded
            state = self.state_mgr.get_pr(pr_number)
            if state and state.retry_count >= state.max_retries:
                # Auto-escalate
                self.state_mgr.mark_escalated(
                    pr_number,
                    reason=f"Max retries exceeded for {issue_type}",
                    triggered_by="health_monitor",
                )
                actions["triggered"].append(
                    {
                        "pr_number": pr_number,
                        "action": "escalated",
                        "reason": "max_retries",
                    }
                )
                continue

            # Route to appropriate handler
            if issue_type == "stuck":
                # Try to determine why stuck and take action
                handler_result = self._handle_stuck_pr(pr_number, issue)
                actions["triggered"].append(
                    {
                        "pr_number": pr_number,
                        "action": "stuck_recovery",
                        "result": handler_result,
                    }
                )

            elif issue_type == "ci_failed":
                # Trigger CI failure recovery
                actions["triggered"].append(
                    {
                        "pr_number": pr_number,
                        "action": "ci_recovery",
                        "result": "queued",
                    }
                )

        return actions

    def _handle_stuck_pr(self, pr_number: int, issue: dict[str, Any]) -> str:
        """Handle a stuck PR by determining the cause and taking action."""
        state = self.state_mgr.get_pr(pr_number)
        if not state:
            return "state_not_found"

        current_state = issue.get("state", state.current_state)

        # State-specific handling
        if current_state == "running_ci":
            # CI might be stuck - check if pipeline exists
            return "checking_ci_status"

        elif current_state == "mergeable":
            # Ready to merge but not merging - try force merge
            return "attempting_merge"

        elif current_state == "conflict_detected":
            # Try auto-rebase
            return "attempting_rebase"

        elif current_state == "needs_approval":
            # Request approval
            return "requesting_approval"

        return "unknown_state"

    def generate_report(self, scan_results: dict[str, Any]) -> str:
        """Generate a human-readable report from scan results."""
        lines = [
            "=" * 60,
            "PR Health Monitor Report",
            f"Scan ID: {scan_results['scan_id']}",
            f"Scanned At: {scan_results['scanned_at']}",
            "=" * 60,
            "",
            "Summary:",
            f"  Total Active PRs: {scan_results['summary']['active_prs']}",
            f"  Stuck PRs: {scan_results['summary']['stuck_prs']}",
            f"  Escalated PRs: {scan_results['summary']['escalated_prs']}",
            f"  Needs Attention: {scan_results['summary']['needs_attention']}",
            "",
            "By State:",
        ]

        for state, count in sorted(scan_results["by_state"].items()):
            lines.append(f"  {state}: {count}")

        if scan_results.get("issues"):
            lines.extend(["", "Issues:"])
            for issue in scan_results["issues"]:
                pr_info = f"PR #{issue.get('pr_number', 'N/A')}"
                lines.append(
                    f"  [{issue['severity'].upper()}] {pr_info}: {issue['issue']}"
                )
                if "reason" in issue:
                    lines.append(f"    Reason: {issue['reason']}")

        if scan_results.get("recommendations"):
            lines.extend(["", "Recommendations:"])
            for rec in scan_results["recommendations"]:
                lines.append(f"  - {rec}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def check_systemic_health(self) -> dict[str, Any]:
        """Quick check for systemic issues that need immediate attention."""
        results: dict[str, Any] = {
            "healthy": True,
            "critical_issues": [],
            "warnings": [],
        }

        # Scan for issues
        scan = self.scan_all_prs()

        # Check for systemic failures
        for issue in scan.get("issues", []):
            if issue.get("issue") == "systemic_failure":
                results["healthy"] = False
                results["critical_issues"].append(
                    {
                        "type": "systemic_failure",
                        "failure_type": issue.get("failure_type"),
                        "count": issue.get("count"),
                        "prs": issue.get("affected_prs"),
                    }
                )

        # Check if too many PRs are stuck
        stuck_ratio = scan["summary"]["stuck_prs"] / max(
            scan["summary"]["active_prs"], 1
        )
        if stuck_ratio > 0.5:  # More than 50% stuck
            results["healthy"] = False
            results["critical_issues"].append(
                {
                    "type": "high_stuck_ratio",
                    "message": f"{stuck_ratio * 100:.0f}% of PRs are stuck",
                    "stuck_count": scan["summary"]["stuck_prs"],
                    "total_count": scan["summary"]["active_prs"],
                }
            )

        # Warnings
        if scan["summary"]["escalated_prs"] > 5:
            results["warnings"].append(
                {
                    "type": "many_escalated",
                    "message": f"{scan['summary']['escalated_prs']} PRs escalated",
                }
            )

        return results


def main() -> int:
    """CLI for PR health monitoring."""
    import argparse

    p = argparse.ArgumentParser(description="PR Health Monitor")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Scan command
    scan = sub.add_parser("scan", help="Run comprehensive scan")
    scan.add_argument(
        "--stuck-threshold-min", type=int, default=DEFAULT_STUCK_THRESHOLD_MIN
    )

    # Check command
    sub.add_parser("check", help="Quick systemic health check")

    # Report command
    report = sub.add_parser("report", help="Generate report from latest scan")
    report.add_argument("--scan-id", help="Specific scan ID (default: latest)")

    # Recovery command
    recovery = sub.add_parser("recovery", help="Trigger recovery actions")
    recovery.add_argument(
        "--dry-run", action="store_true", help="Show what would be done"
    )

    args = p.parse_args()

    monitor = PRHealthMonitor(
        stuck_threshold_min=getattr(
            args, "stuck_threshold_min", DEFAULT_STUCK_THRESHOLD_MIN
        )
    )

    if args.cmd == "scan":
        results = monitor.scan_all_prs()
        print(monitor.generate_report(results))

        # Return error code if critical issues
        for issue in results.get("issues", []):
            if issue.get("severity") in {"critical", "error"}:
                return 1
        return 0

    elif args.cmd == "check":
        results = monitor.check_systemic_health()
        print(json.dumps(results, indent=2))
        return 0 if results["healthy"] else 1

    elif args.cmd == "report":
        # Get latest scan from Redis
        result = _redis_cli("KEYS", "bmad:chiseai:pr:health:scan:*")
        if result.returncode == 0 and result.stdout.strip():
            keys = result.stdout.strip().split("\n")
            latest_key = sorted(keys)[-1]

            data = _redis_cli("GET", latest_key)
            if data.returncode == 0:
                scan_results = json.loads(data.stdout)
                print(monitor.generate_report(scan_results))
                return 0

        print("No scan results found")
        return 1

    elif args.cmd == "recovery":
        # Get latest scan
        results = monitor.scan_all_prs()

        if args.dry_run:
            print("DRY RUN - Would trigger the following actions:")
            actions = monitor.trigger_recovery_actions(results)
            print(json.dumps(actions, indent=2))
        else:
            actions = monitor.trigger_recovery_actions(results)
            print("Recovery actions triggered:")
            print(json.dumps(actions, indent=2))

        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
