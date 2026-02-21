"""Anomaly detection system for ChiseAI.

Detects unusual patterns in trading data:
- PnL spikes (3 std dev from mean)
- Volume spikes (>200% of average)
- Error rate increases (>5x baseline)
- Drawdown spikes
- Latency spikes

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import AnomalyAlert, AnomalySeverity, AnomalyType

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detect anomalies in trading and system metrics.

    Monitors key metrics and detects deviations from normal patterns:
    - PnL anomalies (3 standard deviations from mean)
    - Volume spikes (>200% of average)
    - Error rate increases (>5x baseline)
    - Drawdown spikes
    - Latency spikes

    Attributes:
        influxdb_client: InfluxDB client for querying data
        bucket: InfluxDB bucket name
        org: InfluxDB organization
        baseline_window_days: Days of history for baseline calculation
    """

    # Detection thresholds
    PNL_STD_DEV_THRESHOLD = 3.0  # 3 standard deviations
    VOLUME_SPIKE_THRESHOLD = 2.0  # 200% of average
    ERROR_RATE_SPIKE_THRESHOLD = 5.0  # 5x baseline
    DRAWDOWN_SPIKE_THRESHOLD = 2.0  # 2x average drawdown
    LATENCY_SPIKE_THRESHOLD = 3.0  # 3x average latency

    def __init__(
        self,
        influxdb_client: Any | None = None,
        bucket: str = "chiseai",
        org: str = "chiseai",
        baseline_window_days: int = 30,
    ) -> None:
        """Initialize anomaly detector.

        Args:
            influxdb_client: InfluxDB client instance
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            baseline_window_days: Days of history for baseline calculation
        """
        self._client = influxdb_client
        self._bucket = bucket
        self._org = org
        self._baseline_window_days = baseline_window_days
        self._query_api = None

        # Alert history to prevent duplicate alerts
        self._alert_history: list[dict[str, Any]] = []
        self._max_history = 1000

        logger.info(
            f"AnomalyDetector initialized: bucket={bucket}, "
            f"baseline_window={baseline_window_days}d"
        )

    def _get_query_api(self) -> Any:
        """Get or create InfluxDB query API."""
        if self._query_api is None and self._client is not None:
            self._query_api = self._client.query_api()
        return self._query_api

    async def detect_all(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Run all anomaly detection checks.

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of detected anomalies
        """
        alerts = []

        # Run all detection methods
        alerts.extend(await self.detect_pnl_anomalies(lookback_hours))
        alerts.extend(await self.detect_volume_spikes(lookback_hours))
        alerts.extend(await self.detect_error_rate_spikes(lookback_hours))
        alerts.extend(await self.detect_drawdown_spikes(lookback_hours))
        alerts.extend(await self.detect_latency_spikes(lookback_hours))

        # Filter out duplicates
        unique_alerts = self._filter_duplicates(alerts)

        if unique_alerts:
            logger.warning(f"Detected {len(unique_alerts)} anomalies")

        return unique_alerts

    async def detect_pnl_anomalies(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Detect unusual PnL (3 std dev from mean).

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of PnL anomaly alerts
        """
        logger.debug("Detecting PnL anomalies")

        try:
            # Get baseline PnL statistics
            baseline_pnls = await self._query_baseline_pnls()
            if len(baseline_pnls) < 10:
                logger.debug("Insufficient baseline data for PnL anomaly detection")
                return []

            mean_pnl = statistics.mean(baseline_pnls)
            std_pnl = statistics.stdev(baseline_pnls) if len(baseline_pnls) > 1 else 0.0

            if std_pnl == 0:
                return []

            # Get current PnL
            current_pnl = await self._query_current_pnl(lookback_hours)

            # Check for anomaly
            deviation = abs(current_pnl - mean_pnl) / std_pnl if std_pnl > 0 else 0.0

            if deviation >= self.PNL_STD_DEV_THRESHOLD:
                severity = (
                    AnomalySeverity.CRITICAL
                    if deviation >= 5.0
                    else AnomalySeverity.WARNING
                )

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.PNL_SPIKE,
                    severity=severity,
                    message=f"Unusual PnL detected: {deviation:.1f} standard deviations from mean",
                    detected_at=datetime.now(UTC),
                    metric_name="PnL",
                    current_value=current_pnl,
                    expected_value=mean_pnl,
                    deviation=deviation,
                    details={
                        "std_dev": std_pnl,
                        "threshold": self.PNL_STD_DEV_THRESHOLD,
                        "lookback_hours": lookback_hours,
                    },
                )

                self._record_alert(alert)
                return [alert]

        except Exception as e:
            logger.error(f"Error detecting PnL anomalies: {e}")

        return []

    async def detect_volume_spikes(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Detect volume spikes (>200% of average).

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of volume spike alerts
        """
        logger.debug("Detecting volume spikes")

        try:
            # Get baseline volume
            baseline_volumes = await self._query_baseline_volumes()
            if len(baseline_volumes) < 10:
                logger.debug("Insufficient baseline data for volume spike detection")
                return []

            avg_volume = statistics.mean(baseline_volumes)

            if avg_volume == 0:
                return []

            # Get current volume
            current_volume = await self._query_current_volume(lookback_hours)

            # Check for spike
            ratio = current_volume / avg_volume if avg_volume > 0 else 0.0

            if ratio >= self.VOLUME_SPIKE_THRESHOLD:
                severity = (
                    AnomalySeverity.CRITICAL
                    if ratio >= 5.0
                    else AnomalySeverity.WARNING
                )

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.VOLUME_SPIKE,
                    severity=severity,
                    message=f"Volume spike detected: {ratio:.1f}x average volume",
                    detected_at=datetime.now(UTC),
                    metric_name="Trading Volume",
                    current_value=current_volume,
                    expected_value=avg_volume,
                    deviation=ratio - 1.0,
                    details={
                        "avg_volume": avg_volume,
                        "threshold": self.VOLUME_SPIKE_THRESHOLD,
                        "lookback_hours": lookback_hours,
                    },
                )

                self._record_alert(alert)
                return [alert]

        except Exception as e:
            logger.error(f"Error detecting volume spikes: {e}")

        return []

    async def detect_error_rate_spikes(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Detect error rate increases (>5x baseline).

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of error rate spike alerts
        """
        logger.debug("Detecting error rate spikes")

        try:
            # Get baseline error rate
            baseline_errors = await self._query_baseline_error_rates()
            if len(baseline_errors) < 10:
                logger.debug("Insufficient baseline data for error rate detection")
                return []

            avg_error_rate = statistics.mean(baseline_errors)

            if avg_error_rate == 0:
                # If no errors in baseline, any error is a spike
                avg_error_rate = 0.001  # Small non-zero value

            # Get current error rate
            current_error_rate = await self._query_current_error_rate(lookback_hours)

            # Check for spike
            ratio = current_error_rate / avg_error_rate if avg_error_rate > 0 else 0.0

            if ratio >= self.ERROR_RATE_SPIKE_THRESHOLD:
                severity = (
                    AnomalySeverity.CRITICAL
                    if ratio >= 10.0
                    else AnomalySeverity.WARNING
                )

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.ERROR_RATE_SPIKE,
                    severity=severity,
                    message=f"Error rate spike detected: {ratio:.1f}x baseline",
                    detected_at=datetime.now(UTC),
                    metric_name="Error Rate",
                    current_value=current_error_rate,
                    expected_value=avg_error_rate,
                    deviation=ratio - 1.0,
                    details={
                        "baseline_error_rate": avg_error_rate,
                        "threshold": self.ERROR_RATE_SPIKE_THRESHOLD,
                        "lookback_hours": lookback_hours,
                    },
                )

                self._record_alert(alert)
                return [alert]

        except Exception as e:
            logger.error(f"Error detecting error rate spikes: {e}")

        return []

    async def detect_drawdown_spikes(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Detect drawdown spikes.

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of drawdown spike alerts
        """
        logger.debug("Detecting drawdown spikes")

        try:
            # Get baseline drawdown
            baseline_drawdowns = await self._query_baseline_drawdowns()
            if len(baseline_drawdowns) < 10:
                logger.debug("Insufficient baseline data for drawdown detection")
                return []

            avg_drawdown = statistics.mean(baseline_drawdowns)

            if avg_drawdown == 0:
                avg_drawdown = 0.001  # Small non-zero value

            # Get current drawdown
            current_drawdown = await self._query_current_drawdown(lookback_hours)

            # Check for spike
            ratio = current_drawdown / avg_drawdown if avg_drawdown > 0 else 0.0

            if ratio >= self.DRAWDOWN_SPIKE_THRESHOLD:
                severity = (
                    AnomalySeverity.CRITICAL
                    if ratio >= 5.0 or current_drawdown > 0.1  # 10% drawdown
                    else AnomalySeverity.WARNING
                )

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.DRAWDOWN_SPIKE,
                    severity=severity,
                    message=f"Drawdown spike detected: {ratio:.1f}x average ({current_drawdown:.1%})",
                    detected_at=datetime.now(UTC),
                    metric_name="Drawdown",
                    current_value=current_drawdown,
                    expected_value=avg_drawdown,
                    deviation=ratio - 1.0,
                    details={
                        "avg_drawdown": avg_drawdown,
                        "threshold": self.DRAWDOWN_SPIKE_THRESHOLD,
                        "lookback_hours": lookback_hours,
                    },
                )

                self._record_alert(alert)
                return [alert]

        except Exception as e:
            logger.error(f"Error detecting drawdown spikes: {e}")

        return []

    async def detect_latency_spikes(
        self,
        lookback_hours: int = 1,
    ) -> list[AnomalyAlert]:
        """Detect latency spikes.

        Args:
            lookback_hours: Hours to look back for current metrics

        Returns:
            List of latency spike alerts
        """
        logger.debug("Detecting latency spikes")

        try:
            # Get baseline latency
            baseline_latencies = await self._query_baseline_latencies()
            if len(baseline_latencies) < 10:
                logger.debug("Insufficient baseline data for latency detection")
                return []

            avg_latency = statistics.mean(baseline_latencies)

            if avg_latency == 0:
                avg_latency = 1.0  # 1ms default

            # Get current latency
            current_latency = await self._query_current_latency(lookback_hours)

            # Check for spike
            ratio = current_latency / avg_latency if avg_latency > 0 else 0.0

            if ratio >= self.LATENCY_SPIKE_THRESHOLD:
                severity = (
                    AnomalySeverity.CRITICAL
                    if ratio >= 10.0 or current_latency > 1000  # >1s
                    else AnomalySeverity.WARNING
                )

                alert = AnomalyAlert(
                    anomaly_type=AnomalyType.LATENCY_SPIKE,
                    severity=severity,
                    message=f"Latency spike detected: {ratio:.1f}x average ({current_latency:.0f}ms)",
                    detected_at=datetime.now(UTC),
                    metric_name="Latency",
                    current_value=current_latency,
                    expected_value=avg_latency,
                    deviation=ratio - 1.0,
                    details={
                        "avg_latency_ms": avg_latency,
                        "threshold": self.LATENCY_SPIKE_THRESHOLD,
                        "lookback_hours": lookback_hours,
                    },
                )

                self._record_alert(alert)
                return [alert]

        except Exception as e:
            logger.error(f"Error detecting latency spikes: {e}")

        return []

    # InfluxDB Query Methods

    async def _query_baseline_pnls(self) -> list[float]:
        """Query baseline PnL values."""
        return await self._query_baseline_metric("paper_portfolio", "total_pnl")

    async def _query_current_pnl(self, lookback_hours: int) -> float:
        """Query current PnL."""
        return await self._query_current_metric(
            "paper_portfolio", "total_pnl", lookback_hours
        )

    async def _query_baseline_volumes(self) -> list[float]:
        """Query baseline volume values."""
        return await self._query_baseline_metric("paper_trades", "quantity")

    async def _query_current_volume(self, lookback_hours: int) -> float:
        """Query current volume."""
        return await self._query_current_metric(
            "paper_trades", "quantity", lookback_hours
        )

    async def _query_baseline_error_rates(self) -> list[float]:
        """Query baseline error rates."""
        # Query from health monitoring data
        return await self._query_baseline_metric("health_checks", "error_rate")

    async def _query_current_error_rate(self, lookback_hours: int) -> float:
        """Query current error rate."""
        return await self._query_current_metric(
            "health_checks", "error_rate", lookback_hours
        )

    async def _query_baseline_drawdowns(self) -> list[float]:
        """Query baseline drawdown values."""
        return await self._query_baseline_metric("paper_portfolio", "drawdown_pct")

    async def _query_current_drawdown(self, lookback_hours: int) -> float:
        """Query current drawdown."""
        return await self._query_current_metric(
            "paper_portfolio", "drawdown_pct", lookback_hours
        )

    async def _query_baseline_latencies(self) -> list[float]:
        """Query baseline latency values."""
        return await self._query_baseline_metric("paper_trades", "latency_ms")

    async def _query_current_latency(self, lookback_hours: int) -> float:
        """Query current latency."""
        return await self._query_current_metric(
            "paper_trades", "latency_ms", lookback_hours
        )

    async def _query_baseline_metric(
        self,
        measurement: str,
        field: str,
    ) -> list[float]:
        """Query baseline metric values from InfluxDB.

        Args:
            measurement: InfluxDB measurement name
            field: Field to query

        Returns:
            List of metric values
        """
        query_api = self._get_query_api()
        if query_api is None:
            return []

        start_time = (
            datetime.now(UTC) - timedelta(days=self._baseline_window_days)
        ).isoformat()
        end_time = datetime.now(UTC).isoformat()

        query = f"""
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "{measurement}")
            |> filter(fn: (r) => r._field == "{field}")
            |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
        """

        try:
            tables = query_api.query(query, org=self._org)
            values = []
            for table in tables:
                for record in table.records:
                    value = record.get_value()
                    if value is not None:
                        values.append(float(value))
            return values
        except Exception as e:
            logger.warning(
                f"Failed to query baseline metric {measurement}.{field}: {e}"
            )
            return []

    async def _query_current_metric(
        self,
        measurement: str,
        field: str,
        lookback_hours: int,
    ) -> float:
        """Query current metric value from InfluxDB.

        Args:
            measurement: InfluxDB measurement name
            field: Field to query
            lookback_hours: Hours to look back

        Returns:
            Current metric value
        """
        query_api = self._get_query_api()
        if query_api is None:
            return 0.0

        start_time = (datetime.now(UTC) - timedelta(hours=lookback_hours)).isoformat()
        end_time = datetime.now(UTC).isoformat()

        query = f"""
        from(bucket: "{self._bucket}")
            |> range(start: {start_time}, stop: {end_time})
            |> filter(fn: (r) => r._measurement == "{measurement}")
            |> filter(fn: (r) => r._field == "{field}")
            |> mean()
        """

        try:
            tables = query_api.query(query, org=self._org)
            for table in tables:
                for record in table.records:
                    value = record.get_value()
                    if value is not None:
                        return float(value)
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to query current metric {measurement}.{field}: {e}")
            return 0.0

    def _record_alert(self, alert: AnomalyAlert) -> None:
        """Record alert in history.

        Args:
            alert: Alert to record
        """
        self._alert_history.append(
            {
                "type": alert.anomaly_type.value,
                "detected_at": alert.detected_at,
                "metric_name": alert.metric_name,
            }
        )

        # Trim history if needed
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history :]

    def _filter_duplicates(self, alerts: list[AnomalyAlert]) -> list[AnomalyAlert]:
        """Filter out duplicate alerts.

        Args:
            alerts: List of alerts to filter

        Returns:
            List of unique alerts
        """
        unique = []
        cutoff = datetime.now(UTC) - timedelta(hours=1)  # 1 hour dedup window

        for alert in alerts:
            # Check if similar alert was recently recorded
            is_duplicate = False
            for history in self._alert_history:
                if (
                    history["type"] == alert.anomaly_type.value
                    and history["metric_name"] == alert.metric_name
                    and history["detected_at"] > cutoff
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(alert)

        return unique

    def get_alert_history(
        self,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Get recent alert history.

        Args:
            hours: Hours to look back

        Returns:
            List of recent alerts
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return [a for a in self._alert_history if a["detected_at"] >= cutoff]

    def clear_history(self) -> None:
        """Clear alert history."""
        self._alert_history.clear()
        logger.info("Alert history cleared")
