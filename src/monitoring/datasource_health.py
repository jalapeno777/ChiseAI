"""Data source health monitoring for InfluxDB and PostgreSQL.

Provides real-time monitoring of database connectivity with auto-reconnect logic,
alerting, and health dashboards for Grafana.

For ST-OPS-008: Grafana Data Source Health Monitoring
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

AlertHandler = Callable[["DatasourceHealthAlert"], Awaitable[None]]


class DataSourceType(StrEnum):
    """Types of data sources being monitored."""

    INFLUXDB = "influxdb"
    POSTGRESQL = "postgresql"


class ConnectionStatus(StrEnum):
    """Connection status states."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ConnectionMetrics:
    """Metrics for a single data source connection.

    Attributes:
        source_type: Type of data source
        source_name: Human-readable name
        status: Current connection status
        last_connected_at: Timestamp of last successful connection
        last_disconnected_at: Timestamp of last disconnect
        disconnect_count: Number of disconnects
        reconnect_attempts: Current reconnect attempt count
        total_reconnect_attempts: Total reconnect attempts across all disconnects
        uptime_seconds: Total uptime in current session
        downtime_seconds: Total downtime in current session
        response_time_ms: Last connection response time
        checked_at: When the check was performed
    """

    source_type: DataSourceType
    source_name: str
    status: ConnectionStatus
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    disconnect_count: int = 0
    reconnect_attempts: int = 0
    total_reconnect_attempts: int = 0
    uptime_seconds: float = 0.0
    downtime_seconds: float = 0.0
    response_time_ms: float | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self.status == ConnectionStatus.CONNECTED

    @property
    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return self.status in (
            ConnectionStatus.CONNECTED,
            ConnectionStatus.RECONNECTING,
        )

    @property
    def availability_percentage(self) -> float:
        """Calculate availability percentage."""
        total_time = self.uptime_seconds + self.downtime_seconds
        if total_time == 0:
            return 100.0
        return (self.uptime_seconds / total_time) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "status": self.status.value,
            "last_connected_at": (
                self.last_connected_at.isoformat() if self.last_connected_at else None
            ),
            "last_disconnected_at": (
                self.last_disconnected_at.isoformat()
                if self.last_disconnected_at
                else None
            ),
            "disconnect_count": self.disconnect_count,
            "reconnect_attempts": self.reconnect_attempts,
            "total_reconnect_attempts": self.total_reconnect_attempts,
            "uptime_seconds": self.uptime_seconds,
            "downtime_seconds": self.downtime_seconds,
            "response_time_ms": self.response_time_ms,
            "availability_percentage": self.availability_percentage,
            "is_connected": self.is_connected,
            "is_healthy": self.is_healthy,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class DatasourceHealthAlert:
    """Alert for data source health issues.

    Attributes:
        alert_type: Type of alert (disconnect, reconnect_failed, extended_downtime)
        source_type: Type of data source
        source_name: Human-readable name
        message: Human-readable alert message
        severity: Alert severity
        metrics: Associated metrics
        created_at: When alert was created
    """

    alert_type: str
    source_type: DataSourceType
    source_name: str
    message: str
    severity: AlertSeverity
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type,
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "message": self.message,
            "severity": self.severity.value,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class DatasourceConfig:
    """Configuration for a data source.

    Attributes:
        source_type: Type of data source
        source_name: Human-readable name
        host: Hostname or IP
        port: Port number
        database: Database name (for PostgreSQL)
        token: Authentication token (for InfluxDB)
        username: Username (for PostgreSQL)
        password: Password (for PostgreSQL)
        check_interval_seconds: How often to check connectivity
        enabled: Whether this source is enabled for monitoring
        reconnect_backoff_seconds: Backoff intervals for reconnection attempts
        max_reconnect_attempts: Maximum reconnection attempts before giving up
    """

    source_type: DataSourceType
    source_name: str
    host: str
    port: int
    database: str | None = None
    token: str | None = None
    username: str | None = None
    password: str | None = None
    check_interval_seconds: float = 30.0
    enabled: bool = True
    reconnect_backoff_seconds: tuple[float, ...] = (2.0, 5.0, 10.0)
    max_reconnect_attempts: int = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding sensitive fields)."""
        return {
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "check_interval_seconds": self.check_interval_seconds,
            "enabled": self.enabled,
            "max_reconnect_attempts": self.max_reconnect_attempts,
        }


class InfluxDBHealthChecker:
    """Health checker for InfluxDB."""

    def __init__(self, config: DatasourceConfig):
        """Initialize InfluxDB health checker.

        Args:
            config: Datasource configuration
        """
        self.config = config
        self._client: Any | None = None

    async def check_health(self) -> tuple[bool, float | None]:
        """Check InfluxDB health.

        Returns:
            Tuple of (is_healthy, response_time_ms)
        """
        import time

        start_time = time.time()
        try:
            # Try to import influxdb client
            try:
                from influxdb_client.client.influxdb_client import InfluxDBClient
            except ImportError:
                # Fallback: use HTTP request to health endpoint
                return await self._check_health_http()

            # Use InfluxDB client if available
            url = f"http://{self.config.host}:{self.config.port}"
            client = InfluxDBClient(
                url=url,
                token=self.config.token or "",
                org="chiseai",
            )

            health = client.health()
            response_time_ms = (time.time() - start_time) * 1000

            is_healthy = health.status == "pass"
            client.close()

            return is_healthy, response_time_ms

        except Exception as e:
            logger.debug(f"InfluxDB health check failed: {e}")
            return False, None

    async def _check_health_http(self) -> tuple[bool, float | None]:
        """Check InfluxDB health via HTTP.

        Returns:
            Tuple of (is_healthy, response_time_ms)
        """
        import time

        start_time = time.time()
        try:
            import aiohttp

            url = f"http://{self.config.host}:{self.config.port}/health"
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response,
            ):
                response_time_ms = (time.time() - start_time) * 1000
                is_healthy = response.status == 200
                return is_healthy, response_time_ms

        except Exception as e:
            logger.debug(f"InfluxDB HTTP health check failed: {e}")
            return False, None


class PostgreSQLHealthChecker:
    """Health checker for PostgreSQL."""

    def __init__(self, config: DatasourceConfig):
        """Initialize PostgreSQL health checker.

        Args:
            config: Datasource configuration
        """
        self.config = config

    async def check_health(self) -> tuple[bool, float | None]:
        """Check PostgreSQL health.

        Returns:
            Tuple of (is_healthy, response_time_ms)
        """
        import time

        start_time = time.time()
        try:
            # Try asyncpg first
            try:
                import asyncpg

                conn_str = (
                    f"postgresql://{self.config.username}:{self.config.password}"
                    f"@{self.config.host}:{self.config.port}/{self.config.database}"
                )

                conn = await asyncpg.connect(conn_str)
                await conn.fetch("SELECT 1")
                await conn.close()

                response_time_ms = (time.time() - start_time) * 1000
                return True, response_time_ms

            except ImportError:
                # Fallback to psycopg2 in thread
                return await self._check_health_sync()

        except Exception as e:
            logger.debug(f"PostgreSQL health check failed: {e}")
            return False, None

    async def _check_health_sync(self) -> tuple[bool, float | None]:
        """Check PostgreSQL health using sync driver in thread.

        Returns:
            Tuple of (is_healthy, response_time_ms)
        """
        import time
        from concurrent.futures import ThreadPoolExecutor

        def _check():
            try:
                import psycopg2

                conn = psycopg2.connect(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.username,
                    password=self.config.password,
                    connect_timeout=5,
                )
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                conn.close()
                return True
            except Exception:
                return False

        start_time = time.time()
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, _check)
            response_time_ms = (time.time() - start_time) * 1000
            return result, response_time_ms if result else None
        except Exception as e:
            logger.debug(f"PostgreSQL sync health check failed: {e}")
            return False, None


class DataSourceHealthMonitor:
    """Monitor health of data sources (InfluxDB, PostgreSQL).

    Provides:
    - Periodic connectivity checks
    - Auto-reconnect with exponential backoff
    - Discord alerts on disconnect/reconnect failures
    - Health metrics for Grafana dashboards
    """

    def __init__(
        self,
        datasource_configs: list[DatasourceConfig] | None = None,
        alert_cooldown_seconds: float = 60.0,
        extended_downtime_threshold_seconds: float = 300.0,  # 5 minutes
    ):
        """Initialize data source health monitor.

        Args:
            datasource_configs: Configuration for each data source
            alert_cooldown_seconds: Minimum time between duplicate alerts
            extended_downtime_threshold_seconds: Threshold for critical extended downtime alert
        """
        self.datasource_configs = {
            cfg.source_type: cfg for cfg in (datasource_configs or [])
        }
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.extended_downtime_threshold_seconds = extended_downtime_threshold_seconds

        # Health checkers
        self._checkers: dict[DataSourceType, Any] = {}

        # Connection metrics
        self._metrics: dict[DataSourceType, ConnectionMetrics] = {}

        # Track last alert times to prevent spam
        self._last_alert_times: dict[tuple[DataSourceType, str], datetime] = {}

        # Alert handlers
        self._alert_handlers: list[AlertHandler] = []

        # Running state
        self._running = False
        self._monitor_tasks: dict[DataSourceType, asyncio.Task] = {}

        # Initialize checkers and metrics
        self._initialize_checkers()

    def _initialize_checkers(self) -> None:
        """Initialize health checkers for configured sources."""
        for source_type, config in self.datasource_configs.items():
            if not config.enabled:
                continue

            if source_type == DataSourceType.INFLUXDB:
                self._checkers[source_type] = InfluxDBHealthChecker(config)
            elif source_type == DataSourceType.POSTGRESQL:
                self._checkers[source_type] = PostgreSQLHealthChecker(config)

            # Initialize metrics
            self._metrics[source_type] = ConnectionMetrics(
                source_type=source_type,
                source_name=config.source_name,
                status=ConnectionStatus.DISCONNECTED,
            )

    def add_datasource_config(self, config: DatasourceConfig) -> None:
        """Add or update data source configuration."""
        self.datasource_configs[config.source_type] = config

        if config.enabled:
            if config.source_type == DataSourceType.INFLUXDB:
                self._checkers[config.source_type] = InfluxDBHealthChecker(config)
            elif config.source_type == DataSourceType.POSTGRESQL:
                self._checkers[config.source_type] = PostgreSQLHealthChecker(config)

            if config.source_type not in self._metrics:
                self._metrics[config.source_type] = ConnectionMetrics(
                    source_type=config.source_type,
                    source_name=config.source_name,
                    status=ConnectionStatus.DISCONNECTED,
                )

        logger.info(f"Added monitoring config for {config.source_name}")

    def remove_datasource_config(self, source_type: DataSourceType) -> None:
        """Remove data source configuration."""
        if source_type in self.datasource_configs:
            del self.datasource_configs[source_type]
        if source_type in self._checkers:
            del self._checkers[source_type]
        if source_type in self._metrics:
            del self._metrics[source_type]
        logger.info(f"Removed monitoring config for {source_type.value}")

    def add_alert_handler(self, handler: AlertHandler) -> None:
        """Add an alert handler callback.

        Args:
            handler: Async callable that receives DatasourceHealthAlert
        """
        self._alert_handlers.append(handler)
        name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.info(f"Added alert handler: {name}")

    def remove_alert_handler(self, handler: AlertHandler) -> None:
        """Remove an alert handler."""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)
            name = getattr(handler, "__name__", handler.__class__.__name__)
            logger.info(f"Removed alert handler: {name}")

    async def _dispatch_alert(self, alert: DatasourceHealthAlert) -> None:
        """Dispatch alert to all handlers."""
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                name = getattr(handler, "__name__", handler.__class__.__name__)
                logger.error(f"Alert handler {name} failed: {e}")

    def should_alert(
        self,
        source_type: DataSourceType,
        alert_type: str,
    ) -> bool:
        """Check if an alert should be sent (respects cooldown).

        Args:
            source_type: Data source type
            alert_type: Type of alert

        Returns:
            True if alert should be sent
        """
        key = (source_type, alert_type)
        last_alert = self._last_alert_times.get(key)

        if last_alert is None:
            return True

        elapsed = (datetime.now(UTC) - last_alert).total_seconds()
        return elapsed >= self.alert_cooldown_seconds

    def record_alert(
        self,
        source_type: DataSourceType,
        alert_type: str,
    ) -> None:
        """Record that an alert was sent."""
        key = (source_type, alert_type)
        self._last_alert_times[key] = datetime.now(UTC)

    async def _check_datasource(
        self,
        source_type: DataSourceType,
        config: DatasourceConfig,
    ) -> None:
        """Check a single data source and update metrics."""
        checker = self._checkers.get(source_type)
        if not checker:
            return

        metrics = self._metrics[source_type]
        previous_status = metrics.status

        # Perform health check
        is_healthy, response_time_ms = await checker.check_health()
        now = datetime.now(UTC)

        if is_healthy:
            # Connection successful
            if previous_status != ConnectionStatus.CONNECTED:
                # State change to connected
                metrics.status = ConnectionStatus.CONNECTED
                metrics.last_connected_at = now
                metrics.reconnect_attempts = 0  # Reset on success

                # Calculate downtime if we were disconnected
                if metrics.last_disconnected_at:
                    downtime = (now - metrics.last_disconnected_at).total_seconds()
                    metrics.downtime_seconds += downtime

                logger.info(f"{config.source_name} is now connected")

                # Send recovery alert if we were previously disconnected
                if previous_status in (
                    ConnectionStatus.DISCONNECTED,
                    ConnectionStatus.FAILED,
                ):
                    if self.should_alert(source_type, "recovered"):
                        alert = DatasourceHealthAlert(
                            alert_type="recovered",
                            source_type=source_type,
                            source_name=config.source_name,
                            message=f"{config.source_name} has recovered and is now connected",
                            severity=AlertSeverity.INFO,
                            metrics=metrics.to_dict(),
                        )
                        await self._dispatch_alert(alert)
                        self.record_alert(source_type, "recovered")

            # Update uptime
            if metrics.last_connected_at:
                session_uptime = (now - metrics.last_connected_at).total_seconds()
                metrics.uptime_seconds = max(metrics.uptime_seconds, session_uptime)

            metrics.response_time_ms = response_time_ms

        else:
            # Connection failed
            if previous_status == ConnectionStatus.CONNECTED:
                # First disconnect - trigger alert immediately
                metrics.status = ConnectionStatus.DISCONNECTED
                metrics.last_disconnected_at = now
                metrics.disconnect_count += 1

                logger.warning(f"{config.source_name} disconnected")

                if self.should_alert(source_type, "disconnected"):
                    alert = DatasourceHealthAlert(
                        alert_type="disconnected",
                        source_type=source_type,
                        source_name=config.source_name,
                        message=f"{config.source_name} has disconnected",
                        severity=AlertSeverity.WARNING,
                        metrics=metrics.to_dict(),
                    )
                    await self._dispatch_alert(alert)
                    self.record_alert(source_type, "disconnected")

                # Start reconnection attempts
                await self._attempt_reconnect(source_type, config)

            elif previous_status == ConnectionStatus.DISCONNECTED:
                # Still disconnected - attempt reconnect
                await self._attempt_reconnect(source_type, config)

            elif previous_status == ConnectionStatus.RECONNECTING:
                # Reconnect in progress - check if we need to alert on extended downtime
                if metrics.last_disconnected_at:
                    downtime = (now - metrics.last_disconnected_at).total_seconds()
                    if downtime >= self.extended_downtime_threshold_seconds:
                        if self.should_alert(source_type, "extended_downtime"):
                            alert = DatasourceHealthAlert(
                                alert_type="extended_downtime",
                                source_type=source_type,
                                source_name=config.source_name,
                                message=(
                                    f"{config.source_name} has been down for "
                                    f"{downtime / 60:.1f} minutes"
                                ),
                                severity=AlertSeverity.CRITICAL,
                                metrics=metrics.to_dict(),
                            )
                            await self._dispatch_alert(alert)
                            self.record_alert(source_type, "extended_downtime")

        metrics.checked_at = now

    async def _attempt_reconnect(
        self,
        source_type: DataSourceType,
        config: DatasourceConfig,
    ) -> None:
        """Attempt to reconnect to a data source with backoff."""
        metrics = self._metrics[source_type]
        checker = self._checkers.get(source_type)

        if not checker:
            return

        if metrics.reconnect_attempts >= config.max_reconnect_attempts:
            # Max attempts reached
            if metrics.status != ConnectionStatus.FAILED:
                metrics.status = ConnectionStatus.FAILED
                logger.error(
                    f"{config.source_name} reconnection failed after "
                    f"{config.max_reconnect_attempts} attempts"
                )

                if self.should_alert(source_type, "reconnect_failed"):
                    alert = DatasourceHealthAlert(
                        alert_type="reconnect_failed",
                        source_type=source_type,
                        source_name=config.source_name,
                        message=(
                            f"{config.source_name} failed to reconnect after "
                            f"{config.max_reconnect_attempts} attempts. "
                            "Manual intervention required."
                        ),
                        severity=AlertSeverity.CRITICAL,
                        metrics=metrics.to_dict(),
                    )
                    await self._dispatch_alert(alert)
                    self.record_alert(source_type, "reconnect_failed")
            return

        # Get backoff delay
        backoff_idx = min(
            metrics.reconnect_attempts, len(config.reconnect_backoff_seconds) - 1
        )
        backoff_seconds = config.reconnect_backoff_seconds[backoff_idx]

        metrics.status = ConnectionStatus.RECONNECTING
        metrics.reconnect_attempts += 1
        metrics.total_reconnect_attempts += 1

        logger.info(
            f"Attempting to reconnect to {config.source_name} "
            f"(attempt {metrics.reconnect_attempts}/{config.max_reconnect_attempts}, "
            f"backoff={backoff_seconds}s)"
        )

        # Wait for backoff period
        await asyncio.sleep(backoff_seconds)

        # Try to reconnect (next health check will verify)

    async def _monitor_loop(self, source_type: DataSourceType) -> None:
        """Monitor loop for a single data source."""
        config = self.datasource_configs.get(source_type)
        if not config:
            return

        logger.info(
            f"Started monitoring {config.source_name} "
            f"(interval={config.check_interval_seconds}s)"
        )

        while self._running:
            try:
                await self._check_datasource(source_type, config)
                await asyncio.sleep(config.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error for {config.source_name}: {e}")
                await asyncio.sleep(5)

        logger.info(f"Stopped monitoring {config.source_name}")

    async def start_monitoring(self) -> None:
        """Start monitoring all configured data sources."""
        self._running = True

        for source_type in self.datasource_configs:
            config = self.datasource_configs[source_type]
            if not config.enabled:
                continue

            task = asyncio.create_task(self._monitor_loop(source_type))
            self._monitor_tasks[source_type] = task

        logger.info("Started data source health monitoring")

    async def stop_monitoring(self) -> None:
        """Stop monitoring all data sources."""
        self._running = False

        for source_type, task in self._monitor_tasks.items():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._monitor_tasks.clear()
        logger.info("Stopped data source health monitoring")

    def get_metrics(
        self,
        source_type: DataSourceType | None = None,
    ) -> dict[DataSourceType, ConnectionMetrics] | ConnectionMetrics | None:
        """Get connection metrics.

        Args:
            source_type: Filter by source type, or None for all

        Returns:
            Metrics dictionary, single metrics, or None
        """
        if source_type:
            return self._metrics.get(source_type)
        return self._metrics

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics for dashboard/Grafana.

        Returns:
            Dictionary with all metrics
        """
        return {
            "datasources": {st.value: m.to_dict() for st, m in self._metrics.items()},
            "summary": {
                "total": len(self._metrics),
                "connected": sum(1 for m in self._metrics.values() if m.is_connected),
                "disconnected": sum(
                    1
                    for m in self._metrics.values()
                    if m.status == ConnectionStatus.DISCONNECTED
                ),
                "reconnecting": sum(
                    1
                    for m in self._metrics.values()
                    if m.status == ConnectionStatus.RECONNECTING
                ),
                "failed": sum(
                    1
                    for m in self._metrics.values()
                    if m.status == ConnectionStatus.FAILED
                ),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_metrics_for_grafana(self) -> list[dict[str, Any]]:
        """Get metrics formatted for Grafana.

        Returns:
            List of metrics dictionaries with Grafana-compatible timestamps
        """
        results = []
        for metrics in self._metrics.values():
            results.append(
                {
                    "timestamp": metrics.checked_at.isoformat(),
                    "source_type": metrics.source_type.value,
                    "source_name": metrics.source_name,
                    "status": metrics.status.value,
                    "is_connected": 1 if metrics.is_connected else 0,
                    "is_healthy": 1 if metrics.is_healthy else 0,
                    "disconnect_count": metrics.disconnect_count,
                    "reconnect_attempts": metrics.reconnect_attempts,
                    "uptime_seconds": metrics.uptime_seconds,
                    "downtime_seconds": metrics.downtime_seconds,
                    "availability_percentage": metrics.availability_percentage,
                    "response_time_ms": metrics.response_time_ms or 0,
                }
            )
        return results

    async def check_now(self, source_type: DataSourceType | None = None) -> None:
        """Trigger immediate health check.

        Args:
            source_type: Specific source to check, or None for all
        """
        if source_type:
            config = self.datasource_configs.get(source_type)
            if config:
                await self._check_datasource(source_type, config)
        else:
            for st, config in self.datasource_configs.items():
                if config.enabled:
                    await self._check_datasource(st, config)

    def is_healthy(self, source_type: DataSourceType | None = None) -> bool:
        """Check if data sources are healthy.

        Args:
            source_type: Specific source to check, or None for all

        Returns:
            True if healthy
        """
        if source_type:
            metrics = self._metrics.get(source_type)
            return metrics.is_healthy if metrics else False

        return all(m.is_healthy for m in self._metrics.values())


# Convenience factory functions


def create_influxdb_config(
    host: str = "chiseai-influxdb",
    port: int = 18087,
    token: str | None = None,
    check_interval_seconds: float = 30.0,
) -> DatasourceConfig:
    """Create InfluxDB configuration.

    Args:
        host: InfluxDB host
        port: InfluxDB port
        token: InfluxDB token
        check_interval_seconds: Check interval

    Returns:
        DatasourceConfig for InfluxDB
    """
    return DatasourceConfig(
        source_type=DataSourceType.INFLUXDB,
        source_name="ChiseAI InfluxDB",
        host=host,
        port=port,
        token=token,
        check_interval_seconds=check_interval_seconds,
        reconnect_backoff_seconds=(2.0, 5.0, 10.0),
        max_reconnect_attempts=3,
    )


def create_postgresql_config(
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    username: str | None = None,
    password: str | None = None,
    check_interval_seconds: float = 60.0,
) -> DatasourceConfig:
    """Create PostgreSQL configuration from environment variables.

    Reads configuration from environment variables with intelligent defaults:
    - POSTGRES_HOST: defaults to 'chiseai-postgres' in container, 'host.docker.internal' on host
    - POSTGRES_PORT: defaults to 5434
    - POSTGRES_DB: defaults to 'chiseai'
    - POSTGRES_USER: defaults to 'chiseai'
    - POSTGRES_PASSWORD: required, no default

    Args:
        host: PostgreSQL host (overrides env var)
        port: PostgreSQL port (overrides env var)
        database: Database name (overrides env var)
        username: Username (overrides env var)
        password: Password (overrides env var)
        check_interval_seconds: Check interval

    Returns:
        DatasourceConfig for PostgreSQL

    Raises:
        ValueError: If POSTGRES_PASSWORD is not set and no password provided
    """
    import os

    # Detect if running in container
    in_container = os.path.exists("/.dockerenv")
    try:
        with open("/proc/1/cgroup") as f:
            cgroup = f.read()
            if any(m in cgroup for m in ["docker", "containerd", "kubepods"]):
                in_container = True
    except (FileNotFoundError, PermissionError):
        pass

    # Default host based on execution context
    default_host = "chiseai-postgres" if in_container else "host.docker.internal"

    # Read from environment with defaults
    final_host = (
        host if host is not None else os.environ.get("POSTGRES_HOST", default_host)
    )
    final_port = (
        port if port is not None else int(os.environ.get("POSTGRES_PORT", "5434"))
    )
    final_database = (
        database if database is not None else os.environ.get("POSTGRES_DB", "chiseai")
    )
    final_username = (
        username if username is not None else os.environ.get("POSTGRES_USER", "chiseai")
    )
    final_password = (
        password if password is not None else os.environ.get("POSTGRES_PASSWORD")
    )

    # Password is required
    if not final_password:
        raise ValueError(
            "POSTGRES_PASSWORD environment variable is required but not set. "
            "Please set it in your .env file or environment."
        )

    return DatasourceConfig(
        source_type=DataSourceType.POSTGRESQL,
        source_name="ChiseAI PostgreSQL",
        host=final_host,
        port=final_port,
        database=final_database,
        username=final_username,
        password=final_password,
        check_interval_seconds=check_interval_seconds,
        reconnect_backoff_seconds=(2.0, 5.0, 10.0),
        max_reconnect_attempts=3,
    )


def create_default_monitor(
    influxdb_token: str | None = None,
    postgres_username: str | None = None,
    postgres_password: str | None = None,
) -> DataSourceHealthMonitor:
    """Create a monitor with default ChiseAI configuration.

    Args:
        influxdb_token: InfluxDB token
        postgres_username: PostgreSQL username
        postgres_password: PostgreSQL password

    Returns:
        Configured DataSourceHealthMonitor
    """
    configs = [
        create_influxdb_config(token=influxdb_token),
        create_postgresql_config(
            username=postgres_username,
            password=postgres_password,
        ),
    ]

    return DataSourceHealthMonitor(
        datasource_configs=configs,
        alert_cooldown_seconds=10.0,  # 10s for ST-OPS-008 requirement
        extended_downtime_threshold_seconds=300.0,  # 5 minutes
    )
