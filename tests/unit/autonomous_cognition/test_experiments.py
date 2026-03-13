"""Tests for Phase 3 experiment and champion-challenger flow."""

from __future__ import annotations

from autonomous_cognition.experiments.champion_challenger import (
    ChampionChallengerEngine,
)
from autonomous_cognition.experiments.hypothesis_generator import HypothesisGenerator
from autonomous_cognition.experiments.portfolio_policy_lab import PortfolioPolicyLab


def test_hypothesis_generation_non_empty() -> None:
    """Generator should always return at least one hypothesis."""
    generator = HypothesisGenerator()
    hypotheses = generator.generate(self_assessment={"overall_score": 0.95}, conflicts_count=0)
    assert len(hypotheses) >= 1


def test_portfolio_lab_metrics_shape() -> None:
    """Policy lab should produce complete metric bundle."""
    generator = HypothesisGenerator()
    lab = PortfolioPolicyLab()
    hypothesis = generator.generate(
        self_assessment={"overall_score": 0.7}, conflicts_count=1
    )[0]
    result = lab.run(hypothesis)
    metrics = result.to_metrics()
    assert set(metrics.keys()) == {"sharpe", "sortino", "drawdown", "ece"}


def test_champion_challenger_rejects_failing_metrics() -> None:
    """Failing gates should reject candidate promotion."""
    engine = ChampionChallengerEngine()
    outcome = engine.evaluate_candidate(
        candidate_id="hyp-fail",
        metrics={"sharpe": 0.8, "sortino": 0.9, "drawdown": 0.3, "ece": 0.25},
    )
    assert outcome.promoted is False

