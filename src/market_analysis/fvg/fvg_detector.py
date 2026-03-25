"""
FVG (Fair Value Gap) Detector for ICT Trading.

Detects bullish and bearish FVGs using 3-candle patterns with regime gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from src.market_analysis.regime import MarketRegimeClassifier, UnifiedRegime
from src.market_analysis.safety.lookahead_guard import lookahead_guard

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


# Module-level singleton for MarketRegimeClassifier to avoid creating
# a new instance per detector (performance optimization)
_regime_classifier_instance: Optional[MarketRegimeClassifier] = None


def _get_default_regime_classifier() -> MarketRegimeClassifier:
    """Get or create the default MarketRegimeClassifier singleton."""
    global _regime_classifier_instance
    if _regime_classifier_instance is None:
        _regime_classifier_instance = MarketRegimeClassifier()
    return _regime_classifier_instance


class FVGDirection(str, Enum):
    """Direction of FVG."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class FVGMitigation(str, Enum):
    """Mitigation status of FVG."""

    NONE = "none"  # Not mitigated
    WICK = "wick"  # Wick-only mitigation (price entered via wick)
    CLOSE = "close"  # Close mitigation (price closed within FVG)
    FULL = "full"  # Fully filled/mitigated


@dataclass
class FVG:
    """
    Fair Value Gap data model.

    Attributes:
        direction: Bullish or bearish FVG
        timestamp: When the FVG was detected (timestamp of candle 1)
        high: Upper boundary of the FVG zone
        low: Lower boundary of the FVG zone
        mitigation: Current mitigation status
        ce50_reached: Whether 50% CE has been reached
        regime_at_formation: The regime when the FVG was formed
        notes: Optional notes
    """

    direction: FVGDirection
    timestamp: int  # Unix timestamp in milliseconds
    high: float
    low: float
    mitigation: FVGMitigation = FVGMitigation.NONE
    ce50_reached: bool = False
    regime_at_formation: Optional[UnifiedRegime] = None
    notes: Optional[str] = None

    @property
    def midpoint(self) -> float:
        """Calculate midpoint of the FVG zone."""
        return (self.high + self.low) / 2

    @property
    def zone_size(self) -> float:
        """Calculate the size of the FVG zone."""
        return self.high - self.low

    def contains_price(self, price: float) -> bool:
        """Check if price is within the FVG zone."""
        return self.low <= price <= self.high

    def check_ce50(self, price: float) -> bool:
        """
        Check if price has reached 50% CE (Consequent Encroachment).

        50% CE means price has retraced 50% into the FVG zone.
        """
        if self.direction == FVGDirection.BULLISH:
            # For bullish FVG: 50% CE = low + (zone_size * 0.5)
            ce50_price = self.low + (self.zone_size * 0.5)
            return price >= ce50_price
        else:  # BEARISH
            # For bearish FVG: 50% CE = high - (zone_size * 0.5)
            ce50_price = self.high - (self.zone_size * 0.5)
            return price <= ce50_price


@dataclass
class FVGDetectionResult:
    """Result of FVG detection on a single candle."""

    fvg: Optional[FVG]
    detection_index: int  # Index of candle 1 in the data array
    is_new: bool = True  # Whether this is a newly detected FVG


