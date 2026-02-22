"""Health history tracking module.

Tracks health scores over time and calculates trends.
Maintains 24 hours of history for trend analysis.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .score_calculator import HealthScore

logger = logging.getLogger(__name__)


@dataclass
class HealthSnapshot:
    """A single point-in-time health snapshot."""

    score: float
    status: str
    timestamp: datetime
    component_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": round(self.score, 2),
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "component_scores": {
                k: round(v, 2) for k, v in self.component_scores.items()
            },
        }


@dataclass
class TrendAnalysis:
    """Trend analysis for health scores."""

    direction: str  # "improving", "stable", "degrading"
    change_1h: float  # Change in last hour
    change_24h: float  # Change in last 24 hours
    volatility: float  # Standard deviation of scores
    avg_score: float  # Average score over period
    min_score: float  # Minimum score in period
    max_score: float  # Maximum score in period

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "direction": self.direction,
            "change_1h": round(self.change_1h, 2),
            "change_24h": round(self.change_24h, 2),
            "volatility": round(self.volatility, 2),
            "avg_score": round(self.avg_score, 2),
            "min_score": round(self.min_score, 2),
            "max_score": round(self.max_score, 2),
        }


class HealthHistory:
    """Tracks health history for trend analysis.

    Maintains:
    - 24 hours of snapshots at 1-minute intervals (1440 points)
    - Per-component history for detailed analysis
    - Alert history for incident tracking
    """

    MAX_HISTORY_MINUTES = 1440  # 24 hours
    SNAPSHOT_INTERVAL_SECONDS = 60  # 1 minute

    def __init__(self, max_history_minutes: int | None = None) -> None:
        """Initialize health history tracker.

        Args:
            max_history_minutes: Override default 24-hour window
        """
        self.max_history_minutes = max_history_minutes or self.MAX_HISTORY_MINUTES
        self._history: deque[HealthSnapshot] = deque(maxlen=self.max_history_minutes)
        self._alert_history: deque[dict[str, Any]] = deque(maxlen=100)
        self._lock = asyncio.Lock()
        self._last_snapshot_time: datetime | None = None

        logger.info(
            f"HealthHistory initialized: max_history={self.max_history_minutes}min"
        )

    async def record_snapshot(self, health_score: HealthScore) -> None:
        """Record a health snapshot.

        Args:
            health_score: Current health score to record
        """
        now = datetime.now(UTC)

        # Rate limit snapshots to interval
        if self._last_snapshot_time:
            elapsed = (now - self._last_snapshot_time).total_seconds()
            if elapsed < self.SNAPSHOT_INTERVAL_SECONDS:
                return

        async with self._lock:
            snapshot = HealthSnapshot(
                score=health_score.overall_score,
                status=health_score.status.value,
                timestamp=now,
                component_scores={
                    cs.component.value: cs.score for cs in health_score.component_scores
                },
            )
            self._history.append(snapshot)
            self._last_snapshot_time = now

        logger.debug(f"Health snapshot recorded: score={snapshot.score:.1f}")

    async def record_alert(
        self,
        component: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an alert for history.

        Args:
            component: Component that triggered alert
            severity: Alert severity (info, warning, critical)
            message: Alert message
            details: Additional alert details
        """
        alert = {
            "component": component,
            "severity": severity,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }

        async with self._lock:
            self._alert_history.append(alert)

        logger.info(f"Alert recorded: [{severity}] {component} - {message}")

    async def get_recent_history(
        self,
        minutes: int = 60,
        component: str | None = None,
    ) -> list[HealthSnapshot]:
        """Get recent health history.

        Args:
            minutes: Number of minutes to retrieve
            component: Filter by component (optional)

        Returns:
            List of health snapshots
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

        async with self._lock:
            snapshots = [s for s in self._history if s.timestamp >= cutoff]

        if component:
            # Return snapshots with only the requested component
            filtered = []
            for s in snapshots:
                if component in s.component_scores:
                    filtered.append(
                        HealthSnapshot(
                            score=s.component_scores[component],
                            status=s.status,
                            timestamp=s.timestamp,
                            component_scores={component: s.component_scores[component]},
                        )
                    )
            return filtered

        return snapshots

    async def calculate_trend(
        self,
        hours: int = 24,
        component: str | None = None,
    ) -> TrendAnalysis | None:
        """Calculate health trend over time.

        Args:
            hours: Number of hours to analyze
            component: Component to analyze (None for overall)

        Returns:
            TrendAnalysis or None if insufficient data
        """
        minutes = hours * 60
        snapshots = await self.get_recent_history(minutes, component)

        if len(snapshots) < 2:
            logger.warning(f"Insufficient data for trend: {len(snapshots)} snapshots")
            return None

        scores = [s.score for s in snapshots]

        # Calculate statistics
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)

        # Calculate volatility (standard deviation)
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        volatility = variance**0.5

        # Calculate changes
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)
        now - timedelta(hours=24)

        recent_1h = [s.score for s in snapshots if s.timestamp >= one_hour_ago]
        recent_24h = scores

        change_1h = 0.0
        if len(recent_1h) >= 2:
            change_1h = recent_1h[-1] - recent_1h[0]

        change_24h = 0.0
        if len(recent_24h) >= 2:
            change_24h = recent_24h[-1] - recent_24h[0]

        # Determine direction
        if abs(change_24h) < 5:  # Less than 5 point change = stable
            direction = "stable"
        elif change_24h > 0:
            direction = "improving"
        else:
            direction = "degrading"

        return TrendAnalysis(
            direction=direction,
            change_1h=change_1h,
            change_24h=change_24h,
            volatility=volatility,
            avg_score=avg_score,
            min_score=min_score,
            max_score=max_score,
        )

    async def get_alert_history(
        self,
        hours: int = 24,
        severity: str | None = None,
        component: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get alert history.

        Args:
            hours: Number of hours to retrieve
            severity: Filter by severity (optional)
            component: Filter by component (optional)

        Returns:
            List of alert dictionaries
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        async with self._lock:
            alerts = [
                a
                for a in self._alert_history
                if datetime.fromisoformat(a["timestamp"]) >= cutoff
            ]

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        if component:
            alerts = [a for a in alerts if a["component"] == component]

        return list(alerts)

    def get_stats(self) -> dict[str, Any]:
        """Get history statistics.

        Returns:
            Dictionary with history stats
        """
        return {
            "total_snapshots": len(self._history),
            "total_alerts": len(self._alert_history),
            "max_history_minutes": self.max_history_minutes,
            "snapshot_interval_seconds": self.SNAPSHOT_INTERVAL_SECONDS,
            "oldest_snapshot": (
                self._history[0].timestamp.isoformat() if self._history else None
            ),
            "newest_snapshot": (
                self._history[-1].timestamp.isoformat() if self._history else None
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert history to dictionary (last 100 snapshots)."""
        return {
            "snapshots": [s.to_dict() for s in list(self._history)[-100:]],
            "stats": self.get_stats(),
        }
