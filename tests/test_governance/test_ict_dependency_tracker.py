"""
Tests for ICT Dependency Tracker (ST-ICT-037)

These tests verify the dependency tracking capabilities for EP-ICT-006 Part-B.
"""

from datetime import datetime

import pytest
from src.governance.dependency.ict_dependency_tracker import (
    DependencyInfo,
    ICTDependencyTracker,
    MilestoneStatus,
    TransitionPlan,
    WeeklyReport,
    create_ict_dependency_tracker,
)


class TestMilestoneStatus:
    """Tests for the MilestoneStatus enum."""

    def test_all_statuses_defined(self):
        """Test all milestone statuses are defined."""
        assert MilestoneStatus.PENDING.value == "pending"
        assert MilestoneStatus.IN_PROGRESS.value == "in_progress"
        assert MilestoneStatus.PROVISIONAL_PASS.value == "provisional_pass"
        assert MilestoneStatus.COMPLETED.value == "completed"
        assert MilestoneStatus.BLOCKED.value == "blocked"


class TestDependencyInfo:
    """Tests for the DependencyInfo dataclass."""

    def test_create_dependency_info(self):
        """Test creating a DependencyInfo object."""
        dep = DependencyInfo(
            name="Test Dependency", status=MilestoneStatus.PENDING, owner="team-a"
        )

        assert dep.name == "Test Dependency"
        assert dep.status == MilestoneStatus.PENDING
        assert dep.owner == "team-a"
        assert dep.blockers == []

    def test_dependency_info_with_blockers(self):
        """Test creating a DependencyInfo with blockers."""
        blockers = ["Missing approval", "Resource constraint"]
        dep = DependencyInfo(
            name="Blocked Dependency",
            status=MilestoneStatus.BLOCKED,
            owner="team-b",
            blockers=blockers,
        )

        assert dep.status == MilestoneStatus.BLOCKED
        assert len(dep.blockers) == 2


class TestTransitionPlan:
    """Tests for the TransitionPlan dataclass."""

    def test_create_transition_plan(self):
        """Test creating a TransitionPlan."""
        plan = TransitionPlan(
            current_state="in_progress",
            target_state="completed",
            steps=["Step 1", "Step 2"],
            estimated_duration_hours=4.0,
            prerequisites=["Prereq 1"],
            risks=["Risk 1"],
        )

        assert plan.current_state == "in_progress"
        assert plan.target_state == "completed"
        assert len(plan.steps) == 2
        assert plan.estimated_duration_hours == 4.0


class TestWeeklyReport:
    """Tests for the WeeklyReport dataclass."""

    def test_create_weekly_report(self):
        """Test creating a WeeklyReport."""
        report = WeeklyReport(
            week_start=datetime(2026, 3, 19),
            week_end=datetime(2026, 3, 26),
            dependencies=[],
            status_changes=[],
            blockers=[],
        )

        assert report.week_start < report.week_end
        assert isinstance(report.generated_at, datetime)


