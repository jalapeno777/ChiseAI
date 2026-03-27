"""Champion-challenger evaluation for strategy promotion decisions.

This module provides the ChampionChallengerEngine class which coordinates
model registry with autonomous gate policy for comparing champion vs challenger
strategies and making promotion decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autonomous_cognition.policy_engine import AutonomousPolicyEngine, GateDecision


@dataclass
class EvaluationResult:
    """Result of champion-challenger evaluation.

    Attributes:
        candidate_id: ID of the evaluated candidate
        version_id: Model registry version ID
        metrics: Metrics used for evaluation
        gate_decision: Gate evaluation result
        promoted: Whether the candidate was promoted
        reason: Explanation for the decision
        champion_version_id: Current champion version (if any)
    """

    candidate_id: str
    version_id: str
    metrics: dict[str, float]
    gate_decision: GateDecision
    promoted: bool
    reason: str
    champion_version_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "candidate_id": self.candidate_id,
            "version_id": self.version_id,
            "metrics": self.metrics,
            "gate_decision": {
                "passed": self.gate_decision.passed,
                "failed_gates": self.gate_decision.failed_gates,
            },
            "promoted": self.promoted,
            "reason": self.reason,
            "champion_version_id": self.champion_version_id,
            "metadata": self.metadata,
        }


@dataclass
class ComparisonResult:
    """Result of comparing champion vs challenger.

    Attributes:
        champion_id: Champion model ID
        challenger_id: Challenger model ID
        champion_metrics: Champion performance metrics
        challenger_metrics: Challenger performance metrics
        winner: Which is better: 'champion', 'challenger', or 'tie'
        recommendation: Recommendation for action
    """

    champion_id: str
    challenger_id: str
    champion_metrics: dict[str, float]
    challenger_metrics: dict[str, float]
    winner: str
    recommendation: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "champion_id": self.champion_id,
            "challenger_id": self.challenger_id,
            "champion_metrics": self.champion_metrics,
            "challenger_metrics": self.challenger_metrics,
            "winner": self.winner,
            "recommendation": self.recommendation,
            "metadata": self.metadata,
        }


class ChampionChallengerEngine:
    """Coordinates model registry with autonomous gate policy.

    Evaluates candidates against champion strategies using policy gates
    and determines promotion decisions.

    Example:
        >>> engine = ChampionChallengerEngine()
        >>> result = engine.evaluate_candidate(
        ...     candidate_id="strategy_v2",
        ...     metrics={"sharpe": 1.2, "ece": 0.08, "drawdown": 0.15}
        ... )
    """

    def __init__(
        self,
        policy_engine: AutonomousPolicyEngine | None = None,
    ):
        """Initialize the champion-challenger engine.

        Args:
            policy_engine: Optional policy engine. Uses default if not provided.
        """
        self._policy = policy_engine or AutonomousPolicyEngine()

    def evaluate_candidate(
        self,
        candidate_id: str,
        metrics: dict[str, float],
        model_path: str = "/tmp/autocog_candidate.bin",
    ) -> EvaluationResult:
        """Evaluate a candidate for promotion.

        Runs the candidate through gate evaluation and returns the result.

        Args:
            candidate_id: Unique identifier for the candidate
            metrics: Performance metrics (sharpe, ece, drawdown, etc.)
            model_path: Path to model artifact

        Returns:
            EvaluationResult with promotion decision
        """
        # Evaluate against promotion gates
        gate_decision = self._policy.evaluate_promotion_gates(metrics)

        if not gate_decision.passed:
            reason = f"gates_failed:{','.join(gate_decision.failed_gates)}"
            return EvaluationResult(
                candidate_id=candidate_id,
                version_id=f"ver-{candidate_id}",
                metrics=metrics,
                gate_decision=gate_decision,
                promoted=False,
                reason=reason,
                metadata={"gate_evaluation": True},
            )

        return EvaluationResult(
            candidate_id=candidate_id,
            version_id=f"ver-{candidate_id}",
            metrics=metrics,
            gate_decision=gate_decision,
            promoted=True,
            reason="all_gates_passed",
            metadata={"gate_evaluation": True, "promoted_at": "now"},
        )

    def compare(
        self,
        champion_id: str,
        champion_metrics: dict[str, float],
        challenger_id: str,
        challenger_metrics: dict[str, float],
    ) -> ComparisonResult:
        """Compare champion vs challenger strategies.

        Args:
            champion_id: ID of the champion strategy
            champion_metrics: Champion performance metrics
            challenger_id: ID of the challenger strategy
            challenger_metrics: Challenger performance metrics

        Returns:
            ComparisonResult with winner and recommendation
        """

        # Calculate composite scores
        def score(m: dict[str, float]) -> float:
            """Score based on weighted metrics."""
            return (
                m.get("sharpe", 0.0) * 0.30
                + m.get("sortino", 0.0) * 0.20
                - m.get("drawdown", 0.0) * 0.30
                - m.get("ece", 0.0) * 0.20
            )

        champion_score = score(champion_metrics)
        challenger_score = score(challenger_metrics)

        score_delta = challenger_score - champion_score

        # Determine winner
        if challenger_score > champion_score + 0.05:  # 5% margin
            winner = "challenger"
            recommendation = f"promote_challenger (score delta: {score_delta:.3f})"
        elif champion_score > challenger_score + 0.05:
            winner = "champion"
            recommendation = f"keep_champion (score delta: {score_delta:.3f})"
        else:
            winner = "tie"
            recommendation = "retain_champion (no significant improvement)"

        return ComparisonResult(
            champion_id=champion_id,
            challenger_id=challenger_id,
            champion_metrics=champion_metrics,
            challenger_metrics=challenger_metrics,
            winner=winner,
            recommendation=recommendation,
            metadata={
                "champion_score": round(champion_score, 4),
                "challenger_score": round(challenger_score, 4),
                "score_delta": round(score_delta, 4),
            },
        )

    def evaluate_batch(
        self,
        candidates: list[tuple[str, dict[str, float]]],
    ) -> list[EvaluationResult]:
        """Evaluate multiple candidates.

        Args:
            candidates: List of (candidate_id, metrics) tuples

        Returns:
            List of EvaluationResults in evaluation order
        """
        results = []
        for candidate_id, metrics in candidates:
            result = self.evaluate_candidate(candidate_id, metrics)
            results.append(result)
        return results

    def get_promotion_ranking(
        self, results: list[EvaluationResult]
    ) -> list[EvaluationResult]:
        """Rank evaluation results by composite score.

        Args:
            results: List of EvaluationResults to rank

        Returns:
            Sorted list with highest scoring first
        """
        ranked = []
        for r in results:
            score = (
                r.metrics.get("sharpe", 0.0) * 0.30
                + r.metrics.get("sortino", 0.0) * 0.20
                - r.metrics.get("drawdown", 0.0) * 0.30
                - r.metrics.get("ece", 0.0) * 0.20
            )
            ranked.append((score, r))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in ranked]
