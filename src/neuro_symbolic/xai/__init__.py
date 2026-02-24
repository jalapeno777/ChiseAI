"""Extended XAI (Explainable AI) Utilities Module.

This package provides extended XAI utilities for advanced analysis
and visualization of AI decision explanations.

Submodules:
- shap_utils: SHAP value calculation and visualization utilities
- visualization: Advanced visualization components
- interpretation: Natural language interpretation helpers
"""

from __future__ import annotations

from neuro_symbolic.xai.shap_utils import (
    SHAPCalculator,
    SHAPConfig,
    SHAPResult,
    InteractionDetector,
)
from neuro_symbolic.xai.visualization import (
    ExplanationVisualizer,
    VisualizationConfig,
    PlotType,
)

__all__ = [
    # SHAP utilities
    "SHAPCalculator",
    "SHAPConfig",
    "SHAPResult",
    "InteractionDetector",
    # Visualization
    "ExplanationVisualizer",
    "VisualizationConfig",
    "PlotType",
]
