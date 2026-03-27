"""Discord event helpers for autonomous cognition notifications."""

from __future__ import annotations

from typing import Any

from governance.notifications.discord_notifier import DiscordNotifier


async def emit_autocog_event(
    notifier: DiscordNotifier,
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
) -> bool:
    """Emit a standardized autonomous cognition event."""
    return await notifier.notify_autocog_event(
        event_type=event_type,
        severity=severity,
        summary=summary,
        impact=impact,
        top_metrics=top_metrics,
        artifact_path=artifact_path,
        run_id=run_id,
        title=title,
        issue=issue,
        intended_resolution=intended_resolution,
        expected_improvement=expected_improvement,
        outcome_status=outcome_status,
        evidence_reasoning=evidence_reasoning,
    )


async def emit_self_assessment_completed(
    notifier: DiscordNotifier,
    artifact: Any,
    artifact_path: str | None = None,
    decision_packet: dict[str, Any] | None = None,
) -> bool:
    """Emit a self-assessment completed event to Discord.

    This is a convenience wrapper around the notifier's notify_self_assessment
    method with the proper event type for self-assessment completion.

    Args:
        notifier: DiscordNotifier instance
        artifact: SelfAssessmentArtifact or similar object with assessment data
        artifact_path: Optional path to the artifact file
        decision_packet: Optional decision context to include in notification

    Returns:
        True if notification was sent successfully, False otherwise
    """
    return await notifier.notify_self_assessment(
        artifact=artifact,
        artifact_path=artifact_path,
        decision_packet=decision_packet,
    )
