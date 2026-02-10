"""Stop-loss calculation module.

Provides stop-loss calculation capabilities using multiple methods:
- ATR-based stops (volatility-adjusted)
- Technical level stops (support/resistance)
- Percentage-based stops (configurable)
- Stop-loss hit tracking for outcome correlation
"""

from portfolio_risk.stop_loss.atr_indicator import ATR, ATRResult
from portfolio_risk.stop_loss.calculator import (
    StopLossCalculation,
    StopLossCalculator,
    StopLossConfig,
)
from portfolio_risk.stop_loss.engine import (
    StopLossComparison,
    StopLossEngine,
    StopLossMethod,
    StopLossResult,
    TradeDirection,
)
from portfolio_risk.stop_loss.tracker import (
    SignalOutcome,
    SignalResult,
    StopLossCorrelationStats,
    StopLossHitEvent,
    StopLossOutcome,
    StopLossTracker,
)

__all__ = [
    # ATR Indicator
    "ATR",
    "ATRResult",
    # Calculator
    "StopLossCalculator",
    "StopLossCalculation",
    "StopLossConfig",
    # Engine
    "StopLossEngine",
    StopLossMethod,
    "StopLossResult",
    "StopLossComparison",
    TradeDirection,
    # Tracker
    "StopLossTracker",
    "StopLossHitEvent",
    "StopLossOutcome",
    "SignalOutcome",
    "SignalResult",
    "StopLossCorrelationStats",
]
