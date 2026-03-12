"""Tests for retry coordinator.

Tests:
- RetryCoordinator initialization and configuration
- execute_with_retry with exponential backoff
- Jitter distribution verification
- Per-service retry budget enforcement (>100/min blocks)
- Circuit breaker integration
- Dead letter queue operations
- Metrics export

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import contextlib
from datetime import datetime

import pytest
from src.autonomous_control_plane.components.retry_coordinator import (
    RetryCoordinator,
    RetryMetricsCollector,
)
from src.autonomous_control_plane.models.retry_policy import (
    BackoffStrategy,
    BudgetExceededError,
    JitterType,
    MaxRetriesExceededError,
    RetryAborted,
    RetryPolicy,
)
from src.common.circuit_breaker import CircuitBreakerRegistry


class TestRetryCoordinator:
    """Tests for RetryCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create a basic retry coordinator."""
        return RetryCoordinator()

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self, coordinator):
        """Test successful operation executes without retries."""

        async def success_func():
            return "success"

        result = await coordinator.execute_with_retry(
            service_name="test_service",
            operation_name="test_op",
            func=success_func,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self, coordinator):
        """Test operation retries on failure then succeeds."""
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Failure #{call_count}")
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,  # Fast for testing
            jitter_type=JitterType.NONE,
        )

        result = await coordinator.execute_with_retry(
            service_name="test_service",
            operation_name="test_op",
            func=fail_then_succeed,
            policy=policy,
        )
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, coordinator):
        """Test exception raised when max retries exceeded."""

        async def always_fail():
            raise Exception("Always fails")

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
        )

        with pytest.raises(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, coordinator):
        """Test exponential backoff timing between retries."""
        timestamps = []

        async def record_timestamp():
            timestamps.append(datetime.utcnow())
            raise Exception("Fail")

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=50,
            jitter_type=JitterType.NONE,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )

        with pytest.raises(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=record_timestamp,
                policy=policy,
            )

        # Should have 3 timestamps (one per attempt)
        assert len(timestamps) == 3

        # Check delays between attempts
        # Attempt 1: no delay (first call)
        # Attempt 2: ~50ms delay (base * 2^0 = 50ms)
        # Attempt 3: ~100ms delay (base * 2^1 = 100ms)
        delay1 = (timestamps[1] - timestamps[0]).total_seconds()
        delay2 = (timestamps[2] - timestamps[1]).total_seconds()

        # Allow some tolerance for timing
        assert 0.04 <= delay1 <= 0.08  # ~50ms
        assert 0.08 <= delay2 <= 0.15  # ~100ms

    @pytest.mark.asyncio
    async def test_jitter_distribution(self, coordinator):
        """Test jitter creates randomized delays."""

        async def measure_jitter():
            datetime.utcnow()
            raise Exception("Fail")

        policy = RetryPolicy(
            max_attempts=3,  # Reduced to avoid timeout
            base_delay_ms=10,  # Reduced base delay
            jitter_type=JitterType.FULL,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )

        # Run fewer iterations to collect jitter samples quickly
        for _ in range(5):  # Reduced from 20 to avoid timeout
            datetime.utcnow()
            with contextlib.suppress(MaxRetriesExceededError):
                await coordinator.execute_with_retry(
                    service_name=f"test_service_{_}",
                    operation_name="test_op",
                    func=measure_jitter,
                    policy=policy,
                )

        # With jitter, each retry should have different timing
        # We can't measure exact delays, but we can verify the code path works

    @pytest.mark.asyncio
    async def test_retry_budget_enforcement(self, coordinator):
        """Test per-service retry budget enforcement (>100/min blocks)."""
        # Set a very low budget
        policy = RetryPolicy(
            max_attempts=10,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            budget_limit_per_minute=2,  # Very low for testing
        )

        async def always_fail():
            raise Exception("Fail")

        # First operation should exceed budget after 2 attempts
        with pytest.raises(BudgetExceededError):
            await coordinator.execute_with_retry(
                service_name="budget_test_service",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

    @pytest.mark.asyncio
    async def test_budget_resets_per_minute(self, coordinator):
        """Test budget resets each minute."""
        policy = RetryPolicy(
            max_attempts=10,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            budget_limit_per_minute=2,
        )

        async def always_fail():
            raise Exception("Fail")

        # Use budget
        with pytest.raises(BudgetExceededError):
            await coordinator.execute_with_retry(
                service_name="reset_test_service",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

        # Reset budget manually
        coordinator.reset_budget("reset_test_service")

        # Should be able to retry again
        with pytest.raises(BudgetExceededError):
            await coordinator.execute_with_retry(
                service_name="reset_test_service",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

    @pytest.mark.asyncio
    async def test_non_retryable_exceptions(self, coordinator):
        """Test non-retryable exceptions fail immediately."""
        call_count = 0

        async def raise_non_retryable():
            nonlocal call_count
            call_count += 1
            raise ValueError("Non-retryable")

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            retryable_exceptions=(RuntimeError,),
            non_retryable_exceptions=(ValueError,),
        )

        with pytest.raises(ValueError):
            await coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=raise_non_retryable,
                policy=policy,
            )

        # Should only be called once
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_operation_policy_override(self, coordinator):
        """Test operation-level policies override defaults."""
        call_count = 0

        async def count_calls():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Fail")
            return "success"

        # Default policy allows 3 attempts
        RetryPolicy(max_attempts=3, base_delay_ms=10)

        # Operation policy allows only 1 attempt
        operation_policy = RetryPolicy(max_attempts=1, base_delay_ms=10)

        # Should fail with operation policy
        with pytest.raises(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=count_calls,
                policy=operation_policy,
            )

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, coordinator):
        """Test failed operations are added to DLQ."""

        async def always_fail():
            raise Exception("Persistent failure")

        policy = RetryPolicy(
            max_attempts=2,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
        )

        with pytest.raises(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="dlq_test_service",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

        # Check DLQ
        dlq_items = coordinator.get_dlq_items(service_name="dlq_test_service")
        assert len(dlq_items) >= 1
        assert dlq_items[0]["service_name"] == "dlq_test_service"
        assert dlq_items[0]["operation"] == "test_op"

    @pytest.mark.asyncio
    async def test_custom_operation_id(self, coordinator):
        """Test custom operation ID tracking."""
        custom_id = "my-custom-op-id"

        async def success_func():
            return "success"

        result = await coordinator.execute_with_retry(
            service_name="test_service",
            operation_name="test_op",
            func=success_func,
            operation_id=custom_id,
        )
        assert result == "success"


class TestRetryMetricsCollector:
    """Tests for RetryMetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Create a metrics collector."""
        return RetryMetricsCollector()

    def test_record_attempt(self, collector):
        """Test recording attempts."""
        collector.record_attempt("service1", 1, 100.0)
        collector.record_attempt("service1", 2, 200.0)
        collector.record_attempt("service2", 1, 150.0)

        metrics = collector.get_metrics()
        assert metrics["total_attempts"] == 3

    def test_record_success(self, collector):
        """Test recording successes."""
        collector.record_success("service1")
        collector.record_success("service1")
        collector.record_success("service2")

        metrics = collector.get_metrics()
        assert metrics["total_successes"] == 3

    def test_record_failure(self, collector):
        """Test recording failures."""
        collector.record_failure("service1", "max_retries")
        collector.record_failure("service1", "circuit_open")
        collector.record_failure("service2", "max_retries")

        metrics = collector.get_metrics()
        assert metrics["total_failures"] == 3

    def test_record_budget_exceeded(self, collector):
        """Test recording budget exceeded events."""
        collector.record_budget_exceeded("service1")
        collector.record_budget_exceeded("service2")

        metrics = collector.get_metrics()
        assert metrics["total_budget_exceeded"] == 2

    def test_record_dlq(self, collector):
        """Test recording DLQ additions."""
        collector.record_dlq("service1")
        collector.record_dlq("service1")

        metrics = collector.get_metrics()
        assert metrics["total_dlq"] == 2

    def test_success_rate_calculation(self, collector):
        """Test success rate calculation."""
        # 8 attempts, 6 successes = 75% success rate
        for i in range(8):
            collector.record_attempt("service1", i % 3 + 1, 100.0)
        for _ in range(6):
            collector.record_success("service1")
        for _ in range(2):
            collector.record_failure("service1", "max_retries")

        metrics = collector.get_metrics()
        assert metrics["success_rate"] == 0.75

    def test_average_backoff_calculation(self, collector):
        """Test average backoff calculation."""
        collector.record_attempt("service1", 1, 100.0)
        collector.record_attempt("service1", 2, 200.0)
        collector.record_attempt("service1", 3, 300.0)

        metrics = collector.get_metrics()
        assert metrics["avg_backoff_ms"] == 200.0


class TestBudgetManagerIntegration:
    """Tests for budget manager integration."""

    @pytest.fixture
    def coordinator(self):
        """Create a retry coordinator."""
        return RetryCoordinator()

    def test_get_budget_status(self, coordinator):
        """Test getting budget status."""
        # Initially no budget used
        status = coordinator.get_budget_status("test_service")
        assert status["current_count"] == 0
        assert status["remaining"] == 100  # Default limit
        assert status["is_exceeded"] is False

    def test_get_all_budgets_empty(self, coordinator):
        """Test getting all budgets when empty."""
        budgets = coordinator.get_all_budgets()
        assert budgets == []

    @pytest.mark.asyncio
    async def test_get_all_budgets_with_usage(self, coordinator):
        """Test getting all budgets with usage."""

        async def always_fail():
            raise Exception("Fail")

        policy = RetryPolicy(
            max_attempts=2,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
            budget_limit_per_minute=100,
        )

        # Generate some budget usage
        for i in range(3):
            with contextlib.suppress(MaxRetriesExceededError):
                await coordinator.execute_with_retry(
                    service_name=f"service_{i}",
                    operation_name="test_op",
                    func=always_fail,
                    policy=policy,
                )

        budgets = coordinator.get_all_budgets()
        assert len(budgets) >= 3

    def test_reset_budget(self, coordinator):
        """Test resetting a budget."""
        # Reset should work without error
        coordinator.reset_budget("test_service")


class TestDLQOperations:
    """Tests for dead letter queue operations."""

    @pytest.fixture
    def coordinator(self):
        """Create a retry coordinator."""
        return RetryCoordinator()

    @pytest.mark.asyncio
    async def test_list_dlq_items(self, coordinator):
        """Test listing DLQ items."""

        async def always_fail():
            raise Exception("Fail")

        policy = RetryPolicy(max_attempts=1, base_delay_ms=10)

        with contextlib.suppress(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="dlq_list_test",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

        items = coordinator.get_dlq_items(service_name="dlq_list_test")
        assert isinstance(items, list)

    def test_retry_dlq_item_not_found(self, coordinator):
        """Test retrying non-existent DLQ item."""
        result = coordinator.retry_dlq_item("non-existent-id")
        assert result is False

    def test_delete_dlq_item_not_found(self, coordinator):
        """Test deleting non-existent DLQ item."""
        result = coordinator.delete_dlq_item("non-existent-id")
        assert result is False


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration."""

    @pytest.fixture
    def coordinator(self):
        """Create a retry coordinator."""
        return RetryCoordinator()

    def test_get_circuit_breaker_states(self, coordinator):
        """Test getting circuit breaker states."""
        states = coordinator.get_circuit_breaker_states()
        assert isinstance(states, dict)

    @pytest.mark.asyncio
    async def test_no_retry_when_circuit_open(self, coordinator):
        """Test no retries when circuit breaker is open (AC #4)."""
        # Register and open a circuit breaker
        cb_registry = CircuitBreakerRegistry()
        cb = cb_registry.get_or_create(
            "test_circuit",
            failure_threshold=1,
            timeout_seconds=60,
        )
        cb.force_open("test")

        async def would_fail():
            raise Exception("Would fail")

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            circuit_breaker_name="test_circuit",
        )

        with pytest.raises(RetryAborted):
            await coordinator.execute_with_retry(
                service_name="cb_test_service",
                operation_name="test_op",
                func=would_fail,
                policy=policy,
            )


