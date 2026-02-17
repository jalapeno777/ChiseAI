"""Data models for the reporting system.

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class AnomalyType(Enum):
    """Types of anomalies that can be detected."""

    PNL_SPIKE = "pnl_spike"
    VOLUME_SPIKE = "volume_spike"
    ERROR_RATE_SPIKE = "error_rate_spike"
    DRAWDOWN_SPIKE = "drawdown_spike"
    LATENCY_SPIKE = "latency_spike"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TradeMetrics:
    """Trade execution metrics for a period."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_pnl_per_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    total_volume: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "avg_pnl_per_trade": round(self.avg_pnl_per_trade, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "total_volume": round(self.total_volume, 2),
        }


@dataclass
class RiskMetrics:
    """Risk metrics for a period."""

    sharpe_ratio: float = 0.0
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    var_95: float = 0.0  # Value at Risk (95%)
    exposure_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "volatility": round(self.volatility, 4),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "var_95": round(self.var_95, 2),
            "exposure_pct": round(self.exposure_pct, 2),
        }


@dataclass
class StrategyPerformance:
    """Performance metrics for a single strategy."""

    strategy_id: str
    strategy_name: str
    total_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    sharpe_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 2),
            "total_pnl": round(self.total_pnl, 2),
            "avg_pnl": round(self.avg_pnl, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }


@dataclass
class DailyReport:
    """Daily PnL and trading summary report."""

    date: datetime
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_pnl: float = 0.0
    trade_metrics: TradeMetrics = field(default_factory=TradeMetrics)
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    open_positions: int = 0
    portfolio_value: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 2),
            "total_pnl": round(self.total_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_pnl": round(self.avg_pnl, 2),
            "trade_metrics": self.trade_metrics.to_dict(),
            "risk_metrics": self.risk_metrics.to_dict(),
            "open_positions": self.open_positions,
            "portfolio_value": round(self.portfolio_value, 2),
            "generated_at": self.generated_at.isoformat(),
        }

    def to_markdown(self) -> str:
        """Generate Markdown formatted report."""
        lines = [
            "# 📊 Daily Trading Summary",
            f"",
            f"**Date:** {self.date.strftime('%Y-%m-%d')}",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            "## 📈 PnL Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total PnL | ${self.total_pnl:,.2f} |",
            f"| Realized PnL | ${self.realized_pnl:,.2f} |",
            f"| Unrealized PnL | ${self.unrealized_pnl:,.2f} |",
            f"| Portfolio Value | ${self.portfolio_value:,.2f} |",
            f"",
            "## 📊 Trade Statistics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Trades | {self.total_trades} |",
            f"| Winning Trades | {self.winning_trades} |",
            f"| Losing Trades | {self.losing_trades} |",
            f"| Win Rate | {self.win_rate:.1f}% |",
            f"| Avg PnL/Trade | ${self.avg_pnl:,.2f} |",
            f"",
            "## ⚠️ Risk Metrics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Max Drawdown | ${self.max_drawdown:,.2f} ({self.max_drawdown_pct:.1f}%) |",
            f"| Sharpe Ratio | {self.risk_metrics.sharpe_ratio:.2f} |",
            f"| Volatility | {self.risk_metrics.volatility:.2%} |",
            f"| Open Positions | {self.open_positions} |",
            f"",
            "---",
            f"*Report generated by ChiseAI Automated Reporting System*",
        ]
        return "\n".join(lines)


