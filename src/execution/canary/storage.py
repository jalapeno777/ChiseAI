"""Storage module for canary deployment results.

Provides persistence for canary metrics and results to support
Grafana dashboard visibility and historical analysis.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from execution.canary.models import (
    CanaryDeployment,
    CanaryStatus,
)
from execution.canary.monitor import MonitoringCheck

logger = logging.getLogger(__name__)


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

    Writes canary deployment records and monitoring checks to InfluxDB
    for Grafana dashboard visibility, with in-memory cache for fast reads.
    Uses the ``chiseai`` bucket (not ``data_quality``).
    """

    _BUCKET = "chiseai"
    _ORG = "chiseai"

    def __init__(self, influxdb_client: Any | None = None) -> None:
        """Initialize storage.

        Args:
            influxdb_client: An ``influxdb_client.InfluxDBClient`` instance.
        """
        self._influxdb = influxdb_client
        self._memory = InMemoryCanaryStorage()
        self._write_api: Any | None = None

    def _get_write_api(self) -> Any:
        """Lazily create a synchronous write API from the InfluxDB client."""
        if self._influxdb is None:
            return None
        if self._write_api is None:
            from influxdb_client.client.write_api import SYNCHRONOUS

            self._write_api = self._influxdb.write_api(write_options=SYNCHRONOUS)
        return self._write_api

    def save_deployment(self, deployment: CanaryDeployment) -> None:
        """Save a canary deployment to memory and InfluxDB."""
        # Always save to memory
        self._memory.save_deployment(deployment)

        if self._influxdb:
            try:
                import os

                from influxdb_client import Point

                record = CanaryRecord.from_deployment(deployment)

                # Extract metrics for individual fields (for Grafana dashboard)
                metrics = record.metrics
                max_drawdown_pct = metrics.get("max_drawdown_pct", 0.0)
                win_rate_pct = metrics.get("win_rate_pct", 0.0)
                duration_days = (
                    (record.end_time - record.start_time) / (24 * 60 * 60)
                    if record.end_time > record.start_time
                    else 0.0
                )

                point = (
                    Point("canary_deployment")
                    .tag("canary_id", record.canary_id)
                    .tag("strategy_id", record.strategy_id)
                    .tag("status", record.status)
                    .tag("environment", os.getenv("ENVIRONMENT", "paper"))
                    .field("allocation_pct", record.allocation_pct)
                    .field("start_time", record.start_time)
                    .field("end_time", record.end_time)
                    .field("max_drawdown_pct", max_drawdown_pct)
                    .field("win_rate_pct", win_rate_pct)
                    .field("duration_days", duration_days)
                    .field("metrics_json", json.dumps(record.metrics))
                    .field("metadata_json", json.dumps(record.metadata))
                )
                if record.champion_strategy_id:
                    point = point.tag(
                        "champion_strategy_id", record.champion_strategy_id
                    )

                self._get_write_api().write(
                    bucket=self._BUCKET, org=self._ORG, record=point
                )
                logger.info(
                    "Persisted canary deployment %s to InfluxDB", record.canary_id
                )
            except ImportError:
                logger.warning(
                    "influxdb-client not installed; skipping InfluxDB persistence"
                )
            except Exception:
                logger.exception(
                    "Failed to persist canary deployment %s to InfluxDB",
                    deployment.canary_id,
                )

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

        if self._influxdb:
            try:
                import os

                from influxdb_client import Point

                point = (
                    Point("canary_monitoring_check")
                    .tag("canary_id", check.canary_id)
                    .tag("status", check.status.value)
                    .tag("action_taken", check.action_taken)
                    .tag("environment", os.getenv("ENVIRONMENT", "paper"))
                    .field("message", check.message)
                    .field("timestamp_epoch", check.timestamp)
                    .field(
                        "gate_checks_json",
                        json.dumps([gc.to_dict() for gc in check.gate_checks]),
                    )
                )

                self._get_write_api().write(
                    bucket=self._BUCKET, org=self._ORG, record=point
                )

                # Also write individual gate check records for Grafana dashboard
                for gate_check in check.gate_checks:
                    gate_point = (
                        Point("canary_gate_check")
                        .tag("canary_id", check.canary_id)
                        .tag("gate_name", gate_check.gate_name)
                        .tag("result", gate_check.result.value)
                        .tag("environment", os.getenv("ENVIRONMENT", "paper"))
                        .field("actual_value", gate_check.actual_value)
                        .field("threshold_value", gate_check.threshold_value)
                        .field("message", gate_check.message)
                    )
                    self._get_write_api().write(
                        bucket=self._BUCKET, org=self._ORG, record=gate_point
                    )

                logger.info(
                    "Persisted monitoring check for canary %s to InfluxDB",
                    check.canary_id,
                )
            except ImportError:
                logger.warning(
                    "influxdb-client not installed; skipping InfluxDB persistence"
                )
            except Exception:
                logger.exception(
                    "Failed to persist monitoring check for canary %s to InfluxDB",
                    check.canary_id,
                )

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