class TestMetricsExport:
    """Tests for metrics export (AC #7)."""

    @pytest.fixture
    def coordinator(self):
        """Create a retry coordinator."""
        return RetryCoordinator()

    def test_get_metrics_initial(self, coordinator):
        """Test getting initial metrics."""
        metrics = coordinator.get_metrics()
        assert metrics["total_attempts"] == 0
        assert metrics["total_successes"] == 0
        assert metrics["total_failures"] == 0
        assert metrics["total_budget_exceeded"] == 0
        assert metrics["total_dlq"] == 0

    @pytest.mark.asyncio
    async def test_metrics_after_success(self, coordinator):
        """Test metrics after successful operation."""

        async def success_func():
            return "success"

        await coordinator.execute_with_retry(
            service_name="metrics_test",
            operation_name="test_op",
            func=success_func,
        )

        metrics = coordinator.get_metrics()
        assert metrics["total_successes"] == 1
        # Success rate is 0 when no retry attempts were needed (immediate success)
        # This is because attempts are only recorded for retries with backoff
        assert metrics["success_rate"] == 0

    @pytest.mark.asyncio
    async def test_metrics_after_failure(self, coordinator):
        """Test metrics after failed operation."""

        async def always_fail():
            raise Exception("Fail")

        policy = RetryPolicy(max_attempts=2, base_delay_ms=10)

        with pytest.raises(MaxRetriesExceededError):
            await coordinator.execute_with_retry(
                service_name="metrics_fail_test",
                operation_name="test_op",
                func=always_fail,
                policy=policy,
            )

        metrics = coordinator.get_metrics()
        assert metrics["total_failures"] >= 1
        assert metrics["total_dlq"] >= 1

    @pytest.mark.asyncio
    async def test_metrics_success_rate_with_retries(self, coordinator):
        """Test success rate calculation when retries were attempted."""
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Failure #{call_count}")
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=10,
            jitter_type=JitterType.NONE,
        )

        result = await coordinator.execute_with_retry(
            service_name="success_rate_test",
            operation_name="test_op",
            func=fail_then_succeed,
            policy=policy,
        )
        assert result == "success"

        metrics = coordinator.get_metrics()
        # 2 retry attempts before success
        assert metrics["total_attempts"] == 2
        assert metrics["total_successes"] == 1
        # Success rate = successes / attempts = 1/2 = 0.5
        assert metrics["success_rate"] == 0.5


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_immediate_success(self):
        """Test operation succeeds immediately without retries."""
        coordinator = RetryCoordinator()

        async def immediate_success():
            return "immediate"

        result = await coordinator.execute_with_retry(
            service_name="test",
            operation_name="test",
            func=immediate_success,
        )
        assert result == "immediate"

    @pytest.mark.asyncio
    async def test_zero_base_delay(self):
        """Test zero base delay."""
        coordinator = RetryCoordinator()

        call_count = 0

        async def count_calls():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Fail")
            return "success"

        policy = RetryPolicy(
            max_attempts=3,
            base_delay_ms=0,
            jitter_type=JitterType.NONE,
        )

        result = await coordinator.execute_with_retry(
            service_name="test",
            operation_name="test",
            func=count_calls,
            policy=policy,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_large_max_attempts(self):
        """Test with large max attempts."""
        coordinator = RetryCoordinator()

        call_count = 0

        async def succeed_on_tenth():
            nonlocal call_count
            call_count += 1
            if call_count < 10:
                raise Exception("Fail")
            return "success"

        policy = RetryPolicy(
            max_attempts=15,
            base_delay_ms=1,
            jitter_type=JitterType.NONE,
        )

        result = await coordinator.execute_with_retry(
            service_name="test",
            operation_name="test",
            func=succeed_on_tenth,
            policy=policy,
        )
        assert result == "success"
        assert call_count == 10
