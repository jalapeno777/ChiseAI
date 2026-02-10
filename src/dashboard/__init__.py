"""Dashboard package for pre-market briefing and market analysis display.

This package provides components for aggregating and displaying market data,
key levels, active signals, and market regime detection for dashboard users.
"""

from __future__ import annotations

from dashboard.key_levels import KeyLevel, KeyLevelsAnalyzer, LevelType
from dashboard.market_summary import MarketSummary, MarketSummaryCalculator
from dashboard.pre_market_briefing import PreMarketBriefing, PreMarketBriefingGenerator
from dashboard.regime_detector import MarketRegime, RegimeDetector, RegimeType
from dashboard.signal_list import ActiveSignal, SignalListBuilder

__all__ = [
    # Key Levels
    "KeyLevel",
    "KeyLevelsAnalyzer",
    "LevelType",
    # Market Summary
    "MarketSummary",
    "MarketSummaryCalculator",
    # Pre-Market Briefing
    "PreMarketBriefing",
    "PreMarketBriefingGenerator",
    # Regime Detection
    "MarketRegime",
    "RegimeDetector",
    "RegimeType",
    # Signal List
    "ActiveSignal",
    "SignalListBuilder",
]
