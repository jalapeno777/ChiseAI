"""Hypothesis validation logic.

Provides validation mechanisms for testing hypotheses against
actual market data and outcomes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.strong_system.hypothesis_generator.types import (
    Hypothesis,
    HypothesisType,
    ValidationResult,
    ValidationStatus,
)


class MarketDataProvider(Protocol):
    """Protocol for market data providers."""

    def get_price_at(self, timestamp: datetime) -> float:
        """Get price at a specific timestamp."""
        ...

    def get_price_range(self, start: datetime, end: datetime) -> dict[str, float]:
        """Get price range (high, low, open, close) for a period."""
        ...


@dataclass
class ValidationConfig:
    """Configuration for hypothesis validation.

    Attributes:
        tolerance_percent: Tolerance percentage for price predictions
        min_confidence_for_validation: Minimum confidence to attempt validation
        require_price_target: Whether predictions must include price targets
        max_validation_delay_hours: Maximum hours to wait for validation
        enable_partial_matching: Allow partial validation matches
    """

    tolerance_percent: float = 5.0
    min_confidence_for_validation: float = 0.3
    require_price_target: bool = True
    max_validation_delay_hours: int = 48
    enable_partial_matching: bool = True


@dataclass
class ValidationMetrics:
    """Metrics for validation performance.

    Attributes:
        total_validated: Total number of hypotheses validated
        valid_count: Number of valid hypotheses
        invalid_count: Number of invalid hypotheses
        inconclusive_count: Number of inconclusive validations
        average_accuracy: Average accuracy across validations
        average_error_margin: Average error margin
        validation_history: History of recent validations
    """

    total_validated: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    inconclusive_count: int = 0
    average_accuracy: float = 0.0
    average_error_margin: float = 0.0
    validation_history: list[ValidationResult] = field(default_factory=list)

    def update(self, result: ValidationResult) -> None:
        """Update metrics with a new validation result."""
        self.total_validated += 1

        if result.status == ValidationStatus.VALID:
            self.valid_count += 1
        elif result.status == ValidationStatus.INVALID:
            self.invalid_count += 1
        else:
            self.inconclusive_count += 1

        # Update running averages
        self.average_accuracy = (
            self.average_accuracy * (self.total_validated - 1) + result.accuracy
        ) / self.total_validated

        self.average_error_margin = (
            self.average_error_margin * (self.total_validated - 1) + result.error_margin
        ) / self.total_validated

        # Add to history (keep last 100)
        self.validation_history.append(result)
        if len(self.validation_history) > 100:
            self.validation_history = self.validation_history[-100:]

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_validated": self.total_validated,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "inconclusive_count": self.inconclusive_count,
            "average_accuracy": self.average_accuracy,
            "average_error_margin": self.average_error_margin,
            "validation_history": [v.to_dict() for v in self.validation_history],
        }


class PredictionParser:
    """Parser for extracting numerical predictions from hypothesis text."""

    # Regex patterns for common prediction formats
    PRICE_PATTERNS = [
        r"(?:price|reach|hit|target)\s+(?:of\s+)?[\$]?([\d,]+\.?\d*)",
        r"(?:to|toward)\s+[\$]?([\d,]+\.?\d*)",
        r"[\$]?([\d,]+\.?\d*)\s*(?:level|target|price)",
    ]

    PERCENTAGE_PATTERNS = [
        r"([+-]?\d+\.?\d*)\s*%",
        r"([+-]?\d+\.?\d*)\s*percent",
        r"(?:increase|decrease|gain|loss)\s+(?:of\s+)?([\d\.]+)",
    ]

    DIRECTION_PATTERNS = {
        "up": [r"\b(up|rise|rally|increase|higher|bullish|long)\b"],
        "down": [r"\b(down|fall|drop|decrease|lower|bearish|short)\b"],
    }

    @classmethod
    def extract_price_targets(cls, text: str) -> list[float]:
        """Extract price targets from prediction text.

        Args:
            text: Prediction text to parse

        Returns:
            List of extracted price targets
        """
        targets = []
        text_lower = text.lower()

        for pattern in cls.PRICE_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    # Remove commas and convert
                    price = float(match.replace(",", ""))
                    if price > 0:
                        targets.append(price)
                except ValueError:
                    continue

        return targets

    @classmethod
    def extract_percentage_changes(cls, text: str) -> list[float]:
        """Extract percentage changes from prediction text.

        Args:
            text: Prediction text to parse

        Returns:
            List of extracted percentage changes
        """
        changes = []
        text_lower = text.lower()

        for pattern in cls.PERCENTAGE_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    change = float(match)
                    changes.append(change)
                except ValueError:
                    continue

        return changes

    @classmethod
    def extract_direction(cls, text: str) -> str | None:
        """Extract directional bias from prediction text.

        Args:
            text: Prediction text to parse

        Returns:
            "up", "down", or None
        """
        text_lower = text.lower()

        up_count = 0
        down_count = 0

        for pattern in cls.DIRECTION_PATTERNS["up"]:
            up_count += len(re.findall(pattern, text_lower))

        for pattern in cls.DIRECTION_PATTERNS["down"]:
            down_count += len(re.findall(pattern, text_lower))

        if up_count > down_count:
            return "up"
        elif down_count > up_count:
            return "down"
        return None


class HypothesisValidator:
    """Validator for testing hypotheses against market data."""

    def __init__(self, config: ValidationConfig | None = None) -> None:
        """Initialize the validator.

        Args:
            config: Validation configuration
        """
        self.config = config or ValidationConfig()
        self.metrics = ValidationMetrics()
        self.parser = PredictionParser()

    def validate(
        self,
        hypothesis: Hypothesis,
        market_data: dict[str, Any],
    ) -> ValidationResult:
        """Validate a hypothesis against market data.

        Args:
            hypothesis: The hypothesis to validate
            market_data: Dictionary with actual market outcomes
                Expected keys: 'actual_price', 'high', 'low', 'timestamp'

        Returns:
            ValidationResult with validation status and metrics
        """
        # Check if hypothesis has expired
        if hypothesis.is_expired():
            return ValidationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                status=ValidationStatus.INCONCLUSIVE,
                actual_outcome="Hypothesis expired before validation",
                predicted_outcome=hypothesis.prediction,
                accuracy=0.0,
                error_margin=0.0,
                notes={"error": "Hypothesis expired"},
            )

        # Check confidence threshold
        if hypothesis.confidence.score < self.config.min_confidence_for_validation:
            return ValidationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                status=ValidationStatus.INCONCLUSIVE,
                actual_outcome="Confidence below validation threshold",
                predicted_outcome=hypothesis.prediction,
                accuracy=0.0,
                error_margin=0.0,
                notes={
                    "confidence": hypothesis.confidence.score,
                    "threshold": self.config.min_confidence_for_validation,
                },
            )

        # Extract predictions
        price_targets = self.parser.extract_price_targets(hypothesis.prediction)
        percentages = self.parser.extract_percentage_changes(hypothesis.prediction)
        direction = self.parser.extract_direction(hypothesis.prediction)

        # Get actual market data
        actual_price = market_data.get("actual_price", 0.0)
        high = market_data.get("high", actual_price)
        low = market_data.get("low", actual_price)
        initial_price = hypothesis.context.current_price

        # Validate based on hypothesis type
        if hypothesis.hypothesis_type == HypothesisType.TREND:
            return self._validate_trend(
                hypothesis, direction, actual_price, initial_price, market_data
            )
        elif hypothesis.hypothesis_type == HypothesisType.REVERSAL:
            return self._validate_reversal(
                hypothesis, direction, actual_price, initial_price, high, low
            )
        elif hypothesis.hypothesis_type == HypothesisType.RANGE:
            return self._validate_range(
                hypothesis, price_targets, actual_price, high, low
            )
        elif hypothesis.hypothesis_type == HypothesisType.BREAKOUT:
            return self._validate_breakout(
                hypothesis, direction, price_targets, high, low, initial_price
            )
        else:
            # Generic validation
            return self._validate_generic(
                hypothesis,
                price_targets,
                percentages,
                direction,
                actual_price,
                initial_price,
                high,
                low,
            )

    def _validate_trend(
        self,
        hypothesis: Hypothesis,
        direction: str | None,
        actual_price: float,
        initial_price: float,
        market_data: dict[str, Any],
    ) -> ValidationResult:
        """Validate a trend hypothesis."""
        if not direction or initial_price == 0:
            return ValidationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                status=ValidationStatus.INCONCLUSIVE,
                actual_outcome=f"Price moved to {actual_price}",
                predicted_outcome=hypothesis.prediction,
                accuracy=0.0,
                error_margin=0.0,
                notes={"error": "Could not determine direction"},
            )

        actual_change = ((actual_price - initial_price) / initial_price) * 100
        actual_direction = "up" if actual_change > 0 else "down"

        # Check if direction matches
        direction_correct = direction == actual_direction

        # Calculate accuracy based on magnitude match
        predicted_changes = self.parser.extract_percentage_changes(
            hypothesis.prediction
        )
        if predicted_changes:
            predicted_change = predicted_changes[0]
            magnitude_error = abs(predicted_change - actual_change)
            magnitude_accuracy = max(0.0, 1.0 - (magnitude_error / 100))
        else:
            magnitude_accuracy = 1.0 if direction_correct else 0.0

        accuracy = (1.0 if direction_correct else 0.0) * 0.5 + magnitude_accuracy * 0.5

        status = ValidationStatus.VALID if accuracy >= 0.5 else ValidationStatus.INVALID

        result = ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            status=status,
            actual_outcome=f"Price moved {actual_change:.2f}% to {actual_price}",
            predicted_outcome=hypothesis.prediction,
            accuracy=accuracy,
            error_margin=abs(actual_change) if predicted_changes else 0.0,
            notes={
                "predicted_direction": direction,
                "actual_direction": actual_direction,
                "actual_change_percent": actual_change,
            },
        )

        self.metrics.update(result)
        return result

    def _validate_reversal(
        self,
        hypothesis: Hypothesis,
        direction: str | None,
        actual_price: float,
        initial_price: float,
        high: float,
        low: float,
    ) -> ValidationResult:
        """Validate a reversal hypothesis."""
        # For reversal, we need to see if price moved against initial trend
        # This is simplified - in practice would need historical context

        price_range = high - low
        if price_range == 0:
            return ValidationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                status=ValidationStatus.INCONCLUSIVE,
                actual_outcome="No price movement to validate reversal",
                predicted_outcome=hypothesis.prediction,
                accuracy=0.0,
                error_margin=0.0,
            )

        # Calculate if there was a significant reversal
        max_move_from_start = max(abs(high - initial_price), abs(low - initial_price))
        reversal_strength = max_move_from_start / price_range if price_range > 0 else 0

        # For reversal, we expect price to move significantly and then reverse
        accuracy = min(1.0, reversal_strength)

        # Determine status based on whether reversal occurred
        if reversal_strength > 0.3:  # Significant movement
            status = ValidationStatus.VALID
        else:
            status = ValidationStatus.INVALID

        result = ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            status=status,
            actual_outcome=f"Price range: {low:.2f} - {high:.2f}",
            predicted_outcome=hypothesis.prediction,
            accuracy=accuracy,
            error_margin=1.0 - accuracy,
            notes={
                "reversal_strength": reversal_strength,
                "price_range": price_range,
            },
        )

        self.metrics.update(result)
        return result

    def _validate_range(
        self,
        hypothesis: Hypothesis,
        price_targets: list[float],
        actual_price: float,
        high: float,
        low: float,
    ) -> ValidationResult:
        """Validate a range-bound hypothesis."""
        if len(price_targets) >= 2:
            # Use extracted targets as range bounds
            expected_low = min(price_targets)
            expected_high = max(price_targets)
        else:
            # Use tolerance around current price
            expected_low = actual_price * (1 - self.config.tolerance_percent / 100)
            expected_high = actual_price * (1 + self.config.tolerance_percent / 100)

        # Check if price stayed within range
        actual_within_range = expected_low <= actual_price <= expected_high
        high_within_range = expected_low <= high <= expected_high
        low_within_range = expected_low <= low <= expected_high

        if actual_within_range and high_within_range and low_within_range:
            accuracy = 1.0
            status = ValidationStatus.VALID
        elif actual_within_range:
            accuracy = 0.7
            status = ValidationStatus.VALID
        else:
            # Calculate how far outside range
            if actual_price > expected_high:
                deviation = (actual_price - expected_high) / expected_high
            else:
                deviation = (expected_low - actual_price) / expected_low
            accuracy = max(0.0, 1.0 - deviation)
            status = ValidationStatus.INVALID

        result = ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            status=status,
            actual_outcome=f"Price: {actual_price}, Range: {low:.2f} - {high:.2f}",
            predicted_outcome=hypothesis.prediction,
            accuracy=accuracy,
            error_margin=1.0 - accuracy,
            notes={
                "expected_range": f"{expected_low:.2f} - {expected_high:.2f}",
                "actual_within_range": actual_within_range,
            },
        )

        self.metrics.update(result)
        return result

    def _validate_breakout(
        self,
        hypothesis: Hypothesis,
        direction: str | None,
        price_targets: list[float],
        high: float,
        low: float,
        initial_price: float,
    ) -> ValidationResult:
        """Validate a breakout hypothesis."""
        if not direction:
            return ValidationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                status=ValidationStatus.INCONCLUSIVE,
                actual_outcome=f"High: {high}, Low: {low}",
                predicted_outcome=hypothesis.prediction,
                accuracy=0.0,
                error_margin=0.0,
                notes={"error": "No direction specified for breakout"},
            )

        # Determine if breakout occurred in predicted direction
        if direction == "up":
            breakout_occurred = high > initial_price * 1.01  # 1% breakout threshold
            breakout_magnitude = (high - initial_price) / initial_price
        else:
            breakout_occurred = low < initial_price * 0.99  # 1% breakout threshold
            breakout_magnitude = (initial_price - low) / initial_price

        if breakout_occurred:
            accuracy = min(
                1.0, breakout_magnitude * 10
            )  # Scale up for meaningful breakouts
            status = ValidationStatus.VALID
        else:
            accuracy = 0.0
            status = ValidationStatus.INVALID

        result = ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            status=status,
            actual_outcome=f"High: {high}, Low: {low}, Initial: {initial_price}",
            predicted_outcome=hypothesis.prediction,
            accuracy=accuracy,
            error_margin=1.0 - accuracy,
            notes={
                "predicted_direction": direction,
                "breakout_occurred": breakout_occurred,
                "breakout_magnitude": breakout_magnitude,
            },
        )

        self.metrics.update(result)
        return result

    def _validate_generic(
        self,
        hypothesis: Hypothesis,
        price_targets: list[float],
        percentages: list[float],
        direction: str | None,
        actual_price: float,
        initial_price: float,
        high: float,
        low: float,
    ) -> ValidationResult:
        """Generic validation for hypothesis types without specific logic."""
        # Simple validation: check if any price target was hit
        if price_targets:
            tolerance = self.config.tolerance_percent / 100
            target_hit = any(
                abs(target - actual_price) / target <= tolerance
                or abs(target - high) / target <= tolerance
                or abs(target - low) / target <= tolerance
                for target in price_targets
            )

            if target_hit:
                accuracy = 1.0
                status = ValidationStatus.VALID
            else:
                # Calculate closest approach
                min_deviation = min(
                    abs(target - actual_price) / target for target in price_targets
                )
                accuracy = max(0.0, 1.0 - min_deviation)
                status = ValidationStatus.INVALID
        else:
            # No price targets - validate based on direction if available
            if direction and initial_price > 0:
                actual_change = ((actual_price - initial_price) / initial_price) * 100
                actual_direction = "up" if actual_change > 0 else "down"
                direction_correct = direction == actual_direction

                accuracy = 1.0 if direction_correct else 0.0
                status = (
                    ValidationStatus.VALID
                    if direction_correct
                    else ValidationStatus.INVALID
                )
            else:
                accuracy = 0.0
                status = ValidationStatus.INCONCLUSIVE

        result = ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            status=status,
            actual_outcome=f"Price: {actual_price}, Range: {low:.2f} - {high:.2f}",
            predicted_outcome=hypothesis.prediction,
            accuracy=accuracy,
            error_margin=1.0 - accuracy,
            notes={
                "price_targets": price_targets,
                "percentages": percentages,
                "direction": direction,
            },
        )

        self.metrics.update(result)
        return result

    def get_metrics(self) -> ValidationMetrics:
        """Get current validation metrics.

        Returns:
            Current validation metrics
        """
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset validation metrics."""
        self.metrics = ValidationMetrics()
