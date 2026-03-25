"""Unified Market Regime Classification Module.

This module provides a unified MarketRegimeClassifier that integrates:
- Markov chain is_trending logic (from TrendInferenceEngine)
- VolatilityRegime detection (from ATR-based volatility analysis)
- ADX indicator for trend strength

The classifier outputs one of four unified regime types:
- TRENDING: Market is in a clear trend (up or down)
- RANGING: Market is oscillating within a bounded range
- VOLATILE: Market has high volatility with no clear direction
- UNKNOWN: Insufficient data for classification

Usage:
    from market_analysis.regime import MarketRegimeClassifier, UnifiedRegime

    classifier = MarketRegimeClassifier()
    regime = classifier.classify(ohlcv_data)
    print(regime.regime)  # UnifiedRegime.TRENDING, RANGING, VOLATILE, or UNKNOWN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


class UnifiedRegime(Enum):
    """Unified market regime types.

    Four mutually exclusive regimes that cover all market conditions:
    - TRENDING: Clear directional movement (ADX > 25, aligned with Markov state)
    - RANGING: Bounded oscillation with no clear direction (ADX < 20)
    - VOLATILE: High volatility with conflicting signals (high ATR, uncertain)
    - UNKNOWN: Insufficient data for classification
    """

    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"

    @property
    def is_trending(self) -> bool:
        """Check if regime represents a trending market."""
        return self == UnifiedRegime.TRENDING

    @property
    def is_ranging(self) -> bool:
        """Check if regime represents a ranging market."""
        return self == UnifiedRegime.RANGING

    @property
    def is_volatile(self) -> bool:
        """Check if regime represents a volatile market."""
        return self == UnifiedRegime.VOLATILE


class VolatilityRegime(Enum):
    """Volatility regime classification."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RegimeClassification:
    """Complete regime classification result.

    Attributes:
        regime: The unified regime classification
        confidence: Confidence score (0.0-1.0)
        adx_value: ADX indicator value (0-100)
        volatility_regime: Current volatility regime
        trend_direction: "up", "down", or "neutral"
        markov_trending: Whether Markov chain indicates trending
        markov_confidence: Markov chain confidence (0.0-1.0)
        volatility_score: Current volatility as percentage
        description: Human-readable description
        metadata: Additional metadata dict
    """

    regime: UnifiedRegime
    confidence: float
    adx_value: float
    volatility_regime: VolatilityRegime = VolatilityRegime.MEDIUM
    trend_direction: str = "neutral"
    markov_trending: bool = False
    markov_confidence: float = 0.0
    volatility_score: float = 0.0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "adx_value": round(self.adx_value, 2),
            "volatility_regime": self.volatility_regime.value,
            "trend_direction": self.trend_direction,
            "markov_trending": self.markov_trending,
            "markov_confidence": round(self.markov_confidence, 4),
            "volatility_score": round(self.volatility_score, 4),
            "is_trending": self.regime.is_trending,
            "is_ranging": self.regime.is_ranging,
            "is_volatile": self.regime.is_volatile,
            "description": self.description,
            "metadata": self.metadata,
        }


