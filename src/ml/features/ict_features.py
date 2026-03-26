"""ICT Feature Engineering Pipeline.

This module provides feature extraction for ICT (Inner Circle Trader) signals
including Cumulative Volume Delta (CVD), Fair Value Gap (FVG), and Order Block
features for ML training data.

ST-ICT-028-A: ICT Feature Engineering Pipeline
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from src.market_analysis.cvd.cvd_calculator import CVDResult
    from src.market_analysis.fvg.fvg_detector import FVG
    from src.market_analysis.order_block.ob_detector import OBDetectionResult


logger = logging.getLogger(__name__)

# Feature names for ML training
FEATURE_CVD_SLOPE = "cvd_slope"
FEATURE_CVD_MOMENTUM = "cvd_momentum"
FEATURE_CVD_BULLISH_DIVERGENCE = "cvd_bullish_divergence"
FEATURE_CVD_BEARISH_DIVERGENCE = "cvd_bearish_divergence"
FEATURE_FVG_BULLISH_COUNT = "fvg_bullish_count"
FEATURE_FVG_BEARISH_COUNT = "fvg_bearish_count"
FEATURE_FVG_MITIGATED_RATIO = "fvg_mitigated_ratio"
FEATURE_FVG_50_CE_HIT_RATIO = "fvg_50ce_hit_ratio"
FEATURE_OB_BULLISH_COUNT = "ob_bullish_count"
FEATURE_OB_BEARISH_COUNT = "ob_bearish_count"
FEATURE_OB_MITIGATED_RATIO = "ob_mitigated_ratio"
FEATURE_COMBINED_ICT_SCORE = "combined_ict_score"
FEATURE_REGIME = "market_regime"


class MarketRegime(str, Enum):
    """Market regime classification."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    TRANSITIONAL = "transitional"


