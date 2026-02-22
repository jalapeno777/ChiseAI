"""ML Feedback Loop Module for ChiseAI.

This module provides the ML feedback loop infrastructure for analyzing
predictions vs outcomes and improving model performance over time.

Components:
- matcher: Prediction-outcome matching with time-window support
- analyzer: Performance analysis and drift detection
- updater: Model updates with version control
- orchestrator: Full feedback loop coordination

Usage:
    from ml.feedback import (
        PredictionOutcomeMatcher,
        FeedbackAnalyzer,
        ModelUpdater,
        FeedbackOrchestrator,
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
