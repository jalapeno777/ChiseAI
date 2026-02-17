"""Automated reporting and anomaly detection system for ChiseAI.

Provides:
- DailyReportGenerator: Daily PnL summaries with trade metrics
- WeeklyPerformanceReport: 7-day rolling performance analysis
- AnomalyDetector: Detects unusual PnL, volume spikes, error rate increases
- ReportScheduler: Cron-like scheduling with Discord/email delivery

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

from .daily_generator import DailyReportGenerator
from .weekly_generator import WeeklyPerformanceReport
from .anomaly_detector import AnomalyDetector
from .scheduler import ReportScheduler
from .models import (
    DailyReport,
    WeeklyReport,
    AnomalyAlert,
    AnomalySeverity,
    AnomalyType,
    ReportSchedule,
    TradeMetrics,
    RiskMetrics,
    StrategyPerformance,
)

__version__ = "1.0.0"

__all__ = [
    "DailyReportGenerator",
    "WeeklyPerformanceReport",
    "AnomalyDetector",
    "ReportScheduler",
    "DailyReport",
    "WeeklyReport",
    "AnomalyAlert",
    "AnomalySeverity",
    "AnomalyType",
    "ReportSchedule",
    "TradeMetrics",
    "RiskMetrics",
    "StrategyPerformance",
]
