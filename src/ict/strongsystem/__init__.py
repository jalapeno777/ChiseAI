"""StrongSystem Hypothesis Integration (ST-ICT-029).

This package provides institutional order flow hypothesis scoring
that integrates with existing ICT signals for enhanced confidence.

Modules:
    hypothesis: Bullish/bearish hypothesis scoring from market evidence
    zone_scorer: ICT zone scoring based on hypothesis alignment
    integrator: Combines hypothesis + zones + ICT signals
"""

from ict.strongsystem.hypothesis import (
    BOSConfirmation,
    HypothesisDirection,
    HypothesisScore,
    HypothesisStrength,
    LiquiditySweepEvidence,
    MarketStructureEvidence,
    OrderFlowEvidence,
    StrongSystemHypothesis,
    get_hypothesis_scorer,
)
from ict.strongsystem.integrator import (
    ICTSignal,
    IntegrationResult,
    StrongSystemIntegrator,
    get_integrator,
)
from ict.strongsystem.zone_scorer import (
    ICTZone,
    ZoneAlignment,
    ZoneDirection,
    ZoneScorer,
    ZoneScoreResult,
    ZoneType,
    get_zone_scorer,
)

__all__ = [
    # Hypothesis
    "BOSConfirmation",
    "HypothesisDirection",
    "HypothesisScore",
    "HypothesisStrength",
    "LiquiditySweepEvidence",
    "MarketStructureEvidence",
    "OrderFlowEvidence",
    "StrongSystemHypothesis",
    "get_hypothesis_scorer",
    # Zone Scorer
    "ICTZone",
    "ZoneAlignment",
    "ZoneDirection",
    "ZoneScoreResult",
    "ZoneScorer",
    "ZoneType",
    "get_zone_scorer",
    # Integrator
    "ICTSignal",
    "IntegrationResult",
    "StrongSystemIntegrator",
    "get_integrator",
]
