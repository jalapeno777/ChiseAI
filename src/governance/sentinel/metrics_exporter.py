"""
Sentinel Metrics Exporter for ChiseAI Governance.

Exports metrics related to task validation,
approval workflows, and decomposition enforcement.

Story: ST-GOV-004
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
    MetricType,
)

logger = logging.getLogger(__name__)

# Redis keys for sentinel metrics
SENTINEL_PREFIX = "chise:governance:sentinel"
TASKS_VALIDATED_KEY = f"{SENTINEL_PREFIX}:tasks_validated"
TASKS_BLOCKED_KEY = f"{SENTINEL_PREFIX}:tasks_blocked"
PENDING_APPROVALS_KEY = f"{SENTINEL_PREFIX}:pending_approvals"


class SentinelMetricsExporter(BaseMetricsExporter):
    """
    Metrics exporter for the Task Sentinel governance feature.

    Collects and exports:
    - Tasks validated (approved vs blocked)
    - Pending approval count
    - Average approval time
    - Feature flag state
    - Decomposition recommendations

    Example:
        exporter = SentinelMetricsExporter(redis_client=redis)
        points = exporter.collect()
        # Returns metrics about task validation
    """

    def __init__(
        self,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the sentinel metrics exporter.

        Args:
            influx_client: Optional InfluxDB client
            redis_client: Optional Redis client for reading metrics
        """
        super().__init__(
            feature_name="sentinel",
            influx_client=influx_client,
            redis_client=redis_client,
        )

        # In-memory counters
        self._tasks_validated = 0
        self._tasks_blocked = 0
        self._tasks_approved = 0
        self._approval_times: list[float] = []

    def collect(self) -> list[MetricPoint]:
        """
        Collect sentinel-related metrics.

        Returns:
            List of MetricPoint objects with sentinel metrics
        """
        points: list[MetricPoint] = []
        now = datetime.now(UTC)

        # 1. Tasks validated total
        tasks_validated = self._get_tasks_validated()
        points.append(
            MetricPoint(
                name="governance.sentinel.tasks.validated",
                value=float(tasks_validated),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "sentinel", "status": "total"},
            )
        )

        # 2. Tasks approved
        tasks_approved = self._get_tasks_approved()
        points.append(
            MetricPoint(
                name="governance.sentinel.tasks.approved",
                value=float(tasks_approved),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "sentinel", "status": "approved"},
            )
        )

        # 3. Tasks blocked (>5 SP)
        tasks_blocked = self._get_tasks_blocked()
        points.append(
            MetricPoint(
                name="governance.sentinel.tasks.blocked",
                value=float(tasks_blocked),
                metric_type=MetricType.COUNTER,
                timestamp=now,
                tags={"feature": "sentinel", "status": "blocked"},
            )
        )

        # 4. Pending approvals
        pending_approvals = self._get_pending_approvals()
        points.append(
            MetricPoint(
                name="governance.sentinel.approvals.pending",
                value=float(pending_approvals),
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "sentinel"},
            )
        )

        # 5. Average approval time
        avg_approval_time = self._get_average_approval_time()
        points.append(
            MetricPoint(
                name="governance.sentinel.approvals.avg_time",
                value=avg_approval_time,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "sentinel"},
                fields={"unit": "hours"},
            )
        )

        # 6. Feature flag state
        is_enabled = self._is_feature_enabled()
        points.append(
            MetricPoint(
                name="governance.sentinel.enabled",
                value=1.0 if is_enabled else 0.0,
                metric_type=MetricType.GAUGE,
                timestamp=now,
                tags={"feature": "sentinel"},
            )
        )

        # 7. Block rate (blocked / total)
        if tasks_validated > 0:
            block_rate = (tasks_blocked / tasks_validated) * 100
            points.append(
                MetricPoint(
                    name="governance.sentinel.block_rate",
                    value=block_rate,
                    metric_type=MetricType.GAUGE,
                    timestamp=now,
                    tags={"feature": "sentinel"},
                    fields={"unit": "percent"},
                )
            )

        return points

    def _get_tasks_validated(self) -> int:
        """Get total validated task count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(TASKS_VALIDATED_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._tasks_validated

    def _get_tasks_approved(self) -> int:
        """Get approved task count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(f"{SENTINEL_PREFIX}:tasks_approved")
                if val:
                    return int(val)
            except Exception:
                pass
        return self._tasks_approved

    def _get_tasks_blocked(self) -> int:
        """Get blocked task count."""
        if self._redis_client:
            try:
                val = self._redis_client.get(TASKS_BLOCKED_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return self._tasks_blocked

    def _get_pending_approvals(self) -> int:
        """Get count of pending approvals."""
        if self._redis_client:
            try:
                val = self._redis_client.get(PENDING_APPROVALS_KEY)
                if val:
                    return int(val)
            except Exception:
                pass
        return 0

    def _get_average_approval_time(self) -> float:
        """Get average approval time in hours."""
        if self._approval_times:
            return sum(self._approval_times) / len(self._approval_times)

        if self._redis_client:
            try:
                val = self._redis_client.get(f"{SENTINEL_PREFIX}:avg_approval_time")
                if val:
                    return float(val)
            except Exception:
                pass
        return 0.0

    def _is_feature_enabled(self) -> bool:
        """Check if sentinel feature is enabled."""
        if self._redis_client:
            try:
                val: bytes | str | None = self._redis_client.get(
                    "chise:feature_flags:governance:task_sentinel_active"
                )
                return val == b"true" or val == "true"
            except Exception:
                pass
        return False

    # Methods for updating metrics
    def record_validation(
        self,
        story_points: float,
        blocked: bool = False,
        approved: bool = False,
    ) -> None:
        """Record a task validation event."""
        self._tasks_validated += 1

        if blocked:
            self._tasks_blocked += 1
        elif approved:
            self._tasks_approved += 1

        if self._redis_client:
            try:
                self._redis_client.incr(TASKS_VALIDATED_KEY)
                if blocked:
                    self._redis_client.incr(TASKS_BLOCKED_KEY)
                elif approved:
                    self._redis_client.incr(f"{SENTINEL_PREFIX}:tasks_approved")
            except Exception as e:
                logger.warning(f"Could not record validation to Redis: {e}")

    def record_approval_time(self, hours: float) -> None:
        """Record approval time for metrics."""
        self._approval_times.append(hours)
        if len(self._approval_times) > 100:
            self._approval_times = self._approval_times[-100:]
