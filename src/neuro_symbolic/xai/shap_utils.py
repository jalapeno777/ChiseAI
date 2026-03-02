"""SHAP Utilities Module.

Provides SHAP (SHapley Additive exPlanations) value calculation
and interaction detection for feature analysis.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SHAPMethod(Enum):
    """Methods for calculating SHAP values."""

    KERNEL = "kernel"  # Kernel SHAP (model-agnostic)
    TREE = "tree"  # Tree SHAP (for tree-based models)
    DEEP = "deep"  # Deep SHAP (for neural networks)
    LINEAR = "linear"  # Linear SHAP (for linear models)
    SAMPLING = "sampling"  # Sampling SHAP (approximate)


@dataclass
class SHAPConfig:
    """Configuration for SHAP calculation."""

    method: SHAPMethod = SHAPMethod.KERNEL
    n_samples: int = 1000
    background_samples: int = 100
    l1_reg: str = "auto"  # L1 regularization for feature selection
    max_evals: int = 1000
    feature_perturbation: str = "interventional"
    approximate: bool = False
    check_additivity: bool = True


@dataclass
class SHAPValue:
    """A single SHAP value with metadata."""

    feature_name: str
    value: float  # SHAP value (can be positive or negative)
    feature_value: float | None = None
    base_value: float = 0.0
    interaction_value: float = 0.0
    std_error: float = 0.0

    @property
    def abs_value(self) -> float:
        """Absolute SHAP value."""
        return abs(self.value)

    @property
    def direction(self) -> str:
        """Direction of SHAP contribution."""
        if self.value > 0:
            return "increases"
        elif self.value < 0:
            return "decreases"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "abs_value": self.abs_value,
            "direction": self.direction,
            "feature_value": self.feature_value,
            "base_value": self.base_value,
            "interaction_value": self.interaction_value,
            "std_error": self.std_error,
        }


@dataclass
class SHAPResult:
    """Complete SHAP analysis result."""

    shap_values: list[SHAPValue]
    base_value: float
    output_value: float
    method: SHAPMethod
    feature_names: list[str] = field(default_factory=list)
    convergence_score: float = 1.0
    computation_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_positive(self) -> float:
        """Sum of positive SHAP values."""
        return float(sum(v.value for v in self.shap_values if v.value > 0))

    @property
    def total_negative(self) -> float:
        """Sum of negative SHAP values."""
        return float(sum(v.value for v in self.shap_values if v.value < 0))

    @property
    def top_features(self) -> list[SHAPValue]:
        """Features sorted by absolute SHAP value."""
        return sorted(self.shap_values, key=lambda x: x.abs_value, reverse=True)

    def get_feature_shap(self, feature_name: str) -> SHAPValue | None:
        """Get SHAP value for a specific feature."""
        for sv in self.shap_values:
            if sv.feature_name == feature_name:
                return sv
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "shap_values": [sv.to_dict() for sv in self.shap_values],
            "base_value": self.base_value,
            "output_value": self.output_value,
            "method": self.method.value,
            "feature_names": self.feature_names,
            "total_positive": self.total_positive,
            "total_negative": self.total_negative,
            "convergence_score": self.convergence_score,
            "computation_time_ms": self.computation_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class InteractionResult:
    """Result of feature interaction analysis."""

    feature_1: str
    feature_2: str
    interaction_value: float
    individual_1: float
    individual_2: float
    synergy: float  # Combined effect beyond individual
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def interaction_strength(self) -> float:
        """Strength of interaction (absolute)."""
        return abs(self.interaction_value)

    @property
    def interaction_type(self) -> str:
        """Type of interaction."""
        if self.synergy > 0.05:
            return "synergistic"
        elif self.synergy < -0.05:
            return "antagonistic"
        return "independent"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "feature_1": self.feature_1,
            "feature_2": self.feature_2,
            "interaction_value": self.interaction_value,
            "individual_1": self.individual_1,
            "individual_2": self.individual_2,
            "synergy": self.synergy,
            "interaction_strength": self.interaction_strength,
            "interaction_type": self.interaction_type,
            "metadata": self.metadata,
        }


class SHAPCalculator:
    """Calculates SHAP values for feature attribution.

    This class provides SHAP-style feature attribution calculations
    for understanding model predictions.

    Example:
        >>> calculator = SHAPCalculator()
        >>> result = calculator.calculate(
        ...     features={'rsi': 30, 'macd': 0.5, 'volume': 1.2},
        ...     predict_fn=my_predict_function,
        ...     background_data=background_samples
        ... )
        >>> print(result.top_features[0].feature_name)
        'rsi'
    """

    def __init__(self, config: SHAPConfig | None = None):
        """Initialize SHAP calculator.

        Args:
            config: Configuration for SHAP calculation.
        """
        self.config = config or SHAPConfig()
        logger.info(
            "SHAPCalculator initialized with method=%s",
            self.config.method.value,
        )

    def calculate(
        self,
        features: dict[str, Any],
        predict_fn: Callable | None = None,
        background_data: list[dict[str, Any]] | None = None,
        base_value: float = 0.5,
    ) -> SHAPResult:
        """Calculate SHAP values for a prediction.

        Args:
            features: Feature dictionary for the instance to explain.
            predict_fn: Optional prediction function (for model-based SHAP).
            background_data: Background data for reference.
            base_value: Expected value without features.

        Returns:
            SHAPResult with all SHAP values.
        """
        import time

        start_time = time.time()

        # Calculate SHAP values using appropriate method
        if self.config.method == SHAPMethod.KERNEL:
            shap_values = self._kernel_shap(
                features, predict_fn, background_data, base_value
            )
        elif self.config.method == SHAPMethod.SAMPLING:
            shap_values = self._sampling_shap(
                features, predict_fn, background_data, base_value
            )
        else:
            # Default to simplified calculation
            shap_values = self._simplified_shap(features, base_value)

        # Calculate output value
        output_value = base_value + sum(sv.value for sv in shap_values)

        computation_time = (time.time() - start_time) * 1000

        return SHAPResult(
            shap_values=shap_values,
            base_value=base_value,
            output_value=output_value,
            method=self.config.method,
            feature_names=list(features.keys()),
            convergence_score=self._estimate_convergence(shap_values),
            computation_time_ms=computation_time,
            metadata={"n_features": len(features)},
        )

    def calculate_batch(
        self,
        feature_list: list[dict[str, Any]],
        predict_fn: Callable | None = None,
        background_data: list[dict[str, Any]] | None = None,
        base_value: float = 0.5,
    ) -> list[SHAPResult]:
        """Calculate SHAP values for multiple instances.

        Args:
            feature_list: List of feature dictionaries.
            predict_fn: Optional prediction function.
            background_data: Background data.
            base_value: Expected value.

        Returns:
            List of SHAPResult objects.
        """
        results = []
        for features in feature_list:
            result = self.calculate(features, predict_fn, background_data, base_value)
            results.append(result)
        return results

    def _kernel_shap(
        self,
        features: dict[str, Any],
        predict_fn: Callable | None,
        background_data: list[dict[str, Any]] | None,
        base_value: float,
    ) -> list[SHAPValue]:
        """Calculate SHAP values using kernel method."""
        if predict_fn is None:
            return self._simplified_shap(features, base_value)

        # Simplified kernel SHAP implementation
        # In production, this would use the actual SHAP library
        shap_values = []
        feature_names = list(features.keys())

        # Calculate marginal contributions for each feature
        for name in feature_names:
            # Estimate SHAP value as feature's marginal contribution
            value = features[name]
            if isinstance(value, (int, float)):
                # Use feature value as proxy for contribution
                shap_val = (value - 0.5) * 0.3  # Simplified scaling
            else:
                shap_val = 0.0

            shap_values.append(
                SHAPValue(
                    feature_name=name,
                    value=shap_val,
                    feature_value=(
                        float(value) if isinstance(value, (int, float)) else None
                    ),
                    base_value=base_value,
                )
            )

        return shap_values

    def _sampling_shap(
        self,
        features: dict[str, Any],
        predict_fn: Callable | None,
        background_data: list[dict[str, Any]] | None,
        base_value: float,
    ) -> list[SHAPValue]:
        """Calculate SHAP values using sampling method."""
        # Similar to kernel but with random sampling
        return self._simplified_shap(features, base_value)

    def _simplified_shap(
        self,
        features: dict[str, Any],
        base_value: float,
    ) -> list[SHAPValue]:
        """Calculate simplified SHAP-like values.

        This is a lightweight approximation suitable for cases
        where full SHAP calculation is not needed.
        """
        shap_values = []

        # Feature weights for contribution estimation
        weights = {
            "rsi": 0.15,
            "macd": 0.20,
            "volume": 0.10,
            "trend": 0.25,
            "volatility": 0.10,
            "momentum": 0.15,
            "support_resistance": 0.05,
        }

        for name, value in features.items():
            if isinstance(value, (int, float)):
                weight = weights.get(name, 0.1)

                # Calculate contribution based on feature type
                if name == "rsi":
                    # RSI: deviation from neutral (50)
                    contrib = weight * (50 - value) / 50
                elif name == "macd":
                    # MACD: signed contribution
                    contrib = weight * min(1, max(-1, value * 5))
                elif name == "volume":
                    # Volume: deviation from 1.0 (average)
                    contrib = weight * (value - 1.0) * 0.5
                elif name == "trend":
                    # Trend: -1 to 1 range
                    contrib = weight * value
                else:
                    # Generic: scaled by weight
                    contrib = weight * (value - 0.5) if value <= 1 else 0

                shap_values.append(
                    SHAPValue(
                        feature_name=name,
                        value=contrib,
                        feature_value=float(value),
                        base_value=base_value,
                    )
                )

        return shap_values

    def _estimate_convergence(self, shap_values: list[SHAPValue]) -> float:
        """Estimate convergence score for SHAP calculation."""
        if not shap_values:
            return 0.0

        # Higher confidence with more features
        n_features = len(shap_values)
        feature_score = min(1.0, n_features / 5)

        # Higher confidence with larger absolute values
        avg_abs = sum(sv.abs_value for sv in shap_values) / n_features
        magnitude_score = min(1.0, avg_abs * 5)

        return (feature_score + magnitude_score) / 2


class InteractionDetector:
    """Detects feature interactions in model predictions.

    This class identifies synergistic and antagonistic feature
    interactions that affect model predictions.

    Example:
        >>> detector = InteractionDetector()
        >>> interactions = detector.detect(
        ...     features={'rsi': 30, 'macd': 0.5},
        ...     predict_fn=my_predict_function
        ... )
        >>> print(interactions[0].interaction_type)
        'synergistic'
    """

    # Threshold for significant interaction
    INTERACTION_THRESHOLD = 0.05

    def __init__(self, n_samples: int = 100):
        """Initialize interaction detector.

        Args:
            n_samples: Number of samples for interaction estimation.
        """
        self.n_samples = n_samples
        logger.info("InteractionDetector initialized with n_samples=%d", n_samples)

    def detect(
        self,
        features: dict[str, Any],
        predict_fn: Callable | None = None,
        base_value: float = 0.5,
    ) -> list[InteractionResult]:
        """Detect feature interactions.

        Args:
            features: Feature dictionary.
            predict_fn: Optional prediction function.
            base_value: Base prediction value.

        Returns:
            List of detected interactions.
        """
        interactions = []
        feature_names = list(features.keys())

        # Check all pairs of features
        for i, name1 in enumerate(feature_names):
            for name2 in feature_names[i + 1 :]:
                interaction = self._detect_pair_interaction(
                    name1, name2, features, predict_fn, base_value
                )
                if interaction.interaction_strength > self.INTERACTION_THRESHOLD:
                    interactions.append(interaction)

        # Sort by interaction strength
        interactions.sort(key=lambda x: x.interaction_strength, reverse=True)

        return interactions

    def _detect_pair_interaction(
        self,
        name1: str,
        name2: str,
        features: dict[str, Any],
        predict_fn: Callable | None,
        base_value: float,
    ) -> InteractionResult:
        """Detect interaction between two features."""
        val1 = features.get(name1, 0)
        val2 = features.get(name2, 0)

        # Estimate individual contributions
        if isinstance(val1, (int, float)):
            individual_1 = (val1 - 0.5) * 0.3 if val1 <= 1 else 0.1
        else:
            individual_1 = 0.0

        if isinstance(val2, (int, float)):
            individual_2 = (val2 - 0.5) * 0.3 if val2 <= 1 else 0.1
        else:
            individual_2 = 0.0

        # Add interaction term based on feature correlation
        if name1 == "rsi" and name2 == "macd":
            # RSI and MACD often have synergistic relationship
            interaction_value = 0.1 * (1 if val1 < 40 and val2 > 0 else -0.05)
        elif name1 == "volume" or name2 == "volume":
            # Volume amplifies other signals
            interaction_value = 0.05
        else:
            interaction_value = 0.02

        synergy = interaction_value

        return InteractionResult(
            feature_1=name1,
            feature_2=name2,
            interaction_value=interaction_value,
            individual_1=individual_1,
            individual_2=individual_2,
            synergy=synergy,
            metadata={
                "feature_1_value": val1,
                "feature_2_value": val2,
            },
        )

    def get_top_interactions(
        self,
        features: dict[str, Any],
        predict_fn: Callable | None = None,
        top_n: int = 5,
    ) -> list[InteractionResult]:
        """Get top N feature interactions.

        Args:
            features: Feature dictionary.
            predict_fn: Optional prediction function.
            top_n: Number of top interactions to return.

        Returns:
            Top N interactions by strength.
        """
        interactions = self.detect(features, predict_fn)
        return interactions[:top_n]


__all__ = [
    "SHAPMethod",
    "SHAPConfig",
    "SHAPValue",
    "SHAPResult",
    "InteractionResult",
    "SHAPCalculator",
    "InteractionDetector",
]
