"""Grafana exporter for live trading state visibility.

Exports live trading state to InfluxDB for Grafana dashboard visibility:
- enabled/disabled state
- last approval date
- total trades
- daily PnL

For ST-EX-002: Bitget Live Trading Gating Implementation (AC #6)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.live_gating.gate_manager import LiveGateManager

logger = logging.getLogger(__name__)


@dataclass
class LiveGatingMetrics:
    """Metrics for live trading gating.

    Attributes:
        timestamp: When metrics were captured
        state: Current live trading state
        is_enabled: Whether live trading is enabled
        last_approval_date: Timestamp of last approval (or None)
        total_trades: Total number of live trades
        daily_pnl: Current day's PnL
        daily_loss_cap: Daily loss cap from config
        approval_count: Number of approvals granted
        rejection_count: Number of rejections
        state_change_count: Number of state transitions
    """

    timestamp: datetime
    state: str
    is_enabled: bool
    last_approval_date: datetime | None
    total_trades: int
    daily_pnl: float
    daily_loss_cap: float
    approval_count: int = 0
    rejection_count: int = 0
    state_change_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "is_enabled": self.is_enabled,
            "last_approval_date": self.last_approval_date.isoformat()
            if self.last_approval_date
            else None,
            "total_trades": self.total_trades,
            "daily_pnl": self.daily_pnl,
            "daily_loss_cap": self.daily_loss_cap,
            "approval_count": self.approval_count,
            "rejection_count": self.rejection_count,
            "state_change_count": self.state_change_count,
        }


class LiveGatingGrafanaExporter:
    """Exporter for live trading state to InfluxDB for Grafana.

    This exporter periodically captures live trading state and exports
    to InfluxDB for real-time Grafana dashboard visibility.

    Metrics exported:
    - live_trading_state: Current state (disabled/pending/approved/active)
    - live_trading_enabled: Boolean enabled status
    - last_approval_timestamp: Unix timestamp of last approval
    - total_live_trades: Cumulative trade count
    - daily_pnl: Current day's profit/loss
    - daily_loss_remaining: Remaining loss capacity before cap

    Usage:
        exporter = LiveGatingGrafanaExporter(gate_manager)
        await exporter.start()
        # ... metrics automatically exported ...
        await exporter.stop()
    """

    DEFAULT_INTERVAL = 30.0  # seconds between exports
    MEASUREMENT = "live_trading_gating"

    def __init__(
        self,
        gate_manager: LiveGateManager | None = None,
        influxdb_client: Any | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
        interval: float = DEFAULT_INTERVAL,
    ) -> None:
        """Initialize Grafana exporter.

        Args:
            gate_manager: Live gate manager to monitor
            influxdb_client: InfluxDB client (optional)
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            interval: Export interval in seconds
        """
        self._gate_manager = gate_manager
        self._client = influxdb_client
        self._bucket = bucket
        self._org = org
        self._interval = interval
        self._write_api = None
        self._measurement = self.MEASUREMENT  # Instance variable for consistency

        # Statistics
        self._export_count = 0
        self._last_export_time: datetime | None = None
        self._failed_exports = 0

        # Counters (in case gate_manager not available)
        self._trade_count = 0
        self._approval_count = 0
        self._rejection_count = 0

        logger.info(
            f"LiveGatingGrafanaExporter initialized: "
            f"measurement={self._measurement}, interval={interval}s"
        )

    async def _get_write_api(self) -> Any:
        """Get or create InfluxDB write API."""
        if self._write_api is None and self._client is not None:
            self._write_api = self._client.write_api()
        return self._write_api

    def _create_state_point(
        self,
        state: str,
        is_enabled: bool,
        last_approval_date: datetime | None,
    ) -> Any:
        """Create InfluxDB point for state metrics.

        Args:
            state: Current state string
            is_enabled: Whether live trading is enabled
            last_approval_date: Last approval timestamp

        Returns:
            InfluxDB Point
        """
        try:
            from influxdb_client import Point

            point = Point(self.MEASUREMENT)
            point = point.tag("metric_type", "state")
            point = point.tag("state", state)

            # Fields
            point = point.field("is_enabled", 1.0 if is_enabled else 0.0)
            point = point.field("state_value", self._state_to_numeric(state))

            if last_approval_date:
                point = point.field(
                    "last_approval_timestamp", last_approval_date.timestamp()
                )
                # Days since last approval
                days_since = (datetime.now(UTC) - last_approval_date).days
                point = point.field("days_since_approval", float(days_since))
            else:
                point = point.field("last_approval_timestamp", 0.0)
                point = point.field("days_since_approval", -1.0)

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            return {
                "measurement": self.MEASUREMENT,
                "tags": {"metric_type": "state", "state": state},
                "fields": {
                    "is_enabled": 1.0 if is_enabled else 0.0,
                    "state_value": self._state_to_numeric(state),
                    "last_approval_timestamp": last_approval_date.timestamp()
                    if last_approval_date
                    else 0.0,
                },
                "time": datetime.now(UTC).isoformat(),
            }

    def _create_activity_point(
        self,
        total_trades: int,
        daily_pnl: float,
        daily_loss_cap: float,
    ) -> Any:
        """Create InfluxDB point for activity metrics.

        Args:
            total_trades: Total trade count
            daily_pnl: Current day's PnL
            daily_loss_cap: Daily loss cap

        Returns:
            InfluxDB Point
        """
        try:
            from influxdb_client import Point

            point = Point(self.MEASUREMENT)
            point = point.tag("metric_type", "activity")

            # Fields
            point = point.field("total_trades", float(total_trades))
            point = point.field("daily_pnl", daily_pnl)
            point = point.field("daily_loss_cap", daily_loss_cap)
            point = point.field("daily_loss_remaining", daily_loss_cap + daily_pnl)

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            return {
                "measurement": self.MEASUREMENT,
                "tags": {"metric_type": "activity"},
                "fields": {
                    "total_trades": float(total_trades),
                    "daily_pnl": daily_pnl,
                    "daily_loss_cap": daily_loss_cap,
                    "daily_loss_remaining": daily_loss_cap + daily_pnl,
                },
                "time": datetime.now(UTC).isoformat(),
            }

    def _create_counts_point(
        self,
        approval_count: int,
        rejection_count: int,
        state_change_count: int,
    ) -> Any:
        """Create InfluxDB point for count metrics.

        Args:
            approval_count: Number of approvals
            rejection_count: Number of rejections
            state_change_count: Number of state changes

        Returns:
            InfluxDB Point
        """
        try:
            from influxdb_client import Point

            point = Point(self.MEASUREMENT)
            point = point.tag("metric_type", "counts")

            # Fields
            point = point.field("approval_count", float(approval_count))
            point = point.field("rejection_count", float(rejection_count))
            point = point.field("state_change_count", float(state_change_count))

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            return {
                "measurement": self.MEASUREMENT,
                "tags": {"metric_type": "counts"},
                "fields": {
                    "approval_count": float(approval_count),
                    "rejection_count": float(rejection_count),
                    "state_change_count": float(state_change_count),
                },
                "time": datetime.now(UTC).isoformat(),
            }

    def _state_to_numeric(self, state: str) -> float:
        """Convert state string to numeric value for Grafana.

        Args:
            state: State string

        Returns:
            Numeric value (0=disabled, 1=pending, 2=approved, 3=active)
        """
        mapping = {
            "disabled": 0.0,
            "pending_approval": 1.0,
            "approved": 2.0,
            "active": 3.0,
        }
        return mapping.get(state, -1.0)

    async def export_metrics(self) -> bool:
        """Export current metrics to InfluxDB.

        Returns:
            True if export successful
        """
        try:
            # Get current state from gate manager if available
            if self._gate_manager is not None:
                status = self._gate_manager.get_status()
                state = status.get("state", "disabled")
                is_enabled = status.get("is_live_enabled", False)

                # Get last approval date
                last_approval = status.get("last_approval")
                last_approval_date = None
                if last_approval:
                    ts_str = last_approval.get("timestamp")
                    if ts_str:
                        last_approval_date = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )

                # Get daily PnL
                daily_pnl = status.get("daily_pnl", 0.0)
                daily_loss_cap = status.get("config", {}).get("daily_loss_cap", 1000.0)

                # Get history counts
                state_history_count = status.get("state_history_count", 0)
            else:
                # Default values if no gate manager
                state = "disabled"
                is_enabled = False
                last_approval_date = None
                daily_pnl = 0.0
                daily_loss_cap = 1000.0
                state_history_count = 0

            # Create points
            state_point = self._create_state_point(
                state=state,
                is_enabled=is_enabled,
                last_approval_date=last_approval_date,
            )

            activity_point = self._create_activity_point(
                total_trades=self._trade_count,
                daily_pnl=daily_pnl,
                daily_loss_cap=daily_loss_cap,
            )

            counts_point = self._create_counts_point(
                approval_count=self._approval_count,
                rejection_count=self._rejection_count,
                state_change_count=state_history_count,
            )

            # Write to InfluxDB
            write_api = await self._get_write_api()
            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=[state_point, activity_point, counts_point],
                )

            self._export_count += 1
            self._last_export_time = datetime.now(UTC)

            logger.debug(
                f"Exported live gating metrics: state={state}, enabled={is_enabled}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            self._failed_exports += 1
            return False

    async def start(self) -> None:
        """Start periodic export loop.

        Note: This method should be called from an async context.
        For sync contexts, use export_metrics() directly.
        """
        import asyncio

        self._running = True

        async def export_loop():
            while self._running:
                try:
                    await self.export_metrics()
                    await asyncio.sleep(self._interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Export loop error: {e}")
                    await asyncio.sleep(self._interval)

        self._export_task = asyncio.create_task(export_loop())
        logger.info("Live gating Grafana exporter started")

    async def stop(self) -> None:
        """Stop periodic export loop."""
        self._running = False

        if hasattr(self, "_export_task") and self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Final export
        await self.export_metrics()

        logger.info("Live gating Grafana exporter stopped")

    def record_trade(self) -> None:
        """Record a trade occurrence."""
        self._trade_count += 1

    def record_approval(self) -> None:
        """Record an approval occurrence."""
        self._approval_count += 1

    def record_rejection(self) -> None:
        """Record a rejection occurrence."""
        self._rejection_count += 1

    def get_stats(self) -> dict[str, Any]:
        """Get exporter statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "export_count": self._export_count,
            "last_export_time": self._last_export_time.isoformat()
            if self._last_export_time
            else None,
            "failed_exports": self._failed_exports,
            "interval": self._interval,
            "measurement": self.MEASUREMENT,
            "trade_count": self._trade_count,
            "approval_count": self._approval_count,
            "rejection_count": self._rejection_count,
        }

    def get_metrics(self) -> LiveGatingMetrics | None:
        """Get current metrics snapshot.

        Returns:
            LiveGatingMetrics if gate manager available, None otherwise
        """
        if self._gate_manager is None:
            return None

        try:
            status = self._gate_manager.get_status()
            last_approval = status.get("last_approval")
            last_approval_date = None
            if last_approval:
                ts_str = last_approval.get("timestamp")
                if ts_str:
                    last_approval_date = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00")
                    )

            return LiveGatingMetrics(
                timestamp=datetime.now(UTC),
                state=status.get("state", "disabled"),
                is_enabled=status.get("is_live_enabled", False),
                last_approval_date=last_approval_date,
                total_trades=self._trade_count,
                daily_pnl=status.get("daily_pnl", 0.0),
                daily_loss_cap=status.get("config", {}).get("daily_loss_cap", 1000.0),
                approval_count=self._approval_count,
                rejection_count=self._rejection_count,
                state_change_count=status.get("state_history_count", 0),
            )
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return None
