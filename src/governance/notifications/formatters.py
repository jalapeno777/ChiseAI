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

    # Discord embed color constants (integer values)
    COLOR_OK: int = 0x00FF00  # Green
    COLOR_DEGRADED: int = 0xFFAA00  # Yellow/Orange
    COLOR_FAILED: int = 0xFF0000  # Red
    COLOR_DEFAULT: int = 0x3498DB  # Blue (unknown status)

    def _get_status_color(self, status: str) -> int:
        """Get Discord embed color based on assessment status."""
        return {
            "ok": self.COLOR_OK,
            "degraded": self.COLOR_DEGRADED,
            "failed": self.COLOR_FAILED,
        }.get(status.lower(), self.COLOR_DEFAULT)

    def _get_status_icon(self, status: str) -> str:
        """Get emoji icon for assessment status."""
        return {"ok": "✅", "degraded": "⚠️", "failed": "🚨"}.get(status.lower(), "📌")

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

    def format_self_assessment_completed(
        self,
        artifact: Any,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        """Format a self-assessment completion event as a Discord embed.

        Returns a Discord embed dictionary with:
        - title: Formatted status with icon
        - color: Based on status (green/yellow/red)
        - fields: score, status, findings count, recommendations count, dimensions
        - footer: artifact path

        Args:
            artifact: SelfAssessmentArtifact or similar object
            artifact_path: Optional path to the artifact file

        Returns:
            Dictionary suitable for Discord webhook embed format
        """
        status = getattr(artifact, "status", "unknown")
        assessment_id = getattr(artifact, "assessment_id", "unknown")
        assessment_date = getattr(artifact, "assessment_date", "unknown")
        created_at = getattr(artifact, "created_at", datetime.now(UTC).isoformat())
        score = getattr(artifact, "overall_score", 0.0)
        dimensions = getattr(artifact, "dimensions", {})
        findings = list(getattr(artifact, "findings", []))
        recommendations = list(getattr(artifact, "recommendations", []))

        status_icon = self._get_status_icon(status)
        status_color = self._get_status_color(status)

        # Build dimensions summary string
        dimensions_summary = (
            ", ".join(f"{k}: {v:.2f}" for k, v in list(dimensions.items())[:5])
            if dimensions
            else "No dimensions"
        )

        # Build embed fields
        fields = [
            {
                "name": "Assessment ID",
                "value": f"`{assessment_id}`",
                "inline": True,
            },
            {
                "name": "Date",
                "value": assessment_date,
                "inline": True,
            },
            {
                "name": "Overall Score",
                "value": f"{score:.3f}" if isinstance(score, float) else str(score),
                "inline": True,
            },
            {
                "name": "Status",
                "value": f"{status_icon} {status.capitalize()}",
                "inline": True,
            },
            {
                "name": "Findings",
                "value": str(len(findings)),
                "inline": True,
            },
            {
                "name": "Recommendations",
                "value": str(len(recommendations)),
                "inline": True,
            },
        ]

        # Add dimensions as a field if available
        if dimensions:
            fields.append(
                {
                    "name": "Dimensions",
                    "value": dimensions_summary[:1024],  # Discord field value limit
                    "inline": False,
                }
            )

        embed = {
            "title": f"{status_icon} Self-Assessment Completed",
            "color": status_color,
            "fields": fields,
            "footer": {
                "text": f"Artifact: {artifact_path or 'N/A'}",
            },
            "timestamp": created_at,
        }

        return embed


class AutocogEventFormatter:
    """Formats generic autonomous cognition events for Discord notifications."""

    _MAX_DISCORD_MESSAGE_LEN = 1900

    def format_event(
        self,
        event_type: str,
        severity: str,
        summary: str,
        impact: str,
        top_metrics: dict[str, Any],
        artifact_path: str | None,
        run_id: str,
        title: str | None = None,
        issue: str | None = None,
        intended_resolution: str | None = None,
        expected_improvement: str | None = None,
        outcome_status: str | None = None,
        evidence_reasoning: list[str] | None = None,
        decision_packet: dict[str, Any] | None = None,
    ) -> str:
        """Format a standardized autonomous cognition event."""
        evidence_reasoning = evidence_reasoning or []
        decision_packet = decision_packet or {}
        icon = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "📌",
            "low": "✅",
        }.get(severity.lower(), "📌")

        display_title = title or event_type.replace("_", " ").title()
        layman_issue = issue or summary
        layman_resolution = intended_resolution or impact
        layman_improvement = (
            expected_improvement or "No explicit improvement target provided."
        )
        normalized_outcome = (outcome_status or "unknown").strip().lower()
        outcome_display = {
            "success": "Succeeded",
            "succeeded": "Succeeded",
            "pass": "Succeeded",
            "failed": "Failed",
            "failure": "Failed",
            "error": "Failed",
            "partial": "Partially Succeeded",
            "in_progress": "In Progress",
            "in progress": "In Progress",
            "unknown": "Unknown",
        }.get(normalized_outcome, outcome_status or "Unknown")

        lines = [
            f"{icon} **Autonomous Cognition Event**",
            "",
            f"**Title:** {display_title}",
            f"**Why This Happened (Plain English):** {layman_issue}",
            f"**Intended Resolution:** {layman_resolution}",
            f"**How This Should Improve Things:** {layman_improvement}",
            f"**Result:** {outcome_display}",
            "",
            f"**Event Type:** `{event_type}`",
            f"**Severity:** {severity}",
            f"**Summary:** {summary}",
            f"**Impact:** {impact}",
            f"**Run ID:** `{run_id}`",
            f"**Timestamp:** {datetime.now(UTC).isoformat()}",
        ]

        if evidence_reasoning:
            lines.extend(["", "**Evidence / Reasoning:**"])
            for reason in evidence_reasoning[:8]:
                lines.append(f"  • {reason}")

        if decision_packet:
            lines.extend(["", "**Revision Decision Packet:**"])
            contradiction = decision_packet.get("contradiction")
            if contradiction:
                lines.append(f"  • Contradiction: {contradiction}")
            previous = decision_packet.get("previous_belief")
            if isinstance(previous, dict):
                lines.append(
                    "  • Previous Belief: "
                    f"{previous.get('belief_id', 'unknown')} | "
                    f"{previous.get('statement', 'unknown')}"
                )
            replacement = decision_packet.get("replacement_belief")
            if isinstance(replacement, dict):
                lines.append(
                    "  • Replacement Belief: "
                    f"{replacement.get('belief_id', 'unknown')} | "
                    f"{replacement.get('statement', 'unknown')}"
                )
            rationale = decision_packet.get("selection_rationale")
            if rationale:
                lines.append(f"  • Why This Won: {rationale}")
            expected = decision_packet.get("expected_improvements")
            if isinstance(expected, list):
                for item in expected[:2]:
                    lines.append(f"  • Expected Improvement: {item}")
            source_diversity = decision_packet.get("source_diversity")
            if isinstance(source_diversity, dict):
                lines.append(
                    "  • Source Diversity: "
                    f"distinct={source_diversity.get('distinct_source_families', 0)} "
                    f"non_llm={source_diversity.get('non_llm_source_families', 0)}"
                )
                families = source_diversity.get("source_families")
                if isinstance(families, list) and families:
                    lines.append("  • Source Families: " + ", ".join(families[:5]))
            rollback_hint = decision_packet.get("rollback_hint")
            if rollback_hint:
                lines.append(f"  • Rollback Hint: {rollback_hint}")

        if top_metrics:
            lines.extend(["", "**Top Metrics:**"])
            for key, value in list(top_metrics.items())[:5]:
                lines.append(f"  • {key}: {value}")

        lines.extend(["", f"**Artifact Path:** `{artifact_path or 'N/A'}`"])
        return self._truncate_message("\n".join(lines))

    def _truncate_message(self, content: str) -> str:
        """Trim content to stay safely within Discord 2000-char limit."""
        if len(content) <= self._MAX_DISCORD_MESSAGE_LEN:
            return content
        suffix = "\n\n[truncated for Discord length limit]"
        head_len = self._MAX_DISCORD_MESSAGE_LEN - len(suffix)
        if head_len <= 0:
            return content[: self._MAX_DISCORD_MESSAGE_LEN]
        return content[:head_len] + suffix


