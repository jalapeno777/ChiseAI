"""Tests for Retry Coordinator (ST-NS-039)."""

import pytest
from unittest.mock import Mock
from src.autonomous_control_plane.models.retry_policy import (
    RetryPolicy,
    BackoffStrategy,
    JitterType,
)
from src.autonomous_control_plane.components.retry_coordinator import (
    RetryCoordinator,
    RetryBudgetExceeded,
    RetryAborted,
)


class TestRetryPolicy:
    """Test retry policy models."""

    def test_retry_policy_defaults(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay_ms == 100
        assert policy.max_delay_ms == 30000
        assert policy.backoff_strategy == BackoffStrategy.EXPONENTIAL

    def test_exponential_backoff_calculation(self):
        policy = RetryPolicy(
            base_delay_ms=100,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
        )
        delay0 = policy.calculate_delay(0)
        delay1 = policy.calculate_delay(1)
        delay2 = policy.calculate_delay(2)

        assert delay0 == 0.1  # 100ms
        assert delay1 == 0.2  # 200ms
        assert delay2 == 0.4  # 400ms

    def test_linear_backoff_calculation(self):
        policy = RetryPolicy(
            base_delay_ms=100,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_type=JitterType.NONE,
        )
        delay0 = policy.calculate_delay(0)
        delay1 = policy.calculate_delay(1)

        assert delay0 == 0.1  # 100ms
        assert delay1 == 0.2  # 200ms

    def test_fixed_backoff_calculation(self):
        policy = RetryPolicy(
            base_delay_ms=100,
            backoff_strategy=BackoffStrategy.FIXED,
            jitter_type=JitterType.NONE,
        )
        delay0 = policy.calculate_delay(0)
        delay1 = policy.calculate_delay(5)

        assert delay0 == 0.1
        assert delay1 == 0.1

    def test_max_delay_enforced(self):
        policy = RetryPolicy(
            base_delay_ms=1000,
            max_delay_ms=5000,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
        )
        # 1000 * 2^10 = 1,024,000ms but max is 5000
        delay = policy.calculate_delay(10)
        assert delay == 5.0  # 5000ms


class TestRetryCoordinator:
    """Test retry coordinator functionality."""

    def setup_method(self):
        self.coordinator = RetryCoordinator()

    @pytest.mark.asyncio
    async def test_successful_execution_no_retry(self):
        operation = Mock(return_value="success")
        policy = RetryPolicy(max_attempts=3)

        result = await self.coordinator.execute_with_retry(
            operation, policy, "test-service"
        )

        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self):
        operation = Mock(side_effect=[Exception("fail"), "success"])
        policy = RetryPolicy(max_attempts=3, base_delay_ms=10)

        result = await self.coordinator.execute_with_retry(
            operation, policy, "test-service"
        )

        assert result == "success"
        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        operation = Mock(side_effect=Exception("always fails"))
        policy = RetryPolicy(max_attempts=2, base_delay_ms=10)

        with pytest.raises(Exception, match="always fails"):
            await self.coordinator.execute_with_retry(operation, policy, "test-service")

        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_execution(self):
        cb = Mock()
        cb.can_execute.return_value = False
        operation = Mock()
        policy = RetryPolicy()

        with pytest.raises(RetryAborted, match="Circuit breaker is open"):
            await self.coordinator.execute_with_retry(
                operation, policy, "test-service", circuit_breaker=cb
            )

    @pytest.mark.asyncio
    async def test_retry_budget_enforcement(self):
        # Exhaust budget using current minute key
        from datetime import datetime

        minute_key = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")
        self.coordinator._budgets["test-service"] = {
            minute_key: 100  # Budget limit reached
        }

        operation = Mock()
        policy = RetryPolicy(budget_limit_per_minute=100)

        with pytest.raises(RetryBudgetExceeded):
            await self.coordinator.execute_with_retry(operation, policy, "test-service")

    def test_get_retry_budget(self):
        budget = self.coordinator.get_retry_budget("test-service")
        assert budget["used"] == 0
        assert budget["limit"] == 100
        assert budget["remaining"] == 100

    def test_reset_budget(self):
        from datetime import datetime

        minute_key = datetime.utcnow().strftime("%Y-%m-%d-%H-%M")
        self.coordinator._budgets["test-service"] = {minute_key: 50}
        self.coordinator.reset_budget("test-service")
        assert self.coordinator._budgets["test-service"] == {}
