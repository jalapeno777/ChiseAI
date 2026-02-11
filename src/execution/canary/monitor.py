"""Canary monitoring scheduler.

Provides scheduled monitoring checks for canary deployments.
Runs gate evaluations every 15 minutes during canary period.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import (
    CanaryDeployment,
    CanaryStatus,
    GateCheck,
)
from execution.canary.rollback import RollbackHandler, RollbackResult

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class MonitoringCheck:
    """Result of a monitoring check.

    Attributes:
        canary_id: Canary deployment ID
        timestamp: When check was performed
        gate_checks: Individual gate check results
        status: Canary status after check
        action_taken: Action taken (e.g., "rollback", "promote", "continue")
        message: Human-readable message
    """

    canary_id: str
    timestamp: int
    gate_checks: list[GateCheck]
    status: CanaryStatus
    action_taken: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "canary_id": self.canary_id,
            "timestamp": self.timestamp,
            "gate_checks": [check.to_dict() for check in self.gate_checks],
            "status": self.status.value,
            "action_taken": self.action_taken,
            "message": self.message,
        }


class CanaryMonitor:
    """Monitors canary deployments with scheduled checks.

    This class provides:
    - 15-minute interval monitoring checks
    - Automatic rollback on gate failure
    - Check result persistence
    - Integration with promotion workflow
    """

    DEFAULT_CHECK_INTERVAL_MINUTES = 15

    def __init__(
        self,
        check_interval_minutes: int = DEFAULT_CHECK_INTERVAL_MINUTES,
        gate_evaluator: GateEvaluator | None = None,
        rollback_handler: RollbackHandler | None = None,
        on_status_change: Callable[[CanaryDeployment, CanaryStatus], None]
        | None = None,
        on_rollback: Callable[[RollbackResult], None] | None = None,
    ) -> None:
        """Initialize the canary monitor.

        Args:
            check_interval_minutes: Minutes between checks (default 15)
            gate_evaluator: Gate evaluator instance
            rollback_handler: Rollback handler instance
            on_status_change: Callback when canary status changes
            on_rollback: Callback when rollback is executed
        """
        self.check_interval_minutes = check_interval_minutes
        self.gate_evaluator = gate_evaluator or GateEvaluator()
        self.rollback_handler = rollback_handler or RollbackHandler()
        self.on_status_change = on_status_change
        self.on_rollback = on_rollback

        self._monitored_canaries: dict[str, CanaryDeployment] = {}
        self._check_history: list[MonitoringCheck] = []
        self._running = False
        self._task: asyncio.Task[Any] | None = None

    def register_canary(self, canary: CanaryDeployment) -> None:
        """Register a canary for monitoring.

        Args:
            canary: Canary deployment to monitor
        """
        self._monitored_canaries[canary.canary_id] = canary
        logger.info(
            f"Registered canary {canary.canary_id} for monitoring "
            f"(interval: {self.check_interval_minutes}min)"
        )

    def unregister_canary(self, canary_id: str) -> CanaryDeployment | None:
        """Unregister a canary from monitoring.

        Args:
            canary_id: Canary ID to unregister

        Returns:
            The unregistered canary or None if not found
        """
        return self._monitored_canaries.pop(canary_id, None)

    async def run_check(self, canary: CanaryDeployment) -> MonitoringCheck:
        """Run a single monitoring check on a canary.

        Args:
            canary: Canary deployment to check

        Returns:
            Monitoring check result
        """
        timestamp = int(datetime.now().timestamp())

        # Evaluate all gates
        gate_checks = self.gate_evaluator.evaluate_all_gates(canary)

        # Determine status
        new_status, messages = self.gate_evaluator.determine_status(gate_checks)

        # Check for status change
        old_status = canary.status
        action_taken = "continue"

        if new_status == CanaryStatus.FAILED:
            # Set status to FAILED first so rollback handler will execute
            canary.status = CanaryStatus.FAILED
            # Execute rollback
            rollback_result = self.rollback_handler.execute_rollback(
                canary,
                reason="; ".join(messages),
            )
            action_taken = "rollback"
            if self.on_rollback:
                self.on_rollback(rollback_result)
            message = f"Rollback executed: {rollback_result.message}"

        elif new_status == CanaryStatus.PASSED:
            action_taken = "ready_for_promotion"
            canary.status = CanaryStatus.PASSED
            message = "All gates passed - ready for promotion"

        else:
            message = f"Canary running: {len(messages)} gates pending"

        # Update canary status (only if not already updated by rollback or promotion)
        if new_status != old_status and canary.status not in (
            CanaryStatus.ROLLED_BACK,
            CanaryStatus.PASSED,
        ):
            canary.status = new_status

        # Trigger status change callback for any status change
        if canary.status != old_status and self.on_status_change:
            self.on_status_change(canary, canary.status)

        check = MonitoringCheck(
            canary_id=canary.canary_id,
            timestamp=timestamp,
            gate_checks=gate_checks,
            status=canary.status,
            action_taken=action_taken,
            message=message,
        )

        self._check_history.append(check)
        return check

    async def run_all_checks(self) -> list[MonitoringCheck]:
        """Run checks on all monitored canaries.

        Returns:
            List of monitoring check results
        """
        results = []

        # Filter to only running canaries
        running_canaries = [
            c
            for c in self._monitored_canaries.values()
            if c.status == CanaryStatus.RUNNING
        ]

        for canary in running_canaries:
            try:
                result = await self.run_check(canary)
                results.append(result)
                logger.info(
                    f"Check completed for {canary.canary_id}: {result.action_taken}"
                )
            except Exception as e:
                logger.error(f"Check failed for {canary.canary_id}: {e}")
                # Create error check result
                results.append(
                    MonitoringCheck(
                        canary_id=canary.canary_id,
                        timestamp=int(datetime.now().timestamp()),
                        gate_checks=[],
                        status=canary.status,
                        action_taken="error",
                        message=f"Check failed: {str(e)}",
                    )
                )

        return results

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self.run_all_checks()
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

            # Wait for next check interval
            await asyncio.sleep(self.check_interval_minutes * 60)

    async def start(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info(
            f"Started canary monitor (interval: {self.check_interval_minutes}min)"
        )

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Stopped canary monitor")

    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running

    def get_check_history(
        self,
        canary_id: str | None = None,
        limit: int | None = None,
    ) -> list[MonitoringCheck]:
        """Get check history.

        Args:
            canary_id: Filter by canary ID
            limit: Maximum number of results

        Returns:
            List of monitoring checks
        """
        history = self._check_history

        if canary_id:
            history = [c for c in history if c.canary_id == canary_id]

        # Sort by timestamp descending
        history = sorted(history, key=lambda x: x.timestamp, reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_canary_status(self, canary_id: str) -> CanaryStatus | None:
        """Get current status of a monitored canary.

        Args:
            canary_id: Canary ID

        Returns:
            Current status or None if not monitored
        """
        canary = self._monitored_canaries.get(canary_id)
        return canary.status if canary else None

    def clear_history(self) -> None:
        """Clear check history."""
        self._check_history.clear()


def create_canary_monitor(
    check_interval_minutes: int = CanaryMonitor.DEFAULT_CHECK_INTERVAL_MINUTES,
    gate_evaluator: GateEvaluator | None = None,
    rollback_handler: RollbackHandler | None = None,
) -> CanaryMonitor:
    """Create a new canary monitor.

    Args:
        check_interval_minutes: Minutes between checks
        gate_evaluator: Gate evaluator instance
        rollback_handler: Rollback handler instance

    Returns:
        New CanaryMonitor instance
    """
    return CanaryMonitor(
        check_interval_minutes=check_interval_minutes,
        gate_evaluator=gate_evaluator,
        rollback_handler=rollback_handler,
    )
