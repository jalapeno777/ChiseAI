"""Hypothesis generation from self-assessment and belief conflicts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Hypothesis:
    """Candidate hypothesis for strategy/portfolio improvement."""

    hypothesis_id: str
    title: str
    rationale: str
    target_component: str
    expected_uplift_pct: float


class HypothesisGenerator:
    """Generates bounded improvement hypotheses."""

    def generate(
        self,
        self_assessment: dict[str, Any],
        conflicts_count: int,
    ) -> list[Hypothesis]:
        """Generate deterministic hypotheses from current system state."""
        hypotheses: list[Hypothesis] = []
        score = float(self_assessment.get("overall_score", 0.0))
        if score < 0.8:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="hyp-memory-retrieval",
                    title="Improve memory retrieval relevance",
                    rationale="Assessment score indicates retrieval/memory pressure.",
                    target_component="retrieval",
                    expected_uplift_pct=3.0,
                )
            )
        if conflicts_count > 0:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="hyp-belief-consistency",
                    title="Strengthen belief consistency weighting",
                    rationale="Detected contradictions suggest belief weighting drift.",
                    target_component="belief_engine",
                    expected_uplift_pct=2.0,
                )
            )
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="hyp-calibration-tune",
                    title="Tune confidence calibration thresholds",
                    rationale="No severe findings; optimize for incremental gain.",
                    target_component="calibration",
                    expected_uplift_pct=1.0,
                )
            )
        return hypotheses
