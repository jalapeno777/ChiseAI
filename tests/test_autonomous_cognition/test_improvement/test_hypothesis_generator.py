"""Tests for hypothesis generator."""

from __future__ import annotations

from autonomous_cognition.improvement.hypothesis_generator import (
    Hypothesis,
    HypothesisGenerator,
    HypothesisGeneratorConfig,
)


class TestHypothesis:
    """Tests for Hypothesis dataclass."""

    def test_creation(self):
        """Test hypothesis creation."""
        hyp = Hypothesis(
            hypothesis_id="hyp-1",
            title="Test hypothesis",
            rationale="Testing",
            target_component="test",
            expected_uplift_pct=2.5,
        )
        assert hyp.hypothesis_id == "hyp-1"
        assert hyp.title == "Test hypothesis"
        assert hyp.priority == 3  # default

    def test_to_dict(self):
        """Test serialization."""
        hyp = Hypothesis(
            hypothesis_id="hyp-1",
            title="Test",
            rationale="Testing",
            target_component="test",
            expected_uplift_pct=1.0,
        )
        d = hyp.to_dict()
        assert d["hypothesis_id"] == "hyp-1"
        assert d["target_component"] == "test"


class TestHypothesisGeneratorConfig:
    """Tests for HypothesisGeneratorConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = HypothesisGeneratorConfig()
        assert config.min_score_threshold == 0.8
        assert config.conflict_weight == 1.0
        assert config.max_hypotheses == 5

    def test_custom(self):
        """Test custom configuration."""
        config = HypothesisGeneratorConfig(
            min_score_threshold=0.7,
            conflict_weight=2.0,
            max_hypotheses=3,
        )
        assert config.min_score_threshold == 0.7
        assert config.conflict_weight == 2.0
        assert config.max_hypotheses == 3


class TestHypothesisGenerator:
    """Tests for HypothesisGenerator."""

    def test_generate_below_threshold(self):
        """Test generation when score is below threshold."""
        generator = HypothesisGenerator()
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.75, "retrieval_score": 0.7},
            conflicts_count=0,
        )
        assert len(hypotheses) >= 1
        assert any(h.target_component == "retrieval" for h in hypotheses)

    def test_generate_with_conflicts(self):
        """Test generation when conflicts are detected."""
        generator = HypothesisGenerator()
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.85},
            conflicts_count=3,
        )
        assert len(hypotheses) >= 1
        assert any(h.target_component == "belief_engine" for h in hypotheses)

    def test_generate_with_poor_sharpe(self):
        """Test generation when portfolio sharpe is low."""
        generator = HypothesisGenerator()
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.85},
            conflicts_count=0,
            portfolio_metrics={"sharpe": 0.9, "sortino": 1.0},
        )
        assert len(hypotheses) >= 1
        assert any(h.target_component == "portfolio" for h in hypotheses)

    def test_generate_default_when_healthy(self):
        """Test default hypothesis when system is healthy."""
        generator = HypothesisGenerator()
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.9},
            conflicts_count=0,
            portfolio_metrics={"sharpe": 1.2, "sortino": 1.3},
        )
        assert len(hypotheses) >= 1
        # Should have calibration hypothesis
        assert any(h.target_component == "calibration" for h in hypotheses)

    def test_generate_from_seed(self):
        """Test deterministic generation from seed."""
        generator = HypothesisGenerator()
        results1 = generator.generate_from_seed("test-seed", count=3)
        results2 = generator.generate_from_seed("test-seed", count=3)
        assert len(results1) == len(results2) == 3
        # Same seed should produce same hypothesis_ids
        assert results1[0].hypothesis_id == results2[0].hypothesis_id

    def test_generate_max_hypotheses(self):
        """Test max hypotheses limit."""
        config = HypothesisGeneratorConfig(max_hypotheses=2)
        generator = HypothesisGenerator(config)
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.5},
            conflicts_count=5,
            portfolio_metrics={"sharpe": 0.8},
        )
        assert len(hypotheses) <= config.max_hypotheses

    def test_hypotheses_sorted_by_priority(self):
        """Test that hypotheses are sorted by priority."""
        generator = HypothesisGenerator()
        hypotheses = generator.generate(
            self_assessment={"overall_score": 0.5},
            conflicts_count=3,
            portfolio_metrics={"sharpe": 0.8},
        )
        # Verify sorted by priority (ascending)
        priorities = [h.priority for h in hypotheses]
        assert priorities == sorted(priorities)
