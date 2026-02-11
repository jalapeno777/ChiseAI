"""Data quality monitoring - freshness and gap detection.

Provides real-time monitoring of data freshness across multiple data sources
(Binance, Bybit, Bitget) with configurable thresholds and Discord alerting.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_ingestion.ohlcv_fetcher import OHLCVData
    from data_ingestion.timeframe_config import Timeframe

logger = logging.getLogger(__name__)


class DataSource(str, Enum):
    """Supported data sources for monitoring."""

    BINANCE = "binance"
    BYBIT = "bybit"
    BITGET = "bitget"


class AlertSeverity(str, Enum):
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
class DataQualityAlert:
    """General data quality alert.

    Attributes:
        alert_type: Type of alert (freshness, gap, connection)
        source: Data source
        message: Human-readable alert message
        severity: Alert severity
        metrics: Associated metrics
        created_at: When alert was created
    """

    alert_type: str
    source: DataSource
    message: str
    severity: AlertSeverity
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type,
            "source": self.source.value,
            "message": self.message,
            "severity": self.severity.value,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SourceConfig:
    """Configuration for a data source.

    Attributes:
        source: Data source identifier
        symbols: List of symbols to monitor
        timeframes: List of timeframes to monitor
        freshness_threshold_seconds: Threshold for freshness alerts (default 300s = 5min)
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


