"""Notification formatters for governance events."""

import logging
from datetime import UTC, datetime
from typing import Any

from governance.reflection.bottleneck_reflection import (
    DailyReflectionArtifact,
    WeeklyReflectionArtifact,
)

logger = logging.getLogger(__name__)


class ReflectionNotificationFormatter:
    """Formats reflection artifacts for Discord notifications."""

    def format_daily(
        self, artifact: DailyReflectionArtifact, artifact_path: str | None = None
    ) -> str:
        """Format a daily reflection artifact."""
        lines = [
            "📊 **Daily Reflection Generated**",
            "",
            "**Event Type:** Daily Bottleneck Reflection",
            f"**Period:** {artifact.date}",
            f"**Timestamp:** {artifact.timestamp}",
        ]

        # Key outcomes
        if artifact.top_bottlenecks:
            lines.extend(["", "**Key Outcomes:**"])
            for bn in artifact.top_bottlenecks[:3]:
                trend_icon = {"improving": "📈", "stable": "➡️", "worsening": "📉"}.get(
                    bn.trend_direction, "➡️"
                )
                lines.append(
                    f"  {trend_icon} **{bn.bottleneck_type}**: {bn.occurrence_count} occurrences "
                    f"(impact: {bn.avg_impact_score:.1f}/5, trend: {bn.trend_direction})"
                )

        # Impact scores
        lines.extend(
            [
                "",
                "**Impact Scores (1-5 scale):**",
                f"  • Throughput: {artifact.impact_scores.throughput}",
                f"  • Efficiency: {artifact.impact_scores.efficiency}",
                f"  • Accuracy: {artifact.impact_scores.accuracy}",
                f"  • Reliability: {artifact.impact_scores.reliability}",
            ]
        )

        # Recommendations
        if artifact.remediation_actions:
            lines.extend(["", "**Top Recommendations:**"])
            for rec in artifact.remediation_actions[:3]:
                lines.append(f"  • {rec.action} (Priority: {rec.priority.value})")

        # Artifact info
        lines.extend(
            [
                "",
                f"**Artifact ID:** `{artifact.date}`",
                f"**Artifact Path:** `{artifact_path or 'N/A'}`",
            ]
        )

        return "\n".join(lines)

    def format_weekly(
        self, artifact: WeeklyReflectionArtifact, artifact_path: str | None = None
    ) -> str:
        """Format a weekly reflection artifact."""
        lines = [
            "📊 **Weekly Reflection Generated**",
            "",
            "**Event Type:** Weekly Trend Reflection",
            f"**Period:** {artifact.week_start} to {artifact.week_end}",
            f"**Timestamp:** {artifact.timestamp}",
        ]

        # Trend deltas
        if artifact.trend_deltas:
            lines.extend(["", "**KPI Trends:**"])
            for delta in artifact.trend_deltas:
                icon = {"improved": "📈", "stable": "➡️", "regressed": "📉"}.get(
                    delta.direction, "➡️"
                )
                lines.append(
                    f"  {icon} **{delta.kpi_name}**: {delta.current_value:.2f} "
                    f"({delta.direction}, {abs(delta.delta_percent):.1f}%)"
                )

        # Improvements and regressions
        if artifact.improvements:
            lines.extend(
                ["", f"**✅ Improvements:** {', '.join(artifact.improvements)}"]
            )
        if artifact.regressions:
            lines.extend(["", f"**⚠️ Regressions:** {', '.join(artifact.regressions)}"])

        # Framework improvements
        if artifact.framework_improvements:
            lines.extend(["", "**Framework Recommendations:**"])
            for fi in artifact.framework_improvements[:3]:
                lines.append(f"  • {fi.improvement} (Priority: {fi.priority.value})")

        # Artifact info
        lines.extend(
            [
                "",
                f"**Artifact ID:** `{artifact.week_start}`",
                f"**Artifact Path:** `{artifact_path or 'N/A'}`",
            ]
        )

        return "\n".join(lines)


class DecisionNotificationFormatter:
    """Formats decision events for Discord notifications."""

    def format_decision(self, decision_data: dict[str, Any]) -> str:
        """Format a decision notification."""
        story_id = decision_data.get("story_id", "unknown")
        title = decision_data.get(
            "title", decision_data.get("summary", "Decision Recorded")
        )
        rationale = decision_data.get("rationale", "No rationale provided")
        impact = decision_data.get("impact", "No impact specified")
        timestamp = decision_data.get("timestamp", datetime.now(UTC).isoformat())

        lines = [
            "📝 **Decision Recorded**",
            "",
            f"**Story ID:** {story_id}",
            f"**Decision:** {title}",
            "",
            f"**Rationale:** {rationale}",
            f"**Impact:** {impact}",
            f"**Timestamp:** {timestamp}",
        ]

        return "\n".join(lines)


class SelfAssessmentNotificationFormatter:
    """Formats autonomous self-assessment events for Discord notifications."""

    def format_self_assessment(
        self,
        artifact: Any,
        artifact_path: str | None = None,
    ) -> str:
        """Format a self-assessment completion event."""
        status = getattr(artifact, "status", "unknown")
        assessment_id = getattr(artifact, "assessment_id", "unknown")
        assessment_date = getattr(artifact, "assessment_date", "unknown")
        created_at = getattr(artifact, "created_at", datetime.now(UTC).isoformat())
        score = getattr(artifact, "overall_score", 0.0)
        findings = list(getattr(artifact, "findings", []))
        recommendations = list(getattr(artifact, "recommendations", []))

        status_icon = {"ok": "✅", "degraded": "⚠️", "failed": "🚨"}.get(status, "📌")

        lines = [
            f"{status_icon} **Autonomous Self-Assessment Completed**",
            "",
            "**Event Type:** `self_assessment_completed`",
            f"**Assessment ID:** `{assessment_id}`",
            f"**Date:** {assessment_date}",
            f"**Status:** {status}",
            f"**Overall Score:** {score}",
            f"**Timestamp:** {created_at}",
        ]

        if findings:
            lines.extend(["", "**Findings:**"])
            for item in findings[:3]:
                lines.append(f"  • {item}")

        if recommendations:
            lines.extend(["", "**Recommendations:**"])
            for item in recommendations[:3]:
                lines.append(f"  • {item}")

        lines.extend(["", f"**Artifact Path:** `{artifact_path or 'N/A'}`"])
        return "\n".join(lines)
