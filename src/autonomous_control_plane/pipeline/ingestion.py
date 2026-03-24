"""Telemetry ingestion layer for the autonomous control plane.

Provides multi-source ingestion with rate limiting, backpressure handling,
and buffer management with overflow protection.

ST-CONTROL-001: Telemetry Pipeline
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from autonomous_control_plane.config.pipeline_settings import (
    IngestionSourceConfig,
    IngestionSourceType,
    pipeline_settings,
)

logger = logging.getLogger(__name__)


class IngestionStatus(Enum):
    """Status of an ingestion operation."""

    ACCEPTED = "accepted"
    REJECTED_RATE_LIMIT = "rejected_rate_limit"
    REJECTED_BUFFER_FULL = "rejected_buffer_full"
    REJECTED_FILTERED = "rejected_filtered"
    REJECTED_SAMPLING = "rejected_sampling"


@dataclass
class TelemetryEvent:
    """A telemetry event to be ingested."""

    source_type: IngestionSourceType
    timestamp: float
    data: dict[str, Any]
    metadata: dict[str, str] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(time.time_ns()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "source_type": self.source_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""

    status: IngestionStatus
    event_id: str | None = None
    message: str = ""
    queue_position: int | None = None


class TokenBucketRateLimiter:
    """Token bucket rate limiter for ingestion control."""

    def __init__(self, rate: float, burst_size: int):
        """Initialize rate limiter.

        Args:
            rate: Tokens per second
            burst_size: Maximum burst size
        """
        self.rate = rate
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            return min(self.burst_size, self.tokens + elapsed * self.rate)


class CircularBuffer:
    """Thread-safe circular buffer with overflow protection."""

    def __init__(self, max_size: int, overflow_strategy: str = "drop_oldest"):
        """Initialize circular buffer.

        Args:
            max_size: Maximum buffer size
            overflow_strategy: How to handle overflow (drop_oldest, drop_newest, block)
        """
        self.max_size = max_size
        self.overflow_strategy = overflow_strategy
        self._buffer: deque[TelemetryEvent] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)
        self._dropped_count = 0

    def put(self, event: TelemetryEvent, timeout: float | None = None) -> bool:
        """Put an event into the buffer.

        Args:
            event: Event to add
            timeout: Timeout for blocking strategy

        Returns:
            True if added, False if dropped
        """
        with self._lock:
            if len(self._buffer) >= self.max_size:
                if self.overflow_strategy == "drop_newest":
                    self._dropped_count += 1
                    return False
                elif self.overflow_strategy == "block":
                    if not self._not_full.wait(timeout=timeout):
                        self._dropped_count += 1
                        return False

            self._buffer.append(event)
            self._not_empty.notify()
            return True

    def get(self, timeout: float | None = None) -> TelemetryEvent | None:
        """Get an event from the buffer.

        Args:
            timeout: Timeout to wait for an event

        Returns:
            Event or None if timeout
        """
        with self._lock:
            if not self._buffer:
                if not self._not_empty.wait(timeout=timeout):
                    return None

            if self._buffer:
                event = self._buffer.popleft()
                self._not_full.notify()
                return event
            return None

    def get_batch(
        self, max_size: int, timeout: float | None = None
    ) -> list[TelemetryEvent]:
        """Get a batch of events from the buffer.

        Args:
            max_size: Maximum number of events to get
            timeout: Timeout to wait for events

        Returns:
            List of events
        """
        with self._lock:
            if not self._buffer:
                if not self._not_empty.wait(timeout=timeout):
                    return []

            batch_size = min(max_size, len(self._buffer))
            batch = [self._buffer.popleft() for _ in range(batch_size)]
            self._not_full.notify()
            return batch

    def size(self) -> int:
        """Get current buffer size."""
        with self._lock:
            return len(self._buffer)

    def is_full(self) -> bool:
        """Check if buffer is full."""
        with self._lock:
            return len(self._buffer) >= self.max_size

    def get_dropped_count(self) -> int:
        """Get number of dropped events."""
        with self._lock:
            return self._dropped_count

    def clear(self) -> list[TelemetryEvent]:
        """Clear and return all events in buffer."""
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
            self._not_full.notify_all()
            return events


class IngestionSource:
    """A telemetry ingestion source with rate limiting and buffering."""

    def __init__(self, config: IngestionSourceConfig):
        """Initialize ingestion source.

        Args:
            config: Source configuration
        """
        self.config = config
        self.name = config.name
        self.source_type = config.source_type
        self.enabled = config.enabled

        # Rate limiter
        self._rate_limiter = TokenBucketRateLimiter(
            rate=config.rate_limit.events_per_second,
            burst_size=config.rate_limit.burst_size,
        )

        # Buffer
        self._buffer = CircularBuffer(
            max_size=config.buffer.max_size,
            overflow_strategy=config.buffer.overflow_strategy,
        )

        # Metrics
        self._metrics = {
            "accepted": 0,
            "rejected_rate_limit": 0,
            "rejected_buffer_full": 0,
            "rejected_filtered": 0,
            "rejected_sampling": 0,
        }
        self._metrics_lock = threading.Lock()

        # Callbacks for processed events
        self._callbacks: list[Callable[[TelemetryEvent], None]] = []

    def ingest(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a telemetry event.

        Args:
            data: Event data
            metadata: Event metadata

        Returns:
            Ingestion result
        """
        if not self.enabled:
            return IngestionResult(
                status=IngestionStatus.REJECTED_FILTERED,
                message="Source is disabled",
            )

        # Apply sampling
        if self.config.sampling_rate < 1.0:
            import random

            if random.random() > self.config.sampling_rate:
                with self._metrics_lock:
                    self._metrics["rejected_sampling"] += 1
                return IngestionResult(
                    status=IngestionStatus.REJECTED_SAMPLING,
                    message="Event dropped by sampling",
                )

        # Check rate limit
        if self.config.rate_limit.enabled and not self._rate_limiter.acquire():
            with self._metrics_lock:
                self._metrics["rejected_rate_limit"] += 1
            return IngestionResult(
                status=IngestionStatus.REJECTED_RATE_LIMIT,
                message="Rate limit exceeded",
            )

        # Create event
        event = TelemetryEvent(
            source_type=self.source_type,
            timestamp=time.time(),
            data=data,
            metadata=metadata or {},
        )

        # Check filters
        if not self._apply_filters(event):
            with self._metrics_lock:
                self._metrics["rejected_filtered"] += 1
            return IngestionResult(
                status=IngestionStatus.REJECTED_FILTERED,
                event_id=event.event_id,
                message="Event filtered out",
            )

        # Add to buffer
        if not self._buffer.put(event):
            with self._metrics_lock:
                self._metrics["rejected_buffer_full"] += 1
            return IngestionResult(
                status=IngestionStatus.REJECTED_BUFFER_FULL,
                event_id=event.event_id,
                message="Buffer full",
            )

        with self._metrics_lock:
            self._metrics["accepted"] += 1

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

        return IngestionResult(
            status=IngestionStatus.ACCEPTED,
            event_id=event.event_id,
            queue_position=self._buffer.size(),
        )

    def _apply_filters(self, event: TelemetryEvent) -> bool:
        """Apply filter rules to event.

        Args:
            event: Event to filter

        Returns:
            True if event passes filters
        """
        for filter_rule in self.config.filters:
            field = filter_rule.get("field")
            operator = filter_rule.get("operator")
            value = filter_rule.get("value")

            if field and operator:
                event_value = event.data.get(field)
                if operator == "eq" and event_value != value or operator == "ne" and event_value == value or operator == "gt" and not (event_value > value) or operator == "lt" and not (event_value < value) or operator == "contains" and value not in str(event_value):
                    return False

        return True

    def get_events(
        self, max_count: int = 100, timeout: float = 0.0
    ) -> list[TelemetryEvent]:
        """Get events from buffer.

        Args:
            max_count: Maximum number of events
            timeout: Timeout to wait for events

        Returns:
            List of events
        """
        return self._buffer.get_batch(max_count, timeout)

    def get_metrics(self) -> dict[str, int]:
        """Get ingestion metrics."""
        with self._metrics_lock:
            return self._metrics.copy()

    def get_buffer_stats(self) -> dict[str, Any]:
        """Get buffer statistics."""
        return {
            "size": self._buffer.size(),
            "max_size": self.config.buffer.max_size,
            "is_full": self._buffer.is_full(),
            "dropped_count": self._buffer.get_dropped_count(),
            "available_tokens": self._rate_limiter.get_available_tokens(),
        }

    def register_callback(self, callback: Callable[[TelemetryEvent], None]) -> None:
        """Register a callback for processed events."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[TelemetryEvent], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def clear(self) -> list[TelemetryEvent]:
        """Clear all events from buffer."""
        return self._buffer.clear()


class TelemetryIngestionLayer:
    """Multi-source telemetry ingestion layer.

    Manages multiple ingestion sources with configurable rate limiting,
    buffering, and backpressure handling.

    Example:
        >>> ingestion = TelemetryIngestionLayer()
        >>> result = ingestion.ingest_log({"message": "test", "level": "info"})
        >>> print(result.status)
        IngestionStatus.ACCEPTED
    """

    def __init__(self, settings: PipelineSettings | None = None):
        """Initialize ingestion layer.

        Args:
            settings: Pipeline settings (uses default if not provided)
        """
        self.settings = settings or pipeline_settings
        self._sources: dict[str, IngestionSource] = {}
        self._lock = threading.Lock()

        # Initialize sources from settings
        for source_config in self.settings.sources:
            self._sources[source_config.name] = IngestionSource(source_config)

    def get_source(self, name: str) -> IngestionSource | None:
        """Get an ingestion source by name.

        Args:
            name: Source name

        Returns:
            Ingestion source or None
        """
        with self._lock:
            return self._sources.get(name)

    def add_source(self, config: IngestionSourceConfig) -> IngestionSource:
        """Add a new ingestion source.

        Args:
            config: Source configuration

        Returns:
            Created ingestion source
        """
        with self._lock:
            source = IngestionSource(config)
            self._sources[config.name] = source
            return source

    def remove_source(self, name: str) -> IngestionSource | None:
        """Remove an ingestion source.

        Args:
            name: Source name

        Returns:
            Removed source or None
        """
        with self._lock:
            return self._sources.pop(name, None)

    def ingest_log(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a log event.

        Args:
            data: Log data
            metadata: Log metadata

        Returns:
            Ingestion result
        """
        source = self.get_source("logs")
        if source:
            return source.ingest(data, metadata)
        return IngestionResult(
            status=IngestionStatus.REJECTED_FILTERED,
            message="Logs source not configured",
        )

    def ingest_metric(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a metric event.

        Args:
            data: Metric data
            metadata: Metric metadata

        Returns:
            Ingestion result
        """
        source = self.get_source("metrics")
        if source:
            return source.ingest(data, metadata)
        return IngestionResult(
            status=IngestionStatus.REJECTED_FILTERED,
            message="Metrics source not configured",
        )

    def ingest_event(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a generic event.

        Args:
            data: Event data
            metadata: Event metadata

        Returns:
            Ingestion result
        """
        source = self.get_source("events")
        if source:
            return source.ingest(data, metadata)
        return IngestionResult(
            status=IngestionStatus.REJECTED_FILTERED,
            message="Events source not configured",
        )

    def ingest(
        self,
        source_type: IngestionSourceType,
        data: dict[str, Any],
        metadata: dict[str, str] | None = None,
    ) -> IngestionResult:
        """Ingest an event to a specific source type.

        Args:
            source_type: Type of source
            data: Event data
            metadata: Event metadata

        Returns:
            Ingestion result
        """
        # Find source by type
        with self._lock:
            for source in self._sources.values():
                if source.source_type == source_type and source.enabled:
                    return source.ingest(data, metadata)

        return IngestionResult(
            status=IngestionStatus.REJECTED_FILTERED,
            message=f"No enabled source found for type {source_type.value}",
        )

    def get_all_metrics(self) -> dict[str, dict[str, int]]:
        """Get metrics from all sources."""
        with self._lock:
            return {
                name: source.get_metrics() for name, source in self._sources.items()
            }

    def get_all_buffer_stats(self) -> dict[str, dict[str, Any]]:
        """Get buffer stats from all sources."""
        with self._lock:
            return {
                name: source.get_buffer_stats()
                for name, source in self._sources.items()
            }

    def get_backpressure_status(self) -> dict[str, Any]:
        """Get backpressure status across all sources."""
        stats = self.get_all_buffer_stats()
        total_size = sum(s["size"] for s in stats.values())
        total_capacity = sum(s["max_size"] for s in stats.values())
        utilization = total_size / total_capacity if total_capacity > 0 else 0

        return {
            "utilization": utilization,
            "is_under_backpressure": utilization
            >= self.settings.sources[0].rate_limit.backpressure_threshold,
            "total_size": total_size,
            "total_capacity": total_capacity,
            "source_stats": stats,
        }

    def clear_all(self) -> dict[str, list[TelemetryEvent]]:
        """Clear all events from all sources."""
        with self._lock:
            return {name: source.clear() for name, source in self._sources.items()}


# Singleton instance
ingestion_layer: TelemetryIngestionLayer | None = None


def get_ingestion_layer() -> TelemetryIngestionLayer:
    """Get global ingestion layer instance."""
    global ingestion_layer
    if ingestion_layer is None:
        ingestion_layer = TelemetryIngestionLayer()
    return ingestion_layer
