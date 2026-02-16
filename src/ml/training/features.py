"""Feature definitions for training data.

Defines feature extraction specifications, feature groups, and
validation rules for ML training data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeatureType(Enum):
    """Types of features for training data."""

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BINARY = "binary"
    ORDINAL = "ordinal"


class TrendState(Enum):
    """Trend state enumeration for market analysis."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeatureSpec:
    """Feature specification for validation and documentation.

    Attributes:
        name: Feature name
        feature_type: Type of feature
        description: Human-readable description
        min_value: Minimum allowed value (for numeric features)
        max_value: Maximum allowed value (for numeric features)
        allowed_values: List of allowed values (for categorical features)
        nullable: Whether the feature can be null
        default: Default value if null
    """

    name: str
    feature_type: FeatureType
    description: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None
    nullable: bool = False
    default: Any = None


# Feature specifications for training data
# All features except token and timeframe are nullable=True to allow partial data
FEATURE_SPECS: dict[str, FeatureSpec] = {
    # Metadata features (required)
    "token": FeatureSpec(
        name="token",
        feature_type=FeatureType.CATEGORICAL,
        description="Trading pair token (e.g., BTC, ETH)",
        allowed_values=None,  # Dynamic based on available tokens
        nullable=False,
    ),
    "timeframe": FeatureSpec(
        name="timeframe",
        feature_type=FeatureType.CATEGORICAL,
        description="Chart timeframe (e.g., 1h, 4h, 1d)",
        allowed_values=[
            "1m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "3d",
            "1w",
        ],
        nullable=False,
    ),
    # Technical indicator features (optional)
    "rsi": FeatureSpec(
        name="rsi",
        feature_type=FeatureType.NUMERIC,
        description="Relative Strength Index",
        min_value=0.0,
        max_value=100.0,
        nullable=True,
    ),
    "macd": FeatureSpec(
        name="macd",
        feature_type=FeatureType.NUMERIC,
        description="MACD line value",
        min_value=None,
        max_value=None,
        nullable=True,
    ),
    "macd_signal": FeatureSpec(
        name="macd_signal",
        feature_type=FeatureType.NUMERIC,
        description="MACD signal line value",
        min_value=None,
        max_value=None,
        nullable=True,
    ),
    "macd_histogram": FeatureSpec(
        name="macd_histogram",
        feature_type=FeatureType.NUMERIC,
        description="MACD histogram value",
        min_value=None,
        max_value=None,
        nullable=True,
    ),
    "bb_upper": FeatureSpec(
        name="bb_upper",
        feature_type=FeatureType.NUMERIC,
        description="Bollinger Bands upper band",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    "bb_lower": FeatureSpec(
        name="bb_lower",
        feature_type=FeatureType.NUMERIC,
        description="Bollinger Bands lower band",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    "bb_width": FeatureSpec(
        name="bb_width",
        feature_type=FeatureType.NUMERIC,
        description="Bollinger Bands width percentage",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    "atr": FeatureSpec(
        name="atr",
        feature_type=FeatureType.NUMERIC,
        description="Average True Range",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    "volume_sma": FeatureSpec(
        name="volume_sma",
        feature_type=FeatureType.NUMERIC,
        description="Volume SMA ratio",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    # Trend and confluence features (optional)
    "trend_state": FeatureSpec(
        name="trend_state",
        feature_type=FeatureType.CATEGORICAL,
        description="Overall trend state",
        allowed_values=["bullish", "bearish", "neutral", "unknown"],
        nullable=True,
    ),
    "confluence_score": FeatureSpec(
        name="confluence_score",
        feature_type=FeatureType.NUMERIC,
        description="Confluence score from multiple indicators",
        min_value=0.0,
        max_value=100.0,
        nullable=True,
    ),
    "confidence": FeatureSpec(
        name="confidence",
        feature_type=FeatureType.NUMERIC,
        description="Signal confidence (0.0-1.0)",
        min_value=0.0,
        max_value=1.0,
        nullable=True,
    ),
    "direction": FeatureSpec(
        name="direction",
        feature_type=FeatureType.CATEGORICAL,
        description="Signal direction",
        allowed_values=["long", "short", "neutral"],
        nullable=True,
    ),
    # Price features (optional)
    "entry_price": FeatureSpec(
        name="entry_price",
        feature_type=FeatureType.NUMERIC,
        description="Price at signal generation",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
    "price_change_24h": FeatureSpec(
        name="price_change_24h",
        feature_type=FeatureType.NUMERIC,
        description="24-hour price change percentage",
        min_value=None,
        max_value=None,
        nullable=True,
    ),
    "volatility": FeatureSpec(
        name="volatility",
        feature_type=FeatureType.NUMERIC,
        description="Price volatility measure",
        min_value=0.0,
        max_value=None,
        nullable=True,
    ),
}


# Feature groups for organized access
FEATURE_GROUPS: dict[str, list[str]] = {
    "metadata": ["token", "timeframe"],
    "indicators": [
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "atr",
        "volume_sma",
    ],
    "trend": ["trend_state", "confluence_score", "confidence", "direction"],
    "price": ["entry_price", "price_change_24h", "volatility"],
    "all_features": list(FEATURE_SPECS.keys()),
}


class FeatureValidator:
    """Validates feature values against specifications."""

    def __init__(self, specs: dict[str, FeatureSpec] | None = None) -> None:
        """Initialize validator.

        Args:
            specs: Feature specifications (defaults to FEATURE_SPECS)
        """
        self.specs = specs or FEATURE_SPECS

    def validate_feature(self, name: str, value: Any) -> tuple[bool, str]:
        """Validate a single feature value.

        Args:
            name: Feature name
            value: Feature value

        Returns:
            Tuple of (is_valid, error_message)
        """
        if name not in self.specs:
            return False, f"Unknown feature: {name}"

        spec = self.specs[name]

        # Check nullability
        if value is None:
            if spec.nullable:
                return True, ""
            return False, f"Feature {name} cannot be null"

        # Validate by type
        if spec.feature_type == FeatureType.NUMERIC:
            return self._validate_numeric(spec, value)
        elif spec.feature_type == FeatureType.CATEGORICAL:
            return self._validate_categorical(spec, value)
        elif spec.feature_type == FeatureType.BINARY:
            return self._validate_binary(spec, value)
        elif spec.feature_type == FeatureType.ORDINAL:
            return self._validate_ordinal(spec, value)

        return True, ""

    def _validate_numeric(self, spec: FeatureSpec, value: Any) -> tuple[bool, str]:
        """Validate numeric feature."""
        if not isinstance(value, (int, float)):
            return False, f"Feature {spec.name} must be numeric"

        if spec.min_value is not None and value < spec.min_value:
            return (
                False,
                f"Feature {spec.name} below minimum: {value} < {spec.min_value}",
            )

        if spec.max_value is not None and value > spec.max_value:
            return (
                False,
                f"Feature {spec.name} above maximum: {value} > {spec.max_value}",
            )

        return True, ""

    def _validate_categorical(self, spec: FeatureSpec, value: Any) -> tuple[bool, str]:
        """Validate categorical feature."""
        if not isinstance(value, str):
            return False, f"Feature {spec.name} must be string"

        if spec.allowed_values and value not in spec.allowed_values:
            return (
                False,
                f"Feature {spec.name} has invalid value: {value}",
            )

        return True, ""

    def _validate_binary(self, spec: FeatureSpec, value: Any) -> tuple[bool, str]:
        """Validate binary feature."""
        if not isinstance(value, bool):
            return False, f"Feature {spec.name} must be boolean"
        return True, ""

    def _validate_ordinal(self, spec: FeatureSpec, value: Any) -> tuple[bool, str]:
        """Validate ordinal feature."""
        if spec.allowed_values and value not in spec.allowed_values:
            return (
                False,
                f"Feature {spec.name} has invalid ordinal value: {value}",
            )
        return True, ""

    def validate_features(self, features: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate multiple features.

        Args:
            features: Dictionary of feature names to values

        Returns:
            Tuple of (all_valid, list_of_errors)
        """
        errors = []
        for name, value in features.items():
            is_valid, error = self.validate_feature(name, value)
            if not is_valid:
                errors.append(error)

        return len(errors) == 0, errors

    def get_feature_group(self, group_name: str) -> list[FeatureSpec]:
        """Get feature specifications for a group.

        Args:
            group_name: Name of the feature group

        Returns:
            List of feature specifications
        """
        if group_name not in FEATURE_GROUPS:
            return []

        return [
            self.specs[name]
            for name in FEATURE_GROUPS[group_name]
            if name in self.specs
        ]
