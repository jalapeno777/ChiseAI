"""Unit tests for Rollback Coordinator.

Tests for ST-NS-042: Rollback Coordinator with Pre-flight Validation

Acceptance Criteria:
1. Pre-condition validation
2. Step-wise rollback with verification
3. Automatic rollback on canary failure
4. Rollback <=60 seconds
5. Post-rollback health checks
6. Full audit trail
7. Emergency bypass (force=true)
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.components.rollback_coordinator import (
    InMemoryRollbackStore,
    PostRollbackHealthChecker,
    PreFlightValidator,
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.incidents import IncidentEvent
from src.autonomous_control_plane.models.rollback import (
    HealthCheck,
    HealthCheckStatus,
    RollbackMetrics,
    RollbackOperation,
    RollbackStatus,
    RollbackStep,
    RollbackStepStatus,
    ValidationCheck,
    ValidationCheckStatus,
    ValidationResult,
)


class TestPreFlightValidator:
    """Tests for PreFlightValidator."""

    @pytest.mark.asyncio
    async def test_validate_passes_all_checks(self):
        """AC1: Pre-condition validation - All checks pass before rollback."""
        validator = PreFlightValidator()
        result = await validator.validate("v1.2.3")

        assert result.valid is True
        assert len(result.checks) == 5  # All default checkers registered
        assert len(result.failed_checks) == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_with_force_skips_checks(self):
        """AC7: Emergency bypass - Validation skipped when force=true."""
        validator = PreFlightValidator()
        result = await validator.validate("v1.2.3", force=True)

        assert result.valid is True
        assert all(c.status == ValidationCheckStatus.SKIPPED for c in result.checks)

    @pytest.mark.asyncio
    async def test_validate_with_failing_check(self):
        """AC1: Pre-condition validation fails when check fails."""
        validator = PreFlightValidator()

        # Register a failing checker
        def failing_checker():
            check = ValidationCheck(name="failing", description="Always fails")
            check.mark_fail("Intentional failure")
            return check

        validator.register_checker("failing", failing_checker)

        result = await validator.validate("v1.2.3")

        assert result.valid is False
        assert len(result.failed_checks) == 1
        assert "Intentional failure" in result.errors

    @pytest.mark.asyncio
    async def test_validate_custom_checker(self):
        """Test custom checker registration."""
        validator = PreFlightValidator()

        def custom_checker():
            check = ValidationCheck(name="custom", description="Custom check")
            check.mark_pass("Custom check passed")
            return check

        validator.register_checker("custom", custom_checker)

        result = await validator.validate("v1.2.3")

        custom_check = next((c for c in result.checks if c.name == "custom"), None)
        assert custom_check is not None
        assert custom_check.status == ValidationCheckStatus.PASS


class TestPostRollbackHealthChecker:
    """Tests for PostRollbackHealthChecker."""

    @pytest.mark.asyncio
    async def test_verify_passes_all_checks(self):
        """AC5: Post-rollback health checks - Health verification after rollback."""
        checker = PostRollbackHealthChecker()
        result = await checker.verify("v1.2.3")

        assert result.healthy is True
        assert len(result.checks) == 4  # All default checkers registered
        assert len(result.failed_checks) == 0

    @pytest.mark.asyncio
    async def test_verify_with_warning(self):
        """AC5: Health check with warnings still passes."""
        checker = PostRollbackHealthChecker()

        def warning_checker():
            check = HealthCheck(name="warning", description="Warning check")
            check.mark_warning("Performance slightly degraded")
            return check

        checker.register_checker("warning", warning_checker)

        result = await checker.verify("v1.2.3")

        warning_check = next((c for c in result.checks if c.name == "warning"), None)
        assert warning_check is not None
        assert warning_check.status == HealthCheckStatus.WARNING
        assert result.healthy is True  # Warnings don't fail health check

    @pytest.mark.asyncio
    async def test_verify_with_failing_check(self):
        """AC5: Health check fails when critical check fails."""
        checker = PostRollbackHealthChecker()

        def failing_checker():
            check = HealthCheck(name="critical", description="Critical check")
            check.mark_fail("Critical service down")
            return check

        checker.register_checker("failing", failing_checker)

        result = await checker.verify("v1.2.3")

        assert result.healthy is False
        assert len(result.failed_checks) == 1


class TestRollbackCoordinator:
    """Tests for RollbackCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create a fresh coordinator for each test."""
        return RollbackCoordinator()

    @pytest.fixture
    def coordinator_with_incident_manager(self):
        """Create a coordinator with mock incident manager."""
        mock_incident_manager = AsyncMock(spec=IncidentManager)
        return RollbackCoordinator(incident_manager=mock_incident_manager)

    @pytest.mark.asyncio
    async def test_create_rollback_operation(self, coordinator):
        """Test creating a rollback operation."""
        operation = await coordinator.create_rollback_operation(
            target_state="v1.2.3",
            initiated_by="test",
        )

        assert operation.target_state == "v1.2.3"
        assert operation.initiated_by == "test"
        assert operation.status == RollbackStatus.PENDING
        assert len(operation.steps) == 5  # Default steps
        assert operation.steps[0].order == 1

    @pytest.mark.asyncio
    async def test_create_rollback_with_custom_steps(self, coordinator):
        """Test creating rollback with custom steps."""
        custom_steps = [
            {"name": "step1", "description": "First step", "action": "action1"},
            {"name": "step2", "description": "Second step", "action": "action2"},
        ]

        operation = await coordinator.create_rollback_operation(
            target_state="v1.2.3",
            steps=custom_steps,
        )

        assert len(operation.steps) == 2
        assert operation.steps[0].name == "step1"
        assert operation.steps[1].name == "step2"

    @pytest.mark.asyncio
    async def test_validate_rollback(self, coordinator):
        """AC1: Pre-condition validation - validate_rollback method."""
        result = await coordinator.validate_rollback("v1.2.3")

        assert isinstance(result, ValidationResult)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_execute_rollback_success(self, coordinator):
        """AC2: Step-wise rollback with verification - Successful execution."""
        operation = await coordinator.execute_rollback(
            target_state="v1.2.3",
            initiated_by="test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.duration_seconds >= 0
        assert len(operation.completed_steps) == 5
        assert operation.validation_result is not None
        assert operation.post_rollback_health is not None
        assert len(operation.audit_log) > 0

    @pytest.mark.asyncio
    async def test_execute_rollback_with_force_bypass(self, coordinator):
        """AC7: Emergency bypass - Validation skipped when force=true."""
        operation = await coordinator.execute_rollback(
            target_state="v1.2.3",
            force=True,
            initiated_by="test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.force is True
        assert operation.validation_result is None  # Skipped

        # Check audit log shows validation was skipped
        skip_entry = next(
            (e for e in operation.audit_log if "skipped" in e.message.lower()),
            None,
        )
        assert skip_entry is not None

    @pytest.mark.asyncio
    async def test_emergency_rollback(self, coordinator):
        """AC7: Emergency rollback bypasses validation."""
        operation = await coordinator.emergency_rollback(
            target_state="v1.2.3",
            initiated_by="emergency",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.force is True
        assert operation.initiated_by == "emergency"

    @pytest.mark.asyncio
    async def test_rollback_timing_within_sla(self, coordinator):
        """AC4: Rollback <=60 seconds - Timing test verifies SLA."""
        start_time = time.time()
        operation = await coordinator.execute_rollback(target_state="v1.2.3")
        elapsed = time.time() - start_time

        assert operation.status == RollbackStatus.COMPLETED
        assert elapsed < 60.0, f"Rollback took {elapsed}s, exceeding 60s SLA"
        assert operation.duration_seconds < 60.0

    @pytest.mark.asyncio
    async def test_rollback_step_execution(self, coordinator):
        """AC2: Step-wise rollback - Each step verified before next."""
        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        # All steps should be completed in order
        for i, step in enumerate(operation.steps):
            assert step.status == RollbackStepStatus.COMPLETED
            assert step.order == i + 1
            assert step.started_at is not None
            assert step.completed_at is not None

    @pytest.mark.asyncio
    async def test_rollback_audit_trail(self, coordinator):
        """AC6: Full audit trail - All operations logged."""
        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        # Should have audit entries for:
        # - Operation started
        # - Pre-flight validation
        # - Each step start/complete
        # - Post-rollback verification
        # - Operation completed
        assert len(operation.audit_log) >= 7

        # Check key entries exist
        messages = [e.message for e in operation.audit_log]
        assert any("validation" in m.lower() for m in messages)
        assert any("completed" in m.lower() for m in messages)

    @pytest.mark.asyncio
    async def test_rollback_with_step_failure(self, coordinator):
        """Test rollback fails when a step fails."""
        # Register a failing step handler
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Restore failed"},
        )

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.FAILED
        assert operation.error_message is not None
        assert "restore_previous_state" in operation.error_message.lower()

    @pytest.mark.asyncio
    async def test_rollback_creates_incident_on_failure(
        self, coordinator_with_incident_manager
    ):
        """Test that rollback failure creates P1 incident."""
        coordinator = coordinator_with_incident_manager

        # Register a failing step handler
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Restore failed"},
        )

        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        assert operation.status == RollbackStatus.FAILED
        # Verify incident manager was called
        coordinator._incident_manager.create_incident.assert_called_once()
        call_args = coordinator._incident_manager.create_incident.call_args[0][0]
        assert isinstance(call_args, IncidentEvent)
        assert call_args.event_type == "rollback_failure"

    @pytest.mark.asyncio
    async def test_handle_canary_gate_failure(self, coordinator):
        """AC3: Automatic rollback on canary failure."""
        operation = await coordinator.handle_canary_gate_failure(
            canary_id="canary-123",
            target_state="v1.2.3",
            failure_reason="Error rate exceeded threshold",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.initiated_by == "canary_gate:canary-123"
        assert operation.metadata.get("auto_triggered") is True
        assert operation.metadata.get("canary_id") == "canary-123"

    @pytest.mark.asyncio
    async def test_get_operation(self, coordinator):
        """Test retrieving operation by ID."""
        operation = await coordinator.execute_rollback(target_state="v1.2.3")

        retrieved = await coordinator.get_operation(operation.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id

    @pytest.mark.asyncio
    async def test_list_operations(self, coordinator):
        """Test listing operations."""
        # Create multiple operations
        op1 = await coordinator.execute_rollback(target_state="v1.2.3")
        op2 = await coordinator.execute_rollback(target_state="v1.2.2")

        operations = await coordinator.list_operations()

        assert len(operations) == 2
        assert all(isinstance(o, RollbackOperation) for o in operations)

    @pytest.mark.asyncio
    async def test_list_operations_with_status_filter(self, coordinator):
        """Test listing operations with status filter."""
        await coordinator.execute_rollback(target_state="v1.2.3")

        # Register failing handler to create a failed operation
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Failed"},
        )
        await coordinator.execute_rollback(target_state="v1.2.2")

        completed = await coordinator.list_operations(status=RollbackStatus.COMPLETED)
        failed = await coordinator.list_operations(status=RollbackStatus.FAILED)

        assert len(completed) == 1
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_get_history(self, coordinator):
        """Test getting rollback history."""
        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.2")

        history_v123 = await coordinator.get_history(target_state="v1.2.3")
        all_history = await coordinator.get_history()

        assert len(history_v123) == 2
        assert len(all_history) == 3

    @pytest.mark.asyncio
    async def test_get_metrics(self, coordinator):
        """Test getting rollback metrics."""
        # Execute some rollbacks
        await coordinator.execute_rollback(target_state="v1.2.3")
        await coordinator.execute_rollback(target_state="v1.2.3")

        # Register failing handler
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Failed"},
        )
        await coordinator.execute_rollback(target_state="v1.2.2")

        metrics = await coordinator.get_metrics()

        assert isinstance(metrics, RollbackMetrics)
        assert metrics.total_operations == 3
        assert metrics.successful == 2
        assert metrics.failed == 1

    @pytest.mark.asyncio
    async def test_callback_registration(self, coordinator):
        """Test callback registration and invocation."""
        started_callback = AsyncMock()
        completed_callback = AsyncMock()
        failed_callback = AsyncMock()

        coordinator.on_rollback_started(started_callback)
        coordinator.on_rollback_completed(completed_callback)
        coordinator.on_rollback_failed(failed_callback)

        await coordinator.execute_rollback(target_state="v1.2.3")

        started_callback.assert_called_once()
        completed_callback.assert_called_once()
        failed_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_on_failure(self, coordinator):
        """Test failure callback invocation."""
        failed_callback = AsyncMock()
        coordinator.on_rollback_failed(failed_callback)

        # Register failing handler
        coordinator.register_step_handler(
            "restore_state",
            lambda: {"success": False, "error": "Failed"},
        )

        await coordinator.execute_rollback(target_state="v1.2.3")

        failed_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_canary_gate_failure_callback(self, coordinator):
        """Test canary gate failure callback."""
        canary_callback = AsyncMock()
        coordinator.on_canary_gate_failure(canary_callback)

        await coordinator.handle_canary_gate_failure(
            canary_id="canary-123",
            target_state="v1.2.3",
            failure_reason="Test",
        )

        canary_callback.assert_called_once_with("canary-123", "v1.2.3", "Test")


class TestRollbackOperation:
    """Tests for RollbackOperation model."""

    def test_add_step(self):
        """Test adding steps to operation."""
        operation = RollbackOperation(target_state="v1.2.3")

        step1 = RollbackStep(name="step1", description="Step 1", action="action1")
        step2 = RollbackStep(name="step2", description="Step 2", action="action2")

        operation.add_step(step1)
        operation.add_step(step2)

        assert len(operation.steps) == 2
        assert step1.order == 1
        assert step2.order == 2

    def test_add_audit_entry(self):
        """Test adding audit log entries."""
        operation = RollbackOperation(target_state="v1.2.3")

        operation.add_audit_entry("Test message", level="INFO", actor="test")
        operation.add_audit_entry("Error message", level="ERROR")

        assert len(operation.audit_log) == 2
        assert operation.audit_log[0].message == "Test message"
        assert operation.audit_log[0].actor == "test"
        assert operation.audit_log[1].level == "ERROR"

    def test_mark_completed(self):
        """Test marking operation as completed."""
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_started()
        operation.mark_completed()

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.completed_at is not None
        assert operation.duration_seconds >= 0
        assert any("completed" in e.message.lower() for e in operation.audit_log)

    def test_mark_failed(self):
        """Test marking operation as failed."""
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_started()
        operation.mark_failed("Something went wrong")

        assert operation.status == RollbackStatus.FAILED
        assert operation.error_message == "Something went wrong"
        assert operation.completed_at is not None
        assert any("failed" in e.message.lower() for e in operation.audit_log)

    def test_current_step(self):
        """Test getting current step."""
        operation = RollbackOperation(target_state="v1.2.3")

        step1 = RollbackStep(name="step1", description="Step 1", action="action1")
        step2 = RollbackStep(name="step2", description="Step 2", action="action2")

        operation.add_step(step1)
        operation.add_step(step2)

        assert operation.current_step is None

        step1.mark_in_progress()
        assert operation.current_step == step1

    def test_completed_steps(self):
        """Test getting completed steps."""
        operation = RollbackOperation(target_state="v1.2.3")

        step1 = RollbackStep(name="step1", description="Step 1", action="action1")
        step2 = RollbackStep(name="step2", description="Step 2", action="action2")
        step3 = RollbackStep(name="step3", description="Step 3", action="action3")

        operation.add_step(step1)
        operation.add_step(step2)
        operation.add_step(step3)

        step1.mark_completed({"success": True})
        step2.mark_completed({"success": True})

        completed = operation.completed_steps
        assert len(completed) == 2
        assert step1 in completed
        assert step2 in completed

    def test_to_dict(self):
        """Test serialization to dictionary."""
        operation = RollbackOperation(
            target_state="v1.2.3",
            initiated_by="test",
            force=False,
        )

        step = RollbackStep(name="step1", description="Step 1", action="action1")
        operation.add_step(step)
        operation.mark_started()
        operation.mark_completed()

        data = operation.to_dict()

        assert data["target_state"] == "v1.2.3"
        assert data["initiated_by"] == "test"
        assert data["force"] is False
        assert data["status"] == "completed"
        assert len(data["steps"]) == 1
        assert len(data["audit_log"]) > 0


class TestRollbackStep:
    """Tests for RollbackStep model."""

    def test_mark_in_progress(self):
        """Test marking step as in progress."""
        step = RollbackStep(name="test", description="Test", action="action")
        step.mark_in_progress()

        assert step.status == RollbackStepStatus.IN_PROGRESS
        assert step.started_at is not None

    def test_mark_completed(self):
        """Test marking step as completed."""
        step = RollbackStep(name="test", description="Test", action="action")
        step.mark_in_progress()
        step.mark_completed({"result": "ok"})

        assert step.status == RollbackStepStatus.COMPLETED
        assert step.completed_at is not None
        assert step.execution_result == {"result": "ok"}

    def test_mark_failed(self):
        """Test marking step as failed."""
        step = RollbackStep(name="test", description="Test", action="action")
        step.mark_in_progress()
        step.mark_failed("Something broke", {"error": "details"})

        assert step.status == RollbackStepStatus.FAILED
        assert step.error_message == "Something broke"
        assert step.execution_result == {"error": "details"}

    def test_duration_seconds(self):
        """Test duration calculation."""
        step = RollbackStep(name="test", description="Test", action="action")
        assert step.duration_seconds == 0.0

        step.mark_in_progress()
        # Small sleep to ensure duration > 0
        import time

        time.sleep(0.01)

        assert step.duration_seconds > 0.0


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_all_passed(self):
        """Test all_passed property."""
        result = ValidationResult()

        check1 = ValidationCheck(name="c1", description="Check 1")
        check1.mark_pass()
        check2 = ValidationCheck(name="c2", description="Check 2")
        check2.mark_pass()

        result.add_check(check1)
        result.add_check(check2)

        assert result.all_passed is True

    def test_all_passed_with_skipped(self):
        """Test all_passed with skipped checks."""
        result = ValidationResult()

        check1 = ValidationCheck(name="c1", description="Check 1")
        check1.mark_pass()
        check2 = ValidationCheck(name="c2", description="Check 2")
        check2.mark_skipped()

        result.add_check(check1)
        result.add_check(check2)

        assert result.all_passed is True

    def test_all_passed_with_failure(self):
        """Test all_passed with failing check."""
        result = ValidationResult()

        check1 = ValidationCheck(name="c1", description="Check 1")
        check1.mark_pass()
        check2 = ValidationCheck(name="c2", description="Check 2")
        check2.mark_fail("Failed")

        result.add_check(check1)
        result.add_check(check2)

        assert result.all_passed is False

    def test_finalize(self):
        """Test finalizing validation result."""
        result = ValidationResult()
        result.executed_at = datetime.now(UTC)

        check1 = ValidationCheck(name="c1", description="Check 1")
        check1.mark_pass()
        check2 = ValidationCheck(name="c2", description="Check 2")
        check2.mark_fail("Failed")

        result.add_check(check1)
        result.add_check(check2)

        result.finalize()

        assert result.valid is False
        assert len(result.errors) == 1
        assert "Failed" in result.errors
        assert result.duration_seconds >= 0


class TestInMemoryRollbackStore:
    """Tests for InMemoryRollbackStore."""

    @pytest.mark.asyncio
    async def test_save_and_get(self):
        """Test saving and retrieving operation."""
        store = InMemoryRollbackStore()
        operation = RollbackOperation(target_state="v1.2.3")

        await store.save(operation)
        retrieved = await store.get(operation.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """Test getting non-existent operation."""
        store = InMemoryRollbackStore()

        retrieved = await store.get("non-existent")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list(self):
        """Test listing operations."""
        store = InMemoryRollbackStore()

        op1 = RollbackOperation(target_state="v1.2.3")
        op2 = RollbackOperation(target_state="v1.2.2")

        await store.save(op1)
        await store.save(op2)

        operations = await store.list()

        assert len(operations) == 2

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        """Test listing with status filter."""
        store = InMemoryRollbackStore()

        op1 = RollbackOperation(target_state="v1.2.3")
        op1.mark_started()
        op1.mark_completed()

        op2 = RollbackOperation(target_state="v1.2.2")
        op2.mark_started()
        op2.mark_failed("Failed")

        await store.save(op1)
        await store.save(op2)

        completed = await store.list(status=RollbackStatus.COMPLETED)
        failed = await store.list(status=RollbackStatus.FAILED)

        assert len(completed) == 1
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        """Test list pagination."""
        store = InMemoryRollbackStore()

        for i in range(10):
            op = RollbackOperation(target_state=f"v1.2.{i}")
            await store.save(op)

        first_page = await store.list(limit=5, offset=0)
        second_page = await store.list(limit=5, offset=5)

        assert len(first_page) == 5
        assert len(second_page) == 5

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting operation."""
        store = InMemoryRollbackStore()
        operation = RollbackOperation(target_state="v1.2.3")

        await store.save(operation)
        deleted = await store.delete(operation.operation_id)
        retrieved = await store.get(operation.operation_id)

        assert deleted is True
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Test deleting non-existent operation."""
        store = InMemoryRollbackStore()

        deleted = await store.delete("non-existent")

        assert deleted is False


class TestRollbackMetrics:
    """Tests for RollbackMetrics."""

    def test_record_operation_success(self):
        """Test recording successful operation."""
        metrics = RollbackMetrics()
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_started()
        operation.mark_completed()

        metrics.record_operation(operation)

        assert metrics.total_operations == 1
        assert metrics.successful == 1
        assert metrics.failed == 0
        assert metrics.by_target_state["v1.2.3"]["success"] == 1

    def test_record_operation_failure(self):
        """Test recording failed operation."""
        metrics = RollbackMetrics()
        operation = RollbackOperation(target_state="v1.2.3")
        operation.mark_started()
        operation.mark_failed("Failed")

        metrics.record_operation(operation)

        assert metrics.total_operations == 1
        assert metrics.successful == 0
        assert metrics.failed == 1
        assert metrics.by_target_state["v1.2.3"]["failure"] == 1

    def test_update_stats(self):
        """Test updating duration statistics."""
        metrics = RollbackMetrics()

        op1 = RollbackOperation(target_state="v1.2.3")
        op1.duration_seconds = 10.0

        op2 = RollbackOperation(target_state="v1.2.3")
        op2.duration_seconds = 20.0

        metrics.update_stats([op1, op2])

        assert metrics.avg_duration_seconds == 15.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = RollbackMetrics()
        metrics.total_operations = 5
        metrics.successful = 3
        metrics.failed = 2

        data = metrics.to_dict()

        assert data["total_operations"] == 5
        assert data["successful"] == 3
        assert data["failed"] == 2
