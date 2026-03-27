"""Explanation helpers for belief conflict and revision decisions."""

from __future__ import annotations

from autonomous_cognition.beliefs.models import (
    Belief,
    BeliefConflict,
    BeliefRevision,
    BeliefType,
)


def explain_belief(belief: Belief) -> str:
    """Generate human-readable explanation of a belief's key attributes.

    Args:
        belief: The belief to explain

    Returns:
        Human-readable string describing the belief
    """
    type_label = _get_belief_type_label(belief.belief_type)
    evidence_count = len(belief.evidence_refs)

    parts = [
        f"Belief [{belief.belief_id}]",
        f"Type: {type_label}",
        f"Domain: {belief.domain}",
        f'Statement: "{belief.statement[:100]}{"..." if len(belief.statement) > 100 else ""}"',
        f"Confidence: {belief.confidence:.1%}",
        f"Evidence: {evidence_count} reference{'s' if evidence_count != 1 else ''}",
        f"Status: {belief.status}",
    ]

    if belief.supersedes_belief_id:
        parts.append(f"Supersedes: {belief.supersedes_belief_id}")

    if belief.provenance:
        parts.append(
            f"Provenance: {len(belief.provenance)} step{'s' if len(belief.provenance) != 1 else ''}"
        )

    return "\n".join(parts)


def explain_conflict(conflict: BeliefConflict) -> str:
    """Generate concise explanation for a belief conflict.

    Args:
        conflict: The conflict to explain

    Returns:
        Human-readable conflict explanation
    """
    return (
        f"Conflict {conflict.conflict_id}: beliefs {conflict.belief_id_a} and "
        f"{conflict.belief_id_b} ({conflict.severity}) - {conflict.reason}"
    )


def explain_conflict_detailed(
    conflict: BeliefConflict, belief_a: Belief, belief_b: Belief
) -> str:
    """Generate detailed explanation for a belief conflict.

    Args:
        conflict: The conflict to explain
        belief_a: First belief involved in conflict
        belief_b: Second belief involved in conflict

    Returns:
        Detailed human-readable conflict explanation
    """
    lines = [
        f"=== Conflict Analysis: {conflict.conflict_id} ===",
        f"Severity: {conflict.severity.upper()}",
        f"Detected: {conflict.detected_at}",
        "",
        f"--- Belief A: {conflict.belief_id_a} ---",
        f"Statement: {belief_a.statement}",
        f"Domain: {belief_a.domain}",
        f"Confidence: {belief_a.confidence:.1%}",
        f"Type: {_get_belief_type_label(belief_a.belief_type)}",
        "",
        f"--- Belief B: {conflict.belief_id_b} ---",
        f"Statement: {belief_b.statement}",
        f"Domain: {belief_b.domain}",
        f"Confidence: {belief_b.confidence:.1%}",
        f"Type: {_get_belief_type_label(belief_b.belief_type)}",
        "",
        "--- Analysis ---",
        f"Similarity Score: {conflict.similarity:.2f}",
        f"Reason: {conflict.reason}",
    ]

    return "\n".join(lines)


def explain_revision(revision: BeliefRevision) -> str:
    """Generate concise explanation for a belief revision.

    Args:
        revision: The revision to explain

    Returns:
        Human-readable revision explanation
    """
    delta = revision.confidence_after - revision.confidence_before
    delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"

    return (
        f"Revision {revision.revision_id}: superseded {revision.old_belief_id} "
        f"with {revision.new_belief_id}; confidence "
        f"{revision.confidence_before:.2f}->{revision.confidence_after:.2f} ({delta_str})"
    )


def explain_revision_detailed(revision: BeliefRevision) -> str:
    """Generate detailed explanation for a belief revision.

    Args:
        revision: The revision to explain

    Returns:
        Detailed human-readable revision explanation with full context
    """
    delta = revision.confidence_after - revision.confidence_before
    delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
    evidence_count = len(revision.evidence_refs)

    lines = [
        f"=== Revision: {revision.revision_id} ===",
        f"Timestamp: {revision.applied_at}",
        "",
        "--- Change Summary ---",
        f"Superseded: {revision.old_belief_id}",
        f"Adopted: {revision.new_belief_id}",
        f"Confidence: {revision.confidence_before:.2f} -> {revision.confidence_after:.2f} ({delta_str})",
        f"Evidence Used: {evidence_count} reference{'s' if evidence_count != 1 else ''}",
        "",
        "--- Rationale ---",
        f"{revision.reason}",
    ]

    if revision.evidence_refs:
        lines.append("")
        lines.append("--- Evidence References ---")
        for ref in revision.evidence_refs:
            lines.append(f"  - {ref}")

    return "\n".join(lines)


def _get_belief_type_label(belief_type: BeliefType | str) -> str:
    """Get human-readable label for belief type.

    Args:
        belief_type: The belief type enum or string value

    Returns:
        Human-readable label
    """
    if isinstance(belief_type, BeliefType):
        return belief_type.value.capitalize()

    type_labels = {
        "fact": "FACT",
        "inference": "INFERENCE",
        "hypothesis": "HYPOTHESIS",
    }
    return type_labels.get(belief_type, belief_type.upper())


def explain_consistency_check_result(
    conflicts: list[BeliefConflict],
    total_beliefs: int,
) -> str:
    """Generate human-readable summary of a consistency check.

    Args:
        conflicts: List of conflicts found
        total_beliefs: Total number of beliefs checked

    Returns:
        Human-readable summary
    """
    if not conflicts:
        return (
            f"Consistency check PASSED: {total_beliefs} beliefs checked, "
            f"no conflicts detected."
        )

    # Group by severity
    by_severity: dict[str, int] = {}
    for conflict in conflicts:
        by_severity[conflict.severity] = by_severity.get(conflict.severity, 0) + 1

    severity_parts = [f"{count} {sev}" for sev, count in sorted(by_severity.items())]

    return (
        f"Consistency check COMPLETED: {total_beliefs} beliefs checked, "
        f"{len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''} detected. "
        f"Breakdown: {', '.join(severity_parts)}."
    )
