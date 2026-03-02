#!/usr/bin/env python3
"""Outcome Tracker - Tracks PR outcomes and calculates success metrics.

This module provides comprehensive outcome tracking for PR reviews,
including approved, rejected, merged, and rolled back states.
Data is stored in Redis with 30-day retention.
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
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Redis key prefixes
OUTCOME_PREFIX = "bmad:chiseai:pr:outcome"
METRICS_PREFIX = "bmad:chiseai:pr:metrics"
FEEDBACK_PREFIX = "bmad:chiseai:pr:feedback"

# Default TTL (30 days)
DEFAULT_TTL_SECONDS = 2592000


@dataclass
class PROutcome:
    """Represents the final outcome of a PR."""

    # Identification
    pr_number: int
    story_id: str
    branch: str
    head_sha: str

    # Outcome
    outcome: str  # merged, declined, rejected, rolled_back, abandoned, escalated, closed_unmerged
    outcome_reason: str = ""

    # Timing
    created_at: str = field(default_factory=lambda: _utc_now())
    merged_at: str = ""
    closed_at: str = ""
    time_to_merge_minutes: float = 0.0

    # Review details
    review_decision: str = ""  # approved, changes_requested, rejected
    reviewer: str = ""
    review_comment: str = ""
    auto_approved: bool = False
    auto_merged: bool = False

    # Rollback info (if applicable)
    rolled_back: bool = False
    rolled_back_at: str = ""
    rollback_reason: str = ""
    rollback_sha: str = ""

    # CI info
    ci_passed: bool = False
    ci_failures: list[str] = field(default_factory=list)

    # Agent info
    opened_by_agent: str = ""
    merged_by_agent: str = ""

    # Quality metrics
    lines_added: int = 0
    lines_deleted: int = 0
    files_changed: int = 0
    test_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "pr_number": str(self.pr_number),
            "story_id": self.story_id,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "created_at": self.created_at,
            "merged_at": self.merged_at,
            "closed_at": self.closed_at,
            "time_to_merge_minutes": str(self.time_to_merge_minutes),
            "review_decision": self.review_decision,
            "reviewer": self.reviewer,
            "review_comment": self.review_comment,
            "auto_approved": "true" if self.auto_approved else "false",
            "auto_merged": "true" if self.auto_merged else "false",
            "rolled_back": "true" if self.rolled_back else "false",
            "rolled_back_at": self.rolled_back_at,
            "rollback_reason": self.rollback_reason,
            "rollback_sha": self.rollback_sha,
            "ci_passed": "true" if self.ci_passed else "false",
            "ci_failures": json.dumps(self.ci_failures),
            "opened_by_agent": self.opened_by_agent,
            "merged_by_agent": self.merged_by_agent,
            "lines_added": str(self.lines_added),
            "lines_deleted": str(self.lines_deleted),
            "files_changed": str(self.files_changed),
            "test_coverage": str(self.test_coverage),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> PROutcome:
        """Create PROutcome from dictionary retrieved from Redis."""
        return cls(
            pr_number=int(data.get("pr_number", 0)),
            story_id=data.get("story_id", ""),
            branch=data.get("branch", ""),
            head_sha=data.get("head_sha", ""),
            outcome=data.get("outcome", ""),
            outcome_reason=data.get("outcome_reason", ""),
            created_at=data.get("created_at", ""),
            merged_at=data.get("merged_at", ""),
            closed_at=data.get("closed_at", ""),
            time_to_merge_minutes=float(data.get("time_to_merge_minutes", "0")),
            review_decision=data.get("review_decision", ""),
            reviewer=data.get("reviewer", ""),
            review_comment=data.get("review_comment", ""),
            auto_approved=data.get("auto_approved", "false").lower() == "true",
            auto_merged=data.get("auto_merged", "false").lower() == "true",
            rolled_back=data.get("rolled_back", "false").lower() == "true",
            rolled_back_at=data.get("rolled_back_at", ""),
            rollback_reason=data.get("rollback_reason", ""),
            rollback_sha=data.get("rollback_sha", ""),
            ci_passed=data.get("ci_passed", "false").lower() == "true",
            ci_failures=json.loads(data.get("ci_failures", "[]")),
            opened_by_agent=data.get("opened_by_agent", ""),
            merged_by_agent=data.get("merged_by_agent", ""),
            lines_added=int(data.get("lines_added", "0")),
            lines_deleted=int(data.get("lines_deleted", "0")),
            files_changed=int(data.get("files_changed", "0")),
            test_coverage=float(data.get("test_coverage", "0")),
        )


@dataclass
class SuccessMetrics:
    """Aggregated success metrics for PR pipeline."""

    # Time range
    period_start: str
    period_end: str

    # Volume metrics
    total_prs: int = 0
    merged_prs: int = 0
    rejected_prs: int = 0
    rolled_back_prs: int = 0

    # Success rates
    auto_merge_success_rate: float = 0.0  # % of auto-merged PRs that stayed merged
    review_accuracy: float = 0.0  # % of reviews that were correct (not rolled back)
    overall_success_rate: float = 0.0  # % of PRs that merged successfully

    # Time metrics
    avg_time_to_merge_minutes: float = 0.0
    p95_time_to_merge_minutes: float = 0.0
    max_time_to_merge_minutes: float = 0.0

    # Auto-approval metrics
    auto_approved_count: int = 0
    auto_approved_rolled_back: int = 0
    auto_approved_success_rate: float = 0.0

    # Manual review metrics
    manual_review_count: int = 0
    manual_review_rolled_back: int = 0
    manual_review_success_rate: float = 0.0

    # False positive/negative tracking
    false_positives: int = 0  # Approved but rolled back
    false_negatives: int = 0  # Rejected but should have been approved

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_prs": self.total_prs,
            "merged_prs": self.merged_prs,
            "rejected_prs": self.rejected_prs,
            "rolled_back_prs": self.rolled_back_prs,
            "auto_merge_success_rate": self.auto_merge_success_rate,
            "review_accuracy": self.review_accuracy,
            "overall_success_rate": self.overall_success_rate,
            "avg_time_to_merge_minutes": self.avg_time_to_merge_minutes,
            "p95_time_to_merge_minutes": self.p95_time_to_merge_minutes,
            "max_time_to_merge_minutes": self.max_time_to_merge_minutes,
            "auto_approved_count": self.auto_approved_count,
            "auto_approved_rolled_back": self.auto_approved_rolled_back,
            "auto_approved_success_rate": self.auto_approved_success_rate,
            "manual_review_count": self.manual_review_count,
            "manual_review_rolled_back": self.manual_review_rolled_back,
            "manual_review_success_rate": self.manual_review_success_rate,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }


def _utc_now() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


class OutcomeTracker:
    """Tracks PR outcomes and calculates success metrics."""

    def __init__(self) -> None:
        self.host, self.port, self.db = _get_redis_config()

    def _outcome_key(self, pr_number: int) -> str:
        return f"{OUTCOME_PREFIX}:{pr_number}"

    def _metrics_key(self, date_str: str) -> str:
        return f"{METRICS_PREFIX}:daily:{date_str}"

    def _weekly_metrics_key(self, week_str: str) -> str:
        return f"{METRICS_PREFIX}:weekly:{week_str}"

    def record_outcome(self, outcome: PROutcome) -> bool:
        """Record a PR outcome in Redis."""
        outcome_key = self._outcome_key(outcome.pr_number)

        # Store outcome
        data = outcome.to_dict()
        for key, value in data.items():
            _redis_cli("HSET", outcome_key, key, str(value))

        # Set TTL (30 days)
        _redis_cli("EXPIRE", outcome_key, str(DEFAULT_TTL_SECONDS))

        # Add to outcome index
        _redis_cli(
            "SADD",
            f"{OUTCOME_PREFIX}:all",
            str(outcome.pr_number),
        )
        _redis_cli("EXPIRE", f"{OUTCOME_PREFIX}:all", str(DEFAULT_TTL_SECONDS))

        # Add to outcome type index
        _redis_cli(
            "SADD",
            f"{OUTCOME_PREFIX}:type:{outcome.outcome}",
            str(outcome.pr_number),
        )
        _redis_cli(
            "EXPIRE",
            f"{OUTCOME_PREFIX}:type:{outcome.outcome}",
            str(DEFAULT_TTL_SECONDS),
        )

        # Add to daily index
        date_str = outcome.created_at[:10]  # YYYY-MM-DD
        _redis_cli(
            "SADD",
            f"{OUTCOME_PREFIX}:date:{date_str}",
            str(outcome.pr_number),
        )
        _redis_cli(
            "EXPIRE",
            f"{OUTCOME_PREFIX}:date:{date_str}",
            str(DEFAULT_TTL_SECONDS),
        )

        return True

    def get_outcome(self, pr_number: int) -> PROutcome | None:
        """Get outcome for a specific PR."""
        outcome_key = self._outcome_key(pr_number)
        result = _redis_cli("HGETALL", outcome_key)

        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parse hash output
        lines = result.stdout.strip().split("\n")
        data: dict[str, str] = {}
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                data[lines[i]] = lines[i + 1]

        if not data:
            return None

        return PROutcome.from_dict(data)

    def record_merge(
        self,
        pr_number: int,
        story_id: str,
        branch: str,
        head_sha: str,
        opened_by_agent: str,
        merged_by_agent: str = "",
        auto_merged: bool = False,
        time_to_merge_minutes: float = 0.0,
        lines_added: int = 0,
        lines_deleted: int = 0,
        files_changed: int = 0,
    ) -> bool:
        """Record a successful merge outcome."""
        outcome = PROutcome(
            pr_number=pr_number,
            story_id=story_id,
            branch=branch,
            head_sha=head_sha,
            outcome="merged",
            merged_at=_utc_now(),
            time_to_merge_minutes=time_to_merge_minutes,
            auto_merged=auto_merged,
            opened_by_agent=opened_by_agent,
            merged_by_agent=merged_by_agent,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            files_changed=files_changed,
        )
        return self.record_outcome(outcome)

    def record_rejection(
        self,
        pr_number: int,
        story_id: str,
        branch: str,
        head_sha: str,
        opened_by_agent: str,
        reviewer: str,
        review_comment: str = "",
        rejection_reason: str = "",
    ) -> bool:
        """Record a PR rejection outcome."""
        outcome = PROutcome(
            pr_number=pr_number,
            story_id=story_id,
            branch=branch,
            head_sha=head_sha,
            outcome="rejected",
            review_decision="changes_requested",
            reviewer=reviewer,
            review_comment=review_comment,
            outcome_reason=rejection_reason,
            closed_at=_utc_now(),
            opened_by_agent=opened_by_agent,
        )
        return self.record_outcome(outcome)

    def record_declined(
        self,
        pr_number: int,
        story_id: str,
        branch: str,
        head_sha: str,
        opened_by_agent: str,
        reviewer: str,
        review_comment: str = "",
        decline_reason: str = "",
    ) -> bool:
        """Record a PR decline outcome (distinct from rejected).

        Declined means the PR was closed without merging after review,
        typically because the approach was fundamentally flawed.
        """
        outcome = PROutcome(
            pr_number=pr_number,
            story_id=story_id,
            branch=branch,
            head_sha=head_sha,
            outcome="declined",
            review_decision="declined",
            reviewer=reviewer,
            review_comment=review_comment,
            outcome_reason=decline_reason,
            closed_at=_utc_now(),
            opened_by_agent=opened_by_agent,
        )
        return self.record_outcome(outcome)

    def record_abandoned(
        self,
        pr_number: int,
        story_id: str,
        branch: str,
        head_sha: str,
        opened_by_agent: str,
        abandonment_reason: str = "",
    ) -> bool:
        """Record a PR abandonment outcome.

        Abandoned means the PR was closed without merging and without
        formal review, typically due to inactivity or agent giving up.
        """
        outcome = PROutcome(
            pr_number=pr_number,
            story_id=story_id,
            branch=branch,
            head_sha=head_sha,
            outcome="abandoned",
            outcome_reason=abandonment_reason,
            closed_at=_utc_now(),
            opened_by_agent=opened_by_agent,
        )
        return self.record_outcome(outcome)

    def record_escalated(
        self,
        pr_number: int,
        story_id: str,
        branch: str,
        head_sha: str,
        opened_by_agent: str,
        escalated_to: str,
        escalation_reason: str = "",
    ) -> bool:
        """Record a PR escalation outcome.

        Escalated means the PR was forwarded to human review
        due to complexity, risk, or system limitations.
        """
        outcome = PROutcome(
            pr_number=pr_number,
            story_id=story_id,
            branch=branch,
            head_sha=head_sha,
            outcome="escalated",
            outcome_reason=escalation_reason,
            closed_at=_utc_now(),
            opened_by_agent=opened_by_agent,
            reviewer=escalated_to,
        )
        return self.record_outcome(outcome)

    def record_rollback(
        self,
        pr_number: int,
        rollback_reason: str,
        rollback_sha: str = "",
    ) -> bool:
        """Record a rollback for a previously merged PR."""
        # Get existing outcome
        outcome = self.get_outcome(pr_number)
        if not outcome:
            return False

        # Update with rollback info
        outcome.rolled_back = True
        outcome.rolled_back_at = _utc_now()
        outcome.rollback_reason = rollback_reason
        outcome.rollback_sha = rollback_sha

        # Re-store
        return self.record_outcome(outcome)

    def calculate_metrics(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> SuccessMetrics:
        """Calculate success metrics for a time period."""
        if end_date is None:
            end_date = datetime.now(UTC)
        if start_date is None:
            start_date = end_date - timedelta(days=7)

        # Get all outcomes in date range
        outcomes = self._get_outcomes_in_range(start_date, end_date)

        metrics = SuccessMetrics(
            period_start=start_date.isoformat().replace("+00:00", "Z"),
            period_end=end_date.isoformat().replace("+00:00", "Z"),
            total_prs=len(outcomes),
        )

        if not outcomes:
            return metrics

        # Calculate metrics
        merge_times = []
        auto_approved_total = 0
        auto_approved_rolled = 0
        manual_review_total = 0
        manual_review_rolled = 0

        for outcome in outcomes:
            if outcome.outcome == "merged":
                metrics.merged_prs += 1
                if outcome.time_to_merge_minutes > 0:
                    merge_times.append(outcome.time_to_merge_minutes)

            elif outcome.outcome == "rejected":
                metrics.rejected_prs += 1

            elif outcome.outcome == "declined":
                # Declined is tracked separately but counted in rejected for metrics
                pass

            elif outcome.outcome == "abandoned":
                # Abandoned PRs are tracked but not counted as rejected
                pass

            elif outcome.outcome == "escalated":
                # Escalated PRs are tracked but handled separately
                pass

            if outcome.rolled_back:
                metrics.rolled_back_prs += 1
                if outcome.auto_approved:
                    auto_approved_rolled += 1
                else:
                    manual_review_rolled += 1

            if outcome.auto_approved:
                auto_approved_total += 1
            else:
                manual_review_total += 1

        # Calculate success rates
        if metrics.merged_prs > 0:
            stayed_merged = metrics.merged_prs - metrics.rolled_back_prs
            metrics.auto_merge_success_rate = (stayed_merged / metrics.merged_prs) * 100
            metrics.review_accuracy = (stayed_merged / metrics.merged_prs) * 100

        if metrics.total_prs > 0:
            metrics.overall_success_rate = (
                metrics.merged_prs / metrics.total_prs
            ) * 100

        # Time metrics
        if merge_times:
            metrics.avg_time_to_merge_minutes = sum(merge_times) / len(merge_times)
            metrics.max_time_to_merge_minutes = max(merge_times)
            # P95 calculation
            sorted_times = sorted(merge_times)
            p95_idx = int(len(sorted_times) * 0.95)
            metrics.p95_time_to_merge_minutes = sorted_times[
                min(p95_idx, len(sorted_times) - 1)
            ]

        # Auto-approval metrics
        metrics.auto_approved_count = auto_approved_total
        metrics.auto_approved_rolled_back = auto_approved_rolled
        if auto_approved_total > 0:
            metrics.auto_approved_success_rate = (
                (auto_approved_total - auto_approved_rolled) / auto_approved_total
            ) * 100

        # Manual review metrics
        metrics.manual_review_count = manual_review_total
        metrics.manual_review_rolled_back = manual_review_rolled
        if manual_review_total > 0:
            metrics.manual_review_success_rate = (
                (manual_review_total - manual_review_rolled) / manual_review_total
            ) * 100

        # False positive/negative tracking
        metrics.false_positives = metrics.rolled_back_prs  # Approved but rolled back
        # False negatives would require tracking rejected PRs that were later merged
        # This is a simplified calculation

        return metrics

    def _get_outcomes_in_range(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PROutcome]:
        """Get all outcomes within a date range."""
        outcomes = []

        # Iterate through each day in range
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            result = _redis_cli(
                "SMEMBERS",
                f"{OUTCOME_PREFIX}:date:{date_str}",
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        try:
                            pr_number = int(line)
                            outcome = self.get_outcome(pr_number)
                            if outcome:
                                outcomes.append(outcome)
                        except ValueError:
                            continue

            current += timedelta(days=1)

        return outcomes

    def store_daily_metrics(self, date: datetime | None = None) -> bool:
        """Calculate and store metrics for a specific day."""
        if date is None:
            date = datetime.now(UTC)

        # Calculate for the day
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        metrics = self.calculate_metrics(start, end)
        date_str = date.strftime("%Y-%m-%d")
        metrics_key = self._metrics_key(date_str)

        # Store metrics
        data = metrics.to_dict()
        for key, value in data.items():
            _redis_cli("HSET", metrics_key, key, str(value))

        # Set TTL
        _redis_cli("EXPIRE", metrics_key, str(DEFAULT_TTL_SECONDS))

        # Add to metrics index
        _redis_cli("SADD", f"{METRICS_PREFIX}:dates", date_str)
        _redis_cli("EXPIRE", f"{METRICS_PREFIX}:dates", str(DEFAULT_TTL_SECONDS))

        return True

    def get_daily_metrics(self, date_str: str) -> SuccessMetrics | None:
        """Get stored metrics for a specific day."""
        metrics_key = self._metrics_key(date_str)
        result = _redis_cli("HGETALL", metrics_key)

        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parse hash output
        lines = result.stdout.strip().split("\n")
        data: dict[str, str] = {}
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                data[lines[i]] = lines[i + 1]

        if not data:
            return None

        return SuccessMetrics(
            period_start=data.get("period_start", ""),
            period_end=data.get("period_end", ""),
            total_prs=int(data.get("total_prs", "0")),
            merged_prs=int(data.get("merged_prs", "0")),
            rejected_prs=int(data.get("rejected_prs", "0")),
            rolled_back_prs=int(data.get("rolled_back_prs", "0")),
            auto_merge_success_rate=float(data.get("auto_merge_success_rate", "0")),
            review_accuracy=float(data.get("review_accuracy", "0")),
            overall_success_rate=float(data.get("overall_success_rate", "0")),
            avg_time_to_merge_minutes=float(data.get("avg_time_to_merge_minutes", "0")),
            p95_time_to_merge_minutes=float(data.get("p95_time_to_merge_minutes", "0")),
            max_time_to_merge_minutes=float(data.get("max_time_to_merge_minutes", "0")),
            auto_approved_count=int(data.get("auto_approved_count", "0")),
            auto_approved_rolled_back=int(data.get("auto_approved_rolled_back", "0")),
            auto_approved_success_rate=float(
                data.get("auto_approved_success_rate", "0")
            ),
            manual_review_count=int(data.get("manual_review_count", "0")),
            manual_review_rolled_back=int(data.get("manual_review_rolled_back", "0")),
            manual_review_success_rate=float(
                data.get("manual_review_success_rate", "0")
            ),
            false_positives=int(data.get("false_positives", "0")),
            false_negatives=int(data.get("false_negatives", "0")),
        )

    def get_metrics_history(
        self,
        days: int = 30,
    ) -> list[SuccessMetrics]:
        """Get metrics history for the last N days."""
        history = []
        end_date = datetime.now(UTC)

        for i in range(days):
            date = end_date - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            metrics = self.get_daily_metrics(date_str)
            if metrics:
                history.append(metrics)

        return list(reversed(history))


def main() -> int:
    """CLI for outcome tracking."""
    import argparse

    p = argparse.ArgumentParser(description="PR Outcome Tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Record merge
    merge = sub.add_parser("record-merge", help="Record a merge outcome")
    merge.add_argument("--pr-number", type=int, required=True)
    merge.add_argument("--story-id", required=True)
    merge.add_argument("--branch", required=True)
    merge.add_argument("--head-sha", required=True)
    merge.add_argument("--opened-by", required=True)
    merge.add_argument("--merged-by", default="")
    merge.add_argument("--auto-merged", action="store_true")
    merge.add_argument("--time-to-merge-min", type=float, default=0.0)

    # Record rejection
    reject = sub.add_parser("record-rejection", help="Record a rejection outcome")
    reject.add_argument("--pr-number", type=int, required=True)
    reject.add_argument("--story-id", required=True)
    reject.add_argument("--branch", required=True)
    reject.add_argument("--head-sha", required=True)
    reject.add_argument("--opened-by", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", default="")

    # Record rollback
    rollback = sub.add_parser("record-rollback", help="Record a rollback")
    rollback.add_argument("--pr-number", type=int, required=True)
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--rollback-sha", default="")

    # Get outcome
    get = sub.add_parser("get", help="Get outcome for a PR")
    get.add_argument("--pr-number", type=int, required=True)

    # Calculate metrics
    metrics = sub.add_parser("metrics", help="Calculate metrics for a period")
    metrics.add_argument("--days", type=int, default=7)

    # Store daily metrics
    sub.add_parser("store-daily", help="Store metrics for today")

    # Get history
    history = sub.add_parser("history", help="Get metrics history")
    history.add_argument("--days", type=int, default=30)

    args = p.parse_args()

    tracker = OutcomeTracker()

    if args.cmd == "record-merge":
        if tracker.record_merge(
            pr_number=args.pr_number,
            story_id=args.story_id,
            branch=args.branch,
            head_sha=args.head_sha,
            opened_by_agent=args.opened_by,
            merged_by_agent=args.merged_by,
            auto_merged=args.auto_merged,
            time_to_merge_minutes=args.time_to_merge_min,
        ):
            print(f"Recorded merge for PR #{args.pr_number}")
            return 0
        else:
            print(f"Failed to record merge for PR #{args.pr_number}", file=sys.stderr)
            return 1

    elif args.cmd == "record-rejection":
        if tracker.record_rejection(
            pr_number=args.pr_number,
            story_id=args.story_id,
            branch=args.branch,
            head_sha=args.head_sha,
            opened_by_agent=args.opened_by,
            reviewer=args.reviewer,
            rejection_reason=args.reason,
        ):
            print(f"Recorded rejection for PR #{args.pr_number}")
            return 0
        else:
            print(
                f"Failed to record rejection for PR #{args.pr_number}", file=sys.stderr
            )
            return 1

    elif args.cmd == "record-rollback":
        if tracker.record_rollback(
            pr_number=args.pr_number,
            rollback_reason=args.reason,
            rollback_sha=args.rollback_sha,
        ):
            print(f"Recorded rollback for PR #{args.pr_number}")
            return 0
        else:
            print(
                f"Failed to record rollback for PR #{args.pr_number}", file=sys.stderr
            )
            return 1

    elif args.cmd == "get":
        outcome = tracker.get_outcome(args.pr_number)
        if outcome:
            print(json.dumps(outcome.to_dict(), indent=2))
            return 0
        else:
            print(f"Outcome for PR #{args.pr_number} not found", file=sys.stderr)
            return 1

    elif args.cmd == "metrics":
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=args.days)
        m = tracker.calculate_metrics(start_date, end_date)
        print(json.dumps(m.to_dict(), indent=2))
        return 0

    elif args.cmd == "store-daily":
        if tracker.store_daily_metrics():
            print("Stored daily metrics")
            return 0
        else:
            print("Failed to store daily metrics", file=sys.stderr)
            return 1

    elif args.cmd == "history":
        history_metrics = tracker.get_metrics_history(args.days)
        print(json.dumps([m.to_dict() for m in history_metrics], indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
