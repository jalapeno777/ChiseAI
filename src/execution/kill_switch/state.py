"""Kill-switch state definitions and data classes.

Provides enums and dataclasses for kill-switch state management,
results tracking, and configuration.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class KillSwitchState(Enum):
    """Kill-switch operational states.

    States:
        ARMED: Kill-switch is active and monitoring for triggers
        TRIGGERED: Kill-switch has been activated, positions being closed
        DISABLED: Kill-switch is disabled, no monitoring or execution
    """

    ARMED = "armed"
    TRIGGERED = "triggered"
    DISABLED = "disabled"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


class CloseStatus(Enum):
    """Status of a position close operation."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    PARTIAL = "partial"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class CloseResult:
    """Result of closing a single position.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Position side ("long" or "short")
        quantity: Quantity closed
        price: Execution price
        status: Close operation status
        order_id: Exchange order ID (if available)
        error: Error message (if failed)
        timestamp: When the close was executed
        pnl: Realized PnL from the close
    """

    symbol: str
    side: str
    quantity: float
    price: float
    status: CloseStatus = CloseStatus.PENDING
    order_id: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value,
            "order_id": self.order_id,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "pnl": self.pnl,
        }


@dataclass
class KillSwitchResult:
    """Result of kill-switch execution.

    Attributes:
        success: Whether kill-switch execution completed successfully
        positions_closed: Number of positions closed
        total_pnl: Total realized PnL from all closes
        timestamp: When kill-switch was triggered
        reason: Reason for kill-switch activation
        triggered_by: Alert or condition that triggered the kill-switch
        environment: Trading environment ("live", "paper", "demo")
        close_results: Detailed results for each position close
        metadata: Additional context (drawdown %, positions before close, etc.)
    """

    success: bool = False
    positions_closed: int = 0
    total_pnl: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""
    triggered_by: str = ""
    environment: str = ""
    close_results: list[CloseResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "positions_closed": self.positions_closed,
            "total_pnl": self.total_pnl,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "environment": self.environment,
            "close_results": [r.to_dict() for r in self.close_results],
            "metadata": self.metadata,
        }


@dataclass
class KillSwitchConfig:
    """Configuration for kill-switch behavior.

    Attributes:
        drawdown_threshold_pct: Drawdown percentage that triggers kill-switch (default 15%)
        rolling_window_hours: Rolling window for drawdown calculation (default 24 hours)
        require_reauthorization: Whether human reauthorization is required after trigger
        max_close_retries: Maximum retries for position close operations
        close_retry_delay_seconds: Delay between close retries
        log_to_influxdb: Whether to log state to InfluxDB
        influxdb_measurement: InfluxDB measurement name for kill-switch metrics
    """

    drawdown_threshold_pct: float = 15.0
    rolling_window_hours: int = 24
    require_reauthorization: bool = True
    max_close_retries: int = 3
    close_retry_delay_seconds: float = 1.0
    log_to_influxdb: bool = True
    influxdb_measurement: str = "kill_switch"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "drawdown_threshold_pct": self.drawdown_threshold_pct,
            "rolling_window_hours": self.rolling_window_hours,
            "require_reauthorization": self.require_reauthorization,
            "max_close_retries": self.max_close_retries,
            "close_retry_delay_seconds": self.close_retry_delay_seconds,
            "log_to_influxdb": self.log_to_influxdb,
            "influxdb_measurement": self.influxdb_measurement,
        }


@dataclass
class KillSwitchLogEntry:
    """Log entry for kill-switch events.

    Attributes:
        event_type: Type of event ("state_change", "trigger", "close", "reauthorize")
        state: Kill-switch state at time of event
        timestamp: When the event occurred
        message: Human-readable event description
        drawdown_pct: Current drawdown percentage (if applicable)
        positions_count: Number of open positions
        portfolio_value: Current portfolio value
        metadata: Additional event context
    """

    event_type: str
    state: KillSwitchState
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    drawdown_pct: float = 0.0
    positions_count: int = 0
    portfolio_value: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "drawdown_pct": self.drawdown_pct,
            "positions_count": self.positions_count,
            "portfolio_value": self.portfolio_value,
            "metadata": self.metadata,
        }
