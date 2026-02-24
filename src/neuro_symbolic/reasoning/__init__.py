"""Neuro-symbolic reasoning module.

This module provides hybrid reasoning capabilities combining neural network
pattern recognition with symbolic logic for market analysis.
"""

from src.neuro_symbolic.reasoning.hybrid_engine import (
    HybridReasoningEngine,
    HybridReasoningResult,
    analyze_market_data,
)
from src.neuro_symbolic.reasoning.integration_layer import (
    FusedResult,
    FusionStrategy,
    IntegrationLayer,
    ReasoningChain,
)
from src.neuro_symbolic.reasoning.neural_component import (
    FeatureExtractor,
    MarketFeatureExtractor,
    NeuralComponent,
    NeuralOutput,
    PatternRecognizer,
)
from src.neuro_symbolic.reasoning.symbolic_component import (
    InferenceEngine,
    MomentumRule,
    RuleResult,
    RuleType,
    SupportResistanceRule,
    SymbolicComponent,
    SymbolicOutput,
    SymbolicRule,
    TrendDirection,
    TrendRule,
    VolatilityRule,
    VolumeRule,
)

__all__ = [
    # Neural component
    "NeuralComponent",
    "NeuralOutput",
    "FeatureExtractor",
    "MarketFeatureExtractor",
    "PatternRecognizer",
    # Symbolic component
    "SymbolicComponent",
    "SymbolicOutput",
    "SymbolicRule",
    "RuleResult",
    "RuleType",
    "TrendDirection",
    "TrendRule",
    "VolumeRule",
    "MomentumRule",
    "VolatilityRule",
    "SupportResistanceRule",
    "InferenceEngine",
    # Integration layer
    "IntegrationLayer",
    "FusedResult",
    "ReasoningChain",
    "FusionStrategy",
    # Hybrid engine
    "HybridReasoningEngine",
    "HybridReasoningResult",
    "analyze_market_data",
]
