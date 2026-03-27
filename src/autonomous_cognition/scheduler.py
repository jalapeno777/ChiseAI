"""Scheduler for autonomous cognition daily cycles."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from autonomous_cognition.controller import AutonomousCognitionController

logger = logging.getLogger(__name__)


class SelfAssessmentScheduler:
    """Schedules and executes daily self-assessment cycles."""

    def __init__(
        self,
        controller: AutonomousCognitionController | None = None,
        redis_client: Any | None = None,
    ):
        self._controller = controller or AutonomousCognitionController(
            redis_client=redis_client
        )
        self._last_run: datetime | None = None
        self._running = False

    def run_daily_cycle(self) -> dict[str, Any]:
        """Execute daily self-assessment cycle.

        Returns:
            Dict with status, artifact_path, and any errors
        """
        result = {
            "status": "started",
            "timestamp": datetime.now(UTC).isoformat(),
            "artifact_path": None,
            "error": None,
        }

        try:
            self._running = True
            artifact, artifact_path = self._controller.run_daily_self_assessment()
            result["status"] = artifact.status
            result["artifact_path"] = str(artifact_path) if artifact_path else None
            result["overall_score"] = artifact.overall_score
            self._last_run = datetime.now(UTC)
            logger.info(
                "Daily self-assessment completed: status=%s score=%.2f",
                artifact.status,
                artifact.overall_score,
            )
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            logger.exception("Daily self-assessment failed: %s", e)
        finally:
            self._running = False

        return result

    def should_run(self, last_run_time: datetime | None = None) -> bool:
        """Check if daily cycle should run based on last execution time.

        Args:
            last_run_time: Optional last run timestamp (defaults to self._last_run)

        Returns:
            True if more than 24 hours have passed since last run
        """
        last = last_run_time or self._last_run
        if last is None:
            return True
        return datetime.now(UTC) - last >= timedelta(hours=24)

    @property
    def is_running(self) -> bool:
        """Check if a cycle is currently running."""
        return self._running

    @property
    def last_run_time(self) -> datetime | None:
        """Get timestamp of last successful run."""
        return self._last_run


def run_scheduled_self_assessment(
    scheduler: SelfAssessmentScheduler | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Entry point for running scheduled self-assessment.

    Args:
        scheduler: Optional scheduler instance
        force: If True, run regardless of schedule

    Returns:
        Execution result dictionary
    """
    sched = scheduler or SelfAssessmentScheduler()

    if not force and not sched.should_run():
        return {
            "status": "skipped",
            "reason": "Last run was within 24 hours",
            "last_run": (
                sched.last_run_time.isoformat() if sched.last_run_time else None
            ),
        }

    return sched.run_daily_cycle()
