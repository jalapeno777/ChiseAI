"""Hypothesis Generator Module for STRONG Neuro-Symbolic AI System.

Provides LLM-based hypothesis generation from belief clusters and market context.
Bridges neural pattern recognition with symbolic reasoning by generating structured
hypotheses that can be validated against market conditions.

Components:
    - HypothesisGenerator: Main class for generating and validating hypotheses
    - Hypothesis: Data class representing a testable hypothesis
    - ConfidenceScore: Structured confidence scoring for hypotheses
    - ValidationResult: Results of hypothesis validation against market data
    - PromptTemplate: Templates for LLM hypothesis generation
    - HypothesisValidator: Validation logic for testing hypotheses

Example:
    >>> from src.strong_system.hypothesis_generator import (
    ...     HypothesisGenerator,
    ...     GeneratorConfig,
    ...     MarketContext,
    ... )
    >>> from src.strong_system.belief_embeddings import BeliefVector
    >>> import numpy as np
    >>>
    >>> # Configure generator
    >>> config = GeneratorConfig(
    ...     llm_provider="openai",
    ...     max_hypotheses=5,
    ...     min_confidence=0.5,
    ... )
    >>> generator = HypothesisGenerator(config)
    >>>
    >>> # Create market context
    >>> context = MarketContext(
    ...     symbol="BTC-USD",
    ...     timeframe="1h",
    ...     current_price=50000.0,
    ...     market_regime="bullish",
    ... )
    >>>
    >>> # Generate hypotheses from beliefs
    >>> beliefs = [BeliefVector(vector=np.array([0.5, 0.3, 0.8]))]
    >>> result = generator.generate_from_beliefs(beliefs, context)
    >>>
    >>> # Access generated hypotheses
    >>> for hypothesis in result.hypotheses:
    ...     print(f"{hypothesis.description}: {hypothesis.confidence.score:.2f}")
"""

from __future__ import annotations

from src.strong_system.hypothesis_generator.generator import (
    GeneratorMetrics,
    HypothesisGenerator,
    MockLLMProvider,
)
from src.strong_system.hypothesis_generator.templates import (
    PromptTemplate,
    TemplateRegistry,
    get_template_registry,
    render_prompt,
)
from src.strong_system.hypothesis_generator.types import (
    ConfidenceScore,
    GenerationResult,
    GeneratorConfig,
    Hypothesis,
    HypothesisType,
    MarketContext,
    ValidationResult,
    ValidationStatus,
)
from src.strong_system.hypothesis_generator.validator import (
    HypothesisValidator,
    PredictionParser,
    ValidationConfig,
    ValidationMetrics,
)

__all__ = [
    # Generator exports
    "HypothesisGenerator",
    "GeneratorMetrics",
    "MockLLMProvider",
    # Types exports
    "Hypothesis",
    "HypothesisType",
    "ConfidenceScore",
    "MarketContext",
    "GeneratorConfig",
    "GenerationResult",
    "ValidationResult",
    "ValidationStatus",
    # Templates exports
    "PromptTemplate",
    "TemplateRegistry",
    "get_template_registry",
    "render_prompt",
    # Validator exports
    "HypothesisValidator",
    "PredictionParser",
    "ValidationConfig",
    "ValidationMetrics",
]
