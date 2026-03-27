"""Tests for champion-challenger evaluator."""

from __future__ import annotations

from autonomous_cognition.improvement.champion_challenger_evaluator import (
    ChampionChallengerEngine,
    ComparisonResult,
    EvaluationResult,
)
from autonomous_cognition.policy_engine import GateDecision


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_creation(self):
        """Test result creation."""
        gate = GateDecision(passed=True)
        result = EvaluationResult(
            candidate_id="cand-1",
            version_id="ver-1",
            metrics={"sharpe": 1.2, "ece": 0.08},
            gate_decision=gate,
            promoted=True,
            reason="all_gates_passed",
        )
        assert result.candidate_id == "cand-1"
        assert result.promoted is True

    def test_to_dict(self):
        """Test serialization."""
        gate = GateDecision(passed=True)
        result = EvaluationResult(
            candidate_id="cand-1",
            version_id="ver-1",
            metrics={"sharpe": 1.2},
            gate_decision=gate,
            promoted=True,
            reason="ok",
        )
        d = result.to_dict()
        assert d["candidate_id"] == "cand-1"
        assert d["promoted"] is True


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_creation(self):
        """Test result creation."""
        result = ComparisonResult(
            champion_id="champ-1",
            challenger_id="chall-1",
            champion_metrics={"sharpe": 1.1},
            challenger_metrics={"sharpe": 1.2},
            winner="challenger",
            recommendation="promote_challenger",
        )
        assert result.champion_id == "champ-1"
        assert result.winner == "challenger"

    def test_to_dict(self):
        """Test serialization."""
        result = ComparisonResult(
            champion_id="champ-1",
            challenger_id="chall-1",
            champion_metrics={"sharpe": 1.1},
            challenger_metrics={"sharpe": 1.2},
            winner="challenger",
            recommendation="promote",
        )
        d = result.to_dict()
        assert d["winner"] == "challenger"


class TestChampionChallengerEngine:
    """Tests for ChampionChallengerEngine."""

    def test_evaluate_candidate_passing(self):
        """Test evaluating a candidate that passes gates."""
        engine = ChampionChallengerEngine()
        result = engine.evaluate_candidate(
            candidate_id="cand-1",
            metrics={"sharpe": 1.2, "ece": 0.08, "drawdown": 0.15},
        )
        assert result.candidate_id == "cand-1"
        assert result.promoted is True
        assert result.gate_decision.passed is True

    def test_evaluate_candidate_failing(self):
        """Test evaluating a candidate that fails gates."""
        engine = ChampionChallengerEngine()
        result = engine.evaluate_candidate(
            candidate_id="cand-2",
            metrics={"sharpe": 0.8, "ece": 0.25, "drawdown": 0.30},
        )
        assert result.candidate_id == "cand-2"
        assert result.promoted is False
        assert result.gate_decision.passed is False
        assert len(result.gate_decision.failed_gates) > 0

    def test_evaluate_batch(self):
        """Test evaluating multiple candidates."""
        engine = ChampionChallengerEngine()
        candidates = [
            ("cand-1", {"sharpe": 1.2, "ece": 0.08, "drawdown": 0.15}),
            ("cand-2", {"sharpe": 0.8, "ece": 0.25, "drawdown": 0.30}),
        ]
        results = engine.evaluate_batch(candidates)
        assert len(results) == 2
        # First should pass, second should fail
        assert results[0].promoted is True
        assert results[1].promoted is False

    def test_compare_challenger_wins(self):
        """Test comparison where challenger wins."""
        engine = ChampionChallengerEngine()
        result = engine.compare(
            champion_id="champ-1",
            champion_metrics={
                "sharpe": 1.0,
                "sortino": 1.1,
                "drawdown": 0.20,
                "ece": 0.12,
            },
            challenger_id="chall-1",
            challenger_metrics={
                "sharpe": 1.3,
                "sortino": 1.4,
                "drawdown": 0.10,
                "ece": 0.05,
            },
        )
        assert result.winner == "challenger"
        assert "promote" in result.recommendation.lower()

    def test_compare_champion_wins(self):
        """Test comparison where champion wins."""
        engine = ChampionChallengerEngine()
        result = engine.compare(
            champion_id="champ-1",
            champion_metrics={
                "sharpe": 1.3,
                "sortino": 1.4,
                "drawdown": 0.10,
                "ece": 0.05,
            },
            challenger_id="chall-1",
            challenger_metrics={
                "sharpe": 1.0,
                "sortino": 1.1,
                "drawdown": 0.20,
                "ece": 0.12,
            },
        )
        assert result.winner == "champion"
        assert (
            "keep" in result.recommendation.lower()
            or "retain" in result.recommendation.lower()
        )

    def test_compare_tie(self):
        """Test comparison with tie."""
        engine = ChampionChallengerEngine()
        result = engine.compare(
            champion_id="champ-1",
            champion_metrics={
                "sharpe": 1.15,
                "sortino": 1.2,
                "drawdown": 0.15,
                "ece": 0.08,
            },
            challenger_id="chall-1",
            challenger_metrics={
                "sharpe": 1.16,
                "sortino": 1.21,
                "drawdown": 0.15,
                "ece": 0.08,
            },
        )
        assert result.winner == "tie"

    def test_get_promotion_ranking(self):
        """Test ranking candidates by score."""
        engine = ChampionChallengerEngine()
        results = [
            EvaluationResult(
                candidate_id="cand-1",
                version_id="ver-1",
                metrics={"sharpe": 1.0, "sortino": 1.1, "drawdown": 0.15, "ece": 0.10},
                gate_decision=GateDecision(passed=True),
                promoted=True,
                reason="ok",
            ),
            EvaluationResult(
                candidate_id="cand-2",
                version_id="ver-2",
                metrics={"sharpe": 1.5, "sortino": 1.6, "drawdown": 0.08, "ece": 0.05},
                gate_decision=GateDecision(passed=True),
                promoted=True,
                reason="ok",
            ),
            EvaluationResult(
                candidate_id="cand-3",
                version_id="ver-3",
                metrics={"sharpe": 0.9, "sortino": 1.0, "drawdown": 0.25, "ece": 0.20},
                gate_decision=GateDecision(passed=True),
                promoted=True,
                reason="ok",
            ),
        ]
        ranked = engine.get_promotion_ranking(results)
        # cand-2 should be first (highest score)
        assert ranked[0].candidate_id == "cand-2"
        # cand-3 should be last
        assert ranked[-1].candidate_id == "cand-3"
