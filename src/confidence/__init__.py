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
from confidence.ece_scheduler import (
    ECEScheduler,
    ECEUpdateResult,
    InMemoryPredictionOutcomeStore,
    PredictionOutcomePair,
    PredictionOutcomeStore,
    SchedulerConfig,
    create_default_scheduler,
)
from confidence.ece_tracker import (
    ECEHistoryPoint,
    ECEHistoryTracker,
    ECETrend,
)
from confidence.threshold import (
    CalibrationResult,
    ModeSwitchRecord,
    ThresholdAdjustment,
    ThresholdCalibrator,
    ThresholdConfig,
    ThresholdManager,
    ThresholdMode,
)
from confidence.threshold_tracker import (
    InfluxDBThresholdTracker,
    InMemoryThresholdTracker,
    ThresholdHistoryTracker,
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
    # Threshold calibration
    "ThresholdMode",
    "ThresholdConfig",
    "ThresholdAdjustment",
    "CalibrationResult",
    "ModeSwitchRecord",
    "ThresholdCalibrator",
    "ThresholdManager",
    # Threshold tracking
    "ThresholdHistoryTracker",
    "InMemoryThresholdTracker",
    "InfluxDBThresholdTracker",
    # ECE scheduler
    "ECEScheduler",
    "SchedulerConfig",
    "ECEUpdateResult",
    "PredictionOutcomeStore",
    "PredictionOutcomePair",
    "InMemoryPredictionOutcomeStore",
    "create_default_scheduler",
]
