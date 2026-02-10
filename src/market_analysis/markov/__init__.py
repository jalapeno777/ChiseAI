"""Markov chain-based trend state detection module.

Provides probabilistic market regime identification using Markov chains
to model transitions between bullish, bearish, neutral, and transitional states.
"""

from market_analysis.markov.inference_engine import (
    InferenceResult,
    TrendInferenceEngine,
)
from market_analysis.markov.probability_calculator import (
    ProbabilityCalculator,
    TransitionPrediction,
)
from market_analysis.markov.state_model import (
    MARKOV_STATES,
    StateHistory,
    TrendState,
)

__all__ = [
    # State model
    "TrendState",
    "MARKOV_STATES",
    "StateHistory",
    # Inference engine
    "TrendInferenceEngine",
    "InferenceResult",
    # Probability calculator
    "ProbabilityCalculator",
    "TransitionPrediction",
]
