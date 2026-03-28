"""Automated contradiction resolution for belief graphs."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from autonomous_cognition.beliefs.graph import BeliefGraph
from autonomous_cognition.beliefs.models import (
    Belief,
    BeliefConflict,
    BeliefRelationship,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class ResolutionType:
    """Types of resolution actions."""

    CONFIDENCE_ADJUSTMENT = "confidence_adjustment"
    EVIDENCE_REVIEW = "evidence_review"
    MERGE_BELIEFS = "merge_beliefs"
    ARCHIVE_BELIEF = "archive_belief"
    SUPERSEDE = "supersede"
    NO_ACTION = "no_action"


@dataclass
class ResolutionSuggestion:
    """A suggested resolution for a belief conflict."""

    suggestion_id: str
    conflict_id: str
    resolution_type: str
    target_belief_id: str | None
    source_belief_id: str | None
    confidence_adjustment: float | None = None
    merge_into_belief_id: str | None = None
    archive: bool = False
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.5  # How confident we are in this resolution
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "conflict_id": self.conflict_id,
            "resolution_type": self.resolution_type,
            "target_belief_id": self.target_belief_id,
            "source_belief_id": self.source_belief_id,
            "confidence_adjustment": self.confidence_adjustment,
            "merge_into_belief_id": self.merge_into_belief_id,
            "archive": self.archive,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


@dataclass
class AppliedResolution:
    """Record of an applied resolution."""

    resolution_id: str
    conflict_id: str
    resolution_type: str
    applied_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    belief_id: str | None = None
    previous_confidence: float | None = None
    new_confidence: float | None = None
    archived: bool = False
    merged_into: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "conflict_id": self.conflict_id,
            "resolution_type": self.resolution_type,
            "applied_at": self.applied_at,
            "belief_id": self.belief_id,
            "previous_confidence": self.previous_confidence,
            "new_confidence": self.new_confidence,
            "archived": self.archived,
            "merged_into": self.merged_into,
        }


class ContradictionResolver:
    """Automated contradiction resolution using graph traversal and conflict analysis."""

    GRAPH_RELATIONSHIP_KEY = "bmad:chiseai:autocog:resolver:relationships"

    def __init__(
        self, graph: BeliefGraph | None = None, redis_client: Any | None = None
    ):
        self._graph = graph or BeliefGraph(redis_client=redis_client)
        self._redis_client = redis_client
        self._resolution_history: list[AppliedResolution] = []
        self._pending_suggestions: dict[str, list[ResolutionSuggestion]] = {}

    def detect_contradictions(self) -> list[BeliefConflict]:
        """Detect contradictions using graph traversal and consistency checking.

        Checks both direct edges (CONTRADICTS relationships) and
        transitive conflicts through graph traversal.
        """
        logger.info("[CONTRADICTION_RESOLVER] Detecting contradictions")
        conflicts: list[BeliefConflict] = []

        # Find direct CONTRADICTS relationships
        direct_conflicts = self._find_direct_contradictions()
        conflicts.extend(direct_conflicts)

        # Find transitive contradictions through graph traversal
        transitive_conflicts = self._find_transitive_contradictions()

        # Avoid duplicates
        existing_ids = {c.conflict_id for c in conflicts}
        for conflict in transitive_conflicts:
            if conflict.conflict_id not in existing_ids:
                conflicts.append(conflict)
                existing_ids.add(conflict.conflict_id)

        logger.info("[CONTRADICTION_RESOLVER] Found %d contradictions", len(conflicts))
        return conflicts

    def _find_direct_contradictions(self) -> list[BeliefConflict]:
        """Find contradictions from CONTRADICTS edges."""
        conflicts: list[BeliefConflict] = []

        for rel in self._graph._edges.values():
            if rel.relationship_type == RelationshipType.CONTRADICTS.value:
                belief_a = self._graph.get_belief(rel.source_belief_id)
                belief_b = self._graph.get_belief(rel.target_belief_id)

                if belief_a and belief_b:
                    conflict_id = hashlib.sha256(
                        f"{rel.source_belief_id}:{rel.target_belief_id}:direct".encode()
                    ).hexdigest()[:16]

                    # Determine severity from confidence difference
                    conf_diff = abs(belief_a.confidence - belief_b.confidence)
                    if conf_diff > 0.3:
                        severity = "high"
                    elif conf_diff > 0.15:
                        severity = "medium"
                    else:
                        severity = "low"

                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=rel.source_belief_id,
                            belief_id_b=rel.target_belief_id,
                            similarity=0.5,
                            severity=severity,
                            reason="Direct contradicts edge between beliefs",
                            resolution_status="pending",
                        )
                    )

        return conflicts

    def _find_transitive_contradictions(self) -> list[BeliefConflict]:
        """Find contradictions through path analysis (A supports B, B contradicts C)."""
        conflicts: list[BeliefConflict] = []

        # Get all CONTRADICTS relationships
        contradicts_edges = [
            (
                rel,
                self._graph.get_belief(rel.source_belief_id),
                self._graph.get_belief(rel.target_belief_id),
            )
            for rel in self._graph._edges.values()
            if rel.relationship_type == RelationshipType.CONTRADICTS.value
        ]

        # For each pair of contradicts edges, check if there's a path
        # that creates a transitive conflict
        for i, (rel1, _b1, b2) in enumerate(contradicts_edges):
            for rel2, b3, _b4 in contradicts_edges[i + 1 :]:
                # Check if b2 and b3 are connected via SUPPORTS/RELATED
                if b2 and b3 and rel1.target_belief_id == rel2.source_belief_id:
                    # b1 contradicts b2, and b2 supports/related to b3 which contradicts b4
                    # This creates a potential conflict path
                    if b2.confidence > b3.confidence * 0.8:  # b2 is strongly supported
                        conflict_id = hashlib.sha256(
                            f"{rel1.source_belief_id}:{rel2.target_belief_id}:transitive".encode()
                        ).hexdigest()[:16]

                        conflicts.append(
                            BeliefConflict(
                                conflict_id=conflict_id,
                                belief_id_a=rel1.source_belief_id,
                                belief_id_b=rel2.target_belief_id,
                                similarity=0.3,
                                severity="medium",
                                reason=f"Transitive contradiction through {b2.belief_id}",
                                resolution_status="pending",
                            )
                        )

        return conflicts

    def generate_resolution_suggestions(
        self, conflict: BeliefConflict
    ) -> list[ResolutionSuggestion]:
        """Generate possible resolutions for a conflict."""
        logger.info(
            "[CONTRADICTION_RESOLVER] Generating suggestions for conflict %s",
            conflict.conflict_id,
        )
        suggestions: list[ResolutionSuggestion] = []

        belief_a = self._graph.get_belief(conflict.belief_id_a)
        belief_b = self._graph.get_belief(conflict.belief_id_b)

        if belief_a is None or belief_b is None:
            logger.warning(
                "[CONTRADICTION_RESOLVER] Belief not found for conflict %s",
                conflict.conflict_id,
            )
            return suggestions

        # 1. Confidence adjustment suggestion
        suggestions.append(
            self._suggest_confidence_adjustment(conflict, belief_a, belief_b)
        )

        # 2. Evidence review suggestion
        suggestions.append(self._suggest_evidence_review(conflict, belief_a, belief_b))

        # 3. Merge beliefs suggestion (if semantically similar)
        if conflict.similarity > 0.7:
            suggestions.append(self._suggest_merge(conflict, belief_a, belief_b))

        # 4. Archive outdated belief suggestion
        suggestions.append(self._suggest_archive(conflict, belief_a, belief_b))

        # 5. Supersede suggestion
        suggestions.append(self._suggest_supersede(conflict, belief_a, belief_b))

        # Store suggestions
        self._pending_suggestions[conflict.conflict_id] = suggestions

        return suggestions

    def _suggest_confidence_adjustment(
        self,
        conflict: BeliefConflict,
        belief_a: Belief,
        belief_b: Belief,
    ) -> ResolutionSuggestion:
        """Suggest lowering confidence on lower-evidence belief."""
        # Determine which belief has stronger evidence
        if len(belief_a.evidence_refs) >= len(belief_b.evidence_refs):
            weaker, stronger = belief_b, belief_a
        else:
            weaker, stronger = belief_a, belief_b

        adjustment = -(weaker.confidence * 0.2)  # Reduce by 20%
        new_confidence = max(0.1, weaker.confidence + adjustment)

        return ResolutionSuggestion(
            suggestion_id=self._generate_suggestion_id(
                conflict.conflict_id, "conf_adj"
            ),
            conflict_id=conflict.conflict_id,
            resolution_type=ResolutionType.CONFIDENCE_ADJUSTMENT,
            target_belief_id=weaker.belief_id,
            source_belief_id=stronger.belief_id,
            confidence_adjustment=new_confidence,
            reason=f"Lower confidence of {weaker.belief_id} ({weaker.confidence:.2f} -> {new_confidence:.2f}) "
            f"to resolve conflict with stronger-evidence belief {stronger.belief_id}",
            evidence_refs=stronger.evidence_refs,
            confidence=0.7,
        )

    def _suggest_evidence_review(
        self,
        conflict: BeliefConflict,
        belief_a: Belief,
        belief_b: Belief,
    ) -> ResolutionSuggestion:
        """Suggest manual evidence review for high-severity conflicts."""
        return ResolutionSuggestion(
            suggestion_id=self._generate_suggestion_id(conflict.conflict_id, "ev_rev"),
            conflict_id=conflict.conflict_id,
            resolution_type=ResolutionType.EVIDENCE_REVIEW,
            target_belief_id=belief_a.belief_id,
            source_belief_id=belief_b.belief_id,
            reason=f"Flag conflict for human review due to severity: {conflict.severity}. "
            f"Both beliefs should be evaluated for evidence quality.",
            evidence_refs=belief_a.evidence_refs + belief_b.evidence_refs,
            confidence=0.9 if conflict.severity == "high" else 0.5,
        )

    def _suggest_merge(
        self,
        conflict: BeliefConflict,
        belief_a: Belief,
        belief_b: Belief,
    ) -> ResolutionSuggestion:
        """Suggest merging similar beliefs."""
        # Keep the one with more evidence
        if len(belief_a.evidence_refs) >= len(belief_b.evidence_refs):
            keep, discard = belief_a, belief_b
        else:
            keep, discard = belief_b, belief_a

        return ResolutionSuggestion(
            suggestion_id=self._generate_suggestion_id(conflict.conflict_id, "merge"),
            conflict_id=conflict.conflict_id,
            resolution_type=ResolutionType.MERGE_BELIEFS,
            target_belief_id=discard.belief_id,
            source_belief_id=keep.belief_id,
            merge_into_belief_id=keep.belief_id,
            reason=f"Merge {discard.belief_id} into {keep.belief_id} due to high similarity "
            f"({conflict.similarity:.2f}). Both beliefs express similar ideas.",
            evidence_refs=discard.evidence_refs,
            confidence=0.6,
        )

    def _suggest_archive(
        self,
        conflict: BeliefConflict,
        belief_a: Belief,
        belief_b: Belief,
    ) -> ResolutionSuggestion:
        """Suggest archiving outdated belief."""
        # Archive the one with lower confidence
        if belief_a.confidence >= belief_b.confidence:
            archive, keep = belief_b, belief_a
        else:
            archive, keep = belief_a, belief_b

        return ResolutionSuggestion(
            suggestion_id=self._generate_suggestion_id(conflict.conflict_id, "archive"),
            conflict_id=conflict.conflict_id,
            resolution_type=ResolutionType.ARCHIVE_BELIEF,
            target_belief_id=archive.belief_id,
            source_belief_id=keep.belief_id,
            archive=True,
            reason=f"Archive {archive.belief_id} (confidence={archive.confidence:.2f}) in favor of "
            f"{keep.belief_id} (confidence={keep.confidence:.2f})",
            evidence_refs=keep.evidence_refs,
            confidence=0.5,
        )

    def _suggest_supersede(
        self,
        conflict: BeliefConflict,
        belief_a: Belief,
        belief_b: Belief,
    ) -> ResolutionSuggestion:
        """Suggest using supersedes relationship."""
        if belief_a.confidence >= belief_b.confidence:
            supersede, superseded = belief_a, belief_b
        else:
            supersede, superseded = belief_b, belief_a

        return ResolutionSuggestion(
            suggestion_id=self._generate_suggestion_id(
                conflict.conflict_id, "supersede"
            ),
            conflict_id=conflict.conflict_id,
            resolution_type=ResolutionType.SUPERSEDE,
            target_belief_id=superseded.belief_id,
            source_belief_id=supersede.belief_id,
            reason=f"Supersede {superseded.belief_id} with {supersede.belief_id} "
            f"using formal SUPERSEDES relationship",
            evidence_refs=supersede.evidence_refs,
            confidence=0.65,
        )

    def apply_resolution(
        self,
        suggestion: ResolutionSuggestion,
        store: Any = None,
    ) -> AppliedResolution | None:
        """Apply a resolution suggestion to the belief store."""
        logger.info(
            "[CONTRADICTION_RESOLVER] Applying resolution %s",
            suggestion.suggestion_id,
        )

        if suggestion.resolution_type == ResolutionType.CONFIDENCE_ADJUSTMENT:
            return self._apply_confidence_adjustment(suggestion, store)
        elif suggestion.resolution_type == ResolutionType.EVIDENCE_REVIEW:
            return self._apply_evidence_review(suggestion)
        elif suggestion.resolution_type == ResolutionType.MERGE_BELIEFS:
            return self._apply_merge(suggestion, store)
        elif suggestion.resolution_type == ResolutionType.ARCHIVE_BELIEF:
            return self._apply_archive(suggestion, store)
        elif suggestion.resolution_type == ResolutionType.SUPERSEDE:
            return self._apply_supersede(suggestion, store)
        else:
            logger.warning(
                "[CONTRADICTION_RESOLVER] Unknown resolution type: %s",
                suggestion.resolution_type,
            )
            return None

    def _apply_confidence_adjustment(
        self,
        suggestion: ResolutionSuggestion,
        store: Any,
    ) -> AppliedResolution | None:
        """Apply confidence adjustment."""
        if (
            suggestion.target_belief_id is None
            or suggestion.confidence_adjustment is None
        ):
            return None

        belief = self._graph.get_belief(suggestion.target_belief_id)
        if belief is None:
            return None

        previous_confidence = belief.confidence
        belief.confidence = suggestion.confidence_adjustment
        belief.updated_at = datetime.now(UTC).isoformat()

        # Update in store if provided
        if store is not None:
            if not store.put(belief):
                logger.warning(
                    "[CONTRADICTION_RESOLVER] Failed to persist adjusted belief %s",
                    belief.belief_id,
                )

        # Update graph
        self._graph.add_belief(belief)

        # Record resolution
        resolution = AppliedResolution(
            resolution_id=self._generate_resolution_id(suggestion),
            conflict_id=suggestion.conflict_id,
            resolution_type=suggestion.resolution_type,
            belief_id=belief.belief_id,
            previous_confidence=previous_confidence,
            new_confidence=belief.confidence,
        )
        self._resolution_history.append(resolution)

        return resolution

    def _apply_evidence_review(
        self,
        suggestion: ResolutionSuggestion,
    ) -> AppliedResolution:
        """Apply evidence review (no changes, just logging)."""
        resolution = AppliedResolution(
            resolution_id=self._generate_resolution_id(suggestion),
            conflict_id=suggestion.conflict_id,
            resolution_type=suggestion.resolution_type,
        )
        self._resolution_history.append(resolution)
        return resolution

    def _apply_merge(
        self,
        suggestion: ResolutionSuggestion,
        store: Any,
    ) -> AppliedResolution | None:
        """Apply belief merge."""
        if suggestion.merge_into_belief_id is None:
            return None

        discard_id = suggestion.target_belief_id
        keep_id = suggestion.merge_into_belief_id

        if discard_id is None:
            return None

        discard_belief = self._graph.get_belief(discard_id)
        keep_belief = self._graph.get_belief(keep_id)

        if discard_belief is None or keep_belief is None:
            return None

        # Update keep belief with combined evidence
        combined_refs = list(
            set(keep_belief.evidence_refs + discard_belief.evidence_refs)
        )
        keep_belief.evidence_refs = combined_refs
        keep_belief.updated_at = datetime.now(UTC).isoformat()

        # Archive discard belief
        discard_belief.status = "merged"
        discard_belief.updated_at = datetime.now(UTC).isoformat()

        # Update store and graph
        if store is not None:
            if not store.put(keep_belief):
                logger.warning(
                    "[CONTRADICTION_RESOLVER] Failed to persist keep belief %s",
                    keep_belief.belief_id,
                )
            if not store.put(discard_belief):
                logger.warning(
                    "[CONTRADICTION_RESOLVER] Failed to persist discard belief %s",
                    discard_belief.belief_id,
                )

        self._graph.add_belief(keep_belief)
        self._graph.add_belief(discard_belief)

        # Add SUPERSEDES relationship
        rel_id = f"supersedes-{discard_id}-{keep_id}"
        rel = BeliefRelationship(
            relationship_id=rel_id,
            source_belief_id=keep_id,
            target_belief_id=discard_id,
            relationship_type=RelationshipType.SUPERSEDES.value,
            strength=1.0,
            evidence_refs=combined_refs,
        )
        self._graph.add_relationship(rel)

        resolution = AppliedResolution(
            resolution_id=self._generate_resolution_id(suggestion),
            conflict_id=suggestion.conflict_id,
            resolution_type=suggestion.resolution_type,
            belief_id=discard_id,
            merged_into=keep_id,
        )
        self._resolution_history.append(resolution)

        return resolution

    def _apply_archive(
        self,
        suggestion: ResolutionSuggestion,
        store: Any,
    ) -> AppliedResolution | None:
        """Apply belief archive."""
        if suggestion.target_belief_id is None:
            return None

        belief = self._graph.get_belief(suggestion.target_belief_id)
        if belief is None:
            return None

        belief.status = "archived"
        belief.updated_at = datetime.now(UTC).isoformat()

        if store is not None:
            if not store.put(belief):
                logger.warning(
                    "[CONTRADICTION_RESOLVER] Failed to persist archived belief %s",
                    belief.belief_id,
                )

        self._graph.add_belief(belief)

        resolution = AppliedResolution(
            resolution_id=self._generate_resolution_id(suggestion),
            conflict_id=suggestion.conflict_id,
            resolution_type=suggestion.resolution_type,
            belief_id=belief.belief_id,
            archived=True,
        )
        self._resolution_history.append(resolution)

        return resolution

    def _apply_supersede(
        self,
        suggestion: ResolutionSuggestion,
        store: Any,
    ) -> AppliedResolution | None:
        """Apply supersedes relationship."""
        if suggestion.source_belief_id is None or suggestion.target_belief_id is None:
            return None

        supersede_id = suggestion.source_belief_id
        superseded_id = suggestion.target_belief_id

        supersede_belief = self._graph.get_belief(supersede_id)
        superseded_belief = self._graph.get_belief(superseded_id)

        if supersede_belief is None or superseded_belief is None:
            return None

        # Update superseded belief
        superseded_belief.status = "superseded"
        superseded_belief.supersedes_belief_id = supersede_id
        superseded_belief.updated_at = datetime.now(UTC).isoformat()

        # Update store and graph
        if store is not None:
            if not store.put(superseded_belief):
                logger.warning(
                    "[CONTRADICTION_RESOLVER] Failed to persist superseded belief %s",
                    superseded_belief.belief_id,
                )

        self._graph.add_belief(superseded_belief)

        # Add relationship
        rel_id = f"supersedes-{superseded_id}-{supersede_id}"
        rel = BeliefRelationship(
            relationship_id=rel_id,
            source_belief_id=supersede_id,
            target_belief_id=superseded_id,
            relationship_type=RelationshipType.SUPERSEDES.value,
            strength=1.0,
            evidence_refs=supersede_belief.evidence_refs,
        )
        self._graph.add_relationship(rel)

        resolution = AppliedResolution(
            resolution_id=self._generate_resolution_id(suggestion),
            conflict_id=suggestion.conflict_id,
            resolution_type=suggestion.resolution_type,
            belief_id=superseded_id,
        )
        self._resolution_history.append(resolution)

        return resolution

    def get_resolution_history(self) -> list[AppliedResolution]:
        """Get all applied resolutions."""
        return self._resolution_history

    def explain_resolution(self, resolution: AppliedResolution) -> str:
        """Generate human-readable explanation of a resolution."""
        lines = [
            f"Resolution: {resolution.resolution_id}",
            f"Type: {resolution.resolution_type}",
            f"Applied: {resolution.applied_at}",
        ]

        if resolution.belief_id:
            lines.append(f"Belief affected: {resolution.belief_id}")

        if (
            resolution.previous_confidence is not None
            and resolution.new_confidence is not None
        ):
            lines.append(
                f"Confidence changed: {resolution.previous_confidence:.2f} -> {resolution.new_confidence:.2f}"
            )

        if resolution.archived:
            lines.append("Belief was archived.")

        if resolution.merged_into:
            lines.append(f"Belief was merged into: {resolution.merged_into}")

        return "\n".join(lines)

    def get_suggestions_for_conflict(
        self, conflict_id: str
    ) -> list[ResolutionSuggestion]:
        """Get pending suggestions for a conflict."""
        return self._pending_suggestions.get(conflict_id, [])

    @staticmethod
    def _generate_suggestion_id(conflict_id: str, suffix: str) -> str:
        """Generate unique suggestion ID."""
        return hashlib.sha256(f"{conflict_id}:{suffix}".encode()).hexdigest()[:16]

    @staticmethod
    def _generate_resolution_id(suggestion: ResolutionSuggestion) -> str:
        """Generate unique resolution ID."""
        return hashlib.sha256(
            f"{suggestion.suggestion_id}:{suggestion.resolution_type}".encode()
        ).hexdigest()[:16]

    def get_conflict_summary(self) -> dict[str, Any]:
        """Get summary of conflicts and resolution status."""
        return {
            "total_conflicts": len(self._pending_suggestions),
            "resolved_conflicts": sum(
                1
                for r in self._resolution_history
                if r.conflict_id not in self._pending_suggestions
            ),
            "pending_conflicts": len(self._pending_suggestions),
            "resolution_types_applied": list(
                set(r.resolution_type for r in self._resolution_history)
            ),
        }
