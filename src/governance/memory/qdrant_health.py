"""Qdrant Health Monitor for ChiseAI.

Provides comprehensive health monitoring for Qdrant connectivity, performance,
and reliability with automatic Redis fallback queue for failed writes.

Usage:
    from src.governance.memory.qdrant_health import QdrantHealthMonitor

    monitor = QdrantHealthMonitor()

    # Check basic connectivity
    if monitor.check_connectivity():
        print("Qdrant is accessible")

    # Get current health status
    if monitor.is_healthy():
        print("Qdrant is healthy")
    else:
        print(f"Qdrant unhealthy: {monitor.get_metrics()}")

    # Start background monitoring
    monitor.start_monitoring()
    # ... do work ...
    monitor.stop_monitoring()
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_QDRANT_HOST = "host.docker.internal"
DEFAULT_QDRANT_PORT = 6334
DEFAULT_COLLECTION = "ChiseAI"
DEFAULT_VECTOR_SIZE = 384

# Redis fallback queue configuration
FALLBACK_QUEUE_KEY = "bmad:chiseai:qdrant:fallback_queue"
FALLBACK_QUEUE_MAX_SIZE = 10000
FALLBACK_QUEUE_LOCK_KEY = "bmad:chiseai:qdrant:fallback_queue:lock"

# Health check configuration
DEFAULT_CHECK_INTERVAL_SECONDS = 30
DEFAULT_METRICS_WINDOW_SECONDS = 300  # 5 minutes
DEFAULT_ALERT_THRESHOLD_CONSECUTIVE_FAILURES = 3
DEFAULT_LATENCY_THRESHOLD_MS = 1000  # 1 second
DEFAULT_SUCCESS_RATE_THRESHOLD = 0.95  # 95%

# Retry configuration
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY_SECONDS = 1
DEFAULT_RETRY_MAX_DELAY_SECONDS = 60


class HealthStatus(Enum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ErrorType(Enum):
    """Types of errors that can occur during Qdrant operations."""

    CONNECTION_ERROR = "connection_error"
    TIMEOUT_ERROR = "timeout_error"
    WRITE_ERROR = "write_error"
    READ_ERROR = "read_error"
    VALIDATION_ERROR = "validation_error"
    VECTOR_DIMENSION_ERROR = "vector_dimension_error"
    COLLECTION_ERROR = "collection_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class HealthMetrics:
    """Metrics for Qdrant health monitoring."""

    # Connection metrics
    connectivity_checks_total: int = 0
    connectivity_checks_success: int = 0
    connectivity_checks_failed: int = 0
    last_connectivity_check_at: str | None = None

    # Latency metrics (in milliseconds)
    write_latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    avg_write_latency_ms: float = 0.0
    p95_write_latency_ms: float = 0.0
    max_write_latency_ms: float = 0.0

    # Success rate metrics
    write_attempts_total: int = 0
    write_attempts_success: int = 0
    write_attempts_failed: int = 0
    success_rate: float = 1.0

    # Error tracking
    error_counts: dict[str, int] = field(default_factory=dict)
    consecutive_failures: int = 0
    last_error_at: str | None = None
    last_error_type: str | None = None
    last_error_message: str | None = None

    # Alert state
    alert_triggered: bool = False
    alert_triggered_at: str | None = None
    alert_message: str | None = None

    # Timestamp
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def record_write_latency(self, latency_ms: float) -> None:
        """Record a write latency measurement."""
        self.write_latencies_ms.append(latency_ms)
        self._update_latency_stats()

    def _update_latency_stats(self) -> None:
        """Update latency statistics from recorded measurements."""
        if not self.write_latencies_ms:
            self.avg_write_latency_ms = 0.0
            self.p95_write_latency_ms = 0.0
            self.max_write_latency_ms = 0.0
            return

        sorted_latencies = sorted(self.write_latencies_ms)
        n = len(sorted_latencies)

        self.avg_write_latency_ms = sum(sorted_latencies) / n
        self.max_write_latency_ms = sorted_latencies[-1]

        # Calculate p95
        p95_index = int(n * 0.95)
        if p95_index >= n:
            p95_index = n - 1
        self.p95_write_latency_ms = sorted_latencies[p95_index]

    def record_write_result(
        self,
        success: bool,
        error_type: ErrorType | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record the result of a write attempt."""
        self.write_attempts_total += 1

        if success:
            self.write_attempts_success += 1
            self.consecutive_failures = 0
        else:
            self.write_attempts_failed += 1
            self.consecutive_failures += 1
            self.last_error_at = datetime.now(UTC).isoformat()
            self.last_error_type = (
                error_type.value if error_type else ErrorType.UNKNOWN_ERROR.value
            )
            self.last_error_message = error_message

            # Update error counts
            error_key = (
                error_type.value if error_type else ErrorType.UNKNOWN_ERROR.value
            )
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

        # Update success rate
        if self.write_attempts_total > 0:
            self.success_rate = self.write_attempts_success / self.write_attempts_total

    def record_connectivity_result(self, success: bool) -> None:
        """Record the result of a connectivity check."""
        self.connectivity_checks_total += 1
        self.last_connectivity_check_at = datetime.now(UTC).isoformat()

        if success:
            self.connectivity_checks_success += 1
        else:
            self.connectivity_checks_failed += 1

    def trigger_alert(self, message: str) -> None:
        """Trigger an alert."""
        self.alert_triggered = True
        self.alert_triggered_at = datetime.now(UTC).isoformat()
        self.alert_message = message
        logger.warning(f"Qdrant health alert triggered: {message}")

    def clear_alert(self) -> None:
        """Clear the current alert."""
        if self.alert_triggered:
            self.alert_triggered = False
            logger.info("Qdrant health alert cleared")

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "connectivity": {
                "checks_total": self.connectivity_checks_total,
                "checks_success": self.connectivity_checks_success,
                "checks_failed": self.connectivity_checks_failed,
                "last_check_at": self.last_connectivity_check_at,
            },
            "latency": {
                "avg_ms": round(self.avg_write_latency_ms, 2),
                "p95_ms": round(self.p95_write_latency_ms, 2),
                "max_ms": round(self.max_write_latency_ms, 2),
                "samples": len(self.write_latencies_ms),
            },
            "success_rate": {
                "rate": round(self.success_rate, 4),
                "attempts_total": self.write_attempts_total,
                "attempts_success": self.write_attempts_success,
                "attempts_failed": self.write_attempts_failed,
            },
            "errors": {
                "counts": self.error_counts.copy(),
                "consecutive_failures": self.consecutive_failures,
                "last_error_at": self.last_error_at,
                "last_error_type": self.last_error_type,
                "last_error_message": self.last_error_message,
            },
            "alert": {
                "triggered": self.alert_triggered,
                "triggered_at": self.alert_triggered_at,
                "message": self.alert_message,
            },
            "recorded_at": self.recorded_at,
        }


