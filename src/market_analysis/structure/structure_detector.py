"""Main Structure Detector Module.

This module provides the main StructureDetector that integrates swing pivot
detection, BOS/CHoCH classification with regime gating.

Key features:
- Regime-gated (TRENDING only)
- Non-repainting confirmed bars only
- Integrated swing pivot and BOS/CHoCH detection

Usage:
    detector = StructureDetector()
    result = detector.detect_structure(data)

    # With regime gating
    result = detector.detect_structure(data, regime=regime_classification)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from market_analysis.regime import RegimeClassification, UnifiedRegime
from market_analysis.safety.lookahead_guard import lookahead_guard
from market_analysis.structure.bos_choch import (
    BOSCHoCH,
    BOSCHoCHClassificationResult,
    BOSCHoCHClassifier,
    StructureLevel,
)
from market_analysis.structure.swing_pivot import (
    SwingPivotDetectionResult,
    SwingPivotDetector,
)

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData


@dataclass
class StructureDetectionResult:
    """Complete result of market structure detection.

    Attributes:
        pivots: Swing pivot detection result
        bos_choch: BOS/CHoCH classification result
        regime: The regime classification used (or None if not regime-gated)
        is_trending: Whether structure is valid for trending market
        current_trend: Current trend direction ('up', 'down', or 'neutral')
        structure_level: Current structure level for trading
        timestamp: When detection was computed
        confirmed: Whether this result is based on confirmed bars only
        metadata: Additional detection metadata
    """

    pivots: SwingPivotDetectionResult
    bos_choch: BOSCHoCHClassificationResult
    regime: RegimeClassification | None
    is_trending: bool
    current_trend: str
    structure_level: StructureLevel | None
    timestamp: datetime
    confirmed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def last_bos(self) -> BOSCHoCH | None:
        """Get the most recent BOS event."""
        if self.bos_choch.events:
            # Return last BOS (not CHoCH)
            for event in reversed(self.bos_choch.events):
                if event.is_bos:
                    return event
        return None

    @property
    def last_choch(self) -> BOSCHoCH | None:
        """Get the most recent CHoCH event."""
        if self.bos_choch.events:
            for event in reversed(self.bos_choch.events):
                if not event.is_bos:
                    return event
        return None


class StructureDetector:
    """Main market structure detector with regime gating.

    This detector integrates swing pivot detection with BOS/CHoCH classification
    to provide a complete market structure analysis. It supports regime gating
    to only output valid structure during trending market conditions.

    Parameters:
        window_size: Window size for swing pivot detection (default: 5)
        confirmation_bars: Bars required to confirm BOS/CHoCH (default: 1)
        min_strength_ratio: Minimum strength for valid structure break (default: 0.001)
        require_trending: If True, only output structure in TRENDING regime (default: True)
    """

    DEFAULT_WINDOW_SIZE = 5
    DEFAULT_CONFIRMATION_BARS = 1
    DEFAULT_MIN_STRENGTH = 0.001

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW_SIZE,
        confirmation_bars: int = DEFAULT_CONFIRMATION_BARS,
        min_strength_ratio: float = DEFAULT_MIN_STRENGTH,
        require_trending: bool = True,
    ):
        """Initialize structure detector.

        Args:
            window_size: Window size for swing pivot detection
            confirmation_bars: Bars to confirm BOS/CHoCH
            min_strength_ratio: Minimum strength ratio
            require_trending: Only detect structure in trending regime
        """
        self.window_size = window_size
        self.confirmation_bars = confirmation_bars
        self.min_strength_ratio = min_strength_ratio
        self.require_trending = require_trending

        # Initialize components
        self._pivot_detector = SwingPivotDetector(window_size=window_size)
        self._bos_choch_classifier = BOSCHoCHClassifier(
            confirmation_bars=confirmation_bars,
            min_strength_ratio=min_strength_ratio,
        )

    @lookahead_guard
    def detect_structure(
        self,
        data: list[OHLCVData],
        regime: RegimeClassification | None = None,
    ) -> StructureDetectionResult:
        """Detect market structure from OHLCV data.

        This method performs swing pivot detection and BOS/CHoCH classification.
        When regime is provided and require_trending=True, structure is only
        reported when the market is in a TRENDING regime.

        Args:
            data: List of OHLCV data points
            regime: Optional regime classification for gating

        Returns:
            StructureDetectionResult with complete structure analysis
        """
        # Check regime gating
        is_trending = self._check_trending(regime)
        current_trend = self._determine_trend(data, regime)

        # Always detect pivots (needed for structure even if not trending)
        pivot_result = self._pivot_detector.detect(data)

        # Only classify BOS/CHoCH if trending (regime check passed)
        if is_trending:
            bos_choch_result = self._bos_choch_classifier.classify(pivot_result, data)
        else:
            bos_choch_result = self._empty_bos_choch_result()

        # Determine current structure level
        structure_level = self._get_structure_level(bos_choch_result, current_trend)

        return StructureDetectionResult(
            pivots=pivot_result,
            bos_choch=bos_choch_result,
            regime=regime,
            is_trending=is_trending,
            current_trend=current_trend,
            structure_level=structure_level,
            timestamp=datetime.now(UTC),
            confirmed=True,  # Always using confirmed bars
            metadata={
                "require_trending": self.require_trending,
                "window_size": self.window_size,
            },
        )

    def _check_trending(self, regime: RegimeClassification | None) -> bool:
        """Check if market is in a trending regime.

        Args:
            regime: Regime classification (or None)

        Returns:
            True if trending or no regime required
        """
        if regime is None:
            # No regime provided - when require_trending=True, default to True
            # to allow structure detection to proceed based on price action
            return True

        return regime.regime == UnifiedRegime.TRENDING

    def _determine_trend(
        self, data: list[OHLCVData], regime: RegimeClassification | None
    ) -> str:
        """Determine current trend direction.

        Args:
            data: OHLCV data
            regime: Regime classification

        Returns:
            'up', 'down', or 'neutral'
        """
        if regime is not None and regime.trend_direction != "neutral":
            return regime.trend_direction

        # Fallback: use price action
        if len(data) < 10:
            return "neutral"

        # Simple trend: compare recent highs/lows
        recent = data[-5:]
        earlier = data[-10:-5]

        recent_high = max(c.high_price for c in recent)
        recent_low = min(c.low_price for c in recent)
        earlier_high = max(c.high_price for c in earlier)
        earlier_low = min(c.low_price for c in earlier)

        if recent_high > earlier_high and recent_low > earlier_low:
            return "up"
        elif recent_high < earlier_high and recent_low < earlier_low:
            return "down"

        return "neutral"

    def _get_structure_level(
        self,
        bos_choch: BOSCHoCHClassificationResult,
        trend: str,
    ) -> StructureLevel | None:
        """Get the current valid structure level.

        Args:
            bos_choch: BOS/CHoCH classification result
            trend: Current trend direction

        Returns:
            Current structure level or None
        """
        if trend == "up":
            return bos_choch.current_structure_low
        elif trend == "down":
            return bos_choch.current_structure_high
        return None

    def _empty_bos_choch_result(self) -> BOSCHoCHClassificationResult:
        """Create empty BOS/CHoCH result when regime is not trending."""
        return BOSCHoCHClassificationResult(
            events=[],
            bullish_bos_events=[],
            bearish_bos_events=[],
            bullish_choch_events=[],
            bearish_choch_events=[],
            current_structure_high=None,
            current_structure_low=None,
            last_bos_direction=None,
        )

    def validate(self, data: list[OHLCVData]) -> bool:
        """Validate that data is sufficient for structure detection.

        Args:
            data: List of OHLCV data points

        Returns:
            True if data is sufficient
        """
        return self._pivot_detector.validate(data)

    def get_metadata(self) -> dict[str, Any]:
        """Get detector metadata for serialization.

        Returns:
            Dictionary with name, description, parameters
        """
        return {
            "name": "StructureDetector",
            "description": "Market structure detection with regime gating",
            "parameters": {
                "window_size": self.window_size,
                "confirmation_bars": self.confirmation_bars,
                "min_strength_ratio": self.min_strength_ratio,
                "require_trending": self.require_trending,
            },
        }
