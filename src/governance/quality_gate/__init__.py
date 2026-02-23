"""Quality Gate Module for Automated Self-Review.

Provides automated quality scoring and PR blocking for all pull requests.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

from src.governance.quality_gate.gate import (
    BlockReason,
    QualityGate,
    QualityGateResult,
)
from src.governance.quality_gate.override import (
    HumanOverride,
    OverrideManager,
    OverrideStatus,
)
from src.governance.quality_gate.scorer import (
    QualityScore,
    QualityScorer,
    ScoreComponent,
)

__all__ = [
    # Scorer
    "QualityScorer",
    "QualityScore",
    "ScoreComponent",
    # Gate
    "QualityGate",
    "QualityGateResult",
    "BlockReason",
    # Override
    "HumanOverride",
    "OverrideManager",
    "OverrideStatus",
]
