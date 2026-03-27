"""Shared scoring utilities for autonomous cognition evaluation.

This module provides composite scoring functions used across
champion-challenger evaluation and portfolio policy lab.
"""

from __future__ import annotations


def composite_score(metrics: dict[str, float]) -> float:
    """Calculate composite score from performance metrics.

    Uses weighted combination of risk-adjusted returns and error metrics:
    - Positive factors: sharpe (0.30), sortino (0.20)
    - Negative factors: drawdown (-0.30), ece (-0.20)

    Args:
        metrics: Dictionary with optional keys: sharpe, sortino, drawdown, ece.
                 Missing keys default to 0.0.

    Returns:
        Composite score as float.

    Example:
        >>> score = composite_score({"sharpe": 1.2, "sortino": 1.4, "drawdown": 0.15, "ece": 0.08})
        >>> round(score, 3)
        0.37
    """
    return (
        metrics.get("sharpe", 0.0) * 0.30
        + metrics.get("sortino", 0.0) * 0.20
        - metrics.get("drawdown", 0.0) * 0.30
        - metrics.get("ece", 0.0) * 0.20
    )
