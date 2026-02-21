"""Canary monitoring scheduler.

Provides scheduled monitoring checks for canary deployments.
Runs gate evaluations every 15 minutes during canary period.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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
        on_status_change: (
            Callable[[CanaryDeployment, CanaryStatus], None] | None
        ) = None,
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
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

    def schedule_auto_evaluation(
        self,
        cron_interval_minutes: int = 15,
        storage_path: Path | None = None,
        on_evaluation_complete: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Schedule automatic evaluation with configurable cron interval.

        Args:
            cron_interval_minutes: Minutes between evaluations (default 15)
            storage_path: Path to store evaluation results
            on_evaluation_complete: Callback when evaluation completes

        Returns:
            Schedule configuration dictionary
        """
        schedule_config = {
            "interval_minutes": cron_interval_minutes,
            "storage_path": str(storage_path) if storage_path else None,
            "enabled": True,
            "scheduled_at": int(datetime.now().timestamp()),
            "next_evaluation_at": int(datetime.now().timestamp())
            + (cron_interval_minutes * 60),
        }

        # Store schedule config in metadata
        self._schedule_config = schedule_config
        self._on_evaluation_complete = on_evaluation_complete

        logger.info(
            f"Scheduled auto-evaluation every {cron_interval_minutes} minutes "
            f"for {len(self._monitored_canaries)} canaries"
        )

        return schedule_config

    async def run_auto_evaluation(
        self,
        storage_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        """Run automatic evaluation on all active canaries.

        Loads active canaries, evaluates gates, and stores results.

        Args:
            storage_path: Path to store evaluation results

        Returns:
            List of evaluation results
        """
        results = []

        # Filter to active (running or pending) canaries
        active_canaries = [
            c
            for c in self._monitored_canaries.values()
            if c.status in (CanaryStatus.RUNNING, CanaryStatus.PENDING)
        ]

        if not active_canaries:
            logger.info("No active canaries to evaluate")
            return results

        for canary in active_canaries:
            try:
                # Run gate evaluation
                evaluation_result = await self._evaluate_canary(canary, storage_path)
                results.append(evaluation_result)

                # Trigger status change alert if needed
                await self.alert_on_status_change(canary, evaluation_result)

                logger.info(
                    f"Auto-evaluation completed for {canary.canary_id}: "
                    f"{evaluation_result['status']}"
                )

            except Exception as e:
                logger.error(f"Auto-evaluation failed for {canary.canary_id}: {e}")
                results.append(
                    {
                        "canary_id": canary.canary_id,
                        "status": "ERROR",
                        "error": str(e),
                        "timestamp": int(datetime.now().timestamp()),
                    }
                )

        return results

    async def _evaluate_canary(
        self,
        canary: CanaryDeployment,
        storage_path: Path | None,
    ) -> dict[str, Any]:
        """Evaluate a single canary and store results.

        Args:
            canary: Canary to evaluate
            storage_path: Path to store results

        Returns:
            Evaluation result dictionary
        """
        # Generate pass/fail summary
        summary = self.gate_evaluator.generate_pass_fail_summary(canary)

        # Create evaluation result
        evaluation = {
            "canary_id": canary.canary_id,
            "strategy_id": canary.strategy_id,
            "status": summary["status"],
            "previous_status": canary.status.value,
            "gate_summary": summary["gate_summary"],
            "reasons": summary["reasons"],
            "can_promote": summary["can_promote"],
            "should_rollback": summary["should_rollback"],
            "timestamp": int(datetime.now().timestamp()),
            "gate_details": summary["gate_details"],
        }

        # Store result to disk if path provided
        if storage_path:
            await self._store_evaluation_result(evaluation, storage_path)

        # Update canary status if needed
        if summary["status"] == "PASS":
            canary.status = CanaryStatus.PASSED
        elif summary["status"] == "FAIL":
            canary.status = CanaryStatus.FAILED

        # Trigger callback if provided
        if hasattr(self, "_on_evaluation_complete") and self._on_evaluation_complete:
            self._on_evaluation_complete(canary.canary_id, evaluation)

        return evaluation

    async def _store_evaluation_result(
        self,
        evaluation: dict[str, Any],
        storage_path: Path,
    ) -> Path:
        """Store evaluation result to disk.

        Args:
            evaluation: Evaluation result dictionary
            storage_path: Path to store results

        Returns:
            Path to stored file
        """
        canary_id = evaluation["canary_id"]
        output_dir = storage_path / canary_id / "evaluations"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = evaluation["timestamp"]
        timestamp_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")

        json_path = output_dir / f"auto_eval_{timestamp_str}.json"
        json_path.write_text(json.dumps(evaluation, indent=2))

        return json_path

    async def alert_on_status_change(
        self,
        canary: CanaryDeployment,
        evaluation: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Alert when canary moves from PENDING -> PASS/FAIL.

        Args:
            canary: Canary deployment
            evaluation: Evaluation result

        Returns:
            Alert data if status changed, None otherwise
        """
        previous_status = evaluation["previous_status"]
        current_status = evaluation["status"]

        # Only alert on transitions from PENDING/RUNNING to PASS/FAIL
        status_changed = previous_status in (
            "pending",
            "running",
            "PENDING",
            "RUNNING",
        ) and current_status in ("PASS", "FAIL")

        if not status_changed:
            return None

        alert = {
            "alert_type": "canary_status_change",
            "canary_id": canary.canary_id,
            "strategy_id": canary.strategy_id,
            "previous_status": previous_status,
            "current_status": current_status,
            "can_promote": evaluation["can_promote"],
            "should_rollback": evaluation["should_rollback"],
            "reasons": evaluation["reasons"],
            "timestamp": evaluation["timestamp"],
            "message": (
                f"Canary {canary.canary_id} changed from {previous_status} "
                f"to {current_status}"
            ),
        }

        logger.warning(f"STATUS CHANGE ALERT: {alert['message']}")

        return alert

    def get_active_canaries(self) -> list[CanaryDeployment]:
        """Get list of active (running/pending) canaries.

        Returns:
            List of active canary deployments
        """
        return [
            c
            for c in self._monitored_canaries.values()
            if c.status in (CanaryStatus.RUNNING, CanaryStatus.PENDING)
        ]


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
