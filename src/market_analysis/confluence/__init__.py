"""Confluence-based signal scoring module.

This module provides confluence scoring capabilities that combine multiple
indicator signals into a unified score for identifying high-probability
trading opportunities.

Exports:
    ConfluenceScorer: Main scoring engine
    ConfluenceScore: Result dataclass for scoring
    IndicatorWeights: Weight configuration
    SignalAggregator: Signal aggregation from indicators
    IndicatorSignal: Individual signal dataclass
    AggregatedSignals: Collection of aggregated signals
    SignalDirection: Enum for signal directions
    DEFAULT_WEIGHTS: Default weight configuration
    WeightPreset: Predefined weight configurations
"""

from market_analysis.confluence.indicator_weights import (
    DEFAULT_WEIGHTS,
    IndicatorWeights,
    WeightPreset,
)
from market_analysis.confluence.scorer import ConfluenceScore, ConfluenceScorer
from market_analysis.confluence.signal_aggregator import (
    AggregatedSignals,
    IndicatorSignal,
    SignalAggregator,
    SignalDirection,
)

__all__ = [
    # Scorer
    "ConfluenceScorer",
    "ConfluenceScore",
    # Weights
    "IndicatorWeights",
    "DEFAULT_WEIGHTS",
    "WeightPreset",
    # Signal Aggregation
    "SignalAggregator",
    "AggregatedSignals",
    "IndicatorSignal",
    "SignalDirection",
]
