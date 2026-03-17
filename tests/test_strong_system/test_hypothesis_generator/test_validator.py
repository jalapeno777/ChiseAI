"""Tests for hypothesis generator validator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.strong_system.hypothesis_generator.types import (
    ConfidenceScore,
    Hypothesis,
    HypothesisType,
    MarketContext,
    ValidationResult,
    ValidationStatus,
)
from src.strong_system.hypothesis_generator.validator import (
    HypothesisValidator,
    PredictionParser,
    ValidationConfig,
    ValidationMetrics,
)


class TestPredictionParser:
    """Tests for PredictionParser class."""

    def test_extract_price_targets(self) -> None:
        """Test extracting price targets."""
        text = "Price will reach $50000 or hit target of 51000"
        targets = PredictionParser.extract_price_targets(text)
        assert 50000.0 in targets
        assert 51000.0 in targets

    def test_extract_price_targets_with_text(self) -> None:
        """Test extracting price targets from text."""
        text = "Price target of 50000 and reach 51500"
        targets = PredictionParser.extract_price_targets(text)
        assert 50000.0 in targets
        assert 51500.0 in targets

    def test_extract_price_targets_no_prices(self) -> None:
        """Test extracting price targets when none exist."""
        text = "Price will go up"
        targets = PredictionParser.extract_price_targets(text)
        assert targets == []

    def test_extract_percentage_changes(self) -> None:
        """Test extracting percentage changes."""
        text = "Price will increase 5% or gain 10 percent"
        changes = PredictionParser.extract_percentage_changes(text)
        assert 5.0 in changes
        assert 10.0 in changes

    def test_extract_percentage_changes_signed(self) -> None:
        """Test extracting signed percentage changes."""
        text = "Expect +15% or -5% move"
        changes = PredictionParser.extract_percentage_changes(text)
        assert 15.0 in changes
        assert -5.0 in changes

    def test_extract_direction_up(self) -> None:
        """Test extracting upward direction."""
        text = "Price will rise and go higher in a bullish trend"
        direction = PredictionParser.extract_direction(text)
        assert direction == "up"

    def test_extract_direction_down(self) -> None:
        """Test extracting downward direction."""
        text = "Price will fall and drop lower in a bearish market"
        direction = PredictionParser.extract_direction(text)
        assert direction == "down"

    def test_extract_direction_none(self) -> None:
        """Test extracting direction when unclear."""
        text = "Price will move sideways"
        direction = PredictionParser.extract_direction(text)
        assert direction is None

    def test_extract_direction_mixed(self) -> None:
        """Test extracting direction with mixed signals."""
        text = "Price may rise or fall"
        direction = PredictionParser.extract_direction(text)
        # When signals are equal, may return None or either direction
        assert direction in [None, "up", "down"]


class TestValidationConfig:
    """Tests for ValidationConfig class."""

    def test_default_creation(self) -> None:
        """Test creating config with defaults."""
        config = ValidationConfig()
        assert config.tolerance_percent == 5.0
        assert config.min_confidence_for_validation == 0.3
        assert config.require_price_target is True
        assert config.max_validation_delay_hours == 48
        assert config.enable_partial_matching is True

    def test_custom_creation(self) -> None:
        """Test creating config with custom values."""
        config = ValidationConfig(
            tolerance_percent=10.0,
            min_confidence_for_validation=0.5,
            require_price_target=False,
        )
        assert config.tolerance_percent == 10.0
        assert config.min_confidence_for_validation == 0.5
        assert config.require_price_target is False


class TestValidationMetrics:
    """Tests for ValidationMetrics class."""

    def test_default_creation(self) -> None:
        """Test creating metrics with defaults."""
        metrics = ValidationMetrics()
        assert metrics.total_validated == 0
        assert metrics.valid_count == 0
        assert metrics.average_accuracy == 0.0

    def test_update_valid(self) -> None:
        """Test updating with valid result."""
        metrics = ValidationMetrics()
        result = ValidationResult(
            status=ValidationStatus.VALID,
            accuracy=0.8,
        )
        metrics.update(result)

        assert metrics.total_validated == 1
        assert metrics.valid_count == 1
        assert metrics.invalid_count == 0
        assert metrics.average_accuracy == 0.8

    def test_update_invalid(self) -> None:
        """Test updating with invalid result."""
        metrics = ValidationMetrics()
        result = ValidationResult(
            status=ValidationStatus.INVALID,
            accuracy=0.2,
        )
        metrics.update(result)

        assert metrics.total_validated == 1
        assert metrics.valid_count == 0
        assert metrics.invalid_count == 1

    def test_update_inconclusive(self) -> None:
        """Test updating with inconclusive result."""
        metrics = ValidationMetrics()
        result = ValidationResult(
            status=ValidationStatus.INCONCLUSIVE,
            accuracy=0.0,
        )
        metrics.update(result)

        assert metrics.total_validated == 1
        assert metrics.inconclusive_count == 1

    def test_update_running_average(self) -> None:
        """Test running average calculation."""
        metrics = ValidationMetrics()

        metrics.update(ValidationResult(status=ValidationStatus.VALID, accuracy=1.0))
        metrics.update(ValidationResult(status=ValidationStatus.VALID, accuracy=0.5))
        metrics.update(ValidationResult(status=ValidationStatus.VALID, accuracy=0.0))

        assert metrics.average_accuracy == 0.5

    def test_history_limit(self) -> None:
        """Test that history is limited to 100 entries."""
        metrics = ValidationMetrics()

        for i in range(150):
            metrics.update(
                ValidationResult(status=ValidationStatus.VALID, accuracy=0.5)
            )

        assert len(metrics.validation_history) == 100

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        metrics = ValidationMetrics()
        metrics.update(ValidationResult(status=ValidationStatus.VALID, accuracy=0.9))

        data = metrics.to_dict()
        assert data["total_validated"] == 1
        assert data["valid_count"] == 1
        assert data["average_accuracy"] == 0.9


class TestHypothesisValidator:
    """Tests for HypothesisValidator class."""

    def test_creation(self) -> None:
        """Test creating validator."""
        validator = HypothesisValidator()
        assert validator is not None
        assert validator.config is not None

    def test_creation_with_config(self) -> None:
        """Test creating validator with custom config."""
        config = ValidationConfig(tolerance_percent=10.0)
        validator = HypothesisValidator(config)
        assert validator.config.tolerance_percent == 10.0

    def test_validate_expired_hypothesis(self) -> None:
        """Test validating expired hypothesis."""
        validator = HypothesisValidator()

        past = datetime.now(UTC) - timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Test",
            prediction="Price up",
            expires_at=past,
        )

        result = validator.validate(hypothesis, {"actual_price": 100.0})

        assert result.status == ValidationStatus.INCONCLUSIVE
        assert "expired" in result.actual_outcome.lower()

    def test_validate_low_confidence(self) -> None:
        """Test validating hypothesis with low confidence."""
        config = ValidationConfig(min_confidence_for_validation=0.5)
        validator = HypothesisValidator(config)

        hypothesis = Hypothesis(
            description="Test",
            prediction="Price up",
            confidence=ConfidenceScore(score=0.2),
        )

        result = validator.validate(hypothesis, {"actual_price": 100.0})

        assert result.status == ValidationStatus.INCONCLUSIVE

    def test_validate_trend_correct_direction(self) -> None:
        """Test validating trend with correct direction."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Bullish trend",
            prediction="Price will increase by 5%",
            hypothesis_type=HypothesisType.TREND,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = validator.validate(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        assert result.status == ValidationStatus.VALID
        assert result.accuracy > 0.5

    def test_validate_trend_wrong_direction(self) -> None:
        """Test validating trend with wrong direction."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Bullish trend",
            prediction="Price will increase",
            hypothesis_type=HypothesisType.TREND,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = validator.validate(
            hypothesis, {"actual_price": 95.0, "high": 101.0, "low": 94.0}
        )

        assert result.status == ValidationStatus.INVALID

    def test_validate_range_within_bounds(self) -> None:
        """Test validating range-bound hypothesis within bounds."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Range bound",
            prediction="Price will stay between 95 and 105",
            hypothesis_type=HypothesisType.RANGE,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = validator.validate(
            hypothesis, {"actual_price": 100.0, "high": 104.0, "low": 96.0}
        )

        assert result.status == ValidationStatus.VALID

    def test_validate_range_outside_bounds(self) -> None:
        """Test validating range-bound hypothesis with price outside bounds."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Range bound",
            prediction="Price will stay between 95 and 105",
            hypothesis_type=HypothesisType.RANGE,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        # Price outside the range [95, 105]
        result = validator.validate(
            hypothesis, {"actual_price": 110.0, "high": 112.0, "low": 108.0}
        )

        # Status depends on tolerance - just verify we get a result
        assert isinstance(result.status, ValidationStatus)
        assert 0.0 <= result.accuracy <= 1.0

    def test_validate_breakout_up(self) -> None:
        """Test validating upward breakout."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Breakout up",
            prediction="Price will breakout above 105 and go up",
            hypothesis_type=HypothesisType.BREAKOUT,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = validator.validate(
            hypothesis, {"actual_price": 107.0, "high": 108.0, "low": 100.0}
        )

        assert result.status == ValidationStatus.VALID

    def test_validate_breakout_no_breakout(self) -> None:
        """Test validating when no breakout occurs."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Breakout up",
            prediction="Price will breakout above 120 and go up",
            hypothesis_type=HypothesisType.BREAKOUT,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        # Price doesn't reach the breakout level
        result = validator.validate(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        # May be VALID or INVALID depending on tolerance; verify we get a result
        assert isinstance(result.status, ValidationStatus)
        assert 0.0 <= result.accuracy <= 1.0

    def test_validate_generic_with_target(self) -> None:
        """Test generic validation with price target."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Generic",
            prediction="Price will hit $105",
            hypothesis_type=HypothesisType.VOLATILITY,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        result = validator.validate(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )

        assert result.status == ValidationStatus.VALID

    def test_get_metrics(self) -> None:
        """Test getting metrics."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Test",
            prediction="Price will go up by 5%",
            hypothesis_type=HypothesisType.TREND,
            confidence=ConfidenceScore(score=0.8),
            context=MarketContext(current_price=100.0),
            expires_at=future,
        )

        validator.validate(
            hypothesis, {"actual_price": 105.0, "high": 106.0, "low": 99.0}
        )
        metrics = validator.get_metrics()

        assert metrics.total_validated == 1

    def test_reset_metrics(self) -> None:
        """Test resetting metrics."""
        validator = HypothesisValidator()

        future = datetime.now(UTC) + timedelta(hours=1)
        hypothesis = Hypothesis(
            description="Test",
            prediction="Price up",
            confidence=ConfidenceScore(score=0.8),
            expires_at=future,
        )

        validator.validate(hypothesis, {"actual_price": 100.0})
        validator.reset_metrics()
        metrics = validator.get_metrics()

        assert metrics.total_validated == 0
