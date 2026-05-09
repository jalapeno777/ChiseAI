"""
Zero-signal metrics module for Prometheus-compatible monitoring.

Tracks zero-signal events per datasource with counters, gauges, and timestamps.
Exports metrics in Prometheus text exposition format.
Falls back to in-memory storage when Redis is unavailable.

Redis keys:
  - bmad:chiseai:metrics:zero_signal:{datasource} (hash with metrics fields)
  - chise:config:zero_signal_thresholds (configurable thresholds)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Redis key patterns
METRICS_KEY_PREFIX = "bmad:chiseai:metrics:zero_signal:"
THRESHOLDS_KEY = "chise:config:zero_signal_thresholds"

# Default thresholds (minutes)
DEFAULT_THRESHOLDS: dict[str, int] = {
    "warning_minutes": 15,
    "critical_minutes": 45,
}


@dataclass
class DatasourceMetrics:
    """Per-datasource zero-signal metrics."""

    event_count: int = 0
    total_duration_minutes: float = 0.0
    current_duration_minutes: float = 0.0
    last_signal_timestamp: float = 0.0
    last_zero_signal_timestamp: float = 0.0
    is_zero_signal_active: bool = False
    severity: str = "none"  # none, info, warning, critical


class ZeroSignalMetrics:
    """Zero-signal metrics recorder with Prometheus text exposition export.

    Uses Redis for persistent storage when available, falls back to in-memory.
    Thread-safe via internal lock.
    """

    def __init__(self, redis_client: Any = None) -> None:
        self._redis = redis_client
        self._lock = threading.RLock()
        self._metrics: dict[str, DatasourceMetrics] = {}
        self._thresholds: dict[str, int] = dict(DEFAULT_THRESHOLDS)
        self._redis_available: bool | None = None

        if self._redis is not None:
            self._redis_available = True
            self._load_thresholds()

    def _get_redis(self) -> Any:
        """Lazy Redis client getter."""
        if self._redis is None:
            try:
                import redis

                self._redis = redis.Redis(
                    host=os.getenv(
                        "MONITORING_REDIS_HOST",
                        os.getenv("REDIS_HOST", "host.docker.internal"),
                    ),
                    port=int(
                        os.getenv(
                            "MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")
                        )
                    ),
                    decode_responses=True,
                )
                self._redis.ping()
                self._redis_available = True
            except Exception:
                self._redis = None
                self._redis_available = False
                logger.debug("Redis unavailable, using in-memory metrics")
        return self._redis

    def _load_thresholds(self) -> None:
        """Load thresholds from Redis config."""
        redis = self._get_redis()
        if redis is None:
            return
        try:
            stored = redis.hgetall(THRESHOLDS_KEY)
            if stored:
                for key, value in stored.items():
                    if key in self._thresholds:
                        self._thresholds[key] = int(value)
        except Exception:
            logger.debug("Failed to load thresholds from Redis, using defaults")

    def set_thresholds(self, thresholds: dict[str, int]) -> None:
        """Update thresholds and persist to Redis."""
        with self._lock:
            self._thresholds.update(thresholds)
            redis = self._get_redis()
            if redis is not None:
                try:
                    redis.hset(THRESHOLDS_KEY, mapping=thresholds)  # type: ignore[arg-type]
                except Exception:
                    logger.debug("Failed to persist thresholds to Redis")

    def get_thresholds(self) -> dict[str, int]:
        """Return current thresholds."""
        return dict(self._thresholds)

    def _get_severity(self, duration_minutes: float) -> str:
        """Determine severity level based on duration."""
        if duration_minutes >= self._thresholds["critical_minutes"]:
            return "critical"
        elif duration_minutes >= self._thresholds["warning_minutes"]:
            return "warning"
        elif duration_minutes > 0:
            return "info"
        return "none"

    def _get_or_create_metrics(self, datasource: str) -> DatasourceMetrics:
        """Get or create metrics for a datasource."""
        if datasource not in self._metrics:
            self._metrics[datasource] = DatasourceMetrics()
            self._load_from_redis(datasource)
        return self._metrics[datasource]

    def _load_from_redis(self, datasource: str) -> None:
        """Load metrics state from Redis."""
        redis = self._get_redis()
        if redis is None:
            return
        try:
            key = f"{METRICS_KEY_PREFIX}{datasource}"
            data = redis.hgetall(key)
            if data:
                m = self._metrics[datasource]
                m.event_count = int(data.get("event_count", 0))
                m.total_duration_minutes = float(
                    data.get("total_duration_minutes", 0.0)
                )
                m.current_duration_minutes = float(
                    data.get("current_duration_minutes", 0.0)
                )
                m.last_signal_timestamp = float(data.get("last_signal_timestamp", 0.0))
                m.last_zero_signal_timestamp = float(
                    data.get("last_zero_signal_timestamp", 0.0)
                )
                m.is_zero_signal_active = data.get("is_zero_signal_active", "0") == "1"
                m.severity = data.get("severity", "none")
        except Exception:
            logger.debug("Failed to load metrics from Redis for %s", datasource)

    def _save_to_redis(self, datasource: str) -> None:
        """Save metrics state to Redis."""
        redis = self._get_redis()
        if redis is None:
            return
        try:
            key = f"{METRICS_KEY_PREFIX}{datasource}"
            m = self._metrics[datasource]
            redis.hset(
                key,
                mapping={
                    "event_count": m.event_count,
                    "total_duration_minutes": m.total_duration_minutes,
                    "current_duration_minutes": m.current_duration_minutes,
                    "last_signal_timestamp": m.last_signal_timestamp,
                    "last_zero_signal_timestamp": m.last_zero_signal_timestamp,
                    "is_zero_signal_active": "1" if m.is_zero_signal_active else "0",
                    "severity": m.severity,
                },
            )
        except Exception:
            logger.debug("Failed to save metrics to Redis for %s", datasource)

    def record_zero_signal(
        self, datasource: str, duration_minutes: float, window_count: int = 1
    ) -> dict[str, Any]:
        """Record a zero-signal event for a datasource.

        Args:
            datasource: Name of the datasource with zero signals.
            duration_minutes: How long the zero-signal condition has persisted.
            window_count: Number of consecutive zero-signal windows (default 1).

        Returns:
            Dict with severity and metrics snapshot.
        """
        with self._lock:
            m = self._get_or_create_metrics(datasource)
            m.event_count += 1
            m.current_duration_minutes = duration_minutes
            m.total_duration_minutes += duration_minutes
            m.last_zero_signal_timestamp = time.time()
            m.is_zero_signal_active = True
            m.severity = self._get_severity(duration_minutes)

            self._save_to_redis(datasource)

            return {
                "datasource": datasource,
                "severity": m.severity,
                "event_count": m.event_count,
                "duration_minutes": m.current_duration_minutes,
                "window_count": window_count,
            }

    def record_signal_resumed(self, datasource: str) -> dict[str, Any]:
        """Record that signals have resumed for a datasource.

        Args:
            datasource: Name of the datasource that recovered.

        Returns:
            Dict with recovery info and metrics snapshot.
        """
        with self._lock:
            m = self._get_or_create_metrics(datasource)
            was_active = m.is_zero_signal_active
            outage_duration = m.current_duration_minutes

            m.is_zero_signal_active = False
            m.current_duration_minutes = 0.0
            m.severity = "none"
            m.last_signal_timestamp = time.time()

            self._save_to_redis(datasource)

            return {
                "datasource": datasource,
                "was_active": was_active,
                "outage_duration_minutes": outage_duration,
                "event_count": m.event_count,
            }

    def update_last_signal(self, datasource: str) -> None:
        """Update last signal timestamp for a datasource (heartbeat)."""
        with self._lock:
            m = self._get_or_create_metrics(datasource)
            m.last_signal_timestamp = time.time()

            if m.is_zero_signal_active:
                # Signal resumed
                m.is_zero_signal_active = False
                m.current_duration_minutes = 0.0
                m.severity = "none"

            self._save_to_redis(datasource)

    def get_metrics(self, datasource: str) -> DatasourceMetrics | None:
        """Get metrics for a specific datasource."""
        with self._lock:
            return self._metrics.get(datasource)

    def get_all_metrics(self) -> dict[str, DatasourceMetrics]:
        """Get all datasource metrics."""
        with self._lock:
            return dict(self._metrics)

    def get_metrics_text(self) -> str:
        """Export metrics in Prometheus text exposition format.

        Returns:
            Prometheus-formatted text with all zero-signal metrics.
        """
        with self._lock:
            lines: list[str] = []
            now = time.time()

            # Help and type declarations
            lines.append(
                "# HELP chiseai_zero_signal_event_count "
                "Total zero-signal events per datasource"
            )
            lines.append("# TYPE chiseai_zero_signal_event_count counter")

            lines.append(
                "# HELP chiseai_zero_signal_duration_minutes "
                "Current zero-signal duration in minutes"
            )
            lines.append("# TYPE chiseai_zero_signal_duration_minutes gauge")

            lines.append(
                "# HELP chiseai_zero_signal_total_duration_minutes "
                "Cumulative zero-signal duration in minutes"
            )
            lines.append("# TYPE chiseai_zero_signal_total_duration_minutes counter")

            lines.append(
                "# HELP chiseai_zero_signal_last_signal_timestamp "
                "Unix timestamp of last received signal"
            )
            lines.append("# TYPE chiseai_zero_signal_last_signal_timestamp gauge")

            lines.append(
                "# HELP chiseai_zero_signal_active "
                "Whether zero-signal is currently active (1=active, 0=inactive)"
            )
            lines.append("# TYPE chiseai_zero_signal_active gauge")

            lines.append(
                "# HELP chiseai_zero_signal_severity "
                "Current severity level (0=none, 1=info, 2=warning, 3=critical)"
            )
            lines.append("# TYPE chiseai_zero_signal_severity gauge")

            severity_map = {"none": 0, "info": 1, "warning": 2, "critical": 3}

            for datasource in sorted(self._metrics.keys()):
                m = self._metrics[datasource]
                labels = f'datasource="{datasource}"'

                lines.append(
                    f"chiseai_zero_signal_event_count{{{labels}}} {m.event_count}"
                )
                lines.append(
                    f"chiseai_zero_signal_duration_minutes{{{labels}}} {m.current_duration_minutes:.2f}"
                )
                lines.append(
                    f"chiseai_zero_signal_total_duration_minutes{{{labels}}} {m.total_duration_minutes:.2f}"
                )
                lines.append(
                    f"chiseai_zero_signal_last_signal_timestamp{{{labels}}} {m.last_signal_timestamp:.0f}"
                )
                lines.append(
                    f"chiseai_zero_signal_active{{{labels}}} {1 if m.is_zero_signal_active else 0}"
                )
                lines.append(
                    f"chiseai_zero_signal_severity{{{labels}}} {severity_map.get(m.severity, 0)}"
                )

            # Summary metrics
            active_count = sum(
                1 for m in self._metrics.values() if m.is_zero_signal_active
            )
            total_datasources = len(self._metrics)

            lines.append("")
            lines.append(
                "# HELP chiseai_zero_signal_active_datasources "
                "Number of datasources currently in zero-signal state"
            )
            lines.append("# TYPE chiseai_zero_signal_active_datasources gauge")
            lines.append(f"chiseai_zero_signal_active_datasources {active_count}")

            lines.append(
                "# HELP chiseai_zero_signal_total_datasources "
                "Total number of tracked datasources"
            )
            lines.append("# TYPE chiseai_zero_signal_total_datasources gauge")
            lines.append(f"chiseai_zero_signal_total_datasources {total_datasources}")

            lines.append(f"# Exported at {now:.0f}")
            lines.append("")

            return "\n".join(lines)

    def reset(self, datasource: str | None = None) -> None:
        """Reset metrics for a datasource or all datasources.

        Args:
            datasource: Specific datasource to reset, or None for all.
        """
        with self._lock:
            if datasource:
                if datasource in self._metrics:
                    del self._metrics[datasource]
                    redis = self._get_redis()
                    if redis is not None:
                        import contextlib

                        with contextlib.suppress(Exception):
                            redis.delete(f"{METRICS_KEY_PREFIX}{datasource}")
            else:
                self._metrics.clear()
                redis = self._get_redis()
                if redis is not None:
                    import contextlib

                    with contextlib.suppress(Exception):
                        for key in redis.keys(f"{METRICS_KEY_PREFIX}*"):
                            redis.delete(key)
