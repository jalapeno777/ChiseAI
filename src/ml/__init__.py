"""ML Optimization Suite for ChiseAI.

This package provides machine learning optimization capabilities:

- walk_forward: Walk-forward evaluation framework for robust strategy validation
- hyperopt: Hyperparameter optimization using genetic algorithms and Bayesian optimization
- scheduler: Automated optimization scheduling with volatility adaptation
- feedback: ML feedback loop for prediction-outcome analysis and model improvement
- training: Training data schema and storage for ML model retraining
- models: Model registry for versioning, storage, and retrieval

Usage:
    import sys
    sys.path.insert(0, 'src')
    from ml import (
        WalkForwardEvaluator,
        WalkForwardConfig,
        HyperparameterOptimizer,
        OptimizationConfig,
        OptimizationScheduler,
        ScheduleConfig,
        FeedbackOrchestrator,
        FeedbackAnalyzer,
        ModelUpdater,
        TrainingSample,
        TrainingDataset,
        ModelRegistry,
        ModelMetadata,
        ModelVersion,
    )
"""

from __future__ import annotations

from ml.feedback import (
    AccuracyBySignalType,
    AccuracyByTimeframe,
    AnalysisConfig,
    DriftIndicator,
    DriftSeverity,
    FeatureImportanceChange,
    FeedbackAnalysisReport,
    FeedbackAnalyzer,
    FeedbackOrchestrator,
    LoopIterationResult,
    LoopStatus,
    MarketRegime,
    MatchBatchResult,
    MatchConfidence,
    MatchConfig,
    MatchStatus,
    ModelType,
    ModelUpdater,
    ModelVersion,
    OrchestratorConfig,
    PredictionOutcomeMatch,
    PredictionOutcomeMatcher,
    RegimePerformance,
    TemporalBoundary,
    TemporalSafetyMode,
    UpdateConfig,
    UpdateResult,
    UpdateStatus,
    UpdateStrategy,
)

# Import from absolute paths (requires src/ in sys.path)
# Note: hyperopt.OptimizationRecord and scheduler.OptimizationRecord are different classes
from ml.hyperopt import (
    BaseOptimizer,
    BayesianOptimizer,
    GeneticOptimizer,
    HyperparameterOptimizer,
    OptimizationMethod,
    OptimizationResult,
    OptimizationTrial,
    ParameterConstraint,
    ParameterType,
)
from ml.hyperopt import (
    OptimizationConfig as HyperoptConfig,
)
from ml.scheduler import (
    JobStatus,
    OptimizationScheduler,
    OptimizationTask,
    ParameterDelta,
    ScheduleConfig,
    ScheduledJob,
    ScheduleFrequency,
    VolatilityMonitor,
    VolatilityRegime,
)
from ml.models import (
    FilesystemBackend,
    ModelMetadata,
    ModelRegistry,
    ModelRegistryFactory,
    ModelVersion,
    S3Backend,
    SemanticVersion,
    StorageBackend,
)
from ml.training import (
    FEATURE_GROUPS,
    FEATURE_SPECS,
    DatasetMetadata,
    FeatureSpec,
    FeatureType,
    FeatureValidator,
    SchemaVersion,
    SchemaVersionManager,
    StorageFormatManager,
    TrainingDataset,
    TrainingSample,
    TrendState,
)
from ml.walk_forward import (
    AggregatedMetrics,
    LookAheadBiasCheck,
    TemporalWindow,
    WalkForwardConfig,
    WalkForwardEvaluator,
    WalkForwardResult,
    WindowMetrics,
    WindowStatus,
)

__all__ = [
    # Walk-forward
    "WalkForwardEvaluator",
    "WalkForwardConfig",
    "WalkForwardResult",
    "TemporalWindow",
    "WindowMetrics",
    "AggregatedMetrics",
    "WindowStatus",
    "LookAheadBiasCheck",
    # Hyperopt
    "HyperparameterOptimizer",
    "HyperoptConfig",  # Renamed to avoid conflict
    "OptimizationMethod",
    "OptimizationResult",
    "OptimizationTrial",
    "ParameterConstraint",
    "ParameterType",
    "BaseOptimizer",
    "GeneticOptimizer",
    "BayesianOptimizer",
    # Scheduler
    "OptimizationScheduler",
    "ScheduleConfig",
    "ScheduleFrequency",
    "ScheduledJob",
    "ParameterDelta",
    "JobStatus",
    "VolatilityMonitor",
    "VolatilityRegime",
    "OptimizationTask",
    # Feedback
    "FeedbackOrchestrator",
    "OrchestratorConfig",
    "LoopStatus",
    "LoopIterationResult",
    "TemporalBoundary",
    "TemporalSafetyMode",
    "PredictionOutcomeMatcher",
    "MatchConfig",
    "MatchStatus",
    "MatchConfidence",
    "PredictionOutcomeMatch",
    "MatchBatchResult",
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
    "ModelUpdater",
    "UpdateConfig",
    "UpdateStrategy",
    "UpdateStatus",
    "ModelType",
    "ModelVersion",
    "UpdateResult",
    # Training
    "TrainingSample",
    "TrainingDataset",
    "FeatureSpec",
    "FeatureType",
    "FeatureValidator",
    "FEATURE_SPECS",
    "FEATURE_GROUPS",
    "TrendState",
    "StorageFormatManager",
    "DatasetMetadata",
    "SchemaVersion",
    "SchemaVersionManager",
    # Models
    "ModelRegistry",
    "ModelRegistryFactory",
    "FilesystemBackend",
    "S3Backend",
    "StorageBackend",
    "SemanticVersion",
]
