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

# Market realism models
from execution.paper.slippage_model import SlippageModel, SlippageConfig
from execution.paper.latency_model import LatencyModel, LatencyConfig
from execution.paper.market_impact import MarketImpact, MarketImpactConfig
from execution.paper.fill_probability import FillProbability, FillProbabilityConfig
from execution.paper.config_loader import (
    MarketRealismConfig,
    load_market_realism_config,
)

__all__ = [
    # Core models
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
    # Market realism models
    "SlippageModel",
    "SlippageConfig",
    "LatencyModel",
    "LatencyConfig",
    "MarketImpact",
    "MarketImpactConfig",
    "FillProbability",
    "FillProbabilityConfig",
    "MarketRealismConfig",
    "load_market_realism_config",
]
