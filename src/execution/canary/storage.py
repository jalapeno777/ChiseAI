"""Storage module for canary deployment results.

Provides persistence for canary metrics and results to support
Grafana dashboard visibility and historical analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from execution.canary.models import (
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    GateCheck,
)
from execution.canary.monitor import MonitoringCheck


@dataclass
class CanaryRecord:
    """Record of a canary deployment for storage.

    Attributes:
        canary_id: Unique canary identifier
        strategy_id: Strategy being tested
        champion_strategy_id: Champion strategy for rollback
        status: Current canary status
        allocation_pct: Portfolio allocation percentage
        start_time: Start timestamp
        end_time: End timestamp
        metrics: Canary metrics snapshot
        last_updated: Last update timestamp
        metadata: Additional metadata
    """

    canary_id: str
    strategy_id: str
    champion_strategy_id: str | None
    status: str
    allocation_pct: float
    start_time: int
    end_time: int
    metrics: dict[str, Any]
    last_updated: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_deployment(cls, deployment: CanaryDeployment) -> CanaryRecord:
        """Create record from deployment."""
        return cls(
            canary_id=deployment.canary_id,
            strategy_id=deployment.strategy_id,
            champion_strategy_id=deployment.champion_strategy_id,
            status=deployment.status.value,
            allocation_pct=deployment.allocation_pct,
            start_time=deployment.start_time,
            end_time=deployment.end_time,
            metrics=deployment.metrics.to_dict(),
            last_updated=int(datetime.now().timestamp()),
            metadata=deployment.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "canary_id": self.canary_id,
            "strategy_id": self.strategy_id,
            "champion_strategy_id": self.champion_strategy_id,
            "status": self.status,
            "allocation_pct": self.allocation_pct,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metrics": self.metrics,
            "last_updated": self.last_updated,
            "metadata": self.metadata,
        }


class CanaryStorage(ABC):
    """Abstract base class for canary result storage."""

    @abstractmethod
    def save_deployment(self, deployment: CanaryDeployment) -> None:
        """Save a canary deployment."""
        pass

    @abstractmethod
    def get_deployment(self, canary_id: str) -> CanaryRecord | None:
        """Get a canary deployment by ID."""
        pass

    @abstractmethod
    def list_deployments(
        self,
        strategy_id: str | None = None,
        status: CanaryStatus | None = None,
        limit: int | None = None,
    ) -> list[CanaryRecord]:
        """List canary deployments with optional filters."""
        pass

    @abstractmethod
    def save_monitoring_check(self, check: MonitoringCheck) -> None:
        """Save a monitoring check result."""
        pass

    @abstractmethod
    def get_monitoring_history(
        self,
        canary_id: str,
        limit: int | None = None,
    ) -> list[MonitoringCheck]:
        """Get monitoring check history for a canary."""
        pass


class InMemoryCanaryStorage(CanaryStorage):
    """In-memory storage implementation for testing and development."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._deployments: dict[str, CanaryRecord] = {}
        self._monitoring_checks: list[MonitoringCheck] = []

    def save_deployment(self, deployment: CanaryDeployment) -> None:
        """Save a canary deployment."""
        record = CanaryRecord.from_deployment(deployment)
        self._deployments[deployment.canary_id] = record

    def get_deployment(self, canary_id: str) -> CanaryRecord | None:
        """Get a canary deployment by ID."""
        return self._deployments.get(canary_id)

    def list_deployments(
        self,
        strategy_id: str | None = None,
        status: CanaryStatus | None = None,
        limit: int | None = None,
    ) -> list[CanaryRecord]:
        """List canary deployments with optional filters."""
        records = list(self._deployments.values())

        if strategy_id:
            records = [r for r in records if r.strategy_id == strategy_id]

        if status:
            records = [r for r in records if r.status == status.value]

        # Sort by start time descending
        records = sorted(records, key=lambda r: r.start_time, reverse=True)

        if limit:
            records = records[:limit]

        return records

    def save_monitoring_check(self, check: MonitoringCheck) -> None:
        """Save a monitoring check result."""
        self._monitoring_checks.append(check)

    def get_monitoring_history(
        self,
        canary_id: str,
        limit: int | None = None,
    ) -> list[MonitoringCheck]:
        """Get monitoring check history for a canary."""
        checks = [c for c in self._monitoring_checks if c.canary_id == canary_id]

        # Sort by timestamp descending
        checks = sorted(checks, key=lambda c: c.timestamp, reverse=True)

        if limit:
            checks = checks[:limit]

        return checks

    def clear(self) -> None:
        """Clear all stored data."""
        self._deployments.clear()
        self._monitoring_checks.clear()


class CanaryStorageWithPersistence(CanaryStorage):
    """Storage implementation with persistence to InfluxDB.

    This is a placeholder for the full InfluxDB implementation.
    The actual implementation would write to InfluxDB for Grafana visibility.
    """

    def __init__(self, influxdb_client: Any | None = None) -> None:
        """Initialize storage.

        Args:
            influxdb_client: InfluxDB client instance
        """
        self._influxdb = influxdb_client
        self._memory = InMemoryCanaryStorage()

    def save_deployment(self, deployment: CanaryDeployment) -> None:
        """Save a canary deployment to memory and InfluxDB."""
        # Always save to memory
        self._memory.save_deployment(deployment)

        # TODO: Persist to InfluxDB when client is available
        # This will enable Grafana dashboard visibility
        if self._influxdb:
            pass  # InfluxDB persistence implementation

    def get_deployment(self, canary_id: str) -> CanaryRecord | None:
        """Get a canary deployment by ID."""
        return self._memory.get_deployment(canary_id)

    def list_deployments(
        self,
        strategy_id: str | None = None,
        status: CanaryStatus | None = None,
        limit: int | None = None,
    ) -> list[CanaryRecord]:
        """List canary deployments."""
        return self._memory.list_deployments(strategy_id, status, limit)

    def save_monitoring_check(self, check: MonitoringCheck) -> None:
        """Save a monitoring check result."""
        self._memory.save_monitoring_check(check)

        # TODO: Persist to InfluxDB when client is available
        if self._influxdb:
            pass  # InfluxDB persistence implementation

    def get_monitoring_history(
        self,
        canary_id: str,
        limit: int | None = None,
    ) -> list[MonitoringCheck]:
        """Get monitoring check history."""
        return self._memory.get_monitoring_history(canary_id, limit)


def create_canary_storage(
    influxdb_client: Any | None = None,
) -> CanaryStorage:
    """Create a canary storage instance.

    Args:
        influxdb_client: Optional InfluxDB client for persistence

    Returns:
        CanaryStorage instance
    """
    if influxdb_client:
        return CanaryStorageWithPersistence(influxdb_client)
    return InMemoryCanaryStorage()