@dataclass
class FallbackQueueEntry:
    """Entry in the Redis fallback queue."""

    point_id: str
    vector: list[float]
    payload: dict[str, Any]
    collection: str | None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    retry_count: int = 0
    last_error: str | None = None

    def to_json(self) -> str:
        """Convert entry to JSON string."""
        return json.dumps(
            {
                "point_id": self.point_id,
                "vector": self.vector,
                "payload": self.payload,
                "collection": self.collection,
                "timestamp": self.timestamp,
                "retry_count": self.retry_count,
                "last_error": self.last_error,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> FallbackQueueEntry:
        """Create entry from JSON string."""
        data = json.loads(json_str)
        return cls(
            point_id=data["point_id"],
            vector=data["vector"],
            payload=data["payload"],
            collection=data.get("collection"),
            timestamp=data["timestamp"],
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
        )


class QdrantHealthMonitor:
    """Health monitor for Qdrant with automatic fallback queue.

    This class provides comprehensive health monitoring for Qdrant including:
    - Connectivity checks
    - Write latency measurements
    - Success rate tracking
    - Error type aggregation
    - Alert threshold checking
    - Redis fallback queue for failed writes
    - Background monitoring thread

    Attributes:
        host: Qdrant server host
        port: Qdrant server port
        collection: Default collection name
        vector_size: Expected vector dimension
        check_interval_seconds: Interval between health checks
        metrics_window_seconds: Time window for metrics aggregation
        alert_threshold_consecutive_failures: Number of consecutive failures to trigger alert
        latency_threshold_ms: Latency threshold for degraded status
        success_rate_threshold: Success rate threshold for healthy status
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection: str | None = None,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        redis_client: Any | None = None,
        check_interval_seconds: int = DEFAULT_CHECK_INTERVAL_SECONDS,
        metrics_window_seconds: int = DEFAULT_METRICS_WINDOW_SECONDS,
        alert_threshold_consecutive_failures: int = DEFAULT_ALERT_THRESHOLD_CONSECUTIVE_FAILURES,
        latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS,
        success_rate_threshold: float = DEFAULT_SUCCESS_RATE_THRESHOLD,
    ):
        """Initialize the Qdrant health monitor.

        Args:
            host: Qdrant server host (default: host.docker.internal)
            port: Qdrant server port (default: 6334)
            collection: Default collection name (default: ChiseAI)
            vector_size: Expected vector dimension (default: 384)
            redis_client: Optional pre-configured Redis client
            check_interval_seconds: Interval between health checks
            metrics_window_seconds: Time window for metrics aggregation
            alert_threshold_consecutive_failures: Consecutive failures before alert
            latency_threshold_ms: Latency threshold for degraded status
            success_rate_threshold: Success rate threshold for healthy status
        """
        self.host = host or DEFAULT_QDRANT_HOST
        self.port = port or DEFAULT_QDRANT_PORT
        self.collection = collection or DEFAULT_COLLECTION
        self.vector_size = vector_size
        self._redis_client = redis_client

        self.check_interval_seconds = check_interval_seconds
        self.metrics_window_seconds = metrics_window_seconds
        self.alert_threshold_consecutive_failures = alert_threshold_consecutive_failures
        self.latency_threshold_ms = latency_threshold_ms
        self.success_rate_threshold = success_rate_threshold

        self._metrics = HealthMetrics()
        self._qdrant_client: Any | None = None
        self._monitoring_thread: threading.Thread | None = None
        self._stop_monitoring = threading.Event()
        self._lock = threading.Lock()

        # Redis connection cache
        self._redis: Any | None = None

    def _get_qdrant_client(self) -> Any:
        """Get or create Qdrant client.

        Returns:
            Qdrant client instance

        Raises:
            ImportError: If qdrant_client package is not installed
            ConnectionError: If cannot connect to Qdrant server
        """
        if self._qdrant_client is not None:
            return self._qdrant_client

        try:
            from qdrant_client import QdrantClient

            self._qdrant_client = QdrantClient(
                host=self.host,
                port=self.port,
                timeout=10,
            )
            logger.debug(f"Connected to Qdrant at {self.host}:{self.port}")
            return self._qdrant_client
        except ImportError as e:
            logger.error("qdrant_client package not installed")
            raise ImportError(
                "qdrant_client is required. Install with: pip install qdrant-client"
            ) from e
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise ConnectionError(
                f"Cannot connect to Qdrant at {self.host}:{self.port}"
            ) from e

    def _get_redis(self) -> Any | None:
        """Get or create Redis connection.

        Returns:
            Redis client or None if connection fails
        """
        if self._redis is not None:
            return self._redis

        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis.ping()
            return self._redis
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    def check_connectivity(self) -> bool:
        """Check if Qdrant is accessible.

        Returns:
            True if Qdrant is accessible, False otherwise
        """
        try:
            client = self._get_qdrant_client()
            # Try to get collections as a connectivity test
            client.get_collections()

            with self._lock:
                self._metrics.record_connectivity_result(success=True)

            logger.debug("Qdrant connectivity check: success")
            return True

        except Exception as e:
            with self._lock:
                self._metrics.record_connectivity_result(success=False)
                self._metrics.record_write_result(
                    success=False,
                    error_type=ErrorType.CONNECTION_ERROR,
                    error_message=str(e),
                )

            logger.warning(f"Qdrant connectivity check failed: {e}")
            return False

    def get_write_latency(self) -> float:
        """Measure write latency by performing a test write.

        Returns:
            Write latency in milliseconds
        """
        import hashlib
        import uuid

        from qdrant_client.models import PointStruct

        test_id = f"health_check_{uuid.uuid4().hex[:8]}"
        test_vector = [0.01] * self.vector_size

        # Create deterministic UUID for test point without weak hashing primitives.
        point_id = str(uuid.UUID(bytes=hashlib.sha256(test_id.encode()).digest()[:16]))

        start_time = time.time()

        try:
            client = self._get_qdrant_client()

            # Ensure collection exists
            self._ensure_collection_exists(client, self.collection)

            # Perform test write
            client.upsert(
                collection_name=self.collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=test_vector,
                        payload={
                            "test": True,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )

            latency_ms = (time.time() - start_time) * 1000

            # Clean up test point
            with contextlib.suppress(Exception):
                client.delete(
                    collection_name=self.collection,
                    points_selector=[point_id],
                )

            with self._lock:
                self._metrics.record_write_latency(latency_ms)
                self._metrics.record_write_result(success=True)

            logger.debug(f"Write latency: {latency_ms:.2f}ms")
            return latency_ms

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            with self._lock:
                self._metrics.record_write_latency(latency_ms)
                self._metrics.record_write_result(
                    success=False,
                    error_type=ErrorType.WRITE_ERROR,
                    error_message=str(e),
                )

            logger.warning(f"Write latency check failed: {e}")
            return latency_ms

    def _ensure_collection_exists(self, client: Any, collection_name: str) -> None:
        """Ensure a collection exists, creating it if necessary.

        Args:
            client: Qdrant client instance
            collection_name: Name of the collection
        """
        from qdrant_client.models import Distance, VectorParams

        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if collection_name not in collection_names:
            logger.info(f"Creating collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )

    def get_success_rate(self, window_seconds: int | None = None) -> float:
        """Get the write success rate over a time window.

        Args:
            window_seconds: Time window in seconds (default: metrics_window_seconds)

        Returns:
            Success rate as a float between 0.0 and 1.0
        """
        with self._lock:
            return self._metrics.success_rate

    def get_error_types(self) -> dict[str, int]:
        """Get counts of errors by type.

        Returns:
            Dictionary mapping error type to count
        """
        with self._lock:
            return self._metrics.error_counts.copy()

    def is_healthy(self) -> bool:
        """Check if Qdrant is healthy.

        Returns:
            True if healthy, False otherwise
        """
        status = self._determine_health_status()
        return status == HealthStatus.HEALTHY

    def get_health_status(self) -> HealthStatus:
        """Get the current health status.

        Returns:
            HealthStatus enum value
        """
        return self._determine_health_status()

    def _determine_health_status(self) -> HealthStatus:
        """Determine the health status based on metrics.

        Returns:
            HealthStatus enum value
        """
        with self._lock:
            metrics = self._metrics

        # Check connectivity
        if (
            metrics.connectivity_checks_failed > 0
            and metrics.connectivity_checks_success == 0
        ):
            return HealthStatus.UNHEALTHY

        # Check consecutive failures
        if metrics.consecutive_failures >= self.alert_threshold_consecutive_failures:
            return HealthStatus.UNHEALTHY

        # Check success rate (if we have enough samples)
        if metrics.write_attempts_total >= 10:
            if metrics.success_rate < self.success_rate_threshold:
                return HealthStatus.DEGRADED

        # Check latency
        if metrics.avg_write_latency_ms > self.latency_threshold_ms:
            return HealthStatus.DEGRADED

        # Check for active alerts
        if metrics.alert_triggered:
            return HealthStatus.UNHEALTHY

        return HealthStatus.HEALTHY

    def get_metrics(self) -> dict[str, Any]:
        """Get comprehensive health metrics.

        Returns:
            Dictionary with all health metrics
        """
        with self._lock:
            metrics_dict = self._metrics.to_dict()

        # Add health status
        metrics_dict["health_status"] = self._determine_health_status().value

        # Add configuration
        metrics_dict["config"] = {
            "host": self.host,
            "port": self.port,
            "collection": self.collection,
            "check_interval_seconds": self.check_interval_seconds,
            "alert_threshold_consecutive_failures": self.alert_threshold_consecutive_failures,
            "latency_threshold_ms": self.latency_threshold_ms,
            "success_rate_threshold": self.success_rate_threshold,
        }

        # Add fallback queue info
        metrics_dict["fallback_queue"] = self._get_fallback_queue_info()

        return metrics_dict

    def _check_alert_thresholds(self) -> None:
        """Check if any alert thresholds are crossed and trigger alerts."""
        with self._lock:
            metrics = self._metrics

        # Check consecutive failures
        if metrics.consecutive_failures >= self.alert_threshold_consecutive_failures:
            message = (
                f"Qdrant consecutive failures: {metrics.consecutive_failures} "
                f"(threshold: {self.alert_threshold_consecutive_failures})"
            )
            with self._lock:
                self._metrics.trigger_alert(message)
            return

        # Check success rate
        if metrics.write_attempts_total >= 10:
            if metrics.success_rate < self.success_rate_threshold:
                message = (
                    f"Qdrant success rate degraded: {metrics.success_rate:.2%} "
                    f"(threshold: {self.success_rate_threshold:.2%})"
                )
                with self._lock:
                    self._metrics.trigger_alert(message)
                return

        # Check latency
        if metrics.avg_write_latency_ms > self.latency_threshold_ms:
            message = (
                f"Qdrant latency high: {metrics.avg_write_latency_ms:.2f}ms "
                f"(threshold: {self.latency_threshold_ms}ms)"
            )
            with self._lock:
                self._metrics.trigger_alert(message)
            return

        # Clear alert if conditions are normal
        with self._lock:
            if metrics.alert_triggered:
                self._metrics.clear_alert()

    def start_monitoring(self) -> None:
        """Start the background monitoring thread."""
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            logger.warning("Monitoring thread already running")
            return

        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="qdrant-health-monitor",
            daemon=True,
        )
        self._monitoring_thread.start()
        logger.info("Qdrant health monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the background monitoring thread."""
        if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
            return

        self._stop_monitoring.set()
        self._monitoring_thread.join(timeout=5)
        logger.info("Qdrant health monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while not self._stop_monitoring.is_set():
            try:
                # Check connectivity
                self.check_connectivity()

                # Check write latency
                self.get_write_latency()

                # Check alert thresholds
                self._check_alert_thresholds()

                # Try to replay fallback queue
                self._replay_fallback_queue()

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            # Wait for next check
            self._stop_monitoring.wait(self.check_interval_seconds)

    def _get_fallback_queue_info(self) -> dict[str, Any]:
        """Get information about the fallback queue.

        Returns:
            Dictionary with queue information
        """
        redis = self._get_redis()
        if redis is None:
            return {"available": False, "error": "Redis not available"}

        try:
            queue_length = redis.llen(FALLBACK_QUEUE_KEY)
            return {
                "available": True,
                "queue_length": queue_length,
                "max_size": FALLBACK_QUEUE_MAX_SIZE,
                "utilization": queue_length / FALLBACK_QUEUE_MAX_SIZE,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def add_to_fallback_queue(
        self,
        point_id: str,
        vector: Sequence[float],
        payload: dict[str, Any],
        collection: str | None = None,
    ) -> bool:
        """Add a write operation to the fallback queue.

        Args:
            point_id: Unique identifier for the point
            vector: Vector embedding
            payload: Metadata payload
            collection: Optional collection name override

        Returns:
            True if successfully added to queue, False otherwise
        """
        redis = self._get_redis()
        if redis is None:
            logger.error("Cannot add to fallback queue: Redis not available")
            return False

        try:
            # Check queue size
            current_size = redis.llen(FALLBACK_QUEUE_KEY)
            if current_size >= FALLBACK_QUEUE_MAX_SIZE:
                logger.error(f"Fallback queue full ({current_size} entries)")
                return False

            # Create entry
            entry = FallbackQueueEntry(
                point_id=point_id,
                vector=list(vector),
                payload=payload,
                collection=collection,
            )

            # Add to queue
            redis.lpush(FALLBACK_QUEUE_KEY, entry.to_json())
            logger.info(f"Added point {point_id} to fallback queue")
            return True

        except Exception as e:
            logger.error(f"Failed to add to fallback queue: {e}")
            return False

    def _replay_fallback_queue(self) -> int:
        """Replay entries from the fallback queue.

        Returns:
            Number of entries successfully replayed
        """
        redis = self._get_redis()
        if redis is None:
            return 0

        # Check if Qdrant is healthy before replaying
        if not self.is_healthy():
            logger.debug("Skipping fallback queue replay: Qdrant not healthy")
            return 0

        replayed = 0
        max_entries = 10  # Process in batches

        try:
            for _ in range(max_entries):
                # Pop from queue (from the end, oldest first)
                entry_json = redis.rpop(FALLBACK_QUEUE_KEY)
                if entry_json is None:
                    break

                try:
                    entry = FallbackQueueEntry.from_json(entry_json)

                    # Check retry count
                    if entry.retry_count >= DEFAULT_RETRY_MAX_ATTEMPTS:
                        logger.warning(
                            f"Dropping fallback entry {entry.point_id}: "
                            f"max retries exceeded"
                        )
                        continue

                    # Try to write to Qdrant
                    if self._replay_entry(entry):
                        replayed += 1
                    else:
                        # Re-queue with incremented retry count
                        entry.retry_count += 1
                        entry.last_error = datetime.now(UTC).isoformat()
                        redis.lpush(FALLBACK_QUEUE_KEY, entry.to_json())

                except Exception as e:
                    logger.error(f"Failed to replay fallback entry: {e}")
                    # Re-queue the raw entry
                    redis.lpush(FALLBACK_QUEUE_KEY, entry_json)

        except Exception as e:
            logger.error(f"Error replaying fallback queue: {e}")

        if replayed > 0:
            logger.info(f"Replayed {replayed} entries from fallback queue")

        return replayed

    def _replay_entry(self, entry: FallbackQueueEntry) -> bool:
        """Replay a single fallback queue entry.

        Args:
            entry: Fallback queue entry to replay

        Returns:
            True if replay successful, False otherwise
        """
        from qdrant_client.models import PointStruct

        try:
            client = self._get_qdrant_client()
            collection = entry.collection or self.collection

            # Ensure collection exists
            self._ensure_collection_exists(client, collection)

            # Perform the write
            client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=entry.point_id,
                        vector=entry.vector,
                        payload=entry.payload,
                    )
                ],
            )

            logger.debug(f"Replayed fallback entry: {entry.point_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to replay fallback entry {entry.point_id}: {e}")
            return False

    def clear_fallback_queue(self) -> int:
        """Clear all entries from the fallback queue.

        Returns:
            Number of entries cleared
        """
        redis = self._get_redis()
        if redis is None:
            return 0

        try:
            queue_length = redis.llen(FALLBACK_QUEUE_KEY)
            redis.delete(FALLBACK_QUEUE_KEY)
            logger.info(f"Cleared {queue_length} entries from fallback queue")
            return queue_length
        except Exception as e:
            logger.error(f"Failed to clear fallback queue: {e}")
            return 0

    def get_fallback_queue_entries(self, limit: int = 100) -> list[FallbackQueueEntry]:
        """Get entries from the fallback queue.

        Args:
            limit: Maximum number of entries to retrieve

        Returns:
            List of fallback queue entries
        """
        redis = self._get_redis()
        if redis is None:
            return []

        try:
            entries_json = redis.lrange(FALLBACK_QUEUE_KEY, 0, limit - 1)
            entries = []
            for entry_json in entries_json:
                try:
                    entries.append(FallbackQueueEntry.from_json(entry_json))
                except Exception as e:
                    logger.warning(f"Failed to parse fallback entry: {e}")
            return entries
        except Exception as e:
            logger.error(f"Failed to get fallback queue entries: {e}")
            return []

    def __enter__(self):
        """Context manager entry - start monitoring."""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop monitoring."""
        self.stop_monitoring()
        return False
