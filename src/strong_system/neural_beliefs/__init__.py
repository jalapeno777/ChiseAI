"""Neural Belief Module for Strong AI System.

Provides neural belief revision components with gradient-based updates,
confidence calibration, and conflict resolution capabilities.

Components:
    - NeuralBelief: Belief vector with gradient tracking for neural updates
    - BeliefRevisionEngine: Gradient-based belief optimization
    - ConfidenceCalibrator: Bayesian confidence calibration
    - BeliefConflictResolver: Detection and resolution of contradictory beliefs

Example:
    >>> from src.strong_system.neural_beliefs import NeuralBelief, BeliefRevisionEngine
    >>> import numpy as np
    >>>
    >>> # Create a neural belief with gradient tracking
    >>> belief = NeuralBelief(
    ...     vector=np.array([0.5, 0.3, 0.8]),
    ...     confidence=0.8,
    ...     requires_grad=True
    ... )
    >>>
    >>> # Perform belief revision
    >>> engine = BeliefRevisionEngine(learning_rate=0.01)
    >>> engine.step([belief])
"""

from __future__ import annotations

from .belief import GradientHistory, NeuralBelief
from .calibrator import (
    BetaDistribution,
    CalibrationMetrics,
    ConfidenceCalibrator,
    ReliabilityBin,
)
from .conflict import (
    BeliefConflictResolver,
    ConflictConfig,
    ConflictResolution,
    ConflictStrategy,
)
from .revision import (
    BeliefRevisionEngine,
    LearningRateScheduler,
    OptimizerConfig,
    OptimizerType,
    RevisionMetrics,
)

__all__ = [
    # Belief exports
    "GradientHistory",
    "NeuralBelief",
    # Revision exports
    "BeliefRevisionEngine",
    "LearningRateScheduler",
    "OptimizerConfig",
    "OptimizerType",
    "RevisionMetrics",
    # Calibrator exports
    "BetaDistribution",
    "CalibrationMetrics",
    "ConfidenceCalibrator",
    "ReliabilityBin",
    # Conflict exports
    "BeliefConflictResolver",
    "ConflictConfig",
    "ConflictResolution",
    "ConflictStrategy",
]
