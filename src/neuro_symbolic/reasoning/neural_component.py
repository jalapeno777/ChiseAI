"""Neural component for pattern recognition and feature extraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class NeuralOutput:
    """Output from neural component analysis."""

    features: np.ndarray
    patterns: list[dict[str, Any]]
    confidence: float
    raw_predictions: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FeatureExtractor(ABC):
    """Abstract base class for feature extraction."""

    @abstractmethod
    def extract(self, data: dict[str, Any]) -> np.ndarray:
        """Extract features from input data."""
        pass


class MarketFeatureExtractor(FeatureExtractor):
    """Extract market-related features from trading data."""

    def __init__(self, feature_dim: int = 32):
        self.feature_dim = feature_dim
        self._feature_names = [
            "price_normalized",
            "volume_normalized",
            "price_momentum",
            "volume_momentum",
            "volatility_estimate",
            "trend_strength",
            "support_resistance",
            "price_acceleration",
            "volume_acceleration",
            "relative_strength",
            "moving_avg_deviation",
            "volume_price_correlation",
        ]

    def extract(self, data: dict[str, Any]) -> np.ndarray:
        """Extract market features from input data."""
        features = np.zeros(self.feature_dim)

        # Helper to safely get float values (handles None)
        def safe_float(value, default=0.0):
            if value is None:
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        # Extract basic values with defaults
        price = safe_float(data.get("price"), 0.0)
        volume = safe_float(data.get("volume"), 0.0)
        high = safe_float(data.get("high"), price)
        low = safe_float(data.get("low"), price)
        prev_price = safe_float(data.get("prev_price"), price)
        prev_volume = safe_float(data.get("prev_volume"), volume)
        avg_price = safe_float(data.get("avg_price"), price)
        avg_volume = safe_float(data.get("avg_volume"), volume)

        # Price-based features
        if price > 0:
            features[0] = np.log1p(price) / 20.0  # Normalized log price
            features[4] = (
                (high - low) / price if price > 0 else 0
            )  # Volatility estimate

            if avg_price > 0:
                features[10] = (price - avg_price) / avg_price  # Moving avg deviation

        # Volume-based features
        if volume > 0:
            features[1] = np.log1p(volume) / 20.0  # Normalized log volume

            if avg_volume > 0:
                features[9] = volume / avg_volume  # Relative volume strength

        # Momentum features
        if prev_price > 0:
            features[2] = (price - prev_price) / prev_price  # Price momentum
            features[7] = (
                features[2]
                - (prev_price - float(data.get("prev_price_2", prev_price)))
                / prev_price
                if prev_price > 0
                else 0
            )

        if prev_volume > 0:
            features[3] = (volume - prev_volume) / prev_volume  # Volume momentum
            features[8] = (
                features[3]
                - (prev_volume - float(data.get("prev_volume_2", prev_volume)))
                / prev_volume
                if prev_volume > 0
                else 0
            )

        # Trend strength (simple approximation)
        if price > 0 and prev_price > 0:
            price_change = (price - prev_price) / prev_price
            features[5] = np.tanh(price_change * 10)  # Bounded trend strength

        # Support/resistance proxy
        if high > low and high > 0:
            features[6] = (price - low) / (high - low)  # Position in range

        # Volume-price correlation proxy
        if volume > 0 and prev_volume > 0 and price > 0 and prev_price > 0:
            price_dir = np.sign(price - prev_price)
            vol_dir = np.sign(volume - prev_volume)
            features[11] = price_dir * vol_dir  # Correlation indicator

        # Fill remaining features with derived values
        for i in range(12, self.feature_dim):
            # Create synthetic features for additional dimensionality
            features[i] = np.sin(i * features[0] + features[1]) * 0.1

        return features


class PatternRecognizer:
    """Recognize patterns in market data using neural-like processing."""

    def __init__(self, num_patterns: int = 10):
        self.num_patterns = num_patterns
        self._pattern_weights = np.random.randn(num_patterns, 32) * 0.1
        self._pattern_biases = np.random.randn(num_patterns) * 0.01

    def recognize(self, features: np.ndarray) -> list[dict[str, Any]]:
        """Recognize patterns from extracted features."""
        patterns = []

        # Compute pattern activations (simple feedforward)
        activations = np.dot(self._pattern_weights, features) + self._pattern_biases
        activations = 1 / (1 + np.exp(-activations))  # Sigmoid activation

        # Get top patterns
        top_indices = np.argsort(activations)[-5:][::-1]

        pattern_names = [
            "uptrend",
            "downtrend",
            "consolidation",
            "breakout",
            "reversal",
            "volume_spike",
            "support_test",
            "resistance_test",
            "momentum_shift",
            "accumulation",
        ]

        for idx in top_indices:
            if activations[idx] > 0.3:  # Threshold for pattern detection
                patterns.append(
                    {
                        "name": (
                            pattern_names[idx]
                            if idx < len(pattern_names)
                            else f"pattern_{idx}"
                        ),
                        "confidence": float(activations[idx]),
                        "type": "neural",
                        "features_contributing": self._get_top_feature_contributions(
                            idx, features
                        ),
                    }
                )

        return patterns

    def _get_top_feature_contributions(
        self, pattern_idx: int, features: np.ndarray
    ) -> list[str]:
        """Get names of features contributing most to a pattern."""
        contributions = np.abs(self._pattern_weights[pattern_idx] * features)
        top_feature_indices = np.argsort(contributions)[-3:][::-1]

        feature_names = ["price", "volume", "momentum", "volatility"]

        return [feature_names[i % len(feature_names)] for i in top_feature_indices]


class NeuralComponent:
    """Neural network component for hybrid reasoning.

    Handles pattern recognition and feature extraction from market data
    using neural network-inspired approaches.
    """

    def __init__(
        self,
        feature_dim: int = 32,
        num_patterns: int = 10,
        confidence_threshold: float = 0.5,
    ):
        self.feature_dim = feature_dim
        self.num_patterns = num_patterns
        self.confidence_threshold = confidence_threshold

        self._feature_extractor = MarketFeatureExtractor(feature_dim)
        self._pattern_recognizer = PatternRecognizer(num_patterns)

        # State for tracking
        self._last_features: np.ndarray | None = None
        self._last_patterns: list[dict[str, Any]] = []

    def process(self, data: dict[str, Any]) -> NeuralOutput:
        """Process input data through neural component.

        Args:
            data: Input market data dictionary with fields like
                  'price', 'volume', 'high', 'low', etc.

        Returns:
            NeuralOutput containing features, patterns, and confidence.
        """
        # Extract features
        features = self._feature_extractor.extract(data)
        self._last_features = features

        # Recognize patterns
        patterns = self._pattern_recognizer.recognize(features)
        self._last_patterns = patterns

        # Compute overall confidence
        if patterns:
            confidence = float(np.mean([p["confidence"] for p in patterns]))
        else:
            confidence = 0.0

        return NeuralOutput(
            features=features,
            patterns=patterns,
            confidence=confidence,
            metadata={
                "feature_dim": self.feature_dim,
                "num_patterns_detected": len(patterns),
                "processing_type": "neural",
            },
        )

    def get_feature_importance(self) -> dict[str, float]:
        """Get importance scores for features based on recent processing."""
        if self._last_features is None:
            return {}

        feature_names = self._feature_extractor._feature_names
        importance = {}

        for i, name in enumerate(feature_names):
            if i < len(self._last_features):
                importance[name] = float(abs(self._last_features[i]))

        return importance

    def reset_state(self) -> None:
        """Reset internal state."""
        self._last_features = None
        self._last_patterns = []
