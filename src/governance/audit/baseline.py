"""
Audit Snapshot and Retrieval Baseline Module.

ST-GOV-MINI-001: Audit Snapshot + Retrieval Baseline

This module provides baseline metrics capture for system governance,
including retrieval latency, memory hit rate, and deduplication ratio.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuditSnapshot:
    """
    Captures a point-in-time snapshot of system state for audit purposes.

    Attributes:
        timestamp: UTC timestamp when snapshot was captured
        component: Component identifier (e.g., "memory", "retrieval", "deduplication")
        metrics: Dictionary of metric name -> value
        metadata: Additional context about the snapshot
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    component: str = "system"
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str | None = None

    def __post_init__(self) -> None:
        """Generate snapshot ID if not provided."""
        if self.snapshot_id is None:
            self.snapshot_id = f"snapshot-{self.timestamp.strftime('%Y%m%d%H%M%S')}"

    def capture(
        self, component: str | None = None, **additional_metrics: Any
    ) -> "AuditSnapshot":
        """
        Capture current system state as a snapshot.

        Args:
            component: Optional component override
            **additional_metrics: Additional metrics to include in the snapshot

        Returns:
            Self for method chaining

        Example:
            >>> snapshot = AuditSnapshot().capture("memory", heap_size=1024, gc_count=5)
        """
        if component:
            self.component = component

        # Merge additional metrics
        self.metrics.update(additional_metrics)

        # Update timestamp to capture time
        self.timestamp = datetime.now(UTC)
        self.snapshot_id = f"{self.component}-{self.timestamp.strftime('%Y%m%d%H%M%S')}"

        logger.info(f"Captured audit snapshot: {self.snapshot_id}")
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary for serialization."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "component": self.component,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert snapshot to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditSnapshot":
        """Create snapshot from dictionary."""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class RetrievalBaseline:
    """
    Collects and manages retrieval baseline metrics for governance.

    Core metrics tracked:
    - retrieval_latency: Time to retrieve data from memory/cache
    - memory_hit_rate: Percentage of requests served from memory
    - deduplication_ratio: Ratio of unique items to total items processed

    Attributes:
        baseline_id: Unique identifier for this baseline
        created_at: When this baseline was created
        metrics: Dictionary of baseline metric values
        samples: Number of samples used to compute baseline
    """

    baseline_id: str = "default"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metrics: dict[str, float] = field(
        default_factory=lambda: {
            "retrieval_latency_ms": 0.0,
            "memory_hit_rate": 0.0,
            "deduplication_ratio": 0.0,
        }
    )
    samples: int = 0

    def get_metrics(self) -> dict[str, float]:
        """
        Get current baseline metrics.

        Returns:
            Dictionary with metric names and values:
            - retrieval_latency_ms: Average retrieval latency in milliseconds
            - memory_hit_rate: Hit rate as a percentage (0-100)
            - deduplication_ratio: Ratio of unique to total items (0-1)
        """
        return {
            "retrieval_latency_ms": self.metrics.get("retrieval_latency_ms", 0.0),
            "memory_hit_rate": self.metrics.get("memory_hit_rate", 0.0),
            "deduplication_ratio": self.metrics.get("deduplication_ratio", 0.0),
        }

    def update_metrics(
        self,
        retrieval_latency_ms: float | None = None,
        memory_hit_rate: float | None = None,
        deduplication_ratio: float | None = None,
    ) -> None:
        """
        Update baseline metrics with new values.

        Args:
            retrieval_latency_ms: New retrieval latency measurement
            memory_hit_rate: New memory hit rate measurement
            deduplication_ratio: New deduplication ratio measurement
        """
        if retrieval_latency_ms is not None:
            self.metrics["retrieval_latency_ms"] = retrieval_latency_ms
        if memory_hit_rate is not None:
            self.metrics["memory_hit_rate"] = max(0.0, min(100.0, memory_hit_rate))
        if deduplication_ratio is not None:
            self.metrics["deduplication_ratio"] = max(
                0.0, min(1.0, deduplication_ratio)
            )

        self.samples += 1
        logger.debug(f"Updated baseline metrics: {self.metrics}")

    def export_to_redis(self, redis_client: Any = None) -> dict[str, str]:
        """
        Export baseline metrics to Redis for persistence.

        Redis Keys:
        - governance:audit:baseline:current - Current baseline metrics
        - governance:audit:snapshot:<timestamp> - Historical snapshots

        Args:
            redis_client: Optional Redis client (uses default if None)

        Returns:
            Dictionary of Redis keys that were written

        Note:
            This is a skeleton implementation. Full Redis integration
            requires the redis_state tools or a Redis client instance.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

        # Define Redis keys
        baseline_key = "governance:audit:baseline:current"
        snapshot_key = f"governance:audit:snapshot:{timestamp}"

        # Prepare data for storage
        baseline_data = {
            "baseline_id": self.baseline_id,
            "created_at": self.created_at.isoformat(),
            "metrics": json.dumps(self.metrics),
            "samples": self.samples,
        }

        snapshot_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": json.dumps(self.metrics),
        }

        # TODO: Implement actual Redis storage when client is available
        # For now, return the keys and data that would be written
        logger.info(f"Prepared Redis export for baseline: {baseline_key}")
        logger.info(f"Prepared Redis export for snapshot: {snapshot_key}")

        return {
            "baseline_key": baseline_key,
            "snapshot_key": snapshot_key,
            "baseline_data": json.dumps(baseline_data),
            "snapshot_data": json.dumps(snapshot_data),
        }

    def create_snapshot(self) -> AuditSnapshot:
        """
        Create an AuditSnapshot from current baseline metrics.

        Returns:
            AuditSnapshot containing current baseline metrics
        """
        return AuditSnapshot(
            component="retrieval_baseline",
            metrics=self.get_metrics(),
            metadata={
                "baseline_id": self.baseline_id,
                "samples": self.samples,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert baseline to dictionary for serialization."""
        return {
            "baseline_id": self.baseline_id,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "samples": self.samples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RetrievalBaseline":
        """Create baseline from dictionary."""
        if isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


# Module-level constants for metric thresholds
METRIC_THRESHOLDS = {
    "retrieval_latency_ms": {
        "excellent": 10.0,  # < 10ms is excellent
        "good": 50.0,  # < 50ms is good
        "acceptable": 100.0,  # < 100ms is acceptable
    },
    "memory_hit_rate": {
        "excellent": 95.0,  # > 95% is excellent
        "good": 80.0,  # > 80% is good
        "acceptable": 60.0,  # > 60% is acceptable
    },
    "deduplication_ratio": {
        "excellent": 0.9,  # > 0.9 is excellent
        "good": 0.7,  # > 0.7 is good
        "acceptable": 0.5,  # > 0.5 is acceptable
    },
}


def evaluate_metric(metric_name: str, value: float) -> str:
    """
    Evaluate a metric value against defined thresholds.

    Args:
        metric_name: Name of the metric to evaluate
        value: Current metric value

    Returns:
        Rating string: "excellent", "good", "acceptable", or "needs_improvement"
    """
    if metric_name not in METRIC_THRESHOLDS:
        return "unknown"

    thresholds = METRIC_THRESHOLDS[metric_name]

    # For latency, lower is better
    if metric_name == "retrieval_latency_ms":
        if value <= thresholds["excellent"]:
            return "excellent"
        elif value <= thresholds["good"]:
            return "good"
        elif value <= thresholds["acceptable"]:
            return "acceptable"
        return "needs_improvement"

    # For rates/ratios, higher is better
    if value >= thresholds["excellent"]:
        return "excellent"
    elif value >= thresholds["good"]:
        return "good"
    elif value >= thresholds["acceptable"]:
        return "acceptable"
    return "needs_improvement"
