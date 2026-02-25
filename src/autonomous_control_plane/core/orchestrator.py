"""Core orchestrator for the autonomous control plane.

Manages component lifecycle, persistence connections, and event coordination.

EP-NS-008: Autonomous Control Plane
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.config.settings import Settings, settings

if TYPE_CHECKING:
    import redis
    from influxdb_client.client.influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)


class ACPOrchestrator:
    """Central orchestrator for ACP components.

    Manages Redis and InfluxDB connections, handles component lifecycle,
    and provides graceful degradation when persistence services are unavailable.

    Example:
        >>> orchestrator = ACPOrchestrator()
        >>> orchestrator.start()
        >>> # Components are now connected to persistence
        >>> orchestrator.stop()
    """

    _instance: ACPOrchestrator | None = None
    _lock = threading.Lock()

    def __new__(cls, settings_obj: Settings | None = None) -> ACPOrchestrator:
        """Singleton pattern for global orchestrator access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    instance._pending_settings = settings_obj
                    cls._instance = instance
        return cls._instance

    def __init__(self, settings_obj: Settings | None = None):
        """Initialize the orchestrator.

        Args:
            settings_obj: Optional settings object (uses global settings if not provided)
        """
        if self._initialized:
            return

        self._initialized = True
        self._settings = (
            settings_obj or getattr(self, "_pending_settings", None) or settings
        )

        # Connection clients
        self._redis: redis.Redis | None = None
        self._influxdb: InfluxDBClient | None = None

        # Connection state
        self._redis_connected = False
        self._influxdb_connected = False

        # Lifecycle state
        self._running = False
        self._lock = threading.RLock()

    @property
    def redis(self) -> redis.Redis | None:
        """Get Redis client (None if not connected)."""
        return self._redis if self._redis_connected else None

    @property
    def influxdb(self) -> InfluxDBClient | None:
        """Get InfluxDB client (None if not connected)."""
        return self._influxdb if self._influxdb_connected else None

    @property
    def is_redis_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._redis_connected

    @property
    def is_influxdb_connected(self) -> bool:
        """Check if InfluxDB is connected."""
        return self._influxdb_connected

    def _connect_redis(self) -> bool:
        """Establish Redis connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host=self._settings.redis.host,
                port=self._settings.redis.port,
                db=self._settings.redis.db,
                password=self._settings.redis.password,
                socket_timeout=self._settings.redis.socket_timeout,
                socket_connect_timeout=self._settings.redis.socket_connect_timeout,
                decode_responses=True,
            )
            # Test connection
            self._redis.ping()
            self._redis_connected = True
            logger.info(
                f"ACPOrchestrator: Redis connected to "
                f"{self._settings.redis.host}:{self._settings.redis.port}"
            )
            return True

        except Exception as e:
            logger.warning(
                f"ACPOrchestrator: Redis connection failed - {e}. "
                f"Host: {self._settings.redis.host}:{self._settings.redis.port}. "
                "Running with in-memory fallback."
            )
            self._redis = None
            self._redis_connected = False
            return False

    def _connect_influxdb(self) -> bool:
        """Establish InfluxDB connection.

        Returns:
            True if connection successful, False otherwise
        """
        if not self._settings.telemetry.enabled:
            logger.info(
                "ACPOrchestrator: Telemetry disabled, skipping InfluxDB connection"
            )
            return False

        try:
            from influxdb_client.client.influxdb_client import InfluxDBClient

            self._influxdb = InfluxDBClient(
                url=self._settings.influxdb.url,
                token=self._settings.influxdb.token,
                org=self._settings.influxdb.org,
            )

            # Test connection by querying buckets
            health = self._influxdb.health()
            if health.status == "pass":
                self._influxdb_connected = True
                logger.info(
                    f"ACPOrchestrator: InfluxDB connected to "
                    f"{self._settings.influxdb.host}:{self._settings.influxdb.port}"
                )
                return True
            else:
                logger.warning(
                    f"ACPOrchestrator: InfluxDB health check failed - {health.message}"
                )
                self._influxdb = None
                self._influxdb_connected = False
                return False

        except Exception as e:
            logger.warning(
                f"ACPOrchestrator: InfluxDB connection failed - {e}. "
                f"Host: {self._settings.influxdb.host}:{self._settings.influxdb.port}. "
                "Telemetry disabled."
            )
            self._influxdb = None
            self._influxdb_connected = False
            return False

    def start(self) -> None:
        """Start the orchestrator and establish persistence connections."""
        with self._lock:
            if self._running:
                logger.warning("ACPOrchestrator: Already running")
                return

            self._running = True
            logger.info("ACPOrchestrator: Starting...")

            # Connect to Redis
            self._connect_redis()

            # Connect to InfluxDB
            self._connect_influxdb()

            # Log connection status
            redis_status = (
                "connected" if self._redis_connected else "unavailable (in-memory mode)"
            )
            influxdb_status = (
                "connected"
                if self._influxdb_connected
                else "unavailable (telemetry disabled)"
            )
            logger.info(f"ACPOrchestrator: Redis is {redis_status}")
            logger.info(f"ACPOrchestrator: InfluxDB is {influxdb_status}")

    def stop(self) -> None:
        """Stop the orchestrator and close persistence connections."""
        with self._lock:
            if not self._running:
                return

            logger.info("ACPOrchestrator: Stopping...")

            # Close Redis connection
            if self._redis is not None:
                try:
                    self._redis.close()
                    logger.info("ACPOrchestrator: Redis connection closed")
                except Exception as e:
                    logger.warning(
                        f"ACPOrchestrator: Error closing Redis connection - {e}"
                    )
                finally:
                    self._redis = None
                    self._redis_connected = False

            # Close InfluxDB connection
            if self._influxdb is not None:
                try:
                    self._influxdb.close()
                    logger.info("ACPOrchestrator: InfluxDB connection closed")
                except Exception as e:
                    logger.warning(
                        f"ACPOrchestrator: Error closing InfluxDB connection - {e}"
                    )
                finally:
                    self._influxdb = None
                    self._influxdb_connected = False

            self._running = False
            logger.info("ACPOrchestrator: Stopped")

    def health_check(self) -> dict[str, Any]:
        """Get health status of all persistence connections.

        Returns:
            Dictionary with connection status and details
        """
        with self._lock:
            redis_healthy = False
            redis_message = "Not connected"
            if self._redis is not None:
                try:
                    self._redis.ping()
                    redis_healthy = True
                    redis_message = f"Connected to {self._settings.redis.host}:{self._settings.redis.port}"
                except Exception as e:
                    redis_message = f"Connection error: {e}"

            influxdb_healthy = False
            influxdb_message = "Not connected"
            if self._influxdb is not None:
                try:
                    health = self._influxdb.health()
                    if health.status == "pass":
                        influxdb_healthy = True
                        influxdb_message = f"Connected to {self._settings.influxdb.host}:{self._settings.influxdb.port}"
                    else:
                        influxdb_message = f"Health check failed: {health.message}"
                except Exception as e:
                    influxdb_message = f"Connection error: {e}"

            return {
                "running": self._running,
                "redis": {
                    "connected": self._redis_connected,
                    "healthy": redis_healthy,
                    "message": redis_message,
                    "host": self._settings.redis.host,
                    "port": self._settings.redis.port,
                },
                "influxdb": {
                    "connected": self._influxdb_connected,
                    "healthy": influxdb_healthy,
                    "message": influxdb_message,
                    "host": self._settings.influxdb.host,
                    "port": self._settings.influxdb.port,
                },
            }

    def reconnect(self) -> dict[str, bool]:
        """Attempt to reconnect to persistence services.

        Returns:
            Dictionary mapping service name to connection success status
        """
        with self._lock:
            results = {}

            # Reconnect Redis
            if not self._redis_connected:
                results["redis"] = self._connect_redis()
            else:
                results["redis"] = True

            # Reconnect InfluxDB
            if not self._influxdb_connected:
                results["influxdb"] = self._connect_influxdb()
            else:
                results["influxdb"] = True

            return results


# Global orchestrator instance
orchestrator = ACPOrchestrator()
