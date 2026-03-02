#!/usr/bin/env python3
"""Retry Handler - Handles retry logic for declined PRs.

This module provides:
- /retry comment handler for agents to retry declined PRs
- Retry eligibility checking
- Retry execution logic
- Retry success/failure tracking
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import outcome tracker (must be before bootstrap for path setup)
from outcome_tracker import OutcomeTracker, _utc_now

from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Redis key prefixes
RETRY_PREFIX = "bmad:chiseai:pr:retry"
FEEDBACK_PREFIX = "bmad:chiseai:pr:feedback"

# Default TTL (30 days)
DEFAULT_TTL_SECONDS = 2592000

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_WINDOW_HOURS = 72  # Must retry within 72 hours
MIN_FIXES_REQUIRED = 1  # At least 1 commit required for retry


def _get_redis_config() -> tuple[str, int, int]:
    """Get Redis connection config from environment."""
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    return host, port, db


def _redis_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a redis-cli command."""
    host, port, db = _get_redis_config()
    return subprocess.run(  # nosec B607
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


@dataclass
class RetryAttempt:
    """Represents a retry attempt for a declined PR."""

    pr_number: int
    story_id: str
    attempt_number: int
    started_at: str = field(default_factory=lambda: _utc_now())
    completed_at: str = ""
    status: str = "pending"  # pending, success, failed, abandoned
    fixes_description: str = ""
    new_head_sha: str = ""
    previous_head_sha: str = ""
    triggered_by: str = ""  # agent name
    failure_reason: str = ""
    time_to_resolution_minutes: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "pr_number": str(self.pr_number),
            "story_id": self.story_id,
            "attempt_number": str(self.attempt_number),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "fixes_description": self.fixes_description,
            "new_head_sha": self.new_head_sha,
            "previous_head_sha": self.previous_head_sha,
            "triggered_by": self.triggered_by,
            "failure_reason": self.failure_reason,
            "time_to_resolution_minutes": str(self.time_to_resolution_minutes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> RetryAttempt:
        """Create RetryAttempt from dictionary."""
        return cls(
            pr_number=int(data.get("pr_number", "0")),
            story_id=data.get("story_id", ""),
            attempt_number=int(data.get("attempt_number", "1")),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            status=data.get("status", "pending"),
            fixes_description=data.get("fixes_description", ""),
            new_head_sha=data.get("new_head_sha", ""),
            previous_head_sha=data.get("previous_head_sha", ""),
            triggered_by=data.get("triggered_by", ""),
            failure_reason=data.get("failure_reason", ""),
            time_to_resolution_minutes=float(
                data.get("time_to_resolution_minutes", "0")
            ),
        )


@dataclass
class RetryEligibility:
    """Result of retry eligibility check."""

    eligible: bool
    pr_number: int
    reason: str = ""
    attempts_remaining: int = 0
    hours_since_decline: float = 0.0
    fixes_detected: int = 0
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "pr_number": self.pr_number,
            "reason": self.reason,
            "attempts_remaining": self.attempts_remaining,
            "hours_since_decline": self.hours_since_decline,
            "fixes_detected": self.fixes_detected,
            "suggested_action": self.suggested_action,
        }


@dataclass
class RetryMetrics:
    """Metrics for retry tracking."""

    total_retries: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    abandoned_retries: int = 0
    success_rate: float = 0.0
    avg_time_to_resolution_minutes: float = 0.0
    common_failure_patterns: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
            "failed_retries": self.failed_retries,
            "abandoned_retries": self.abandoned_retries,
            "success_rate": self.success_rate,
            "avg_time_to_resolution_minutes": self.avg_time_to_resolution_minutes,
            "common_failure_patterns": self.common_failure_patterns,
        }


