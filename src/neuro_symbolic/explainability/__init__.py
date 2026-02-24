"""Explainability Module for ChiseAI.

This package provides explainable AI capabilities for trading decisions:

- generator: Human-readable explanation generation with reasoning chains
- feature_importance: SHAP-style feature importance analysis
- confidence_scorer: Explanation confidence and reliability scoring
- formatter: Multi-audience explanation formatting

Usage:
    from neuro_symbolic.explainability import (
        ExplanationGenerator,
        FeatureImportanceAnalyzer,
        ExplanationConfidenceScorer,
        ExplanationFormatter,
    )

    # Generate explanation
    generator = ExplanationGenerator()
    explanation = generator.explain({
        'prediction': 'buy',
        'confidence': 0.85,
        'features': {'rsi': 30, 'macd': 0.5}
    })

    # Analyze feature importance
    analyzer = FeatureImportanceAnalyzer()
    importance = analyzer.analyze(features, prediction=0.85)

    # Score explanation confidence
    scorer = ExplanationConfidenceScorer()
    confidence = scorer.score_explanation(explanation.to_dict())

    # Format for different audiences
    formatter = ExplanationFormatter()
    formatted = formatter.format_for_trader(explanation.to_dict())
"""

from __future__ import annotations

from neuro_symbolic.explainability.generator import (
    ExplanationConfig,
    ExplanationGenerator,
    ExplanationResult,
    ExplanationType,
    ReasoningStep,
)
from neuro_symbolic.explainability.feature_importance import (
    FeatureContribution,
    FeatureImportanceAnalyzer,
    FeatureImportanceResult,
    ImportanceMethod,
    ImportanceVisualization,
)
from neuro_symbolic.explainability.confidence_scorer import (
    ConfidenceLevel,
    ConfidenceMetric,
    ConfidenceScore,
    ExplanationConfidenceScorer,
    ScoringConfig,
)
from neuro_symbolic.explainability.formatter import (
    AudienceType,
    ExplanationFormatter,
    FormattedExplanation,
    FormatterConfig,
    OutputFormat,
)

__all__ = [
    # Generator
    "ExplanationType",
    "ReasoningStep",
    "ExplanationResult",
    "ExplanationConfig",
    "ExplanationGenerator",
    # Feature Importance
    "ImportanceMethod",
    "FeatureContribution",
    "FeatureImportanceResult",
    "ImportanceVisualization",
    "FeatureImportanceAnalyzer",
    # Confidence Scorer
    "ConfidenceLevel",
    "ConfidenceMetric",
    "ConfidenceScore",
    "ScoringConfig",
    "ExplanationConfidenceScorer",
    # Formatter
    "AudienceType",
    "OutputFormat",
    "FormatterConfig",
    "FormattedExplanation",
    "ExplanationFormatter",
]
