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


async def emit_runtime_decision(
    notifier: DiscordNotifier,
    decision_type: str,
    severity: str,
    summary: str,
    impact: str,
    confidence_breakdown: dict[str, float],
    decision_id: str,
    reasoning_chain: list[str],
) -> bool:
    """Emit a runtime integration decision event to Discord.

    This is a convenience wrapper for emitting events from the
    NeuroSymbolicRuntimeIntegrator for key decisions like
    mode transitions, promotions, and demotions.

    Args:
        notifier: DiscordNotifier instance
        decision_type: Type of decision (mode_promotion, mode_demotion, etc.)
        severity: Event severity (low, medium, high, critical)
        summary: Human-readable summary of the decision
        impact: Impact description of the decision
        confidence_breakdown: Confidence scores for different aspects
        decision_id: Unique identifier for this decision
        reasoning_chain: Step-by-step reasoning that led to the decision

    Returns:
        True if notification was sent successfully, False otherwise
    """
    return await notifier.notify_autocog_event(
        event_type=f"runtime_{decision_type}",
        severity=severity,
        summary=summary,
        impact=impact,
        top_metrics=confidence_breakdown,
        artifact_path=None,
        run_id=decision_id,
        title=f"Runtime Decision: {decision_type}",
        evidence_reasoning=reasoning_chain,
    )


def create_runtime_decision_artifact(
    decision_id: str,
    decision_type: str,
    mode: str,
    summary: str,
    reasoning_chain: list[str],
    confidence_breakdown: dict[str, float],
    divergence_score: float | None = None,
    success: bool = True,
) -> dict[str, Any]:
    """Create a structured artifact for a runtime decision.

    This creates a dictionary representation of a runtime decision
    that can be persisted or used for Discord notifications.

    Args:
        decision_id: Unique identifier for this decision
        decision_type: Type of decision (promotion, demotion, etc.)
        mode: Current integration mode at time of decision
        summary: Human-readable summary of the decision
        reasoning_chain: Step-by-step reasoning that led to the decision
        confidence_breakdown: Confidence scores for different aspects
        divergence_score: Optional divergence score at time of decision
        success: Whether the decision action succeeded

    Returns:
        Dictionary containing the structured decision artifact
    """
    from datetime import UTC, datetime

    return {
        "artifact_type": "runtime_decision",
        "decision_id": decision_id,
        "decision_type": decision_type,
        "mode": mode,
        "summary": summary,
        "reasoning_chain": reasoning_chain,
        "confidence_breakdown": {
            k: round(v, 4) for k, v in confidence_breakdown.items()
        },
        "divergence_score": (
            round(divergence_score, 4) if divergence_score is not None else None
        ),
        "success": success,
        "timestamp": datetime.now(UTC).isoformat(),
    }
