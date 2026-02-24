"""Learning module for adaptive model improvement.

This module provides base classes and utilities for online learning,
feedback integration, and model adaptation.
"""

from src.neuro_symbolic.learning.base import (
    LearningConfig,
    FeedbackSignal,
    AdaptationResult,
    PerformanceMetrics,
)

__all__ = [
    "LearningConfig",
    "FeedbackSignal",
    "AdaptationResult",
    "PerformanceMetrics",
]
