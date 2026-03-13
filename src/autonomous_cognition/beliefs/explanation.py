"""Explanation helpers for belief conflict and revision decisions."""

from __future__ import annotations

from autonomous_cognition.beliefs.models import BeliefConflict, BeliefRevision


def explain_conflict(conflict: BeliefConflict) -> str:
    """Generate concise explanation for a belief conflict."""
    return (
        f"Conflict {conflict.conflict_id}: beliefs {conflict.belief_id_a} and "
        f"{conflict.belief_id_b} ({conflict.severity}) - {conflict.reason}"
    )


def explain_revision(revision: BeliefRevision) -> str:
    """Generate concise explanation for a belief revision."""
    return (
        f"Revision {revision.revision_id}: superseded {revision.old_belief_id} "
        f"with {revision.new_belief_id}; confidence "
        f"{revision.confidence_before:.2f}->{revision.confidence_after:.2f}"
    )

