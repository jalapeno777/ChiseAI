"""Market analysis package for multi-timeframe analysis.

Provides tools for aggregating and analyzing OHLCV data across
multiple timeframes with consistency validation and Markov chain
trend state detection.
"""

from market_analysis.markov import (
    MARKOV_STATES,
    InferenceResult,
    ProbabilityCalculator,
    StateHistory,
    TransitionPrediction,
    TrendInferenceEngine,
    TrendState,
)
from market_analysis.timeframe_aggregator import AggregationResult, TimeframeAggregator

__all__ = [
    # Timeframe aggregation
    "TimeframeAggregator",
    "AggregationResult",
    # Markov chain trend detection
    "TrendState",
    "MARKOV_STATES",
    "StateHistory",
    "TrendInferenceEngine",
    "InferenceResult",
    "ProbabilityCalculator",
    "TransitionPrediction",
]
