"""Consistency checker for belief contradiction detection."""

from __future__ import annotations

import hashlib
from typing import Any

from autonomous_cognition.beliefs.models import Belief, BeliefConflict
from governance.memory.contradiction import ContradictionDetector


class BeliefConsistencyChecker:
    """Find contradictions between active beliefs."""

    def __init__(self, contradiction_detector: ContradictionDetector | None = None):
        self._detector = contradiction_detector or ContradictionDetector()

    def detect_conflicts(self, beliefs: list[Belief]) -> list[BeliefConflict]:
        """Detect conflicts among beliefs."""
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
