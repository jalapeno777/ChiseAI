"""Tests for hypothesis generator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.strong_system.belief_embeddings import BeliefVector
from src.strong_system.hypothesis_generator import (
    ConfidenceScore,
    GenerationResult,
    GeneratorConfig,
    GeneratorMetrics,
    Hypothesis,
    HypothesisGenerator,
    HypothesisType,
    MarketContext,
    MockLLMProvider,
    ValidationResult,
    ValidationStatus,
)


class TestMockLLMProvider:
    """Tests for MockLLMProvider class."""

    def test_creation(self) -> None:
        """Test creating mock provider."""
        provider = MockLLMProvider()
        assert provider is not None

    def test_generate(self) -> None:
        """Test generating mock response."""
        provider = MockLLMProvider()
        result = provider.generate("system", "user")

        assert "hypotheses" in result
        assert isinstance(result["hypotheses"], list)
        assert len(result["hypotheses"]) > 0

    def test_generate_trend_type(self) -> None:
        """Test generating with trend type hint."""
        provider = MockLLMProvider()
        result = provider.generate("system", "TREND hypothesis")

        assert "hypotheses" in result

    def test_generate_reversal_type(self) -> None:
        """Test generating with reversal type hint."""
        provider = MockLLMProvider()
        result = provider.generate("system", "REVERSAL hypothesis")

        assert "hypotheses" in result


class TestGeneratorMetrics:
    """Tests for GeneratorMetrics class."""

    def test_default_creation(self) -> None:
        """Test creating metrics with defaults."""
        metrics = GeneratorMetrics()
        assert metrics.total_generated == 0
        assert metrics.average_generation_time_ms == 0.0
        assert metrics.average_confidence == 0.0

    def test_update(self) -> None:
        """Test updating metrics."""
        metrics = GeneratorMetrics()

        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            hypothesis_type=HypothesisType.TREND,
            confidence=ConfidenceScore(score=0.8),
        )
        result = GenerationResult(
            hypotheses=[hypothesis],
            generation_time_ms=100.0,
        )

        metrics.update(result)

        assert metrics.total_generated == 1
        assert metrics.average_generation_time_ms == 100.0
        assert metrics.average_confidence == 0.8
        assert metrics.total_by_type["TREND"] == 1

    def test_update_multiple(self) -> None:
        """Test updating with multiple hypotheses."""
        metrics = GeneratorMetrics()

        hypotheses = [
            Hypothesis(
                description="Test1",
                prediction="Up",
                hypothesis_type=HypothesisType.TREND,
                confidence=ConfidenceScore(score=0.8),
            ),
            Hypothesis(
                description="Test2",
                prediction="Down",
                hypothesis_type=HypothesisType.REVERSAL,
                confidence=ConfidenceScore(score=0.6),
            ),
        ]
        result = GenerationResult(hypotheses=hypotheses, generation_time_ms=100.0)

        metrics.update(result)

        assert metrics.total_generated == 2
        assert metrics.total_by_type["TREND"] == 1
        assert metrics.total_by_type["REVERSAL"] == 1
        assert metrics.average_confidence == 0.7

    def test_history_limit(self) -> None:
        """Test that history is limited to 100 entries."""
        metrics = GeneratorMetrics()

        for _ in range(150):
            result = GenerationResult(
                hypotheses=[Hypothesis(description="Test", prediction="Up")],
                generation_time_ms=1.0,
            )
            metrics.update(result)

        assert len(metrics.generation_history) == 100

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = GeneratorMetrics()
        result = GenerationResult(
            hypotheses=[Hypothesis(description="Test", prediction="Up")],
            generation_time_ms=50.0,
        )
        metrics.update(result)

        data = metrics.to_dict()
        assert data["total_generated"] == 1
        assert data["average_generation_time_ms"] == 50.0


class TestHypothesisGenerator:
    """Tests for HypothesisGenerator class."""

    def test_creation(self) -> None:
        """Test creating generator."""
        generator = HypothesisGenerator()
        assert generator is not None
        assert generator.config is not None

    def test_creation_with_config(self) -> None:
        """Test creating generator with custom config."""
        config = GeneratorConfig(max_hypotheses=5, min_confidence=0.5)
        generator = HypothesisGenerator(config)
        assert generator.config.max_hypotheses == 5
        assert generator.config.min_confidence == 0.5

    def test_creation_with_provider(self) -> None:
        """Test creating generator with custom provider."""
        provider = MockLLMProvider()
        generator = HypothesisGenerator(llm_provider=provider)
        assert generator.llm_provider is provider

    def test_generate_from_beliefs_empty(self) -> None:
        """Test generating with no beliefs."""
        generator = HypothesisGenerator()
        result = generator.generate_from_beliefs([], MarketContext())

        assert len(result) == 0
        assert result.beliefs_used == 0
        assert "error" in result.metadata

    def test_generate_from_beliefs(self) -> None:
        """Test generating from beliefs."""
        generator = HypothesisGenerator()
        beliefs = [BeliefVector(vector=np.array([0.5, 0.3, 0.8]))]
        context = MarketContext(symbol="BTC-USD", current_price=50000.0)

        result = generator.generate_from_beliefs(beliefs, context)

        assert result.beliefs_used == 1
        assert isinstance(result.hypotheses, list)

    def test_generate_from_beliefs_with_types(self) -> None:
        """Test generating specific hypothesis types."""
        config = GeneratorConfig(max_hypotheses=2)
        generator = HypothesisGenerator(config)

        beliefs = [BeliefVector(vector=np.array([0.5]))]
        context = MarketContext()
        types_to_generate = [HypothesisType.TREND, HypothesisType.RANGE]

        result = generator.generate_from_beliefs(beliefs, context, types_to_generate)

        assert len(result.hypotheses) <= 2

    def test_generate_from_beliefs_respects_max(self) -> None:
        """Test that generation respects max_hypotheses."""
        config = GeneratorConfig(max_hypotheses=3)
        generator = HypothesisGenerator(config)

        beliefs = [
            BeliefVector(vector=np.array([0.5])),
            BeliefVector(vector=np.array([0.6])),
        ]
        context = MarketContext()

        result = generator.generate_from_beliefs(beliefs, context)

        assert len(result.hypotheses) <= 3

    def test_validate_hypothesis(self) -> None:
        """Test validating a hypothesis."""
        generator = HypothesisGenerator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Test",
            prediction="Price up",
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = generator.validate_hypothesis(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        assert isinstance(result, ValidationResult)

    def test_score_confidence(self) -> None:
        """Test scoring confidence."""
        generator = HypothesisGenerator()

        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            confidence=ConfidenceScore(score=0.6),
        )

        evidence = {
            "belief_strength": 0.8,
            "market_alignment": 0.7,
            "historical_accuracy": 0.75,
        }

        new_confidence = generator.score_confidence(hypothesis, evidence)

        assert 0.0 <= new_confidence.score <= 1.0
        assert new_confidence.evidence_strength == 0.8

    def test_rank_hypotheses(self) -> None:
        """Test ranking hypotheses."""
        generator = HypothesisGenerator()

        hypotheses = [
            Hypothesis(
                description="Low confidence",
                prediction="Up",
                confidence=ConfidenceScore(score=0.3),
            ),
            Hypothesis(
                description="High confidence",
                prediction="Down",
                confidence=ConfidenceScore(score=0.9),
            ),
            Hypothesis(
                description="Medium confidence",
                prediction="Sideways",
                confidence=ConfidenceScore(score=0.6),
            ),
        ]

        ranked = generator.rank_hypotheses(hypotheses)

        assert ranked[0].description == "High confidence"
        assert ranked[1].description == "Medium confidence"
        assert ranked[2].description == "Low confidence"

    def test_filter_hypotheses(self) -> None:
        """Test filtering hypotheses."""
        generator = HypothesisGenerator()

        future = datetime.now(UTC) + timedelta(hours=1)
        past = datetime.now(UTC) - timedelta(hours=1)

        hypotheses = [
            Hypothesis(
                description="High confidence",
                prediction="Up",
                confidence=ConfidenceScore(score=0.8),
                hypothesis_type=HypothesisType.TREND,
                expires_at=future,
            ),
            Hypothesis(
                description="Low confidence",
                prediction="Down",
                confidence=ConfidenceScore(score=0.2),
                hypothesis_type=HypothesisType.REVERSAL,
                expires_at=future,
            ),
            Hypothesis(
                description="Expired",
                prediction="Sideways",
                confidence=ConfidenceScore(score=0.9),
                expires_at=past,
            ),
        ]

        filtered = generator.filter_hypotheses(hypotheses)

        assert len(filtered) == 1
        assert filtered[0].description == "High confidence"

    def test_filter_hypotheses_by_type(self) -> None:
        """Test filtering by hypothesis type."""
        generator = HypothesisGenerator()
        future = datetime.now(UTC) + timedelta(hours=1)

        hypotheses = [
            Hypothesis(
                description="Trend",
                prediction="Up",
                hypothesis_type=HypothesisType.TREND,
                confidence=ConfidenceScore(score=0.8),
                expires_at=future,
            ),
            Hypothesis(
                description="Reversal",
                prediction="Down",
                hypothesis_type=HypothesisType.REVERSAL,
                confidence=ConfidenceScore(score=0.8),
                expires_at=future,
            ),
        ]

        filtered = generator.filter_hypotheses(
            hypotheses, hypothesis_type=HypothesisType.TREND
        )

        assert len(filtered) == 1
        assert filtered[0].hypothesis_type == HypothesisType.TREND

    def test_filter_hypotheses_include_expired(self) -> None:
        """Test filtering including expired hypotheses."""
        generator = HypothesisGenerator()
        past = datetime.now(UTC) - timedelta(hours=1)

        hypotheses = [
            Hypothesis(
                description="Expired but high confidence",
                prediction="Up",
                confidence=ConfidenceScore(score=0.9),
                expires_at=past,
            ),
        ]

        filtered = generator.filter_hypotheses(
            hypotheses, exclude_expired=False, min_confidence=0.5
        )

        assert len(filtered) == 1

    def test_get_metrics(self) -> None:
        """Test getting metrics."""
        generator = HypothesisGenerator()

        beliefs = [BeliefVector(vector=np.array([0.5]))]
        generator.generate_from_beliefs(beliefs, MarketContext())

        metrics = generator.get_metrics()
        assert metrics.total_generated >= 0

    def test_get_validation_metrics(self) -> None:
        """Test getting validation metrics."""
        generator = HypothesisGenerator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )
        generator.validate_hypothesis(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        metrics = generator.get_validation_metrics()
        assert "total_validated" in metrics

    def test_reset_metrics(self) -> None:
        """Test resetting metrics."""
        generator = HypothesisGenerator()

        beliefs = [BeliefVector(vector=np.array([0.5]))]
        generator.generate_from_beliefs(beliefs, MarketContext())

        generator.reset_metrics()
        metrics = generator.get_metrics()

        assert metrics.total_generated == 0

    def test_generation_updates_metrics(self) -> None:
        """Test that generation updates metrics."""
        generator = HypothesisGenerator()

        initial_total = generator.get_metrics().total_generated

        beliefs = [BeliefVector(vector=np.array([0.5]))]
        generator.generate_from_beliefs(beliefs, MarketContext())

        new_total = generator.get_metrics().total_generated
        assert new_total >= initial_total
