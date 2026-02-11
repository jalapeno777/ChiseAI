"""Position sizing calculation engine.

Provides multiple position sizing methods including Kelly Criterion,
fixed fractional sizing, and volatility-based sizing with risk management
constraints.
"""

from __future__ import annotations

import logging

from portfolio_risk.position_sizing.api import (
    PositionSizingAPI,
    create_position_sizing_routes,
)
from portfolio_risk.position_sizing.calculator import PositionSizeCalculator
from portfolio_risk.position_sizing.engine import PositionSizingEngine
from portfolio_risk.position_sizing.integration import (
    PortfolioExposure,
    PositionSizingCache,
    PositionSizingIntegration,
    SizingRecommendation,
)
from portfolio_risk.position_sizing.types import (
    KellyInputs,
    PositionSizeResult,
    SizingConfig,
    SizingMethod,
    VolatilityInputs,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Types
    "KellyInputs",
    "PositionSizeResult",
    "SizingConfig",
    "SizingMethod",
    "VolatilityInputs",
    # Engine
    "PositionSizingEngine",
    # Calculator
    "PositionSizeCalculator",
    # Integration
    "PortfolioExposure",
    "PositionSizingCache",
    "PositionSizingIntegration",
    "SizingRecommendation",
    # API
    "PositionSizingAPI",
    "create_position_sizing_routes",
]
