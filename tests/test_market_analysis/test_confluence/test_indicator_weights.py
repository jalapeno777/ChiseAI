"""Tests for indicator weight configuration."""

from market_analysis.confluence.indicator_weights import (
    DEFAULT_WEIGHTS,
    IndicatorWeights,
    WeightPreset,
)


class TestIndicatorWeights:
    """Test suite for IndicatorWeights class."""

    def test_default_initialization(self) -> None:
        """Test default weight initialization."""
        weights = IndicatorWeights()

        # Check default timeframe weights
        assert weights.timeframe_weights["1m"] == 0.5
        assert weights.timeframe_weights["5m"] == 0.7
        assert weights.timeframe_weights["15m"] == 0.9
        assert weights.timeframe_weights["1h"] == 1.0
        assert weights.timeframe_weights["4h"] == 1.1
        assert weights.timeframe_weights["1d"] == 1.3

        # Check default indicator weights
        assert weights.indicator_weights["rsi"] == 1.0
        assert weights.indicator_weights["macd"] == 1.2
        assert weights.indicator_weights["bb"] == 1.0
        assert weights.indicator_weights["markov"] == 1.3

        # Check other defaults
        assert weights.min_signal_threshold == 0.3
        assert weights.max_indicators == 10

    def test_get_weight_calculation(self) -> None:
        """Test combined weight calculation."""
        weights = IndicatorWeights()

        # Test known combinations
        assert weights.get_weight("rsi", "1h") == 1.0 * 1.0  # 1.0
        assert weights.get_weight("macd", "1h") == 1.2 * 1.0  # 1.2
        assert weights.get_weight("markov", "1d") == 1.3 * 1.3  # 1.69

    def test_get_weight_unknown_values(self) -> None:
        """Test weight calculation with unknown indicator/timeframe."""
        weights = IndicatorWeights()

        # Unknown values should default to 1.0
        assert weights.get_weight("unknown_indicator", "1h") == 1.0 * 1.0
        assert weights.get_weight("rsi", "unknown_timeframe") == 1.0 * 1.0
        assert weights.get_weight("unknown", "unknown") == 1.0 * 1.0

    def test_set_timeframe_weight(self) -> None:
        """Test setting timeframe weight."""
        weights = IndicatorWeights()

        weights.set_timeframe_weight("30m", 0.85)
        assert weights.timeframe_weights["30m"] == 0.85

        # Test overwriting existing
        weights.set_timeframe_weight("1h", 1.5)
        assert weights.timeframe_weights["1h"] == 1.5

    def test_set_indicator_weight(self) -> None:
        """Test setting indicator weight."""
        weights = IndicatorWeights()

        weights.set_indicator_weight("ema", 1.1)
        assert weights.indicator_weights["ema"] == 1.1

        # Test overwriting existing
        weights.set_indicator_weight("rsi", 0.8)
        assert weights.indicator_weights["rsi"] == 0.8

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        weights = IndicatorWeights()
        data = weights.to_dict()

        assert "timeframe_weights" in data
        assert "indicator_weights" in data
        assert "min_signal_threshold" in data
        assert "max_indicators" in data

        assert data["timeframe_weights"]["1h"] == 1.0
        assert data["indicator_weights"]["macd"] == 1.2
        assert data["min_signal_threshold"] == 0.3

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "timeframe_weights": {"1h": 1.5, "4h": 1.8},
            "indicator_weights": {"rsi": 0.9, "macd": 1.4},
            "min_signal_threshold": 0.4,
            "max_indicators": 8,
        }

        weights = IndicatorWeights.from_dict(data)

        assert weights.timeframe_weights["1h"] == 1.5
        assert weights.timeframe_weights["4h"] == 1.8
        assert weights.indicator_weights["rsi"] == 0.9
        assert weights.indicator_weights["macd"] == 1.4
        assert weights.min_signal_threshold == 0.4
        assert weights.max_indicators == 8

    def test_from_dict_defaults(self) -> None:
        """Test from_dict with missing values uses defaults."""
        data = {"timeframe_weights": {"1h": 1.5}}

        weights = IndicatorWeights.from_dict(data)

        assert weights.timeframe_weights["1h"] == 1.5
        # Should use defaults for missing values
        assert weights.min_signal_threshold == 0.3
        assert weights.max_indicators == 10

    def test_validate_valid_config(self) -> None:
        """Test validation with valid configuration."""
        weights = IndicatorWeights()
        errors = weights.validate()

        assert errors == []

    def test_validate_negative_timeframe_weight(self) -> None:
        """Test validation catches negative timeframe weight."""
        weights = IndicatorWeights()
        weights.timeframe_weights["1h"] = -0.5

        errors = weights.validate()

        assert len(errors) == 1
        assert "Negative timeframe weight" in errors[0]

    def test_validate_negative_indicator_weight(self) -> None:
        """Test validation catches negative indicator weight."""
        weights = IndicatorWeights()
        weights.indicator_weights["rsi"] = -1.0

        errors = weights.validate()

        assert len(errors) == 1
        assert "Negative indicator weight" in errors[0]

    def test_validate_invalid_threshold(self) -> None:
        """Test validation catches invalid threshold."""
        weights = IndicatorWeights()
        weights.min_signal_threshold = 1.5

        errors = weights.validate()

        assert len(errors) == 1
        assert "min_signal_threshold must be 0-1" in errors[0]

    def test_validate_invalid_max_indicators(self) -> None:
        """Test validation catches invalid max_indicators."""
        weights = IndicatorWeights()
        weights.max_indicators = 0

        errors = weights.validate()

        assert len(errors) == 1
        assert "max_indicators must be >= 1" in errors[0]

    def test_validate_multiple_errors(self) -> None:
        """Test validation returns multiple errors."""
        weights = IndicatorWeights()
        weights.timeframe_weights["1h"] = -0.5
        weights.indicator_weights["rsi"] = -1.0
        weights.min_signal_threshold = 2.0

        errors = weights.validate()

        assert len(errors) == 3