@dataclass
class ICTFeatures:
    """Container for extracted ICT features.

    Attributes:
        timestamp: Timestamp of the feature extraction
        token: Trading pair symbol
        timeframe: Timeframe of the analysis
        cvd_slope: Slope of CVD over recent period
        cvd_momentum: Momentum indicator from CVD
        cvd_bullish_divergence: Bullish divergence strength [0, 1]
        cvd_bearish_divergence: Bearish divergence strength [0, 1]
        fvg_bullish_count: Number of active bullish FVGs
        fvg_bearish_count: Number of active bearish FVGs
        fvg_mitigated_ratio: Ratio of mitigated FVGs [0, 1]
        fvg_50ce_hit_ratio: Ratio of FVGs with 50% CE hit [0, 1]
        ob_bullish_count: Number of active bullish order blocks
        ob_bearish_count: Number of active bearish order blocks
        ob_mitigated_ratio: Ratio of mitigated order blocks [0, 1]
        combined_ict_score: Combined ICT signal score [-1, 1]
        regime: Current market regime
        features_dict: Dictionary of all features for ML training
    """

    timestamp: datetime
    token: str
    timeframe: str
    cvd_slope: float = 0.0
    cvd_momentum: float = 0.0
    cvd_bullish_divergence: float = 0.0
    cvd_bearish_divergence: float = 0.0
    fvg_bullish_count: int = 0
    fvg_bearish_count: int = 0
    fvg_mitigated_ratio: float = 0.0
    fvg_50ce_hit_ratio: float = 0.0
    ob_bullish_count: int = 0
    ob_bearish_count: int = 0
    ob_mitigated_ratio: float = 0.0
    combined_ict_score: float = 0.0
    regime: MarketRegime = MarketRegime.NEUTRAL
    features_dict: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Build features dictionary for ML training."""
        self.features_dict = {
            FEATURE_CVD_SLOPE: self.cvd_slope,
            FEATURE_CVD_MOMENTUM: self.cvd_momentum,
            FEATURE_CVD_BULLISH_DIVERGENCE: self.cvd_bullish_divergence,
            FEATURE_CVD_BEARISH_DIVERGENCE: self.cvd_bearish_divergence,
            FEATURE_FVG_BULLISH_COUNT: self.fvg_bullish_count,
            FEATURE_FVG_BEARISH_COUNT: self.fvg_bearish_count,
            FEATURE_FVG_MITIGATED_RATIO: self.fvg_mitigated_ratio,
            FEATURE_FVG_50_CE_HIT_RATIO: self.fvg_50ce_hit_ratio,
            FEATURE_OB_BULLISH_COUNT: self.ob_bullish_count,
            FEATURE_OB_BEARISH_COUNT: self.ob_bearish_count,
            FEATURE_OB_MITIGATED_RATIO: self.ob_mitigated_ratio,
            FEATURE_COMBINED_ICT_SCORE: self.combined_ict_score,
            FEATURE_REGIME: self.regime.value,
        }

    def to_training_sample(self, label: int | None = None) -> dict[str, Any]:
        """Convert to ML training sample format.

        Args:
            label: Optional outcome label (1 for win, 0 for loss)

        Returns:
            Dictionary suitable for ML training
        """
        sample = {
            "timestamp": self.timestamp.isoformat(),
            "token": self.token,
            "timeframe": self.timeframe,
            **self.features_dict,
        }
        if label is not None:
            sample["outcome"] = label
        return sample

    @property
    def feature_names(self) -> list[str]:
        """Get list of feature names."""
        return list(self.features_dict.keys())

    @property
    def feature_values(self) -> list[float]:
        """Get list of feature values (numeric only)."""
        result = []
        for v in self.features_dict.values():
            if isinstance(v, (int, float, np.integer, np.floating)):
                result.append(float(v))
            elif isinstance(v, str) and v in [r.value for r in MarketRegime]:
                # Convert enum string to numeric encoding
                regime_map = {
                    MarketRegime.BULLISH.value: 1.0,
                    MarketRegime.BEARISH.value: -1.0,
                    MarketRegime.NEUTRAL.value: 0.0,
                    MarketRegime.TRANSITIONAL.value: 0.5,
                }
                result.append(regime_map.get(v, 0.0))
        return result


@dataclass
class ICTFeatureExtractorConfig:
    """Configuration for ICT feature extraction.

    Attributes:
        cvd_window_size: Window size for CVD slope calculation
        cvd_momentum_window: Window for CVD momentum
        divergence_threshold: Minimum threshold for divergence detection
        fvg_lookback_count: Number of FVGs to consider
        ob_lookback_count: Number of order blocks to consider
        score_weights: Weights for combined ICT score calculation
    """

    cvd_window_size: int = 20
    cvd_momentum_window: int = 10
    divergence_threshold: float = 0.05
    fvg_lookback_count: int = 5
    ob_lookback_count: int = 5
    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "cvd": 0.3,
            "fvg": 0.35,
            "ob": 0.35,
        }
    )


class ICTFeatureExtractor:
    """Extracts ICT features for ML training.

    Integrates with existing ICT signal detectors (CVD, FVG, Order Block)
    to produce ML-ready feature vectors.

    Example:
        >>> from src.ml.features.ict_features import ICTFeatureExtractor
        >>> extractor = ICTFeatureExtractor()
        >>> features = extractor.extract(
        ...     token="BTC/USDT",
        ...     timeframe="1h",
        ...     cvd_result=cvd_result,
        ...     fvgs=[fvg1, fvg2],
        ...     order_blocks=[ob1, ob2],
        ...     regime=MarketRegime.BULLISH,
        ... )
        >>> sample = features.to_training_sample()
    """

    def __init__(self, config: ICTFeatureExtractorConfig | None = None) -> None:
        """Initialize ICT feature extractor.

        Args:
            config: Optional configuration
        """
        self._config = config or ICTFeatureExtractorConfig()
        self._logger = logging.getLogger(__name__)

    @property
    def config(self) -> ICTFeatureExtractorConfig:
        """Get configuration."""
        return self._config

    def extract(
        self,
        token: str,
        timeframe: str,
        cvd_result: CVDResult | None = None,
        fvgs: list[FVG] | None = None,
        order_blocks: list[OBDetectionResult] | None = None,
        regime: MarketRegime = MarketRegime.NEUTRAL,
        current_price: float | None = None,
        timestamp: datetime | None = None,
    ) -> ICTFeatures:
        """Extract ICT features from signal data.

        Args:
            token: Trading pair symbol
            timeframe: Timeframe of analysis
            cvd_result: CVD calculation result
            fvgs: List of detected FVGs
            order_blocks: List of detected order blocks
            regime: Current market regime
            current_price: Current price for mitigation checks
            timestamp: Timestamp of extraction (default: now)

        Returns:
            ICTFeatures container with all extracted features
        """
        ts = timestamp or datetime.now(UTC)

        # Extract CVD features
        cvd_slope, cvd_momentum = self._extract_cvd_features(cvd_result)
        cvd_bullish, cvd_bearish = self._extract_cvd_divergence(
            cvd_result, current_price
        )

        # Extract FVG features
        (
            fvg_bullish_count,
            fvg_bearish_count,
            fvg_mitigated_ratio,
            fvg_50ce_hit_ratio,
        ) = self._extract_fvg_features(fvgs, current_price)

        # Extract Order Block features
        (
            ob_bullish_count,
            ob_bearish_count,
            ob_mitigated_ratio,
        ) = self._extract_ob_features(order_blocks, current_price)

        # Calculate combined ICT score
        combined_score = self._calculate_combined_score(
            cvd_slope=cvd_slope,
            cvd_momentum=cvd_momentum,
            fvg_bullish=fvg_bullish_count,
            fvg_bearish=fvg_bearish_count,
            ob_bullish=ob_bullish_count,
            ob_bearish=ob_bearish_count,
            regime=regime,
        )

        features = ICTFeatures(
            timestamp=ts,
            token=token,
            timeframe=timeframe,
            cvd_slope=cvd_slope,
            cvd_momentum=cvd_momentum,
            cvd_bullish_divergence=cvd_bullish,
            cvd_bearish_divergence=cvd_bearish,
            fvg_bullish_count=fvg_bullish_count,
            fvg_bearish_count=fvg_bearish_count,
            fvg_mitigated_ratio=fvg_mitigated_ratio,
            fvg_50ce_hit_ratio=fvg_50ce_hit_ratio,
            ob_bullish_count=ob_bullish_count,
            ob_bearish_count=ob_bearish_count,
            ob_mitigated_ratio=ob_mitigated_ratio,
            combined_ict_score=combined_score,
            regime=regime,
        )

        self._logger.debug(
            f"Extracted ICT features for {token} {timeframe}: "
            f"score={combined_score:.3f}, regime={regime.value}"
        )

        return features

    def _extract_cvd_features(
        self, cvd_result: CVDResult | None
    ) -> tuple[float, float]:
        """Extract slope and momentum from CVD.

        Args:
            cvd_result: CVD calculation result

        Returns:
            Tuple of (slope, momentum)
        """
        if (
            cvd_result is None
            or len(cvd_result.cvd_values) < self._config.cvd_window_size
        ):
            return 0.0, 0.0

        # Use full array for all calculations
        cvd_array = np.array(cvd_result.cvd_values)

        # Calculate slope using last window_size values
        window_vals = cvd_array[-self._config.cvd_window_size :]
        x = np.arange(len(window_vals))
        slope = float(np.polyfit(x, window_vals, 1)[0])

        # Normalize slope by average CVD magnitude
        avg_cvd = float(np.mean(np.abs(window_vals)))
        if avg_cvd > 0:
            slope = slope / avg_cvd

        # Calculate momentum using the full array
        momentum_window = min(
            self._config.cvd_momentum_window, self._config.cvd_window_size
        )
        if momentum_window >= 2 and len(cvd_array) >= momentum_window * 2:
            recent = float(np.mean(cvd_array[-momentum_window:]))
            previous = float(
                np.mean(cvd_array[-momentum_window * 2 : -momentum_window])
            )
            if abs(previous) > 1e-10:
                momentum = float((recent - previous) / abs(previous))
            else:
                momentum = 0.0
        else:
            momentum = 0.0

        return slope, momentum

    def _extract_cvd_divergence(
        self, cvd_result: CVDResult | None, current_price: float | None
    ) -> tuple[float, float]:
        """Extract bullish and bearish divergence from CVD.

        Args:
            cvd_result: CVD calculation result
            current_price: Current price for comparison

        Returns:
            Tuple of (bullish_divergence, bearish_divergence) normalized [0, 1]
        """
        if cvd_result is None or current_price is None:
            return 0.0, 0.0

        if len(cvd_result.cvd_values) < 3 or len(cvd_result.timestamps) < 3:
            return 0.0, 0.0

        cvd_values = np.array(cvd_result.cvd_values)
        threshold = self._config.divergence_threshold

        # Detect divergences
        bullish_strength = 0.0
        bearish_strength = 0.0

        for i in range(1, len(cvd_values) - 1):
            cvd_delta = cvd_values[i] - cvd_values[i - 1]
            cvd_delta_next = cvd_values[i + 1] - cvd_values[i]

            # Classify based on direction
            if cvd_delta > 0 and cvd_delta_next < 0:
                # CVD peaked, check if bearish divergence
                bearish_strength = max(
                    bearish_strength, min(abs(cvd_delta) / threshold, 1.0)
                )
            elif cvd_delta < 0 and cvd_delta_next > 0:
                # CVD bottomed, check if bullish divergence
                bullish_strength = max(
                    bullish_strength, min(abs(cvd_delta) / threshold, 1.0)
                )

        return bullish_strength, bearish_strength

    def _extract_fvg_features(
        self, fvgs: list[FVG] | None, current_price: float | None
    ) -> tuple[int, int, float, float]:
        """Extract features from FVG list.

        Args:
            fvgs: List of FVGs
            current_price: Current price for mitigation checks

        Returns:
            Tuple of (bullish_count, bearish_count, mitigated_ratio, 50ce_hit_ratio)
        """
        if fvgs is None or len(fvgs) == 0:
            return 0, 0, 0.0, 0.0

        # Get recent FVGs based on lookback count
        recent_fvgs = fvgs[-self._config.fvg_lookback_count :]

        bullish_count = sum(
            1 for fvg in recent_fvgs if fvg.direction.value == "bullish"
        )
        bearish_count = sum(
            1 for fvg in recent_fvgs if fvg.direction.value == "bearish"
        )

        # Calculate mitigation ratio
        mitigated_count = sum(
            1 for fvg in recent_fvgs if fvg.mitigation.value != "none"
        )
        mitigated_ratio = mitigated_count / len(recent_fvgs) if recent_fvgs else 0.0

        # Calculate 50% CE hit ratio
        ce50_hit_count = sum(1 for fvg in recent_fvgs if fvg.ce50_reached)
        ce50_hit_ratio = ce50_hit_count / len(recent_fvgs) if recent_fvgs else 0.0

        return bullish_count, bearish_count, mitigated_ratio, ce50_hit_ratio

    def _extract_ob_features(
        self, order_blocks: list[OBDetectionResult] | None, current_price: float | None
    ) -> tuple[int, int, float]:
        """Extract features from Order Block list.

        Args:
            order_blocks: List of order blocks
            current_price: Current price for mitigation checks

        Returns:
            Tuple of (bullish_count, bearish_count, mitigated_ratio)
        """
        if order_blocks is None or len(order_blocks) == 0:
            return 0, 0, 0.0

        # Get recent order blocks based on lookback count
        recent_obs = order_blocks[-self._config.ob_lookback_count :]

        bullish_count = sum(
            1 for ob in recent_obs if getattr(ob, "direction", None) == "bullish"
        )
        bearish_count = sum(
            1 for ob in recent_obs if getattr(ob, "direction", None) == "bearish"
        )

        # Calculate mitigation ratio
        mitigated_count = sum(
            1
            for ob in recent_obs
            if getattr(ob, "mitigated", False) or getattr(ob, "is_mitigated", False)
        )
        mitigated_ratio = mitigated_count / len(recent_obs) if recent_obs else 0.0

        return bullish_count, bearish_count, mitigated_ratio

    def _calculate_combined_score(
        self,
        cvd_slope: float,
        cvd_momentum: float,
        fvg_bullish: int,
        fvg_bearish: int,
        ob_bullish: int,
        ob_bearish: int,
        regime: MarketRegime,
    ) -> float:
        """Calculate combined ICT score from individual components.

        Args:
            cvd_slope: CVD slope
            cvd_momentum: CVD momentum
            fvg_bullish: Number of bullish FVGs
            fvg_bearish: Number of bearish FVGs
            ob_bullish: Number of bullish order blocks
            ob_bearish: Number of bearish order blocks
            regime: Current market regime

        Returns:
            Combined ICT score normalized [-1, 1]
        """
        weights = self._config.score_weights

        # CVD component
        cvd_component = np.tanh(cvd_slope + cvd_momentum) * weights["cvd"]

        # FVG component (net direction)
        fvg_net = fvg_bullish - fvg_bearish
        fvg_normalized = np.tanh(fvg_net * 0.5) * weights["fvg"]

        # Order Block component (net direction)
        ob_net = ob_bullish - ob_bearish
        ob_normalized = np.tanh(ob_net * 0.5) * weights["ob"]

        # Regime adjustment
        regime_multiplier = 1.0
        if regime == MarketRegime.BULLISH:
            regime_multiplier = 1.0
        elif regime == MarketRegime.BEARISH:
            regime_multiplier = -1.0
        elif regime == MarketRegime.NEUTRAL:
            regime_multiplier = 0.5
        else:  # TRANSITIONAL
            regime_multiplier = 0.0

        # Calculate final score
        raw_score = cvd_component + fvg_normalized + ob_normalized
        combined_score = raw_score * regime_multiplier

        # Clamp to [-1, 1]
        return float(np.clip(combined_score, -1.0, 1.0))

    def extract_batch(
        self,
        token: str,
        timeframe: str,
        samples: list[dict[str, Any]],
    ) -> list[ICTFeatures]:
        """Extract features from a batch of signal data.

        Args:
            token: Trading pair symbol
            timeframe: Timeframe of analysis
            samples: List of signal data dictionaries

        Returns:
            List of ICTFeatures
        """
        features_list = []

        for sample in samples:
            features = self.extract(
                token=token,
                timeframe=timeframe,
                cvd_result=sample.get("cvd_result"),
                fvgs=sample.get("fvgs"),
                order_blocks=sample.get("order_blocks"),
                regime=sample.get("regime", MarketRegime.NEUTRAL),
                current_price=sample.get("current_price"),
                timestamp=sample.get("timestamp"),
            )
            features_list.append(features)

        return features_list


def normalize_ict_features(
    features: ICTFeatures,
    normalization_stats: dict[str, dict[str, float]] | None = None,
) -> ICTFeatures:
    """Normalize ICT features using provided statistics.

    Args:
        features: ICTFeatures to normalize
        normalization_stats: Dictionary with mean/std per feature

    Returns:
        Normalized ICTFeatures
    """
    if normalization_stats is None:
        return features

    normalized_dict = features.features_dict.copy()

    for key, value in normalized_dict.items():
        if key in normalization_stats and isinstance(value, (int, float)):
            stats = normalization_stats[key]
            mean = stats.get("mean", 0.0)
            std = stats.get("std", 1.0)
            if std > 0:
                normalized_dict[key] = (value - mean) / std

    # Create new ICTFeatures with normalized values
    normalized = ICTFeatures(
        timestamp=features.timestamp,
        token=features.token,
        timeframe=features.timeframe,
        cvd_slope=normalized_dict.get(FEATURE_CVD_SLOPE, 0.0),
        cvd_momentum=normalized_dict.get(FEATURE_CVD_MOMENTUM, 0.0),
        cvd_bullish_divergence=normalized_dict.get(FEATURE_CVD_BULLISH_DIVERGENCE, 0.0),
        cvd_bearish_divergence=normalized_dict.get(FEATURE_CVD_BEARISH_DIVERGENCE, 0.0),
        fvg_bullish_count=features.fvg_bullish_count,
        fvg_bearish_count=features.fvg_bearish_count,
        fvg_mitigated_ratio=normalized_dict.get(FEATURE_FVG_MITIGATED_RATIO, 0.0),
        fvg_50ce_hit_ratio=normalized_dict.get(FEATURE_FVG_50_CE_HIT_RATIO, 0.0),
        ob_bullish_count=features.ob_bullish_count,
        ob_bearish_count=features.ob_bearish_count,
        ob_mitigated_ratio=normalized_dict.get(FEATURE_OB_MITIGATED_RATIO, 0.0),
        combined_ict_score=normalized_dict.get(FEATURE_COMBINED_ICT_SCORE, 0.0),
        regime=features.regime,
    )

    return normalized
