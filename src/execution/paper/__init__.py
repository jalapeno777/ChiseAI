"""Paper trading execution module.

Provides paper execution components including risk enforcement and orchestrated flow.
"""

from __future__ import annotations

from execution.paper.fill_model import FillModel, FillModelConfig
from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperFill,
    PaperOrder,
    PaperTradeResult,
    TradeStatus,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.order_simulator import OrderSimulator
from execution.paper.pipeline import PipelineMetrics, SignalToOrderPipeline
from execution.paper.risk_enforcer import PaperRiskEnforcer
from execution.paper.risk_models import (
    PaperPosition,
    RiskAssessment,
    RiskCheck,
    RiskSeverity,
    RiskViolation,
)

__all__ = [
    "FillModel",
    "FillModelConfig",
    "OrderSide",
    "OrderState",
    "OrderType",
    "OrderSimulator",
    "PaperFill",
    "PaperOrder",
    "PaperPosition",
    "PaperRiskEnforcer",
    "PaperTradeResult",
    "PaperTradingOrchestrator",
    "PipelineMetrics",
    "RiskAssessment",
    "RiskCheck",
    "RiskSeverity",
    "RiskViolation",
    "SignalToOrderPipeline",
    "TradeStatus",
]