@dataclass
class WeeklyReport:
    """Weekly performance analysis report."""

    start_date: datetime
    end_date: datetime
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_daily_pnl: float = 0.0
    best_day: tuple[datetime, float] = field(
        default_factory=lambda: (datetime.now(UTC), 0.0)
    )
    worst_day: tuple[datetime, float] = field(
        default_factory=lambda: (datetime.now(UTC), 0.0)
    )
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    strategy_performance: list[StrategyPerformance] = field(default_factory=list)
    week_over_week_change: dict[str, float] = field(default_factory=dict)
    daily_breakdown: list[dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start_date": self.start_date.strftime("%Y-%m-%d"),
            "end_date": self.end_date.strftime("%Y-%m-%d"),
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 2),
            "win_rate": round(self.win_rate, 2),
            "avg_daily_pnl": round(self.avg_daily_pnl, 2),
            "best_day": {
                "date": self.best_day[0].strftime("%Y-%m-%d"),
                "pnl": round(self.best_day[1], 2),
            },
            "worst_day": {
                "date": self.worst_day[0].strftime("%Y-%m-%d"),
                "pnl": round(self.worst_day[1], 2),
            },
            "risk_metrics": self.risk_metrics.to_dict(),
            "strategy_performance": [sp.to_dict() for sp in self.strategy_performance],
            "week_over_week_change": {
                k: round(v, 2) for k, v in self.week_over_week_change.items()
            },
            "daily_breakdown": self.daily_breakdown,
            "generated_at": self.generated_at.isoformat(),
        }

    def to_markdown(self) -> str:
        """Generate Markdown formatted report."""
        lines = [
            "# 📈 Weekly Performance Report",
            f"",
            f"**Period:** {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            "## 📊 Summary",
            f"",
            f"| Metric | Value | WoW Change |",
            f"|--------|-------|------------|",
            f"| Total PnL | ${self.total_pnl:,.2f} | {self.week_over_week_change.get('total_pnl', 0):+.1f}% |",
            f"| Total Trades | {self.total_trades} | {self.week_over_week_change.get('total_trades', 0):+.1f}% |",
            f"| Win Rate | {self.win_rate:.1f}% | {self.week_over_week_change.get('win_rate', 0):+.1f}% |",
            f"| Avg Daily PnL | ${self.avg_daily_pnl:,.2f} | {self.week_over_week_change.get('avg_daily_pnl', 0):+.1f}% |",
            f"",
            "## 🏆 Best/Worst Days",
            f"",
            f"- **Best Day:** {self.best_day[0].strftime('%Y-%m-%d')} (${self.best_day[1]:,.2f})",
            f"- **Worst Day:** {self.worst_day[0].strftime('%Y-%m-%d')} (${self.worst_day[1]:,.2f})",
            f"",
            "## ⚠️ Risk Metrics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Sharpe Ratio | {self.risk_metrics.sharpe_ratio:.2f} |",
            f"| Volatility | {self.risk_metrics.volatility:.2%} |",
            f"| Max Drawdown | {self.risk_metrics.max_drawdown_pct:.1f}% |",
            f"",
        ]

        # Add strategy performance if available
        if self.strategy_performance:
            lines.extend(
                [
                    "## 🎯 Strategy Performance",
                    f"",
                    "| Strategy | Trades | Win Rate | Total PnL | Sharpe |",
                    "|----------|--------|----------|-----------|--------|",
                ]
            )
            for sp in self.strategy_performance:
                lines.append(
                    f"| {sp.strategy_name} | {sp.total_trades} | {sp.win_rate:.1f}% | "
                    f"${sp.total_pnl:,.2f} | {sp.sharpe_ratio:.2f} |"
                )
            lines.append("")

        lines.extend(
            [
                "---",
                "*Report generated by ChiseAI Automated Reporting System*",
            ]
        )

        return "\n".join(lines)


@dataclass
class AnomalyAlert:
    """Anomaly detection alert."""

    anomaly_type: AnomalyType
    severity: AnomalySeverity
    message: str
    detected_at: datetime
    metric_name: str
    current_value: float
    expected_value: float
    deviation: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "detected_at": self.detected_at.isoformat(),
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "expected_value": round(self.expected_value, 4),
            "deviation": round(self.deviation, 4),
            "details": self.details,
        }

    def to_markdown(self) -> str:
        """Generate Markdown formatted alert."""
        emoji = {
            AnomalySeverity.INFO: "ℹ️",
            AnomalySeverity.WARNING: "⚠️",
            AnomalySeverity.CRITICAL: "🚨",
        }.get(self.severity, "⚠️")

        lines = [
            f"{emoji} **Anomaly Detected: {self.anomaly_type.value.replace('_', ' ').title()}**",
            f"",
            f"**Severity:** {self.severity.value.upper()}",
            f"**Detected:** {self.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            f"**{self.metric_name}:**",
            f"- Current: {self.current_value:.4f}",
            f"- Expected: {self.expected_value:.4f}",
            f"- Deviation: {self.deviation:.2%}",
            f"",
            f"**Message:** {self.message}",
        ]

        if self.details:
            lines.append("")
            lines.append("**Details:**")
            for key, value in self.details.items():
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)


@dataclass
class ReportSchedule:
    """Schedule configuration for automated reports."""

    name: str
    report_type: str  # "daily" or "weekly"
    cron_expression: str
    enabled: bool = True
    discord_webhook: str | None = None
    email_recipients: list[str] = field(default_factory=list)
    output_dir: str = "./reports"
    archive_days: int = 30
    last_run: datetime | None = None
    next_run: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "report_type": self.report_type,
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "discord_webhook": self.discord_webhook,
            "email_recipients": self.email_recipients,
            "output_dir": self.output_dir,
            "archive_days": self.archive_days,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }
