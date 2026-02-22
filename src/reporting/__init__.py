"""Automated reporting and anomaly detection system for ChiseAI.

Provides:
- DailyReportGenerator: Daily PnL summaries with trade metrics
- WeeklyPerformanceReport: 7-day rolling performance analysis
- AnomalyDetector: Detects unusual PnL, volume spikes, error rate increases
- ReportScheduler: Cron-like scheduling with Discord/email delivery

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

from .anomaly_detector import AnomalyDetector
from .daily_generator import DailyReportGenerator
from .models import (
    AnomalyAlert,
    AnomalySeverity,
    AnomalyType,
    DailyReport,
    PaperHealthMetrics,
    PaperHealthReport,
    ReportSchedule,
    RiskMetrics,
    StrategyPerformance,
    TradeMetrics,
    WeeklyReport,
)
from .scheduler import ReportScheduler
from .weekly_generator import WeeklyPerformanceReport

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
    "PaperHealthMetrics",
    "PaperHealthReport",
]
