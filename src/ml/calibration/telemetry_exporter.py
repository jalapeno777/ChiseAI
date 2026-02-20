"""InfluxDB Telemetry Exporter for Calibration System.

This module provides the CalibrationTelemetryExporter class for exporting
calibration metrics, threshold changes, and health status to InfluxDB for
Grafana dashboard visibility.

Exported Metrics:
- calibration_threshold: Current threshold values per signal type
- calibration_ece: ECE (Expected Calibration Error) values
- calibration_adjustment: Threshold adjustment events
- calibration_health: Overall calibration health status
- calibration_adjustment_velocity: Adjustment frequency metrics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ml.calibration.controller import ThresholdController
    from ml.calibration.dynamic import DynamicThresholdAdjuster, ThresholdAdjustment

logger = logging.getLogger(__name__)


@dataclass
class CalibrationTelemetryConfig:
    """Configuration for calibration telemetry exporter.

    Attributes:
        bucket: InfluxDB bucket name
        org: InfluxDB organization
        measurement_prefix: Prefix for measurement names
        retention_days: Data retention period in days
        batch_size: Number of points to batch before writing
        flush_interval: Seconds between forced flushes
    """

    bucket: str = "chiseai"
    org: str = "chiseai"
    measurement_prefix: str = "calibration"
    retention_days: int = 90
    batch_size: int = 100
    flush_interval: float = 60.0


@dataclass
class CalibrationHealthMetrics:
    """Health metrics for calibration system.

    Attributes:
        timestamp: When metrics were captured
        signal_type: Signal type (LONG, SHORT, SCALP) or 'all'
        ece: Current Expected Calibration Error
        threshold: Current threshold value
        health_status: 'well_calibrated' or 'poorly_calibrated'
        adjustment_count_1h: Number of adjustments in last hour
        adjustment_count_24h: Number of adjustments in last 24 hours
        stability_score: Lower is better (0-100 scale)
    """

    timestamp: datetime
    signal_type: str
    ece: float
    threshold: float
    health_status: str
    adjustment_count_1h: int = 0
    adjustment_count_24h: int = 0
    stability_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "ece": round(self.ece, 6),
            "threshold": round(self.threshold, 4),
            "health_status": self.health_status,
            "adjustment_count_1h": self.adjustment_count_1h,
            "adjustment_count_24h": self.adjustment_count_24h,
            "stability_score": round(self.stability_score, 2),
        }


class CalibrationTelemetryExporter:
    """Export calibration metrics to InfluxDB for Grafana visibility.

        This exporter provides methods to export calibration system metrics
    to InfluxDB for real-time dashboard monitoring:
        - Threshold values per signal type
        - ECE trends
        - Adjustment events
        - Health status

        Usage:
            exporter = CalibrationTelemetryExporter(influxdb_client)
            await exporter.export_thresholds(controller)
            await exporter.export_ece_values(controller, signal_type="LONG")
            await exporter.export_adjustment_event(adjustment)
            await exporter.export_health_status(metrics)
    """

    def __init__(
        self,
        influxdb_client: Any | None = None,
        config: CalibrationTelemetryConfig | None = None,
    ) -> None:
        """Initialize telemetry exporter.

        Args:
            influxdb_client: InfluxDB client instance (optional)
            config: Telemetry configuration (optional, uses defaults)
        """
        self._client = influxdb_client
        self.config = config or CalibrationTelemetryConfig()
        self._write_api = None
        self._batch: list[Any] = []

        # Statistics
        self._export_count = 0
        self._failed_exports = 0
        self._last_export_time: datetime | None = None

        logger.info(
            f"CalibrationTelemetryExporter initialized: "
            f"bucket={self.config.bucket}, prefix={self.config.measurement_prefix}"
        )

    async def _get_write_api(self) -> Any:
        """Get or create InfluxDB write API."""
        if self._write_api is None and self._client is not None:
            try:
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.warning(f"Could not create InfluxDB write API: {e}")
        return self._write_api

    async def _write_point(self, point: Any) -> bool:
        """Write a single point to InfluxDB with batching.

        Args:
            point: InfluxDB Point to write

        Returns:
            True if queued successfully (or written)
        """
        if self._client is None:
            logger.debug("No InfluxDB client, skipping write")
            return False

        try:
            self._batch.append(point)

            # Flush if batch is full
            if len(self._batch) >= self.config.batch_size:
                await self._flush_batch()

            return True

        except Exception as e:
            logger.warning(f"Failed to queue point: {e}")
            self._failed_exports += 1
            return False

    async def _flush_batch(self) -> bool:
        """Flush pending batch to InfluxDB.

        Returns:
            True if flush successful
        """
        if not self._batch or self._client is None:
            return False

        try:
            write_api = await self._get_write_api()
            if write_api is None:
                return False

            write_api.write(
                bucket=self.config.bucket,
                org=self.config.org,
                record=self._batch,
            )

            self._export_count += len(self._batch)
            self._last_export_time = datetime.now(UTC)
            self._batch.clear()

            return True

        except Exception as e:
            logger.warning(f"Failed to flush batch to InfluxDB: {e}")
            self._failed_exports += len(self._batch)
            self._batch.clear()
            return False

    async def export_thresholds(self, controller: ThresholdController) -> bool:
        """Export current threshold values for all signal types.

        Args:
            controller: ThresholdController with current thresholds

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            timestamp = datetime.now(UTC)
            thresholds = controller.current_thresholds

            for signal_type, threshold in thresholds.items():
                point = (
                    Point(f"{self.config.measurement_prefix}_threshold")
                    .tag("signal_type", signal_type)
                    .field("value", float(threshold))
                    .time(timestamp)
                )

                await self._write_point(point)

            logger.debug(f"Exported thresholds: {thresholds}")
            return True

        except ImportError:
            logger.debug("influxdb-client not installed, skipping export")
            return False

        except Exception as e:
            logger.warning(f"Failed to export thresholds: {e}")
            return False

    async def export_ece_values(
        self,
        controller: ThresholdController,
        signal_type: str | None = None,
    ) -> bool:
        """Export ECE values for signal types.

        Args:
            controller: ThresholdController with ECE data
            signal_type: Specific signal type, or None for all

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            timestamp = datetime.now(UTC)
            signal_types = [signal_type] if signal_type else ["LONG", "SHORT", "SCALP"]

            for st in signal_types:
                ece = controller._last_ece.get(st)
                if ece is not None:
                    point = (
                        Point(f"{self.config.measurement_prefix}_ece")
                        .tag("signal_type", st)
                        .field("value", float(ece))
                        .time(timestamp)
                    )

                    await self._write_point(point)

            logger.debug(f"Exported ECE values for {signal_types}")
            return True

        except ImportError:
            logger.debug("influxdb-client not installed, skipping export")
            return False

        except Exception as e:
            logger.warning(f"Failed to export ECE values: {e}")
            return False

    async def export_adjustment_event(
        self,
        adjustment: ThresholdAdjustment,
    ) -> bool:
        """Export a threshold adjustment event.

        Args:
            adjustment: ThresholdAdjustment record to export

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            point = (
                Point(f"{self.config.measurement_prefix}_adjustment")
                .tag("signal_type", adjustment.signal_type)
                .field("old_threshold", float(adjustment.old_threshold))
                .field("new_threshold", float(adjustment.new_threshold))
                .field("change_amount", float(adjustment.change_amount))
                .field("ece_before", float(adjustment.ece_before))
                .field(
                    "ece_after",
                    (
                        float(adjustment.ece_after)
                        if adjustment.ece_after is not None
                        else -1.0
                    ),
                )
                .field("reason", adjustment.reason[:255])  # Limit length
                .time(adjustment.timestamp)
            )

            await self._write_point(point)

            logger.debug(
                f"Exported adjustment event: {adjustment.signal_type} "
                f"{adjustment.old_threshold:.2f} -> {adjustment.new_threshold:.2f}"
            )
            return True

        except ImportError:
            logger.debug("influxdb-client not installed, skipping export")
            return False

        except Exception as e:
            logger.warning(f"Failed to export adjustment event: {e}")
            return False

    async def export_health_status(self, metrics: CalibrationHealthMetrics) -> bool:
        """Export calibration health status.

        Args:
            metrics: CalibrationHealthMetrics to export

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            point = (
                Point(f"{self.config.measurement_prefix}_health")
                .tag("signal_type", metrics.signal_type)
                .tag("health_status", metrics.health_status)
                .field("ece", float(metrics.ece))
                .field("threshold", float(metrics.threshold))
                .field("adjustment_count_1h", int(metrics.adjustment_count_1h))
                .field("adjustment_count_24h", int(metrics.adjustment_count_24h))
                .field("stability_score", float(metrics.stability_score))
                .time(metrics.timestamp)
            )

            await self._write_point(point)

            logger.debug(f"Exported health status: {metrics.health_status}")
            return True

        except ImportError:
            logger.debug("influxdb-client not installed, skipping export")
            return False

        except Exception as e:
            logger.warning(f"Failed to export health status: {e}")
            return False

    async def export_adjustment_velocity(
        self,
        adjuster: DynamicThresholdAdjuster,
        signal_type: str | None = None,
    ) -> bool:
        """Export adjustment velocity metrics (adjustments per hour).

        Args:
            adjuster: DynamicThresholdAdjuster with adjustment history
            signal_type: Specific signal type, or None for all

        Returns:
            True if export successful
        """
        try:
            from influxdb_client import Point

            timestamp = datetime.now(UTC)
            signal_types = [signal_type] if signal_type else ["LONG", "SHORT", "SCALP"]

            for st in signal_types:
                # Count adjustments in last hour and last 24 hours
                hour_ago = timestamp - timedelta(hours=1)
                day_ago = timestamp - timedelta(hours=24)

                adjustments_1h = sum(
                    1
                    for adj in adjuster.adjustment_history
                    if adj.signal_type == st and adj.timestamp >= hour_ago
                )
                adjustments_24h = sum(
                    1
                    for adj in adjuster.adjustment_history
                    if adj.signal_type == st and adj.timestamp >= day_ago
                )

                # Calculate velocity (adjustments per hour over 24h period)
                velocity_24h = adjustments_24h / 24.0 if adjustments_24h > 0 else 0.0

                point = (
                    Point(f"{self.config.measurement_prefix}_adjustment_velocity")
                    .tag("signal_type", st)
                    .field("adjustments_1h", int(adjustments_1h))
                    .field("adjustments_24h", int(adjustments_24h))
                    .field("velocity_24h", float(velocity_24h))
                    .time(timestamp)
                )

                await self._write_point(point)

            logger.debug(f"Exported adjustment velocity for {signal_types}")
            return True

        except ImportError:
            logger.debug("influxdb-client not installed, skipping export")
            return False

        except Exception as e:
            logger.warning(f"Failed to export adjustment velocity: {e}")
            return False

    async def flush(self) -> bool:
        """Flush any pending metrics to InfluxDB.

        Returns:
            True if flush successful or no pending data
        """
        return await self._flush_batch()

    def get_statistics(self) -> dict[str, Any]:
        """Get export statistics.

        Returns:
            Dictionary with export statistics
        """
        return {
            "export_count": self._export_count,
            "failed_exports": self._failed_exports,
            "pending_batch_size": len(self._batch),
            "last_export_time": (
                self._last_export_time.isoformat() if self._last_export_time else None
            ),
        }


__all__ = [
    "CalibrationTelemetryExporter",
    "CalibrationTelemetryConfig",
    "CalibrationHealthMetrics",
]
