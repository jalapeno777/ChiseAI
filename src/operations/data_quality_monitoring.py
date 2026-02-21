"""Data Quality Monitoring - Freshness + Gaps.

Provides comprehensive data quality monitoring for ChiseAI data sources,
including freshness checking, gap detection, and alerting.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps

Key Features:
- Configurable freshness thresholds per data source (>5min default)
- Gap detection within 60 seconds of occurrence
- Discord alerting to #alerts channel
- InfluxDB integration for historical tracking
- Grafana dashboard support

Memory Context Applied:
- Circuit breaker pattern with asyncio.Lock() prevents race conditions
- InfluxDB as primary time-series storage with PostgreSQL fallback
- Docker connectivity: chiseai network for inter-container communication
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

# Try to import influxdb_client, handle gracefully if not available
try:
    from influxdb_client.client.influxdb_client import InfluxDBClient
    from influxdb_client.client.write.point import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False
    InfluxDBClient = None  # type: ignore[misc,assignment]
    Point = None  # type: ignore[misc,assignment]
    SYNCHRONOUS: Any = None  # type: ignore[misc,no-redef]

logger = logging.getLogger(__name__)


class DataSource(StrEnum):
    """Supported data sources for monitoring."""

    BINANCE = "binance"
    BYBIT = "bybit"
    BITGET = "bitget"


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class FreshnessMetrics:
    """Freshness metrics for a data source.

    Attributes:
        source: Data source name
        symbol: Trading pair symbol
        timeframe: Timeframe being monitored
        last_update_timestamp: Timestamp of most recent data (ms)
        data_age_seconds: Age of data in seconds
        threshold_seconds: Configured freshness threshold
        is_fresh: Whether data is within threshold
        checked_at: When the check was performed
    """

    source: DataSource
    symbol: str
    timeframe: str
    last_update_timestamp: int | None
    data_age_seconds: float | None
    threshold_seconds: float
    is_fresh: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_stale(self) -> bool:
        """Check if data is stale (not fresh)."""
        return not self.is_fresh

    @property
    def staleness_seconds(self) -> float | None:
        """How stale the data is (0 if fresh)."""
        if self.is_fresh or self.data_age_seconds is None:
            return 0.0
        return max(0.0, self.data_age_seconds - self.threshold_seconds)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "last_update_timestamp": self.last_update_timestamp,
            "data_age_seconds": self.data_age_seconds,
            "threshold_seconds": self.threshold_seconds,
            "is_fresh": self.is_fresh,
            "is_stale": self.is_stale,
            "staleness_seconds": self.staleness_seconds,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class GapAlert:
    """Alert for detected data gap.

    Attributes:
        source: Data source where gap was detected
        symbol: Trading pair symbol
        timeframe: Timeframe with gap
        gap_start: Start timestamp of gap (ms)
        gap_end: End timestamp of gap (ms)
        expected_candles: Number of missing candles
        detected_at: When the gap was detected
        severity: Alert severity
    """

    source: DataSource
    symbol: str
    timeframe: str
    gap_start: int
    gap_end: int
    expected_candles: int
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    severity: AlertSeverity = AlertSeverity.WARNING

    @property
    def duration_seconds(self) -> float:
        """Duration of the gap in seconds."""
        return (self.gap_end - self.gap_start) / 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "duration_seconds": self.duration_seconds,
            "expected_candles": self.expected_candles,
            "detected_at": self.detected_at.isoformat(),
            "severity": self.severity.value,
        }


@dataclass
class SourceConfig:
    """Configuration for a data source.

    Attributes:
        source: Data source identifier
        symbols: List of symbols to monitor
        timeframes: List of timeframes to monitor
        freshness_threshold_seconds:
            Threshold for freshness alerts (default 300s = 5min)
        gap_detection_enabled: Whether to enable gap detection
        enabled: Whether this source is enabled for monitoring
    """

    source: DataSource
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h"])
    freshness_threshold_seconds: float = 300.0  # 5 minutes default
    gap_detection_enabled: bool = True
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source.value,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "freshness_threshold_seconds": self.freshness_threshold_seconds,
            "gap_detection_enabled": self.gap_detection_enabled,
            "enabled": self.enabled,
        }


class DataPoint(Protocol):
    """Protocol for data points that can be freshness-checked."""

    timestamp: int

    @property
    def datetime_utc(self) -> datetime:
        """Return timestamp as UTC datetime."""
        ...


class AlertHandler(Protocol):
    """Protocol for alert handlers."""

    async def __call__(
        self,
        alert_type: str,
        source: DataSource,
        message: str,
        severity: AlertSeverity,
        metrics: dict[str, Any],
    ) -> None:
        """Handle an alert."""
        ...


class DataQualityMonitor:
    """Main data quality monitoring orchestrator.

    Combines freshness monitoring and gap detection with alerting.
    Designed for 60-second detection window requirement.
    """

    def __init__(
        self,
        source_configs: list[SourceConfig] | None = None,
        freshness_cooldown_seconds: float = 60.0,
        gap_detection_window_seconds: float = 60.0,
    ):
        """Initialize data quality monitor.

        Args:
            source_configs: Configuration for each data source
            freshness_cooldown_seconds: Cooldown between freshness alerts
            gap_detection_window_seconds: Target gap detection latency
        """
        self.source_configs = {cfg.source: cfg for cfg in (source_configs or [])}
        self.freshness_cooldown_seconds = freshness_cooldown_seconds
        self.gap_detection_window_seconds = gap_detection_window_seconds

        # Track last alert times to prevent spam
        self._last_alert_times: dict[tuple[DataSource, str, str], datetime] = {}

        # Store latest metrics for Grafana queries
        self._latest_metrics: dict[tuple[DataSource, str, str], FreshnessMetrics] = {}

        # Historical metrics for trending (last 7 days)
        self._metrics_history: list[FreshnessMetrics] = []
        self._max_history_size = 10000  # Limit memory usage

        # Gap detection state
        self._last_seen: dict[tuple[DataSource, str, str], int] = {}
        self._active_gaps: dict[tuple[DataSource, str, str], GapAlert] = {}
        self._gap_history: list[GapAlert] = []
        self._max_gap_history_size = 1000

        # Alert handlers
        self._alert_handlers: list[Callable[..., Awaitable[None]]] = []

        # Running state
        self._running = False
        self._monitor_task: asyncio.Task | None = None

        # Circuit breaker lock for thread-safe operations
        self._lock = asyncio.Lock()

    def add_source_config(self, config: SourceConfig) -> None:
        """Add or update source configuration."""
        self.source_configs[config.source] = config
        logger.info(f"Added monitoring config for {config.source.value}")

    def remove_source_config(self, source: DataSource) -> None:
        """Remove source configuration."""
        if source in self.source_configs:
            del self.source_configs[source]
            logger.info(f"Removed monitoring config for {source.value}")

    def add_alert_handler(self, handler: Callable[..., Awaitable[None]]) -> None:
        """Add an alert handler callback.

        Args:
            handler: Async callable that receives alert data
        """
        self._alert_handlers.append(handler)
        name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.info(f"Added alert handler: {name}")

    def remove_alert_handler(self, handler: Callable[..., Awaitable[None]]) -> None:
        """Remove an alert handler."""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)
            name = getattr(handler, "__name__", handler.__class__.__name__)
            logger.info(f"Removed alert handler: {name}")

    async def _dispatch_alert(
        self,
        alert_type: str,
        source: DataSource,
        message: str,
        severity: AlertSeverity,
        metrics: dict[str, Any],
    ) -> None:
        """Dispatch alert to all handlers."""
        for handler in self._alert_handlers:
            try:
                await handler(alert_type, source, message, severity, metrics)
            except Exception as e:
                name = getattr(handler, "__name__", handler.__class__.__name__)
                logger.error(f"Alert handler {name} failed: {e}")

    async def check_data_freshness(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[DataPoint],
        reference_time: datetime | None = None,
    ) -> FreshnessMetrics:
        """Check freshness for a specific source/symbol/timeframe.

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe being checked
            data: Current data to check
            reference_time: Time to check against (defaults to UTC now)

        Returns:
            FreshnessMetrics with freshness status
        """
        if reference_time is None:
            reference_time = datetime.now(UTC)

        # Get threshold for this source
        config = self.source_configs.get(source)
        threshold = (
            config.freshness_threshold_seconds if config else 300.0
        )  # 5 min default

        # Calculate data age
        if not data:
            metrics = FreshnessMetrics(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                last_update_timestamp=None,
                data_age_seconds=None,
                threshold_seconds=threshold,
                is_fresh=False,
                checked_at=reference_time,
            )
        else:
            most_recent = max(data, key=lambda x: x.timestamp)
            data_time = datetime.fromtimestamp(most_recent.timestamp / 1000, tz=UTC)
            data_age = (reference_time - data_time).total_seconds()
            data_age = max(0.0, data_age)  # Ensure non-negative

            is_fresh = data_age <= threshold

            metrics = FreshnessMetrics(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                last_update_timestamp=most_recent.timestamp,
                data_age_seconds=data_age,
                threshold_seconds=threshold,
                is_fresh=is_fresh,
                checked_at=reference_time,
            )

        # Store metrics with circuit breaker lock
        async with self._lock:
            key = (source, symbol, timeframe)
            self._latest_metrics[key] = metrics
            self._metrics_history.append(metrics)

            # Trim history if needed
            if len(self._metrics_history) > self._max_history_size:
                self._metrics_history = self._metrics_history[-self._max_history_size :]

        return metrics

    async def detect_data_gaps(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[DataPoint],
        expected_interval_ms: int,
    ) -> list[GapAlert]:
        """Detect data gaps in real-time.

        Monitors incoming data and detects gaps within 60 seconds of occurrence.

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe
            data: New data points
            expected_interval_ms: Expected interval between candles (ms)

        Returns:
            List of newly detected gaps
        """
        key = (source, symbol, timeframe)
        detected_gaps: list[GapAlert] = []

        if not data:
            return detected_gaps

        # Sort data by timestamp
        sorted_data = sorted(data, key=lambda x: x.timestamp)

        # Get last seen timestamp
        last_seen = self._last_seen.get(key)
        current_max = sorted_data[-1].timestamp

        async with self._lock:
            if last_seen is not None:
                # Check for gap between last seen and current data
                gap_duration_ms = sorted_data[0].timestamp - last_seen

                if gap_duration_ms > expected_interval_ms * 1.5:  # 50% tolerance
                    expected_candles = int(gap_duration_ms / expected_interval_ms)

                    if self._is_valid_gap_duration(gap_duration_ms):
                        gap_alert = GapAlert(
                            source=source,
                            symbol=symbol,
                            timeframe=timeframe,
                            gap_start=last_seen + expected_interval_ms,
                            gap_end=sorted_data[0].timestamp,
                            expected_candles=expected_candles,
                            severity=self._determine_severity(
                                expected_candles, timeframe
                            ),
                        )

                        detected_gaps.append(gap_alert)
                        self._active_gaps[key] = gap_alert
                        self._gap_history.append(gap_alert)

                        logger.warning(
                            f"Detected gap in {source.value}/{symbol}/{timeframe}: "
                            f"{expected_candles} missing candles"
                        )

            # Check for internal gaps in the new data
            for i in range(1, len(sorted_data)):
                prev_ts = sorted_data[i - 1].timestamp
                curr_ts = sorted_data[i].timestamp
                gap_duration_ms = curr_ts - prev_ts

                if gap_duration_ms > expected_interval_ms * 1.5:
                    expected_candles = int(gap_duration_ms / expected_interval_ms)

                    if self._is_valid_gap_duration(gap_duration_ms):
                        gap_alert = GapAlert(
                            source=source,
                            symbol=symbol,
                            timeframe=timeframe,
                            gap_start=prev_ts + expected_interval_ms,
                            gap_end=curr_ts,
                            expected_candles=expected_candles,
                            severity=self._determine_severity(
                                expected_candles, timeframe
                            ),
                        )

                        detected_gaps.append(gap_alert)
                        self._gap_history.append(gap_alert)

            # Update last seen
            self._last_seen[key] = current_max

            # Trim history
            if len(self._gap_history) > self._max_gap_history_size:
                self._gap_history = self._gap_history[-self._max_gap_history_size :]

        return detected_gaps

    def _is_valid_gap_duration(self, gap_duration_ms: float) -> bool:
        """Check if gap duration should be reported."""
        max_duration_ms = 24.0 * 3600 * 1000  # 24 hours
        return gap_duration_ms <= max_duration_ms

    def _determine_severity(
        self, expected_candles: int, timeframe: str
    ) -> AlertSeverity:
        """Determine alert severity based on gap size."""
        # Severity thresholds based on timeframe
        thresholds = {
            "1m": (5, 15),  # warning at 5, critical at 15
            "5m": (2, 6),
            "15m": (2, 4),
            "1h": (1, 3),
            "4h": (1, 2),
            "1d": (1, 2),
        }

        warning_threshold, critical_threshold = thresholds.get(timeframe, (2, 5))

        if expected_candles >= critical_threshold:
            return AlertSeverity.CRITICAL
        elif expected_candles >= warning_threshold:
            return AlertSeverity.WARNING
        return AlertSeverity.INFO

    async def send_freshness_alert(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data_age_seconds: float | None,
        threshold_seconds: float,
    ) -> None:
        """Send a freshness alert.

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe
            data_age_seconds: Age of data
            threshold_seconds: Threshold for alert
        """
        # Check cooldown
        key = (source, symbol, timeframe)
        last_alert = self._last_alert_times.get(key)

        if last_alert is not None:
            elapsed = (datetime.now(UTC) - last_alert).total_seconds()
            if elapsed < self.freshness_cooldown_seconds:
                return  # Still in cooldown

        # Record alert time
        self._last_alert_times[key] = datetime.now(UTC)

        # Create alert message
        if data_age_seconds is None:
            message = f"No data received for {source.value}/{symbol}/{timeframe}"
        else:
            age_minutes = data_age_seconds / 60
            threshold_minutes = threshold_seconds / 60
            staleness_minutes = max(0, age_minutes - threshold_minutes)
            message = (
                f"Stale data detected for {source.value}/{symbol}/{timeframe}: "
                f"age={age_minutes:.1f}min, threshold={threshold_minutes:.1f}min, "
                f"staleness={staleness_minutes:.1f}min"
            )

        metrics = {
            "source": source.value,
            "symbol": symbol,
            "timeframe": timeframe,
            "data_age_seconds": data_age_seconds,
            "threshold_seconds": threshold_seconds,
            "alert_type": "freshness",
        }

        await self._dispatch_alert(
            alert_type="freshness",
            source=source,
            message=message,
            severity=AlertSeverity.CRITICAL,
            metrics=metrics,
        )

        logger.info(f"Sent freshness alert: {source.value}/{symbol}/{timeframe}")

    async def check_data_quality(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[DataPoint],
        expected_interval_ms: int,
    ) -> tuple[FreshnessMetrics, list[GapAlert]]:
        """Check both freshness and gaps for incoming data.

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe
            data: Current data
            expected_interval_ms: Expected interval between candles

        Returns:
            Tuple of (FreshnessMetrics, list of GapAlerts)
        """
        # Check freshness
        freshness = await self.check_data_freshness(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data=data,
        )

        # Send freshness alert if stale and cooldown elapsed
        if freshness.is_stale:
            await self.send_freshness_alert(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                data_age_seconds=freshness.data_age_seconds,
                threshold_seconds=freshness.threshold_seconds,
            )

        # Detect gaps
        gaps = await self.detect_data_gaps(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data=data,
            expected_interval_ms=expected_interval_ms,
        )

        # Send gap alerts
        for gap in gaps:
            message = (
                f"Data gap detected for {source.value}/{symbol}/{timeframe}: "
                f"{gap.expected_candles} missing candles, "
                f"duration={gap.duration_seconds:.0f}s"
            )
            await self._dispatch_alert(
                alert_type="gap",
                source=source,
                message=message,
                severity=gap.severity,
                metrics=gap.to_dict(),
            )

        return freshness, gaps

    def get_latest_metrics(
        self,
        source: DataSource | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[FreshnessMetrics]:
        """Get latest freshness metrics with optional filtering.

        Args:
            source: Filter by source
            symbol: Filter by symbol
            timeframe: Filter by timeframe

        Returns:
            List of matching FreshnessMetrics
        """
        results = []
        for key, metrics in self._latest_metrics.items():
            src, sym, tf = key
            if source and src != source:
                continue
            if symbol and sym != symbol:
                continue
            if timeframe and tf != timeframe:
                continue
            results.append(metrics)
        return results

    def get_metrics_history(
        self,
        source: DataSource | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        since: datetime | None = None,
    ) -> list[FreshnessMetrics]:
        """Get historical metrics for trending.

        Args:
            source: Filter by source
            symbol: Filter by symbol
            timeframe: Filter by timeframe
            since: Only return metrics after this time

        Returns:
            List of matching FreshnessMetrics
        """
        results = []
        for metrics in self._metrics_history:
            if source and metrics.source != source:
                continue
            if symbol and metrics.symbol != symbol:
                continue
            if timeframe and metrics.timeframe != timeframe:
                continue
            if since and metrics.checked_at < since:
                continue
            results.append(metrics)
        return results

    def get_stale_sources(self) -> list[FreshnessMetrics]:
        """Get all sources with stale data.

        Returns:
            List of stale FreshnessMetrics
        """
        return [m for m in self._latest_metrics.values() if m.is_stale]

    def get_active_gaps(
        self,
        source: DataSource | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[GapAlert]:
        """Get active (unresolved) gaps with optional filtering."""
        results = []
        for key, gap in self._active_gaps.items():
            src, sym, tf = key
            if source and src != source:
                continue
            if symbol and sym != symbol:
                continue
            if timeframe and tf != timeframe:
                continue
            results.append(gap)
        return results

    def get_gap_history(
        self,
        source: DataSource | None = None,
        since: datetime | None = None,
    ) -> list[GapAlert]:
        """Get gap history with optional filtering."""
        results = []
        for gap in self._gap_history:
            if source and gap.source != source:
                continue
            if since and gap.detected_at < since:
                continue
            results.append(gap)
        return results

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all current metrics for dashboard/Grafana.

        Returns:
            Dictionary with freshness and gap metrics
        """
        stale_sources = self.get_stale_sources()
        active_gaps = self.get_active_gaps()

        return {
            "freshness": {
                "total_monitored": len(self._latest_metrics),
                "stale_count": len(stale_sources),
                "stale_sources": [m.to_dict() for m in stale_sources],
                "all_metrics": [m.to_dict() for m in self._latest_metrics.values()],
            },
            "gaps": {
                "active_count": len(active_gaps),
                "active_gaps": [g.to_dict() for g in active_gaps],
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_freshness_for_grafana(self) -> list[dict[str, Any]]:
        """Get freshness metrics formatted for Grafana.

        Returns:
            List of metrics dictionaries with Grafana-compatible timestamps
        """
        results = []
        for metrics in self._latest_metrics.values():
            results.append(
                {
                    "timestamp": metrics.checked_at.isoformat(),
                    "source": metrics.source.value,
                    "symbol": metrics.symbol,
                    "timeframe": metrics.timeframe,
                    "data_age_seconds": metrics.data_age_seconds,
                    "threshold_seconds": metrics.threshold_seconds,
                    "is_fresh": 1 if metrics.is_fresh else 0,
                    "is_stale": 1 if metrics.is_stale else 0,
                }
            )
        return results

    def get_gap_history_for_grafana(
        self,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get gap history formatted for Grafana.

        Args:
            since: Only return gaps after this time

        Returns:
            List of gap dictionaries with Grafana-compatible timestamps
        """
        gaps = self.get_gap_history(since=since)
        return [
            {
                "timestamp": gap.detected_at.isoformat(),
                "source": gap.source.value,
                "symbol": gap.symbol,
                "timeframe": gap.timeframe,
                "duration_seconds": gap.duration_seconds,
                "expected_candles": gap.expected_candles,
                "severity": gap.severity.value,
            }
            for gap in gaps
        ]

    async def start_monitoring(self, interval_seconds: float = 60.0) -> None:
        """Start continuous monitoring loop.

        Args:
            interval_seconds: Check interval
        """
        self._running = True

        async def monitor_loop() -> None:
            while self._running:
                try:
                    # Periodic health check - could trigger alerts
                    # for sources with no recent data
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Monitor loop error: {e}")
                    await asyncio.sleep(5)

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info(f"Started data quality monitoring (interval={interval_seconds}s)")

    async def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        logger.info("Stopped data quality monitoring")

    def clear_metrics(self) -> None:
        """Clear all stored metrics."""
        self._latest_metrics.clear()
        self._metrics_history.clear()
        self._last_alert_times.clear()
        self._last_seen.clear()
        self._active_gaps.clear()
        self._gap_history.clear()
        logger.info("Cleared all metrics")


class InfluxDBExporter:
    """Export data quality metrics to InfluxDB for Grafana visualization."""

    def __init__(
        self,
        influx_url: str = "http://chiseai-influxdb:18087",
        influx_token: str = "",
        influx_org: str = "chiseai",
        influx_bucket: str = "chiseai",
    ):
        """Initialize InfluxDB exporter.

        Args:
            influx_url: InfluxDB URL (default uses chiseai network)
            influx_token: InfluxDB token
            influx_org: InfluxDB organization
            influx_bucket: Bucket for data quality metrics
        """
        self.influx_url = influx_url
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket
        self._client: Any = None
        self._write_api: Any = None

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if not INFLUXDB_AVAILABLE:
            logger.warning("influxdb-client not installed")
            return None

        if self._client is None:
            try:
                # Import here to avoid issues when not available
                from influxdb_client.client.influxdb_client import (
                    InfluxDBClient as Client,
                )
                from influxdb_client.client.write_api import SYNCHRONOUS as Sync

                self._client = Client(
                    url=self.influx_url,
                    token=self.influx_token,
                    org=self.influx_org,
                )
                self._write_api = self._client.write_api(write_options=Sync)
            except Exception as e:
                logger.error(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def export_freshness_metric(self, metrics: FreshnessMetrics) -> bool:
        """Export freshness metric to InfluxDB.

        Args:
            metrics: Freshness metrics to export

        Returns:
            True if export successful
        """
        if not INFLUXDB_AVAILABLE:
            return False

        client = self._get_client()
        if client is None:
            return False

        try:
            # Import Point here to avoid issues when not available
            from influxdb_client.client.write.point import Point as Pt

            point = (
                Pt("data_freshness")
                .tag("source", metrics.source.value)
                .tag("symbol", metrics.symbol)
                .tag("timeframe", metrics.timeframe)
                .field(
                    "data_age_seconds",
                    metrics.data_age_seconds if metrics.data_age_seconds else -1,
                )
                .field("threshold_seconds", metrics.threshold_seconds)
                .field("is_fresh", 1 if metrics.is_fresh else 0)
                .field("is_stale", 1 if metrics.is_stale else 0)
                .field(
                    "staleness_seconds",
                    metrics.staleness_seconds if metrics.staleness_seconds else 0,
                )
                .time(metrics.checked_at)
            )

            if self._write_api:
                self._write_api.write(
                    bucket=self.influx_bucket,
                    org=self.influx_org,
                    record=point,
                )

            logger.debug(
                f"Exported freshness metric: {metrics.source.value}/{metrics.symbol}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export freshness metric: {e}")
            return False

    def export_gap_alert(self, gap: GapAlert) -> bool:
        """Export gap alert to InfluxDB.

        Args:
            gap: Gap alert to export

        Returns:
            True if export successful
        """
        if not INFLUXDB_AVAILABLE:
            return False

        client = self._get_client()
        if client is None:
            return False

        try:
            # Import Point here to avoid issues when not available
            from influxdb_client.client.write.point import Point as Pt

            point = (
                Pt("data_gaps")
                .tag("source", gap.source.value)
                .tag("symbol", gap.symbol)
                .tag("timeframe", gap.timeframe)
                .tag("severity", gap.severity.value)
                .field("duration_seconds", gap.duration_seconds)
                .field("expected_candles", gap.expected_candles)
                .field("gap_start", gap.gap_start)
                .field("gap_end", gap.gap_end)
                .time(gap.detected_at)
            )

            if self._write_api:
                self._write_api.write(
                    bucket=self.influx_bucket,
                    org=self.influx_org,
                    record=point,
                )

            logger.debug(f"Exported gap alert: {gap.source.value}/{gap.symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to export gap alert: {e}")
            return False

    def close(self) -> None:
        """Close the exporter connection."""
        if self._write_api:
            self._write_api.close()
            self._write_api = None
        if self._client:
            self._client.close()
            self._client = None


class DiscordAlertSender:
    """Send data quality alerts to Discord #alerts channel."""

    # Color mapping for severity levels
    SEVERITY_COLORS = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
    }

    # Source emoji mapping
    SOURCE_EMOJI = {
        "binance": "🟡",  # Yellow
        "bybit": "🔵",  # Blue
        "bitget": "🟢",  # Green
    }

    def __init__(
        self,
        webhook_url: str | None = None,
        alerts_channel: str = "alerts",
        require_webhook: bool = False,  # If True, raise exception when webhook missing
    ):
        """Initialize Discord alert sender.

        Args:
            webhook_url: Discord webhook URL
            alerts_channel: Channel for data quality alerts
            require_webhook: If True, raise exception when webhook is not configured
        """
        self.webhook_url = webhook_url
        self.alerts_channel = alerts_channel
        self.require_webhook = require_webhook
        self._consecutive_failures = 0
        self._circuit_open = False

    def _format_freshness_embed(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data_age_seconds: float | None,
        threshold_seconds: float,
    ) -> dict[str, Any]:
        """Format a freshness alert as Discord embed."""
        emoji = self.SOURCE_EMOJI.get(source.value, "📊")

        if data_age_seconds is None:
            title = f"{emoji} {source.value.upper()} - No Data"
            description = f"No data received for **{symbol}** ({timeframe})"
            staleness_text = "N/A"
        else:
            age_minutes = data_age_seconds / 60
            threshold_minutes = threshold_seconds / 60
            staleness_minutes = max(0, age_minutes - threshold_minutes)

            title = f"{emoji} {source.value.upper()} - Stale Data Alert"
            description = (
                f"Data for **{symbol}** ({timeframe}) is stale\n\n"
                f"• Age: **{age_minutes:.1f}** minutes\n"
                f"• Threshold: **{threshold_minutes:.1f}** minutes\n"
                f"• Staleness: **{staleness_minutes:.1f}** minutes over threshold"
            )
            staleness_text = f"{staleness_minutes:.1f} min"

        return {
            "title": title,
            "description": description,
            "color": self.SEVERITY_COLORS["critical"],
            "fields": [
                {
                    "name": "Source",
                    "value": source.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Symbol",
                    "value": symbol,
                    "inline": True,
                },
                {
                    "name": "Timeframe",
                    "value": timeframe,
                    "inline": True,
                },
                {
                    "name": "Staleness",
                    "value": staleness_text,
                    "inline": True,
                },
                {
                    "name": "Timestamp",
                    "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Data Quality Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _send_via_webhook(
        self, content: str, embeds: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Send message via Discord webhook.

        Args:
            content: Message content
            embeds: Optional Discord embeds

        Returns:
            Dictionary with success status and message info
        """
        if not self.webhook_url:
            if self.require_webhook:
                raise ValueError("Discord webhook URL required but not configured")
            logger.warning(
                "Discord webhook not configured. Alert delivery attempted but will not be sent. "
                "Set DISCORD_ALERT_WEBHOOK_URL environment variable."
            )
            return {
                "success": False,
                "error": "No webhook URL configured",
                "message_id": None,
                "circuit_open": False,
            }

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status == 204:
                        # Webhooks return 204 on success
                        return {
                            "success": True,
                            "error": None,
                            "message_id": None,  # Webhooks don't return message ID
                            "channel": self.alerts_channel,
                        }
                    elif resp.status == 429:
                        # Rate limited
                        retry_after = resp.headers.get("Retry-After", "5")
                        return {
                            "success": False,
                            "error": f"Rate limited. Retry after {retry_after}s",
                            "message_id": None,
                            "retry_after": float(retry_after),
                        }
                    else:
                        body = await resp.text()
                        return {
                            "success": False,
                            "error": f"HTTP {resp.status}: {body}",
                            "message_id": None,
                        }

        except ImportError:
            logger.error("aiohttp not installed, cannot send Discord webhook")
            return {
                "success": False,
                "error": "aiohttp not installed",
                "message_id": None,
            }
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message_id": None,
            }

    def _format_gap_embed(self, gap: GapAlert) -> dict[str, Any]:
        """Format a gap alert as Discord embed."""
        emoji = self.SOURCE_EMOJI.get(gap.source.value, "📊")
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
        }.get(gap.severity.value, "⚠️")

        gap_start_dt = datetime.fromtimestamp(gap.gap_start / 1000, tz=UTC)
        gap_end_dt = datetime.fromtimestamp(gap.gap_end / 1000, tz=UTC)

        source_name = gap.source.value.upper()
        title = f"{severity_emoji} {emoji} {source_name} - Data Gap Detected"
        description = (
            "Missing data detected for "
            f"**{gap.symbol}** ({gap.timeframe})\n\n"
            f"• Missing candles: **{gap.expected_candles}**\n"
            f"• Gap duration: **{gap.duration_seconds:.0f}** seconds\n"
            f"• Gap start: {gap_start_dt.strftime('%H:%M:%S')}\n"
            f"• Gap end: {gap_end_dt.strftime('%H:%M:%S')}"
        )

        return {
            "title": title,
            "description": description,
            "color": self.SEVERITY_COLORS.get(
                gap.severity.value, self.SEVERITY_COLORS["warning"]
            ),
            "fields": [
                {
                    "name": "Source",
                    "value": gap.source.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Symbol",
                    "value": gap.symbol,
                    "inline": True,
                },
                {
                    "name": "Timeframe",
                    "value": gap.timeframe,
                    "inline": True,
                },
                {
                    "name": "Missing Candles",
                    "value": str(gap.expected_candles),
                    "inline": True,
                },
                {
                    "name": "Severity",
                    "value": gap.severity.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Detected At",
                    "value": gap.detected_at.strftime("%H:%M:%S UTC"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Data Quality Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def send_freshness_alert(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data_age_seconds: float | None,
        threshold_seconds: float,
    ) -> dict[str, Any]:
        """Send a freshness alert to Discord.

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe
            data_age_seconds: Age of data
            threshold_seconds: Threshold for alert

        Returns:
            Send result dictionary
        """
        embed = self._format_freshness_embed(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data_age_seconds=data_age_seconds,
            threshold_seconds=threshold_seconds,
        )

        message = f"🚨 Data Quality Alert: Stale data from {source.value.upper()}"

        # Send via webhook if configured
        if self.webhook_url:
            return await self._send_via_webhook(message, [embed])

        # No webhook configured - log warning and return mock result
        logger.warning(
            f"Discord webhook not configured. Set DISCORD_ALERT_WEBHOOK_URL "
            f"environment variable to enable Discord alerts. "
            f"Alert for {source.value}/{symbol} was not sent."
        )
        return {
            "success": False,
            "channel": self.alerts_channel,
            "embed": embed,
            "message": message,
            "error": "Discord webhook not configured. Set DISCORD_ALERT_WEBHOOK_URL.",
        }

    async def send_gap_alert(self, gap: GapAlert) -> dict[str, Any]:
        """Send a gap alert to Discord.

        Args:
            gap: Gap alert to send

        Returns:
            Send result dictionary
        """
        embed = self._format_gap_embed(gap)
        message = f"⚠️ Data Quality Alert: Gap detected in {gap.source.value.upper()}"

        # Send via webhook if configured
        if self.webhook_url:
            return await self._send_via_webhook(message, [embed])

        # No webhook configured - log warning and return mock result
        logger.warning(
            f"Discord webhook not configured. Set DISCORD_ALERT_WEBHOOK_URL "
            f"environment variable to enable Discord alerts. "
            f"Alert for {gap.source.value}/{gap.symbol} was not sent."
        )
        return {
            "success": False,
            "channel": self.alerts_channel,
            "embed": embed,
            "message": message,
            "error": "Discord webhook not configured. Set DISCORD_ALERT_WEBHOOK_URL.",
        }


class GrafanaDashboardQueries:
    """Flux queries for Grafana dashboard panels."""

    @staticmethod
    def get_freshness_panel_query(
        bucket: str = "data_quality",
        source: str | None = None,
    ) -> str:
        """Get Flux query for freshness panel.

        Args:
            bucket: InfluxDB bucket name
            source: Optional source filter

        Returns:
            Flux query string
        """
        query = f"""
from(bucket: "{bucket}")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "data_age_seconds")
"""
        if source:
            query += f'  |> filter(fn: (r) => r.source == "{source}")\n'

        query += """
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> yield(name: "mean")
"""
        return query

    @staticmethod
    def get_freshness_status_query(bucket: str = "data_quality") -> str:
        """Get Flux query for freshness status (fresh/stale counts)."""
        return f"""
from(bucket: "{bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "is_stale")
  |> last()
  |> group(columns: ["source"])
  |> sum()
"""

    @staticmethod
    def get_gap_count_query(
        bucket: str = "data_quality",
        hours: int = 24,
    ) -> str:
        """Get Flux query for gap count."""
        return f"""
from(bucket: "{bucket}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "data_gaps")
  |> filter(fn: (r) => r._field == "expected_candles")
  |> count()
  |> group(columns: ["source", "symbol"])
"""

    @staticmethod
    def get_last_update_query(bucket: str = "data_quality") -> str:
        """Get Flux query for last update timestamp per source."""
        return f"""
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "data_freshness")
  |> filter(fn: (r) => r._field == "data_age_seconds")
  |> last()
"""

    @classmethod
    def get_dashboard_json_template(cls) -> dict[str, Any]:
        """Get a template for Grafana dashboard JSON.

        Returns:
            Dashboard template dictionary
        """
        return {
            "dashboard": {
                "title": "Data Quality Monitoring",
                "tags": ["data-quality", "monitoring"],
                "timezone": "utc",
                "schemaVersion": 36,
                "refresh": "30s",
                "panels": [
                    {
                        "id": 1,
                        "title": "Data Freshness by Source",
                        "type": "timeseries",
                        "targets": [
                            {
                                "query": cls.get_freshness_panel_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    },
                    {
                        "id": 2,
                        "title": "Stale Data Sources",
                        "type": "stat",
                        "targets": [
                            {
                                "query": cls.get_freshness_status_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                    },
                    {
                        "id": 3,
                        "title": "Data Gaps (24h)",
                        "type": "table",
                        "targets": [
                            {
                                "query": cls.get_gap_count_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
                    },
                    {
                        "id": 4,
                        "title": "Last Update per Source",
                        "type": "table",
                        "targets": [
                            {
                                "query": cls.get_last_update_query(),
                                "refId": "A",
                            }
                        ],
                        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
                    },
                ],
            },
            "overwrite": False,
        }


# Convenience functions for standalone usage
async def check_data_freshness(
    source: DataSource,
    symbol: str,
    timeframe: str,
    data: list[DataPoint],
    threshold_seconds: float = 300.0,
) -> FreshnessMetrics:
    """Check data freshness for a single source/symbol/timeframe.

    Convenience function for quick freshness checks without setting up
    the full monitor.

    Args:
        source: Data source
        symbol: Trading pair symbol
        timeframe: Timeframe being checked
        data: Current data to check
        threshold_seconds: Freshness threshold (default 5 minutes)

    Returns:
        FreshnessMetrics with freshness status
    """
    monitor = DataQualityMonitor()
    config = SourceConfig(
        source=source,
        symbols=[symbol],
        timeframes=[timeframe],
        freshness_threshold_seconds=threshold_seconds,
    )
    monitor.add_source_config(config)

    return await monitor.check_data_freshness(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        data=data,
    )


async def detect_data_gaps(
    source: DataSource,
    symbol: str,
    timeframe: str,
    data: list[DataPoint],
    expected_interval_ms: int,
) -> list[GapAlert]:
    """Detect data gaps for a single source/symbol/timeframe.

    Convenience function for quick gap detection without setting up
    the full monitor.

    Args:
        source: Data source
        symbol: Trading pair symbol
        timeframe: Timeframe
        data: New data points
        expected_interval_ms: Expected interval between candles (ms)

    Returns:
        List of detected gaps
    """
    monitor = DataQualityMonitor()
    return await monitor.detect_data_gaps(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        data=data,
        expected_interval_ms=expected_interval_ms,
    )


async def send_freshness_alert(
    source: DataSource,
    symbol: str,
    timeframe: str,
    data_age_seconds: float | None,
    threshold_seconds: float,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Send a freshness alert.

    Convenience function for sending alerts without setting up
    the full monitor.

    Args:
        source: Data source
        symbol: Trading pair symbol
        timeframe: Timeframe
        data_age_seconds: Age of data
        threshold_seconds: Threshold for alert
        webhook_url: Discord webhook URL

    Returns:
        Send result dictionary
    """
    sender = DiscordAlertSender(webhook_url=webhook_url)
    return await sender.send_freshness_alert(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        data_age_seconds=data_age_seconds,
        threshold_seconds=threshold_seconds,
    )


# Export all public symbols
__all__ = [
    "DataSource",
    "AlertSeverity",
    "FreshnessMetrics",
    "GapAlert",
    "SourceConfig",
    "DataQualityMonitor",
    "InfluxDBExporter",
    "DiscordAlertSender",
    "GrafanaDashboardQueries",
    "check_data_freshness",
    "detect_data_gaps",
    "send_freshness_alert",
]
