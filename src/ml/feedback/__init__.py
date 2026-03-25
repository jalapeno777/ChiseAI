"""ML Feedback Loop Module for ChiseAI.

This module provides the ML feedback loop infrastructure for analyzing
predictions vs outcomes and improving model performance over time.

Components:
- matcher: Prediction-outcome matching with time-window support
- analyzer: Performance analysis and drift detection
- updater: Model updates with version control
- orchestrator: Full feedback loop coordination
- outcome_capture: Real-time trade outcome capture from exchange fills
- bybit_fill_listener: Bybit WebSocket fill event listener
- ict_signal_tracker: ICT signal prediction tracking (CVD, FVG, Order Block)
- ict_matcher: ICT prediction-outcome matching

Usage:
    from ml.feedback import (
        PredictionOutcomeMatcher,
        FeedbackAnalyzer,
        ModelUpdater,
        FeedbackOrchestrator,
        OutcomeCaptureService,
        BybitFillListener,
    )

    # Run complete feedback loop
    orchestrator = FeedbackOrchestrator()
    result = await orchestrator.run_feedback_loop()
"""

from __future__ import annotations

# Analyzer components
from ml.feedback.analyzer import (
    AccuracyBySignalType,
    AccuracyByTimeframe,
    AnalysisConfig,
    DriftIndicator,
    DriftSeverity,
    FeatureImportanceChange,
    FeedbackAnalysisReport,
    FeedbackAnalyzer,
    MarketRegime,
    RegimePerformance,
)

# ICT Signal Tracker (ST-ICT-017)
from ml.feedback.ict_signal_tracker import (
    ICTSignalDirection,
    ICTSignalRecord,
    ICTSignalTracker,
    get_ict_tracker,
)

# Matcher components
from ml.feedback.matcher import (
    MatchBatchResult,
    MatchConfidence,
    MatchConfig,
    MatchStatus,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
)

# Orchestrator components
from ml.feedback.orchestrator import (
    FeedbackOrchestrator,
    LoopIterationResult,
    LoopStatus,
    OrchestratorConfig,
    TemporalBoundary,
    TemporalSafetyMode,
)

# ICT Prediction-Outcome Matcher (ST-ICT-017)
from ml.feedback.prediction_outcome_matcher_ict import (
    ICTMatchConfidence,
    ICTMatchConfig,
    ICTMatchStatus,
    ICTPredictionMatch,
    ICTPredictionOutcomeMatcher,
    ICTSignalMetrics,
    get_ict_matcher,
)

# Signal Outcome Matcher (ST-LAUNCH-006)
from ml.feedback.signal_outcome_matcher import (
    DEFAULT_MATCH_WINDOWS,
    MatcherMetrics,
    MatchMetadata,
    SignalMatcherConfig,
    SignalOutcomeMatcher,
)

# Updater components
from ml.feedback.updater import (
    ModelType,
    ModelUpdater,
    ModelVersion,
    UpdateConfig,
    UpdateResult,
    UpdateStatus,
    UpdateStrategy,
)

__all__ = [
    # Outcome Capture (ST-LAUNCH-018)
    "OutcomeCaptureService",
    "OutcomeCaptureConfig",
    "CaptureMetrics",
    "BybitFillListener",
    "BybitListenerConfig",
    "ConnectionState",
    # Signal Outcome Matcher (ST-LAUNCH-006)
    "SignalOutcomeMatcher",
    "SignalMatcherConfig",
    "MatcherMetrics",
    "MatchMetadata",
    "DEFAULT_MATCH_WINDOWS",
    # ICT Signal Tracker (ST-ICT-017)
    "ICTSignalTracker",
    "ICTSignalRecord",
    "ICTSignalDirection",
    "get_ict_tracker",
    # ICT Prediction-Outcome Matcher (ST-ICT-017)
    "ICTPredictionOutcomeMatcher",
    "ICTMatchConfig",
    "ICTMatchStatus",
    "ICTMatchConfidence",
    "ICTPredictionMatch",
    "ICTSignalMetrics",
    "get_ict_matcher",
    # Matcher
    "PredictionOutcomeMatcher",
    "MatchConfig",
    "MatchStatus",
    "MatchConfidence",
    "PredictionOutcomeMatch",
    "MatchBatchResult",
    # Analyzer
    "FeedbackAnalyzer",
    "AnalysisConfig",
    "MarketRegime",
    "DriftSeverity",
    "AccuracyBySignalType",
    "AccuracyByTimeframe",
    "RegimePerformance",
    "FeatureImportanceChange",
    "DriftIndicator",
    "FeedbackAnalysisReport",
    # Updater
    "ModelUpdater",
    "UpdateConfig",
    "UpdateStrategy",
    "UpdateStatus",
    "ModelType",
    "ModelVersion",
    "UpdateResult",
    # Orchestrator
    "FeedbackOrchestrator",
    "OrchestratorConfig",
    "LoopStatus",
    "LoopIterationResult",
    "TemporalBoundary",
    "TemporalSafetyMode",
]
