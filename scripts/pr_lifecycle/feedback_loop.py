#!/usr/bin/env python3
"""Feedback Loop - Analyzes PR outcomes and generates improvement suggestions.

This module provides:
- Analysis of outcome patterns
- Automatic rule adjustment suggestions
- Weekly feedback reports
- Export to InfluxDB for Grafana dashboards
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Import outcome tracker (must be before bootstrap for path setup)
from outcome_tracker import OutcomeTracker, SuccessMetrics

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap

# Bootstrap environment first
bootstrap(load_env=True)

# Redis key prefixes
FEEDBACK_PREFIX = "bmad:chiseai:pr:feedback"
RULE_ADJUSTMENT_PREFIX = "bmad:chiseai:pr:rule_adjustment"
REPORT_PREFIX = "bmad:chiseai:pr:report"

# Default TTL (90 days for reports)
REPORT_TTL_SECONDS = 7776000

# InfluxDB configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "chiseai")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "pr_metrics")

# Discord webhook for reports
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


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
    return subprocess.run(
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


@dataclass
class RuleAdjustmentSuggestion:
    """Represents a suggested rule adjustment based on feedback."""

    suggestion_id: str
    created_at: str
    rule_type: str  # auto_approval, merge_criteria, review_threshold
    current_value: str
    suggested_value: str
    confidence: float  # 0-100
    rationale: str
    supporting_evidence: dict[str, Any]
    applied: bool = False
    applied_at: str = ""
    applied_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "created_at": self.created_at,
            "rule_type": self.rule_type,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "confidence": str(self.confidence),
            "rationale": self.rationale,
            "supporting_evidence": json.dumps(self.supporting_evidence),
            "applied": "true" if self.applied else "false",
            "applied_at": self.applied_at,
            "applied_by": self.applied_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> RuleAdjustmentSuggestion:
        return cls(
            suggestion_id=data.get("suggestion_id", ""),
            created_at=data.get("created_at", ""),
            rule_type=data.get("rule_type", ""),
            current_value=data.get("current_value", ""),
            suggested_value=data.get("suggested_value", ""),
            confidence=float(data.get("confidence", "0")),
            rationale=data.get("rationale", ""),
            supporting_evidence=json.loads(data.get("supporting_evidence", "{}")),
            applied=data.get("applied", "false").lower() == "true",
            applied_at=data.get("applied_at", ""),
            applied_by=data.get("applied_by", ""),
        )


@dataclass
class WeeklyReport:
    """Represents a weekly feedback report."""

    report_id: str
    week_start: str
    week_end: str
    generated_at: str

    # Summary metrics
    total_prs: int
    merged_prs: int
    rejected_prs: int
    rolled_back_prs: int

    # Success rates
    auto_merge_success_rate: float
    review_accuracy: float
    overall_success_rate: float

    # Time metrics
    avg_time_to_merge_minutes: float
    p95_time_to_merge_minutes: float

    # Trends (vs previous week)
    success_rate_trend: float  # percentage point change
    time_to_merge_trend: float  # percentage change

    # Rule adjustment suggestions
    suggestions: list[RuleAdjustmentSuggestion]

    # Key insights
    insights: list[str]

    # Action items
    action_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "generated_at": self.generated_at,
            "total_prs": self.total_prs,
            "merged_prs": self.merged_prs,
            "rejected_prs": self.rejected_prs,
            "rolled_back_prs": self.rolled_back_prs,
            "auto_merge_success_rate": self.auto_merge_success_rate,
            "review_accuracy": self.review_accuracy,
            "overall_success_rate": self.overall_success_rate,
            "avg_time_to_merge_minutes": self.avg_time_to_merge_minutes,
            "p95_time_to_merge_minutes": self.p95_time_to_merge_minutes,
            "success_rate_trend": self.success_rate_trend,
            "time_to_merge_trend": self.time_to_merge_trend,
            "suggestions": json.dumps([s.to_dict() for s in self.suggestions]),
            "insights": json.dumps(self.insights),
            "action_items": json.dumps(self.action_items),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> WeeklyReport:
        return cls(
            report_id=data.get("report_id", ""),
            week_start=data.get("week_start", ""),
            week_end=data.get("week_end", ""),
            generated_at=data.get("generated_at", ""),
            total_prs=int(data.get("total_prs", "0")),
            merged_prs=int(data.get("merged_prs", "0")),
            rejected_prs=int(data.get("rejected_prs", "0")),
            rolled_back_prs=int(data.get("rolled_back_prs", "0")),
            auto_merge_success_rate=float(data.get("auto_merge_success_rate", "0")),
            review_accuracy=float(data.get("review_accuracy", "0")),
            overall_success_rate=float(data.get("overall_success_rate", "0")),
            avg_time_to_merge_minutes=float(data.get("avg_time_to_merge_minutes", "0")),
            p95_time_to_merge_minutes=float(data.get("p95_time_to_merge_minutes", "0")),
            success_rate_trend=float(data.get("success_rate_trend", "0")),
            time_to_merge_trend=float(data.get("time_to_merge_trend", "0")),
            suggestions=[
                RuleAdjustmentSuggestion.from_dict(s)
                for s in json.loads(data.get("suggestions", "[]"))
            ],
            insights=json.loads(data.get("insights", "[]")),
            action_items=json.loads(data.get("action_items", "[]")),
        )


@dataclass
class AgentFeedback:
    """Feedback sent to agents when PRs are declined."""

    pr_number: int
    story_id: str
    agent_name: str
    feedback_id: str
    created_at: str
    decline_reason: str
    specific_issues: list[str]
    suggested_fixes: list[str]
    retry_eligible: bool
    retry_conditions: list[str]
    documentation_links: list[str]
    feedback_latency_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_number": str(self.pr_number),
            "story_id": self.story_id,
            "agent_name": self.agent_name,
            "feedback_id": self.feedback_id,
            "created_at": self.created_at,
            "decline_reason": self.decline_reason,
            "specific_issues": json.dumps(self.specific_issues),
            "suggested_fixes": json.dumps(self.suggested_fixes),
            "retry_eligible": "true" if self.retry_eligible else "false",
            "retry_conditions": json.dumps(self.retry_conditions),
            "documentation_links": json.dumps(self.documentation_links),
            "feedback_latency_seconds": str(self.feedback_latency_seconds),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> AgentFeedback:
        return cls(
            pr_number=int(data.get("pr_number", "0")),
            story_id=data.get("story_id", ""),
            agent_name=data.get("agent_name", ""),
            feedback_id=data.get("feedback_id", ""),
            created_at=data.get("created_at", ""),
            decline_reason=data.get("decline_reason", ""),
            specific_issues=json.loads(data.get("specific_issues", "[]")),
            suggested_fixes=json.loads(data.get("suggested_fixes", "[]")),
            retry_eligible=data.get("retry_eligible", "false").lower() == "true",
            retry_conditions=json.loads(data.get("retry_conditions", "[]")),
            documentation_links=json.loads(data.get("documentation_links", "[]")),
            feedback_latency_seconds=float(data.get("feedback_latency_seconds", "0")),
        )


@dataclass
class MonthlyReport:
    """Monthly feedback report with review accuracy and agent performance."""

    report_id: str
    month_start: str
    month_end: str
    generated_at: str

    # Volume metrics
    total_prs: int = 0
    merged_prs: int = 0
    declined_prs: int = 0
    rejected_prs: int = 0
    abandoned_prs: int = 0
    escalated_prs: int = 0

    # Review accuracy metrics
    review_accuracy: float = 0.0
    auto_merge_success_rate: float = 0.0
    overall_success_rate: float = 0.0
    false_positive_rate: float = 0.0

    # Agent performance
    agent_performance: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Time metrics
    avg_time_to_merge_minutes: float = 0.0
    p95_time_to_merge_minutes: float = 0.0

    # Retry metrics
    total_retries: int = 0
    successful_retries: int = 0
    retry_success_rate: float = 0.0

    # Feedback metrics
    avg_feedback_latency_seconds: float = 0.0
    feedbacks_sent: int = 0

    # Insights and recommendations
    insights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "month_start": self.month_start,
            "month_end": self.month_end,
            "generated_at": self.generated_at,
            "total_prs": self.total_prs,
            "merged_prs": self.merged_prs,
            "declined_prs": self.declined_prs,
            "rejected_prs": self.rejected_prs,
            "abandoned_prs": self.abandoned_prs,
            "escalated_prs": self.escalated_prs,
            "review_accuracy": self.review_accuracy,
            "auto_merge_success_rate": self.auto_merge_success_rate,
            "overall_success_rate": self.overall_success_rate,
            "false_positive_rate": self.false_positive_rate,
            "agent_performance": json.dumps(self.agent_performance),
            "avg_time_to_merge_minutes": self.avg_time_to_merge_minutes,
            "p95_time_to_merge_minutes": self.p95_time_to_merge_minutes,
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
            "retry_success_rate": self.retry_success_rate,
            "avg_feedback_latency_seconds": self.avg_feedback_latency_seconds,
            "feedbacks_sent": self.feedbacks_sent,
            "insights": json.dumps(self.insights),
            "recommendations": json.dumps(self.recommendations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> MonthlyReport:
        return cls(
            report_id=data.get("report_id", ""),
            month_start=data.get("month_start", ""),
            month_end=data.get("month_end", ""),
            generated_at=data.get("generated_at", ""),
            total_prs=int(data.get("total_prs", "0")),
            merged_prs=int(data.get("merged_prs", "0")),
            declined_prs=int(data.get("declined_prs", "0")),
            rejected_prs=int(data.get("rejected_prs", "0")),
            abandoned_prs=int(data.get("abandoned_prs", "0")),
            escalated_prs=int(data.get("escalated_prs", "0")),
            review_accuracy=float(data.get("review_accuracy", "0")),
            auto_merge_success_rate=float(data.get("auto_merge_success_rate", "0")),
            overall_success_rate=float(data.get("overall_success_rate", "0")),
            false_positive_rate=float(data.get("false_positive_rate", "0")),
            agent_performance=json.loads(data.get("agent_performance", "{}")),
            avg_time_to_merge_minutes=float(data.get("avg_time_to_merge_minutes", "0")),
            p95_time_to_merge_minutes=float(data.get("p95_time_to_merge_minutes", "0")),
            total_retries=int(data.get("total_retries", "0")),
            successful_retries=int(data.get("successful_retries", "0")),
            retry_success_rate=float(data.get("retry_success_rate", "0")),
            avg_feedback_latency_seconds=float(
                data.get("avg_feedback_latency_seconds", "0")
            ),
            feedbacks_sent=int(data.get("feedbacks_sent", "0")),
            insights=json.loads(data.get("insights", "[]")),
            recommendations=json.loads(data.get("recommendations", "[]")),
        )


class FeedbackLoop:
    """Analyzes PR outcomes and generates feedback."""

    def __init__(self) -> None:
        self.tracker = OutcomeTracker()
        self.host, self.port, self.db = _get_redis_config()

    def _suggestion_key(self, suggestion_id: str) -> str:
        return f"{RULE_ADJUSTMENT_PREFIX}:{suggestion_id}"

    def _report_key(self, report_id: str) -> str:
        return f"{REPORT_PREFIX}:{report_id}"

    def _feedback_key(self, feedback_id: str) -> str:
        return f"{FEEDBACK_PREFIX}:agent:{feedback_id}"

    def _monthly_report_key(self, report_id: str) -> str:
        return f"{REPORT_PREFIX}:monthly:{report_id}"

    def send_agent_feedback(
        self,
        pr_number: int,
        story_id: str,
        agent_name: str,
        decline_reason: str,
        specific_issues: list[str],
        suggested_fixes: list[str],
        retry_eligible: bool = True,
        retry_conditions: list[str] | None = None,
        documentation_links: list[str] | None = None,
        decline_timestamp: str = "",
    ) -> AgentFeedback | None:
        """Send actionable feedback to an agent via Redis when PR is declined.

        Args:
            pr_number: The PR number
            story_id: The story ID
            agent_name: Name of the agent who opened the PR
            decline_reason: High-level reason for decline
            specific_issues: List of specific issues found
            suggested_fixes: List of suggested fixes
            retry_eligible: Whether the PR can be retried
            retry_conditions: Conditions for retry eligibility
            documentation_links: Links to relevant documentation
            decline_timestamp: ISO timestamp of when PR was declined

        Returns:
            AgentFeedback if successful, None otherwise
        """
        feedback_id = f"feedback_{pr_number}_{_utc_now()}"
        created_at = _utc_now()

        # Calculate feedback latency
        feedback_latency_seconds = 0.0
        if decline_timestamp:
            try:
                declined = datetime.fromisoformat(
                    decline_timestamp.replace("Z", "+00:00")
                )
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                feedback_latency_seconds = (created - declined).total_seconds()
            except (ValueError, TypeError):
                pass

        feedback = AgentFeedback(
            pr_number=pr_number,
            story_id=story_id,
            agent_name=agent_name,
            feedback_id=feedback_id,
            created_at=created_at,
            decline_reason=decline_reason,
            specific_issues=specific_issues,
            suggested_fixes=suggested_fixes,
            retry_eligible=retry_eligible,
            retry_conditions=retry_conditions or [],
            documentation_links=documentation_links or [],
            feedback_latency_seconds=feedback_latency_seconds,
        )

        # Store in Redis
        self._store_agent_feedback(feedback)

        # Publish to agent's feedback channel
        self._publish_agent_feedback(feedback)

        return feedback

    def _store_agent_feedback(self, feedback: AgentFeedback) -> None:
        """Store agent feedback in Redis."""
        key = self._feedback_key(feedback.feedback_id)
        data = feedback.to_dict()

        for field_name, value in data.items():
            _redis_cli("HSET", key, field_name, str(value))

        _redis_cli("EXPIRE", key, str(REPORT_TTL_SECONDS))

        # Add to agent's feedback index
        _redis_cli(
            "LPUSH",
            f"{FEEDBACK_PREFIX}:agent:{feedback.agent_name}:feedbacks",
            feedback.feedback_id,
        )
        _redis_cli(
            "EXPIRE",
            f"{FEEDBACK_PREFIX}:agent:{feedback.agent_name}:feedbacks",
            str(REPORT_TTL_SECONDS),
        )

        # Add to PR's feedback index
        _redis_cli(
            "SADD",
            f"{FEEDBACK_PREFIX}:pr:{feedback.pr_number}",
            feedback.feedback_id,
        )
        _redis_cli(
            "EXPIRE",
            f"{FEEDBACK_PREFIX}:pr:{feedback.pr_number}",
            str(REPORT_TTL_SECONDS),
        )

    def _publish_agent_feedback(self, feedback: AgentFeedback) -> None:
        """Publish feedback to Redis pub/sub for real-time notification."""
        event = {
            "type": "agent_feedback",
            "feedback_id": feedback.feedback_id,
            "pr_number": feedback.pr_number,
            "story_id": feedback.story_id,
            "agent_name": feedback.agent_name,
            "retry_eligible": feedback.retry_eligible,
            "timestamp": feedback.created_at,
        }
        _redis_cli(
            "PUBLISH",
            f"{FEEDBACK_PREFIX}:channel:{feedback.agent_name}",
            json.dumps(event),
        )

    def get_agent_feedback(self, feedback_id: str) -> AgentFeedback | None:
        """Retrieve agent feedback by ID."""
        key = self._feedback_key(feedback_id)
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

        return AgentFeedback.from_dict(data)

    def get_agent_feedbacks(
        self, agent_name: str, limit: int = 10
    ) -> list[AgentFeedback]:
        """Get feedback history for an agent."""
        result = _redis_cli(
            "LRANGE",
            f"{FEEDBACK_PREFIX}:agent:{agent_name}:feedbacks",
            "0",
            str(limit - 1),
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        feedbacks = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                feedback = self.get_agent_feedback(line)
                if feedback:
                    feedbacks.append(feedback)

        return feedbacks

    def analyze_patterns(
        self,
        days: int = 14,
    ) -> dict[str, Any]:
        """Analyze outcome patterns over a period."""
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        metrics = self.tracker.calculate_metrics(start_date, end_date)

        patterns = {
            "period_days": days,
            "analyzed_at": _utc_now(),
            "total_prs": metrics.total_prs,
            "success_rate": metrics.overall_success_rate,
            "auto_approval_rate": (
                (metrics.auto_approved_count / metrics.total_prs * 100)
                if metrics.total_prs > 0
                else 0
            ),
            "rollback_rate": (
                (metrics.rolled_back_prs / metrics.merged_prs * 100)
                if metrics.merged_prs > 0
                else 0
            ),
            "false_positive_rate": (
                (metrics.false_positives / metrics.merged_prs * 100)
                if metrics.merged_prs > 0
                else 0
            ),
            "avg_time_to_merge": metrics.avg_time_to_merge_minutes,
            "concerns": [],
            "positives": [],
        }

        # Identify concerns
        if metrics.auto_approved_success_rate < 90:
            patterns["concerns"].append(
                f"Auto-approval success rate is {metrics.auto_approved_success_rate:.1f}%, "
                "below 90% threshold"
            )

        if metrics.rolled_back_prs > 0:
            patterns["concerns"].append(
                f"{metrics.rolled_back_prs} PRs were rolled back, "
                f"indicating {metrics.false_positives} false positive(s)"
            )

        if metrics.avg_time_to_merge_minutes > 60:
            patterns["concerns"].append(
                f"Average time to merge is {metrics.avg_time_to_merge_minutes:.1f} minutes, "
                "above 60 minute target"
            )

        # Identify positives
        if metrics.overall_success_rate >= 95:
            patterns["positives"].append(
                f"Overall success rate is {metrics.overall_success_rate:.1f}%, "
                "exceeding 95% target"
            )

        if metrics.auto_approved_success_rate >= 95:
            patterns["positives"].append(
                f"Auto-approval success rate is {metrics.auto_approved_success_rate:.1f}%, "
                "exceeding 95% target"
            )

        return patterns

    def generate_rule_adjustments(
        self,
        days: int = 14,
    ) -> list[RuleAdjustmentSuggestion]:
        """Generate rule adjustment suggestions based on feedback."""
        suggestions = []

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)
        metrics = self.tracker.calculate_metrics(start_date, end_date)

        # Check auto-approval threshold
        if metrics.auto_approved_count > 0:
            rollback_rate = (
                metrics.auto_approved_rolled_back / metrics.auto_approved_count
            )

            if rollback_rate > 0.1:  # More than 10% rollback rate
                # Suggest tightening auto-approval criteria
                suggestions.append(
                    RuleAdjustmentSuggestion(
                        suggestion_id=f"suggestion_{_utc_now()}_001",
                        created_at=_utc_now(),
                        rule_type="auto_approval",
                        current_value="current_threshold",
                        suggested_value="increase_confidence_threshold",
                        confidence=min(rollback_rate * 100, 95),
                        rationale=(
                            f"Auto-approval rollback rate is {rollback_rate * 100:.1f}%. "
                            "Consider increasing confidence threshold to reduce false positives."
                        ),
                        supporting_evidence={
                            "auto_approved_count": metrics.auto_approved_count,
                            "rolled_back_count": metrics.auto_approved_rolled_back,
                            "rollback_rate": rollback_rate,
                        },
                    )
                )

            elif rollback_rate < 0.02 and metrics.auto_approved_count >= 10:
                # Very low rollback rate, could potentially auto-approve more
                suggestions.append(
                    RuleAdjustmentSuggestion(
                        suggestion_id=f"suggestion_{_utc_now()}_002",
                        created_at=_utc_now(),
                        rule_type="auto_approval",
                        current_value="current_threshold",
                        suggested_value="decrease_confidence_threshold",
                        confidence=70,
                        rationale=(
                            f"Auto-approval rollback rate is only {rollback_rate * 100:.1f}%. "
                            "Consider lowering confidence threshold to auto-approve more PRs."
                        ),
                        supporting_evidence={
                            "auto_approved_count": metrics.auto_approved_count,
                            "rolled_back_count": metrics.auto_approved_rolled_back,
                            "rollback_rate": rollback_rate,
                        },
                    )
                )

        # Check review accuracy
        if metrics.manual_review_count > 0:
            manual_rollback_rate = (
                metrics.manual_review_rolled_back / metrics.manual_review_count
            )

            if manual_rollback_rate > 0.05:
                suggestions.append(
                    RuleAdjustmentSuggestion(
                        suggestion_id=f"suggestion_{_utc_now()}_003",
                        created_at=_utc_now(),
                        rule_type="review_threshold",
                        current_value="current_review_criteria",
                        suggested_value="enhance_review_checklist",
                        confidence=min(manual_rollback_rate * 200, 90),
                        rationale=(
                            f"Manual review rollback rate is {manual_rollback_rate * 100:.1f}%. "
                            "Consider enhancing review checklist or training."
                        ),
                        supporting_evidence={
                            "manual_review_count": metrics.manual_review_count,
                            "rolled_back_count": metrics.manual_review_rolled_back,
                            "rollback_rate": manual_rollback_rate,
                        },
                    )
                )

        # Check time to merge
        if metrics.avg_time_to_merge_minutes > 120:  # More than 2 hours
            suggestions.append(
                RuleAdjustmentSuggestion(
                    suggestion_id=f"suggestion_{_utc_now()}_004",
                    created_at=_utc_now(),
                    rule_type="merge_criteria",
                    current_value="current_merge_requirements",
                    suggested_value="optimize_ci_pipeline",
                    confidence=80,
                    rationale=(
                        f"Average time to merge is {metrics.avg_time_to_merge_minutes:.1f} minutes. "
                        "Consider optimizing CI pipeline or reducing required checks."
                    ),
                    supporting_evidence={
                        "avg_time_to_merge": metrics.avg_time_to_merge_minutes,
                        "p95_time_to_merge": metrics.p95_time_to_merge_minutes,
                    },
                )
            )

        # Store suggestions
        for suggestion in suggestions:
            self._store_suggestion(suggestion)

        return suggestions

    def _store_suggestion(self, suggestion: RuleAdjustmentSuggestion) -> None:
        """Store a suggestion in Redis."""
        key = self._suggestion_key(suggestion.suggestion_id)
        data = suggestion.to_dict()

        for field_name, value in data.items():
            _redis_cli("HSET", key, field_name, str(value))

        _redis_cli("EXPIRE", key, str(REPORT_TTL_SECONDS))

        # Add to pending suggestions index
        if not suggestion.applied:
            _redis_cli(
                "SADD", f"{RULE_ADJUSTMENT_PREFIX}:pending", suggestion.suggestion_id
            )
            _redis_cli(
                "EXPIRE", f"{RULE_ADJUSTMENT_PREFIX}:pending", str(REPORT_TTL_SECONDS)
            )

    def get_pending_suggestions(self) -> list[RuleAdjustmentSuggestion]:
        """Get all pending rule adjustment suggestions."""
        result = _redis_cli("SMEMBERS", f"{RULE_ADJUSTMENT_PREFIX}:pending")

        if result.returncode != 0 or not result.stdout.strip():
            return []

        suggestions = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                key = self._suggestion_key(line)
                data_result = _redis_cli("HGETALL", key)

                if data_result.returncode == 0 and data_result.stdout.strip():
                    lines = data_result.stdout.strip().split("\n")
                    data: dict[str, str] = {}
                    for i in range(0, len(lines), 2):
                        if i + 1 < len(lines):
                            data[lines[i]] = lines[i + 1]

                    if data:
                        suggestions.append(RuleAdjustmentSuggestion.from_dict(data))

        return suggestions

    def apply_suggestion(
        self,
        suggestion_id: str,
        applied_by: str,
    ) -> bool:
        """Mark a suggestion as applied."""
        key = self._suggestion_key(suggestion_id)

        _redis_cli("HSET", key, "applied", "true")
        _redis_cli("HSET", key, "applied_at", _utc_now())
        _redis_cli("HSET", key, "applied_by", applied_by)

        # Remove from pending
        _redis_cli("SREM", f"{RULE_ADJUSTMENT_PREFIX}:pending", suggestion_id)

        return True

    def generate_weekly_report(
        self,
        week_start: datetime | None = None,
    ) -> WeeklyReport:
        """Generate a weekly feedback report."""
        if week_start is None:
            # Default to previous week
            week_start = datetime.now(UTC) - timedelta(days=7)

        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        # Get current week metrics
        current_metrics = self.tracker.calculate_metrics(week_start, week_end)

        # Get previous week metrics for comparison
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start
        prev_metrics = self.tracker.calculate_metrics(prev_week_start, prev_week_end)

        # Calculate trends
        success_rate_trend = (
            current_metrics.overall_success_rate - prev_metrics.overall_success_rate
        )
        time_to_merge_trend = 0
        if prev_metrics.avg_time_to_merge_minutes > 0:
            time_to_merge_trend = (
                (
                    current_metrics.avg_time_to_merge_minutes
                    - prev_metrics.avg_time_to_merge_minutes
                )
                / prev_metrics.avg_time_to_merge_minutes
            ) * 100

        # Generate suggestions
        suggestions = self.generate_rule_adjustments(days=7)

        # Generate insights
        insights = []
        if current_metrics.overall_success_rate >= 95:
            insights.append(
                f"Excellent week! {current_metrics.overall_success_rate:.1f}% success rate."
            )
        elif current_metrics.overall_success_rate >= 90:
            insights.append(
                f"Good week with {current_metrics.overall_success_rate:.1f}% success rate."
            )
        else:
            insights.append(
                f"Success rate at {current_metrics.overall_success_rate:.1f}%, "
                "below 90% target. Review recommended."
            )

        if current_metrics.rolled_back_prs > 0:
            insights.append(
                f"{current_metrics.rolled_back_prs} PR(s) were rolled back this week. "
                "Consider reviewing auto-approval criteria."
            )

        # Generate action items
        action_items = []
        if suggestions:
            action_items.append(
                f"Review {len(suggestions)} rule adjustment suggestion(s)"
            )

        if current_metrics.auto_approved_success_rate < 90:
            action_items.append("Investigate auto-approval false positives")

        if current_metrics.avg_time_to_merge_minutes > 120:
            action_items.append("Optimize CI pipeline to reduce time to merge")

        report = WeeklyReport(
            report_id=f"weekly_{week_start.strftime('%Y-%m-%d')}",
            week_start=week_start.isoformat().replace("+00:00", "Z"),
            week_end=week_end.isoformat().replace("+00:00", "Z"),
            generated_at=_utc_now(),
            total_prs=current_metrics.total_prs,
            merged_prs=current_metrics.merged_prs,
            rejected_prs=current_metrics.rejected_prs,
            rolled_back_prs=current_metrics.rolled_back_prs,
            auto_merge_success_rate=current_metrics.auto_merge_success_rate,
            review_accuracy=current_metrics.review_accuracy,
            overall_success_rate=current_metrics.overall_success_rate,
            avg_time_to_merge_minutes=current_metrics.avg_time_to_merge_minutes,
            p95_time_to_merge_minutes=current_metrics.p95_time_to_merge_minutes,
            success_rate_trend=success_rate_trend,
            time_to_merge_trend=time_to_merge_trend,
            suggestions=suggestions,
            insights=insights,
            action_items=action_items,
        )

        # Store report
        self._store_report(report)

        return report

    def _store_report(self, report: WeeklyReport) -> None:
        """Store a report in Redis."""
        key = self._report_key(report.report_id)
        data = report.to_dict()

        for field_name, value in data.items():
            _redis_cli("HSET", key, field_name, str(value))

        _redis_cli("EXPIRE", key, str(REPORT_TTL_SECONDS))

        # Add to reports index
        _redis_cli("SADD", f"{REPORT_PREFIX}:all", report.report_id)
        _redis_cli("EXPIRE", f"{REPORT_PREFIX}:all", str(REPORT_TTL_SECONDS))

    def generate_monthly_report(
        self,
        month_start: datetime | None = None,
    ) -> MonthlyReport:
        """Generate a monthly feedback report with review accuracy and agent performance.

        Args:
            month_start: Start of month (defaults to first day of current month)

        Returns:
            MonthlyReport with comprehensive metrics
        """
        if month_start is None:
            # Default to first day of current month
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Calculate month end
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

        # Get metrics for the month
        metrics = self.tracker.calculate_metrics(month_start, month_end)

        # Get outcomes for detailed analysis
        outcomes = self.tracker._get_outcomes_in_range(month_start, month_end)

        # Count by outcome type
        declined_count = sum(1 for o in outcomes if o.outcome == "declined")
        abandoned_count = sum(1 for o in outcomes if o.outcome == "abandoned")
        escalated_count = sum(1 for o in outcomes if o.outcome == "escalated")

        # Calculate review accuracy
        review_accuracy = 0.0
        if metrics.merged_prs > 0:
            stayed_merged = metrics.merged_prs - metrics.rolled_back_prs
            review_accuracy = (stayed_merged / metrics.merged_prs) * 100

        # Calculate false positive rate
        false_positive_rate = 0.0
        if metrics.merged_prs > 0:
            false_positive_rate = (metrics.rolled_back_prs / metrics.merged_prs) * 100

        # Calculate agent performance
        agent_stats: dict[str, dict[str, Any]] = {}
        for outcome in outcomes:
            agent = outcome.opened_by_agent
            if not agent:
                continue

            if agent not in agent_stats:
                agent_stats[agent] = {
                    "total_prs": 0,
                    "merged": 0,
                    "declined": 0,
                    "rejected": 0,
                    "abandoned": 0,
                    "escalated": 0,
                    "rolled_back": 0,
                    "success_rate": 0.0,
                }

            agent_stats[agent]["total_prs"] += 1
            if outcome.outcome == "merged":
                agent_stats[agent]["merged"] += 1
            elif outcome.outcome == "declined":
                agent_stats[agent]["declined"] += 1
            elif outcome.outcome == "rejected":
                agent_stats[agent]["rejected"] += 1
            elif outcome.outcome == "abandoned":
                agent_stats[agent]["abandoned"] += 1
            elif outcome.outcome == "escalated":
                agent_stats[agent]["escalated"] += 1

            if outcome.rolled_back:
                agent_stats[agent]["rolled_back"] += 1

        # Calculate success rates per agent
        for agent, stats in agent_stats.items():
            if stats["total_prs"] > 0:
                stats["success_rate"] = (stats["merged"] / stats["total_prs"]) * 100

        # Get retry metrics (simplified - would integrate with retry_handler)
        retry_metrics = {"total_retries": 0, "successful_retries": 0}

        # Get feedback metrics
        feedback_result = _redis_cli("KEYS", f"{FEEDBACK_PREFIX}:agent:*:feedbacks")
        feedbacks_sent = 0
        if feedback_result.returncode == 0 and feedback_result.stdout.strip():
            feedbacks_sent = len(feedback_result.stdout.strip().split("\n"))

        # Calculate average feedback latency
        avg_feedback_latency = 0.0
        # Simplified - would calculate from stored feedbacks

        # Generate insights
        insights = []
        if review_accuracy >= 95:
            insights.append(f"Excellent review accuracy: {review_accuracy:.1f}%")
        elif review_accuracy >= 90:
            insights.append(f"Good review accuracy: {review_accuracy:.1f}%")
        else:
            insights.append(f"Review accuracy below target: {review_accuracy:.1f}%")

        if metrics.rolled_back_prs > 0:
            insights.append(
                f"{metrics.rolled_back_prs} PR(s) rolled back ({false_positive_rate:.1f}% false positive rate)"
            )

        if escalated_count > 0:
            insights.append(f"{escalated_count} PR(s) escalated to human review")

        # Generate recommendations
        recommendations = []
        if false_positive_rate > 5:
            recommendations.append(
                "High false positive rate detected. Consider tightening auto-approval criteria."
            )

        if metrics.avg_time_to_merge_minutes > 120:
            recommendations.append(
                "Average time to merge exceeds 2 hours. Consider CI optimization."
            )

        # Find top performing agent
        if agent_stats:
            top_agent = max(agent_stats.items(), key=lambda x: x[1]["success_rate"])
            recommendations.append(
                f"Top performer: {top_agent[0]} with {top_agent[1]['success_rate']:.1f}% success rate"
            )

        report = MonthlyReport(
            report_id=f"monthly_{month_start.strftime('%Y-%m')}",
            month_start=month_start.isoformat().replace("+00:00", "Z"),
            month_end=month_end.isoformat().replace("+00:00", "Z"),
            generated_at=_utc_now(),
            total_prs=metrics.total_prs,
            merged_prs=metrics.merged_prs,
            declined_prs=declined_count,
            rejected_prs=metrics.rejected_prs,
            abandoned_prs=abandoned_count,
            escalated_prs=escalated_count,
            review_accuracy=review_accuracy,
            auto_merge_success_rate=metrics.auto_merge_success_rate,
            overall_success_rate=metrics.overall_success_rate,
            false_positive_rate=false_positive_rate,
            agent_performance=agent_stats,
            avg_time_to_merge_minutes=metrics.avg_time_to_merge_minutes,
            p95_time_to_merge_minutes=metrics.p95_time_to_merge_minutes,
            total_retries=retry_metrics["total_retries"],
            successful_retries=retry_metrics["successful_retries"],
            retry_success_rate=0.0,  # Would calculate from retry metrics
            avg_feedback_latency_seconds=avg_feedback_latency,
            feedbacks_sent=feedbacks_sent,
            insights=insights,
            recommendations=recommendations,
        )

        # Store report
        self._store_monthly_report(report)

        return report

    def _store_monthly_report(self, report: MonthlyReport) -> None:
        """Store a monthly report in Redis."""
        key = self._monthly_report_key(report.report_id)
        data = report.to_dict()

        for field_name, value in data.items():
            _redis_cli("HSET", key, field_name, str(value))

        _redis_cli("EXPIRE", key, str(REPORT_TTL_SECONDS))

        # Add to monthly reports index
        _redis_cli("SADD", f"{REPORT_PREFIX}:monthly:all", report.report_id)
        _redis_cli("EXPIRE", f"{REPORT_PREFIX}:monthly:all", str(REPORT_TTL_SECONDS))

    def get_monthly_report(self, report_id: str) -> MonthlyReport | None:
        """Get a stored monthly report."""
        key = self._monthly_report_key(report_id)
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

        return MonthlyReport.from_dict(data)

    def get_report(self, report_id: str) -> WeeklyReport | None:
        """Get a stored report."""
        key = self._report_key(report_id)
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

        return WeeklyReport.from_dict(data)

    def export_to_influxdb(self, metrics: SuccessMetrics) -> bool:
        """Export metrics to InfluxDB for Grafana."""
        if not INFLUXDB_URL or not INFLUXDB_TOKEN:
            print("InfluxDB not configured, skipping export", file=sys.stderr)
            return False
        # Build line protocol
        lines = [
            f"pr_metrics,period=daily total_prs={metrics.total_prs}i,merged_prs={metrics.merged_prs}i,"
            f"rejected_prs={metrics.rejected_prs}i,rolled_back_prs={metrics.rolled_back_prs}i,"
            f"auto_merge_success_rate={metrics.auto_merge_success_rate},"
            f"review_accuracy={metrics.review_accuracy},overall_success_rate={metrics.overall_success_rate},"
            f"avg_time_to_merge={metrics.avg_time_to_merge_minutes},"
            f"p95_time_to_merge={metrics.p95_time_to_merge_minutes} {int(datetime.now(UTC).timestamp() * 1e9)}",
        ]

        try:
            url = f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns"
            headers = {
                "Authorization": f"Token {INFLUXDB_TOKEN}",
                "Content-Type": "text/plain; charset=utf-8",
            }

            data = "\n".join(lines).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return True
                else:
                    print(
                        f"InfluxDB export failed: HTTP {resp.status}", file=sys.stderr
                    )
                    return False

        except Exception as e:
            print(f"InfluxDB export error: {e}", file=sys.stderr)
            return False

    def post_report_to_discord(self, report: WeeklyReport) -> bool:
        """Post a weekly report to Discord."""
        if not DISCORD_WEBHOOK_URL:
            print("Discord webhook not configured, skipping post", file=sys.stderr)
            return False

        # Build embed
        embed = {
            "title": f"📊 PR Pipeline Weekly Report ({report.week_start[:10]} to {report.week_end[:10]})",
            "color": 3447003,  # Blue
            "fields": [
                {
                    "name": "📈 Volume",
                    "value": (
                        f"Total PRs: {report.total_prs}\n"
                        f"Merged: {report.merged_prs}\n"
                        f"Rejected: {report.rejected_prs}\n"
                        f"Rolled Back: {report.rolled_back_prs}"
                    ),
                    "inline": True,
                },
                {
                    "name": "✅ Success Rates",
                    "value": (
                        f"Overall: {report.overall_success_rate:.1f}%\n"
                        f"Auto-Merge: {report.auto_merge_success_rate:.1f}%\n"
                        f"Review Accuracy: {report.review_accuracy:.1f}%"
                    ),
                    "inline": True,
                },
                {
                    "name": "⏱️ Time to Merge",
                    "value": (
                        f"Average: {report.avg_time_to_merge_minutes:.1f} min\n"
                        f"P95: {report.p95_time_to_merge_minutes:.1f} min"
                    ),
                    "inline": True,
                },
            ],
            "footer": {
                "text": f"Generated at {report.generated_at}",
            },
        }

        # Add trend indicators
        trend_emoji = "📈" if report.success_rate_trend >= 0 else "📉"
        embed["fields"].append(
            {
                "name": "📊 Trends (vs last week)",
                "value": (
                    f"{trend_emoji} Success Rate: {report.success_rate_trend:+.1f}pp\n"
                    f"⏱️ Time to Merge: {report.time_to_merge_trend:+.1f}%"
                ),
                "inline": False,
            }
        )

        # Add insights if any
        if report.insights:
            embed["fields"].append(
                {
                    "name": "💡 Key Insights",
                    "value": "\n".join(f"• {i}" for i in report.insights),
                    "inline": False,
                }
            )

        # Add action items if any
        if report.action_items:
            embed["fields"].append(
                {
                    "name": "📝 Action Items",
                    "value": "\n".join(f"• {a}" for a in report.action_items),
                    "inline": False,
                }
            )

        # Add suggestions count
        if report.suggestions:
            embed["fields"].append(
                {
                    "name": "🔧 Rule Adjustments",
                    "value": f"{len(report.suggestions)} suggestion(s) available",
                    "inline": False,
                }
            )

        payload = {
            "embeds": [embed],
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(
                DISCORD_WEBHOOK_URL,
                data=data,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 204

        except Exception as e:
            print(f"Discord post error: {e}", file=sys.stderr)
            return False

    def run_weekly_cycle(self) -> WeeklyReport:
        """Run the complete weekly feedback cycle."""
        # Generate report
        report = self.generate_weekly_report()

        # Export to InfluxDB
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)
        metrics = self.tracker.calculate_metrics(start_date, end_date)
        self.export_to_influxdb(metrics)

        # Post to Discord
        self.post_report_to_discord(report)

        return report


def main() -> int:
    """CLI for feedback loop."""
    import argparse

    p = argparse.ArgumentParser(description="PR Feedback Loop")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Analyze patterns
    analyze = sub.add_parser("analyze", help="Analyze outcome patterns")
    analyze.add_argument("--days", type=int, default=14)

    # Generate suggestions
    suggest = sub.add_parser("suggest", help="Generate rule adjustment suggestions")
    suggest.add_argument("--days", type=int, default=14)

    # Get pending suggestions
    sub.add_parser("pending", help="Get pending suggestions")

    # Apply suggestion
    apply_cmd = sub.add_parser("apply", help="Apply a suggestion")
    apply_cmd.add_argument("--suggestion-id", required=True)
    apply_cmd.add_argument("--by", required=True, help="Who is applying the suggestion")

    # Generate weekly report
    weekly = sub.add_parser("weekly", help="Generate weekly report")
    weekly.add_argument("--post-discord", action="store_true", help="Post to Discord")

    # Export to InfluxDB
    export_cmd = sub.add_parser("export", help="Export metrics to InfluxDB")
    export_cmd.add_argument("--days", type=int, default=7)

    # Run full weekly cycle
    sub.add_parser("weekly-cycle", help="Run complete weekly cycle")

    args = p.parse_args()

    feedback = FeedbackLoop()

    if args.cmd == "analyze":
        patterns = feedback.analyze_patterns(days=args.days)
        print(json.dumps(patterns, indent=2))
        return 0

    elif args.cmd == "suggest":
        suggestions = feedback.generate_rule_adjustments(days=args.days)
        print(json.dumps([s.to_dict() for s in suggestions], indent=2))
        return 0

    elif args.cmd == "pending":
        suggestions = feedback.get_pending_suggestions()
        print(json.dumps([s.to_dict() for s in suggestions], indent=2))
        return 0

    elif args.cmd == "apply":
        if feedback.apply_suggestion(args.suggestion_id, args.by):
            print(f"Applied suggestion {args.suggestion_id}")
            return 0
        else:
            print(f"Failed to apply suggestion {args.suggestion_id}", file=sys.stderr)
            return 1

    elif args.cmd == "weekly":
        report = feedback.generate_weekly_report()
        print(json.dumps(report.to_dict(), indent=2))

        if args.post_discord:
            if feedback.post_report_to_discord(report):
                print("Posted to Discord")
            else:
                print("Failed to post to Discord", file=sys.stderr)

        return 0

    elif args.cmd == "export":
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=args.days)
        metrics = feedback.tracker.calculate_metrics(start_date, end_date)

        if feedback.export_to_influxdb(metrics):
            print("Exported to InfluxDB")
            return 0
        else:
            print("Failed to export to InfluxDB", file=sys.stderr)
            return 1

    elif args.cmd == "weekly-cycle":
        report = feedback.run_weekly_cycle()
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
