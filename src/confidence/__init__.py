"""Confidence scoring and calibration module.

Provides ECE (Expected Calibration Error) calculation, historical tracking,
and threshold calibration for trading signal confidence scores.
"""

from confidence.ece import (
    ECEBin,
    ECECalculator,
    ECEResult,
    SignalType,
    calculate_ece,
)
from confidence.ece_tracker import (
    ECEHistoryPoint,
    ECEHistoryTracker,
    ECETrend,
)

__all__ = [
    # ECE calculation
    "ECECalculator",
    "ECEResult",
    "ECEBin",
    "SignalType",
    "calculate_ece",
    # ECE tracking
    "ECEHistoryTracker",
    "ECEHistoryPoint",
    "ECETrend",
]
