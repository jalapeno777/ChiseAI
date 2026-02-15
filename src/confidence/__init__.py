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
    InMemoryThresholdTracker,
    InfluxDBThresholdTracker,
    ThresholdHistoryTracker,
)
from confidence.ece_scheduler import (
    ECEUpdateResult,
    ECEScheduler,
    InMemoryPredictionOutcomeStore,
    PredictionOutcomePair,
    PredictionOutcomeStore,
    SchedulerConfig,
    create_default_scheduler,
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
