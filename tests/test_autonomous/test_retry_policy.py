"""Tests for retry policy models.

Tests:
- RetryPolicy validation and configuration
- Backoff calculation with different strategies
- Jitter distribution verification
- RetryBudget tracking
- DeadLetterQueueItem creation

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

from datetime import datetime

import pytest
from src.autonomous_control_plane.models.retry_policy import (
    BackoffStrategy,
    BudgetExceededError,
    DeadLetterQueueItem,
    JitterType,
    MaxRetriesExceededError,
    RetryAborted,
    RetryBudget,
    RetryOperation,
    RetryPolicy,
    RetryStatus,
)


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_default_values(self):
        """Test default policy values."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay_ms == 100
        assert policy.max_delay_ms == 30000
        assert policy.jitter_factor == 0.1
        assert policy.budget_limit_per_minute == 100
        assert policy.circuit_breaker_name is None
        assert policy.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert policy.jitter_type == JitterType.FULL

    def test_custom_values(self):
        """Test custom policy configuration."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=200,
            max_delay_ms=5000,
            jitter_factor=0.2,
            budget_limit_per_minute=50,
            circuit_breaker_name="test_cb",
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_type=JitterType.EQUAL,
        )
        assert policy.max_attempts == 5
        assert policy.base_delay_ms == 200
        assert policy.max_delay_ms == 5000
        assert policy.jitter_factor == 0.2
        assert policy.budget_limit_per_minute == 50
        assert policy.circuit_breaker_name == "test_cb"
        assert policy.backoff_strategy == BackoffStrategy.LINEAR
        assert policy.jitter_type == JitterType.EQUAL

    def test_invalid_max_attempts(self):
        """Test validation of max_attempts."""
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryPolicy(max_attempts=-1)

    def test_invalid_base_delay(self):
        """Test validation of base_delay_ms."""
        with pytest.raises(ValueError, match="base_delay_ms must be >= 0"):
            RetryPolicy(base_delay_ms=-1)

    def test_invalid_max_delay(self):
        """Test validation of max_delay_ms."""
        with pytest.raises(ValueError, match="max_delay_ms must be >= base_delay_ms"):
            RetryPolicy(base_delay_ms=100, max_delay_ms=50)

    def test_invalid_jitter_factor(self):
        """Test validation of jitter_factor."""
        with pytest.raises(
            ValueError, match="jitter_factor must be between 0.0 and 1.0"
        ):
            RetryPolicy(jitter_factor=-0.1)
        with pytest.raises(
            ValueError, match="jitter_factor must be between 0.0 and 1.0"
        ):
            RetryPolicy(jitter_factor=1.5)

    def test_invalid_budget_limit(self):
        """Test validation of budget_limit_per_minute."""
        with pytest.raises(ValueError, match="budget_limit_per_minute must be >= 1"):
            RetryPolicy(budget_limit_per_minute=0)


class TestBackoffCalculation:
    """Tests for delay calculation with different strategies."""

    def test_exponential_backoff_first_attempt(self):
        """Test exponential backoff for first attempt."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        delay = policy.calculate_delay(attempt=1)
        assert delay == 100  # 100 * (2 ** 0) = 100

    def test_exponential_backoff_second_attempt(self):
        """Test exponential backoff for second attempt."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        delay = policy.calculate_delay(attempt=2)
        assert delay == 200  # 100 * (2 ** 1) = 200

    def test_exponential_backoff_third_attempt(self):
        """Test exponential backoff for third attempt."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        delay = policy.calculate_delay(attempt=3)
        assert delay == 400  # 100 * (2 ** 2) = 400

    def test_exponential_backoff_max_cap(self):
        """Test exponential backoff respects max_delay_ms cap."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
            max_delay_ms=500,
        )
        # 4th attempt would be 800ms, but capped at 500
        delay = policy.calculate_delay(attempt=4)
        assert delay == 500

    def test_linear_backoff(self):
        """Test linear backoff strategy."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        assert policy.calculate_delay(attempt=1) == 100
        assert policy.calculate_delay(attempt=2) == 200
        assert policy.calculate_delay(attempt=3) == 300

    def test_fixed_backoff(self):
        """Test fixed backoff strategy."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.FIXED,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        assert policy.calculate_delay(attempt=1) == 100
        assert policy.calculate_delay(attempt=2) == 100
        assert policy.calculate_delay(attempt=10) == 100


class TestJitterCalculation:
    """Tests for jitter algorithms."""

    def test_no_jitter(self):
        """Test no jitter produces consistent results."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.NONE,
            base_delay_ms=100,
        )
        delays = [policy.calculate_delay(attempt=2) for _ in range(10)]
        # All delays should be the same (200ms)
        assert all(d == 200 for d in delays)

    def test_full_jitter_range(self):
        """Test full jitter produces values in expected range."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.FULL,
            base_delay_ms=100,
        )
        delays = [policy.calculate_delay(attempt=2) for _ in range(100)]
        # Full jitter: random(0, 200)
        assert all(0 <= d <= 200 for d in delays)
        # Should have some variation
        assert len(set(delays)) > 1

    def test_full_jitter_distribution(self):
        """Test full jitter has reasonable distribution."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.FULL,
            base_delay_ms=100,
        )
        delays = [policy.calculate_delay(attempt=2) for _ in range(1000)]
        # Check that we have values across the range
        assert min(delays) < 50  # Some low values
        assert max(delays) > 150  # Some high values
        # Average should be roughly around 100ms (half of max)
        avg_delay = sum(delays) / len(delays)
        assert 50 < avg_delay < 150

    def test_equal_jitter_range(self):
        """Test equal jitter produces values in expected range."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.EQUAL,
            base_delay_ms=100,
        )
        delays = [policy.calculate_delay(attempt=2) for _ in range(100)]
        # Equal jitter: delay/2 + random(0, delay/2) = 100 + random(0, 100)
        assert all(100 <= d <= 200 for d in delays)

    def test_decorrelated_jitter_range(self):
        """Test decorrelated jitter produces values in expected range."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.DECORRELATED,
            base_delay_ms=100,
        )
        delays = [policy.calculate_delay(attempt=2) for _ in range(100)]
        # Decorrelated: random(base, delay * 3) = random(100, 600)
        assert all(100 <= d <= 600 for d in delays)

    def test_jitter_prevents_thundering_herd(self):
        """Test that jitter spreads out retry attempts."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_type=JitterType.FULL,
            base_delay_ms=100,
            max_delay_ms=1000,
        )
        # Simulate 100 concurrent retries
        delays = [policy.calculate_delay(attempt=3) for _ in range(100)]
        # Without jitter, all would be 400ms
        # With jitter, they should be spread out
        unique_delays = len(set(delays))
        assert unique_delays > 50  # Most should be unique


class TestRetryBudget:
    """Tests for RetryBudget tracking."""

    def test_initial_state(self):
        """Test initial budget state."""
        budget = RetryBudget(service_name="test_service")
        assert budget.service_name == "test_service"
        assert budget.current_count == 0
        assert budget.limit == 100
        assert budget.is_exceeded is False

    def test_record_attempt_within_limit(self):
        """Test recording attempts within budget."""
        budget = RetryBudget(service_name="test_service", limit=5)
        assert budget.record_attempt() is True
        assert budget.current_count == 1
        assert budget.record_attempt() is True
        assert budget.current_count == 2
        assert budget.is_exceeded is False

    def test_record_attempt_exceeds_limit(self):
        """Test recording attempts that exceed budget."""
        budget = RetryBudget(service_name="test_service", limit=2)
        assert budget.record_attempt() is True
        assert budget.record_attempt() is True
        assert budget.record_attempt() is False  # Exceeds limit
        assert budget.is_exceeded is True

    def test_window_reset(self):
        """Test budget resets in new time window."""
        budget = RetryBudget(service_name="test_service", limit=2)
        budget.record_attempt()
        budget.record_attempt()
        assert budget.is_exceeded is True

        # Simulate new minute by advancing window_start
        from datetime import timedelta

        budget.window_start = budget.window_start - timedelta(minutes=1)

        # Should be able to record again
        assert budget.record_attempt() is True
        assert budget.is_exceeded is False

    def test_to_dict(self):
        """Test budget serialization."""
        budget = RetryBudget(service_name="test_service", limit=100)
        budget.record_attempt()
        budget.record_attempt()

        data = budget.to_dict()
        assert data["service_name"] == "test_service"
        assert data["current_count"] == 2
        assert data["limit"] == 100
        assert data["remaining"] == 98
        assert data["is_exceeded"] is False


class TestDeadLetterQueueItem:
    """Tests for DeadLetterQueueItem."""

    def test_creation(self):
        """Test DLQ item creation."""
        item = DeadLetterQueueItem(
            id="test-id",
            service_name="test_service",
            operation="test_operation",
            payload={"key": "value"},
            error_message="Something failed",
            retry_count=3,
        )
        assert item.id == "test-id"
        assert item.service_name == "test_service"
        assert item.operation == "test_operation"
        assert item.payload == {"key": "value"}
        assert item.error_message == "Something failed"
        assert item.retry_count == 3
        assert item.status == RetryStatus.DLQ

    def test_to_dict(self):
        """Test DLQ item serialization."""
        item = DeadLetterQueueItem(
            id="test-id",
            service_name="test_service",
            operation="test_operation",
            payload={"key": "value"},
            error_message="Something failed",
            retry_count=3,
        )
        data = item.to_dict()
        assert data["id"] == "test-id"
        assert data["service_name"] == "test_service"
        assert data["operation"] == "test_operation"
        assert data["payload"] == {"key": "value"}
        assert data["error_message"] == "Something failed"
        assert data["retry_count"] == 3
        assert data["status"] == "DLQ"


class TestRetryOperation:
    """Tests for RetryOperation."""

    @pytest.mark.asyncio
    async def test_creation(self):
        """Test operation creation."""

        async def test_func():
            return "result"

        operation = RetryOperation(
            id="test-op-id",
            service_name="test_service",
            operation_name="test_op",
            func=test_func,
        )
        assert operation.id == "test-op-id"
        assert operation.service_name == "test_service"
        assert operation.operation_name == "test_op"
        assert operation.status == RetryStatus.PENDING
        assert operation.attempt_count == 0

    def test_to_dict(self):
        """Test operation serialization."""

        async def test_func():
            return "result"

        operation = RetryOperation(
            id="test-op-id",
            service_name="test_service",
            operation_name="test_op",
            func=test_func,
        )
        operation.attempt_count = 2
        operation.status = RetryStatus.IN_PROGRESS

        data = operation.to_dict()
        assert data["id"] == "test-op-id"
        assert data["service_name"] == "test_service"
        assert data["operation_name"] == "test_op"
        assert data["attempt_count"] == 2
        assert data["status"] == "IN_PROGRESS"
        assert "func" not in data  # Function should not be serialized


class TestPolicySerialization:
    """Tests for policy serialization/deserialization."""

    def test_to_dict(self):
        """Test policy to dictionary conversion."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_ms=200,
            circuit_breaker_name="test_cb",
        )
        data = policy.to_dict()
        assert data["max_attempts"] == 5
        assert data["base_delay_ms"] == 200
        assert data["circuit_breaker_name"] == "test_cb"
        assert data["backoff_strategy"] == "EXPONENTIAL"
        assert data["jitter_type"] == "FULL"

    def test_from_dict(self):
        """Test policy from dictionary creation."""
        data = {
            "max_attempts": 5,
            "base_delay_ms": 200,
            "max_delay_ms": 10000,
            "jitter_factor": 0.2,
            "budget_limit_per_minute": 50,
            "circuit_breaker_name": "test_cb",
            "backoff_strategy": "LINEAR",
            "jitter_type": "EQUAL",
        }
        policy = RetryPolicy.from_dict(data)
        assert policy.max_attempts == 5
        assert policy.base_delay_ms == 200
        assert policy.max_delay_ms == 10000
        assert policy.jitter_factor == 0.2
        assert policy.budget_limit_per_minute == 50
        assert policy.circuit_breaker_name == "test_cb"
        assert policy.backoff_strategy == BackoffStrategy.LINEAR
        assert policy.jitter_type == JitterType.EQUAL

    def test_from_dict_defaults(self):
        """Test policy from dictionary with defaults."""
        data = {}
        policy = RetryPolicy.from_dict(data)
        assert policy.max_attempts == 3
        assert policy.base_delay_ms == 100
        assert policy.backoff_strategy == BackoffStrategy.EXPONENTIAL


class TestExceptions:
    """Tests for custom exceptions."""

    def test_retry_aborted(self):
        """Test RetryAborted exception."""
        exc = RetryAborted("Circuit breaker open")
        assert str(exc) == "Circuit breaker open"
        assert isinstance(exc, Exception)

    def test_budget_exceeded_error(self):
        """Test BudgetExceededError exception."""
        exc = BudgetExceededError("Budget exceeded")
        assert str(exc) == "Budget exceeded"
        assert isinstance(exc, Exception)

    def test_max_retries_exceeded_error(self):
        """Test MaxRetriesExceededError exception."""
        exc = MaxRetriesExceededError("Max retries exceeded")
        assert str(exc) == "Max retries exceeded"
        assert isinstance(exc, Exception)
