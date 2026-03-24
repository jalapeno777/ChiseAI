"""Tests for hypothesis generator types."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from src.strong_system.hypothesis_generator.types import (
    ConfidenceScore,
    GenerationResult,
    GeneratorConfig,
    Hypothesis,
    HypothesisType,
    MarketContext,
    ValidationResult,
    ValidationStatus,
)


class TestMarketContext:
    """Tests for MarketContext class."""

    def test_default_creation(self) -> None:
        """Test creating context with default values."""
        context = MarketContext()
        assert context.symbol == "UNKNOWN"
        assert context.timeframe == "1h"
        assert context.current_price == 0.0
        assert isinstance(context.timestamp, datetime)
        assert context.indicators == {}
        assert context.market_regime == "unknown"
        assert context.additional_data == {}

    def test_custom_creation(self) -> None:
        """Test creating context with custom values."""
        now = datetime.now(UTC)
        context = MarketContext(
            symbol="BTC-USD",
            timeframe="1d",
            current_price=50000.0,
            timestamp=now,
            indicators={"rsi": 65.0, "macd": 0.5},
            market_regime="bullish",
            additional_data={"volume": 1000000},
        )
        assert context.symbol == "BTC-USD"
        assert context.timeframe == "1d"
        assert context.current_price == 50000.0
        assert context.timestamp == now
        assert context.indicators == {"rsi": 65.0, "macd": 0.5}
        assert context.market_regime == "bullish"
        assert context.additional_data == {"volume": 1000000}

    def test_symbol_validation_empty(self) -> None:
        """Test that empty symbol raises error."""
        with pytest.raises(ValueError, match="Symbol must be a non-empty string"):
            MarketContext(symbol="")

    def test_price_validation_negative(self) -> None:
        """Test that negative price raises error."""
        with pytest.raises(ValueError, match="Current price cannot be negative"):
            MarketContext(current_price=-100.0)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        context = MarketContext(
            symbol="ETH-USD",
            current_price=3000.0,
            timestamp=now,
            indicators={"sma": 2950.0},
        )
        data = context.to_dict()
        assert data["symbol"] == "ETH-USD"
        assert data["current_price"] == 3000.0
        assert data["timestamp"] == now.isoformat()
        assert data["indicators"] == {"sma": 2950.0}

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(UTC)
        data = {
            "symbol": "SOL-USD",
            "timeframe": "4h",
            "current_price": 150.0,
            "timestamp": now.isoformat(),
            "indicators": {"atr": 2.5},
            "market_regime": "volatile",
        }
        context = MarketContext.from_dict(data)
        assert context.symbol == "SOL-USD"
        assert context.timeframe == "4h"
        assert context.current_price == 150.0
        assert context.indicators == {"atr": 2.5}
        assert context.market_regime == "volatile"


class TestConfidenceScore:
    """Tests for ConfidenceScore class."""

    def test_default_creation(self) -> None:
        """Test creating confidence with default values."""
        score = ConfidenceScore()
        assert score.score == 0.5
        assert score.evidence_strength == 0.5
        assert score.consistency_score == 0.5
        assert score.historical_accuracy == 0.5
        assert score.factors == {}

    def test_custom_creation(self) -> None:
        """Test creating confidence with custom values."""
        score = ConfidenceScore(
            score=0.85,
            evidence_strength=0.9,
            consistency_score=0.8,
            historical_accuracy=0.75,
            factors={"trend": 0.9, "volume": 0.7},
        )
        assert score.score == 0.85
        assert score.evidence_strength == 0.9
        assert score.consistency_score == 0.8
        assert score.historical_accuracy == 0.75
        assert score.factors == {"trend": 0.9, "volume": 0.7}

    def test_score_validation_low(self) -> None:
        """Test that score below 0.0 raises error."""
        with pytest.raises(ValueError, match="score must be between"):
            ConfidenceScore(score=-0.1)

    def test_score_validation_high(self) -> None:
        """Test that score above 1.0 raises error."""
        with pytest.raises(ValueError, match="score must be between"):
            ConfidenceScore(score=1.1)

    def test_evidence_strength_validation(self) -> None:
        """Test evidence strength validation."""
        with pytest.raises(ValueError, match="evidence_strength must be between"):
            ConfidenceScore(evidence_strength=1.5)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        score = ConfidenceScore(
            score=0.75,
            factors={"support": 0.8},
        )
        data = score.to_dict()
        assert data["score"] == 0.75
        assert data["factors"] == {"support": 0.8}

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "score": 0.9,
            "evidence_strength": 0.85,
            "consistency_score": 0.9,
            "historical_accuracy": 0.8,
            "factors": {"momentum": 0.95},
        }
        score = ConfidenceScore.from_dict(data)
        assert score.score == 0.9
        assert score.factors == {"momentum": 0.95}


class TestHypothesis:
    """Tests for Hypothesis class."""

    def test_default_creation(self) -> None:
        """Test that default creation requires description."""
        with pytest.raises(ValueError, match="Description cannot be empty"):
            Hypothesis()

    def test_custom_creation(self) -> None:
        """Test creating hypothesis with custom values."""
        now = datetime.now(UTC)
        expires = now + timedelta(hours=24)
        hypothesis = Hypothesis(
            hypothesis_id="test_123",
            hypothesis_type=HypothesisType.TREND,
            description="Bullish trend continuation",
            prediction="Price will increase 5%",
            confidence=ConfidenceScore(score=0.8),
            supporting_beliefs=["belief_1", "belief_2"],
            created_at=now,
            expires_at=expires,
        )
        assert hypothesis.hypothesis_id == "test_123"
        assert hypothesis.hypothesis_type == HypothesisType.TREND
        assert hypothesis.description == "Bullish trend continuation"
        assert hypothesis.prediction == "Price will increase 5%"
        assert hypothesis.confidence.score == 0.8
        assert hypothesis.supporting_beliefs == ["belief_1", "belief_2"]

    def test_prediction_required(self) -> None:
        """Test that prediction cannot be empty."""
        with pytest.raises(ValueError, match="Prediction cannot be empty"):
            Hypothesis(description="Test hypothesis")

    def test_is_expired(self) -> None:
        """Test expiration check."""
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)

        expired = Hypothesis(
            description="Test",
            prediction="Test",
            expires_at=past,
        )
        assert expired.is_expired() is True

        not_expired = Hypothesis(
            description="Test",
            prediction="Test",
            expires_at=future,
        )
        assert not_expired.is_expired() is False

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        hypothesis = Hypothesis(
            description="Test hypothesis",
            prediction="Price will rise",
            hypothesis_type=HypothesisType.BREAKOUT,
        )
        data = hypothesis.to_dict()
        assert data["description"] == "Test hypothesis"
        assert data["prediction"] == "Price will rise"
        assert data["hypothesis_type"] == "BREAKOUT"
        assert "hypothesis_id" in data

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(UTC)
        data = {
            "hypothesis_id": "hyp_123",
            "hypothesis_type": "REVERSAL",
            "description": "Test reversal",
            "prediction": "Price will reverse",
            "confidence": {"score": 0.7},
            "supporting_beliefs": ["b1"],
            "created_at": now.isoformat(),
            "expires_at": now.isoformat(),
        }
        hypothesis = Hypothesis.from_dict(data)
        assert hypothesis.hypothesis_id == "hyp_123"
        assert hypothesis.hypothesis_type == HypothesisType.REVERSAL
        assert hypothesis.description == "Test reversal"


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_default_creation(self) -> None:
        """Test creating validation result with defaults."""
        result = ValidationResult()
        assert result.hypothesis_id == ""
        assert result.status == ValidationStatus.PENDING
        assert result.accuracy == 0.0

    def test_accuracy_validation(self) -> None:
        """Test accuracy validation."""
        with pytest.raises(ValueError, match="Accuracy must be between"):
            ValidationResult(accuracy=1.5)

    def test_error_margin_validation(self) -> None:
        """Test error margin validation."""
        with pytest.raises(ValueError, match="Error margin cannot be negative"):
            ValidationResult(error_margin=-1.0)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = ValidationResult(
            hypothesis_id="hyp_123",
            status=ValidationStatus.VALID,
            accuracy=0.85,
            notes={"reason": "Target hit"},
        )
        data = result.to_dict()
        assert data["hypothesis_id"] == "hyp_123"
        assert data["status"] == "VALID"
        assert data["accuracy"] == 0.85

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "hypothesis_id": "hyp_456",
            "status": "INVALID",
            "accuracy": 0.2,
            "error_margin": 0.15,
        }
        result = ValidationResult.from_dict(data)
        assert result.hypothesis_id == "hyp_456"
        assert result.status == ValidationStatus.INVALID
        assert result.accuracy == 0.2


class TestGeneratorConfig:
    """Tests for GeneratorConfig class."""

    def test_default_creation(self) -> None:
        """Test creating config with default values."""
        config = GeneratorConfig()
        assert config.llm_provider == "openai"
        assert config.model_name == "gpt-4"
        assert config.max_hypotheses == 10
        assert config.min_confidence == 0.3
        assert config.default_ttl_hours == 24
        assert config.enable_validation is True

    def test_default_hypothesis_types(self) -> None:
        """Test that default hypothesis types are set."""
        config = GeneratorConfig()
        assert len(config.hypothesis_types) == 4
        assert HypothesisType.TREND in config.hypothesis_types
        assert HypothesisType.REVERSAL in config.hypothesis_types

    def test_min_confidence_validation(self) -> None:
        """Test min_confidence validation."""
        with pytest.raises(ValueError, match="min_confidence must be between"):
            GeneratorConfig(min_confidence=1.5)

    def test_max_hypotheses_validation(self) -> None:
        """Test max_hypotheses validation."""
        with pytest.raises(ValueError, match="max_hypotheses must be at least 1"):
            GeneratorConfig(max_hypotheses=0)


class TestGenerationResult:
    """Tests for GenerationResult class."""

    def test_default_creation(self) -> None:
        """Test creating result with default values."""
        result = GenerationResult()
        assert result.hypotheses == []
        assert result.generation_time_ms == 0.0
        assert result.beliefs_used == 0

    def test_len(self) -> None:
        """Test __len__ method."""
        hypotheses = [
            Hypothesis(description="Test 1", prediction="P1"),
            Hypothesis(description="Test 2", prediction="P2"),
        ]
        result = GenerationResult(hypotheses=hypotheses)
        assert len(result) == 2

    def test_iter(self) -> None:
        """Test __iter__ method."""
        hypotheses = [
            Hypothesis(description="Test 1", prediction="P1"),
        ]
        result = GenerationResult(hypotheses=hypotheses)
        iterated = list(result)
        assert len(iterated) == 1
        assert iterated[0].description == "Test 1"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        hypothesis = Hypothesis(description="Test", prediction="P")
        result = GenerationResult(
            hypotheses=[hypothesis],
            generation_time_ms=100.0,
            beliefs_used=5,
        )
        data = result.to_dict()
        assert data["generation_time_ms"] == 100.0
        assert data["beliefs_used"] == 5
        assert len(data["hypotheses"]) == 1

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "hypotheses": [
                {"description": "Test", "prediction": "P", "hypothesis_type": "TREND"},
            ],
            "generation_time_ms": 50.0,
            "beliefs_used": 3,
        }
        result = GenerationResult.from_dict(data)
        assert result.generation_time_ms == 50.0
        assert result.beliefs_used == 3
        assert len(result.hypotheses) == 1


class TestHypothesisType:
    """Tests for HypothesisType enum."""

    def test_enum_values(self) -> None:
        """Test that all hypothesis types exist."""
        assert HypothesisType.TREND is not None
        assert HypothesisType.REVERSAL is not None
        assert HypothesisType.RANGE is not None
        assert HypothesisType.BREAKOUT is not None
        assert HypothesisType.VOLATILITY is not None
        assert HypothesisType.MOMENTUM is not None

    def test_enum_names(self) -> None:
        """Test enum names."""
        assert HypothesisType.TREND.name == "TREND"
        assert HypothesisType.REVERSAL.name == "REVERSAL"


class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_enum_values(self) -> None:
        """Test that all validation statuses exist."""
        assert ValidationStatus.PENDING is not None
        assert ValidationStatus.VALID is not None
        assert ValidationStatus.INVALID is not None
        assert ValidationStatus.INCONCLUSIVE is not None
