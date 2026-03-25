"""Indicator weight configuration for confluence scoring.

Provides configurable weights for different indicators and timeframes
to enable flexible confluence scoring based on indicator reliability
and timeframe importance.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndicatorWeights:
    """Configuration for indicator and timeframe weights.

    Weights are multiplicative: final_weight = timeframe_weight * indicator_weight

    Attributes:
        timeframe_weights: Dict mapping timeframe strings to weight multipliers
        indicator_weights: Dict mapping indicator names to weight multipliers
        min_signal_threshold: Minimum signal strength to include (0-1)
        max_indicators: Maximum number of indicators to consider
    """

    # Timeframe importance weights (higher = more important)
    timeframe_weights: dict[str, float] = field(
        default_factory=lambda: {
            "1m": 0.5,  # 1 minute - lowest weight (noise)
            "5m": 0.7,  # 5 minutes
            "15m": 0.9,  # 15 minutes
            "1h": 1.0,  # 1 hour - baseline
            "4h": 1.1,  # 4 hours
            "1d": 1.3,  # 1 day - highest weight (trend)
        }
    )

    # Indicator type reliability weights
    indicator_weights: dict[str, float] = field(
        default_factory=lambda: {
            "rsi": 1.0,  # RSI - reliable for extremes
            "macd": 1.2,  # MACD - strong trend indicator
            "bb": 1.0,  # Bollinger Bands - volatility-based
            "markov": 1.3,  # Markov state - highest reliability (composite)
        }
    )

    # Minimum signal strength threshold (0-1)
    min_signal_threshold: float = 0.3

    # Maximum number of indicators to aggregate
    max_indicators: int = 10

    def get_weight(self, indicator_type: str, timeframe: str) -> float:
        """Calculate combined weight for an indicator at a specific timeframe.

        Args:
            indicator_type: Type of indicator (rsi, macd, bb, markov)
            timeframe: Timeframe string (1m, 5m, 15m, 1h, 4h, 1d)

        Returns:
            Combined weight (timeframe_weight * indicator_weight)
        """
        tf_weight = self.timeframe_weights.get(timeframe, 1.0)
        ind_weight = self.indicator_weights.get(indicator_type, 1.0)
        return tf_weight * ind_weight

    def set_timeframe_weight(self, timeframe: str, weight: float) -> None:
        """Set weight for a specific timeframe.

        Args:
            timeframe: Timeframe string
            weight: Weight value (typically 0.5-1.5)
        """
        self.timeframe_weights[timeframe] = weight

    def set_indicator_weight(self, indicator_type: str, weight: float) -> None:
        """Set weight for a specific indicator type.

        Args:
            indicator_type: Indicator name
            weight: Weight value (typically 0.8-1.5)
        """
        self.indicator_weights[indicator_type] = weight

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary for serialization.

        Returns:
            Dictionary representation of weights configuration
        """
        return {
            "timeframe_weights": self.timeframe_weights.copy(),
            "indicator_weights": self.indicator_weights.copy(),
            "min_signal_threshold": self.min_signal_threshold,
            "max_indicators": self.max_indicators,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndicatorWeights":
        """Create configuration from dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            New IndicatorWeights instance
        """
        return cls(
            timeframe_weights=data.get("timeframe_weights", {}),
            indicator_weights=data.get("indicator_weights", {}),
            min_signal_threshold=data.get("min_signal_threshold", 0.3),
            max_indicators=data.get("max_indicators", 10),
        )

    def validate(self) -> list[str]:
        """Validate weight configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check for negative weights
        for tf, weight in self.timeframe_weights.items():
            if weight < 0:
                errors.append(f"Negative timeframe weight for {tf}: {weight}")

        for ind, weight in self.indicator_weights.items():
            if weight < 0:
                errors.append(f"Negative indicator weight for {ind}: {weight}")

        # Check threshold range
        if not 0 <= self.min_signal_threshold <= 1:
            errors.append(
                f"min_signal_threshold must be 0-1, got {self.min_signal_threshold}"
            )

        # Check max_indicators
        if self.max_indicators < 1:
            errors.append(f"max_indicators must be >= 1, got {self.max_indicators}")

        return errors


# Default weights instance for convenience
DEFAULT_WEIGHTS = IndicatorWeights()


class WeightPreset:
    """Predefined weight configurations for common scenarios."""

    @staticmethod
    def conservative() -> IndicatorWeights:
        """Conservative weights favoring higher timeframes and reliable indicators.

        Returns:
            IndicatorWeights with conservative settings
        """
        return IndicatorWeights(
            timeframe_weights={
                "1m": 0.3,
                "5m": 0.5,
                "15m": 0.7,
                "1h": 1.0,
                "4h": 1.2,
                "1d": 1.5,
            },
            indicator_weights={
                "rsi": 0.9,
                "macd": 1.3,
                "bb": 0.9,
                "markov": 1.5,
                "order_flow": 1.0,
            },
            min_signal_threshold=0.4,
            max_indicators=8,
        )

    @staticmethod
    def aggressive() -> IndicatorWeights:
        """Aggressive weights with more emphasis on lower timeframes.

        Returns:
            IndicatorWeights with aggressive settings
        """
        return IndicatorWeights(
            timeframe_weights={
                "1m": 0.8,
                "5m": 0.9,
                "15m": 1.0,
                "1h": 1.1,
                "4h": 1.2,
                "1d": 1.3,
            },
            indicator_weights={
                "rsi": 1.1,
                "macd": 1.1,
                "bb": 1.1,
                "markov": 1.2,
                "order_flow": 1.2,
            },
            min_signal_threshold=0.2,
            max_indicators=12,
        )

    @staticmethod
    def balanced() -> IndicatorWeights:
        """Balanced weights - the default configuration.

        Returns:
            IndicatorWeights with balanced settings
        """
        return IndicatorWeights()
