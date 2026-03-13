"""Belief revision engine with policy gating."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from autonomous_cognition.beliefs.models import Belief, BeliefConflict, BeliefRevision


class BeliefRevisionEngine:
    """Applies safe revisions to conflicting beliefs."""

    def __init__(self, min_confidence_delta: float = 0.1):
        self._min_confidence_delta = min_confidence_delta

    def apply_revisions(
        self,
        beliefs: dict[str, Belief],
        conflicts: list[BeliefConflict],
    ) -> list[BeliefRevision]:
        """Apply revisions when policy thresholds are met."""
        revisions: list[BeliefRevision] = []
        for conflict in conflicts:
            a = beliefs.get(conflict.belief_id_a)
            b = beliefs.get(conflict.belief_id_b)
            if a is None or b is None:
                continue
            winner, loser = self._pick_winner(a, b)
            confidence_delta = winner.confidence - loser.confidence
            if confidence_delta < self._min_confidence_delta:
                continue

            loser.status = "superseded"
            loser.updated_at = datetime.now(UTC).isoformat()

            winner.updated_at = datetime.now(UTC).isoformat()

            revision_id = hashlib.sha256(
                f"{winner.belief_id}:{loser.belief_id}:{conflict.conflict_id}".encode()
            ).hexdigest()[:16]
            revisions.append(
                BeliefRevision(
                    revision_id=revision_id,
                    old_belief_id=loser.belief_id,
                    new_belief_id=winner.belief_id,
                    reason=f"Resolved conflict {conflict.conflict_id}: {conflict.reason}",
                    evidence_refs=winner.evidence_refs,
                    confidence_before=loser.confidence,
                    confidence_after=winner.confidence,
                )
            )
        return revisions

    def _pick_winner(self, a: Belief, b: Belief) -> tuple[Belief, Belief]:
        """Pick winner by confidence then evidence quality."""
        if a.confidence > b.confidence:
            return a, b
        if b.confidence > a.confidence:
            return b, a
        if a.sources_quality_score >= b.sources_quality_score:
            return a, b
        return b, a
