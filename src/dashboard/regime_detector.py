"""Market regime detection for pre-market briefing.

Detects whether the market is trending or ranging using ADX indicator,
volatility analysis, and volume confirmation. Implements a state machine
for regime transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


class RegimeType(Enum):
    """Market regime type."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    TRANSITIONAL = "transitional"
    UNKNOWN = "unknown"


@dataclass
class MarketRegime:
    """Market regime detection result.

    Attributes:
        regime: Current regime type
        confidence: Confidence in the regime detection (0-100)
        adx_value: ADX indicator value
        volatility_regime: Volatility regime (high/medium/low)
        volume_confirmation: Whether volume confirms the regime
        duration_bars: How long the current regime has persisted
        transition_probability: Probability of regime transition
        description: Human-readable description
    """

    regime: RegimeType
    confidence: float
    adx_value: float
    volatility_regime: str = "medium"
    volume_confirmation: bool = False
    duration_bars: int = 0
    transition_probability: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.confidence = max(0.0, min(100.0, self.confidence))
        self.transition_probability = max(0.0, min(1.0, self.transition_probability))

    @property
    def is_trending(self) -> bool:
        """Check if market is trending."""
        return self.regime in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN)

    @property
    def is_ranging(self) -> bool:
        """Check if market is ranging."""
        return self.regime == RegimeType.RANGING

    @property
    def direction(self) -> str:
        """Get trend direction if trending."""
        if self.regime == RegimeType.TRENDING_UP:
            return "up"
        elif self.regime == RegimeType.TRENDING_DOWN:
            return "down"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for dashboard payload."""
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 1),
            "adx_value": round(self.adx_value, 2),
            "volatility_regime": self.volatility_regime,
            "volume_confirmation": self.volume_confirmation,
            "duration_bars": self.duration_bars,
            "transition_probability": round(self.transition_probability, 2),
            "is_trending": self.is_trending,
            "is_ranging": self.is_ranging,
            "direction": self.direction,
            "description": self.description,
        }


@dataclass
class RegimeState:
    """Internal state for regime detection state machine.

    Attributes:
        current_regime: Current detected regime
        previous_regime: Previous regime before current
        regime_history: List of recent regimes
        adx_history: List of recent ADX values
        volatility_history: List of recent volatility values
    """

    current_regime: RegimeType = RegimeType.UNKNOWN
    previous_regime: RegimeType = RegimeType.UNKNOWN
    regime_history: list[RegimeType] = field(default_factory=list)
    adx_history: list[float] = field(default_factory=list)
    volatility_history: list[float] = field(default_factory=list)

    def update(self, regime: RegimeType, adx: float, volatility: float) -> None:
        """Update state with new regime detection.

        Args:
            regime: Newly detected regime
            adx: ADX value
            volatility: Volatility value
        """
        if regime != self.current_regime:
            self.previous_regime = self.current_regime
            self.current_regime = regime

        self.regime_history.append(regime)
        self.adx_history.append(adx)
        self.volatility_history.append(volatility)

        # Keep history limited
        max_history = 50
        if len(self.regime_history) > max_history:
            self.regime_history = self.regime_history[-max_history:]
            self.adx_history = self.adx_history[-max_history:]
            self.volatility_history = self.volatility_history[-max_history:]

    @property
    def regime_duration(self) -> int:
        """Calculate how long current regime has persisted."""
        if not self.regime_history:
            return 0

        count = 0
        for regime in reversed(self.regime_history):
            if regime == self.current_regime:
                count += 1
            else:
                break
        return count


class RegimeDetector:
    """Market regime detector using ADX, volatility, and volume.

    Detects market regimes:
    - Trending: ADX > 25 with directional movement
    - Ranging: ADX < 20 with bounded price action
    - Transitional: ADX between 20-25 or conflicting signals

    Uses state machine for smooth regime transitions.
    """

    def __init__(
        self,
        adx_period: int = 14,
        adx_trending_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        volatility_period: int = 14,
    ):
        """Initialize regime detector.

        Args:
            adx_period: Period for ADX calculation (default: 14)
            adx_trending_threshold: ADX threshold for trending (default: 25)
            adx_ranging_threshold: ADX threshold for ranging (default: 20)
            volatility_period: Period for volatility calculation (default: 14)
        """
        self.adx_period = adx_period
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_ranging_threshold = adx_ranging_threshold
        self.volatility_period = volatility_period

        self._state = RegimeState()

    def detect(
        self,
        data: list["OHLCVData"],
        volume_data: list[float] | None = None,
    ) -> MarketRegime:
        """Detect market regime from price data.

        Args:
            data: OHLCV price data
            volume_data: Optional volume data for confirmation

        Returns:
            MarketRegime with detection results
        """
        if len(data) < self.adx_period + 5:
            return MarketRegime(
                regime=RegimeType.UNKNOWN,
                confidence=0.0,
                adx_value=0.0,
                description="Insufficient data for regime detection",
            )

        # Calculate ADX
        adx_value = self._calculate_adx(data)

        # Calculate volatility
        volatility = self._calculate_volatility(data)

        # Determine volatility regime
        vol_regime = self._classify_volatility(volatility, data)

        # Check volume confirmation
        volume_confirmed = self._check_volume_confirmation(volume_data)

        # Determine regime based on ADX and price action
        regime = self._determine_regime(data, adx_value)

        # Calculate confidence
        confidence = self._calculate_confidence(regime, adx_value, volatility)

        # Update state machine
        self._state.update(regime, adx_value, volatility)

        # Calculate transition probability
        transition_prob = self._calculate_transition_probability()

        # Generate description
        description = self._generate_description(
            regime, adx_value, vol_regime, volume_confirmed
        )

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            adx_value=adx_value,
            volatility_regime=vol_regime,
            volume_confirmation=volume_confirmed,
            duration_bars=self._state.regime_duration,
            transition_probability=transition_prob,
            description=description,
        )

    def _calculate_adx(self, data: list["OHLCVData"]) -> float:
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
        for i in range(1, len(data)):
            high = data[i].high_price
            low = data[i].low_price
            prev_close = data[i - 1].close_price

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        # Calculate +DM and -DM
        plus_dm_list: list[float] = []
        minus_dm_list: list[float] = []

        for i in range(1, len(data)):
            high_diff = data[i].high_price - data[i - 1].high_price
            low_diff = data[i - 1].low_price - data[i].low_price

            plus_dm = max(high_diff, 0) if high_diff > low_diff else 0
            minus_dm = max(low_diff, 0) if low_diff > high_diff else 0

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        # Calculate smoothed averages
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

        # Calculate +DI and -DI
        plus_di = (plus_di / atr) * 100
        minus_di = (minus_di / atr) * 100

        # Calculate DX
        dx = (
            abs(plus_di - minus_di) / (plus_di + minus_di) * 100
            if (plus_di + minus_di) > 0
            else 0
        )

        # ADX is smoothed DX (simplified - using current DX)
        return float(dx)

    def _wilder_smooth(self, values: np.ndarray, period: int) -> float:
        """Apply Wilder's smoothing to values.

        Args:
            values: Array of values
            period: Smoothing period

        Returns:
            Smoothed value
        """
        if len(values) == 0:
            return 0.0

        if len(values) < period:
            return float(np.mean(values))

        # Initial SMA
        smoothed = np.mean(values[:period])

        # Apply smoothing
        alpha = 1.0 / period
        for value in values[period:]:
            smoothed = (smoothed * (period - 1) + value) / period

        return float(smoothed)

    def _calculate_volatility(self, data: list["OHLCVData"]) -> float:
        """Calculate price volatility as percentage.

        Args:
            data: OHLCV price data

        Returns:
            Volatility percentage
        """
        if len(data) < 2:
            return 0.0

        closes = np.array([c.close_price for c in data[-self.volatility_period :]])

        if len(closes) < 2 or closes[0] == 0:
            return 0.0

        # Calculate standard deviation of returns
        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns) * 100  # As percentage

        return float(volatility)

    def _classify_volatility(
        self,
        volatility: float,
        data: list["OHLCVData"],
    ) -> str:
        """Classify volatility regime.

        Args:
            volatility: Volatility percentage
            data: Price data for context

        Returns:
            Volatility regime classification
        """
        # Calculate average volatility from historical data
        if len(data) >= self.volatility_period * 2:
            hist_volatilities = []
            for i in range(self.volatility_period, len(data) - self.volatility_period):
                window = data[i : i + self.volatility_period]
                vol = self._calculate_volatility(window)
                hist_volatilities.append(vol)

            avg_vol = np.mean(hist_volatilities) if hist_volatilities else volatility
        else:
            avg_vol = volatility

        if volatility > avg_vol * 1.5:
            return "high"
        elif volatility < avg_vol * 0.5:
            return "low"
        return "medium"

    def _check_volume_confirmation(self, volume_data: list[float] | None) -> bool:
        """Check if volume confirms the current regime.

        Args:
            volume_data: Volume data list

        Returns:
            True if volume confirms regime
        """
        if not volume_data or len(volume_data) < 10:
            return False

        recent_volume = np.mean(volume_data[-5:])
        avg_volume = np.mean(volume_data)

        # Higher volume confirms trend/range breakout
        return recent_volume > avg_volume * 1.1

    def _determine_regime(
        self,
        data: list["OHLCVData"],
        adx_value: float,
    ) -> RegimeType:
        """Determine market regime from ADX and price action.

        Args:
            data: Price data
            adx_value: ADX value

        Returns:
            Detected regime type
        """
        # Determine trend direction from recent price action
        if len(data) >= 10:
            recent_change = (
                (data[-1].close_price - data[-10].close_price)
                / data[-10].close_price
                * 100
            )
        else:
            recent_change = 0.0

        if adx_value >= self.adx_trending_threshold:
            # Trending regime
            if recent_change > 1.0:
                return RegimeType.TRENDING_UP
            elif recent_change < -1.0:
                return RegimeType.TRENDING_DOWN
            else:
                # ADX high but price not moving much - transitional
                return RegimeType.TRANSITIONAL
        elif adx_value <= self.adx_ranging_threshold:
            # Ranging regime
            return RegimeType.RANGING
        else:
            # Transitional zone
            return RegimeType.TRANSITIONAL

    def _calculate_confidence(
        self,
        regime: RegimeType,
        adx_value: float,
        volatility: float,
    ) -> float:
        """Calculate confidence in regime detection.

        Args:
            regime: Detected regime
            adx_value: ADX value
            volatility: Volatility

        Returns:
            Confidence score (0-100)
        """
        # Base confidence on ADX strength
        if regime in (RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN):
            # Higher ADX = higher confidence for trending
            confidence = min(100.0, adx_value * 3)
        elif regime == RegimeType.RANGING:
            # Lower ADX = higher confidence for ranging
            confidence = min(100.0, (25 - adx_value) * 4)
        else:
            # Transitional - medium confidence
            confidence = 50.0

        # Adjust for volatility (extreme volatility reduces confidence)
        if volatility > 5.0:
            confidence *= 0.8

        return max(0.0, min(100.0, confidence))

    def _calculate_transition_probability(self) -> float:
        """Calculate probability of regime transition.

        Returns:
            Transition probability (0-1)
        """
        if len(self._state.regime_history) < 10:
            return 0.0

        # Check for ADX convergence/divergence
        if len(self._state.adx_history) >= 5:
            recent_adx = np.mean(self._state.adx_history[-3:])
            prev_adx = np.mean(self._state.adx_history[-5:-2])

            # ADX moving toward middle zone suggests transition
            if self._state.current_regime in (
                RegimeType.TRENDING_UP,
                RegimeType.TRENDING_DOWN,
            ):
                if recent_adx < prev_adx:
                    return min(0.5, (prev_adx - recent_adx) / 10)
            elif self._state.current_regime == RegimeType.RANGING:
                if recent_adx > prev_adx:
                    return min(0.5, (recent_adx - prev_adx) / 10)

        return 0.0

    def _generate_description(
        self,
        regime: RegimeType,
        adx_value: float,
        vol_regime: str,
        volume_confirmed: bool,
    ) -> str:
        """Generate human-readable regime description.

        Args:
            regime: Detected regime
            adx_value: ADX value
            vol_regime: Volatility regime
            volume_confirmed: Volume confirmation status

        Returns:
            Description string
        """
        regime_desc = {
            RegimeType.TRENDING_UP: "Trending Up",
            RegimeType.TRENDING_DOWN: "Trending Down",
            RegimeType.RANGING: "Ranging/Sideways",
            RegimeType.TRANSITIONAL: "In Transition",
            RegimeType.UNKNOWN: "Unknown",
        }.get(regime, "Unknown")

        parts = [regime_desc]

        if vol_regime != "medium":
            parts.append(f"{vol_regime.capitalize()} volatility")

        if volume_confirmed:
            parts.append("Volume confirmed")

        return " | ".join(parts)

    def reset_state(self) -> None:
        """Reset the state machine."""
        self._state = RegimeState()
