"""Metrics collection for Model Registry.

Provides comprehensive metrics collection for monitoring registry operations,
performance, and health. Supports both Prometheus and custom collectors.

Example:
    # Set up Prometheus metrics
    collector = PrometheusMetricsCollector()
    set_metrics_collector(collector)

    # Or use Redis-backed metrics
    collector = RedisMetricsCollector(redis_url="redis://localhost:6379")
    set_metrics_collector(collector)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_metric_name(source_name: str, target_format: str) -> str:
    """Sanitize a metric name for the target format.

    Handles naming conflicts between Prometheus and InfluxDB:
    - Prometheus: underscores allowed, dots NOT allowed, hyphens NOT allowed,
      no uppercase. Labels for dimensions.
    - InfluxDB: underscores allowed, dots allowed, hyphens discouraged but
      allowed. Tags for dimensions.

    Args:
        source_name: Original metric name (e.g. 'model.accuracy.score')
        target_format: One of 'prometheus' or 'influxdb'

    Returns:
        Sanitized metric name compatible with the target format

    Raises:
        ValueError: If target_format is not 'prometheus' or 'influxdb'

    Example:
        >>> sanitize_metric_name('model.accuracy.score', 'prometheus')
        'model_accuracy_score'
        >>> sanitize_metric_name('model_accuracy_score', 'influxdb')
        'model_accuracy_score'
    """
    if target_format not in ("prometheus", "influxdb"):
        raise ValueError(
            f"target_format must be 'prometheus' or 'influxdb', got '{target_format}'"
        )

    name = source_name

    if target_format == "prometheus":
        # Replace dots and hyphens with underscores (dots/hyphens invalid in Prometheus)
        name = name.replace(".", "_").replace("-", "_")
        # Lowercase (Prometheus names must be lowercase)
        name = name.lower()
        # Collapse consecutive underscores
        while "__" in name:
            name = name.replace("__", "_")
        # Strip leading/trailing underscores
        name = name.strip("_")
        # Ensure name starts with a letter (Prometheus requirement)
        if name and not name[0].isalpha():
            name = f"metric_{name}"
    elif target_format == "influxdb":
        # InfluxDB is more permissive - mainly ensure no spaces
        name = name.replace(" ", "_")
        # Replace hyphens with underscores for consistency
        name = name.replace("-", "_")
        # Lowercase for consistency (not strictly required by InfluxDB)
        name = name.lower()

    return name


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the current metrics collector singleton.

    Returns:
        Active metrics collector or NullMetricsCollector if none set
    """
    global _metrics_collector
    return _metrics_collector or NullMetricsCollector()


def set_metrics_collector(collector: MetricsCollector) -> None:
    """Set the global metrics collector singleton.

    Args:
        collector: Metrics collector to use globally
    """
    global _metrics_collector
    _metrics_collector = collector
    logger.info(f"Set metrics collector: {collector.__class__.__name__}")


