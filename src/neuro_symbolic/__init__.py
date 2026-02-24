"""Neuro-Symbolic AI Module for ChiseAI.

This package provides neuro-symbolic AI capabilities combining neural networks
with symbolic reasoning for explainable trading decisions.

Submodules:
- explainability: Human-readable explanations for AI decisions
- xai: Extended explainability utilities and SHAP-style analysis

Usage:
    from neuro_symbolic.explainability import (
        ExplanationGenerator,
        FeatureImportanceAnalyzer,
        ExplanationConfidenceScorer,
        ExplanationFormatter,
    )
"""

from __future__ import annotations

__all__ = [
    # explainability module
    "ExplanationGenerator",
    "ExplanationConfig",
    "ExplanationResult",
    "ExplanationType",
    "FeatureImportanceAnalyzer",
    "FeatureImportanceResult",
    "ImportanceMethod",
    "ExplanationConfidenceScorer",
    "ConfidenceScore",
    "ConfidenceLevel",
    "ExplanationFormatter",
    "FormatterConfig",
    "AudienceType",
    "FormattedExplanation",
]