class MarketRegimeClassifier:
    """Unified market regime classifier.

    Integrates multiple regime detection methods:
    1. ADX (Average Directional Index) for trend strength
    2. Markov chain TrendInferenceEngine for trend state
    3. ATR-based volatility for volatility regime

    The classifier outputs one of four unified regimes:
    - TRENDING: ADX > 25 AND Markov agrees trending
    - RANGING: ADX < 20 AND Markov agrees ranging/neutral
    - VOLATILE: High volatility OR conflicting signals
    - UNKNOWN: Insufficient data

    Parameters:
        adx_period: Period for ADX calculation (default: 14)
        adx_trending_threshold: ADX threshold for trending (default: 25.0)
        adx_ranging_threshold: ADX threshold for ranging (default: 20.0)
        volatility_period: Period for volatility calculation (default: 14)
        min_data_ratio: Minimum ratio of required data vs available (default: 0.8)
    """

    # ADX thresholds
    ADX_TRENDING_THRESHOLD = 25.0
    ADX_RANGING_THRESHOLD = 20.0

    # Volatility thresholds (multipliers relative to average)
    VOLATILITY_HIGH_MULTIPLIER = 1.5
    VOLATILITY_LOW_MULTIPLIER = 0.5

    # Markov integration weight
    MARKOV_WEIGHT = 0.4
    ADX_WEIGHT = 0.6

    def __init__(
        self,
        adx_period: int = 14,
        adx_trending_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        volatility_period: int = 14,
        min_data_ratio: float = 0.8,
    ):
        """Initialize the classifier.

        Args:
            adx_period: Period for ADX calculation (default: 14)
            adx_trending_threshold: ADX threshold for trending (default: 25.0)
            adx_ranging_threshold: ADX threshold for ranging (default: 20.0)
            volatility_period: Period for volatility calculation (default: 14)
            min_data_ratio: Minimum ratio of data quality threshold (default: 0.8)
        """
        self.adx_period = adx_period
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_ranging_threshold = adx_ranging_threshold
        self.volatility_period = volatility_period
        self.min_data_ratio = min_data_ratio

        # Internal state for smoothing
        self._last_regime: UnifiedRegime | None = None
        self._consecutive_counts: dict[UnifiedRegime, int] = {
            UnifiedRegime.TRENDING: 0,
            UnifiedRegime.RANGING: 0,
            UnifiedRegime.VOLATILE: 0,
            UnifiedRegime.UNKNOWN: 0,
        }

    def classify(
        self,
        data: list[OHLCVData],
        volume_data: list[float] | None = None,
    ) -> RegimeClassification:
        """Classify market regime from OHLCV data.

        Integrates ADX, Markov chain state, and volatility analysis
        to produce a unified regime classification.

        Args:
            data: OHLCV price data (list of OHLCVData objects)
            volume_data: Optional volume data for confirmation

        Returns:
            RegimeClassification with regime type, confidence, and metadata
        """
        min_required = int((self.adx_period + 5) / self.min_data_ratio)

        if len(data) < min_required:
            return RegimeClassification(
                regime=UnifiedRegime.UNKNOWN,
                confidence=0.0,
                adx_value=0.0,
                description="Insufficient data for regime classification",
            )

        # Calculate components
        adx_value = self._calculate_adx(data)
        volatility_score = self._calculate_volatility(data)
        vol_regime = self._classify_volatility(volatility_score, data)
        markov_result = self._get_markov_trend(data)
        trend_direction = self._determine_trend_direction(data, adx_value)

        # Compute unified regime
        regime, confidence = self._compute_unified_regime(
            adx_value=adx_value,
            volatility_score=volatility_score,
            vol_regime=vol_regime,
            markov_trending=markov_result.is_trending,
            markov_confidence=markov_result.confidence,
        )

        # Smooth regime detection (avoid flapping)
        regime, confidence = self._smooth_regime_detection(regime, confidence)

        # Generate description
        description = self._generate_description(
            regime=regime,
            adx_value=adx_value,
            vol_regime=vol_regime,
            trend_direction=trend_direction,
            markov_trending=markov_result.is_trending,
        )

        return RegimeClassification(
            regime=regime,
            confidence=confidence,
            adx_value=adx_value,
            volatility_regime=vol_regime,
            trend_direction=trend_direction,
            markov_trending=markov_result.is_trending,
            markov_confidence=markov_result.confidence,
            volatility_score=volatility_score,
            description=description,
            metadata={
                "adx_trending_threshold": self.adx_trending_threshold,
                "adx_ranging_threshold": self.adx_ranging_threshold,
                "data_points": len(data),
            },
        )

    def _calculate_adx(self, data: list[OHLCVData]) -> float:
        """Calculate ADX (Average Directional Index).

        Args:
            data: OHLCV price data

        Returns:
            ADX value (0-100)
        """
        if len(data) < self.adx_period + 1:
            return 0.0

        # Calculate True Range
        tr_list: list[float] = []
        plus_dm_list: list[float] = []
        minus_dm_list: list[float] = []

        for i in range(1, len(data)):
            high = data[i].high_price
            low = data[i].low_price
            prev_close = data[i - 1].close_price

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

            high_diff = high - data[i - 1].high_price
            low_diff = data[i - 1].low_price - low

            plus_dm = max(high_diff, 0) if high_diff > low_diff else 0
            minus_dm = max(low_diff, 0) if low_diff > high_diff else 0

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        # Calculate smoothed values using Wilder's method
        atr = self._wilder_smooth(
            np.array(tr_list[-self.adx_period :]), self.adx_period
        )
        plus_di = self._wilder_smooth(
            np.array(plus_dm_list[-self.adx_period :]), self.adx_period
        )
        minus_di = self._wilder_smooth(
            np.array(minus_dm_list[-self.adx_period :]), self.adx_period
        )

        if atr == 0:
            return 0.0

        # Calculate DI values
        plus_di_pct = (plus_di / atr) * 100
        minus_di_pct = (minus_di / atr) * 100

        # Calculate DX
        di_sum = plus_di_pct + minus_di_pct
        if di_sum == 0:
            return 0.0

        dx = abs(plus_di_pct - minus_di_pct) / di_sum * 100

        return float(np.clip(dx, 0, 100))

    def _wilder_smooth(self, values: np.ndarray, period: int) -> float:
        """Apply Wilder's smoothing.

        Args:
            values: Array of values to smooth
            period: Smoothing period

        Returns:
            Smoothed value
        """
        if len(values) == 0:
            return 0.0

        if len(values) < period:
            return float(np.mean(values))

        # Initial SMA
        smoothed = float(np.mean(values[:period]))

        # Apply Wilder's smoothing
        for value in values[period:]:
            smoothed = (smoothed * (period - 1) + value) / period

        return smoothed

    def _calculate_volatility(self, data: list[OHLCVData]) -> float:
        """Calculate price volatility as percentage.

        Args:
            data: OHLCV price data

        Returns:
            Volatility as percentage (e.g., 2.5 means 2.5%)
        """
        if len(data) < 2:
            return 0.0

        closes = np.array([c.close_price for c in data[-self.volatility_period :]])

        if len(closes) < 2 or closes[0] == 0:
            return 0.0

        # Calculate standard deviation of returns
        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns) * 100

        return float(volatility)

    def _classify_volatility(
        self,
        volatility: float,
        data: list[OHLCVData],
    ) -> VolatilityRegime:
        """Classify volatility regime.

        Args:
            volatility: Current volatility percentage
            data: Price data for context

        Returns:
            Volatility regime classification
        """
        # Calculate historical average volatility
        if len(data) >= self.volatility_period * 2:
            hist_volatilities = []
            for i in range(self.volatility_period, len(data) - self.volatility_period):
                window = data[i : i + self.volatility_period]
                vol = self._calculate_volatility(window)
                hist_volatilities.append(vol)

            avg_vol = np.mean(hist_volatilities) if hist_volatilities else volatility
        else:
            avg_vol = volatility

        if avg_vol == 0:
            return VolatilityRegime.MEDIUM

        ratio = volatility / avg_vol

        if ratio > self.VOLATILITY_HIGH_MULTIPLIER:
            return VolatilityRegime.HIGH
        elif ratio < self.VOLATILITY_LOW_MULTIPLIER:
            return VolatilityRegime.LOW
        return VolatilityRegime.MEDIUM

    def _get_markov_trend(self, data: list[OHLCVData]) -> MarkovTrendResult:
        """Get trend state from Markov chain inference.

        Args:
            data: OHLCV price data

        Returns:
            MarkovTrendResult with is_trending and confidence
        """
        try:
            from market_analysis.markov import TrendInferenceEngine

            engine = TrendInferenceEngine()
            result = engine.infer_state(data)

            # Map TrendState to is_trending
            is_trending = (
                result.state.is_trending
                if hasattr(result.state, "is_trending")
                else False
            )

            return MarkovTrendResult(
                is_trending=is_trending,
                confidence=result.confidence,
            )
        except Exception:
            # If Markov inference fails, return neutral
            return MarkovTrendResult(is_trending=False, confidence=0.5)

    def _determine_trend_direction(
        self,
        data: list[OHLCVData],
        adx_value: float,
    ) -> str:
        """Determine trend direction.

        Args:
            data: OHLCV price data
            adx_value: Current ADX value

        Returns:
            "up", "down", or "neutral"
        """
        if len(data) < 10:
            return "neutral"

        if adx_value < self.adx_ranging_threshold:
            return "neutral"

        # Calculate recent price change
        recent_change = (
            (data[-1].close_price - data[-10].close_price) / data[-10].close_price * 100
        )

        if recent_change > 1.0:
            return "up"
        elif recent_change < -1.0:
            return "down"
        return "neutral"

    def _compute_unified_regime(
        self,
        adx_value: float,
        volatility_score: float,
        vol_regime: VolatilityRegime,
        markov_trending: bool,
        markov_confidence: float,
    ) -> tuple[UnifiedRegime, float]:
        """Compute unified regime from components.

        Args:
            adx_value: ADX indicator value
            volatility_score: Current volatility percentage
            vol_regime: Volatility regime classification
            markov_trending: Whether Markov indicates trending
            markov_confidence: Markov chain confidence

        Returns:
            Tuple of (regime, confidence)
        """
        # Weighted score for trending
        trending_score = self.ADX_WEIGHT * (adx_value / 100) + self.MARKOV_WEIGHT * (
            markov_confidence if markov_trending else 1 - markov_confidence
        )

        # High volatility reduces confidence and can indicate volatile regime
        is_high_volatility = vol_regime == VolatilityRegime.HIGH

        # Check for volatile market (high volatility with conflicting signals)
        if is_high_volatility:
            # If volatility is high but ADX is in ranging zone, likely volatile
            if adx_value < self.adx_trending_threshold:
                return UnifiedRegime.VOLATILE, 0.6

        # Trending: ADX above threshold AND (strong ADX OR Markov agrees)
        if adx_value >= self.adx_trending_threshold:
            if markov_trending or adx_value >= self.adx_trending_threshold + 10:
                confidence = min(1.0, trending_score + 0.2)
                return UnifiedRegime.TRENDING, confidence
            else:
                # High ADX but Markov not trending - could be volatile
                if is_high_volatility:
                    return UnifiedRegime.VOLATILE, 0.5

        # Ranging: ADX below ranging threshold AND not high volatility
        if adx_value <= self.adx_ranging_threshold and not is_high_volatility:
            confidence = min(1.0, (25 - adx_value) / 25 + 0.3)
            return UnifiedRegime.RANGING, confidence

        # Transitional zone (ADX between 20-25)
        # Default to volatile if volatility is high, otherwise ranging
        if is_high_volatility:
            return UnifiedRegime.VOLATILE, 0.4
        else:
            return UnifiedRegime.RANGING, 0.3

    def _smooth_regime_detection(
        self,
        regime: UnifiedRegime,
        confidence: float,
    ) -> tuple[UnifiedRegime, float]:
        """Apply smoothing to avoid regime flapping.

        Requires consecutive confirmations before changing regime.

        Args:
            regime: Raw detected regime
            confidence: Raw confidence

        Returns:
            Tuple of (smoothed regime, adjusted confidence)
        """
        # Reset counter for current regime
        for r in UnifiedRegime:
            if r != regime:
                self._consecutive_counts[r] = 0

        # Increment counter for detected regime
        self._consecutive_counts[regime] += 1

        # Require 2 consecutive detections before accepting regime change
        if self._last_regime is not None and self._last_regime != regime:
            if self._consecutive_counts[regime] < 2:
                # Not enough confirmation - keep previous regime
                return self._last_regime, confidence * 0.8

        # Update last regime
        self._last_regime = regime

        # Boost confidence for sustained regime
        if self._consecutive_counts[regime] >= 3:
            confidence = min(1.0, confidence + 0.1)

        return regime, confidence

    def _generate_description(
        self,
        regime: UnifiedRegime,
        adx_value: float,
        vol_regime: VolatilityRegime,
        trend_direction: str,
        markov_trending: bool,
    ) -> str:
        """Generate human-readable description.

        Args:
            regime: Detected regime
            adx_value: ADX value
            vol_regime: Volatility regime
            trend_direction: Trend direction
            markov_trending: Whether Markov indicates trending

        Returns:
            Description string
        """
        regime_descriptions = {
            UnifiedRegime.TRENDING: (
                f"Trending {trend_direction.title()}"
                if trend_direction != "neutral"
                else "Trending"
            ),
            UnifiedRegime.RANGING: "Ranging/Sideways",
            UnifiedRegime.VOLATILE: "High Volatility",
            UnifiedRegime.UNKNOWN: "Unknown",
        }

        parts = [regime_descriptions.get(regime, "Unknown")]

        if vol_regime != VolatilityRegime.MEDIUM:
            parts.append(f"{vol_regime.value.capitalize()} volatility")

        if regime == UnifiedRegime.TRENDING:
            if markov_trending:
                parts.append("Markov confirmed")
        elif regime == UnifiedRegime.VOLATILE:
            parts.append(f"ADX: {adx_value:.1f}")

        return " | ".join(parts)

    def reset(self) -> None:
        """Reset internal state for fresh classification."""
        self._last_regime = None
        self._consecutive_counts = {
            UnifiedRegime.TRENDING: 0,
            UnifiedRegime.RANGING: 0,
            UnifiedRegime.VOLATILE: 0,
            UnifiedRegime.UNKNOWN: 0,
        }


@dataclass
class MarkovTrendResult:
    """Result from Markov trend analysis.

    Attributes:
        is_trending: Whether Markov indicates trending market
        confidence: Confidence in the trend detection (0.0-1.0)
    """

    is_trending: bool
    confidence: float


# Backward compatibility - deprecated aliases
RegimeType = UnifiedRegime
MarketRegime = RegimeClassification
