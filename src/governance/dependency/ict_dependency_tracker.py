"""
ICT Dependency Tracker for EP-ICT-006 Part-B Milestone Tracking

This module provides automated dependency tracking for EP-ICT-006 Part-B,
including status checks, transition planning, and weekly reports.

Story: ST-ICT-037
Epic: EP-ICT-006 Part-B
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MilestoneStatus(Enum):
    """Status values for milestone tracking."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PROVISIONAL_PASS = "provisional_pass"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class DependencyInfo:
    """Information about a dependency."""

    name: str
    status: MilestoneStatus
    owner: str
    due_date: datetime | None = None
    blockers: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class TransitionPlan:
    """Plan for transitioning from provisional to final deployment."""

    current_state: str
    target_state: str
    steps: list[str]
    estimated_duration_hours: float
    prerequisites: list[str]
    risks: list[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WeeklyReport:
    """Weekly dependency status report."""

    week_start: datetime
    week_end: datetime
    dependencies: list[DependencyInfo]
    status_changes: list[dict[str, Any]]
    blockers: list[str]
    generated_at: datetime = field(default_factory=datetime.utcnow)


class ICTDependencyTracker:
    """
    Tracks EP-ICT-006 Part-B dependencies and provides transition planning.

    This class manages:
    - EP-ICT-006 Part-B milestone status tracking
    - Dependency health monitoring
    - Transition planning from provisional to final
    - Weekly status report generation
    """

    def __init__(self, epic_id: str = "EP-ICT-006", part: str = "Part-B"):
        """
        Initialize the dependency tracker.

        Args:
            epic_id: The epic identifier (default: EP-ICT-006)
            part: The part identifier (default: Part-B)
        """
        self.epic_id = epic_id
        self.part = part
        self._dependencies: dict[str, DependencyInfo] = {}
        self._status_history: list[dict[str, Any]] = []

    def add_dependency(self, dependency: DependencyInfo) -> None:
        """
        Add a dependency to track.

        Args:
            dependency: DependencyInfo object with dependency details
        """
        self._dependencies[dependency.name] = dependency
        self._record_status_change(
            f"Added dependency: {dependency.name}", dependency.status.value
        )
        logger.info(f"Added dependency: {dependency.name} ({dependency.status.value})")

    def update_dependency_status(
        self, name: str, status: MilestoneStatus, notes: str = ""
    ) -> bool:
        """
        Update the status of a tracked dependency.

        Args:
            name: Name of the dependency to update
            status: New status value
            notes: Optional notes about the update

        Returns:
            True if update was successful, False if dependency not found
        """
        if name not in self._dependencies:
            logger.warning(f"Dependency not found: {name}")
            return False

        old_status = self._dependencies[name].status
        self._dependencies[name].status = status
        self._dependencies[name].notes = notes

        self._record_status_change(
            f"Updated {name}: {old_status.value} -> {status.value}", status.value
        )

        logger.info(f"Updated {name}: {old_status.value} -> {status.value}")
        return True

    def _record_status_change(self, description: str, status: str) -> None:
        """Record a status change in history."""
        self._status_history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "description": description,
                "status": status,
            }
        )

    def check_ep_ict_006_part_b_status(self) -> dict[str, Any]:
        """
        Check the current status of EP-ICT-006 Part-B.

        This method returns the overall status based on tracked dependencies:
        - Overall status is the worst status among all dependencies
        - Blockers are aggregated from all dependencies
        - Health score is calculated based on completion percentage

        Returns:
            Dict containing:
                - overall_status: str
                - dependencies_count: int
                - by_status: Dict[str, int]
                - blockers: List[str]
                - health_score: float (0.0 to 1.0)
                - last_updated: str (ISO format)
        """
        if not self._dependencies:
            return {
                "overall_status": "no_dependencies",
                "dependencies_count": 0,
                "by_status": {},
                "blockers": [],
                "health_score": 0.0,
                "last_updated": datetime.utcnow().isoformat(),
            }

        # Count dependencies by status
        by_status: dict[str, int] = {}
        all_blockers: list[str] = []

        for dep in self._dependencies.values():
            status_key = dep.status.value
            by_status[status_key] = by_status.get(status_key, 0) + 1

            if dep.status == MilestoneStatus.BLOCKED:
                all_blockers.extend(dep.blockers)

        # Determine overall status (worst case)
        if MilestoneStatus.BLOCKED in [d.status for d in self._dependencies.values()]:
            overall_status = MilestoneStatus.BLOCKED.value
        elif MilestoneStatus.IN_PROGRESS in [
            d.status for d in self._dependencies.values()
        ]:
            overall_status = MilestoneStatus.IN_PROGRESS.value
        elif all(
            d.status == MilestoneStatus.COMPLETED for d in self._dependencies.values()
        ):
            overall_status = MilestoneStatus.COMPLETED.value
        elif all(
            d.status == MilestoneStatus.PROVISIONAL_PASS
            for d in self._dependencies.values()
        ):
            overall_status = MilestoneStatus.PROVISIONAL_PASS.value
        else:
            overall_status = MilestoneStatus.PENDING.value

        # Calculate health score
        total_deps = len(self._dependencies)
        completed_deps = sum(
            1
            for d in self._dependencies.values()
            if d.status in (MilestoneStatus.COMPLETED, MilestoneStatus.PROVISIONAL_PASS)
        )
        health_score = completed_deps / total_deps if total_deps > 0 else 0.0

        return {
            "epic_id": self.epic_id,
            "part": self.part,
            "overall_status": overall_status,
            "dependencies_count": total_deps,
            "by_status": by_status,
            "blockers": all_blockers,
            "health_score": round(health_score, 2),
            "last_updated": datetime.utcnow().isoformat(),
        }

    def generate_transition_plan(self) -> TransitionPlan:
        """
        Generate a transition plan from provisional to final deployment.

        The transition plan includes:
        - Current state assessment
        - Target state definition
        - Step-by-step transition steps
        - Estimated duration
        - Prerequisites
        - Identified risks

        Returns:
            TransitionPlan object with full transition details
        """
        status = self.check_ep_ict_006_part_b_status()

        current_state = status["overall_status"]
        target_state = MilestoneStatus.COMPLETED.value

        # Generate transition steps based on current state
        steps = []

        if current_state == "no_dependencies":
            steps.append("No dependencies configured - manual planning required")
        else:
            if status["blockers"]:
                steps.append("Resolve blockers before proceeding")
                for blocker in status["blockers"]:
                    steps.append(f"  - Address: {blocker}")

            if status["by_status"].get("in_progress", 0) > 0:
                steps.append("Complete in-progress items")

            if status["by_status"].get("pending", 0) > 0:
                steps.append("Execute pending dependencies")

            steps.append("Verify all provisional_pass items")
            steps.append("Final validation and sign-off")
            steps.append("Execute production deployment")

        # Prerequisites
        prerequisites = [
            "All blockers resolved",
            "Health score above 0.8",
            "ST-ICT-033 outcome_label is provisional_pass",
            "30-second rollback capability verified",
        ]

        # Risks
        risks = [
            "Dependency delays could impact timeline",
            "Rollback might be needed if issues arise",
            "Feature flag ict:bos_choch:enabled defaults to false - ensure correct initialization",
        ]

        return TransitionPlan(
            current_state=current_state,
            target_state=target_state,
            steps=steps,
            estimated_duration_hours=4.0,
            prerequisites=prerequisites,
            risks=risks,
        )

    def generate_weekly_report(self) -> WeeklyReport:
        """
        Generate a weekly dependency status report.

        The report covers the past week and includes:
        - All tracked dependencies
        - Status changes during the week
        - Current blockers
        - Overall health assessment

        Returns:
            WeeklyReport object with complete weekly status
        """
        now = datetime.utcnow()
        week_end = now
        week_start = now - timedelta(days=7)

        # Filter status changes to last week
        recent_changes = [
            change
            for change in self._status_history
            if datetime.fromisoformat(change["timestamp"]) >= week_start
        ]

        # Get current blockers
        current_blockers = [
            blocker
            for dep in self._dependencies.values()
            if dep.status == MilestoneStatus.BLOCKED
            for blocker in dep.blockers
        ]

        return WeeklyReport(
            week_start=week_start,
            week_end=week_end,
            dependencies=list(self._dependencies.values()),
            status_changes=recent_changes,
            blockers=current_blockers,
        )

    def get_dependency(self, name: str) -> DependencyInfo | None:
        """
        Get information about a specific dependency.

        Args:
            name: Name of the dependency

        Returns:
            DependencyInfo if found, None otherwise
        """
        return self._dependencies.get(name)

    def list_dependencies(
        self, status_filter: MilestoneStatus | None = None
    ) -> list[DependencyInfo]:
        """
        List dependencies, optionally filtered by status.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of matching DependencyInfo objects
        """
        if status_filter is None:
            return list(self._dependencies.values())

        return [
            dep for dep in self._dependencies.values() if dep.status == status_filter
        ]


def create_ict_dependency_tracker() -> ICTDependencyTracker:
    """
    Factory function to create an ICTDependencyTracker instance.

    Returns:
        Configured ICTDependencyTracker instance
    """
    return ICTDependencyTracker()
