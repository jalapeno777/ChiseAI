"""Signal aggregator for collecting and normalizing indicator signals.

Provides interfaces to collect signals from multiple indicators,
normalize them to a common format, filter weak signals, and
aggregate into a unified structure for confluence scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from market_analysis.indicators.bollinger_bands import BollingerBandsResult
    from market_analysis.indicators.macd import MACDResult
    from market_analysis.indicators.rsi import RSIResult
    from market_analysis.markov.state_model import TrendState

logger = logging.getLogger(__name__)


class SignalDirection(Enum):
    """Direction of a trading signal."""

    LONG = auto()
    SHORT = auto()
    NEUTRAL = auto()

    def __str__(self) -> str:
        """Return human-readable direction name."""
        return self.name.lower()

    def opposite(self) -> SignalDirection:
        """Get the opposite direction."""
        if self == SignalDirection.LONG:
            return SignalDirection.SHORT
        elif self == SignalDirection.SHORT:
            return SignalDirection.LONG
        return SignalDirection.NEUTRAL


@dataclass
class IndicatorSignal:
    """Normalized signal from an individual indicator.

    Attributes:
        indicator_type: Type of indicator (rsi, macd, bb, markov)
        timeframe: Timeframe of the signal (1m, 5m, 15m, 1h, 4h, 1d)
        direction: Signal direction (LONG, SHORT, NEUTRAL)
        strength: Signal strength (0.0-1.0)
        confidence: Confidence in the signal (0.0-1.0)
        raw_value: Raw indicator value for logging
        timestamp: Timestamp of the signal (ms)
        metadata: Additional indicator-specific data
    """

    indicator_type: str
    timeframe: str
    direction: SignalDirection
    strength: float
    confidence: float
    raw_value: float | None = None
    timestamp: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate signal values."""
        self.strength = max(0.0, min(1.0, self.strength))
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_valid(self) -> bool:
        """Check if signal has valid values."""
        return bool(
            0.0 <= self.strength <= 1.0
            and 0.0 <= self.confidence <= 1.0
            and self.indicator_type
            and self.timeframe
        )

    @property
    def weighted_score(self) -> float:
        """Calculate weighted score for this signal.

        Returns:
            Score combining direction, strength, and confidence
        """
        direction_multiplier = 1.0 if self.direction != SignalDirection.NEUTRAL else 0.5
        return self.strength * self.confidence * direction_multiplier

    def to_dict(self) -> dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            "indicator_type": self.indicator_type,
            "timeframe": self.timeframe,
            "direction": str(self.direction),
            "strength": self.strength,
            "confidence": self.confidence,
            "raw_value": self.raw_value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class AggregatedSignals:
    """Collection of aggregated signals from multiple indicators.

    Attributes:
        signals: List of individual indicator signals
        timestamp: Timestamp of aggregation (ms)
        long_count: Number of LONG signals
        short_count: Number of SHORT signals
        neutral_count: Number of NEUTRAL signals
        total_strength: Sum of all signal strengths
    """

    signals: list[IndicatorSignal] = field(default_factory=list)
    timestamp: int | None = None

    def __post_init__(self) -> None:
        """Initialize counts from signals."""
        self._update_counts()

    def _update_counts(self) -> None:
        """Update signal counts."""
        self.long_count = sum(
            1 for s in self.signals if s.direction == SignalDirection.LONG
        )
        self.short_count = sum(
            1 for s in self.signals if s.direction == SignalDirection.SHORT
        )
        self.neutral_count = sum(
            1 for s in self.signals if s.direction == SignalDirection.NEUTRAL
        )

    @property
    def total_signals(self) -> int:
        """Total number of signals."""
        return len(self.signals)

    @property
    def total_strength(self) -> float:
        """Sum of all signal strengths."""
        return sum(s.strength for s in self.signals)

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all signals."""
        if not self.signals:
            return 0.0
        return sum(s.confidence for s in self.signals) / len(self.signals)

    @property
    def dominant_direction(self) -> SignalDirection:
        """Determine dominant direction based on signal counts."""
        if self.long_count > self.short_count:
            return SignalDirection.LONG
        elif self.short_count > self.long_count:
            return SignalDirection.SHORT
        return SignalDirection.NEUTRAL

    @property
    def direction_agreement(self) -> float:
        """Calculate agreement ratio for dominant direction.

        Returns:
            Ratio of signals agreeing with dominant direction (0-1)
        """
        if not self.signals:
            return 0.0

        dominant = self.dominant_direction
        if dominant == SignalDirection.NEUTRAL:
            return self.neutral_count / len(self.signals)

        agreeing = (
            self.long_count if dominant == SignalDirection.LONG else self.short_count
        )
        return agreeing / len(self.signals)

    def get_signals_by_direction(
        self, direction: SignalDirection
    ) -> list[IndicatorSignal]:
        """Get all signals with a specific direction.

        Args:
            direction: Direction to filter by

        Returns:
            List of matching signals
        """
        return [s for s in self.signals if s.direction == direction]

    def get_signals_by_timeframe(self, timeframe: str) -> list[IndicatorSignal]:
        """Get all signals for a specific timeframe.

        Args:
            timeframe: Timeframe to filter by

        Returns:
            List of matching signals
        """
        return [s for s in self.signals if s.timeframe == timeframe]

    def add_signal(self, signal: IndicatorSignal) -> None:
        """Add a signal to the aggregation.

        Args:
            signal: Signal to add
        """
        self.signals.append(signal)
        self._update_counts()

    def filter_by_strength(self, min_strength: float) -> AggregatedSignals:
        """Filter signals by minimum strength.

        Args:
            min_strength: Minimum strength threshold (0-1)

        Returns:
            New AggregatedSignals with filtered signals
        """
        filtered = [s for s in self.signals if s.strength >= min_strength]
        return AggregatedSignals(
            signals=filtered,
            timestamp=self.timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert aggregated signals to dictionary."""
        return {
            "signals": [s.to_dict() for s in self.signals],
            "timestamp": self.timestamp,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "neutral_count": self.neutral_count,
            "total_strength": self.total_strength,
            "avg_confidence": self.avg_confidence,
            "dominant_direction": str(self.dominant_direction),
            "direction_agreement": self.direction_agreement,
        }