class DataFreshnessMonitor:
    """Monitor data freshness across multiple sources.

    Tracks last update timestamps and triggers alerts when data becomes stale.
    Designed for 60-second detection window requirement.
    """

    def __init__(
        self,
        source_configs: list[SourceConfig] | None = None,
        alert_cooldown_seconds: float = 60.0,
    ):
        """Initialize freshness monitor.

        Args:
            source_configs: Configuration for each data source
            alert_cooldown_seconds: Minimum time between duplicate alerts
        """
        self.source_configs = {cfg.source: cfg for cfg in (source_configs or [])}
        self.alert_cooldown_seconds = alert_cooldown_seconds

        # Track last alert times to prevent spam
        self._last_alert_times: dict[tuple[DataSource, str, str], datetime] = {}

        # Store latest metrics for Grafana queries
        self._latest_metrics: dict[tuple[DataSource, str, str], FreshnessMetrics] = {}

        # Historical metrics for trending (last 7 days)
        self._metrics_history: list[FreshnessMetrics] = []
        self._max_history_size = 10000  # Limit memory usage

    def add_source_config(self, config: SourceConfig) -> None:
        """Add or update source configuration."""
        self.source_configs[config.source] = config
        logger.info(f"Added monitoring config for {config.source.value}")

    def remove_source_config(self, source: DataSource) -> None:
        """Remove source configuration."""
        if source in self.source_configs:
            del self.source_configs[source]
            logger.info(f"Removed monitoring config for {source.value}")

    async def check_freshness(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[OHLCVData],
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
            data_time = most_recent.datetime_utc
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

        # Store metrics
        key = (source, symbol, timeframe)
        self._latest_metrics[key] = metrics
        self._metrics_history.append(metrics)

        # Trim history if needed
        if len(self._metrics_history) > self._max_history_size:
            self._metrics_history = self._metrics_history[-self._max_history_size :]

        return metrics

    def should_alert(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
    ) -> bool:
        """Check if an alert should be sent (respects cooldown).

        Args:
            source: Data source
            symbol: Trading pair symbol
            timeframe: Timeframe

        Returns:
            True if alert should be sent
        """
        key = (source, symbol, timeframe)
        last_alert = self._last_alert_times.get(key)

        if last_alert is None:
            return True

        elapsed = (datetime.now(UTC) - last_alert).total_seconds()
        return elapsed >= self.alert_cooldown_seconds

    def record_alert(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Record that an alert was sent."""
        key = (source, symbol, timeframe)
        self._last_alert_times[key] = datetime.now(UTC)

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

    def clear_metrics(self) -> None:
        """Clear all stored metrics."""
        self._latest_metrics.clear()
        self._metrics_history.clear()
        logger.info("Cleared all freshness metrics")


class GapDetector:
    """Detect data gaps in real-time.

    Monitors incoming data and detects gaps within 60 seconds of occurrence.
    """

    def __init__(
        self,
        detection_window_seconds: float = 60.0,
        max_gap_duration_hours: float = 24.0,
    ):
        """Initialize gap detector.

        Args:
            detection_window_seconds: Target detection latency (default 60s)
            max_gap_duration_hours: Maximum gap to report (longer = market closure)
        """
        self.detection_window_seconds = detection_window_seconds
        self.max_gap_duration_hours = max_gap_duration_hours

        # Track last seen timestamps per source/symbol/timeframe
        self._last_seen: dict[tuple[DataSource, str, str], int] = {}

        # Active gap alerts
        self._active_gaps: dict[tuple[DataSource, str, str], GapAlert] = {}

        # Gap history
        self._gap_history: list[GapAlert] = []
        self._max_history_size = 1000

    def update_and_detect(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[OHLCVData],
        expected_interval_ms: int,
    ) -> list[GapAlert]:
        """Update state and detect gaps.

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
                        severity=self._determine_severity(expected_candles, timeframe),
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
                        severity=self._determine_severity(expected_candles, timeframe),
                    )

                    detected_gaps.append(gap_alert)
                    self._gap_history.append(gap_alert)

        # Update last seen
        self._last_seen[key] = current_max

        # Trim history
        if len(self._gap_history) > self._max_history_size:
            self._gap_history = self._gap_history[-self._max_history_size :]

        return detected_gaps

    def _is_valid_gap_duration(self, gap_duration_ms: float) -> bool:
        """Check if gap duration should be reported."""
        max_duration_ms = self.max_gap_duration_hours * 3600 * 1000
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

    def clear_gap(self, source: DataSource, symbol: str, timeframe: str) -> None:
        """Mark a gap as resolved."""
        key = (source, symbol, timeframe)
        if key in self._active_gaps:
            del self._active_gaps[key]

    def reset(self) -> None:
        """Reset all gap detection state."""
        self._last_seen.clear()
        self._active_gaps.clear()
        self._gap_history.clear()
        logger.info("Reset gap detector state")


class DataQualityMonitor:
    """Main data quality monitoring orchestrator.

    Combines freshness monitoring and gap detection with alerting.
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
        self.freshness_monitor = DataFreshnessMonitor(
            source_configs=source_configs,
            alert_cooldown_seconds=freshness_cooldown_seconds,
        )
        self.gap_detector = GapDetector(
            detection_window_seconds=gap_detection_window_seconds,
        )

        # Alert handlers
        self._alert_handlers: list[callable] = []

        # Running state
        self._running = False
        self._monitor_task: asyncio.Task | None = None

    def add_alert_handler(self, handler: callable) -> None:
        """Add an alert handler callback.

        Args:
            handler: Async callable that receives DataQualityAlert
        """
        self._alert_handlers.append(handler)
        logger.info(f"Added alert handler: {handler.__name__}")

    def remove_alert_handler(self, handler: callable) -> None:
        """Remove an alert handler."""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)
            logger.info(f"Removed alert handler: {handler.__name__}")

    async def _dispatch_alert(self, alert: DataQualityAlert) -> None:
        """Dispatch alert to all handlers."""
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler {handler.__name__} failed: {e}")

    async def check_data_quality(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data: list[OHLCVData],
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
        freshness = await self.freshness_monitor.check_freshness(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data=data,
        )

        # Send freshness alert if stale and cooldown elapsed
        if freshness.is_stale and self.freshness_monitor.should_alert(
            source, symbol, timeframe
        ):
            alert = DataQualityAlert(
                alert_type="freshness",
                source=source,
                message=(
                    f"Stale data detected for {source.value}/{symbol}/{timeframe}: "
                    f"age={freshness.data_age_seconds:.0f}s, "
                    f"threshold={freshness.threshold_seconds:.0f}s"
                ),
                severity=AlertSeverity.CRITICAL,
                metrics=freshness.to_dict(),
            )
            await self._dispatch_alert(alert)
            self.freshness_monitor.record_alert(source, symbol, timeframe)

        # Detect gaps
        gaps = self.gap_detector.update_and_detect(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data=data,
            expected_interval_ms=expected_interval_ms,
        )

        # Send gap alerts
        for gap in gaps:
            alert = DataQualityAlert(
                alert_type="gap",
                source=source,
                message=(
                    f"Data gap detected for {source.value}/{symbol}/{timeframe}: "
                    f"{gap.expected_candles} missing candles, "
                    f"duration={gap.duration_seconds:.0f}s"
                ),
                severity=gap.severity,
                metrics=gap.to_dict(),
            )
            await self._dispatch_alert(alert)

        return freshness, gaps

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all current metrics for dashboard/Grafana.

        Returns:
            Dictionary with freshness and gap metrics
        """
        stale_sources = self.freshness_monitor.get_stale_sources()
        active_gaps = self.gap_detector.get_active_gaps()

        return {
            "freshness": {
                "total_monitored": len(self.freshness_monitor._latest_metrics),
                "stale_count": len(stale_sources),
                "stale_sources": [m.to_dict() for m in stale_sources],
                "all_metrics": [
                    m.to_dict() for m in self.freshness_monitor._latest_metrics.values()
                ],
            },
            "gaps": {
                "active_count": len(active_gaps),
                "active_gaps": [g.to_dict() for g in active_gaps],
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

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
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("Stopped data quality monitoring")

    def get_freshness_for_grafana(self) -> list[dict[str, Any]]:
        """Get freshness metrics formatted for Grafana.

        Returns:
            List of metrics dictionaries with Grafana-compatible timestamps
        """
        results = []
        for metrics in self.freshness_monitor._latest_metrics.values():
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
        gaps = self.gap_detector.get_gap_history(since=since)
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
