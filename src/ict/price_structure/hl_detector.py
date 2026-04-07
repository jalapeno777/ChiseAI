"""High/Low (H/L) and Old High/Low (H-OLD/L-OLD) break detector.

Detects ICT price structure breakouts:
- H: Current period high breaking above previous high
- L: Current period low breaking below previous low
- H-OLD: Price breaking above the OLD significant high
- L-OLD: Price breaking below the OLD significant low

A breakout is detected when the close price crosses beyond a level
(not just wick penetration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData

logger = logging.getLogger(__name__)


@dataclass
class HLBreakout:
    """Represents a detected H/L/H-OLD/L-OLD breakout.

    Attributes:
        breakout_type: One of "h", "l", "high_old", "low_old".
        price: The price at which the breakout occurred (close price).
        direction: "long" for bullish breakouts (H, H-OLD), "short" for bearish (L, L-OLD).
        confidence: Confidence score from 0.0 to 1.0.
        timestamp: Unix timestamp in milliseconds.
        swing_high: For H-OLD/L-OLD, the swing high reference (if applicable).
        swing_low: For H-OLD/L-OLD, the swing low reference (if applicable).
        level_price: The level price that was broken.
        penetration_pct: How far beyond the level the close penetrated (%).
    """

    breakout_type: str
    price: float
    direction: str
    confidence: float
    timestamp: int
    swing_high: float | None = None
    swing_low: float | None = None
    level_price: float = 0.0
    penetration_pct: float = 0.0

    def __post_init__(self) -> None:
        if self.breakout_type not in ("h", "l", "high_old", "low_old"):
            raise ValueError(
                f"breakout_type must be one of 'h', 'l', 'high_old', 'low_old', "
                f"got {self.breakout_type!r}"
            )
        if self.direction not in ("long", "short"):
            raise ValueError(
                f"direction must be 'long' or 'short', got {self.direction!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.level_price <= 0:
            raise ValueError(f"level_price must be positive, got {self.level_price}")
        if self.penetration_pct < 0:
            raise ValueError(
                f"penetration_pct must be non-negative, got {self.penetration_pct}"
            )

    def to_signal_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by ICTSignalEmitter."""
        return {
            "price": self.price,
            "direction": self.direction,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "swing_high": self.swing_high,
            "swing_low": self.swing_low,
        }


class HLDetectorConfig:
    """Configuration for HLDetector.

    Attributes:
        lookback: Number of bars to look back for H-OLD/L-OLD identification.
        break_threshold_pct: Minimum % beyond level to count as a breakout.
            A breakout must exceed this threshold to be valid.
    """

    def __init__(
        self,
        lookback: int = 20,
        break_threshold_pct: float = 0.01,
    ) -> None:
        if lookback < 2:
            raise ValueError(f"lookback must be >= 2, got {lookback}")
        if break_threshold_pct < 0:
            raise ValueError(
                f"break_threshold_pct must be non-negative, got {break_threshold_pct}"
            )

        self.lookback = lookback
        self.break_threshold_pct = break_threshold_pct


