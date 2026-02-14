"""ML Optimization Suite for ChiseAI.

This package provides machine learning optimization capabilities:

- walk_forward: Walk-forward evaluation framework for robust strategy validation
- hyperopt: Hyperparameter optimization using genetic algorithms and Bayesian optimization
- scheduler: Automated optimization scheduling with volatility adaptation

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
    )
"""

from __future__ import annotations

# Import from absolute paths (requires src/ in sys.path)
# Note: hyperopt.OptimizationRecord and scheduler.OptimizationRecord are different classes
from ml.hyperopt import (
    BaseOptimizer,
    BayesianOptimizer,
    GeneticOptimizer,
    HyperparameterOptimizer,
    OptimizationConfig as HyperoptConfig,
    OptimizationMethod,
    OptimizationResult,
    OptimizationTrial,
    ParameterConstraint,
    ParameterType,
)
from ml.scheduler import (
    JobStatus,
    OptimizationScheduler,
    OptimizationTask,
    ParameterDelta,
    ScheduleConfig,
    ScheduleFrequency,
    ScheduledJob,
    VolatilityMonitor,
    VolatilityRegime,
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
]
