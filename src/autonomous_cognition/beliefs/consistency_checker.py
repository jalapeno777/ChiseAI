"""Consistency checker for belief contradiction detection."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from autonomous_cognition.beliefs.audit_writer import (
    BeliefMutationAuditWriter,
    BeliefMutationEvent,
)
from autonomous_cognition.beliefs.models import Belief, BeliefConflict
from governance.memory.contradiction import ContradictionDetector

TEST_DOMAINS: frozenset[str] = frozenset({"debug", "test"})


class BeliefConsistencyChecker:
    """Find contradictions between active beliefs with additional consistency checks."""

    DEFAULT_CONFIDENCE_THRESHOLD = 0.15
    DEFAULT_FRESHNESS_DAYS = 30

    def __init__(
        self,
        contradiction_detector: ContradictionDetector | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    ):
        self._detector = contradiction_detector or ContradictionDetector()
        self._confidence_threshold = confidence_threshold
        self._freshness_days = freshness_days
        self._audit_writer = BeliefMutationAuditWriter()

    def check_consistency(self, beliefs: list[Belief]) -> list[BeliefConflict]:
        """Full consistency check returning all detected conflicts.

        Combines contradiction detection, confidence threshold checks,
        domain boundary validation, and evidence freshness validation.
        """
        logger = logging.getLogger(__name__)

        original_count = len(beliefs)
        beliefs = [b for b in beliefs if b.domain not in TEST_DOMAINS]
        filtered_count = original_count - len(beliefs)
        if filtered_count > 0:
            logger.debug(
                "[CONSISTENCY_CHECKER] Filtered out %d test/debug domain beliefs",
                filtered_count,
            )

        logger.info(
            "[CONSISTENCY_CHECKER] Starting consistency check for %d beliefs",
            len(beliefs),
        )

        conflicts: list[BeliefConflict] = []

        # 1. Contradiction detection
        contradiction_conflicts = self.detect_conflicts(beliefs)
        conflicts.extend(contradiction_conflicts)
        logger.info(
            "[CONSISTENCY_CHECKER] Found %d contradiction conflicts",
            len(contradiction_conflicts),
        )

        # 2. Confidence threshold conflicts
        confidence_conflicts = self._check_confidence_thresholds(beliefs)
        conflicts.extend(confidence_conflicts)
        logger.info(
            "[CONSISTENCY_CHECKER] Found %d confidence threshold conflicts",
            len(confidence_conflicts),
        )

        # 3. Domain boundary validation
        domain_conflicts = self._check_domain_boundaries(beliefs)
        conflicts.extend(domain_conflicts)
        logger.info(
            "[CONSISTENCY_CHECKER] Found %d domain boundary conflicts",
            len(domain_conflicts),
        )

        # 4. Evidence freshness validation
        freshness_conflicts = self._check_evidence_freshness(beliefs)
        conflicts.extend(freshness_conflicts)
        logger.info(
            "[CONSISTENCY_CHECKER] Found %d evidence freshness conflicts",
            len(freshness_conflicts),
        )

        logger.info(
            "[CONSISTENCY_CHECKER] Consistency check complete: %d total conflicts",
            len(conflicts),
        )

        # Emit audit events for detected conflicts
        self._emit_conflict_audit(beliefs, conflicts)

        return conflicts

    def _emit_conflict_audit(
        self, beliefs: list[Belief], conflicts: list[BeliefConflict]
    ) -> None:
        """Emit audit events for detected belief conflicts.

        Maps conflict detections to BeliefMutationEvent entries via the canonical
        audit writer pipeline (LPUSH + TTL Redis storage). Respects the existing
        feature flag gating in BeliefMutationAuditWriter.is_enabled().

        confidence_before / confidence_after are set to the involved beliefs'
        current confidence values.  No mutation has occurred at detection time,
        so these represent the pre-conflict confidence state for downstream
        analysis.  If a belief_id cannot be resolved (e.g. synthetic IDs like
        "domain:*" or "evidence_system"), the confidence is set to None.
        """
        logger = logging.getLogger(__name__)

        if not conflicts:
            return

        belief_map: dict[str, Belief] = {b.belief_id: b for b in beliefs}

        for conflict in conflicts:
            belief_a = belief_map.get(conflict.belief_id_a)
            belief_b = belief_map.get(conflict.belief_id_b)

            event = BeliefMutationEvent(
                event_id=f"conflict-{conflict.conflict_id}",
                timestamp=datetime.now(UTC).isoformat(),
                actor="BeliefConsistencyChecker",
                belief_key=conflict.belief_id_a,
                mutation_type="conflict_resolution",
                severity=conflict.severity,
                old_value={
                    "belief_id": conflict.belief_id_a,
                    "confidence": belief_a.confidence if belief_a else None,
                },
                new_value={
                    "belief_id": conflict.belief_id_b,
                    "confidence": belief_b.confidence if belief_b else None,
                },
                conflict_resolution={
                    "similarity": conflict.similarity,
                    "belief_id_a": conflict.belief_id_a,
                    "belief_id_b": conflict.belief_id_b,
                },
                applied=False,
                confidence_before=belief_a.confidence if belief_a else None,
                confidence_after=belief_b.confidence if belief_b else None,
                conflict_detected=True,
                conflict_resolution_summary=conflict.reason,
            )

            written = self._audit_writer.write_mutation_event(event)
            if not written:
                logger.debug(
                    "[CONSISTENCY_CHECKER] Could not emit audit event for conflict %s",
                    conflict.conflict_id,
                )

    def _check_confidence_thresholds(
        self, beliefs: list[Belief]
    ) -> list[BeliefConflict]:
        """Find beliefs with similar statements but widely different confidence.

        When two beliefs have high similarity but very different confidence scores,
        this may indicate an inconsistency in how certain we are.
        """
        conflicts: list[BeliefConflict] = []
        for i in range(len(beliefs)):
            for j in range(i + 1, len(beliefs)):
                a = beliefs[i]
                b = beliefs[j]

                # Only check within same domain
                if a.domain != b.domain:
                    continue

                # Skip if same belief
                if a.belief_id == b.belief_id:
                    continue

                # Calculate textual similarity (simple word overlap)
                similarity = self._calculate_textual_similarity(
                    a.statement, b.statement
                )

                # If statements are similar but confidence differs significantly
                if similarity > 0.7:
                    confidence_delta = abs(a.confidence - b.confidence)
                    if confidence_delta > self._confidence_threshold * 3:
                        conflict_id = hashlib.sha256(
                            f"{a.belief_id}:{b.belief_id}:confidence_threshold".encode()
                        ).hexdigest()[:16]
                        conflicts.append(
                            BeliefConflict(
                                conflict_id=conflict_id,
                                belief_id_a=a.belief_id,
                                belief_id_b=b.belief_id,
                                similarity=float(similarity),
                                severity="low",
                                reason=(
                                    f"Confidence inconsistency: both beliefs address similar "
                                    f"topic but confidence delta is {confidence_delta:.3f} "
                                    f"(threshold: {self._confidence_threshold * 3:.3f})"
                                ),
                            )
                        )
        return conflicts

    def _check_domain_boundaries(self, beliefs: list[Belief]) -> list[BeliefConflict]:
        """Detect beliefs that may have incorrect domain assignments.

        When beliefs in the same domain have very different vocabularies or topics,
        it may indicate domain boundary issues.
        """
        conflicts: list[BeliefConflict] = []
        domains: dict[str, list[Belief]] = {}

        # Group beliefs by domain
        for belief in beliefs:
            if belief.status != "active":
                continue
            if belief.domain not in domains:
                domains[belief.domain] = []
            domains[belief.domain].append(belief)

        # Check each domain for internal consistency
        for domain, domain_beliefs in domains.items():
            if len(domain_beliefs) < 2:
                continue

            # Check for outlier beliefs within domain
            for i, belief in enumerate(domain_beliefs):
                other_beliefs = domain_beliefs[:i] + domain_beliefs[i + 1 :]
                avg_similarity = sum(
                    self._calculate_textual_similarity(
                        belief.statement, other.statement
                    )
                    for other in other_beliefs
                ) / len(other_beliefs)

                if avg_similarity < 0.2 and len(domain_beliefs) >= 3:
                    # This belief seems out of place in its domain
                    conflict_id = hashlib.sha256(
                        f"{belief.belief_id}:domain_boundary".encode()
                    ).hexdigest()[:16]
                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=belief.belief_id,
                            belief_id_b=f"domain:{domain}",
                            similarity=float(avg_similarity),
                            severity="low",
                            reason=(
                                f"Belief may belong to different domain: "
                                f"average similarity {avg_similarity:.3f} with domain '{domain}'"
                            ),
                        )
                    )
        return conflicts

    def _check_evidence_freshness(self, beliefs: list[Belief]) -> list[BeliefConflict]:
        """Detect beliefs with stale evidence that may need updating.

        A belief with high confidence but very old evidence may be outdated.
        """
        conflicts: list[BeliefConflict] = []
        now = datetime.now(UTC)

        for belief in beliefs:
            if belief.status != "active":
                continue

            if not belief.evidence_refs:
                # Belief without evidence - may be okay, but check confidence
                if belief.confidence > 0.8:
                    conflict_id = hashlib.sha256(
                        f"{belief.belief_id}:no_evidence_high_confidence".encode()
                    ).hexdigest()[:16]
                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=belief.belief_id,
                            belief_id_b="evidence_system",
                            similarity=1.0,
                            severity="low",
                            reason=(
                                f"High confidence ({belief.confidence:.3f}) belief "
                                f"has no evidence references"
                            ),
                        )
                    )
                continue

            # Check for stale evidence based on belief's updated_at
            try:
                updated = datetime.fromisoformat(
                    belief.updated_at.replace("Z", "+00:00")
                )
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                age_days = (now - updated.astimezone(UTC)).total_seconds() / 86400

                if age_days > self._freshness_days and belief.confidence > 0.7:
                    conflict_id = hashlib.sha256(
                        f"{belief.belief_id}:stale_belief".encode()
                    ).hexdigest()[:16]
                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=belief.belief_id,
                            belief_id_b="freshness_check",
                            similarity=1.0,
                            severity="low",
                            reason=(
                                f"Belief may be stale: {age_days:.1f} days old "
                                f"with confidence {belief.confidence:.3f}"
                            ),
                        )
                    )
            except Exception:
                continue

        return conflicts

    def _calculate_textual_similarity(self, a: str, b: str) -> float:
        """Calculate simple word-overlap similarity between two statements."""
        if not a or not b:
            return 0.0
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a.intersection(tokens_b))
        union = len(tokens_a.union(tokens_b))
        return intersection / union if union > 0 else 0.0

    def detect_conflicts(self, beliefs: list[Belief]) -> list[BeliefConflict]:
        """Detect conflicts among beliefs."""
        beliefs = [b for b in beliefs if b.domain not in TEST_DOMAINS]
        conflicts: list[BeliefConflict] = []
        for i in range(len(beliefs)):
            for j in range(i + 1, len(beliefs)):
                a = beliefs[i]
                b = beliefs[j]
                mem_a = self._belief_to_memory(a)
                mem_b = self._belief_to_memory(b)
                contradiction = self._detector.detect_contradiction(mem_a, mem_b)
                if contradiction is not None:
                    conflict_id = hashlib.sha256(
                        f"{a.belief_id}:{b.belief_id}:{contradiction.reason}".encode()
                    ).hexdigest()[:16]
                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=a.belief_id,
                            belief_id_b=b.belief_id,
                            similarity=float(contradiction.similarity),
                            severity=contradiction.severity,
                            reason=contradiction.reason,
                        )
                    )
                    continue

                # Fallback heuristic for practical contradiction phrasing.
                fallback_reason = self._heuristic_conflict_reason(
                    a.statement, b.statement
                )
                if fallback_reason:
                    conflict_id = hashlib.sha256(
                        f"{a.belief_id}:{b.belief_id}:{fallback_reason}".encode()
                    ).hexdigest()[:16]
                    conflicts.append(
                        BeliefConflict(
                            conflict_id=conflict_id,
                            belief_id_a=a.belief_id,
                            belief_id_b=b.belief_id,
                            similarity=0.8,
                            severity="medium",
                            reason=fallback_reason,
                        )
                    )
        return conflicts

    def _belief_to_memory(self, belief: Belief) -> dict[str, Any]:
        """Map belief to contradiction detector memory shape."""
        return {
            "id": belief.belief_id,
            "content": belief.statement,
            "vector": self._statement_embedding(belief.statement),
        }

    def _statement_embedding(self, text: str, dimensions: int = 32) -> list[float]:
        """Simple deterministic embedding for local conflict checks."""
        if not text:
            return [0.0] * dimensions
        values: list[float] = []
        raw = text.encode("utf-8")
        for idx in range(dimensions):
            h = hashlib.sha256(raw + idx.to_bytes(2, "little")).digest()
            n = int.from_bytes(h[:4], "little")
            values.append((n % 20000) / 10000 - 1.0)
        return values

    def _heuristic_conflict_reason(self, a: str, b: str) -> str | None:
        """Detect contradiction phrasing when vector thresholds miss."""
        if not a or not b:
            return None
        negation_keywords = {
            "no longer",
            "obsolete",
            "invalid",
            "deprecated",
            "override",
            "supersede",
            "replaced",
        }
        lower_a = a.lower()
        lower_b = b.lower()
        tokens_a = set(lower_a.split())
        tokens_b = set(lower_b.split())
        overlap = len(tokens_a.intersection(tokens_b))
        if overlap == 0:
            return None
        has_negation = any(k in lower_a for k in negation_keywords) or any(
            k in lower_b for k in negation_keywords
        )
        if has_negation:
            return "Heuristic contradiction phrase detected with overlapping context"
        return None