class TestWeightPresets:
    """Test suite for WeightPreset class."""

    def test_conservative_preset(self) -> None:
        """Test conservative preset configuration."""
        weights = WeightPreset.conservative()

        # Higher timeframe weights
        assert weights.timeframe_weights["1d"] == 1.5
        assert weights.timeframe_weights["1m"] == 0.3

        # Higher indicator weights for reliable indicators
        assert weights.indicator_weights["markov"] == 1.5
        assert weights.indicator_weights["macd"] == 1.3

        # Stricter thresholds
        assert weights.min_signal_threshold == 0.4
        assert weights.max_indicators == 8

    def test_aggressive_preset(self) -> None:
        """Test aggressive preset configuration."""
        weights = WeightPreset.aggressive()

        # More balanced timeframe weights
        assert weights.timeframe_weights["1m"] == 0.8
        assert weights.timeframe_weights["1d"] == 1.3

        # More balanced indicator weights
        assert weights.indicator_weights["rsi"] == 1.1
        assert weights.indicator_weights["markov"] == 1.2

        # Lower threshold, more indicators
        assert weights.min_signal_threshold == 0.2
        assert weights.max_indicators == 12

    def test_balanced_preset(self) -> None:
        """Test balanced preset matches defaults."""
        weights = WeightPreset.balanced()
        defaults = IndicatorWeights()

        assert weights.timeframe_weights == defaults.timeframe_weights
        assert weights.indicator_weights == defaults.indicator_weights
        assert weights.min_signal_threshold == defaults.min_signal_threshold
        assert weights.max_indicators == defaults.max_indicators

    def test_default_weights_constant(self) -> None:
        """Test DEFAULT_WEIGHTS constant."""
        defaults = IndicatorWeights()

        assert DEFAULT_WEIGHTS.timeframe_weights == defaults.timeframe_weights
        assert DEFAULT_WEIGHTS.indicator_weights == defaults.indicator_weights
