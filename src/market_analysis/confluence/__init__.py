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
    TwoLayerScorer: Two-layer ICT signal scorer
    TwoLayerScore: Result dataclass for two-layer scoring
    Layer1SignalScorer: Layer 1 individual signal scorer
    Layer1Score: Result dataclass for Layer 1 scoring
    Layer2ConfluenceAggregator: Layer 2 confluence aggregator
    Layer2ConfluenceResult: Result dataclass for Layer 2 aggregation
    ICTSignalType: Enum for ICT signal types (excludes BOS/CHoCH)
    ICT_SIGNAL_WEIGHTS: Signal weights from EP-ICT-004 validation
    get_signal_weight: Get weight for a specific signal type
    SignalWeight: Dataclass for signal weight configuration
"""

from market_analysis.confluence.indicator_weights import (
    DEFAULT_WEIGHTS,
    IndicatorWeights,
    WeightPreset,
)
from market_analysis.confluence.layer1_signal_scorer import (
    Layer1Score,
    Layer1SignalDirection,
    Layer1SignalScorer,
)
from market_analysis.confluence.layer2_confluence_aggregator import (
    Layer2ConfluenceAggregator,
    Layer2ConfluenceResult,
)
from market_analysis.confluence.scorer import ConfluenceScore, ConfluenceScorer
from market_analysis.confluence.signal_aggregator import (
    AggregatedSignals,
    IndicatorSignal,
    SignalAggregator,
    SignalDirection,
)
from market_analysis.confluence.signal_weights import (
    ICT_SIGNAL_WEIGHTS,
    ICTSignalType,
    SignalWeight,
    get_all_weights,
    get_signal_metadata,
    get_signal_weight,
)
from market_analysis.confluence.two_layer_scorer import (
    TwoLayerScore,
    TwoLayerScorer,
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
    # Two-Layer Scorer
    "TwoLayerScorer",
    "TwoLayerScore",
    # Layer 1
    "Layer1SignalScorer",
    "Layer1Score",
    "Layer1SignalDirection",
    # Layer 2
    "Layer2ConfluenceAggregator",
    "Layer2ConfluenceResult",
    # Signal Weights (EP-ICT-004)
    "ICTSignalType",
    "ICT_SIGNAL_WEIGHTS",
    "SignalWeight",
    "get_signal_weight",
    "get_all_weights",
    "get_signal_metadata",
]
