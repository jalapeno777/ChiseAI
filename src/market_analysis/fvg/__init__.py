"""
Fair Value Gap (FVG) Module for ICT Trading.

This module provides FVG detection, tracking, and mitigation analysis.

FVG Pattern:
    A 3-candle pattern consisting of:
    - Candle 1: Large impulse candle
    - Candle 2: Smaller candle with a gap from Candle 1
    - Candle 3: May fill/mitigate the FVG

Bullish FVG:
    Candle 1 closes higher, Candle 2 opens with a gap up from Candle 1's close.
    The FVG zone is between Candle 1's close and Candle 2's low.

Bearish FVG:
    Candle 1 closes lower, Candle 2 opens with a gap down from Candle 1's close.
    The FVG zone is between Candle 1's close and Candle 2's high.

Mitigation Types:
    - Wick Mitigation: Price enters FVG via wick only
    - Close Mitigation: Price closes within FVG
    - 50% CE: Price has retraced 50% into the FVG

Usage:
    from src.market_analysis.fvg import FVGDetector, MitigationTracker

    detector = FVGDetector()
    fvgs = detector.detect(candles)

    tracker = MitigationTracker()
    tracker.check_mitigation(fvg, current_candle)
"""

from src.market_analysis.fvg.fvg_detector import (
    FVGDetector,
    FVG,
    FVGDirection,
    FVGMitigation,
)
from src.market_analysis.fvg.mitigation_tracker import (
    MitigationTracker,
    MitigationType,
)

__all__ = [
    "FVGDetector",
    "FVG",
    "FVGDirection",
    "FVGMitigation",
    "MitigationTracker",
    "MitigationType",
]
