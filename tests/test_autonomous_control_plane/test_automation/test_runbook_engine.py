"""Tests for runbook engine.

For ST-CONTROL-002: Self-Healing Automation
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from autonomous_control_plane.automation.runbook_engine import (
    Runbook,
    RunbookEngine,
    RunbookExecution,
    RunbookStatus,
    RunbookStep,
    RunbookStepStatus,
)


class TestRunbookEngine:
    """Test suite for RunbookEngine."""

    @pytest.fixture
    def engine(self):
        """Create engine fixture."""
        return RunbookEngine(trading_mode="paper")

    @pytest.fixture
    def sample_step(self):
        """Create sample step fixture."""
        return RunbookStep(
            name="Test Step",
            action="test_action",
            action_type="python",
        )

    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine._trading_mode == "paper"
        assert engine._enable_approval_gates is True

    def test_create_runbook(self, engine):
        """Test creating a runbook."""
        runbook = engine.create_runbook(
            name="Test Runbook",
            description="Test description",
            tags=["test", "sample"],
        )

        assert runbook.name == "Test Runbook"
        assert runbook.description == "Test description"
        assert runbook.tags == ["test", "sample"]
        assert runbook.runbook_id in engine._runbooks

    def test_get_runbook(self, engine):
        """Test getting a runbook by ID."""
        runbook = engine.create_runbook(name="Test Runbook")

        retrieved = engine.get_runbook(runbook.runbook_id)

        assert retrieved is not None
        assert retrieved.name == "Test Runbook"

    def test_get_runbook_not_found(self, engine):
        """Test getting non-existent runbook."""
        retrieved = engine.get_runbook("non_existent_id")
        assert retrieved is None

    def test_list_runbooks(self, engine):
        """Test listing runbooks."""
        engine.create_runbook(name="Runbook 1", tags=["tag1"])
        engine.create_runbook(name="Runbook 2", tags=["tag2"])

        runbooks = engine.list_runbooks()

        assert len(runbooks) == 2

    def test_list_runbooks_filtered(self, engine):
        """Test listing runbooks with tag filter."""
        engine.create_runbook(name="Runbook 1", tags=["tag1"])
        engine.create_runbook(name="Runbook 2", tags=["tag2"])

        filtered = engine.list_runbooks(tag="tag1")

        assert len(filtered) == 1
        assert filtered[0]["name"] == "Runbook 1"

    @pytest.mark.asyncio
    async def test_execute_runbook(self, engine, sample_step):
        """Test executing a runbook."""
        runbook = engine.create_runbook(name="Test Runbook")
        runbook.add_step(sample_step)

        execution = await engine.execute_runbook(runbook)

        assert execution.runbook_id == runbook.runbook_id
        assert execution.execution_id in engine._executions

    @pytest.mark.asyncio
    async def test_execute_runbook_with_context(self, engine):
        """Test executing runbook with context."""
        runbook = engine.create_runbook(name="Test Runbook")
        runbook.add_step(
            RunbookStep(
                name="Test Step",
                action="test_action",
                action_type="python",
            )
        )

        context = {"key": "value", "number": 42}
        execution = await engine.execute_runbook(runbook, context=context)

        assert execution.context == context

    @pytest.mark.asyncio
    async def test_get_execution_status(self, engine, sample_step):
        """Test getting execution status."""
        runbook = engine.create_runbook(name="Test Runbook")
        runbook.add_step(sample_step)

        execution = await engine.execute_runbook(runbook)

        # Wait for execution to complete
        await asyncio.sleep(0.5)

        status = engine.get_execution_status(execution.execution_id)

        assert status is not None
        assert status["runbook_id"] == runbook.runbook_id
        assert "steps" in status

    def test_get_execution_status_not_found(self, engine):
        """Test getting status for non-existent execution."""
        status = engine.get_execution_status("non_existent_id")
        assert status is None

    @pytest.mark.asyncio
    async def test_approve_step(self, engine):
        """Test approving a step."""
        runbook = engine.create_runbook(name="Test Runbook")
        step = runbook.add_step(
            RunbookStep(
                name="Approval Step",
                action="test_action",
                action_type="python",
                requires_approval=True,
            )
        )

        execution = await engine.execute_runbook(runbook)

        # Approve step
        result = engine.approve_step(
            execution.execution_id,
            step.step_id,
            approved_by="test_user",
        )

        assert result is True
        assert step.approved_by == "test_user"

    @pytest.mark.asyncio
    async def test_reject_step(self, engine):
        """Test rejecting a step."""
        runbook = engine.create_runbook(name="Test Runbook")
        step = runbook.add_step(
            RunbookStep(
                name="Approval Step",
                action="test_action",
                action_type="python",
                requires_approval=True,
            )
        )

        execution = await engine.execute_runbook(runbook)

        # Reject step
        result = engine.reject_step(
            execution.execution_id,
            step.step_id,
            rejected_by="test_user",
            reason="Test rejection",
        )

        assert result is True
        assert step.status == RunbookStepStatus.FAILED

    def test_get_pending_approvals_empty(self, engine):
        """Test getting pending approvals when none exist."""
        pending = engine.get_pending_approvals()
        assert pending == []

    def test_get_status(self, engine):
        """Test getting engine status."""
        status = engine.get_status()

        assert "trading_mode" in status
        assert "runbooks" in status
        assert "executions" in status
        assert "pending_approvals" in status
        assert "stats" in status
        assert "action_handlers" in status

    def test_stats_tracking(self, engine):
        """Test statistics are tracked."""
        initial_stats = engine._stats.copy()

        engine.create_runbook(name="Test Runbook")

        assert engine._stats["runbooks_created"] > initial_stats["runbooks_created"]


class TestRunbook:
    """Test suite for Runbook."""

    def test_runbook_creation(self):
        """Test runbook creation."""
        runbook = Runbook(
            name="Test Runbook",
            description="Test description",
            tags=["test"],
        )

        assert runbook.name == "Test Runbook"
        assert runbook.description == "Test description"
        assert runbook.tags == ["test"]
        assert runbook.version == "1.0.0"
        assert runbook.auto_rollback is True

    def test_add_step(self):
        """Test adding steps to runbook."""
        runbook = Runbook(name="Test Runbook")

        step = runbook.add_step(
            RunbookStep(
                name="Step 1",
                action="action1",
                action_type="python",
            )
        )

        assert len(runbook.steps) == 1
        assert runbook.steps[0].name == "Step 1"
        assert step.step_id is not None

    def test_add_multiple_steps(self):
        """Test adding multiple steps."""
        runbook = Runbook(name="Test Runbook")

        runbook.add_step(RunbookStep(name="Step 1", action="a1", action_type="python"))
        runbook.add_step(RunbookStep(name="Step 2", action="a2", action_type="shell"))
        runbook.add_step(RunbookStep(name="Step 3", action="a3", action_type="api"))

        assert len(runbook.steps) == 3

    def test_to_dict(self):
        """Test runbook serialization."""
        runbook = Runbook(
            name="Test Runbook",
            description="Test",
            tags=["test"],
        )
        runbook.add_step(RunbookStep(name="Step 1", action="a1", action_type="python"))

        d = runbook.to_dict()

        assert d["name"] == "Test Runbook"
        assert d["description"] == "Test"
        assert d["tags"] == ["test"]
        assert len(d["steps"]) == 1


class TestRunbookStep:
    """Test suite for RunbookStep."""

    def test_step_creation(self):
        """Test step creation."""
        step = RunbookStep(
            name="Test Step",
            description="Test description",
            action="test_action",
            action_type="python",
            timeout_seconds=30.0,
        )

        assert step.name == "Test Step"
        assert step.description == "Test description"
        assert step.action == "test_action"
        assert step.action_type == "python"
        assert step.timeout_seconds == 30.0
        assert step.status == RunbookStepStatus.PENDING

    def test_step_with_approval(self):
        """Test step requiring approval."""
        step = RunbookStep(
            name="Approval Step",
            action="action",
            action_type="python",
            requires_approval=True,
            approval_timeout_seconds=600.0,
        )

        assert step.requires_approval is True
        assert step.approval_timeout_seconds == 600.0

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = RunbookStep(
            name="Dependent Step",
            action="action",
            action_type="python",
            depends_on=["step1", "step2"],
        )

        assert step.depends_on == ["step1", "step2"]

    def test_step_with_retry(self):
        """Test step with retry configuration."""
        step = RunbookStep(
            name="Retry Step",
            action="action",
            action_type="python",
            max_retries=3,
        )

        assert step.max_retries == 3
        assert step.retry_count == 0

    def test_step_to_dict(self):
        """Test step serialization."""
        step = RunbookStep(
            name="Test Step",
            action="test_action",
            action_type="python",
        )

        d = step.to_dict()

        assert d["name"] == "Test Step"
        assert d["action"] == "test_action"
        assert d["action_type"] == "python"
        assert d["status"] == "pending"


class TestRunbookExecution:
    """Test suite for RunbookExecution."""

    def test_execution_creation(self):
        """Test execution creation."""
        execution = RunbookExecution(
            runbook_id="rb123",
            runbook_name="Test Runbook",
            triggered_by="test_user",
            trading_mode="live",
        )

        assert execution.runbook_id == "rb123"
        assert execution.runbook_name == "Test Runbook"
        assert execution.triggered_by == "test_user"
        assert execution.trading_mode == "live"
        assert execution.status == RunbookStatus.PENDING

    def test_execution_with_context(self):
        """Test execution with context."""
        context = {"key": "value"}
        execution = RunbookExecution(
            runbook_id="rb123",
            runbook_name="Test",
            context=context,
        )

        assert execution.context == context

    def test_to_dict(self):
        """Test execution serialization."""
        execution = RunbookExecution(
            runbook_id="rb123",
            runbook_name="Test Runbook",
        )

        d = execution.to_dict()

        assert d["runbook_id"] == "rb123"
        assert d["runbook_name"] == "Test Runbook"
        assert d["status"] == "pending"
        assert "execution_id" in d
