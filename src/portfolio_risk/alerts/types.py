"""Risk threshold alert system for portfolio management.

Provides automated alerts for risk threshold breaches including:
- Exposure threshold alerts (configurable, default 80%)
- Margin utilization alerts (configurable thresholds)
- Concentration risk alerts (configurable thresholds)
- Kill-switch activation alerts (immediate)

Alert suppression prevents spam with configurable minimum interval.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


class AlertType(Enum):
    """Types of risk alerts."""

    EXPOSURE = "exposure"
    MARGIN_UTILIZATION = "margin_utilization"
    CONCENTRATION = "concentration"
    KILL_SWITCH = "kill_switch"
    POSITION_COUNT = "position_count"
    # Paper trading specific alerts (ST-PAPER-008)
    REDIS_FAILURE = "redis_failure"
    PAPER_SYNC_DIVERGENCE = "paper_sync_divergence"
    VALIDATION_FAILURE_RATE = "validation_failure_rate"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class RiskAlert:
    """A risk threshold alert.

    Attributes:
        alert_type: Type of alert (exposure, margin, concentration, kill_switch)
        severity: Alert severity level
        message: Human-readable alert message
        threshold: Threshold value that was breached
        current_value: Current value that triggered the alert
        portfolio_id: Portfolio identifier
        timestamp: When the alert was triggered
        metadata: Additional alert metadata
    """

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    threshold: float
    current_value: float
    portfolio_id: str = "default"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "threshold": round(self.threshold, 4),
            "current_value": round(self.current_value, 4),
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @property
    def alert_key(self) -> str:
        """Generate unique key for alert deduplication.

        Returns:
            String key combining alert type and portfolio
        """
        return f"{self.portfolio_id}:{self.alert_type.value}"


@dataclass
class AlertThresholds:
    """Configurable alert thresholds.

    Attributes:
        exposure_threshold_pct: Exposure threshold percentage (default 80%)
        margin_utilization_threshold_pct: Margin utilization threshold (default 80%)
        concentration_threshold_pct: Concentration risk threshold (default 50%)
        min_alert_interval_seconds: Minimum seconds between same alert type
            (default 300 = 5 min)
    """

    exposure_threshold_pct: float = 80.0
    margin_utilization_threshold_pct: float = 80.0
    concentration_threshold_pct: float = 50.0
    min_alert_interval_seconds: int = 300  # 5 minutes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "exposure_threshold_pct": self.exposure_threshold_pct,
            "margin_utilization_threshold_pct": self.margin_utilization_threshold_pct,
            "concentration_threshold_pct": self.concentration_threshold_pct,
            "min_alert_interval_seconds": self.min_alert_interval_seconds,
        }


@dataclass
class AlertState:
    """Tracks alert state for suppression logic.

    Attributes:
        last_alert_time: Timestamp of last alert sent
        alert_count: Number of alerts sent
        suppressed_count: Number of suppressed alerts
    """

    last_alert_time: datetime | None = None
    alert_count: int = 0
    suppressed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "last_alert_time": (
                self.last_alert_time.isoformat() if self.last_alert_time else None
            ),
            "alert_count": self.alert_count,
            "suppressed_count": self.suppressed_count,
        }
