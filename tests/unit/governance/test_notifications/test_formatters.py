"""Tests for notification formatters."""

import pytest
from datetime import UTC, datetime

from governance.notifications.formatters import (
    ReflectionNotificationFormatter,
    DecisionNotificationFormatter,
)
from governance.reflection.bottleneck_reflection import (
    DailyReflectionArtifact,
    WeeklyReflectionArtifact,
    BottleneckKPI,
    ImpactScore,
    RemediationAction,
    Priority,
    TrendDelta,
    FrameworkImprovement,
)


class TestReflectionNotificationFormatter:
    """Test reflection notification formatter."""

    def test_format_daily_basic(self):
        """Test basic daily reflection formatting."""
        formatter = ReflectionNotificationFormatter()
        artifact = DailyReflectionArtifact(
            date="2026-03-03",
            timestamp="2026-03-03T12:00:00Z",
            provenance="test",
            top_bottlenecks=[
                BottleneckKPI(
                    bottleneck_type="ci_failures",
                    occurrence_count=5,
                    avg_impact_score=4.0,
                    affected_stories=["ST-001"],
                    trend_direction="improving",
                )
            ],
            impact_scores=ImpactScore(
                throughput=3, efficiency=4, accuracy=2, reliability=5
            ),
            remediation_actions=[
                RemediationAction(
                    action="Fix CI pipeline",
                    priority=Priority.HIGH,
                    owner_placeholder="OWNER_TBD: devops",
                    estimated_effort="2-4 hours",
                )
            ],
            summary="Test summary",
        )

        result = formatter.format_daily(artifact, "/path/to/artifact.json")

        assert "Daily Reflection Generated" in result
        assert "2026-03-03" in result
        assert "ci_failures" in result
        assert "5 occurrences" in result
        assert "/path/to/artifact.json" in result

    def test_format_weekly_basic(self):
        """Test basic weekly reflection formatting."""
        formatter = ReflectionNotificationFormatter()
        artifact = WeeklyReflectionArtifact(
            week_start="2026-02-24",
            week_end="2026-03-02",
            timestamp="2026-03-03T12:00:00Z",
            provenance="test",
            trend_deltas=[
                TrendDelta(
                    kpi_name="ci_pass_rate",
                    current_value=0.95,
                    previous_value=0.90,
                    delta=0.05,
                    delta_percent=5.56,
                    direction="improved",
                )
            ],
            improvements=["ci_pass_rate"],
            regressions=[],
            framework_improvements=[
                FrameworkImprovement(
                    improvement="Add monitoring",
                    priority=Priority.MEDIUM,
                    owner_placeholder="OWNER_TBD: dev",
                    rationale="Need better visibility",
                    estimated_impact="High",
                )
            ],
            summary="Test summary",
        )

        result = formatter.format_weekly(artifact, "/path/to/weekly.json")

        assert "Weekly Reflection Generated" in result
        assert "2026-02-24" in result
        assert "ci_pass_rate" in result
        assert "improved" in result


class TestDecisionNotificationFormatter:
    """Test decision notification formatter."""

    def test_format_decision_basic(self):
        """Test basic decision formatting."""
        formatter = DecisionNotificationFormatter()
        decision_data = {
            "story_id": "ST-001",
            "title": "Use Redis for caching",
            "rationale": "Better performance",
            "impact": "30% faster queries",
            "timestamp": "2026-03-03T12:00:00Z",
        }

        result = formatter.format_decision(decision_data)

        assert "Decision Recorded" in result
        assert "ST-001" in result
        assert "Use Redis for caching" in result
        assert "Better performance" in result
        assert "30% faster queries" in result
