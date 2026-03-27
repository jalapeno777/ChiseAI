"""Hypothesis generation from performance data for strategy improvement.

This module provides the HypothesisGenerator class which generates bounded
improvement hypotheses from assessment data, belief consistency metrics,
and portfolio performance signals.

It integrates with the improvement cycle orchestrator to feed the PROPOSING phase.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Hypothesis:
    """Candidate hypothesis for strategy/portfolio improvement.

    Attributes:
        hypothesis_id: Unique identifier for this hypothesis
        title: Short descriptive title
        rationale: Explanation of why this hypothesis was generated
        target_component: Component or system this targets (e.g., 'retrieval', 'belief_engine')
        expected_uplift_pct: Expected improvement percentage
        priority: Priority level (1=highest, 5=lowest)
        metadata: Additional context and parameters
    """

    hypothesis_id: str
    title: str
    rationale: str
    target_component: str
    expected_uplift_pct: float
    priority: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "rationale": self.rationale,
            "target_component": self.target_component,
            "expected_uplift_pct": self.expected_uplift_pct,
            "priority": self.priority,
            "metadata": self.metadata,
        }


@dataclass
class HypothesisGeneratorConfig:
    """Configuration for hypothesis generation.

    Attributes:
        min_score_threshold: Score below which memory/retrieval hypothesis is generated
        conflict_weight: Weight factor for belief conflict detection
        max_hypotheses: Maximum number of hypotheses to generate per cycle
        uplift_floor: Minimum expected uplift percentage to include hypothesis
    """

    min_score_threshold: float = 0.8
    conflict_weight: float = 1.0
    max_hypotheses: int = 5
    uplift_floor: float = 0.5


class HypothesisGenerator:
    """Generates bounded improvement hypotheses from performance data.

    Analyzes self-assessment scores, belief conflict counts, and portfolio
    metrics to generate targeted hypotheses for the improvement cycle.

    Example:
        >>> config = HypothesisGeneratorConfig()
        >>> generator = HypothesisGenerator(config)
        >>> hypotheses = generator.generate(
        ...     self_assessment={"overall_score": 0.75, "retrieval_score": 0.7},
        ...     conflicts_count=3,
        ...     portfolio_metrics={"sharpe": 0.9, "sortino": 1.0}
        ... )
    """

    def __init__(self, config: HypothesisGeneratorConfig | None = None):
        """Initialize the hypothesis generator.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self._config = config or HypothesisGeneratorConfig()

    def generate(
        self,
        self_assessment: dict[str, Any],
        conflicts_count: int = 0,
        portfolio_metrics: dict[str, float] | None = None,
    ) -> list[Hypothesis]:
        """Generate deterministic hypotheses from current system state.

        Args:
            self_assessment: Assessment data containing overall_score, component scores
            conflicts_count: Number of detected belief conflicts
            portfolio_metrics: Optional portfolio performance metrics (sharpe, sortino, etc.)

        Returns:
            List of generated hypotheses, sorted by priority
        """
        hypotheses: list[Hypothesis] = []
        portfolio_metrics = portfolio_metrics or {}

        # Memory/retrieval hypothesis
        score = float(self_assessment.get("overall_score", 0.0))
        if score < self._config.min_score_threshold:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                    title="Improve memory retrieval relevance",
                    rationale=f"Assessment score {score:.2f} below threshold {self._config.min_score_threshold}",
                    target_component="retrieval",
                    expected_uplift_pct=max(
                        2.0, (self._config.min_score_threshold - score) * 10
                    ),
                    priority=1,
                    metadata={
                        "current_score": score,
                        "threshold": self._config.min_score_threshold,
                    },
                )
            )

        # Belief consistency hypothesis
        weighted_conflicts = conflicts_count * self._config.conflict_weight
        if weighted_conflicts > 0:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                    title="Strengthen belief consistency weighting",
                    rationale=f"Detected {conflicts_count} contradictions suggesting belief drift",
                    target_component="belief_engine",
                    expected_uplift_pct=min(3.0, 0.5 + weighted_conflicts * 0.5),
                    priority=2,
                    metadata={
                        "conflicts_count": conflicts_count,
                        "weighted": weighted_conflicts,
                    },
                )
            )

        # Portfolio performance hypothesis
        sharpe = portfolio_metrics.get("sharpe", 1.0)
        if sharpe < 1.1:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                    title="Improve risk-adjusted returns",
                    rationale=f"Sharpe ratio {sharpe:.2f} below target 1.1",
                    target_component="portfolio",
                    expected_uplift_pct=max(1.5, (1.1 - sharpe) * 10),
                    priority=2,
                    metadata={"sharpe": sharpe, "target_sharpe": 1.1},
                )
            )

        # Calibration tuning (default when no severe findings)
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"hyp-{uuid.uuid4().hex[:8]}",
                    title="Tune confidence calibration thresholds",
                    rationale="No severe findings; optimize for incremental gain",
                    target_component="calibration",
                    expected_uplift_pct=1.0,
                    priority=4,
                    metadata={"reason": "incremental_improvement"},
                )
            )

        # Sort by priority and limit
        hypotheses.sort(key=lambda h: h.priority)
        return hypotheses[: self._config.max_hypotheses]

    def generate_from_seed(self, seed: str, count: int = 3) -> list[Hypothesis]:
        """Generate deterministic hypotheses from a seed string.

        Useful for reproducibility and testing.

        Args:
            seed: Seed string for deterministic generation
            count: Number of hypotheses to generate

        Returns:
            List of generated hypotheses
        """
        seed_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        seed_int = int(seed_hash[:8], 16)

        hypotheses: list[Hypothesis] = []
        components = ["retrieval", "belief_engine", "portfolio", "calibration"]
        titles = [
            "Improve retrieval latency",
            "Strengthen belief consistency",
            "Optimize portfolio allocation",
            "Tune calibration thresholds",
        ]

        for i in range(min(count, len(components))):
            idx = (seed_int + i) % len(components)
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"hyp-seed-{seed_hash[:8]}-{i}",
                    title=titles[idx],
                    rationale=f"Generated from seed for component {components[idx]}",
                    target_component=components[idx],
                    expected_uplift_pct=0.5 + ((seed_int + i) % 10) * 0.2,
                    priority=(i % 3) + 1,
                    metadata={"seed": seed, "index": i},
                )
            )

        return hypotheses