class TestICTDependencyTracker:
    """Tests for the ICTDependencyTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh tracker instance."""
        return ICTDependencyTracker()

    def test_init_default_values(self, tracker):
        """Test initialization with default values."""
        assert tracker.epic_id == "EP-ICT-006"
        assert tracker.part == "Part-B"
        assert tracker._dependencies == {}

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        tracker = ICTDependencyTracker(epic_id="EP-ICT-007", part="Part-A")

        assert tracker.epic_id == "EP-ICT-007"
        assert tracker.part == "Part-A"

    def test_add_dependency(self, tracker):
        """Test adding a dependency."""
        dep = DependencyInfo(
            name="Test Dep", status=MilestoneStatus.PENDING, owner="team-a"
        )

        tracker.add_dependency(dep)

        assert "Test Dep" in tracker._dependencies
        assert tracker._dependencies["Test Dep"].status == MilestoneStatus.PENDING

    def test_update_dependency_status(self, tracker):
        """Test updating dependency status."""
        dep = DependencyInfo(
            name="Test Dep", status=MilestoneStatus.PENDING, owner="team-a"
        )
        tracker.add_dependency(dep)

        result = tracker.update_dependency_status(
            "Test Dep", MilestoneStatus.IN_PROGRESS, "Started work"
        )

        assert result is True
        assert tracker._dependencies["Test Dep"].status == MilestoneStatus.IN_PROGRESS
        assert tracker._dependencies["Test Dep"].notes == "Started work"

    def test_update_nonexistent_dependency(self, tracker):
        """Test updating a dependency that doesn't exist."""
        result = tracker.update_dependency_status(
            "Nonexistent", MilestoneStatus.COMPLETED
        )

        assert result is False

    def test_check_ep_ict_006_part_b_status_no_dependencies(self, tracker):
        """Test status check with no dependencies."""
        status = tracker.check_ep_ict_006_part_b_status()

        assert status["overall_status"] == "no_dependencies"
        assert status["dependencies_count"] == 0
        assert status["health_score"] == 0.0

    def test_check_ep_ict_006_part_b_status_mixed(self, tracker):
        """Test status check with mixed dependency statuses."""
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 1", status=MilestoneStatus.COMPLETED, owner="team-a"
            )
        )
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 2", status=MilestoneStatus.IN_PROGRESS, owner="team-b"
            )
        )
        tracker.add_dependency(
            DependencyInfo(name="Dep 3", status=MilestoneStatus.PENDING, owner="team-c")
        )

        status = tracker.check_ep_ict_006_part_b_status()

        assert status["dependencies_count"] == 3
        assert status["by_status"]["completed"] == 1
        assert status["by_status"]["in_progress"] == 1
        assert status["by_status"]["pending"] == 1
        assert status["overall_status"] == "in_progress"

    def test_check_ep_ict_006_part_b_status_all_blocked(self, tracker):
        """Test status check when all dependencies are blocked."""
        tracker.add_dependency(
            DependencyInfo(
                name="Blocked Dep",
                status=MilestoneStatus.BLOCKED,
                owner="team-a",
                blockers=["Cannot proceed"],
            )
        )

        status = tracker.check_ep_ict_006_part_b_status()

        assert status["overall_status"] == "blocked"
        assert "Cannot proceed" in status["blockers"]

    def test_check_ep_ict_006_part_b_status_health_score(self, tracker):
        """Test health score calculation."""
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 1", status=MilestoneStatus.COMPLETED, owner="team-a"
            )
        )
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 2", status=MilestoneStatus.PROVISIONAL_PASS, owner="team-b"
            )
        )
        tracker.add_dependency(
            DependencyInfo(name="Dep 3", status=MilestoneStatus.PENDING, owner="team-c")
        )
        tracker.add_dependency(
            DependencyInfo(name="Dep 4", status=MilestoneStatus.PENDING, owner="team-d")
        )

        status = tracker.check_ep_ict_006_part_b_status()

        # 2 completed/provisional_pass out of 4 = 0.5
        assert status["health_score"] == 0.5

    def test_generate_transition_plan_no_dependencies(self, tracker):
        """Test transition plan with no dependencies."""
        plan = tracker.generate_transition_plan()

        assert plan.current_state == "no_dependencies"
        assert len(plan.steps) == 1

    def test_generate_transition_plan_with_blockers(self, tracker):
        """Test transition plan with blockers."""
        tracker.add_dependency(
            DependencyInfo(
                name="Blocked Dep",
                status=MilestoneStatus.BLOCKED,
                owner="team-a",
                blockers=["Approval pending"],
            )
        )

        plan = tracker.generate_transition_plan()

        assert "Resolve blockers" in plan.steps[0]
        assert len(plan.prerequisites) > 0
        assert len(plan.risks) > 0

    def test_generate_weekly_report(self, tracker):
        """Test weekly report generation."""
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 1", status=MilestoneStatus.COMPLETED, owner="team-a"
            )
        )
        tracker.update_dependency_status("Dep 1", MilestoneStatus.IN_PROGRESS)

        report = tracker.generate_weekly_report()

        assert isinstance(report, WeeklyReport)
        assert report.week_start < report.week_end
        assert len(report.dependencies) == 1
        assert len(report.status_changes) > 0

    def test_get_dependency(self, tracker):
        """Test getting a specific dependency."""
        tracker.add_dependency(
            DependencyInfo(
                name="Test Dep", status=MilestoneStatus.PENDING, owner="team-a"
            )
        )

        dep = tracker.get_dependency("Test Dep")

        assert dep is not None
        assert dep.name == "Test Dep"

    def test_get_nonexistent_dependency(self, tracker):
        """Test getting a dependency that doesn't exist."""
        dep = tracker.get_dependency("Nonexistent")

        assert dep is None

    def test_list_dependencies_no_filter(self, tracker):
        """Test listing all dependencies."""
        tracker.add_dependency(
            DependencyInfo(
                name="Dep 1", status=MilestoneStatus.COMPLETED, owner="team-a"
            )
        )
        tracker.add_dependency(
            DependencyInfo(name="Dep 2", status=MilestoneStatus.PENDING, owner="team-b")
        )

        deps = tracker.list_dependencies()

        assert len(deps) == 2

    def test_list_dependencies_with_filter(self, tracker):
        """Test listing dependencies with status filter."""
        tracker.add_dependency(
            DependencyInfo(
                name="Completed Dep", status=MilestoneStatus.COMPLETED, owner="team-a"
            )
        )
        tracker.add_dependency(
            DependencyInfo(
                name="Pending Dep", status=MilestoneStatus.PENDING, owner="team-b"
            )
        )

        completed = tracker.list_dependencies(MilestoneStatus.COMPLETED)
        pending = tracker.list_dependencies(MilestoneStatus.PENDING)

        assert len(completed) == 1
        assert len(pending) == 1
        assert completed[0].name == "Completed Dep"

    def test_create_ict_dependency_tracker_factory(self):
        """Test factory function creates correct instance."""
        tracker = create_ict_dependency_tracker()

        assert isinstance(tracker, ICTDependencyTracker)
        assert tracker.epic_id == "EP-ICT-006"


class TestDependencyTrackerIntegration:
    """Integration tests for dependency tracker."""

    def test_full_workflow(self):
        """Test complete dependency tracking workflow."""
        tracker = ICTDependencyTracker()

        # Add dependencies
        tracker.add_dependency(
            DependencyInfo(
                name="Infrastructure",
                status=MilestoneStatus.COMPLETED,
                owner="infra-team",
            )
        )
        tracker.add_dependency(
            DependencyInfo(
                name="Feature Development",
                status=MilestoneStatus.IN_PROGRESS,
                owner="dev-team",
            )
        )
        tracker.add_dependency(
            DependencyInfo(
                name="Testing", status=MilestoneStatus.PENDING, owner="qa-team"
            )
        )

        # Check status
        status = tracker.check_ep_ict_006_part_b_status()
        assert status["dependencies_count"] == 3
        assert status["overall_status"] == "in_progress"

        # Generate transition plan
        plan = tracker.generate_transition_plan()
        assert plan.target_state == "completed"
        assert len(plan.steps) > 0

        # Generate weekly report
        report = tracker.generate_weekly_report()
        assert len(report.dependencies) == 3

        # Update status
        tracker.update_dependency_status(
            "Feature Development", MilestoneStatus.COMPLETED
        )

        # Verify update
        updated_status = tracker.check_ep_ict_006_part_b_status()
        assert updated_status["by_status"]["completed"] == 2
