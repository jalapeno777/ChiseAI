"""Rollback handler for canary deployments.

Provides automatic rollback functionality when canary gates fail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from execution.canary.models import CanaryDeployment, CanaryStatus


class RollbackStatus(Enum):
    """Status of a rollback operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        canary_id: Canary deployment ID
        champion_strategy_id: Strategy rolled back to
        status: Rollback status
        success: Whether rollback was successful
        message: Human-readable result message
        timestamp: When rollback completed
        details: Additional rollback details
    """

    canary_id: str
    champion_strategy_id: str | None
    status: RollbackStatus
    success: bool
    message: str
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "canary_id": self.canary_id,
            "champion_strategy_id": self.champion_strategy_id,
            "status": self.status.value,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class RollbackHandler:
    """Handles automatic rollback for failed canary deployments.

    This class provides:
    - Automatic rollback trigger on gate failure
    - Rollback to previous champion strategy
    - Rollback result tracking and logging
    """

    def __init__(
        self,
        rollback_callback: Callable[[str, str | None], bool] | None = None,
    ) -> None:
        """Initialize the rollback handler.

        Args:
            rollback_callback: Optional callback function to execute rollback.
                Function signature: (canary_id, champion_strategy_id) -> success
        """
        self.rollback_callback = rollback_callback
        self._rollback_history: list[RollbackResult] = []

    def execute_rollback(
        self,
        canary: CanaryDeployment,
        reason: str,
        force: bool = False,
    ) -> RollbackResult:
        """Execute rollback for a canary deployment.

        Args:
            canary: Canary deployment to roll back
            reason: Reason for rollback
            force: Force rollback even if status doesn't indicate failure

        Returns:
            Rollback result
        """
        # Check if rollback is needed
        # Only allow rollback if status is FAILED/ROLLED_BACK or force=True.
        if not force and canary.status not in (
            CanaryStatus.FAILED,
            CanaryStatus.ROLLED_BACK,
        ):
            return RollbackResult(
                canary_id=canary.canary_id,
                champion_strategy_id=canary.champion_strategy_id,
                status=RollbackStatus.FAILED,
                success=False,
                message=(
                    f"Rollback not needed: canary status is {canary.status.value}"
                ),
                details={"reason": reason, "forced": force},
            )

        # Check if champion exists for rollback
        if not canary.champion_strategy_id:
            return RollbackResult(
                canary_id=canary.canary_id,
                champion_strategy_id=None,
                status=RollbackStatus.FAILED,
                success=False,
                message="Rollback failed: no champion strategy available",
                details={"reason": reason, "forced": force},
            )

        # Execute rollback
        rollback_start = int(datetime.now().timestamp())

        try:
            if self.rollback_callback:
                success = self.rollback_callback(
                    canary.canary_id,
                    canary.champion_strategy_id,
                )
            else:
                # Default behavior: just mark as rolled back
                success = True

            rollback_end = int(datetime.now().timestamp())
            duration_ms = (rollback_end - rollback_start) * 1000

            if success:
                canary.status = CanaryStatus.ROLLED_BACK
                result = RollbackResult(
                    canary_id=canary.canary_id,
                    champion_strategy_id=canary.champion_strategy_id,
                    status=RollbackStatus.COMPLETED,
                    success=True,
                    message=(
                        f"Rollback completed: reverted to champion "
                        f"{canary.champion_strategy_id}"
                    ),
                    details={
                        "reason": reason,
                        "duration_ms": duration_ms,
                        "forced": force,
                    },
                )
            else:
                result = RollbackResult(
                    canary_id=canary.canary_id,
                    champion_strategy_id=canary.champion_strategy_id,
                    status=RollbackStatus.FAILED,
                    success=False,
                    message="Rollback failed: callback returned False",
                    details={
                        "reason": reason,
                        "duration_ms": duration_ms,
                        "forced": force,
                    },
                )

        except Exception as e:
            result = RollbackResult(
                canary_id=canary.canary_id,
                champion_strategy_id=canary.champion_strategy_id,
                status=RollbackStatus.FAILED,
                success=False,
                message=f"Rollback failed with exception: {str(e)}",
                details={
                    "reason": reason,
                    "error": str(e),
                    "forced": force,
                },
            )

        self._rollback_history.append(result)
        return result

    def check_and_rollback(
        self,
        canary: CanaryDeployment,
        failure_reasons: list[str],
    ) -> RollbackResult | None:
        """Check if rollback is needed and execute if so.

        Args:
            canary: Canary deployment to check
            failure_reasons: List of failure reasons

        Returns:
            Rollback result if rollback was executed, None otherwise
        """
        if not failure_reasons:
            return None

        # Set status to FAILED so rollback handler will execute
        canary.status = CanaryStatus.FAILED
        reason = "; ".join(failure_reasons)
        return self.execute_rollback(canary, reason)

    def get_rollback_history(
        self, canary_id: str | None = None
    ) -> list[RollbackResult]:
        """Get rollback history.

        Args:
            canary_id: Filter by canary ID (optional)

        Returns:
            List of rollback results
        """
        if canary_id:
            return [r for r in self._rollback_history if r.canary_id == canary_id]
        return self._rollback_history.copy()

    def clear_history(self) -> None:
        """Clear rollback history."""
        self._rollback_history.clear()


def create_rollback_handler(
    rollback_callback: Callable[[str, str | None], bool] | None = None,
) -> RollbackHandler:
    """Create a new rollback handler.

    Args:
        rollback_callback: Optional callback for rollback execution

    Returns:
        New RollbackHandler instance
    """
    return RollbackHandler(rollback_callback=rollback_callback)