class RetryHandler:
    """Handles retry logic for declined PRs."""

    def __init__(self) -> None:
        self.tracker = OutcomeTracker()
        self.host, self.port, self.db = _get_redis_config()

    def _retry_key(self, pr_number: int, attempt_number: int) -> str:
        """Generate Redis key for a retry attempt."""
        return f"{RETRY_PREFIX}:{pr_number}:{attempt_number}"

    def _retry_index_key(self, pr_number: int) -> str:
        """Generate Redis key for retry index."""
        return f"{RETRY_PREFIX}:index:{pr_number}"

    def check_retry_eligibility(
        self,
        pr_number: int,
        current_head_sha: str = "",
    ) -> RetryEligibility:
        """Check if a PR is eligible for retry.

        Args:
            pr_number: The PR number to check
            current_head_sha: Current HEAD SHA to detect changes

        Returns:
            RetryEligibility with eligibility status and details
        """
        # Get the original outcome
        outcome = self.tracker.get_outcome(pr_number)
        if not outcome:
            return RetryEligibility(
                eligible=False,
                pr_number=pr_number,
                reason="PR outcome not found",
                suggested_action="Record outcome first",
            )

        # Check if outcome is declined/rejected
        if outcome.outcome not in ("declined", "rejected"):
            return RetryEligibility(
                eligible=False,
                pr_number=pr_number,
                reason=f"PR outcome is '{outcome.outcome}', not declined",
                suggested_action="Only declined PRs can be retried",
            )

        # Check retry window
        declined_at = datetime.fromisoformat(outcome.closed_at.replace("Z", "+00:00"))
        hours_since_decline = (datetime.now(UTC) - declined_at).total_seconds() / 3600

        if hours_since_decline > RETRY_WINDOW_HOURS:
            return RetryEligibility(
                eligible=False,
                pr_number=pr_number,
                reason=f"Retry window expired ({hours_since_decline:.1f} hours > {RETRY_WINDOW_HOURS} hours)",
                hours_since_decline=hours_since_decline,
                suggested_action="Create a new PR instead",
            )

        # Check retry attempts
        previous_attempts = self._get_retry_attempts(pr_number)
        if len(previous_attempts) >= MAX_RETRY_ATTEMPTS:
            return RetryEligibility(
                eligible=False,
                pr_number=pr_number,
                reason=f"Maximum retry attempts ({MAX_RETRY_ATTEMPTS}) reached",
                attempts_remaining=0,
                hours_since_decline=hours_since_decline,
                suggested_action="Escalate to human review",
            )

        # Check for new commits (fixes)
        fixes_detected = 0
        if current_head_sha and outcome.head_sha:
            if current_head_sha != outcome.head_sha:
                fixes_detected = 1  # Simplified - would use git log in production

        if fixes_detected < MIN_FIXES_REQUIRED:
            return RetryEligibility(
                eligible=False,
                pr_number=pr_number,
                reason="No new commits detected since decline",
                attempts_remaining=MAX_RETRY_ATTEMPTS - len(previous_attempts),
                hours_since_decline=hours_since_decline,
                fixes_detected=fixes_detected,
                suggested_action="Push fixes before retrying",
            )

        return RetryEligibility(
            eligible=True,
            pr_number=pr_number,
            reason="PR is eligible for retry",
            attempts_remaining=MAX_RETRY_ATTEMPTS - len(previous_attempts),
            hours_since_decline=hours_since_decline,
            fixes_detected=fixes_detected,
            suggested_action="Comment /retry to proceed",
        )

    def _get_retry_attempts(self, pr_number: int) -> list[RetryAttempt]:
        """Get all retry attempts for a PR."""
        result = _redis_cli("SMEMBERS", self._retry_index_key(pr_number))
        attempts = []

        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        attempt_num = int(line)
                        attempt = self._get_retry_attempt(pr_number, attempt_num)
                        if attempt:
                            attempts.append(attempt)
                    except ValueError:
                        continue

        return attempts

    def _get_retry_attempt(
        self, pr_number: int, attempt_number: int
    ) -> RetryAttempt | None:
        """Get a specific retry attempt."""
        key = self._retry_key(pr_number, attempt_number)
        result = _redis_cli("HGETALL", key)

        if result.returncode != 0 or not result.stdout.strip():
            return None

        lines = result.stdout.strip().split("\n")
        data: dict[str, str] = {}
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                data[lines[i]] = lines[i + 1]

        if not data:
            return None

        return RetryAttempt.from_dict(data)

    def initiate_retry(
        self,
        pr_number: int,
        story_id: str,
        triggered_by: str,
        fixes_description: str = "",
        new_head_sha: str = "",
    ) -> RetryAttempt | None:
        """Initiate a retry attempt for a declined PR.

        Args:
            pr_number: The PR number to retry
            story_id: The story ID associated with the PR
            triggered_by: Agent name triggering the retry
            fixes_description: Description of fixes applied
            new_head_sha: New HEAD SHA after fixes

        Returns:
            RetryAttempt if successful, None otherwise
        """
        # Check eligibility first
        eligibility = self.check_retry_eligibility(pr_number, new_head_sha)
        if not eligibility.eligible:
            print(
                f"PR #{pr_number} not eligible for retry: {eligibility.reason}",
                file=sys.stderr,
            )
            return None

        # Get previous attempts
        previous_attempts = self._get_retry_attempts(pr_number)
        attempt_number = len(previous_attempts) + 1

        # Get original outcome for previous SHA
        outcome = self.tracker.get_outcome(pr_number)
        previous_head_sha = outcome.head_sha if outcome else ""

        # Create retry attempt
        attempt = RetryAttempt(
            pr_number=pr_number,
            story_id=story_id,
            attempt_number=attempt_number,
            fixes_description=fixes_description,
            new_head_sha=new_head_sha,
            previous_head_sha=previous_head_sha,
            triggered_by=triggered_by,
        )

        # Store retry attempt
        self._store_retry_attempt(attempt)

        # Publish retry event to Redis
        self._publish_retry_event(attempt, "initiated")

        return attempt

    def _store_retry_attempt(self, attempt: RetryAttempt) -> None:
        """Store a retry attempt in Redis."""
        key = self._retry_key(attempt.pr_number, attempt.attempt_number)
        data = attempt.to_dict()

        for field_name, value in data.items():
            _redis_cli("HSET", key, field_name, str(value))

        _redis_cli("EXPIRE", key, str(DEFAULT_TTL_SECONDS))

        # Add to index
        _redis_cli(
            "SADD",
            self._retry_index_key(attempt.pr_number),
            str(attempt.attempt_number),
        )
        _redis_cli(
            "EXPIRE",
            self._retry_index_key(attempt.pr_number),
            str(DEFAULT_TTL_SECONDS),
        )

        # Add to global retry index
        _redis_cli(
            "SADD",
            f"{RETRY_PREFIX}:all",
            f"{attempt.pr_number}:{attempt.attempt_number}",
        )
        _redis_cli("EXPIRE", f"{RETRY_PREFIX}:all", str(DEFAULT_TTL_SECONDS))

    def _publish_retry_event(self, attempt: RetryAttempt, event_type: str) -> None:
        """Publish retry event to Redis pub/sub."""
        event = {
            "type": event_type,
            "pr_number": attempt.pr_number,
            "story_id": attempt.story_id,
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "timestamp": _utc_now(),
        }
        _redis_cli("PUBLISH", f"{RETRY_PREFIX}:events", json.dumps(event))

    def complete_retry(
        self,
        pr_number: int,
        attempt_number: int,
        success: bool,
        failure_reason: str = "",
    ) -> bool:
        """Mark a retry attempt as complete.

        Args:
            pr_number: The PR number
            attempt_number: The attempt number
            success: Whether the retry was successful
            failure_reason: Reason for failure if unsuccessful

        Returns:
            True if successful, False otherwise
        """
        attempt = self._get_retry_attempt(pr_number, attempt_number)
        if not attempt:
            print(
                f"Retry attempt {attempt_number} for PR #{pr_number} not found",
                file=sys.stderr,
            )
            return False

        attempt.status = "success" if success else "failed"
        attempt.completed_at = _utc_now()
        attempt.failure_reason = failure_reason

        # Calculate time to resolution
        started = datetime.fromisoformat(attempt.started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(attempt.completed_at.replace("Z", "+00:00"))
        attempt.time_to_resolution_minutes = (completed - started).total_seconds() / 60

        # Update stored attempt
        self._store_retry_attempt(attempt)

        # Publish completion event
        self._publish_retry_event(attempt, "completed")

        return True

    def abandon_retry(
        self,
        pr_number: int,
        attempt_number: int,
        reason: str,
    ) -> bool:
        """Mark a retry attempt as abandoned.

        Args:
            pr_number: The PR number
            attempt_number: The attempt number
            reason: Reason for abandonment

        Returns:
            True if successful, False otherwise
        """
        attempt = self._get_retry_attempt(pr_number, attempt_number)
        if not attempt:
            return False

        attempt.status = "abandoned"
        attempt.completed_at = _utc_now()
        attempt.failure_reason = reason

        self._store_retry_attempt(attempt)
        self._publish_retry_event(attempt, "abandoned")

        return True

    def handle_retry_comment(
        self,
        pr_number: int,
        story_id: str,
        agent_name: str,
        comment: str,
        current_head_sha: str = "",
    ) -> dict[str, Any]:
        """Handle a /retry comment from an agent.

        Args:
            pr_number: The PR number
            story_id: The story ID
            agent_name: Name of the agent commenting
            comment: The comment text (should start with /retry)
            current_head_sha: Current HEAD SHA

        Returns:
            Response dict with status and message
        """
        if not comment.strip().startswith("/retry"):
            return {
                "success": False,
                "message": "Comment does not start with /retry",
            }

        # Check eligibility
        eligibility = self.check_retry_eligibility(pr_number, current_head_sha)
        if not eligibility.eligible:
            return {
                "success": False,
                "message": f"Retry not eligible: {eligibility.reason}",
                "suggested_action": eligibility.suggested_action,
            }

        # Parse fixes description from comment
        fixes_description = ""
        lines = comment.strip().split("\n")
        if len(lines) > 1:
            fixes_description = "\n".join(lines[1:]).strip()

        # Initiate retry
        attempt = self.initiate_retry(
            pr_number=pr_number,
            story_id=story_id,
            triggered_by=agent_name,
            fixes_description=fixes_description,
            new_head_sha=current_head_sha,
        )

        if attempt:
            return {
                "success": True,
                "message": f"Retry attempt #{attempt.attempt_number} initiated for PR #{pr_number}",
                "attempt": attempt.to_dict(),
                "attempts_remaining": eligibility.attempts_remaining - 1,
            }
        else:
            return {
                "success": False,
                "message": "Failed to initiate retry",
            }

    def calculate_retry_metrics(
        self,
        days: int = 30,
    ) -> RetryMetrics:
        """Calculate retry metrics for a time period.

        Args:
            days: Number of days to analyze

        Returns:
            RetryMetrics with aggregated statistics
        """
        metrics = RetryMetrics()

        # Get all retry attempts
        result = _redis_cli("SMEMBERS", f"{RETRY_PREFIX}:all")
        if result.returncode != 0 or not result.stdout.strip():
            return metrics

        all_attempts: list[RetryAttempt] = []
        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                try:
                    pr_num, attempt_num = line.split(":")
                    attempt = self._get_retry_attempt(int(pr_num), int(attempt_num))
                    if attempt:
                        started = datetime.fromisoformat(
                            attempt.started_at.replace("Z", "+00:00")
                        )
                        if started >= cutoff_date:
                            all_attempts.append(attempt)
                except (ValueError, IndexError):
                    continue

        if not all_attempts:
            return metrics

        metrics.total_retries = len(all_attempts)

        # Calculate success/failure/abandoned
        for attempt in all_attempts:
            if attempt.status == "success":
                metrics.successful_retries += 1
            elif attempt.status == "failed":
                metrics.failed_retries += 1
            elif attempt.status == "abandoned":
                metrics.abandoned_retries += 1

        # Calculate success rate
        completed = metrics.successful_retries + metrics.failed_retries
        if completed > 0:
            metrics.success_rate = (metrics.successful_retries / completed) * 100

        # Calculate average time to resolution
        resolution_times = [
            a.time_to_resolution_minutes
            for a in all_attempts
            if a.time_to_resolution_minutes > 0
        ]
        if resolution_times:
            metrics.avg_time_to_resolution_minutes = sum(resolution_times) / len(
                resolution_times
            )

        # Identify common failure patterns
        failure_patterns: dict[str, int] = {}
        for attempt in all_attempts:
            if attempt.failure_reason:
                # Categorize failure reason
                reason_lower = attempt.failure_reason.lower()
                if "test" in reason_lower:
                    category = "test_failure"
                elif "lint" in reason_lower or "format" in reason_lower:
                    category = "code_quality"
                elif "conflict" in reason_lower:
                    category = "merge_conflict"
                elif "ci" in reason_lower:
                    category = "ci_failure"
                else:
                    category = "other"

                failure_patterns[category] = failure_patterns.get(category, 0) + 1

        metrics.common_failure_patterns = failure_patterns

        return metrics

    def get_retry_history(self, pr_number: int) -> list[RetryAttempt]:
        """Get retry history for a specific PR."""
        return self._get_retry_attempts(pr_number)

    def identify_common_failure_patterns(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """Identify common failure patterns for process improvement.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with patterns and recommendations
        """
        metrics = self.calculate_retry_metrics(days)

        patterns: dict[str, Any] = {
            "analysis_period_days": days,
            "total_retries": metrics.total_retries,
            "success_rate": metrics.success_rate,
            "common_patterns": metrics.common_failure_patterns,
            "recommendations": [],
        }

        # Generate recommendations based on patterns
        if "test_failure" in metrics.common_failure_patterns:
            count = metrics.common_failure_patterns["test_failure"]
            patterns["recommendations"].append(
                f"{count} retries failed due to test failures. "
                "Consider improving test coverage or pre-commit hooks."
            )

        if "code_quality" in metrics.common_failure_patterns:
            count = metrics.common_failure_patterns["code_quality"]
            patterns["recommendations"].append(
                f"{count} retries failed due to linting/formatting issues. "
                "Consider running black/ruff before retry."
            )

        if "merge_conflict" in metrics.common_failure_patterns:
            count = metrics.common_failure_patterns["merge_conflict"]
            patterns["recommendations"].append(
                f"{count} retries failed due to merge conflicts. "
                "Consider rebasing before retry."
            )

        if "ci_failure" in metrics.common_failure_patterns:
            count = metrics.common_failure_patterns["ci_failure"]
            patterns["recommendations"].append(
                f"{count} retries failed due to CI issues. "
                "Consider checking CI pipeline health."
            )

        if metrics.success_rate < 50 and metrics.total_retries >= 5:
            patterns["recommendations"].append(
                f"Low retry success rate ({metrics.success_rate:.1f}%). "
                "Consider requiring human review before retry."
            )

        return patterns


def main() -> int:
    """CLI for retry handler."""
    import argparse

    p = argparse.ArgumentParser(description="PR Retry Handler")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Check eligibility
    eligible = sub.add_parser("check", help="Check retry eligibility")
    eligible.add_argument("--pr-number", type=int, required=True)
    eligible.add_argument("--head-sha", default="")

    # Initiate retry
    initiate = sub.add_parser("initiate", help="Initiate a retry")
    initiate.add_argument("--pr-number", type=int, required=True)
    initiate.add_argument("--story-id", required=True)
    initiate.add_argument("--triggered-by", required=True)
    initiate.add_argument("--fixes-description", default="")
    initiate.add_argument("--head-sha", default="")

    # Complete retry
    complete = sub.add_parser("complete", help="Complete a retry attempt")
    complete.add_argument("--pr-number", type=int, required=True)
    complete.add_argument("--attempt-number", type=int, required=True)
    complete.add_argument("--success", action="store_true")
    complete.add_argument("--failure-reason", default="")

    # Handle /retry comment
    comment = sub.add_parser("handle-comment", help="Handle /retry comment")
    comment.add_argument("--pr-number", type=int, required=True)
    comment.add_argument("--story-id", required=True)
    comment.add_argument("--agent-name", required=True)
    comment.add_argument("--comment", required=True)
    comment.add_argument("--head-sha", default="")

    # Get metrics
    metrics_cmd = sub.add_parser("metrics", help="Get retry metrics")
    metrics_cmd.add_argument("--days", type=int, default=30)

    # Get history
    history = sub.add_parser("history", help="Get retry history for a PR")
    history.add_argument("--pr-number", type=int, required=True)

    # Identify patterns
    patterns_cmd = sub.add_parser("patterns", help="Identify failure patterns")
    patterns_cmd.add_argument("--days", type=int, default=30)

    args = p.parse_args()

    handler = RetryHandler()

    if args.cmd == "check":
        eligibility = handler.check_retry_eligibility(args.pr_number, args.head_sha)
        print(json.dumps(eligibility.to_dict(), indent=2))
        return 0 if eligibility.eligible else 1

    elif args.cmd == "initiate":
        attempt = handler.initiate_retry(
            pr_number=args.pr_number,
            story_id=args.story_id,
            triggered_by=args.triggered_by,
            fixes_description=args.fixes_description,
            new_head_sha=args.head_sha,
        )
        if attempt:
            print(json.dumps(attempt.to_dict(), indent=2))
            return 0
        else:
            print("Failed to initiate retry", file=sys.stderr)
            return 1

    elif args.cmd == "complete":
        if handler.complete_retry(
            pr_number=args.pr_number,
            attempt_number=args.attempt_number,
            success=args.success,
            failure_reason=args.failure_reason,
        ):
            print(f"Retry attempt {args.attempt_number} completed")
            return 0
        else:
            print("Failed to complete retry", file=sys.stderr)
            return 1

    elif args.cmd == "handle-comment":
        result = handler.handle_retry_comment(
            pr_number=args.pr_number,
            story_id=args.story_id,
            agent_name=args.agent_name,
            comment=args.comment,
            current_head_sha=args.head_sha,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1

    elif args.cmd == "metrics":
        metrics_result = handler.calculate_retry_metrics(args.days)
        print(json.dumps(metrics_result.to_dict(), indent=2))
        return 0

    elif args.cmd == "history":
        attempts = handler.get_retry_history(args.pr_number)
        print(json.dumps([a.to_dict() for a in attempts], indent=2))
        return 0

    elif args.cmd == "patterns":
        pattern_results = handler.identify_common_failure_patterns(args.days)
        print(json.dumps(pattern_results, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
