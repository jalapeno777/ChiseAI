"""Belief revision engine with policy gating."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from autonomous_cognition.beliefs.models import (
    Belief,
    BeliefConflict,
    BeliefRevision,
    BeliefSupportScore,
    EvidenceRecord,
)


class BeliefRevisionEngine:
    """Applies safe revisions to conflicting beliefs."""

    def __init__(
        self,
        min_confidence_delta: float = 0.1,
        min_support_delta: float = 0.05,
        min_winner_evidence_count: int = 1,
        min_distinct_source_families: int = 3,
        min_non_llm_source_families: int = 2,
        min_temporal_confirmations: int = 2,
    ):
        self._min_confidence_delta = min_confidence_delta
        self._min_support_delta = min_support_delta
        self._min_winner_evidence_count = min_winner_evidence_count
        self._min_distinct_source_families = min_distinct_source_families
        self._min_non_llm_source_families = min_non_llm_source_families
        self._min_temporal_confirmations = min_temporal_confirmations
        self.last_blocked_revisions: list[dict[str, Any]] = []
        self.last_support_scores: dict[str, dict[str, Any]] = {}

    def apply_revisions(
        self,
        beliefs: dict[str, Belief],
        conflicts: list[BeliefConflict],
        evidence_index: dict[str, list[EvidenceRecord]] | None = None,
    ) -> list[BeliefRevision]:
        """Apply revisions when policy thresholds are met."""
        self.last_blocked_revisions = []
        self.last_support_scores = {}
        evidence_index = evidence_index or {}

        revisions: list[BeliefRevision] = []
        for conflict in conflicts:
            a = beliefs.get(conflict.belief_id_a)
            b = beliefs.get(conflict.belief_id_b)
            if a is None or b is None:
                continue

            score_a = self._score_belief_support(a, evidence_index)
            score_b = self._score_belief_support(b, evidence_index)
            self.last_support_scores[a.belief_id] = score_a.to_dict()
            self.last_support_scores[b.belief_id] = score_b.to_dict()

            winner, loser, winner_score, loser_score = self._pick_winner(
                a,
                b,
                score_a,
                score_b,
            )
            confidence_delta = winner.confidence - loser.confidence
            support_delta = winner_score.support_score - loser_score.support_score
            winner_source_summary = self._summarize_evidence_sources(
                winner, evidence_index
            )

            if winner_score.evidence_count < self._min_winner_evidence_count:
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "insufficient_evidence:"
                            f"winner_evidence_count={winner_score.evidence_count}"
                        ),
                    )
                )
                continue

            if support_delta < self._min_support_delta:
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "support_margin_too_small:"
                            f"support_delta={support_delta:.3f}"
                        ),
                    )
                )
                continue

            if confidence_delta < self._min_confidence_delta:
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "confidence_margin_too_small:"
                            f"confidence_delta={confidence_delta:.3f}"
                        ),
                    )
                )
                continue

            if (
                winner_source_summary["distinct_source_families"]
                < self._min_distinct_source_families
            ):
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "insufficient_source_diversity:"
                            "distinct_source_families="
                            f"{winner_source_summary['distinct_source_families']}"
                        ),
                    )
                )
                continue

            if (
                winner_source_summary["non_llm_source_families"]
                < self._min_non_llm_source_families
            ):
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "insufficient_non_llm_sources:"
                            "non_llm_source_families="
                            f"{winner_source_summary['non_llm_source_families']}"
                        ),
                    )
                )
                continue

            if (
                winner_source_summary["temporal_confirmations"]
                < self._min_temporal_confirmations
            ):
                self.last_blocked_revisions.append(
                    self._build_blocked_revision(
                        conflict=conflict,
                        winner=winner,
                        loser=loser,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        winner_source_summary=winner_source_summary,
                        reason=(
                            "insufficient_temporal_confirmation:"
                            "confirmed_runs="
                            f"{winner_source_summary['temporal_confirmations']}"
                        ),
                    )
                )
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

    def _pick_winner(
        self,
        a: Belief,
        b: Belief,
        score_a: BeliefSupportScore,
        score_b: BeliefSupportScore,
    ) -> tuple[Belief, Belief, BeliefSupportScore, BeliefSupportScore]:
        """Pick winner by support score, then confidence, then source quality."""
        if score_a.support_score > score_b.support_score:
            return a, b, score_a, score_b
        if score_b.support_score > score_a.support_score:
            return b, a, score_b, score_a
        if a.confidence > b.confidence:
            return a, b, score_a, score_b
        if b.confidence > a.confidence:
            return b, a, score_b, score_a
        if a.sources_quality_score >= b.sources_quality_score:
            return a, b, score_a, score_b
        return b, a, score_b, score_a

    def _score_belief_support(
        self,
        belief: Belief,
        evidence_index: dict[str, list[EvidenceRecord]],
    ) -> BeliefSupportScore:
        """Compute evidence-backed support score for a belief."""
        records: list[EvidenceRecord] = []
        for ref in belief.evidence_refs:
            records.extend(evidence_index.get(ref, []))
        evidence_count = len(records)
        avg_reliability = (
            sum(r.reliability for r in records) / evidence_count if evidence_count else 0.0
        )
        evidence_factor = min(1.0, evidence_count / 3)
        support_score = (
            0.4 * belief.confidence
            + 0.2 * belief.sources_quality_score
            + 0.2 * avg_reliability
            + 0.2 * evidence_factor
        )
        if evidence_count == 0:
            support_score *= 0.5
        return BeliefSupportScore(
            belief_id=belief.belief_id,
            support_score=round(support_score, 3),
            evidence_count=evidence_count,
            avg_reliability=round(avg_reliability, 3),
            confidence=belief.confidence,
            sources_quality_score=belief.sources_quality_score,
        )

    @staticmethod
    def _build_blocked_revision(
        *,
        conflict: BeliefConflict,
        winner: Belief,
        loser: Belief,
        winner_score: BeliefSupportScore,
        loser_score: BeliefSupportScore,
        winner_source_summary: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Build explainable blocked-revision payload."""
        return {
            "conflict_id": conflict.conflict_id,
            "winner_belief_id": winner.belief_id,
            "loser_belief_id": loser.belief_id,
            "winner_support_score": winner_score.support_score,
            "loser_support_score": loser_score.support_score,
            "winner_evidence_count": winner_score.evidence_count,
            "loser_evidence_count": loser_score.evidence_count,
            "winner_distinct_source_families": winner_source_summary[
                "distinct_source_families"
            ],
            "winner_non_llm_source_families": winner_source_summary[
                "non_llm_source_families"
            ],
            "winner_temporal_confirmations": winner_source_summary[
                "temporal_confirmations"
            ],
            "winner_source_families": winner_source_summary["source_families"],
            "reason": reason,
            "blocked_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _summarize_evidence_sources(
        belief: Belief,
        evidence_index: dict[str, list[EvidenceRecord]],
    ) -> dict[str, Any]:
        """Summarize evidence-source diversity and temporal strength."""
        records: list[EvidenceRecord] = []
        for ref in belief.evidence_refs:
            records.extend(evidence_index.get(ref, []))
        source_families = {r.source_family for r in records if r.source_family}
        non_llm_families = {
            r.source_family
            for r in records
            if r.source_family and not r.is_llm_judgment
        }
        temporal_confirmations = max(
            (
                int(r.metrics.get("confirmed_runs", 1))
                for r in records
                if isinstance(r.metrics.get("confirmed_runs", 1), int)
            ),
            default=0,
        )
        return {
            "distinct_source_families": len(source_families),
            "non_llm_source_families": len(non_llm_families),
            "temporal_confirmations": temporal_confirmations,
            "source_families": sorted(source_families),
        }