@dataclass
class RegistryMetrics:
    """Container for registry metrics data.

    Attributes:
        models_registered_total: Total models registered by time period
        model_retrieval_latency_seconds: Latency histogram for model retrieval
        cache_hits_total: Number of cache hits
        cache_misses_total: Number of cache misses
        storage_usage_bytes: Total storage used in bytes
        models_count: Total number of models
        rollback_operations_total: Number of rollback operations
        version_comparisons_total: Number of version comparison operations
        failed_operations_total: Number of failed operations by type
        active_models_by_status: Count of active models by status
    """

    models_registered_total: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    model_retrieval_latency_seconds: list[float] = field(default_factory=list)
    cache_hits_total: int = 0
    cache_misses_total: int = 0
    storage_usage_bytes: int = 0
    models_count: int = 0
    rollback_operations_total: int = 0
    version_comparisons_total: int = 0
    failed_operations_total: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    active_models_by_status: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary format.

        Returns:
            Dictionary representation of metrics
        """
        # Calculate latency percentiles
        latencies = sorted(self.model_retrieval_latency_seconds)
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        p95_index = int(len(latencies) * 0.95)
        p95 = (
            latencies[p95_index]
            if p95_index < len(latencies)
            else (latencies[-1] if latencies else 0.0)
        )
        p99_index = int(len(latencies) * 0.99)
        p99 = (
            latencies[p99_index]
            if p99_index < len(latencies)
            else (latencies[-1] if latencies else 0.0)
        )

        # Calculate cache hit rate
        total_cache_ops = self.cache_hits_total + self.cache_misses_total
        cache_hit_rate = (
            (self.cache_hits_total / total_cache_ops * 100)
            if total_cache_ops > 0
            else 0.0
        )

        return {
            "models_registered_total": dict(self.models_registered_total),
            "model_retrieval_latency": {
                "p50": p50,
                "p95": p95,
                "p99": p99,
                "count": len(latencies),
            },
            "cache": {
                "hits": self.cache_hits_total,
                "misses": self.cache_misses_total,
                "hit_rate_percent": cache_hit_rate,
            },
            "storage": {
                "usage_bytes": self.storage_usage_bytes,
                "models_count": self.models_count,
            },
            "operations": {
                "rollback_total": self.rollback_operations_total,
                "version_comparisons_total": self.version_comparisons_total,
                "failed_total": dict(self.failed_operations_total),
            },
            "active_models_by_status": dict(self.active_models_by_status),
        }


class MetricsCollector(ABC):
    """Abstract base class for metrics collection.

    Implementations should handle metric storage, aggregation, and export
    for different backends (Prometheus, Redis, InfluxDB, etc.).
    """

    @abstractmethod
    def record_model_registered(self, model_name: str, version: str) -> None:
        """Record a model registration event.

        Args:
            model_name: Name of the registered model
            version: Version string
        """
        pass

    @abstractmethod
    def record_model_retrieval(
        self, model_name: str, version: str, latency_seconds: float, cache_hit: bool
    ) -> None:
        """Record a model retrieval operation.

        Args:
            model_name: Name of the retrieved model
            version: Version string
            latency_seconds: Time taken to retrieve
            cache_hit: Whether retrieval was from cache
        """
        pass

    @abstractmethod
    def record_rollback(
        self, model_name: str, from_version: str, to_version: str
    ) -> None:
        """Record a rollback operation.

        Args:
            model_name: Name of the model
            from_version: Version rolling back from
            to_version: Version rolling back to
        """
        pass

    @abstractmethod
    def record_version_comparison(
        self, model_name: str, version1: str, version2: str
    ) -> None:
        """Record a version comparison operation.

        Args:
            model_name: Name of the model
            version1: First version compared
            version2: Second version compared
        """
        pass

    @abstractmethod
    def record_failed_operation(
        self, operation: str, model_name: str, error_type: str, error_message: str
    ) -> None:
        """Record a failed operation.

        Args:
            operation: Type of operation (register, retrieve, rollback, etc.)
            model_name: Name of the model
            error_type: Exception type
            error_message: Error message
        """
        pass

    @abstractmethod
    def update_storage_metrics(self, usage_bytes: int, models_count: int) -> None:
        """Update storage usage metrics.

        Args:
            usage_bytes: Total storage used
            models_count: Total number of models
        """
        pass

    @abstractmethod
    def update_model_status(self, model_name: str, version: str, status: str) -> None:
        """Update model status tracking.

        Args:
            model_name: Name of the model
            version: Version string
            status: Status (active, inactive, deprecated)
        """
        pass

    @abstractmethod
    def get_metrics(self) -> RegistryMetrics:
        """Get current metrics snapshot.

        Returns:
            Current metrics data
        """
        pass

    @abstractmethod
    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        pass


class NullMetricsCollector(MetricsCollector):
    """No-op metrics collector that discards all metrics.

    Used as default when no metrics collection is configured.
    """

    def record_model_registered(self, model_name: str, version: str) -> None:
        """No-op implementation."""
        pass

    def record_model_retrieval(
        self, model_name: str, version: str, latency_seconds: float, cache_hit: bool
    ) -> None:
        """No-op implementation."""
        pass

    def record_rollback(
        self, model_name: str, from_version: str, to_version: str
    ) -> None:
        """No-op implementation."""
        pass

    def record_version_comparison(
        self, model_name: str, version1: str, version2: str
    ) -> None:
        """No-op implementation."""
        pass

    def record_failed_operation(
        self, operation: str, model_name: str, error_type: str, error_message: str
    ) -> None:
        """No-op implementation."""
        pass

    def update_storage_metrics(self, usage_bytes: int, models_count: int) -> None:
        """No-op implementation."""
        pass

    def update_model_status(self, model_name: str, version: str, status: str) -> None:
        """No-op implementation."""
        pass

    def get_metrics(self) -> RegistryMetrics:
        """Return empty metrics."""
        return RegistryMetrics()

    def reset_metrics(self) -> None:
        """No-op implementation."""
        pass


class PrometheusMetricsCollector(MetricsCollector):
    """Prometheus-compatible metrics collector.

    Exposes metrics in Prometheus format for scraping by Prometheus server.
    Uses prometheus_client library if available, falls back to simple tracking.
    """

    def __init__(self, namespace: str = "chiseai") -> None:
        """Initialize Prometheus metrics collector.

        Args:
            namespace: Metrics namespace prefix
        """
        self.namespace = namespace
        self._metrics = RegistryMetrics()
        self._start_time = time.time()

        # Try to import prometheus_client
        self._prometheus_available = False
        try:
            from prometheus_client import (  # noqa: F401
                CollectorRegistry,
                Counter,
                Gauge,
                Histogram,
            )

            self._prometheus_available = True
            self._setup_prometheus_metrics()
            logger.info("Prometheus metrics initialized with prometheus_client")
        except ImportError:
            logger.warning(
                "prometheus_client not available, using simple metrics tracking. "
                "Install with: pip install prometheus_client"
            )

    def _setup_prometheus_metrics(self) -> None:
        """Set up Prometheus metric objects."""
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

        # Create a unique registry for this collector instance to avoid
        # "Duplicated timeseries in CollectorRegistry" errors in tests
        self._registry = CollectorRegistry()

        # Model registration counter
        self._models_registered = Counter(
            f"{self.namespace}_model_registrations_total",
            "Total number of model registrations",
            ["model_name"],
            registry=self._registry,
        )

        # Retrieval latency histogram
        self._retrieval_latency = Histogram(
            f"{self.namespace}_model_retrieval_latency_seconds",
            "Model retrieval latency in seconds",
            ["model_name"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self._registry,
        )

        # Cache metrics
        self._cache_hits = Counter(
            f"{self.namespace}_cache_hits_total",
            "Total number of cache hits",
            registry=self._registry,
        )
        self._cache_misses = Counter(
            f"{self.namespace}_cache_misses_total",
            "Total number of cache misses",
            registry=self._registry,
        )

        # Storage metrics
        self._storage_bytes = Gauge(
            f"{self.namespace}_storage_usage_bytes",
            "Total storage usage in bytes",
            registry=self._registry,
        )
        self._models_count = Gauge(
            f"{self.namespace}_models_total",
            "Total number of models",
            registry=self._registry,
        )

        # Operation counters
        self._rollbacks = Counter(
            f"{self.namespace}_rollback_operations_total",
            "Total number of rollback operations",
            ["model_name"],
            registry=self._registry,
        )
        self._version_comparisons = Counter(
            f"{self.namespace}_version_comparisons_total",
            "Total number of version comparison operations",
            registry=self._registry,
        )
        self._failed_ops = Counter(
            f"{self.namespace}_failed_operations_total",
            "Total number of failed operations",
            ["operation", "error_type"],
            registry=self._registry,
        )

        # Model status gauge
        self._models_by_status = Gauge(
            f"{self.namespace}_models_by_status",
            "Number of models by status",
            ["status"],
            registry=self._registry,
        )

    def record_model_registered(self, model_name: str, version: str) -> None:
        """Record model registration."""
        self._metrics.models_registered_total[datetime.now(UTC).date().isoformat()] += 1

        if self._prometheus_available:
            self._models_registered.labels(model_name=model_name).inc()

        logger.debug(f"Recorded model registration: {model_name}@{version}")

    def record_model_retrieval(
        self, model_name: str, version: str, latency_seconds: float, cache_hit: bool
    ) -> None:
        """Record model retrieval."""
        self._metrics.model_retrieval_latency_seconds.append(latency_seconds)

        if cache_hit:
            self._metrics.cache_hits_total += 1
        else:
            self._metrics.cache_misses_total += 1

        if self._prometheus_available:
            self._retrieval_latency.labels(model_name=model_name).observe(
                latency_seconds
            )
            if cache_hit:
                self._cache_hits.inc()
            else:
                self._cache_misses.inc()

        logger.debug(
            f"Recorded model retrieval: {model_name}@{version} "
            f"(latency={latency_seconds:.3f}s, cache_hit={cache_hit})"
        )

    def record_rollback(
        self, model_name: str, from_version: str, to_version: str
    ) -> None:
        """Record rollback operation."""
        self._metrics.rollback_operations_total += 1

        if self._prometheus_available:
            self._rollbacks.labels(model_name=model_name).inc()

        logger.info(f"Recorded rollback: {model_name} {from_version} -> {to_version}")

    def record_version_comparison(
        self, model_name: str, version1: str, version2: str
    ) -> None:
        """Record version comparison."""
        self._metrics.version_comparisons_total += 1

        if self._prometheus_available:
            self._version_comparisons.inc()

        logger.debug(
            f"Recorded version comparison: {model_name} {version1} vs {version2}"
        )

    def record_failed_operation(
        self, operation: str, model_name: str, error_type: str, error_message: str
    ) -> None:
        """Record failed operation."""
        self._metrics.failed_operations_total[f"{operation}:{error_type}"] += 1

        if self._prometheus_available:
            self._failed_ops.labels(operation=operation, error_type=error_type).inc()

        logger.warning(
            f"Recorded failed operation: {operation} on {model_name} "
            f"({error_type}: {error_message})"
        )

    def update_storage_metrics(self, usage_bytes: int, models_count: int) -> None:
        """Update storage metrics."""
        self._metrics.storage_usage_bytes = usage_bytes
        self._metrics.models_count = models_count

        if self._prometheus_available:
            self._storage_bytes.set(usage_bytes)
            self._models_count.set(models_count)

        logger.debug(
            f"Updated storage metrics: {usage_bytes} bytes, {models_count} models"
        )

    def update_model_status(self, model_name: str, version: str, status: str) -> None:
        """Update model status."""
        # This is more complex as we need to track status changes
        # For simplicity, just increment the count for the new status
        self._metrics.active_models_by_status[status] += 1

        if self._prometheus_available:
            self._models_by_status.labels(status=status).inc()

        logger.debug(f"Updated model status: {model_name}@{version} -> {status}")

    def get_metrics(self) -> RegistryMetrics:
        """Get current metrics snapshot."""
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self._metrics = RegistryMetrics()
        logger.info("Metrics reset")

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        if self._prometheus_available:
            from prometheus_client import generate_latest

            return generate_latest(self._registry).decode("utf-8")
        else:
            # Fallback to simple text format
            metrics = self._metrics.to_dict()
            lines = []

            lines.append(f"# HELP {self.namespace}_uptime_seconds Total uptime")
            lines.append(f"# TYPE {self.namespace}_uptime_seconds gauge")
            lines.append(
                f"{self.namespace}_uptime_seconds {time.time() - self._start_time}"
            )

            lines.append(
                f"\n# HELP {self.namespace}_models_registered_total Total models registered"
            )
            lines.append(f"# TYPE {self.namespace}_models_registered_total counter")
            for date, count in metrics["models_registered_total"].items():
                lines.append(
                    f'{self.namespace}_models_registered_total{{date="{date}"}} {count}'
                )

            lines.append(
                f"\n# HELP {self.namespace}_cache_hit_rate_percent Cache hit rate"
            )
            lines.append(f"# TYPE {self.namespace}_cache_hit_rate_percent gauge")
            lines.append(
                f"{self.namespace}_cache_hit_rate_percent {metrics['cache']['hit_rate_percent']}"
            )

            lines.append(f"\n# HELP {self.namespace}_storage_usage_bytes Storage usage")
            lines.append(f"# TYPE {self.namespace}_storage_usage_bytes gauge")
            lines.append(
                f"{self.namespace}_storage_usage_bytes {metrics['storage']['usage_bytes']}"
            )

            return "\n".join(lines) + "\n"
