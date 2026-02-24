"""Adaptive Learning module for continuous model improvement.

This module provides components for adaptive learning from market feedback:
- AdaptiveLearningEngine: Main orchestration class
- FeedbackIntegrator: Processes trade outcomes into learning signals
- ModelAdapter: Handles model parameter adjustments and A/B testing
- LearningScheduler: Schedules retraining based on performance
"""

from src.neuro_symbolic.adaptive_learning.adapter import (
    ABTest,
    ABTestVariant,
    AdapterConfig,
    HyperparameterSpace,
    ModelAdapter,
)
from src.neuro_symbolic.adaptive_learning.engine import (
    AdaptiveLearningEngine,
    EngineConfig,
    EngineState,
)
from src.neuro_symbolic.adaptive_learning.feedback import (
    FeedbackHistory,
    FeedbackIntegrator,
    IntegratorConfig,
)
from src.neuro_symbolic.adaptive_learning.scheduler import (
    LearningScheduler,
    ScheduledTask,
    SchedulerConfig,
    ScheduleStatus,
    TriggerRule,
)

__all__ = [
    # Engine
    "AdaptiveLearningEngine",
    "EngineConfig",
    "EngineState",
    # Feedback
    "FeedbackIntegrator",
    "IntegratorConfig",
    "FeedbackHistory",
    # Adapter
    "ModelAdapter",
    "AdapterConfig",
    "ABTest",
    "ABTestVariant",
    "HyperparameterSpace",
    # Scheduler
    "LearningScheduler",
    "SchedulerConfig",
    "ScheduledTask",
    "TriggerRule",
    "ScheduleStatus",
]