class HLDetector:
    """Detects H/L and H-OLD/L-OLD breakouts from OHLCV data.

    ICT concepts:
        - H: Current period high (highest high of current period).
        - L: Current period low (lowest low of current period).
        - H-OLD: Previous significant high from lookback period.
        - L-OLD: Previous significant low from lookback period.

    A "breakout" occurs when the close price closes beyond a level
    (not just wick penetration).

    The detector identifies:
        - H breakout (bullish): close closes above previous high
        - L breakout (bearish): close closes below previous low
        - H-OLD breakout (bullish): close closes above OLD high
        - L-OLD breakout (bearish): close closes below OLD low

    Parameters:
        config: Detector configuration parameters.
    """

    def __init__(
        self,
        config: HLDetectorConfig | None = None,
        lookback: int = 20,
        break_threshold_pct: float = 0.01,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = HLDetectorConfig(
                lookback=lookback,
                break_threshold_pct=break_threshold_pct,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        data: list[OHLCVData],
    ) -> dict[str, HLBreakout | None]:
        """Detect H/L/H-OLD/L-OLD breakouts from OHLCV data.

        Analyzes the data to find breakouts. At least `lookback + 2` candles
        are required to detect H-OLD/L-OLD signals.

        Args:
            data: List of OHLCV candles (oldest to newest).

        Returns:
            Dict with keys: "h", "l", "high_old", "low_old".
            Each value is either HLBreakout (signal detected) or None (no signal).
        """
        if len(data) < 2:
            return {"h": None, "l": None, "high_old": None, "low_old": None}

        result: dict[str, HLBreakout | None] = {
            "h": None,
            "l": None,
            "high_old": None,
            "low_old": None,
        }

        # Detect H and L (current period breakouts)
        result["h"] = self._detect_h_breakout(data)
        result["l"] = self._detect_l_breakout(data)

        # Detect H-OLD and L-OLD (require sufficient lookback)
        if len(data) >= self.config.lookback + 2:
            result["high_old"] = self._detect_high_old_breakout(data)
            result["low_old"] = self._detect_low_old_breakout(data)

        return result

    # ------------------------------------------------------------------
    # H/L Detection
    # ------------------------------------------------------------------

    def _detect_h_breakout(self, data: list[OHLCVData]) -> HLBreakout | None:
        """Detect H breakout: close closes above previous high.

        Args:
            data: List of OHLCV candles.

        Returns:
            HLBreakout if H breakout detected, None otherwise.
        """
        if len(data) < 2:
            return None

        # Current close price
        current_close = data[-1].close_price
        current_timestamp = data[-1].timestamp

        # Previous high is the high of the second-most recent candle
        prev_high = data[-2].high_price

        # H breakout: bullish when close closes above previous high
        if prev_high > 0 and current_close > prev_high:
            penetration_pct = (current_close - prev_high) / prev_high * 100
            if penetration_pct >= self.config.break_threshold_pct:
                confidence = self._calculate_confidence(penetration_pct)
                return HLBreakout(
                    breakout_type="h",
                    price=current_close,
                    direction="long",
                    confidence=confidence,
                    timestamp=current_timestamp,
                    level_price=prev_high,
                    penetration_pct=penetration_pct,
                )

        return None

    def _detect_l_breakout(self, data: list[OHLCVData]) -> HLBreakout | None:
        """Detect L breakout: close closes below previous low.

        Args:
            data: List of OHLCV candles.

        Returns:
            HLBreakout if L breakout detected, None otherwise.
        """
        if len(data) < 2:
            return None

        # Current close price
        current_close = data[-1].close_price
        current_timestamp = data[-1].timestamp

        # Previous low is the low of the second-most recent candle
        prev_low = data[-2].low_price

        # L breakout: bearish when close closes below previous low
        if prev_low > 0 and current_close < prev_low:
            penetration_pct = (prev_low - current_close) / prev_low * 100
            if penetration_pct >= self.config.break_threshold_pct:
                confidence = self._calculate_confidence(penetration_pct)
                return HLBreakout(
                    breakout_type="l",
                    price=current_close,
                    direction="short",
                    confidence=confidence,
                    timestamp=current_timestamp,
                    level_price=prev_low,
                    penetration_pct=penetration_pct,
                )

        return None

    # ------------------------------------------------------------------
    # H-OLD/L-OLD Detection
    # ------------------------------------------------------------------

    def _detect_high_old_breakout(self, data: list[OHLCVData]) -> HLBreakout | None:
        """Detect H-OLD breakout: close closes above OLD high from lookback period.

        The OLD high is the highest high from the lookback period (excluding
        the most recent candle). A breakout occurs when the close price
        closes above this level.

        Args:
            data: List of OHLCV candles.

        Returns:
            HLBreakout if H-OLD breakout detected, None otherwise.
        """
        if len(data) < self.config.lookback + 2:
            return None

        # Lookback period: all candles except the most recent (current period)
        lookback_end = len(data) - 1  # Exclude current period candle
        lookback_start = max(0, lookback_end - self.config.lookback)

        # Find the highest high in the lookback period
        old_high = 0.0
        old_high_idx = -1
        for i in range(lookback_start, lookback_end):
            if data[i].high_price > old_high:
                old_high = data[i].high_price
                old_high_idx = i

        if old_high <= 0 or old_high_idx < 0:
            return None

        # Current close price
        current_close = data[-1].close_price
        current_timestamp = data[-1].timestamp

        # H-OLD breakout: bullish when close closes above OLD high
        if current_close > old_high:
            penetration_pct = (current_close - old_high) / old_high * 100
            if penetration_pct >= self.config.break_threshold_pct:
                # Find the swing low reference for context
                swing_low = self._find_swing_low(data, lookback_start, lookback_end)
                confidence = self._calculate_confidence(penetration_pct)
                return HLBreakout(
                    breakout_type="high_old",
                    price=current_close,
                    direction="long",
                    confidence=confidence,
                    timestamp=current_timestamp,
                    swing_high=old_high,
                    swing_low=swing_low,
                    level_price=old_high,
                    penetration_pct=penetration_pct,
                )

        return None

    def _detect_low_old_breakout(self, data: list[OHLCVData]) -> HLBreakout | None:
        """Detect L-OLD breakout: close closes below OLD low from lookback period.

        The OLD low is the lowest low from the lookback period (excluding
        the most recent candle). A breakout occurs when the close price
        closes below this level.

        Args:
            data: List of OHLCV candles.

        Returns:
            HLBreakout if L-OLD breakout detected, None otherwise.
        """
        if len(data) < self.config.lookback + 2:
            return None

        # Lookback period: all candles except the most recent (current period)
        lookback_end = len(data) - 1  # Exclude current period candle
        lookback_start = max(0, lookback_end - self.config.lookback)

        # Find the lowest low in the lookback period
        old_low = float("inf")
        old_low_idx = -1
        for i in range(lookback_start, lookback_end):
            if data[i].low_price < old_low:
                old_low = data[i].low_price
                old_low_idx = i

        if old_low == float("inf") or old_low_idx < 0:
            return None

        # Current close price
        current_close = data[-1].close_price
        current_timestamp = data[-1].timestamp

        # L-OLD breakout: bearish when close closes below OLD low
        if current_close < old_low:
            penetration_pct = (old_low - current_close) / old_low * 100
            if penetration_pct >= self.config.break_threshold_pct:
                # Find the swing high reference for context
                swing_high = self._find_swing_high(data, lookback_start, lookback_end)
                confidence = self._calculate_confidence(penetration_pct)
                return HLBreakout(
                    breakout_type="low_old",
                    price=current_close,
                    direction="short",
                    confidence=confidence,
                    timestamp=current_timestamp,
                    swing_high=swing_high,
                    swing_low=old_low,
                    level_price=old_low,
                    penetration_pct=penetration_pct,
                )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_swing_high(
        self, data: list[OHLCVData], start: int, end: int
    ) -> float | None:
        """Find the swing high within a range.

        A swing high is a local maximum surrounded by lower highs.

        Args:
            data: List of OHLCV candles.
            start: Start index (inclusive).
            end: End index (exclusive).

        Returns:
            The swing high price, or None if no swing high found.
        """
        if end - start < 3:
            return None

        swing_high = 0.0
        for i in range(start + 1, end - 1):
            prev_h = data[i - 1].high_price
            curr_h = data[i].high_price
            next_h = data[i + 1].high_price
            if curr_h > prev_h and curr_h > next_h and curr_h > swing_high:
                swing_high = curr_h

        return swing_high if swing_high > 0 else None

    def _find_swing_low(
        self, data: list[OHLCVData], start: int, end: int
    ) -> float | None:
        """Find the swing low within a range.

        A swing low is a local minimum surrounded by higher lows.

        Args:
            data: List of OHLCV candles.
            start: Start index (inclusive).
            end: End index (exclusive).

        Returns:
            The swing low price, or None if no swing low found.
        """
        if end - start < 3:
            return None

        swing_low = float("inf")
        for i in range(start + 1, end - 1):
            prev_l = data[i - 1].low_price
            curr_l = data[i].low_price
            next_l = data[i + 1].low_price
            if curr_l < prev_l and curr_l < next_l and curr_l < swing_low:
                swing_low = curr_l

        return swing_low if swing_low < float("inf") else None

    def _calculate_confidence(self, penetration_pct: float) -> float:
        """Calculate confidence based on penetration depth.

        Confidence ranges from 0.60 to 0.80 based on penetration depth.
        Deeper penetrations get slightly higher confidence.

        Args:
            penetration_pct: Penetration percentage beyond the level.

        Returns:
            Confidence score from 0.0 to 1.0.
        """
        # Base confidence: 0.60
        base = 0.60
        # Additional confidence from penetration: 0.0 to 0.20
        # Use 10x threshold as the point where we reach max confidence
        # This ensures meaningful differentiation: at threshold, ~0.62; at 5x, ~0.70; at 10x, ~0.80
        max_penetration = self.config.break_threshold_pct * 10
        if penetration_pct >= max_penetration:
            additional = 0.20
        else:
            additional = (penetration_pct / max_penetration) * 0.20

        confidence = base + additional
        return round(min(max(confidence, 0.60), 0.80), 4)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self) -> dict[str, Any]:
        """Return detector configuration metadata."""
        return {
            "name": "HLDetector",
            "description": "ICT H/L/H-OLD/L-OLD price structure breakout detector",
            "parameters": {
                "lookback": self.config.lookback,
                "break_threshold_pct": self.config.break_threshold_pct,
            },
        }
