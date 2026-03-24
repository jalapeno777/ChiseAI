"""
Pattern Recognition Engine for price action analysis.

Deep learning model for detecting patterns in time series data using
convolutional and LSTM layers.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from src.neuro_symbolic.neural.network import NetworkConfig, NeuralNetwork


class PatternType(Enum):
    """Types of recognizable patterns."""

    HEAD_AND_SHOULDERS = "head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    BULL_FLAG = "bull_flag"
    BEAR_FLAG = "bear_flag"
    CUP_AND_HANDLE = "cup_and_handle"
    ROUNDED_BOTTOM = "rounded_bottom"
    WEDGE_RISING = "wedge_rising"
    WEDGE_FALLING = "wedge_falling"
    CHANNEL_UP = "channel_up"
    CHANNEL_DOWN = "channel_down"
    V_TOP = "v_top"
    V_BOTTOM = "v_bottom"
    UNKNOWN = "unknown"


@dataclass
class PatternMatch:
    """Represents a detected pattern match."""

    pattern_type: PatternType
    confidence: float
    start_idx: int
    end_idx: int
    features: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "pattern_type": self.pattern_type.value,
            "confidence": self.confidence,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "features": self.features,
            "metadata": self.metadata,
        }


@dataclass
class PatternRecognitionConfig:
    """Configuration for pattern recognition engine."""

    sequence_length: int = 50
    num_features: int = 5  # OHLCV
    num_pattern_classes: int = len(PatternType) - 1  # Exclude UNKNOWN
    confidence_threshold: float = 0.7
    min_pattern_length: int = 10
    max_pattern_length: int = 100
    use_technical_indicators: bool = True
    smoothing_window: int = 3


class PatternRecognitionEngine:
    """Deep learning engine for pattern recognition in price action.

    Uses a combination of convolutional and LSTM layers to detect
    complex patterns in time series data.
    """

    PATTERN_NAMES = [p.value for p in PatternType if p != PatternType.UNKNOWN]

    def __init__(self, config: PatternRecognitionConfig | None = None):
        """Initialize pattern recognition engine.

        Args:
            config: Engine configuration. Uses defaults if None.
        """
        self.config = config or PatternRecognitionConfig()
        self.network: NeuralNetwork | None = None
        self._build_network()
        self._pattern_library: dict[str, np.ndarray] = {}
        self._load_default_patterns()

    def _build_network(self) -> None:
        """Build the neural network for pattern recognition."""
        # Use a simpler architecture with Dense layers for reliability
        network_config = NetworkConfig(
            input_shape=(self.config.sequence_length, self.config.num_features),
            output_size=self.config.num_pattern_classes,
            layers=[
                {
                    "type": "lstm",
                    "units": 64,
                    "return_sequences": True,
                },
                {
                    "type": "lstm",
                    "units": 32,
                    "return_sequences": False,
                },
                {
                    "type": "dense",
                    "units": 32,
                    "activation": "relu",
                },
                {
                    "type": "dropout",
                    "rate": 0.3,
                },
                {
                    "type": "dense",
                    "units": self.config.num_pattern_classes,
                    "activation": "softmax",
                },
            ],
            learning_rate=0.001,
            loss="categorical_crossentropy",
        )
        self.network = NeuralNetwork(network_config)

    def _load_default_patterns(self) -> None:
        """Load default pattern templates into library."""
        # Generate synthetic pattern templates
        self._pattern_library = {
            "double_top": self._generate_double_top_template(),
            "double_bottom": self._generate_double_bottom_template(),
            "head_and_shoulders": self._generate_head_shoulders_template(),
            "ascending_triangle": self._generate_ascending_triangle_template(),
            "descending_triangle": self._generate_descending_triangle_template(),
            "bull_flag": self._generate_bull_flag_template(),
            "bear_flag": self._generate_bear_flag_template(),
            "cup_and_handle": self._generate_cup_handle_template(),
        }

    def _generate_double_top_template(self) -> np.ndarray:
        """Generate double top pattern template."""
        x = np.linspace(0, 2 * np.pi, self.config.sequence_length)
        template = -np.abs(np.sin(x)) + 1  # Two peaks
        return template / np.max(np.abs(template))

    def _generate_double_bottom_template(self) -> np.ndarray:
        """Generate double bottom pattern template."""
        x = np.linspace(0, 2 * np.pi, self.config.sequence_length)
        template = np.abs(np.sin(x)) - 1  # Two troughs
        return template / np.max(np.abs(template))

    def _generate_head_shoulders_template(self) -> np.ndarray:
        """Generate head and shoulders pattern template."""
        seq_len = self.config.sequence_length
        x = np.linspace(0, 3 * np.pi, seq_len)
        # Three peaks: smaller, larger, smaller - create amplitude modulation
        amplitude = np.zeros(seq_len)
        for i in range(seq_len):
            phase = i / seq_len
            if phase < 0.33:
                amplitude[i] = 0.7
            elif phase < 0.67:
                amplitude[i] = 1.0
            else:
                amplitude[i] = 0.7
        template = np.sin(x) * amplitude
        return template / np.max(np.abs(template))

    def _generate_ascending_triangle_template(self) -> np.ndarray:
        """Generate ascending triangle pattern template."""
        seq_len = self.config.sequence_length
        template = np.zeros(seq_len)
        for i in range(seq_len):
            # Flat top, rising bottom
            template[i] = 0.3 + (i / seq_len) * 0.4
            if i > seq_len // 2:
                template[i] = min(template[i], 0.7)
        return template / np.max(np.abs(template))

    def _generate_descending_triangle_template(self) -> np.ndarray:
        """Generate descending triangle pattern template."""
        seq_len = self.config.sequence_length
        template = np.zeros(seq_len)
        for i in range(seq_len):
            # Flat bottom, falling top
            template[i] = 0.7 - (i / seq_len) * 0.4
            if i > seq_len // 2:
                template[i] = max(template[i], 0.3)
        return template / np.max(np.abs(template))

    def _generate_bull_flag_template(self) -> np.ndarray:
        """Generate bull flag pattern template."""
        seq_len = self.config.sequence_length
        template = np.zeros(seq_len)
        # Sharp rise, then consolidation
        for i in range(seq_len):
            if i < seq_len // 4:
                template[i] = (i / (seq_len // 4)) * 0.8
            else:
                template[i] = 0.8 - (i - seq_len // 4) * 0.002
        return template / np.max(np.abs(template))

    def _generate_bear_flag_template(self) -> np.ndarray:
        """Generate bear flag pattern template."""
        seq_len = self.config.sequence_length
        template = np.zeros(seq_len)
        # Sharp fall, then consolidation
        for i in range(seq_len):
            if i < seq_len // 4:
                template[i] = 0.8 - (i / (seq_len // 4)) * 0.8
            else:
                template[i] = 0.0 + (i - seq_len // 4) * 0.002
        return template / np.max(np.abs(template))

    def _generate_cup_handle_template(self) -> np.ndarray:
        """Generate cup and handle pattern template."""
        seq_len = self.config.sequence_length
        template = np.zeros(seq_len)
        for i in range(seq_len):
            if i < seq_len * 0.8:
                # Cup shape (U-shaped)
                x = (i / (seq_len * 0.8)) * np.pi
                template[i] = -np.sin(x) * 0.5 + 0.5
            else:
                # Handle (small dip)
                handle_pos = (i - seq_len * 0.8) / (seq_len * 0.2)
                template[i] = 0.5 - handle_pos * 0.1
        return template / np.max(np.abs(template))

    def preprocess_data(
        self,
        data: list[float] | np.ndarray,
        normalize: bool = True,
    ) -> np.ndarray:
        """Preprocess raw price data for pattern detection.

        Args:
            data: Raw price data (list or array)
            normalize: Whether to normalize data

        Returns:
            Preprocessed data array of shape (1, sequence_length, features)
        """
        if isinstance(data, list):
            data = np.array(data)

        # Handle empty data
        if len(data) == 0:
            # Return zeros array with correct shape
            return np.zeros((1, self.config.sequence_length, self.config.num_features))

        # Handle 1D data
        if data.ndim == 1:
            # Reshape to (1, seq_len, 1)
            if len(data) < self.config.sequence_length:
                # Pad with edge values (use constant for small arrays)
                pad_size = self.config.sequence_length - len(data)
                if len(data) > 0:
                    data = np.pad(
                        data, (pad_size, 0), mode="constant", constant_values=data[0]
                    )
                else:
                    data = np.zeros(self.config.sequence_length)
            data = data[-self.config.sequence_length :]
            data = data.reshape(1, -1, 1)

            # Create pseudo-OHLCV features from single price series
            ohlcv = np.zeros((1, self.config.sequence_length, 5))
            ohlcv[:, :, 0] = data[:, :, 0]  # Close
            ohlcv[:, :, 1] = data[:, :, 0] * 1.001  # High (pseudo)
            ohlcv[:, :, 2] = data[:, :, 0] * 0.999  # Low (pseudo)
            ohlcv[:, :, 3] = data[:, :, 0]  # Open (same as close for simplicity)
            ohlcv[:, :, 4] = 1000  # Volume (placeholder)
            data = ohlcv

        # Normalize if requested
        if normalize:
            mean = np.mean(data, axis=1, keepdims=True)
            std = np.std(data, axis=1, keepdims=True) + 1e-8
            data = (data - mean) / std

        return data

    def detect_patterns(
        self,
        data: list[float] | np.ndarray,
        return_all: bool = False,
    ) -> PatternMatch | list[PatternMatch] | None:
        """Detect patterns in price data.

        Args:
            data: Price data to analyze
            return_all: Return all pattern matches above threshold

        Returns:
            PatternMatch, list of PatternMatch, or None if no patterns found
        """
        preprocessed = self.preprocess_data(data)

        if self.network is None:
            return None

        # Get network predictions
        predictions = self.network.predict(preprocessed)

        # Get top predictions
        if predictions.ndim == 2:
            predictions = predictions[0]

        # Create pattern matches
        matches = []
        for i, confidence in enumerate(predictions):
            if confidence >= self.config.confidence_threshold:
                try:
                    pattern_type = PatternType(self.PATTERN_NAMES[i])
                except (IndexError, ValueError):
                    continue

                match = PatternMatch(
                    pattern_type=pattern_type,
                    confidence=float(confidence),
                    start_idx=0,
                    end_idx=self.config.sequence_length - 1,
                    features={"raw_confidence": float(confidence)},
                )
                matches.append(match)

        if not matches:
            return None

        # Sort by confidence
        matches.sort(key=lambda x: x.confidence, reverse=True)

        if return_all:
            return matches

        return matches[0]

    def get_pattern_probabilities(
        self, data: list[float] | np.ndarray
    ) -> dict[str, float]:
        """Get probability distribution over all patterns.

        Args:
            data: Price data to analyze

        Returns:
            Dictionary mapping pattern names to probabilities
        """
        preprocessed = self.preprocess_data(data)
        predictions = self.network.predict(preprocessed)

        if predictions.ndim == 2:
            predictions = predictions[0]

        return {
            name: float(prob)
            for name, prob in zip(self.PATTERN_NAMES, predictions, strict=False)
        }

    def compute_features(self, data: list[float] | np.ndarray) -> dict[str, float]:
        """Compute technical features for pattern analysis.

        Args:
            data: Price data

        Returns:
            Dictionary of computed features
        """
        if isinstance(data, list):
            data = np.array(data)

        if data.ndim == 1:
            close = data
        else:
            close = data[:, 0] if data.ndim == 2 else data[0, :, 0]

        features = {}

        # Price momentum
        if len(close) > 1:
            features["momentum"] = float(close[-1] - close[0])
            features["momentum_pct"] = float((close[-1] - close[0]) / close[0])

        # Volatility
        features["volatility"] = float(np.std(close) / np.mean(close))

        # Trend
        if len(close) > 5:
            x = np.arange(len(close), dtype=float)
            try:
                slope = np.polyfit(x, close.astype(float), 1)[0]
                features["trend_slope"] = float(slope)
            except (ValueError, TypeError):
                features["trend_slope"] = 0.0

        # Local extrema count
        local_max = 0
        local_min = 0
        for i in range(1, len(close) - 1):
            if close[i] > close[i - 1] and close[i] > close[i + 1]:
                local_max += 1
            if close[i] < close[i - 1] and close[i] < close[i + 1]:
                local_min += 1

        features["local_max_count"] = local_max
        features["local_min_count"] = local_min

        # Pattern-specific features
        features["peak_to_peak_range"] = float(np.max(close) - np.min(close))
        features["mean_reversion"] = float(np.mean(np.abs(close - np.mean(close))))

        return features

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        **kwargs,
    ) -> dict[str, list[float]]:
        """Train the pattern recognition model.

        Args:
            x: Training data
            y: Training labels (one-hot encoded)
            **kwargs: Additional training arguments

        Returns:
            Training history
        """
        if self.network is None:
            self._build_network()

        return self.network.fit(x, y, **kwargs)

    def save(self, path: str | Path) -> None:
        """Save engine state to disk.

        Args:
            path: Directory to save engine
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if self.network:
            self.network.save(path / "network")

        # Save config
        import json

        config_dict = {
            "sequence_length": self.config.sequence_length,
            "num_features": self.config.num_features,
            "num_pattern_classes": self.config.num_pattern_classes,
            "confidence_threshold": self.config.confidence_threshold,
            "min_pattern_length": self.config.min_pattern_length,
            "max_pattern_length": self.config.max_pattern_length,
            "use_technical_indicators": self.config.use_technical_indicators,
            "smoothing_window": self.config.smoothing_window,
        }

        with open(path / "engine_config.json", "w") as f:
            json.dump(config_dict, f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "PatternRecognitionEngine":
        """Load engine from saved state.

        Args:
            path: Directory containing saved engine

        Returns:
            Loaded PatternRecognitionEngine
        """
        import json

        path = Path(path)

        with open(path / "engine_config.json") as f:
            config_dict = json.load(f)

        config = PatternRecognitionConfig(**config_dict)
        engine = cls(config)

        if (path / "network").exists():
            engine.network = NeuralNetwork.load(path / "network")

        return engine

    def get_supported_patterns(self) -> list[str]:
        """Get list of supported pattern types.

        Returns:
            List of pattern type names
        """
        return self.PATTERN_NAMES.copy()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"PatternRecognitionEngine("
            f"patterns={self.config.num_pattern_classes}, "
            f"seq_len={self.config.sequence_length}, "
            f"threshold={self.config.confidence_threshold})"
        )
