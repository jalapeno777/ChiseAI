"""Integration tests for hypothesis generator with belief pipeline."""

from __future__ import annotations

import numpy as np
from src.strong_system.belief_embeddings import BeliefVector
from src.strong_system.hypothesis_generator import (
    ConfidenceScore,
    GeneratorConfig,
    Hypothesis,
    HypothesisGenerator,
    HypothesisType,
    MarketContext,
    ValidationStatus,
)


class TestBeliefPipelineIntegration:
    """Tests for integration with belief embedding pipeline."""

    def test_generate_from_belief_vectors(self) -> None:
        """Test generating hypotheses from actual BeliefVectors."""
        generator = HypothesisGenerator()

        # Create real belief vectors
        beliefs = [
            BeliefVector(
                vector=np.array([0.8, 0.6, 0.9, 0.4]),
                belief_id="belief_trend_001",
            ),
            BeliefVector(
                vector=np.array([0.3, 0.2, 0.5, 0.8]),
                belief_id="belief_reversal_001",
            ),
        ]

        context = MarketContext(
            symbol="BTC-USD",
            timeframe="1h",
            current_price=50000.0,
            market_regime="bullish",
            indicators={"rsi": 65.0, "macd": 0.5},
        )

        result = generator.generate_from_beliefs(beliefs, context)

        assert result.beliefs_used == 2
        assert isinstance(result.hypotheses, list)

    def test_hypothesis_tracks_supporting_beliefs(self) -> None:
        """Test that hypotheses track their supporting beliefs."""
        generator = HypothesisGenerator()

        beliefs = [
            BeliefVector(vector=np.array([0.5]), belief_id=f"belief_{i}")
            for i in range(5)
        ]

        result = generator.generate_from_beliefs(beliefs, MarketContext())

        for hypothesis in result.hypotheses:
            assert len(hypothesis.supporting_beliefs) > 0
            # Belief IDs should be strings
            assert all(isinstance(bid, str) for bid in hypothesis.supporting_beliefs)

    def test_context_passed_to_hypotheses(self) -> None:
        """Test that market context is preserved in hypotheses."""
        generator = HypothesisGenerator()

        context = MarketContext(
            symbol="ETH-USD",
            timeframe="4h",
            current_price=3000.0,
            indicators={"sma": 2950.0},
        )

        beliefs = [BeliefVector(vector=np.array([0.5]))]
        result = generator.generate_from_beliefs(beliefs, context)

        for hypothesis in result.hypotheses:
            assert hypothesis.context.symbol == "ETH-USD"
            assert hypothesis.context.current_price == 3000.0


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_full_workflow_trend(self) -> None:
        """Test complete workflow for trend hypothesis."""
        config = GeneratorConfig(
            max_hypotheses=3,
            min_confidence=0.3,
            hypothesis_types=[HypothesisType.TREND],
        )
        generator = HypothesisGenerator(config)

        # Step 1: Generate beliefs (simulated)
        beliefs = [
            BeliefVector(vector=np.array([0.8, 0.7, 0.9])),
            BeliefVector(vector=np.array([0.6, 0.8, 0.7])),
        ]

        # Step 2: Create market context
        context = MarketContext(
            symbol="BTC-USD",
            current_price=50000.0,
            market_regime="bullish",
        )

        # Step 3: Generate hypotheses
        result = generator.generate_from_beliefs(beliefs, context)

        # Step 4: Validate hypotheses (simulated market outcome)
        for hypothesis in result.hypotheses:
            validation = generator.validate_hypothesis(
                hypothesis,
                {
                    "actual_price": 52500.0,  # 5% increase
                    "high": 53000.0,
                    "low": 49500.0,
                },
            )

            assert validation.status in [
                ValidationStatus.VALID,
                ValidationStatus.INVALID,
                ValidationStatus.INCONCLUSIVE,
            ]

    def test_full_workflow_range(self) -> None:
        """Test complete workflow for range-bound hypothesis."""
        config = GeneratorConfig(
            max_hypotheses=2,
            hypothesis_types=[HypothesisType.RANGE],
        )
        generator = HypothesisGenerator(config)

        beliefs = [BeliefVector(vector=np.array([0.5, 0.5, 0.5]))]
        context = MarketContext(
            symbol="BTC-USD",
            current_price=50000.0,
        )

        result = generator.generate_from_beliefs(beliefs, context)

        # Simulate price staying in range
        for hypothesis in result.hypotheses:
            validation = generator.validate_hypothesis(
                hypothesis,
                {
                    "actual_price": 50100.0,
                    "high": 50500.0,
                    "low": 49800.0,
                },
            )
            assert isinstance(validation.accuracy, float)
            assert 0.0 <= validation.accuracy <= 1.0

    def test_confidence_scoring_workflow(self) -> None:
        """Test confidence scoring workflow."""
        generator = HypothesisGenerator()

        # Create hypothesis
        hypothesis = Hypothesis(
            description="Test workflow",
            prediction="Price increase",
            confidence=ConfidenceScore(score=0.5),
        )

        # Score with evidence
        evidence = {
            "belief_strength": 0.8,
            "market_alignment": 0.7,
            "historical_accuracy": 0.9,
        }

        new_confidence = generator.score_confidence(hypothesis, evidence)

        # New confidence should be different
        assert new_confidence.score != hypothesis.confidence.score
        assert 0.0 <= new_confidence.score <= 1.0

    def test_ranking_and_filtering_workflow(self) -> None:
        """Test ranking and filtering workflow."""
        generator = HypothesisGenerator()
        future = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ) + __import__("datetime").timedelta(hours=1)

        # Create multiple hypotheses
        hypotheses = [
            Hypothesis(
                description="High confidence trend",
                prediction="Up 10%",
                hypothesis_type=HypothesisType.TREND,
                confidence=ConfidenceScore(score=0.9),
                expires_at=future,
            ),
            Hypothesis(
                description="Medium confidence reversal",
                prediction="Down 5%",
                hypothesis_type=HypothesisType.REVERSAL,
                confidence=ConfidenceScore(score=0.6),
                expires_at=future,
            ),
            Hypothesis(
                description="Low confidence breakout",
                prediction="Up 20%",
                hypothesis_type=HypothesisType.BREAKOUT,
                confidence=ConfidenceScore(score=0.4),
                expires_at=future,
            ),
        ]

        # Rank hypotheses
        ranked = generator.rank_hypotheses(hypotheses)
        assert ranked[0].confidence.score >= ranked[1].confidence.score

        # Filter by confidence
        filtered = generator.filter_hypotheses(hypotheses, min_confidence=0.5)
        assert len(filtered) == 2
        assert all(h.confidence.score >= 0.5 for h in filtered)

        # Filter by type
        trend_only = generator.filter_hypotheses(
            hypotheses, hypothesis_type=HypothesisType.TREND
        )
        assert len(trend_only) == 1
        assert trend_only[0].hypothesis_type == HypothesisType.TREND


