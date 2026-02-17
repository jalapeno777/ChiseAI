"""Paper trading execution module.

Provides components for simulating order execution and paper trading:
- OrderSimulator: Simulates order placement and fills
- FillModel: Models realistic fill prices with slippage
- PaperRiskEnforcer: Validates orders against risk limits
- PaperTradingOrchestrator: End-to-end signal-to-position workflow
- SignalToOrderPipeline: Streamlined signal processing pipeline
"""

from execution.paper.fill_model import FillModel, FillModelConfig
from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperFill,
    PaperOrder,
    PaperTradeResult,
    RiskAssessment,
    TradeStatus,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.order_simulator import OrderSimulator
from execution.paper.pipeline import PipelineMetrics, SignalToOrderPipeline
from execution.paper.risk_enforcer import PaperRiskEnforcer, RiskEnforcerConfig

__all__ = [
    # Models
    "OrderSide",
    "OrderState",
    "OrderType",
    "PaperFill",
    "PaperOrder",
    "PaperTradeResult",
    "RiskAssessment",
    "TradeStatus",
    # Components
    "FillModel",
    "FillModelConfig",
    "OrderSimulator",
    "PaperRiskEnforcer",
    "RiskEnforcerConfig",
    "PaperTradingOrchestrator",
    "SignalToOrderPipeline",
    "PipelineMetrics",
]
