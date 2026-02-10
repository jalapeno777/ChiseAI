"""Correlation analysis module for portfolio risk management."""

from portfolio_risk.correlation.api import (
    CorrelationAPI,
    create_correlation_routes,
)
from portfolio_risk.correlation.engine import (
    CorrelationEngine,
    CorrelationMethod,
    CorrelationResult,
    RollingCorrelationResult,
)

__all__ = [
    "CorrelationAPI",
    "CorrelationEngine",
    "CorrelationMethod",
    "CorrelationResult",
    "RollingCorrelationResult",
    "create_correlation_routes",
]
