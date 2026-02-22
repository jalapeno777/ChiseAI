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

# Matcher components
from ml.feedback.matcher import (
    MatchBatchResult,
    MatchConfig,
    MatchConfidence,
    MatchStatus,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
)

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

# Orchestrator components
from ml.feedback.orchestrator import (
    FeedbackOrchestrator,
    LoopIterationResult,
    LoopStatus,
    OrchestratorConfig,
    TemporalBoundary,
    TemporalSafetyMode,
)

__all__ = [
    # Outcome Capture (ST-LAUNCH-018)
    "OutcomeCaptureService",
    "OutcomeCaptureConfig",
    "CaptureMetrics",
    "BybitFillListener",
    "BybitListenerConfig",
    "ConnectionState",
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
