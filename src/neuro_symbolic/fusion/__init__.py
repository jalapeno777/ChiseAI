"""Fusion module for multi-modal signal combination."""

from src.neuro_symbolic.fusion.engine import (
    MultiModalFusionEngine,
    FusionResult,
    FusionConfig,
)
from src.neuro_symbolic.fusion.aggregator import (
    SignalAggregator,
    AggregationConfig,
    AggregatedSignals,
)
from src.neuro_symbolic.fusion.strategy_selector import (
    FusionStrategySelector,
    FusionStrategy,
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
