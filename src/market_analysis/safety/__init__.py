"""Safety module for repainting and lookahead detection.

This module provides guards against repainting and lookahead biases in
market analysis indicators with 0% tolerance policy.

Exports:
    lookahead_guard: Decorator for lookahead protection
    RepaintingDetector: Detector for repainting violations
    RepaintingViolation: Violation data class
    RepaintingViolationType: Types of violations
    GuardResult: Result of guard check
    RepaintingError: Exception raised on violation
    check_indicator: Convenience function to check indicators
    check_lookahead: Convenience function to check calculations
    get_detector: Get global detector instance
"""

from market_analysis.safety.lookahead_guard import (
    CheckpointedData,
    GuardResult,
    LookaheadAccessError,
    LookaheadGuard,
    RepaintingDetector,
    RepaintingError,
    RepaintingViolation,
    RepaintingViolationType,
    checkpoint,
    check_indicator,
    check_lookahead,
    get_detector,
    lookahead_guard,
)

__all__ = [
    "lookahead_guard",
    "RepaintingDetector",
    "RepaintingViolation",
    "RepaintingViolationType",
    "GuardResult",
    "RepaintingError",
    "LookaheadAccessError",
    "LookaheadGuard",
    "get_detector",
    "check_indicator",
    "check_lookahead",
    "checkpoint",
    "CheckpointedData",
]