class SignalAggregator:
    """Aggregates signals from multiple indicators into a unified structure."""

    def __init__(
        self,
        min_signal_threshold: float = 0.3,
        max_indicators: int = 10,
    ):
        """Initialize signal aggregator.

        Args:
            min_signal_threshold: Minimum signal strength to include
            max_indicators: Maximum number of indicators to aggregate
        """
        self.min_signal_threshold = min_signal_threshold
        self.max_indicators = max_indicators

    def aggregate(
        self,
        signals: Sequence[IndicatorSignal],
        timestamp: int | None = None,
    ) -> AggregatedSignals:
        """Aggregate multiple indicator signals.

        Args:
            signals: Sequence of indicator signals
            timestamp: Optional timestamp for the aggregation

        Returns:
            AggregatedSignals containing filtered and organized signals
        """
        # Filter by strength threshold
        filtered = [
            s for s in signals if s.strength >= self.min_signal_threshold and s.is_valid
        ]

        # Sort by weighted score (descending) and limit count
        sorted_signals = sorted(
            filtered,
            key=lambda s: s.weighted_score,
            reverse=True,
        )[: self.max_indicators]

        logger.debug(
            f"Aggregated {len(signals)} signals -> {len(sorted_signals)} "
            f"after filtering (threshold={self.min_signal_threshold})"
        )

        return AggregatedSignals(
            signals=sorted_signals,
            timestamp=timestamp,
        )

    @staticmethod
    def from_rsi(
        rsi_result: RSIResult,
        timeframe: str,
        timestamp: int | None = None,
    ) -> IndicatorSignal | None:
        """Create signal from RSI result.

        Args:
            rsi_result: RSI calculation result
            timeframe: Timeframe of the data
            timestamp: Optional timestamp override

        Returns:
            IndicatorSignal or None if insufficient data
        """
        current_rsi = rsi_result.current
        if current_rsi is None:
            return None

        # Determine direction and strength based on RSI
        if rsi_result.is_overbought:
            direction = SignalDirection.SHORT
            # Strength increases as RSI goes higher above 70
            strength = min(1.0, (current_rsi - 70) / 20 + 0.5)
        elif rsi_result.is_oversold:
            direction = SignalDirection.LONG
            # Strength increases as RSI goes lower below 30
            strength = min(1.0, (30 - current_rsi) / 20 + 0.5)
        else:
            direction = SignalDirection.NEUTRAL
            # Neutral zone - strength based on distance from 50
            distance_from_center = abs(current_rsi - 50)
            strength = distance_from_center / 50  # 0 at 50, 0.4 at 30/70

        # Confidence based on how clear the signal is
        if direction in (SignalDirection.LONG, SignalDirection.SHORT):
            confidence = 0.7 + strength * 0.3  # 0.7-1.0 for extreme signals
        else:
            confidence = 0.5  # Lower confidence for neutral

        return IndicatorSignal(
            indicator_type="rsi",
            timeframe=timeframe,
            direction=direction,
            strength=strength,
            confidence=confidence,
            raw_value=current_rsi,
            timestamp=(
                timestamp or int(rsi_result.timestamps[-1])
                if len(rsi_result.timestamps) > 0
                else None
            ),
            metadata={
                "overbought": rsi_result.is_overbought,
                "oversold": rsi_result.is_oversold,
            },
        )

    @staticmethod
    def from_macd(
        macd_result: MACDResult,
        timeframe: str,
        timestamp: int | None = None,
    ) -> IndicatorSignal | None:
        """Create signal from MACD result.

        Args:
            macd_result: MACD calculation result
            timeframe: Timeframe of the data
            timestamp: Optional timestamp override

        Returns:
            IndicatorSignal or None if insufficient data
        """
        macd_line = macd_result.current_macd
        signal_line = macd_result.current_signal
        histogram = macd_result.current_histogram

        if macd_line is None or signal_line is None:
            return None

        # Determine direction based on MACD vs signal line
        diff = macd_line - signal_line
        abs_diff = abs(diff)

        if diff > 0:
            direction = SignalDirection.LONG
        elif diff < 0:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL

        # Strength based on histogram magnitude (normalized)
        if histogram is not None:
            # Normalize histogram - assume typical range of +/- 0.5% of price
            # This is approximate; in practice, you'd want price context
            strength = min(1.0, abs_diff / max(abs(macd_line) * 0.1, 0.001))
        else:
            strength = 0.5

        # Check for recent crossover
        latest_crossover = macd_result.latest_crossover
        crossover_boost = 0.0
        if latest_crossover.value != "none":
            # Recent crossover increases confidence
            crossover_boost = 0.2

        # Confidence based on histogram trend and crossover
        confidence = 0.6 + strength * 0.2 + crossover_boost
        confidence = min(1.0, confidence)

        return IndicatorSignal(
            indicator_type="macd",
            timeframe=timeframe,
            direction=direction,
            strength=strength,
            confidence=confidence,
            raw_value=macd_line,
            timestamp=(
                timestamp or int(macd_result.timestamps[-1])
                if len(macd_result.timestamps) > 0
                else None
            ),
            metadata={
                "signal_line": signal_line,
                "histogram": histogram,
                "latest_crossover": str(latest_crossover),
            },
        )

    @staticmethod
    def from_bollinger_bands(
        bb_result: BollingerBandsResult,
        current_price: float,
        timeframe: str,
        timestamp: int | None = None,
    ) -> IndicatorSignal | None:
        """Create signal from Bollinger Bands result.

        Args:
            bb_result: Bollinger Bands calculation result
            current_price: Current price for %B calculation
            timeframe: Timeframe of the data
            timestamp: Optional timestamp override

        Returns:
            IndicatorSignal or None if insufficient data
        """
        percent_b = bb_result.current_percent_b
        if percent_b is None:
            return None

        # Determine direction based on %B position
        if percent_b > 0.8:
            direction = SignalDirection.SHORT  # Near upper band = overbought
            strength = min(1.0, (percent_b - 0.8) / 0.2)
        elif percent_b < 0.2:
            direction = SignalDirection.LONG  # Near lower band = oversold
            strength = min(1.0, (0.2 - percent_b) / 0.2)
        else:
            direction = SignalDirection.NEUTRAL
            # Strength based on distance from middle (0.5)
            distance_from_middle = abs(percent_b - 0.5)
            strength = distance_from_middle * 2  # 0 at 0.5, 0.6 at 0.2/0.8

        # Confidence based on band squeeze (volatility)
        band_width = bb_result.current_band_width
        if band_width is not None and bb_result.current_middle is not None:
            # Squeeze = lower confidence (breakout potential)
            # Wide bands = higher confidence (established range)
            relative_width = band_width / max(bb_result.current_middle, 0.001)
            if relative_width < 0.01:  # Very tight squeeze
                confidence = 0.4
            elif relative_width > 0.05:  # Wide bands
                confidence = 0.9
            else:
                confidence = 0.6 + (relative_width - 0.01) / 0.04 * 0.3
        else:
            confidence = 0.6

        return IndicatorSignal(
            indicator_type="bb",
            timeframe=timeframe,
            direction=direction,
            strength=strength,
            confidence=confidence,
            raw_value=percent_b,
            timestamp=(
                timestamp or int(bb_result.timestamps[-1])
                if len(bb_result.timestamps) > 0
                else None
            ),
            metadata={
                "upper_band": bb_result.current_upper,
                "lower_band": bb_result.current_lower,
                "band_width": band_width,
            },
        )

    @staticmethod
    def from_markov_state(
        state: TrendState,
        confidence: float,
        signal_strength: float,
        timeframe: str,
        timestamp: int | None = None,
    ) -> IndicatorSignal | None:
        """Create signal from Markov trend state.

        Args:
            state: Trend state from Markov model
            confidence: State confidence (0.0-1.0)
            signal_strength: Signal strength from inference
            timeframe: Timeframe of the data
            timestamp: Optional timestamp

        Returns:
            IndicatorSignal or None if insufficient data
        """
        # Map trend state to signal direction
        if state.value == 1:  # BULLISH
            direction = SignalDirection.LONG
        elif state.value == 2:  # BEARISH
            direction = SignalDirection.SHORT
        else:  # NEUTRAL or TRANSITIONAL
            direction = SignalDirection.NEUTRAL

        # Strength from signal_strength, normalized to 0-1
        strength = min(1.0, max(0.0, signal_strength))

        # Confidence directly from Markov inference
        signal_confidence = min(1.0, max(0.0, confidence))

        return IndicatorSignal(
            indicator_type="markov",
            timeframe=timeframe,
            direction=direction,
            strength=strength,
            confidence=signal_confidence,
            raw_value=float(state.value) if hasattr(state, "value") else None,
            timestamp=timestamp,
            metadata={
                "state_name": str(state),
                "is_trending": (
                    state.is_trending if hasattr(state, "is_trending") else None
                ),
            },
        )
