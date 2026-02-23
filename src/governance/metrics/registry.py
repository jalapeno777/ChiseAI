"""
Metrics Registry for Governance Features.

Central registry for all governance metrics exporters.
Provides unified collection and export capabilities.

Story: ST-GOV-004
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    ExportResult,
    MetricPoint,
)

logger = logging.getLogger(__name__)


@dataclass
class RegistryStats:
    """Statistics for the metrics registry."""

    exporters_registered: int = 0
    """Number of exporters currently registered"""

    total_collections: int = 0
    """Total collections across all exporters"""

    total_points_exported: int = 0
    """Total metric points exported"""

    last_collection_time: datetime | None = None
    """Time of last successful collection"""

    errors_count: int = 0
    """Total errors encountered"""


class MetricsRegistry:
    """
    Central registry for governance metrics exporters.

    Manages registration, collection, and export of metrics from
    all governance features in a unified manner.

    Example:
        registry = MetricsRegistry()
        registry.register(sentinel_exporter)
        registry.register(memory_exporter)

        # Collect from all exporters
        all_points = registry.collect_all()

        # Export to InfluxDB
        results = registry.export_all()
    """

    _instance = None
    _lock = Lock()

    def __new__(cls) -> "MetricsRegistry":
        """Singleton pattern for global registry access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the metrics registry."""
        if self._initialized:
            return

        self._exporters: dict[str, BaseMetricsExporter] = {}
        self._stats = RegistryStats()
        self._influx_client: Any | None = None
        self._initialized = True

        logger.info("MetricsRegistry initialized")

    def set_influx_client(self, client: Any) -> None:
        """
        Set the InfluxDB client for all exporters.

        Args:
            client: InfluxDB client instance
        """
        self._influx_client = client
        logger.info("InfluxDB client set for metrics registry")

    def register(self, exporter: BaseMetricsExporter) -> None:
        """
        Register a metrics exporter.

        Args:
            exporter: Exporter instance to register
        """
        if exporter.feature_name in self._exporters:
            logger.warning(f"Overwriting existing exporter for {exporter.feature_name}")

        self._exporters[exporter.feature_name] = exporter
        self._stats.exporters_registered = len(self._exporters)

        logger.info(f"Registered exporter: {exporter.feature_name}")

    def unregister(self, feature_name: str) -> bool:
        """
        Unregister a metrics exporter.

        Args:
            feature_name: Name of feature to unregister

        Returns:
            True if exporter was removed, False if not found
        """
        if feature_name in self._exporters:
            del self._exporters[feature_name]
            self._stats.exporters_registered = len(self._exporters)
            logger.info(f"Unregistered exporter: {feature_name}")
            return True
        return False

    def get_exporter(self, feature_name: str) -> BaseMetricsExporter | None:
        """
        Get a registered exporter by feature name.

        Args:
            feature_name: Name of the feature

        Returns:
            Exporter instance or None if not found
        """
        return self._exporters.get(feature_name)

    def collect_all(self) -> list[MetricPoint]:
        """
        Collect metrics from all registered exporters.

        Returns:
            Combined list of all metric points
        """
        all_points: list[MetricPoint] = []

        for feature_name, exporter in self._exporters.items():
            try:
                points = exporter.collect()
                all_points.extend(points)
                self._stats.total_collections += 1
            except Exception as e:
                logger.error(f"Failed to collect from {feature_name}: {e}")
                self._stats.errors_count += 1

        self._stats.last_collection_time = datetime.now(UTC)
        return all_points

    def export_all(self, bucket: str = "governance") -> dict[str, ExportResult]:
        """
        Export metrics from all registered exporters.

        Args:
            bucket: InfluxDB bucket to write to

        Returns:
            Dict mapping feature names to their export results
        """
        results: dict[str, ExportResult] = {}

        for feature_name, exporter in self._exporters.items():
            try:
                result = exporter.export(bucket=bucket)
                results[feature_name] = result
                self._stats.total_points_exported += result.points_exported

                if not result.success:
                    self._stats.errors_count += 1

            except Exception as e:
                results[feature_name] = ExportResult(success=False, errors=[str(e)])
                self._stats.errors_count += 1
                logger.error(f"Failed to export {feature_name}: {e}")

        return results

    def get_stats(self) -> RegistryStats:
        """
        Get registry statistics.

        Returns:
            Current RegistryStats
        """
        return self._stats

    def get_feature_names(self) -> list[str]:
        """
        Get names of all registered features.

        Returns:
            List of feature names
        """
        return list(self._exporters.keys())

    def is_healthy(self) -> bool:
        """
        Check if the registry is healthy.

        Returns:
            True if at least one exporter is healthy
        """
        return any(exp.is_healthy() for exp in self._exporters.values())

    def clear(self) -> None:
        """Clear all registered exporters (useful for testing)."""
        self._exporters.clear()
        self._stats = RegistryStats()
        logger.info("Metrics registry cleared")


# Global registry instance
def get_registry() -> MetricsRegistry:
    """
    Get the global metrics registry.

    Returns:
        Singleton MetricsRegistry instance
    """
    return MetricsRegistry()
