"""Comprehensive tests for action execution framework.

This module provides unit and integration tests for:
- ActionExecutor
- ActionValidator
- RollbackManager
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from autonomous_cognition.action_executor import (
    Action,
    ActionExecutor,
    ActionOutcome,
    ActionPriority,
    ActionStatus,
)
from autonomous_cognition.rollback import (
    ActionSnapshot,
    RollbackManager,
    RollbackResult,
)
from autonomous_cognition.validation import (
    ActionValidator,
    BudgetConfig,
    RateLimitConfig,
    SafetyConstraint,
    ValidationResult,
)


class TestAction:
    """Tests for Action dataclass."""

    def test_action_creation(self):
        """Test basic action creation."""
        action = Action(
            name="test_action",
            action_type="test",
            payload={"key": "value"},
        )

        assert action.name == "test_action"
        assert action.action_type == "test"
        assert action.payload == {"key": "value"}
        assert action.priority == ActionPriority.MEDIUM
        assert action.timeout_seconds == 30.0
        assert action.max_retries == 0
        assert action.require_validation is True
        assert action.enable_rollback is True

    def test_action_with_custom_values(self):
        """Test action creation with custom values."""
        action = Action(
            name="custom_action",
            action_type="custom",
            payload={"data": [1, 2, 3]},
            priority=ActionPriority.HIGH,
            timeout_seconds=60.0,
            max_retries=3,
            retry_delay_seconds=2.0,
            require_validation=False,
            enable_rollback=False,
            metadata={"source": "test"},
        )

        assert action.priority == ActionPriority.HIGH
        assert action.timeout_seconds == 60.0
        assert action.max_retries == 3
        assert action.retry_delay_seconds == 2.0
        assert action.require_validation is False
        assert action.enable_rollback is False
        assert action.metadata == {"source": "test"}

    def test_action_invalid_timeout(self):
        """Test that invalid timeout raises error."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            Action(
                name="test",
                action_type="test",
                timeout_seconds=0,
            )

    def test_action_invalid_retries(self):
        """Test that negative retries raises error."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            Action(
                name="test",
                action_type="test",
                max_retries=-1,
            )

    def test_action_invalid_retry_delay(self):
        """Test that negative retry delay raises error."""
        with pytest.raises(
            ValueError, match="retry_delay_seconds must be non-negative"
        ):
            Action(
                name="test",
                action_type="test",
                retry_delay_seconds=-1,
            )


class TestActionOutcome:
    """Tests for ActionOutcome dataclass."""

    def test_success_outcome(self):
        """Test successful outcome."""
        outcome = ActionOutcome(
            action_id="test-123",
            status=ActionStatus.SUCCEEDED,
            result={"data": "value"},
        )

        assert outcome.success is True
        assert outcome.failed is False
        assert outcome.rolled_back is False
        assert outcome.result == {"data": "value"}

    def test_failed_outcome(self):
        """Test failed outcome."""
        outcome = ActionOutcome(
            action_id="test-123",
            status=ActionStatus.FAILED,
            error="Something went wrong",
        )

        assert outcome.success is False
        assert outcome.failed is True
        assert outcome.rolled_back is False
        assert outcome.error == "Something went wrong"

    def test_timeout_outcome(self):
        """Test timeout outcome."""
        outcome = ActionOutcome(
            action_id="test-123",
            status=ActionStatus.TIMEOUT,
            error="Timeout occurred",
        )

        assert outcome.success is False
        assert outcome.failed is True

    def test_rolled_back_outcome(self):
        """Test rolled back outcome."""
        outcome = ActionOutcome(
            action_id="test-123",
            status=ActionStatus.ROLLED_BACK,
            error="Failed and rolled back",
        )

        assert outcome.success is False
        assert outcome.failed is False
        assert outcome.rolled_back is True


class TestActionExecutorBasics:
    """Basic tests for ActionExecutor."""

    def test_executor_creation(self):
        """Test executor initialization."""
        executor = ActionExecutor()

        assert executor._max_concurrent == 10
        assert executor._default_timeout == 30.0
        assert executor._enable_audit_logging is True
        assert executor._running is False

    def test_executor_custom_config(self):
        """Test executor with custom config."""
        validator = ActionValidator()
        rollback_manager = RollbackManager()

        executor = ActionExecutor(
            validator=validator,
            rollback_manager=rollback_manager,
            max_concurrent=5,
            default_timeout=60.0,
            enable_audit_logging=False,
        )

        assert executor._max_concurrent == 5
        assert executor._default_timeout == 60.0
        assert executor._enable_audit_logging is False
        assert executor._validator is validator
        assert executor._rollback_manager is rollback_manager

    def test_register_handler(self):
        """Test handler registration."""
        executor = ActionExecutor()

        def handler(action):
            return {"result": "success"}

        executor.register_handler("test_type", handler)
        assert "test_type" in executor._handlers

    def test_register_duplicate_handler(self):
        """Test that duplicate handler registration raises error."""
        executor = ActionExecutor()

        def handler(action):
            return {"result": "success"}

        executor.register_handler("test_type", handler)

        with pytest.raises(ValueError, match="Handler already registered"):
            executor.register_handler("test_type", handler)

    def test_unregister_handler(self):
        """Test handler unregistration."""
        executor = ActionExecutor()

        def handler(action):
            return {"result": "success"}

        executor.register_handler("test_type", handler)
        executor.unregister_handler("test_type")

        assert "test_type" not in executor._handlers


@pytest.mark.asyncio
class TestActionExecutorAsync:
    """Async tests for ActionExecutor."""

    async def test_execute_success(self, async_action_executor, sample_action):
        """Test successful action execution."""

        async def handler(action):
            return {"result": "success", "data": action.payload}

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(sample_action)

        assert outcome.success is True
        assert outcome.status == ActionStatus.SUCCEEDED
        assert outcome.result == {"result": "success", "data": {"key": "value"}}
        assert outcome.execution_time_ms > 0

    async def test_execute_with_validation(self, async_action_executor, sample_action):
        """Test action execution with validation."""

        async def handler(action):
            return {"result": "handled"}

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(sample_action)

        assert outcome.success is True
        assert outcome.validation_time_ms >= 0

    async def test_execute_without_validation(self, async_action_executor):
        """Test action execution without validation."""
        action = Action(
            name="no_validation",
            action_type="test",
            require_validation=False,
        )

        async def handler(action):
            return {"result": "success"}

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is True

    async def test_execute_no_handler(self, async_action_executor, sample_action):
        """Test execution with no handler registered."""
        outcome = await async_action_executor.execute(sample_action)

        assert outcome.success is False
        assert outcome.status in (ActionStatus.FAILED, ActionStatus.ROLLED_BACK)
        assert "No handler registered" in outcome.error

    async def test_execute_timeout(self, async_action_executor):
        """Test action execution timeout."""
        action = Action(
            name="timeout_action",
            action_type="slow",
            timeout_seconds=0.1,
        )

        async def slow_handler(action):
            await asyncio.sleep(1.0)
            return {"result": "should_not_reach"}

        async_action_executor.register_handler("slow", slow_handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is False
        assert outcome.status in (ActionStatus.FAILED, ActionStatus.ROLLED_BACK)
        assert "Timeout" in outcome.error

    async def test_execute_with_retry(self, async_action_executor):
        """Test action execution with retry."""
        action = Action(
            name="retry_action",
            action_type="flaky",
            max_retries=2,
            retry_delay_seconds=0.01,
        )

        call_count = 0

        def flaky_handler(action):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Failure {call_count}")
            return {"result": "success_on_retry"}

        async_action_executor.register_handler("flaky", flaky_handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is True
        assert call_count == 3

    async def test_execute_all_retries_exhausted(self, async_action_executor):
        """Test when all retries are exhausted."""
        action = Action(
            name="always_fail",
            action_type="failing",
            max_retries=1,
            retry_delay_seconds=0.01,
        )

        def failing_handler(action):
            raise ValueError("Always fails")

        async_action_executor.register_handler("failing", failing_handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is False
        assert "Always fails" in outcome.error

    async def test_execute_batch(self, async_action_executor):
        """Test batch execution."""

        async def handler(action):
            return {"result": action.name}

        async_action_executor.register_handler("test", handler)

        actions = [Action(name=f"action_{i}", action_type="test") for i in range(5)]

        outcomes = await async_action_executor.execute_batch(actions)

        assert len(outcomes) == 5
        assert all(o.success for o in outcomes)

    async def test_execute_batch_with_failure(self, async_action_executor):
        """Test batch execution with some failures."""

        def handler(action):
            if action.payload.get("fail"):
                raise ValueError("Intentional failure")
            return {"result": "success"}

        async_action_executor.register_handler("test", handler)

        actions = [
            Action(name="success", action_type="test", payload={"fail": False}),
            Action(name="failure", action_type="test", payload={"fail": True}),
            Action(name="success2", action_type="test", payload={"fail": False}),
        ]

        outcomes = await async_action_executor.execute_batch(
            actions, continue_on_error=True
        )

        assert len(outcomes) == 3
        assert outcomes[0].success is True
        assert outcomes[1].success is False
        assert outcomes[2].success is True

    async def test_priority_queue_ordering(self, async_action_executor):
        """Test that priority queue orders actions correctly."""
        results = []

        async def handler(action):
            results.append(action.name)
            return {"result": action.name}

        async_action_executor.register_handler("test", handler)

        # Submit in reverse priority order
        low_action = Action(name="low", action_type="test", priority=ActionPriority.LOW)
        medium_action = Action(
            name="medium", action_type="test", priority=ActionPriority.MEDIUM
        )
        high_action = Action(
            name="high", action_type="test", priority=ActionPriority.HIGH
        )
        critical_action = Action(
            name="critical", action_type="test", priority=ActionPriority.CRITICAL
        )

        await asyncio.gather(
            async_action_executor.execute(low_action),
            async_action_executor.execute(medium_action),
            async_action_executor.execute(high_action),
            async_action_executor.execute(critical_action),
        )

        # Higher priority should execute first
        assert results[0] == "critical"
        assert results[1] == "high"
        assert results[2] == "medium"
        assert results[3] == "low"

    async def test_audit_logging(self, async_action_executor, sample_action):
        """Test that audit logs are created."""

        async def handler(action):
            return {"result": "success"}

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(sample_action)

        assert outcome.success is True

        logs = async_action_executor.get_audit_logs()
        assert len(logs) >= 1

        latest_log = logs[-1]
        assert latest_log["action_name"] == sample_action.name
        assert latest_log["action_type"] == sample_action.action_type
        assert latest_log["status"] == "SUCCEEDED"

    async def test_audit_log_filtering(self, async_action_executor):
        """Test audit log filtering."""

        async def handler(action):
            return {"result": action.action_type}

        async_action_executor.register_handler("type_a", handler)
        async_action_executor.register_handler("type_b", handler)

        await async_action_executor.execute(Action(name="a1", action_type="type_a"))
        await async_action_executor.execute(Action(name="b1", action_type="type_b"))
        await async_action_executor.execute(Action(name="a2", action_type="type_a"))

        type_a_logs = async_action_executor.get_audit_logs(action_type="type_a")
        assert len(type_a_logs) == 2

        type_b_logs = async_action_executor.get_audit_logs(action_type="type_b")
        assert len(type_b_logs) == 1


@pytest.mark.asyncio
class TestActionExecutorRollback:
    """Tests for rollback functionality."""

    async def test_rollback_on_failure(self, async_action_executor):
        """Test that rollback is executed on failure."""
        action = Action(
            name="rollback_test",
            action_type="test",
            enable_rollback=True,
            max_retries=0,
        )

        def handler(action):
            raise ValueError("Intentional failure")

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is False
        assert outcome.status == ActionStatus.ROLLED_BACK

    async def test_no_rollback_when_disabled(self, async_action_executor):
        """Test that rollback is not executed when disabled."""
        action = Action(
            name="no_rollback_test",
            action_type="test",
            enable_rollback=False,
            max_retries=0,
        )

        def handler(action):
            raise ValueError("Intentional failure")

        async_action_executor.register_handler("test", handler)
        outcome = await async_action_executor.execute(action)

        assert outcome.success is False
        assert outcome.status == ActionStatus.FAILED  # Not ROLLED_BACK


class TestActionExecutorSync:
    """Tests for synchronous execution."""

    def test_execute_sync(self, sample_action):
        """Test synchronous execution."""
        executor = ActionExecutor()

        def handler(action):
            return {"result": "sync_success"}

        executor.register_handler("test", handler)
        outcome = executor.execute_sync(sample_action)

        assert outcome.success is True
        assert outcome.result == {"result": "sync_success"}

        executor.shutdown()


class TestActionValidator:
    """Tests for ActionValidator."""

    def test_validator_creation(self):
        """Test validator initialization."""
        validator = ActionValidator()

        assert validator._rate_limits.max_requests_per_minute == 60
        assert validator._rate_limits.max_requests_per_hour == 1000
        assert validator._rate_limits.burst_size == 10

    def test_validator_custom_config(self):
        """Test validator with custom config."""
        rate_limits = RateLimitConfig(
            max_requests_per_minute=30,
            max_requests_per_hour=500,
            burst_size=5,
        )
        budget = BudgetConfig(
            max_daily_actions=5000,
            max_concurrent_actions=50,
        )

        validator = ActionValidator(rate_limits=rate_limits, budget=budget)

        assert validator._rate_limits.max_requests_per_minute == 30
        assert validator._budget.max_daily_actions == 5000

    @pytest.mark.asyncio
    async def test_validate_valid_action(self, validator, sample_action):
        """Test validation of a valid action."""
        result = await validator.validate(sample_action, "test-id")

        assert result.valid is True
        assert result.error == ""
        assert result.validation_time_ms >= 0
        assert "schema" in result.constraints_checked

    @pytest.mark.asyncio
    async def test_validate_empty_name(self, validator):
        """Test validation rejects empty name."""
        action = Action(name="", action_type="test")
        result = await validator.validate(action, "test-id")

        assert result.valid is False
        assert "name is required" in result.error

    @pytest.mark.asyncio
    async def test_validate_empty_type(self, validator):
        """Test validation rejects empty type."""
        action = Action(name="test", action_type="")
        result = await validator.validate(action, "test-id")

        assert result.valid is False
        assert "type is required" in result.error

    @pytest.mark.asyncio
    async def test_validate_none_payload(self, validator):
        """Test validation rejects None payload."""
        action = Action(name="test", action_type="test")
        # Manually set payload to None to test
        object.__setattr__(action, "payload", None)
        result = await validator.validate(action, "test-id")

        assert result.valid is False
        assert "payload cannot be None" in result.error

    @pytest.mark.asyncio
    async def test_validate_large_payload(self, validator):
        """Test validation warns about large payload."""
        large_payload = {"data": "x" * 100001}  # > 100KB
        action = Action(name="test", action_type="test", payload=large_payload)
        result = await validator.validate(action, "test-id")

        assert result.valid is True
        assert any("exceeds recommended" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_rate_limit(self, validator_with_limits):
        """Test rate limiting validation."""
        validator = validator_with_limits

        # Exhaust the rate limit
        action = Action(name="test", action_type="test")

        # First 5 should pass (burst size)
        for _ in range(5):
            result = await validator.validate(action, "test-id")
            assert result.valid is True

        # Sixth should fail (burst exhausted)
        result = await validator.validate(action, "test-id")
        assert result.valid is False
        assert "burst capacity exhausted" in result.error

    @pytest.mark.asyncio
    async def test_validate_budget_limit(self, validator_with_limits):
        """Test budget constraint validation."""
        validator = validator_with_limits

        # Reset rate limits first to ensure clean state
        validator.reset_rate_limits()

        # Exhaust concurrent limit
        action = Action(name="test", action_type="test")

        for i in range(5):
            result = await validator.validate(action, f"test-id-{i}")
            if result.valid:
                validator.release_concurrent_slot()
            assert result.valid is True

        # Sixth should fail
        result = await validator.validate(action, "test-id-6")
        assert result.valid is False
        assert (
            "Concurrent action limit exceeded" in result.error
            or "burst capacity" in result.error
        )

    def test_release_concurrent_slot(self, validator_with_limits):
        """Test releasing concurrent slots."""
        validator = validator_with_limits

        # Use up slots
        validator._concurrent_count = 5

        # Release one
        validator.release_concurrent_slot()
        assert validator._concurrent_count == 4

        # Release all (shouldn't go negative)
        for _ in range(10):
            validator.release_concurrent_slot()
        assert validator._concurrent_count == 0

    def test_get_rate_limit_status(self, validator):
        """Test getting rate limit status."""
        status = validator.get_rate_limit_status()

        assert "requests_last_minute" in status
        assert "max_requests_per_minute" in status
        assert "available_tokens" in status
        assert "concurrent_count" in status

    def test_reset_rate_limits(self, validator):
        """Test resetting rate limits."""
        # Add some usage
        validator._request_times = [time.time()] * 10
        validator._daily_count = 100
        validator._concurrent_count = 5

        validator.reset_rate_limits()

        assert len(validator._request_times) == 0
        assert validator._daily_count == 0
        assert validator._concurrent_count == 0


class TestActionValidatorCustomConstraints:
    """Tests for custom safety constraints."""

    @pytest.mark.asyncio
    async def test_custom_constraint_pass(self):
        """Test custom constraint that passes."""
        constraint = SafetyConstraint(
            name="test_constraint",
            check=lambda action: action.payload.get("allowed", False),
            error_message="Action not allowed",
        )

        validator = ActionValidator(custom_constraints=[constraint])
        action = Action(name="test", action_type="test", payload={"allowed": True})

        result = await validator.validate(action, "test-id")
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_custom_constraint_fail(self):
        """Test custom constraint that fails."""
        constraint = SafetyConstraint(
            name="test_constraint",
            check=lambda action: action.payload.get("allowed", False),
            error_message="Action not allowed",
        )

        validator = ActionValidator(custom_constraints=[constraint])
        action = Action(name="test", action_type="test", payload={"allowed": False})

        result = await validator.validate(action, "test-id")
        assert result.valid is False
        assert "Action not allowed" in result.error


class TestRollbackManager:
    """Tests for RollbackManager."""

    @pytest.mark.asyncio
    async def test_create_snapshot(self, rollback_manager, sample_action):
        """Test snapshot creation."""
        snapshot = await rollback_manager.create_snapshot(
            sample_action,
            "action-123",
            state={"original": "value"},
        )

        assert snapshot.snapshot_id is not None
        assert snapshot.action_id == "action-123"
        assert snapshot.action_type == "test"
        assert snapshot.state["original"] == "value"
        assert snapshot.timestamp > 0

    async def test_create_snapshot_with_compensation(
        self, rollback_manager, sample_action
    ):
        """Test snapshot with compensation action."""
        compensation = {"type": "reverse", "params": {}}

        snapshot = await rollback_manager.create_snapshot(
            sample_action,
            "action-123",
            compensation_action=compensation,
        )

        assert snapshot.compensation_action == compensation

    async def test_rollback_success(self, rollback_manager, sample_action):
        """Test successful rollback."""
        snapshot = await rollback_manager.create_snapshot(
            sample_action,
            "action-123",
        )

        result = await rollback_manager.rollback(snapshot)

        assert result.success is True
        assert result.snapshot_id == snapshot.snapshot_id
        assert result.execution_time_ms >= 0

    async def test_rollback_by_id(self, rollback_manager, sample_action):
        """Test rollback using snapshot ID."""
        snapshot = await rollback_manager.create_snapshot(
            sample_action,
            "action-123",
        )

        result = await rollback_manager.rollback(snapshot.snapshot_id)

        assert result.success is True

    async def test_rollback_nonexistent_snapshot(self, rollback_manager):
        """Test rollback of non-existent snapshot."""
        result = await rollback_manager.rollback("nonexistent-id")

        assert result.success is False
        assert "not found" in result.error

    async def test_rollback_chain(self, rollback_manager):
        """Test rollback chain execution."""
        action = Action(name="chain_test", action_type="test")

        # Create multiple snapshots for same action
        snapshot1 = await rollback_manager.create_snapshot(
            action, "action-123", state={"step": 1}
        )
        snapshot2 = await rollback_manager.create_snapshot(
            action, "action-123", state={"step": 2}
        )
        snapshot3 = await rollback_manager.create_snapshot(
            action, "action-123", state={"step": 3}
        )

        # Rollback chain
        results = await rollback_manager.rollback_chain("action-123")

        assert len(results) == 3
        # Should rollback in reverse order
        assert all(r.success for r in results)

    async def test_rollback_chain_empty(self, rollback_manager):
        """Test rollback chain with no snapshots."""
        results = await rollback_manager.rollback_chain("nonexistent-action")

        assert len(results) == 0

    def test_get_snapshot(self, rollback_manager, sample_action):
        """Test retrieving a snapshot."""
        snapshot = asyncio.run(
            rollback_manager.create_snapshot(sample_action, "action-123")
        )

        retrieved = rollback_manager.get_snapshot(snapshot.snapshot_id)
        assert retrieved is not None
        assert retrieved.snapshot_id == snapshot.snapshot_id

    def test_get_rollback_chain(self, rollback_manager, sample_action):
        """Test getting rollback chain."""
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-123"))
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-123"))

        chain = rollback_manager.get_rollback_chain("action-123")
        assert len(chain) == 2

    def test_get_rollback_logs(self, rollback_manager, sample_action):
        """Test getting rollback logs."""
        snapshot = asyncio.run(
            rollback_manager.create_snapshot(sample_action, "action-123")
        )
        asyncio.run(rollback_manager.rollback(snapshot))

        logs = rollback_manager.get_rollback_logs()
        assert len(logs) >= 1

    def test_clear_snapshots(self, rollback_manager, sample_action):
        """Test clearing snapshots."""
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-123"))
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-123"))

        count = rollback_manager.clear_snapshots("action-123")
        assert count == 2

        chain = rollback_manager.get_rollback_chain("action-123")
        assert len(chain) == 0

    def test_clear_all_snapshots(self, rollback_manager, sample_action):
        """Test clearing all snapshots."""
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-1"))
        asyncio.run(rollback_manager.create_snapshot(sample_action, "action-2"))

        count = rollback_manager.clear_snapshots()
        assert count == 2

    def test_get_stats(self, rollback_manager, sample_action):
        """Test getting rollback manager stats."""
        stats = rollback_manager.get_stats()

        assert "total_snapshots" in stats
        assert "max_snapshots" in stats
        assert "total_rollbacks" in stats

        # Create and rollback a snapshot
        snapshot = asyncio.run(
            rollback_manager.create_snapshot(sample_action, "action-123")
        )
        asyncio.run(rollback_manager.rollback(snapshot))

        stats = rollback_manager.get_stats()
        assert stats["total_snapshots"] == 1
        assert stats["successful_rollbacks"] == 1
        assert stats["success_rate"] == 1.0

    def test_register_compensation_handler(self, rollback_manager):
        """Test compensation handler registration."""

        def handler(state):
            return {"rolled_back": True}

        rollback_manager.register_compensation_handler("test_type", handler)
        assert "test_type" in rollback_manager._compensation_handlers

    def test_unregister_compensation_handler(self, rollback_manager):
        """Test compensation handler unregistration."""

        def handler(state):
            return {"rolled_back": True}

        rollback_manager.register_compensation_handler("test_type", handler)
        rollback_manager.unregister_compensation_handler("test_type")
        assert "test_type" not in rollback_manager._compensation_handlers


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for the full action execution flow."""

    async def test_full_success_flow(self):
        """Test complete successful execution flow."""
        validator = ActionValidator()
        rollback_manager = RollbackManager()
        executor = ActionExecutor(
            validator=validator,
            rollback_manager=rollback_manager,
        )

        async def handler(action):
            return {"processed": True, "data": action.payload}

        executor.register_handler("process", handler)

        action = Action(
            name="integration_test",
            action_type="process",
            payload={"key": "value"},
            priority=ActionPriority.HIGH,
        )

        outcome = await executor.execute(action)

        assert outcome.success is True
        assert outcome.result == {"processed": True, "data": {"key": "value"}}
        assert outcome.validation_time_ms >= 0
        assert outcome.execution_time_ms >= 0

        await executor.shutdown()

    async def test_full_failure_with_rollback(self):
        """Test complete failure flow with rollback."""
        validator = ActionValidator()
        rollback_manager = RollbackManager()
        executor = ActionExecutor(
            validator=validator,
            rollback_manager=rollback_manager,
        )

        def handler(action):
            raise ValueError("Processing failed")

        executor.register_handler("failing", handler)

        action = Action(
            name="failing_test",
            action_type="failing",
            payload={"data": "value"},
            enable_rollback=True,
        )

        outcome = await executor.execute(action)

        assert outcome.success is False
        assert outcome.status == ActionStatus.ROLLED_BACK
        assert outcome.rollback_time_ms >= 0

        # Verify rollback was logged
        logs = rollback_manager.get_rollback_logs()
        assert len(logs) >= 1

        await executor.shutdown()

    async def test_concurrent_execution(self):
        """Test concurrent action execution."""
        executor = ActionExecutor(max_concurrent=5)

        async def handler(action):
            await asyncio.sleep(0.01)
            return {"handled": action.name}

        executor.register_handler("concurrent", handler)

        actions = [
            Action(name=f"concurrent_{i}", action_type="concurrent") for i in range(10)
        ]

        start_time = time.time()
        outcomes = await executor.execute_batch(actions)
        duration = time.time() - start_time

        assert len(outcomes) == 10
        assert all(o.success for o in outcomes)
        # Should complete faster than sequential (10 * 0.01 = 0.1s)
        assert duration < 0.15  # Concurrent should be faster (allow some margin)

        await executor.shutdown()

    async def test_end_to_end_with_all_features(self):
        """Test end-to-end with all features enabled."""
        rate_limits = RateLimitConfig(
            max_requests_per_minute=100,
            burst_size=20,
        )
        budget = BudgetConfig(
            max_daily_actions=1000,
            max_concurrent_actions=10,
        )
        validator = ActionValidator(rate_limits=rate_limits, budget=budget)
        rollback_manager = RollbackManager()
        executor = ActionExecutor(
            validator=validator,
            rollback_manager=rollback_manager,
            enable_audit_logging=True,
        )

        execution_count = 0

        async def handler(action):
            nonlocal execution_count
            execution_count += 1
            if action.payload.get("fail"):
                raise ValueError("Intentional failure")
            return {"success": True, "count": execution_count}

        executor.register_handler("e2e", handler)

        # Mix of successful and failing actions
        actions = [
            Action(name="success_1", action_type="e2e", priority=ActionPriority.HIGH),
            Action(name="success_2", action_type="e2e", priority=ActionPriority.MEDIUM),
            Action(
                name="failure_1",
                action_type="e2e",
                payload={"fail": True},
                enable_rollback=True,
            ),
            Action(name="success_3", action_type="e2e", priority=ActionPriority.LOW),
        ]

        outcomes = await executor.execute_batch(actions, continue_on_error=True)

        assert len(outcomes) == 4
        assert outcomes[0].success is True
        assert outcomes[1].success is True
        assert outcomes[2].success is False
        assert outcomes[3].success is True

        # Check audit logs
        logs = executor.get_audit_logs()
        assert len(logs) == 4

        await executor.shutdown()
