"""Feature Importance Analyzer Module.

Analyzes which features contributed to predictions using SHAP-style
value attribution and provides visual importance ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import logging
import math

logger = logging.getLogger(__name__)


class ImportanceMethod(Enum):
    """Methods for calculating feature importance."""

    SHAP = "shap"  # SHAP values
    PERMUTATION = "permutation"  # Permutation importance
    GAIN = "gain"  # Tree-based gain
    WEIGHT = "weight"  # Feature weight/frequency
    CORRELATION = "correlation"  # Correlation-based
    INTEGRATED_GRADIENTS = "integrated_gradients"  # Gradient-based


@dataclass
class FeatureContribution:
    """Contribution of a single feature to a prediction."""

    feature_name: str
    contribution_value: float  # SHAP-style value (can be positive or negative)
    base_value: float = 0.0  # Base/expected value
    feature_value: Optional[float] = None  # Actual feature value
    interaction_effects: dict[str, float] = field(default_factory=dict)

    @property
    def absolute_contribution(self) -> float:
        """Absolute value of contribution."""
        return abs(self.contribution_value)

    @property
    def direction(self) -> str:
        """Direction of contribution."""
        if self.contribution_value > 0:
            return "positive"
        elif self.contribution_value < 0:
            return "negative"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "feature_name": self.feature_name,
            "contribution_value": self.contribution_value,
            "base_value": self.base_value,
            "feature_value": self.feature_value,
            "absolute_contribution": self.absolute_contribution,
            "direction": self.direction,
            "interaction_effects": self.interaction_effects,
        }


@dataclass
class FeatureImportanceResult:
    """Complete feature importance analysis result."""

    contributions: list[FeatureContribution]
    method: ImportanceMethod
    base_prediction: float  # Expected value without features
    final_prediction: float  # Actual prediction value
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_positive_contribution(self) -> float:
        """Sum of all positive contributions."""
        return sum(
            c.contribution_value for c in self.contributions if c.contribution_value > 0
        )

    @property
    def total_negative_contribution(self) -> float:
        """Sum of all negative contributions."""
        return sum(
            c.contribution_value for c in self.contributions if c.contribution_value < 0
        )

    @property
    def top_positive_features(self) -> list[FeatureContribution]:
        """Features with highest positive contribution."""
        positive = [c for c in self.contributions if c.contribution_value > 0]
        return sorted(positive, key=lambda x: x.contribution_value, reverse=True)

    @property
    def top_negative_features(self) -> list[FeatureContribution]:
        """Features with highest negative contribution."""
        negative = [c for c in self.contributions if c.contribution_value < 0]
        return sorted(negative, key=lambda x: x.contribution_value)

    def get_ranked_features(self, top_n: int = 10) -> list[FeatureContribution]:
        """Get top N features by absolute contribution."""
        sorted_contributions = sorted(
            self.contributions,
            key=lambda x: x.absolute_contribution,
            reverse=True,
        )
        return sorted_contributions[:top_n]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "contributions": [c.to_dict() for c in self.contributions],
            "method": self.method.value,
            "base_prediction": self.base_prediction,
            "final_prediction": self.final_prediction,
            "confidence": self.confidence,
            "total_positive": self.total_positive_contribution,
            "total_negative": self.total_negative_contribution,
            "metadata": self.metadata,
        }


@dataclass
class ImportanceVisualization:
    """Visualization data for feature importance."""

    feature_names: list[str]
    values: list[float]
    colors: list[str]
    title: str = "Feature Importance"
    x_label: str = "Contribution"
    y_label: str = "Feature"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "feature_names": self.feature_names,
            "values": self.values,
            "colors": self.colors,
            "title": self.title,
            "x_label": self.x_label,
            "y_label": self.y_label,
        }


class FeatureImportanceAnalyzer:
    """Analyzes feature contributions using SHAP-style value attribution.

    This class provides methods for calculating and visualizing feature
    importance, supporting multiple attribution methods including SHAP-style
    additive feature attributions.

    Example:
        >>> analyzer = FeatureImportanceAnalyzer()
        >>> result = analyzer.analyze(
        ...     features={'rsi': 30, 'macd': 0.5, 'volume': 1.2},
        ...     prediction=0.85,
        ...     base_value=0.5
        ... )
        >>> print(result.get_ranked_features(3))
        [FeatureContribution(...), FeatureContribution(...), FeatureContribution(...)]
    """

    # Default feature weights for different signal types
    _DEFAULT_WEIGHTS = {
        "rsi": 0.15,
        "macd": 0.20,
        "volume": 0.10,
        "trend": 0.25,
        "volatility": 0.10,
        "momentum": 0.15,
        "support_resistance": 0.05,
    }

    # Feature value thresholds for contribution calculation
    _FEATURE_THRESHOLDS = {
        "rsi": {
            "oversold": 30,
            "neutral_low": 40,
            "neutral_high": 60,
            "overbought": 70,
        },
        "macd": {"bearish": -0.1, "neutral": 0.1, "bullish": 0.3},
        "volume": {"low": 0.5, "normal": 1.0, "high": 1.5},
        "volatility": {"low": 0.01, "normal": 0.02, "high": 0.04},
    }

    def __init__(
        self,
        method: ImportanceMethod = ImportanceMethod.SHAP,
        feature_weights: Optional[dict[str, float]] = None,
    ):
        """Initialize the feature importance analyzer.

        Args:
            method: The attribution method to use.
            feature_weights: Custom weights for features.
        """
        self.method = method
        self.feature_weights = feature_weights or self._DEFAULT_WEIGHTS.copy()
        logger.info(
            "FeatureImportanceAnalyzer initialized with method=%s",
            method.value,
        )

    def analyze(
        self,
        features: dict[str, Any],
        prediction: float,
        base_value: float = 0.5,
        model_output: Optional[dict[str, Any]] = None,
    ) -> FeatureImportanceResult:
        """Analyze feature contributions to a prediction.

        Args:
            features: Dictionary of feature names to values.
            prediction: The model's prediction value.
            base_value: The expected/base prediction value.
            model_output: Optional additional model output for analysis.

        Returns:
            FeatureImportanceResult with all contributions.
        """
        # Calculate contributions based on method
        if self.method == ImportanceMethod.SHAP:
            contributions = self._calculate_shap_values(
                features, prediction, base_value
            )
        elif self.method == ImportanceMethod.PERMUTATION:
            contributions = self._calculate_permutation_importance(
                features, prediction, base_value
            )
        else:
            contributions = self._calculate_weighted_contributions(
                features, prediction, base_value
            )

        # Normalize contributions to sum to prediction difference
        total_contribution = sum(c.contribution_value for c in contributions)
        prediction_delta = prediction - base_value

        if (
            total_contribution != 0
            and abs(total_contribution - prediction_delta) > 0.001
        ):
            # Scale contributions to match prediction delta
            scale_factor = prediction_delta / total_contribution
            for contrib in contributions:
                contrib.contribution_value *= scale_factor

        return FeatureImportanceResult(
            contributions=contributions,
            method=self.method,
            base_prediction=base_value,
            final_prediction=prediction,
            confidence=self._calculate_confidence(contributions),
            metadata={"feature_count": len(features)},
        )

    def analyze_batch(
        self,
        feature_list: list[dict[str, Any]],
        predictions: list[float],
        base_value: float = 0.5,
    ) -> list[FeatureImportanceResult]:
        """Analyze feature importance for multiple predictions.

        Args:
            feature_list: List of feature dictionaries.
            predictions: List of prediction values.
            base_value: Base prediction value.

        Returns:
            List of FeatureImportanceResult objects.
        """
        results = []
        for features, prediction in zip(feature_list, predictions):
            result = self.analyze(features, prediction, base_value)
            results.append(result)
        return results

    def get_global_importance(
        self,
        results: list[FeatureImportanceResult],
    ) -> dict[str, float]:
        """Calculate global feature importance from multiple results.

        Args:
            results: List of analysis results.

        Returns:
            Dictionary of feature names to global importance scores.
        """
        feature_importance: dict[str, list[float]] = {}

        for result in results:
            for contrib in result.contributions:
                if contrib.feature_name not in feature_importance:
                    feature_importance[contrib.feature_name] = []
                feature_importance[contrib.feature_name].append(
                    contrib.absolute_contribution
                )

        # Average absolute contribution per feature
        global_importance = {}
        for feature, values in feature_importance.items():
            global_importance[feature] = sum(values) / len(values)

        # Normalize to sum to 1
        total = sum(global_importance.values())
        if total > 0:
            global_importance = {k: v / total for k, v in global_importance.items()}

        return dict(sorted(global_importance.items(), key=lambda x: x[1], reverse=True))

    def create_visualization(
        self,
        result: FeatureImportanceResult,
        top_n: int = 10,
        title: str = "Feature Importance",
    ) -> ImportanceVisualization:
        """Create visualization data for feature importance.

        Args:
            result: The analysis result to visualize.
            top_n: Number of top features to include.
            title: Title for the visualization.

        Returns:
            ImportanceVisualization with plotting data.
        """
        ranked = result.get_ranked_features(top_n)

        feature_names = [c.feature_name for c in ranked]
        values = [c.contribution_value for c in ranked]

        # Color based on direction
        colors = []
        for val in values:
            if val > 0:
                colors.append("#2ecc71")  # Green for positive
            elif val < 0:
                colors.append("#e74c3c")  # Red for negative
            else:
                colors.append("#95a5a6")  # Gray for neutral

        return ImportanceVisualization(
            feature_names=feature_names,
            values=values,
            colors=colors,
            title=title,
            x_label="SHAP Value (Contribution)",
            y_label="Feature",
        )

    def create_waterfall_data(
        self,
        result: FeatureImportanceResult,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """Create waterfall chart data for SHAP values.

        Args:
            result: The analysis result.
            top_n: Number of top features to include.

        Returns:
            Dictionary with waterfall chart data.
        """
        ranked = result.get_ranked_features(top_n)

        data = {
            "base": result.base_prediction,
            "steps": [],
            "final": result.final_prediction,
        }

        cumulative = result.base_prediction
        for contrib in ranked:
            cumulative += contrib.contribution_value
            data["steps"].append(
                {
                    "feature": contrib.feature_name,
                    "value": contrib.contribution_value,
                    "cumulative": cumulative,
                }
            )

        return data

    def _calculate_shap_values(
        self,
        features: dict[str, Any],
        prediction: float,
        base_value: float,
    ) -> list[FeatureContribution]:
        """Calculate SHAP-style values for features.

        This is a simplified approximation of SHAP values that:
        1. Uses feature weights as importance priors
        2. Scales by feature value deviation from neutral
        3. Accounts for direction relative to prediction
        """
        contributions = []
        prediction_delta = prediction - base_value

        for feature_name, feature_value in features.items():
            if not isinstance(feature_value, (int, float)):
                continue

            # Get feature weight
            weight = self.feature_weights.get(feature_name, 0.1)

            # Calculate contribution based on feature value
            contribution = self._calculate_single_contribution(
                feature_name, feature_value, weight, prediction_delta
            )

            contributions.append(
                FeatureContribution(
                    feature_name=feature_name,
                    contribution_value=contribution,
                    base_value=base_value,
                    feature_value=float(feature_value),
                )
            )

        return contributions

    def _calculate_single_contribution(
        self,
        feature_name: str,
        feature_value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate contribution for a single feature."""
        # Get feature-specific calculation
        if feature_name == "rsi":
            return self._rsi_contribution(feature_value, weight, prediction_delta)
        elif feature_name == "macd":
            return self._macd_contribution(feature_value, weight, prediction_delta)
        elif feature_name == "volume":
            return self._volume_contribution(feature_value, weight, prediction_delta)
        elif feature_name == "volatility":
            return self._volatility_contribution(
                feature_value, weight, prediction_delta
            )
        elif feature_name == "trend":
            return self._trend_contribution(feature_value, weight, prediction_delta)
        else:
            # Generic contribution based on normalized value
            return self._generic_contribution(feature_value, weight, prediction_delta)

    def _rsi_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate RSI contribution."""
        # RSI is bounded 0-100, neutral is 50
        deviation = (value - 50) / 50  # -1 to 1

        # Oversold (<30) pushes up, overbought (>70) pushes down
        if value < 30:
            # Strong positive contribution for buy signals
            contribution = weight * (1 + (30 - value) / 30)
        elif value > 70:
            # Strong negative contribution
            contribution = -weight * (1 + (value - 70) / 30)
        else:
            # Linear in neutral zone
            contribution = weight * deviation * 0.5

        # Scale by prediction direction
        if prediction_delta > 0:
            return contribution
        return -contribution

    def _macd_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate MACD contribution."""
        # MACD positive = bullish, negative = bearish
        # Normalize by typical range
        normalized = max(-1, min(1, value * 5))  # Assume typical range ±0.2

        contribution = weight * normalized

        # Scale by prediction direction
        if prediction_delta > 0:
            return contribution
        return -contribution

    def _volume_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate volume contribution."""
        # Volume relative to average (1.0 = average)
        # High volume confirms signals, low volume weakens them

        if value > 1.5:
            # High volume - strengthens the signal
            contribution = weight * 0.8
        elif value < 0.5:
            # Low volume - weakens confidence
            contribution = -weight * 0.5
        else:
            # Normal volume - moderate contribution
            contribution = weight * 0.3 * (value - 1)

        # Align with prediction direction
        return contribution if prediction_delta > 0 else contribution * 0.5

    def _volatility_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate volatility contribution."""
        # Higher volatility increases uncertainty (reduces confidence)
        # Assume value is normalized volatility (0-1)

        if value > 0.7:
            # High volatility - reduces confidence
            contribution = -weight * 0.6
        elif value < 0.3:
            # Low volatility - increases confidence
            contribution = weight * 0.4
        else:
            contribution = weight * (0.5 - value)

        return contribution

    def _trend_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate trend contribution."""
        # Trend: -1 (downtrend), 0 (sideways), 1 (uptrend)
        contribution = weight * value

        # Scale by prediction direction
        if prediction_delta > 0:
            return contribution
        return -contribution

    def _generic_contribution(
        self,
        value: float,
        weight: float,
        prediction_delta: float,
    ) -> float:
        """Calculate generic contribution for unknown features."""
        # Normalize value to -1 to 1 range (sigmoid-like)
        normalized = value / (1 + abs(value))

        contribution = weight * normalized * 0.5

        # Scale by prediction direction
        return contribution if prediction_delta > 0 else -contribution

    def _calculate_permutation_importance(
        self,
        features: dict[str, Any],
        prediction: float,
        base_value: float,
    ) -> list[FeatureContribution]:
        """Calculate permutation-based importance (simplified)."""
        # Without actual model access, use weight-based approximation
        return self._calculate_weighted_contributions(features, prediction, base_value)

    def _calculate_weighted_contributions(
        self,
        features: dict[str, Any],
        prediction: float,
        base_value: float,
    ) -> list[FeatureContribution]:
        """Calculate simple weighted contributions."""
        contributions = []
        prediction_delta = prediction - base_value

        # Calculate total weight of present features
        present_weights = sum(
            self.feature_weights.get(name, 0.1)
            for name in features.keys()
            if isinstance(features.get(name), (int, float))
        )

        for feature_name, feature_value in features.items():
            if not isinstance(feature_value, (int, float)):
                continue

            weight = self.feature_weights.get(feature_name, 0.1)
            # Proportional contribution
            contribution = (
                prediction_delta * (weight / present_weights)
                if present_weights > 0
                else 0
            )

            contributions.append(
                FeatureContribution(
                    feature_name=feature_name,
                    contribution_value=contribution,
                    base_value=base_value,
                    feature_value=float(feature_value),
                )
            )

        return contributions

    def _calculate_confidence(
        self,
        contributions: list[FeatureContribution],
    ) -> float:
        """Calculate confidence in the analysis."""
        if not contributions:
            return 0.0

        # Confidence based on:
        # 1. Number of features (more = more confident up to a point)
        # 2. Magnitude of contributions (larger = more confident)

        n_features = len(contributions)
        feature_confidence = min(1.0, n_features / 5)  # Max at 5 features

        avg_magnitude = sum(c.absolute_contribution for c in contributions) / n_features
        magnitude_confidence = min(1.0, avg_magnitude * 5)

        return (feature_confidence + magnitude_confidence) / 2


__all__ = [
    "ImportanceMethod",
    "FeatureContribution",
    "FeatureImportanceResult",
    "ImportanceVisualization",
    "FeatureImportanceAnalyzer",
]
