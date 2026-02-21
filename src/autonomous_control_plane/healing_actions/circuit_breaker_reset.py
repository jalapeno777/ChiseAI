"""Circuit breaker reset healing action.

Manually resets circuit breaker to CLOSED state.

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.autonomous_control_plane.healing_actions.base import BaseHealingAction
from src.autonomous_control_plane.models.healing import (
    ActionPriority,
    HealingContext,
    ResourceLimits,
)
from src.common.circuit_breaker import CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class CircuitBreakerResetAction(BaseHealingAction):
    """Healing action to reset circuit breaker to CLOSED state.

    This action:
    1. Identifies the tripped circuit breaker
    2. Resets it to CLOSED state
    3. Verifies the reset

    Resource limits:
    - CPU: 2 seconds
    - Memory: 10 MB
    - Timeout: 10 seconds
    """

    action_type = "circuit_breaker_reset"
    priority = ActionPriority.P2

    def __init__(self, circuit_name: str | None = None):
        """Initialize circuit breaker reset action.

        Args:
            circuit_name: Name of circuit to reset (auto-detected if None)
        """
        super().__init__()
        self._circuit_name = circuit_name
        self._registry = CircuitBreakerRegistry()
        self._previous_state: dict[str, Any] | None = None

    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits for this action."""
        return ResourceLimits(
            max_cpu_seconds=2.0,
            max_memory_mb=10,
            max_execution_seconds=10.0,
            max_file_descriptors=5,
        )

    def _capture_state(self, context: HealingContext) -> dict[str, Any]:
        """Capture circuit breaker state before healing."""
        # Determine circuit name from context if not provided
        circuit_name = self._circuit_name
        if not circuit_name and context.log_entry:
            circuit_name = context.log_entry.metadata.get("circuit_name")
        if not circuit_name:
            circuit_name = context.service

        state = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": context.service,
            "action_type": self.action_type,
            "circuit_name": circuit_name,
        }

        # Capture current CB state
        try:
            breaker = self._registry.get(circuit_name)
            if breaker:
                state["previous_state"] = breaker.get_state_dict()
                self._previous_state = state["previous_state"]
        except Exception as e:
            logger.warning(f"Failed to capture circuit breaker state: {e}")

        return state

    def _execute_impl(self, context: HealingContext) -> dict[str, Any]:
        """Execute circuit breaker reset."""
        # Determine circuit name
        circuit_name = self._circuit_name
        if not circuit_name and context.log_entry:
            circuit_name = context.log_entry.metadata.get("circuit_name")
        if not circuit_name:
            circuit_name = context.service

        logger.info(f"Resetting circuit breaker: {circuit_name}")

        try:
            breaker = self._registry.get(circuit_name)
            if not breaker:
                return {
                    "success": False,
                    "error": f"Circuit breaker '{circuit_name}' not found",
                }

            # Capture state before reset
            before_state = breaker.get_state_dict()

            # Reset the circuit breaker
            breaker.force_close(reason=f"healing_action:{context.action_id}")

            # Verify reset
            after_state = breaker.get_state_dict()

            if after_state["state"] == "CLOSED":
                return {
                    "success": True,
                    "circuit_name": circuit_name,
                    "before_state": before_state["state"],
                    "after_state": after_state["state"],
                    "message": f"Circuit breaker '{circuit_name}' reset to CLOSED",
                }
            else:
                return {
                    "success": False,
                    "circuit_name": circuit_name,
                    "current_state": after_state["state"],
                    "error": "Circuit breaker did not transition to CLOSED",
                }

        except Exception as e:
            logger.error(f"Circuit breaker reset failed: {e}")
            return {
                "success": False,
                "circuit_name": circuit_name,
                "error": str(e),
            }

    def _rollback_impl(
        self, context: HealingContext, pre_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Rollback circuit breaker reset.

        Restores previous state (OPEN if it was OPEN before).
        """
        circuit_name = pre_state.get("circuit_name")
        previous_state = pre_state.get("previous_state", {})
        previous_state_name = previous_state.get("state")

        logger.info(f"Rolling back circuit breaker reset for {circuit_name}")

        try:
            breaker = self._registry.get(circuit_name)
            if not breaker:
                return {
                    "success": False,
                    "error": f"Circuit breaker '{circuit_name}' not found",
                }

            # Restore previous state if it was OPEN
            if previous_state_name == "OPEN":
                breaker.force_open(reason=f"rollback:{context.action_id}")
                return {
                    "success": True,
                    "circuit_name": circuit_name,
                    "restored_state": "OPEN",
                    "message": f"Circuit breaker '{circuit_name}' restored to OPEN",
                }
            else:
                return {
                    "success": True,
                    "circuit_name": circuit_name,
                    "restored_state": previous_state_name or "UNKNOWN",
                    "message": f"Circuit breaker '{circuit_name}' was already CLOSED, no action needed",
                }

        except Exception as e:
            logger.error(f"Circuit breaker rollback failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }
