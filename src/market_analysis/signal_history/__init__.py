"""Signal history package.

Provides signal tracking and accuracy calculation for performance analysis.

Exports:
    SignalTracker: Main signal tracking class
    PredictionAccuracyCalculator: Accuracy calculation per signal type and confidence
    AccuracyMetrics: Dataclass for accuracy metrics
    AccuracyReport: Comprehensive accuracy report
    get_confidence_bucket: Helper to get confidence bucket
    DEFAULT_CONFIDENCE_BUCKETS: Default confidence bucket definitions
"""

from market_analysis.signal_history.accuracy_calculator import (
    DEFAULT_CONFIDENCE_BUCKETS,
    AccuracyMetrics,
    AccuracyReport,
    PredictionAccuracyCalculator,
    get_confidence_bucket,
)
from market_analysis.signal_history.tracker import SignalTracker

__all__ = [
    # Tracker
    "SignalTracker",
    # Accuracy calculation
    "PredictionAccuracyCalculator",
    "AccuracyMetrics",
    "AccuracyReport",
    "get_confidence_bucket",
    "DEFAULT_CONFIDENCE_BUCKETS",
]