class LowSeverityDigestFormatter:
    """Formats batched low-severity events into a single digest notification."""

    _MAX_DISCORD_MESSAGE_LEN = 1900

    def format_digest(self, items: list[dict[str, Any]]) -> str:
        """Format a list of low-severity events into a digest message.

        Args:
            items: List of event dicts with at least ``event_type`` and
                ``summary`` keys.

        Returns:
            Formatted Discord message string.
        """
        if not items:
            return ""

        lines = [
            f"📋 **Low-Severity Event Digest ({len(items)} items)**",
            "",
        ]

        for idx, item in enumerate(items, 1):
            event_type = item.get("event_type", "unknown")
            summary = item.get("summary", "No summary")
            run_id = item.get("run_id", "")
            severity = item.get("severity", "low").upper()

            lines.append(f"**{idx}. [{severity}]** `{event_type}`")
            lines.append(f"   {summary}")
            if run_id:
                lines.append(f"   Run: `{run_id}`")
            lines.append("")

        lines.append(f"_Digest generated at {datetime.now(UTC).isoformat()}_")
        return self._truncate_message("\n".join(lines))

    def _truncate_message(self, content: str) -> str:
        """Trim content to stay safely within Discord 2000-char limit."""
        if len(content) <= self._MAX_DISCORD_MESSAGE_LEN:
            return content
        suffix = "\n\n[digest truncated for Discord length limit]"
        head_len = self._MAX_DISCORD_MESSAGE_LEN - len(suffix)
        if head_len <= 0:
            return content[: self._MAX_DISCORD_MESSAGE_LEN]
        return content[:head_len] + suffix
