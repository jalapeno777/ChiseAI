"""Tests for rollback validation endpoint and schema behavior.

Verifies rollback validation, API schemas, and coordinator integration.

EP-NS-008: Autonomous Control Plane - Batch 1, Task 3
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

# Ensure src is in path
sys.path.insert(0, "src")

from src.autonomous_control_plane.components.rollback_coordinator import (
    InMemoryRollbackStore,
    PreFlightValidator,
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.rollback import (
    RollbackHistoryItem,
    RollbackHistoryResponse,
    RollbackMetricsResponse,
    RollbackRequest,
    RollbackResponse,
    RollbackScheduleRequest,
    RollbackStatus,
    RollbackStepItem,
    RollbackValidationResponse,
    ValidationCheck,
    ValidationCheckItem,
    ValidationCheckStatus,
    ValidationResult,
)

# =============================================================================
# Test Validation Models
# =============================================================================


class TestValidationCheck:
    """Test ValidationCheck model."""

    def test_validation_check_creation(self):
        """Test creating a validation check."""
        check = ValidationCheck(
            name="test_check",
            description="Test validation check",
        )

        assert check.name == "test_check"
        assert check.description == "Test validation check"
        assert check.status == ValidationCheckStatus.PENDING
        assert check.check_id is not None

    def test_validation_check_mark_pass(self):
        """Test marking a validation check as passed."""
        check = ValidationCheck(name="test", description="Test")
        check.mark_pass("All systems go")

        assert check.status == ValidationCheckStatus.PASS
        assert check.message == "All systems go"
        assert check.executed_at is not None

    def test_validation_check_mark_fail(self):
        """Test marking a validation check as failed."""
        check = ValidationCheck(name="test", description="Test")
        check.mark_fail("System check failed")

        assert check.status == ValidationCheckStatus.FAIL
        assert check.message == "System check failed"
        assert check.executed_at is not None

    def test_validation_check_mark_skipped(self):
        """Test marking a validation check as skipped."""
        check = ValidationCheck(name="test", description="Test")
        check.mark_skipped("Skipped due to force flag")

        assert check.status == ValidationCheckStatus.SKIPPED
        assert check.executed_at is not None

    def test_validation_check_to_dict(self):
        """Test converting validation check to dictionary."""
        check = ValidationCheck(name="test", description="Test")
        check.mark_pass("Success")

        data = check.to_dict()

        assert data["name"] == "test"
        assert data["status"] == "pass"
        assert data["message"] == "Success"
        assert "check_id" in data


class TestValidationResult:
    """Test ValidationResult model."""

    def test_validation_result_creation(self):
        """Test creating a validation result."""
        result = ValidationResult()

        assert result.checks == []
        assert result.valid is False
        assert result.errors == []

    def test_validation_result_add_check(self):
        """Test adding a check to validation result."""
        result = ValidationResult()
        check = ValidationCheck(name="test", description="Test")
        check.mark_pass()

        result.add_check(check)

        assert len(result.checks) == 1
        assert result.checks[0].name == "test"

    def test_validation_result_all_passed(self):
        """Test all_passed property."""
        result = ValidationResult()

        check1 = ValidationCheck(name="test1", description="Test 1")
        check1.mark_pass()
        result.add_check(check1)

        check2 = ValidationCheck(name="test2", description="Test 2")
        check2.mark_pass()
        result.add_check(check2)

        result.finalize()

        assert result.all_passed is True
        assert result.valid is True

    def test_validation_result_failed_checks(self):
        """Test failed_checks property."""
        result = ValidationResult()

        check1 = ValidationCheck(name="test1", description="Test 1")
        check1.mark_pass()
        result.add_check(check1)

        check2 = ValidationCheck(name="test2", description="Test 2")
        check2.mark_fail("Failed")
        result.add_check(check2)

        assert len(result.failed_checks) == 1
        assert result.failed_checks[0].name == "test2"

    def test_validation_result_to_dict(self):
        """Test converting validation result to dictionary."""
        result = ValidationResult()
        check = ValidationCheck(name="test", description="Test")
        check.mark_pass()
        result.add_check(check)
        result.finalize()

        data = result.to_dict()

        assert data["valid"] is True
        assert len(data["checks"]) == 1
        assert data["errors"] == []


# =============================================================================
# Test PreFlightValidator
# =============================================================================


class TestPreFlightValidator:
    """Test PreFlightValidator."""

    @pytest.mark.asyncio
    async def test_validator_initialization(self):
        """Test validator initialization."""
        validator = PreFlightValidator()

        assert "system_health" in validator._health_checkers
        assert "database_connections" in validator._health_checkers
        assert "resource_availability" in validator._health_checkers

    @pytest.mark.asyncio
    async def test_validate_with_force(self):
        """Test validation with force flag."""
        validator = PreFlightValidator()
        result = await validator.validate("v1.0.0", force=True)

        assert result.valid is True
        assert len(result.checks) == 5  # Default checks
        assert all(c.status == ValidationCheckStatus.SKIPPED for c in result.checks)

    @pytest.mark.asyncio
    async def test_validate_without_force(self):
        """Test validation without force flag."""
        validator = PreFlightValidator()
        result = await validator.validate("v1.0.0", force=False)

        assert result.valid is True
        assert len(result.checks) == 5
        assert all(c.status == ValidationCheckStatus.PASS for c in result.checks)

    @pytest.mark.asyncio
    async def test_validate_with_custom_checker(self):
        """Test validation with custom checker."""

        def custom_checker():
            check = ValidationCheck(name="custom", description="Custom check")
            check.mark_pass("Custom passed")
            return check

        validator = PreFlightValidator()
        validator.register_checker("custom", custom_checker)

        result = await validator.validate("v1.0.0")

        assert len(result.checks) == 6
        check_names = [c.name for c in result.checks]
        assert "custom" in check_names


# =============================================================================
# Test RollbackCoordinator
# =============================================================================


class TestRollbackCoordinator:
    """Test RollbackCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create a rollback coordinator for testing."""
        return RollbackCoordinator()

    @pytest.mark.asyncio
    async def test_coordinator_initialization(self, coordinator):
        """Test coordinator initialization."""
        assert coordinator._store is not None
        assert coordinator._validator is not None
        assert coordinator._health_checker is not None

    def test_can_rollback_valid(self, coordinator):
        """Test can_rollback with valid target state."""
        can_roll, reason = coordinator.can_rollback("v1.0.0")

        assert can_roll is True
        assert "v1.0.0" in reason

    def test_can_rollback_empty_target(self, coordinator):
        """Test can_rollback with empty target state."""
        can_roll, reason = coordinator.can_rollback("")

        assert can_roll is False
        assert "empty" in reason.lower()

    @pytest.mark.asyncio
    async def test_create_rollback_operation(self, coordinator):
        """Test creating a rollback operation."""
        operation = await coordinator.create_rollback_operation(
            target_state="v1.0.0",
            initiated_by="test",
        )

        assert operation.target_state == "v1.0.0"
        assert operation.initiated_by == "test"
        assert operation.status == RollbackStatus.PENDING
        assert len(operation.steps) == 5  # Default steps

    @pytest.mark.asyncio
    async def test_execute_rollback_success(self, coordinator):
        """Test successful rollback execution."""
        operation = await coordinator.execute_rollback(
            target_state="v1.0.0",
            initiated_by="test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.error_message is None
        assert operation.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_rollback_with_force(self, coordinator):
        """Test rollback execution with force flag."""
        operation = await coordinator.execute_rollback(
            target_state="v1.0.0",
            force=True,
            initiated_by="test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        # Check that validation was skipped
        assert any(
            "skipped" in entry.message.lower() or "force" in entry.message.lower()
            for entry in operation.audit_log
        )

    @pytest.mark.asyncio
    async def test_emergency_rollback(self, coordinator):
        """Test emergency rollback."""
        operation = await coordinator.emergency_rollback(
            target_state="v1.0.0",
            initiated_by="emergency_test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.force is True

    @pytest.mark.asyncio
    async def test_get_operation(self, coordinator):
        """Test getting an operation by ID."""
        operation = await coordinator.create_rollback_operation(
            target_state="v1.0.0",
            initiated_by="test",
        )

        retrieved = await coordinator.get_operation(operation.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id

    @pytest.mark.asyncio
    async def test_list_operations(self, coordinator):
        """Test listing operations."""
        # Create a few operations
        for i in range(3):
            await coordinator.create_rollback_operation(
                target_state=f"v1.{i}.0",
                initiated_by="test",
            )

        operations = await coordinator.list_operations(limit=10)

        assert len(operations) == 3

    @pytest.mark.asyncio
    async def test_get_history(self, coordinator):
        """Test getting rollback history."""
        # Create and complete an operation
        await coordinator.execute_rollback(target_state="v1.0.0", initiated_by="test")

        history = await coordinator.get_history(limit=10)

        assert len(history) >= 1
        assert all(isinstance(op.target_state, str) for op in history)

    @pytest.mark.asyncio
    async def test_get_rollback_history_alias(self, coordinator):
        """Test get_rollback_history alias method."""
        await coordinator.execute_rollback(target_state="v1.0.0", initiated_by="test")

        history = await coordinator.get_rollback_history(limit=10)

        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_schedule_rollback(self, coordinator):
        """Test scheduling a rollback."""
        scheduled_time = datetime.now(UTC) + timedelta(hours=1)

        operation = await coordinator.schedule_rollback(
            target_state="v1.0.0",
            scheduled_at=scheduled_time,
            initiated_by="scheduler_test",
        )

        assert operation.status == RollbackStatus.PENDING
        assert operation.metadata.get("scheduled") is True
        assert "scheduled_at" in operation.metadata

    @pytest.mark.asyncio
    async def test_get_metrics(self, coordinator):
        """Test getting rollback metrics."""
        # Execute a rollback to generate metrics
        await coordinator.execute_rollback(target_state="v1.0.0", initiated_by="test")

        metrics = await coordinator.get_metrics()

        assert metrics.total_operations >= 1
        assert metrics.successful >= 1


# =============================================================================
# Test Pydantic API Models
# =============================================================================


class TestRollbackRequest:
    """Test RollbackRequest Pydantic model."""

    def test_rollback_request_creation(self):
        """Test creating a rollback request."""
        request = RollbackRequest(
            target_state="v1.0.0",
            force=False,
            initiated_by="api",
            metadata={"reason": "test"},
        )

        assert request.target_state == "v1.0.0"
        assert request.force is False
        assert request.initiated_by == "api"
        assert request.metadata == {"reason": "test"}

    def test_rollback_request_defaults(self):
        """Test rollback request default values."""
        request = RollbackRequest(target_state="v1.0.0")

        assert request.force is False
        assert request.initiated_by == "api"
        assert request.metadata == {}

    def test_rollback_request_validation(self):
        """Test rollback request validation."""
        # Valid request
        request = RollbackRequest(target_state="v1.0.0")
        assert request.target_state == "v1.0.0"


class TestRollbackValidationResponse:
    """Test RollbackValidationResponse Pydantic model."""

    def test_validation_response_creation(self):
        """Test creating a validation response."""
        response = RollbackValidationResponse(
            can_rollback=True,
            reason="All checks passed",
            validation_checks=[
                ValidationCheckItem(
                    check_id="1",
                    name="system_health",
                    description="Check system health",
                    status="pass",
                    message="Healthy",
                    details={},
                    executed_at=datetime.now(UTC).isoformat(),
                    duration_seconds=0.1,
                )
            ],
            errors=[],
            warnings=[],
        )

        assert response.can_rollback is True
        assert response.reason == "All checks passed"
        assert len(response.validation_checks) == 1

    def test_validation_response_failed(self):
        """Test validation response for failed validation."""
        response = RollbackValidationResponse(
            can_rollback=False,
            reason="System unhealthy",
            validation_checks=[],
            errors=["Database connection failed"],
            warnings=["High CPU usage"],
        )

        assert response.can_rollback is False
        assert len(response.errors) == 1
        assert len(response.warnings) == 1


class TestRollbackResponse:
    """Test RollbackResponse Pydantic model."""

    def test_rollback_response_creation(self):
        """Test creating a rollback response."""
        response = RollbackResponse(
            rollback_id=str(uuid.uuid4()),
            target_state="v1.0.0",
            status="completed",
            steps=[
                RollbackStepItem(
                    step_id="1",
                    name="stop_operations",
                    description="Stop operations",
                    action="stop",
                    status="completed",
                    order=1,
                    started_at=datetime.now(UTC).isoformat(),
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message=None,
                    execution_result={"success": True},
                    timeout_seconds=10.0,
                    duration_seconds=1.0,
                )
            ],
            created_at=datetime.now(UTC).isoformat(),
            initiated_by="api",
            force=False,
        )

        assert response.target_state == "v1.0.0"
        assert response.status == "completed"
        assert len(response.steps) == 1


class TestRollbackHistoryItem:
    """Test RollbackHistoryItem Pydantic model."""

    def test_history_item_creation(self):
        """Test creating a history item."""
        item = RollbackHistoryItem(
            rollback_id=str(uuid.uuid4()),
            target_state="v1.0.0",
            status="completed",
            created_at=datetime.now(UTC).isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_seconds=5.0,
            initiated_by="api",
            force=False,
            error_message=None,
        )

        assert item.target_state == "v1.0.0"
        assert item.status == "completed"
        assert item.duration_seconds == 5.0


class TestRollbackScheduleRequest:
    """Test RollbackScheduleRequest Pydantic model."""

    def test_schedule_request_creation(self):
        """Test creating a schedule request."""
        scheduled_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        request = RollbackScheduleRequest(
            target_state="v1.0.0",
            scheduled_at=scheduled_time,
            force=False,
            initiated_by="scheduler",
            metadata={"reason": "maintenance"},
        )

        assert request.target_state == "v1.0.0"
        assert request.scheduled_at == scheduled_time


# =============================================================================
# Test API Router Helper Functions
# =============================================================================


class TestAPIHelperFunctions:
    """Test API router helper functions."""

    def test_validation_result_to_response(self):
        """Test converting ValidationResult to response."""
        from src.autonomous_control_plane.api.v1.rollback import (
            _validation_result_to_response,
        )

        result = ValidationResult()
        check = ValidationCheck(name="test", description="Test")
        check.mark_pass("Success")
        result.add_check(check)
        result.finalize()

        response = _validation_result_to_response(result, "v1.0.0")

        assert isinstance(response, RollbackValidationResponse)
        assert response.can_rollback is True
        assert "v1.0.0" in response.reason
        assert len(response.validation_checks) == 1

    def test_operation_to_response(self):
        """Test converting RollbackOperation to response."""
        from src.autonomous_control_plane.api.v1.rollback import (
            _operation_to_response,
        )
        from src.autonomous_control_plane.models.rollback import RollbackOperation

        operation = RollbackOperation(
            target_state="v1.0.0",
            initiated_by="test",
        )

        response = _operation_to_response(operation)

        assert isinstance(response, RollbackResponse)
        assert response.target_state == "v1.0.0"
        assert response.initiated_by == "test"

    def test_operation_to_history_item(self):
        """Test converting RollbackOperation to history item."""
        from src.autonomous_control_plane.api.v1.rollback import (
            _operation_to_history_item,
        )
        from src.autonomous_control_plane.models.rollback import RollbackOperation

        operation = RollbackOperation(
            target_state="v1.0.0",
            initiated_by="test",
        )

        item = _operation_to_history_item(operation)

        assert isinstance(item, RollbackHistoryItem)
        assert item.target_state == "v1.0.0"


# =============================================================================
# Test API Endpoints (with mocked coordinator)
# =============================================================================


class TestAPIEndpoints:
    """Test API endpoints with mocked coordinator."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        mock = MagicMock()
        mock.can_rollback.return_value = (True, "Can rollback")
        return mock

    @pytest.mark.asyncio
    async def test_validate_rollback_endpoint(self, mock_coordinator):
        """Test validate rollback endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            set_coordinator,
            validate_rollback,
        )

        # Create a real coordinator for the test
        real_coordinator = RollbackCoordinator()
        set_coordinator(real_coordinator)

        request = RollbackRequest(target_state="v1.0.0")
        response = await validate_rollback(request)

        assert isinstance(response, RollbackValidationResponse)
        assert response.can_rollback is True

    @pytest.mark.asyncio
    async def test_execute_rollback_endpoint(self):
        """Test execute rollback endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            execute_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        request = RollbackRequest(target_state="v1.0.0")
        response = await execute_rollback(request)

        assert isinstance(response, RollbackResponse)
        assert response.target_state == "v1.0.0"
        assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_rollback_endpoint_cannot_rollback(self):
        """Test execute rollback when cannot rollback."""
        from fastapi import HTTPException
        from src.autonomous_control_plane.api.v1.rollback import (
            execute_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        # Test with empty target state
        request = RollbackRequest(target_state="")

        with pytest.raises(HTTPException) as exc_info:
            await execute_rollback(request)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_emergency_rollback_endpoint(self):
        """Test emergency rollback endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            emergency_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        request = RollbackRequest(target_state="v1.0.0")
        response = await emergency_rollback(request)

        assert isinstance(response, RollbackResponse)
        assert response.force is True

    @pytest.mark.asyncio
    async def test_get_rollback_status_endpoint(self):
        """Test get rollback status endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_status,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        # Create an operation first
        operation = await coordinator.create_rollback_operation(
            target_state="v1.0.0",
            initiated_by="test",
        )

        response = await get_rollback_status(operation.operation_id)

        assert isinstance(response, RollbackResponse)
        assert response.rollback_id == operation.operation_id

    @pytest.mark.asyncio
    async def test_get_rollback_status_not_found(self):
        """Test get rollback status for non-existent operation."""
        from fastapi import HTTPException
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_status,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        with pytest.raises(HTTPException) as exc_info:
            await get_rollback_status("non-existent-id")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_rollback_history_endpoint(self):
        """Test get rollback history endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_history,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        # Create an operation
        await coordinator.execute_rollback(target_state="v1.0.0", initiated_by="test")

        response = await get_rollback_history(limit=10, offset=0)

        assert isinstance(response, RollbackHistoryResponse)
        assert len(response.operations) >= 1

    @pytest.mark.asyncio
    async def test_schedule_rollback_endpoint(self):
        """Test schedule rollback endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            schedule_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        scheduled_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        request = RollbackScheduleRequest(
            target_state="v1.0.0",
            scheduled_at=scheduled_time,
        )

        response = await schedule_rollback(request)

        assert isinstance(response, RollbackResponse)
        assert response.status == "pending"

    @pytest.mark.asyncio
    async def test_schedule_rollback_invalid_timestamp(self):
        """Test schedule rollback with invalid timestamp."""
        from fastapi import HTTPException
        from src.autonomous_control_plane.api.v1.rollback import (
            schedule_rollback,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        request = RollbackScheduleRequest(
            target_state="v1.0.0",
            scheduled_at="invalid-timestamp",
        )

        with pytest.raises(HTTPException) as exc_info:
            await schedule_rollback(request)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_rollback_metrics_endpoint(self):
        """Test get rollback metrics endpoint."""
        from src.autonomous_control_plane.api.v1.rollback import (
            get_rollback_metrics,
            set_coordinator,
        )

        coordinator = RollbackCoordinator()
        set_coordinator(coordinator)

        # Execute a rollback to generate metrics
        await coordinator.execute_rollback(target_state="v1.0.0", initiated_by="test")

        response = await get_rollback_metrics()

        assert isinstance(response, RollbackMetricsResponse)
        assert response.total_operations >= 1


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling in rollback operations."""

    @pytest.mark.asyncio
    async def test_rollback_with_invalid_target(self):
        """Test rollback with invalid target state."""
        coordinator = RollbackCoordinator()

        # Test can_rollback with invalid target
        can_roll, reason = coordinator.can_rollback("")
        assert can_roll is False

    @pytest.mark.asyncio
    async def test_rollback_store_operations(self):
        """Test rollback store operations."""
        store = InMemoryRollbackStore()

        from src.autonomous_control_plane.models.rollback import RollbackOperation

        operation = RollbackOperation(target_state="v1.0.0")

        # Save
        await store.save(operation)

        # Get
        retrieved = await store.get(operation.operation_id)
        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id

        # List
        operations = await store.list(limit=10)
        assert len(operations) == 1

        # Delete
        deleted = await store.delete(operation.operation_id)
        assert deleted is True

        # Verify deletion
        retrieved = await store.get(operation.operation_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_rollback_store_delete_nonexistent(self):
        """Test deleting non-existent operation."""
        store = InMemoryRollbackStore()

        deleted = await store.delete("non-existent-id")
        assert deleted is False


# =============================================================================
# Test Integration with Health Monitor (simulated)
# =============================================================================


class TestHealthMonitorIntegration:
    """Test integration with health monitoring."""

    @pytest.mark.asyncio
    async def test_pre_rollback_health_check(self):
        """Test pre-rollback health check integration."""
        coordinator = RollbackCoordinator()

        # Run validation which includes health checks
        result = await coordinator.validate_rollback("v1.0.0")

        assert result.valid is True
        # Check that system health check was performed
        check_names = [c.name for c in result.checks]
        assert "system_health" in check_names

    @pytest.mark.asyncio
    async def test_post_rollback_health_check(self):
        """Test post-rollback health check integration."""
        coordinator = RollbackCoordinator()

        # Execute rollback which includes post-rollback health checks
        operation = await coordinator.execute_rollback(
            target_state="v1.0.0",
            initiated_by="test",
        )

        assert operation.status == RollbackStatus.COMPLETED
        assert operation.post_rollback_health is not None
        assert operation.post_rollback_health.healthy is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
