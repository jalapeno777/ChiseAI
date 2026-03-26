"""Neuro-Symbolic Explainability for ICT signals.

Generates human-readable explanations that link quantitative signals
to their underlying ICT (Inner Circle Trader) concepts: Order Blocks,
Fair Value Gaps, and Cumulative Volume Delta.

Public API:
    ICTConceptRegistry   - knowledge base of ICT concept descriptions
    ICTExplainer          - generates ExplanationResult from signal data
    ICTExplanationResult - structured explanation with rendering methods
    format_for_discord   - markdown-formatted Discord payload
    format_for_dashboard - dict payload for dashboard consumption
"""

from .concepts import ICTConceptRegistry
from .explainer import ICTExplainer, ICTExplanationResult
from .formatter import format_for_dashboard, format_for_discord

__all__ = [
    "ICTConceptRegistry",
    "ICTExplainer",
    "ICTExplanationResult",
    "format_for_dashboard",
    "format_for_discord",
]