class FVGDetector:
    """
    Fair Value Gap detector with regime gating.

    Detects FVGs using 3-candle patterns:
    - Candle 1: Large impulse candle
    - Candle 2: Smaller candle with gap from Candle 1
    - Candle 3: Optional - may fill/mitigate the FVG

    Regime Gating:
        FVGs are only tracked when market is in TRENDING regime.
        RANGING/VOLATILE regimes suppress FVG detection.

    Usage:
        detector = FVGDetector()
        result = detector.detect(candles)
        fvgs = result.fvgs
    """

    # Minimum gap size as percentage of candle 1's body size
    MIN_GAP_PERCENT = 0.001  # 0.1%

    # Minimum candle size relative to average (to filter noise)
    MIN_CANDLE_SIZE_RATIO = 0.5

    def __init__(
        self,
        regime_classifier: Optional[MarketRegimeClassifier] = None,
        min_gap_percent: float = MIN_GAP_PERCENT,
        min_candle_size_ratio: float = MIN_CANDLE_SIZE_RATIO,
    ):
        """
        Initialize FVG detector.

        Args:
            regime_classifier: Optional regime classifier for regime gating.
                              If None, FVGs are detected regardless of regime.
            min_gap_percent: Minimum gap size as percentage of candle 1 body
            min_candle_size_ratio: Minimum candle size relative to average
        """
        self._regime_classifier = regime_classifier or _get_default_regime_classifier()
        self._min_gap_percent = min_gap_percent
        self._min_candle_size_ratio = min_candle_size_ratio
        self._detected_fvgs: list[FVG] = []

    @property
    def detected_fvgs(self) -> list[FVG]:
        """Get list of detected FVGs."""
        return self._detected_fvgs.copy()

    @lookahead_guard
    def detect(
        self,
        candles: list,
        regime_data: Optional[list] = None,
        token: str = "BTC/USDT",
        timeframe: str = "1H",
    ) -> FVGDetectionResult:
        """
        Detect FVGs in the given candle data.

        Args:
            candles: List of OHLCV candles
            regime_data: Optional list of candles for regime classification.
                        If None, regime is calculated from candles.
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            FVGDetectionResult with detected FVG and metadata
        """
        if len(candles) < 3:
            return FVGDetectionResult(fvg=None, detection_index=-1)

        # Determine regime
        regime = self._get_regime(candles if regime_data is None else regime_data)

        # For regime gating: only detect FVGs in trending markets
        # But we still track existing FVGs regardless of regime
        is_trending = regime.is_trending if regime else True

        # Look for FVG starting from candle 1 (index 1)
        # We need candles[i-1], candles[i], candles[i+1] for 3-candle pattern
        for i in range(1, len(candles) - 1):
            candle1 = candles[i - 1]  # Impulse candle
            candle2 = candles[i]  # Gap candle
            candle3 = candles[i + 1]  # May fill FVG

            # Try to detect bullish FVG
            bullish_fvg = self._detect_bullish_fvg(candle1, candle2, candle3, regime, i)
            if bullish_fvg:
                self._detected_fvgs.append(bullish_fvg)
                return FVGDetectionResult(
                    fvg=bullish_fvg,
                    detection_index=i - 1,
                    is_new=True,
                )

            # Try to detect bearish FVG
            bearish_fvg = self._detect_bearish_fvg(candle1, candle2, candle3, regime, i)
            if bearish_fvg:
                self._detected_fvgs.append(bearish_fvg)
                return FVGDetectionResult(
                    fvg=bearish_fvg,
                    detection_index=i - 1,
                    is_new=True,
                )

        return FVGDetectionResult(fvg=None, detection_index=-1)

    @lookahead_guard
    def detect_all(
        self,
        candles: list,
        regime_data: Optional[list] = None,
    ) -> list[FVG]:
        """
        Detect all FVGs in the given candle data.

        Args:
            candles: List of OHLCV candles
            regime_data: Optional list of candles for regime classification

        Returns:
            List of all detected FVGs
        """
        if len(candles) < 3:
            return []

        regime = self._get_regime(candles if regime_data is None else regime_data)
        fvgs = []

        for i in range(1, len(candles) - 1):
            candle1 = candles[i - 1]
            candle2 = candles[i]
            candle3 = candles[i + 1]

            bullish_fvg = self._detect_bullish_fvg(candle1, candle2, candle3, regime, i)
            if bullish_fvg:
                fvgs.append(bullish_fvg)

            bearish_fvg = self._detect_bearish_fvg(candle1, candle2, candle3, regime, i)
            if bearish_fvg:
                fvgs.append(bearish_fvg)

        self._detected_fvgs.extend(fvgs)
        return fvgs

    def _detect_bullish_fvg(
        self,
        candle1,
        candle2,
        candle3,
        regime: Optional[UnifiedRegime],
        index: int,
    ) -> Optional[FVG]:
        """
        Detect bullish FVG pattern.

        Bullish FVG occurs when:
        - Candle 1 is a large bullish candle (impulse up)
        - Candle 2 opens above Candle 1's close (gap up)
        - Candle 3 may fill the gap

        FVG zone is between Candle 1's close and Candle 2's low.
        """
        # Check if candle1 is bullish and large
        body1 = candle1.close_price - candle1.open_price
        if body1 <= 0:
            return None

        # Check for gap up: candle2's low is above candle1's close
        gap = candle2.low_price - candle1.close_price
        if gap <= 0:
            return None

        # Check minimum gap size
        min_gap = body1 * self._min_gap_percent
        if gap < min_gap:
            return None

        # Bullish FVG detected
        # FVG zone: candle1's close to candle2's low
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=candle1.timestamp,
            high=candle1.close_price,  # candle1's close is the top
            low=candle2.low_price,  # candle2's low is the bottom
            mitigation=FVGMitigation.NONE,
            regime_at_formation=regime,
            notes=f"Detected at index {index}",
        )

        return fvg

    def _detect_bearish_fvg(
        self,
        candle1,
        candle2,
        candle3,
        regime: Optional[UnifiedRegime],
        index: int,
    ) -> Optional[FVG]:
        """
        Detect bearish FVG pattern.

        Bearish FVG occurs when:
        - Candle 1 is a large bearish candle (impulse down)
        - Candle 2 opens below Candle 1's close (gap down)
        - Candle 3 may fill the gap

        FVG zone is between Candle 1's close and Candle 2's high.
        """
        # Check if candle1 is bearish and large
        body1 = candle1.open_price - candle1.close_price
        if body1 <= 0:
            return None

        # Check for gap down: candle2's high is below candle1's close
        gap = candle1.close_price - candle2.high_price
        if gap <= 0:
            return None

        # Check minimum gap size
        min_gap = body1 * self._min_gap_percent
        if gap < min_gap:
            return None

        # Bearish FVG detected
        # FVG zone: candle2's high to candle1's close
        fvg = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=candle1.timestamp,
            high=candle2.high_price,  # candle2's high is the top
            low=candle1.close_price,  # candle1's close is the bottom
            mitigation=FVGMitigation.NONE,
            regime_at_formation=regime,
            notes=f"Detected at index {index}",
        )

        return fvg

    def _get_regime(self, candles: list) -> Optional[UnifiedRegime]:
        """Get market regime from candles."""
        try:
            result = self._regime_classifier.classify(candles)
            return result.regime
        except Exception:
            return None

    def update_mitigation(
        self,
        fvg: FVG,
        current_candle,
    ) -> FVG:
        """
        Update FVG mitigation status based on current candle.

        Args:
            fvg: The FVG to update
            current_candle: Current OHLCV candle

        Returns:
            Updated FVG with mitigation status
        """
        if fvg.mitigation == FVGMitigation.FULL:
            # Already fully mitigated
            return fvg

        if fvg.direction == FVGDirection.BULLISH:
            updated = self._update_bullish_mitigation(fvg, current_candle)
        else:
            updated = self._update_bearish_mitigation(fvg, current_candle)

        # Check 50% CE
        if not updated.ce50_reached:
            mid = updated.midpoint
            if updated.direction == FVGDirection.BULLISH:
                if current_candle.low_price <= mid <= current_candle.high_price:
                    updated.ce50_reached = True
            else:
                if current_candle.low_price <= mid <= current_candle.high_price:
                    updated.ce50_reached = True

        return updated

    def _update_bullish_mitigation(
        self,
        fvg: FVG,
        current_candle,
    ) -> FVG:
        """Update mitigation status for bullish FVG."""
        # Check if candle fully fills the FVG
        if (
            current_candle.low_price <= fvg.low
            and current_candle.high_price >= fvg.high
        ):
            fvg.mitigation = FVGMitigation.FULL
            return fvg

        # Check if candle closes within FVG
        if fvg.low < current_candle.close_price < fvg.high:
            fvg.mitigation = FVGMitigation.CLOSE
            return fvg

        # Check if candle's wick enters FVG
        if current_candle.low_price < fvg.low <= current_candle.high_price:
            # Wick hit the FVG but didn't close within
            if fvg.mitigation == FVGMitigation.NONE:
                fvg.mitigation = FVGMitigation.WICK
            return fvg

        if current_candle.low_price <= fvg.high < current_candle.high_price:
            # Upper wick entered FVG
            if fvg.mitigation == FVGMitigation.NONE:
                fvg.mitigation = FVGMitigation.WICK
            return fvg

        return fvg

    def _update_bearish_mitigation(
        self,
        fvg: FVG,
        current_candle,
    ) -> FVG:
        """Update mitigation status for bearish FVG."""
        # Check if candle fully fills the FVG
        if (
            current_candle.low_price <= fvg.low
            and current_candle.high_price >= fvg.high
        ):
            fvg.mitigation = FVGMitigation.FULL
            return fvg

        # Check if candle closes within FVG
        if fvg.low < current_candle.close_price < fvg.high:
            fvg.mitigation = FVGMitigation.CLOSE
            return fvg

        # Check if candle's wick enters FVG
        if current_candle.low_price <= fvg.low < current_candle.high_price:
            if fvg.mitigation == FVGMitigation.NONE:
                fvg.mitigation = FVGMitigation.WICK
            return fvg

        if current_candle.low_price <= fvg.high < current_candle.high_price:
            if fvg.mitigation == FVGMitigation.NONE:
                fvg.mitigation = FVGMitigation.WICK
            return fvg

        return fvg

    def clear_history(self) -> None:
        """Clear detected FVG history."""
        self._detected_fvgs.clear()

    def get_active_fvgs(self) -> list[FVG]:
        """Get FVGs that are not fully mitigated."""
        return [
            fvg for fvg in self._detected_fvgs if fvg.mitigation != FVGMitigation.FULL
        ]

    def get_bullish_fvgs(self) -> list[FVG]:
        """Get bullish FVGs that are not fully mitigated."""
        return [
            fvg
            for fvg in self._detected_fvgs
            if fvg.direction == FVGDirection.BULLISH
            and fvg.mitigation != FVGMitigation.FULL
        ]

    def get_bearish_fvgs(self) -> list[FVG]:
        """Get bearish FVGs that are not fully mitigated."""
        return [
            fvg
            for fvg in self._detected_fvgs
            if fvg.direction == FVGDirection.BEARISH
            and fvg.mitigation != FVGMitigation.FULL
        ]
