"""Fundamental analysis module for market microstructure signals.

Provides tools for analyzing funding rates, open interest, and other
fundamental derivatives market data that complement technical indicators.

Exports:
    FundingRateAnalyzer: Main funding rate analysis class
    FundingRatePoint: Single funding rate data point
    FundingTrend: Trend statistics over a window
    ExtremeFundingDetection: Extreme funding detection result
    FundingRateResult: Complete analysis result
    FundingDirection: Enum for funding direction
"""

from market_analysis.fundamentals.funding_rate import (
    ExtremeFundingDetection,
    FundingDirection,
    FundingRateAnalyzer,
    FundingRatePoint,
    FundingRateResult,
    FundingTrend,
)

__all__ = [
    "FundingRateAnalyzer",
    "FundingRatePoint",
    "FundingTrend",
    "ExtremeFundingDetection",
    "FundingRateResult",
    "FundingDirection",
]
