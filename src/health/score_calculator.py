"""Health score calculation module.

Calculates weighted health scores for components and overall system health.

Weights:
- Paper components: 40% (orchestrator, position tracker, order simulator)
- Data sources: 30% (Redis, InfluxDB, PostgreSQL)
- Exchanges: 20% (Bybit, Bitget)
- Kill-switch: 10%
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import ComponentType, HealthStatus

logger = logging.getLogger(__name__)


@dataclass
class ComponentScore:
    """Health score for a single component."""

    component: ComponentType
    score: float  # 0-100
    weight: float  # Weight in overall calculation
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def status(self) -> HealthStatus:
        """Get traffic light status."""
        return HealthStatus.from_score(self.score)

    @property
    def weighted_score(self) -> float:
        """Get weighted contribution to overall score."""
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component.value,
            "score": round(self.score, 2),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 2),
            "status": self.status.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HealthScore:
    """Aggregated health score for the entire system."""

    overall_score: float  # 0-100
    component_scores: list[ComponentScore]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def status(self) -> HealthStatus:
        """Get overall traffic light status."""
        return HealthStatus.from_score(self.overall_score)

    def get_component_score(self, component: ComponentType) -> ComponentScore | None:
        """Get score for a specific component."""
        for cs in self.component_scores:
            if cs.component == component:
                return cs
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_score": round(self.overall_score, 2),
            "status": self.status.value,
            "component_scores": [cs.to_dict() for cs in self.component_scores],
            "timestamp": self.timestamp.isoformat(),
        }


class ScoreCalculator:
    """Calculates health scores for components and overall system."""

    # Weight configuration (must sum to 1.0)
    COMPONENT_WEIGHTS: dict[ComponentType, float] = {
        # Paper components (40% total)
        ComponentType.ORCHESTRATOR: 0.15,
        ComponentType.POSITION_TRACKER: 0.15,
        ComponentType.ORDER_SIMULATOR: 0.10,
        # Data sources (30% total)
        ComponentType.REDIS: 0.10,
        ComponentType.INFLUXDB: 0.10,
        ComponentType.POSTGRESQL: 0.10,
        # Exchanges (20% total)
        ComponentType.BYBIT: 0.10,
        ComponentType.BITGET: 0.10,
        # Kill-switch (10%)
        ComponentType.KILL_SWITCH: 0.10,
    }

    def __init__(self) -> None:
        """Initialize score calculator."""
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Validate that weights sum to 1.0."""
        total = sum(self.COMPONENT_WEIGHTS.values())
        if not 0.99 <= total <= 1.01:  # Allow small floating point errors
            raise ValueError(f"Component weights must sum to 1.0, got {total}")

    def calculate_component_score(
        self,
        component: ComponentType,
        health_data: dict[str, Any],
    ) -> ComponentScore:
        """Calculate health score for a component.

        Args:
            component: Component type
            health_data: Health metrics from component

        Returns:
            ComponentScore with calculated score
        """
        weight = self.COMPONENT_WEIGHTS.get(component, 0.0)

        # Calculate score based on component type
        if component in (
            ComponentType.ORCHESTRATOR,
            ComponentType.POSITION_TRACKER,
            ComponentType.ORDER_SIMULATOR,
        ):
            score = self._calculate_paper_component_score(health_data)
        elif component in (
            ComponentType.REDIS,
            ComponentType.INFLUXDB,
            ComponentType.POSTGRESQL,
        ):
            score = self._calculate_data_source_score(health_data)
        elif component in (ComponentType.BYBIT, ComponentType.BITGET):
            score = self._calculate_exchange_score(health_data)
        elif component == ComponentType.KILL_SWITCH:
            score = self._calculate_kill_switch_score(health_data)
        else:
            score = 50.0  # Default for unknown components

        return ComponentScore(
            component=component,
            score=score,
            weight=weight,
            details=health_data,
        )

    def _calculate_paper_component_score(self, health_data: dict[str, Any]) -> float:
        """Calculate score for paper trading component.

        Factors:
        - is_running: +40 points if running
        - error_rate: -20 points per 1% error rate (max -40)
        - latency_ms: -10 points if >1000ms, -20 if >2000ms
        - last_success_seconds_ago: -10 per minute of inactivity (max -30)
        """
        score = 100.0

        # Check if running
        if not health_data.get("is_running", True):
            score -= 40

        # Error rate penalty
        error_rate = health_data.get("error_rate", 0.0)
        score -= min(error_rate * 20, 40)

        # Latency penalty
        latency_ms = health_data.get("latency_ms", 0)
        if latency_ms > 2000:
            score -= 20
        elif latency_ms > 1000:
            score -= 10

        # Inactivity penalty
        last_success = health_data.get("last_success_seconds_ago", 0)
        inactivity_minutes = last_success / 60
        score -= min(inactivity_minutes * 10, 30)

        return max(0, min(100, score))

    def _calculate_data_source_score(self, health_data: dict[str, Any]) -> float:
        """Calculate score for data source component.

        Factors:
        - is_connected: +40 points if connected
        - error_rate: -25 points per 1% error rate (max -50)
        - response_time_ms: -10 if >500ms, -20 if >1000ms
        - circuit_breaker_open: -30 points
        """
        score = 100.0

        # Connection status
        if not health_data.get("is_connected", True):
            score -= 40

        # Error rate penalty
        error_rate = health_data.get("error_rate", 0.0)
        score -= min(error_rate * 25, 50)

        # Response time penalty
        response_ms = health_data.get("response_time_ms", 0)
        if response_ms > 1000:
            score -= 20
        elif response_ms > 500:
            score -= 10

        # Circuit breaker penalty
        if health_data.get("circuit_breaker_open", False):
            score -= 30

        return max(0, min(100, score))

    def _calculate_exchange_score(self, health_data: dict[str, Any]) -> float:
        """Calculate score for exchange connection.

        Factors:
        - is_connected: +40 points if connected
        - latency_ms: -10 if >200ms, -20 if >500ms, -30 if >1000ms
        - reconnect_count: -5 per reconnection (max -20)
        - data_gap_seconds: -10 per 10 seconds of gap (max -30)
        """
        score = 100.0

        # Connection status
        if not health_data.get("is_connected", True):
            score -= 40

        # Latency penalty
        latency_ms = health_data.get("latency_ms", 0)
        if latency_ms > 1000:
            score -= 30
        elif latency_ms > 500:
            score -= 20
        elif latency_ms > 200:
            score -= 10

        # Reconnection penalty
        reconnects = health_data.get("reconnect_count", 0)
        score -= min(reconnects * 5, 20)

        # Data gap penalty
        gap_seconds = health_data.get("data_gap_seconds", 0)
        score -= min((gap_seconds / 10) * 10, 30)

        return max(0, min(100, score))

    def _calculate_kill_switch_score(self, health_data: dict[str, Any]) -> float:
        """Calculate score for kill-switch component.

        Factors:
        - is_armed: +30 points if armed (ready to trigger)
        - last_test_seconds_ago: -10 per day since last test (max -30)
        - error_rate: -20 points per 1% error rate (max -40)
        - state: +40 if ARMED, +20 if TRIGGERED, +10 if REAUTHORIZING
        """
        score = 100.0

        # State scoring
        state = health_data.get("state", "UNKNOWN")
        if state == "ARMED":
            score -= 0  # Full points
        elif state == "TRIGGERED":
            score -= 20  # Active emergency is concerning
        elif state == "REAUTHORIZING":
            score -= 30  # Being reset, not ready
        else:
            score -= 40  # Unknown/uninitialized state

        # Last test penalty
        last_test = health_data.get("last_test_seconds_ago", 0)
        days_since_test = last_test / (24 * 3600)
        score -= min(days_since_test * 10, 30)

        # Error rate penalty
        error_rate = health_data.get("error_rate", 0.0)
        score -= min(error_rate * 20, 40)

        return max(0, min(100, score))

    def calculate_overall_score(
        self, component_scores: list[ComponentScore]
    ) -> HealthScore:
        """Calculate overall health score from component scores.

        Args:
            component_scores: List of component scores

        Returns:
            HealthScore with overall score and component breakdown
        """
        if not component_scores:
            logger.warning("No component scores provided, returning 0")
            return HealthScore(overall_score=0.0, component_scores=[])

        # Calculate weighted average
        total_weighted_score = sum(cs.weighted_score for cs in component_scores)
        total_weight = sum(cs.weight for cs in component_scores)

        if total_weight == 0:
            overall_score = 0.0
        else:
            overall_score = total_weighted_score / total_weight

        return HealthScore(
            overall_score=overall_score,
            component_scores=component_scores,
        )
