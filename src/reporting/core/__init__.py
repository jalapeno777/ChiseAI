"""Core report generation engine for ST-NS-023 Performance Reporting System.

Provides:
- ReportScheduler: Daily/weekly/monthly trigger support
- PnLCalculator: Calculate daily/weekly/monthly P&L
- DrawdownAnalyzer: Calculate maximum drawdown and recovery
- WinRateCalculator: Win/loss counts and percentages
- TradeStatsAggregator: Trade statistics aggregation
- ReportArchive: Report archival with queryable history

For EP-NS-005: Performance Reporting System
"""

from __future__ import annotations

from .archive import ReportArchive
from .drawdown_analyzer import DrawdownAnalyzer
from .pnl_calculator import PnLCalculator
from .scheduler import ReportScheduler
from .trade_stats import TradeStatsAggregator
from .win_rate import WinRateCalculator

__version__ = "1.0.0"

__all__ = [
    "ReportScheduler",
    "PnLCalculator",
    "DrawdownAnalyzer",
    "WinRateCalculator",
    "TradeStatsAggregator",
    "ReportArchive",
]
