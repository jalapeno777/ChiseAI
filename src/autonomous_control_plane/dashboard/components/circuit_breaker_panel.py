"""Circuit breaker status panel component.

Provides real-time circuit breaker status display with filtering,
grouping, and interactive controls.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import CircuitBreakerPanelData

if TYPE_CHECKING:
    from autonomous_control_plane.components.circuit_breaker_registry import (
        CircuitBreakerRegistry,
    )

logger = logging.getLogger(__name__)


class CircuitBreakerPanel:
    """Circuit breaker status panel component.

    Displays circuit breaker states with filtering, grouping,
    and interactive controls for manual operations.

    Example:
        >>> panel = CircuitBreakerPanel(circuit_breaker_registry=registry)
        >>> data = await panel.get_data(group="database")
        >>> await panel.force_open("redis_service")
    """

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
    ):
        """Initialize circuit breaker panel.

        Args:
            circuit_breaker_registry: Circuit breaker registry
        """
        self._registry = circuit_breaker_registry

    async def get_data(self, group: str | None = None) -> CircuitBreakerPanelData:
        """Get circuit breaker panel data.

        Args:
            group: Filter by group name

        Returns:
            CircuitBreakerPanelData
        """
        data = CircuitBreakerPanelData()

        if self._registry is None:
            return data

        try:
            # Get all states
            states = self._registry.get_all_states_dict()
            data.total_count = len(states)

            # Process each breaker
            for name, state in states.items():
                state_value = state.get("state", "unknown")

                # Count by state
                if state_value == "open":
                    data.open_count += 1
                elif state_value == "closed":
                    data.closed_count += 1
                elif state_value == "half_open":
                    data.half_open_count += 1

                # Get health info
                health = None
                if hasattr(self._registry, "get_health"):
                    health = self._registry.get_health(name)

                # Build breaker data
                breaker_data = {
                    "name": name,
                    "state": state_value,
                    "failure_count": state.get("metrics", {}).get("failure_count", 0),
                    "success_count": state.get("metrics", {}).get("success_count", 0),
                    "rejection_count": state.get("metrics", {}).get(
                        "rejection_count", 0
                    ),
                    "consecutive_failures": state.get("metrics", {}).get(
                        "consecutive_failures", 0
                    ),
                    "consecutive_successes": state.get("metrics", {}).get(
                        "consecutive_successes", 0
                    ),
                    "last_error": state.get("last_error"),
                    "updated_at": state.get("updated_at"),
                    "is_healthy": health.is_healthy if health else None,
                    "failure_rate": health.failure_rate if health else 0.0,
                }

                # Add adaptive metrics if available
                if hasattr(self._registry, "get_adaptive_metrics"):
                    adaptive = self._registry.get_adaptive_metrics(name)
                    if adaptive:
                        breaker_data["adaptive"] = adaptive

                # Add canary state if available
                if hasattr(self._registry, "get_canary_state"):
                    canary = self._registry.get_canary_state(name)
                    if canary:
                        breaker_data["canary"] = canary

                data.breakers.append(breaker_data)

            # Get groups
            if hasattr(self._registry, "list_groups"):
                group_names = self._registry.list_groups()
                for group_name in group_names:
                    if group is None or group == group_name:
                        group_data = {"name": group_name}

                        if hasattr(self._registry, "get_group_metrics"):
                            metrics = self._registry.get_group_metrics(group_name)
                            if metrics:
                                group_data["metrics"] = metrics.to_dict()

                        data.groups.append(group_data)

        except Exception as e:
            logger.error(f"Error getting circuit breaker panel data: {e}")

        return data

    async def force_open(self, name: str, reason: str = "manual") -> bool:
        """Force open a circuit breaker.

        Args:
            name: Circuit breaker name
            reason: Reason for forcing open

        Returns:
            True if successful
        """
        if self._registry is None:
            return False

        try:
            return self._registry.force_open(name, reason)
        except Exception as e:
            logger.error(f"Error forcing open circuit breaker {name}: {e}")
            return False

    async def force_close(self, name: str, reason: str = "manual") -> bool:
        """Force close a circuit breaker.

        Args:
            name: Circuit breaker name
            reason: Reason for forcing close

        Returns:
            True if successful
        """
        if self._registry is None:
            return False

        try:
            return self._registry.force_close(name, reason)
        except Exception as e:
            logger.error(f"Error forcing close circuit breaker {name}: {e}")
            return False

    async def reset(self, name: str) -> bool:
        """Reset a circuit breaker.

        Args:
            name: Circuit breaker name

        Returns:
            True if successful
        """
        if self._registry is None:
            return False

        try:
            return self._registry.reset(name)
        except Exception as e:
            logger.error(f"Error resetting circuit breaker {name}: {e}")
            return False

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for all circuit breakers.

        Returns:
            Health summary dictionary
        """
        if self._registry is None:
            return {"total": 0, "healthy": 0, "unhealthy": 0}

        try:
            states = self._registry.get_all_states_dict()
            healthy = 0
            unhealthy = 0

            for name in states:
                health = self._registry.get_health(name)
                if health:
                    if health.is_healthy:
                        healthy += 1
                    else:
                        unhealthy += 1

            return {
                "total": len(states),
                "healthy": healthy,
                "unhealthy": unhealthy,
                "health_percentage": (healthy / len(states) * 100) if states else 100,
            }

        except Exception as e:
            logger.error(f"Error getting health summary: {e}")
            return {"total": 0, "healthy": 0, "unhealthy": 0}
