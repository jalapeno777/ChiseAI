"""Unified health monitoring system for ChiseAI.

Aggregates health from all components:
- Paper trading components (orchestrator, position tracker, order simulator)
- Data sources (Redis, InfluxDB, PostgreSQL)
- Exchange connections (Bybit, Bitget)
- Kill-switch status

Provides health scores (0-100) per component and overall with
traffic light status: GREEN (90-100), YELLOW (70-89), RED (0-69).

For PAPER-003-001: Unified Health Monitoring System
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .history import HealthHistory
    from .monitor import HealthMonitor
    from .score_calculator import HealthScore, ScoreCalculator


class HealthStatus(Enum):
    """Traffic light status for health scores."""

    GREEN = "green"  # 90-100: Healthy
    YELLOW = "yellow"  # 70-89: Warning
    RED = "red"  # 0-69: Critical

    @classmethod
    def from_score(cls, score: float) -> HealthStatus:
        """Get status from numeric score.

        Args:
            score: Health score (0-100)

        Returns:
            Corresponding HealthStatus
        """
        if score >= 90:
            return cls.GREEN
        elif score >= 70:
            return cls.YELLOW
        else:
            return cls.RED


class ComponentType(Enum):
    """Types of health-monitored components."""

    ORCHESTRATOR = "orchestrator"
    POSITION_TRACKER = "position_tracker"
    ORDER_SIMULATOR = "order_simulator"
    REDIS = "redis"
    INFLUXDB = "influxdb"
    POSTGRESQL = "postgresql"
    BYBIT = "bybit"
    BITGET = "bitget"
    KILL_SWITCH = "kill_switch"


__all__ = [
    "HealthMonitor",
    "HealthScore",
    "ScoreCalculator",
    "HealthHistory",
    "HealthStatus",
    "ComponentType",
]
