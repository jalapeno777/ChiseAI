"""Model validation module for ChiseAI.

Provides validation gates with shadow mode and A/B testing.
"""

from ml.validation.gate import (
    ComparisonResult,
    ValidationConfig,
    ValidationGate,
    ValidationMetrics,
    ValidationMode,
    ValidationRun,
    ValidationState,
)
from ml.validation.promotion import (
    PromotionRequest,
    PromotionRequestStatus,
    PromotionResult,
    PromotionWorkflow,
)
from ml.validation.model_validator import (
    CompositeGateResult,
    DefaultInfluxDBLogger,
    DegradationDetector,
    GateResult,
    GateStatus,
    ShadowComparisonResult,
    ShadowModeConfig,
    ShadowModeManager,
    ValidationGate as ModelValidationGate,
    ValidationLevel,
    ValidationThresholds,
    validate_model_metrics,
)

__all__ = [
    # From gate.py
    "ComparisonResult",
    "ValidationConfig",
    "ValidationGate",
    "ValidationMetrics",
    "ValidationMode",
    "ValidationRun",
    "ValidationState",
    # From promotion.py
    "PromotionRequest",
    "PromotionRequestStatus",
    "PromotionResult",
    "PromotionWorkflow",
    # From model_validator.py
    "CompositeGateResult",
    "DefaultInfluxDBLogger",
    "DegradationDetector",
    "GateResult",
    "GateStatus",
    "ModelValidationGate",
    "ShadowComparisonResult",
    "ShadowModeConfig",
    "ShadowModeManager",
    "ValidationLevel",
    "ValidationThresholds",
    "validate_model_metrics",
]