class TestMetricsAccumulation:
    """Tests for metrics accumulation across operations."""

    def test_generation_metrics_accumulate(self) -> None:
        """Test that generation metrics accumulate."""
        generator = HypothesisGenerator()

        # First generation
        beliefs1 = [BeliefVector(vector=np.array([0.5]))]
        generator.generate_from_beliefs(beliefs1, MarketContext())

        initial_total = generator.get_metrics().total_generated

        # Second generation
        beliefs2 = [BeliefVector(vector=np.array([0.6]))]
        generator.generate_from_beliefs(beliefs2, MarketContext())

        final_total = generator.get_metrics().total_generated
        assert final_total >= initial_total

    def test_validation_metrics_accumulate(self) -> None:
        """Test that validation metrics accumulate."""
        generator = HypothesisGenerator()
        future = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ) + __import__("datetime").timedelta(hours=1)

        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        # First validation
        generator.validate_hypothesis(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        initial_total = generator.get_validation_metrics()["total_validated"]

        # Second validation
        generator.validate_hypothesis(
            hypothesis, {"actual_price": 95.0, "high": 100.0, "low": 94.0}
        )

        final_total = generator.get_validation_metrics()["total_validated"]
        assert final_total > initial_total


class TestErrorHandling:
    """Tests for error handling in integration scenarios."""

    def test_empty_beliefs_handling(self) -> None:
        """Test handling of empty beliefs."""
        generator = HypothesisGenerator()

        result = generator.generate_from_beliefs([], MarketContext())

        assert len(result) == 0
        assert "error" in result.metadata

    def test_invalid_market_data_handling(self) -> None:
        """Test handling of invalid market data."""
        generator = HypothesisGenerator()
        future = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ) + __import__("datetime").timedelta(hours=1)

        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        # Missing required fields
        result = generator.validate_hypothesis(hypothesis, {})

        # Should not crash, returns validation result
        assert isinstance(result.status, ValidationStatus)

    def test_expired_hypothesis_handling(self) -> None:
        """Test handling of expired hypotheses."""
        generator = HypothesisGenerator()
        past = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ) - __import__("datetime").timedelta(hours=1)

        hypothesis = Hypothesis(
            description="Test",
            prediction="Up",
            confidence=ConfidenceScore(score=0.8),
            expires_at=past,
        )

        result = generator.validate_hypothesis(hypothesis, {"actual_price": 100.0})

        assert result.status == ValidationStatus.INCONCLUSIVE
