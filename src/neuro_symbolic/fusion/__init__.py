"""Fusion module for multi-modal signal combination."""

from src.neuro_symbolic.fusion.aggregator import (
    AggregatedSignals,
    AggregationConfig,
    SignalAggregator,
)
from src.neuro_symbolic.fusion.engine import (
    FusionConfig,
    FusionResult,
    MultiModalFusionEngine,
)
from src.neuro_symbolic.fusion.strategy_selector import (
    FusionStrategy,
    FusionStrategySelector,
    StrategyPerformance,
)

__all__ = [
    "MultiModalFusionEngine",
    "FusionResult",
    "FusionConfig",
    "SignalAggregator",
    "AggregationConfig",
    "AggregatedSignals",
    "FusionStrategySelector",
    "FusionStrategy",
    "StrategyPerformance",
]
