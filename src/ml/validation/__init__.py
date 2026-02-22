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

__all__ = [
    "ComparisonResult",
    "PromotionRequest",
    "PromotionRequestStatus",
    "PromotionResult",
    "PromotionWorkflow",
    "ValidationConfig",
    "ValidationGate",
    "ValidationMetrics",
    "ValidationMode",
    "ValidationRun",
    "ValidationState",
]
