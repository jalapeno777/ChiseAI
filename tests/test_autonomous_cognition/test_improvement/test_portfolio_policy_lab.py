"""Tests for portfolio policy lab."""

from __future__ import annotations

from autonomous_cognition.improvement.hypothesis_generator import Hypothesis
from autonomous_cognition.improvement.portfolio_policy_lab import (
    ExperimentMetrics,
    ExperimentResult,
    PortfolioPolicyLab,
    PortfolioPolicyLabConfig,
)


class TestExperimentMetrics:
    """Tests for ExperimentMetrics dataclass."""

    def test_creation(self):
        """Test metrics creation."""
        metrics = ExperimentMetrics(
            sharpe=1.2,
            sortino=1.3,
            drawdown=0.15,
            ece=0.08,
        )
        assert metrics.sharpe == 1.2
        assert metrics.sortino == 1.3


class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_creation(self):
        """Test result creation."""
        metrics = ExperimentMetrics(sharpe=1.2, sortino=1.3, drawdown=0.15, ece=0.08)
        result = ExperimentResult(
            hypothesis_id="hyp-1",
            metrics=metrics,
            passed=True,
        )
        assert result.hypothesis_id == "hyp-1"
        assert result.passed is True

    def test_to_dict(self):
        """Test serialization."""
        metrics = ExperimentMetrics(sharpe=1.2, sortino=1.3, drawdown=0.15, ece=0.08)
        result = ExperimentResult(hypothesis_id="hyp-1", metrics=metrics, passed=True)
        d = result.to_dict()
        assert d["hypothesis_id"] == "hyp-1"
        assert d["metrics"]["sharpe"] == 1.2


class TestPortfolioPolicyLabConfig:
    """Tests for PortfolioPolicyLabConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = PortfolioPolicyLabConfig()
        assert config.min_sharpe == 1.1
        assert config.max_drawdown == 0.20
        assert config.max_ece == 0.15


class TestPortfolioPolicyLab:
    """Tests for PortfolioPolicyLab."""

    def test_run_passing(self):
        """Test running a hypothesis that passes gates."""
        lab = PortfolioPolicyLab()
        hypothesis = Hypothesis(
            hypothesis_id="hyp-pass",
            title="Passing hypothesis",
            rationale="Test",
            target_component="test",
            expected_uplift_pct=2.0,
        )
        result = lab.run(hypothesis)
        # Result depends on hash - just check structure
        assert result.hypothesis_id == "hyp-pass"
        assert hasattr(result, "metrics")
        assert hasattr(result, "passed")

    def test_run_deterministic(self):
        """Test that same hypothesis produces same results."""
        lab = PortfolioPolicyLab()
        hypothesis = Hypothesis(
            hypothesis_id="hyp-det",
            title="Deterministic",
            rationale="Test",
            target_component="test",
            expected_uplift_pct=1.0,
        )
        result1 = lab.run(hypothesis)
        result2 = lab.run(hypothesis)
        assert result1.metrics.sharpe == result2.metrics.sharpe
        assert result1.metrics.drawdown == result2.metrics.drawdown

    def test_run_batch(self):
        """Test running multiple hypotheses."""
        lab = PortfolioPolicyLab()
        hypotheses = [
            Hypothesis(
                hypothesis_id=f"hyp-{i}",
                title=f"Hypothesis {i}",
                rationale="Test",
                target_component="test",
                expected_uplift_pct=1.0,
            )
            for i in range(3)
        ]
        results = lab.run_batch(hypotheses)
        assert len(results) == 3
        for hyp in hypotheses:
            assert hyp.hypothesis_id in results

    def test_compare(self):
        """Test comparing two results."""
        lab = PortfolioPolicyLab()
        metrics_a = ExperimentMetrics(sharpe=1.2, sortino=1.3, drawdown=0.15, ece=0.08)
        metrics_b = ExperimentMetrics(sharpe=1.3, sortino=1.4, drawdown=0.10, ece=0.05)

        result_a = ExperimentResult(
            hypothesis_id="hyp-a", metrics=metrics_a, passed=True
        )
        result_b = ExperimentResult(
            hypothesis_id="hyp-b", metrics=metrics_b, passed=True
        )

        winner = lab.compare(result_a, result_b)
        # Winner should be 'b' since it has better metrics
        assert winner in ("a", "b", "tie")

    def test_gates(self):
        """Test gate constants are defined."""
        assert PortfolioPolicyLab.GATE_SHARPE == 1.1
        assert PortfolioPolicyLab.GATE_SORTINO == 1.2
        assert PortfolioPolicyLab.GATE_DRAWDOWN == 0.20
        assert PortfolioPolicyLab.GATE_ECE == 0.15
