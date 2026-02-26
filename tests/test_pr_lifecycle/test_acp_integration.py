"""Tests for ACP integration with PR lifecycle.

Tests circuit breaker integration, retry coordinator integration,
and graceful degradation when ACP components are unavailable.

ST-AUTO-006: EP-NS-008 Integration for PR Pipeline
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add paths for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "scripts" / "pr_lifecycle")
)

from circuit_breaker_pr import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    PRCircuitBreakerRegistry,
    get_global_registry,
    with_circuit_breaker,
)
from retry_pr_operations import (
    BudgetExceededError,
    MaxRetriesExceededError,
    PRRetryCoordinator,
    RetryBudgetManager,
    RetryPolicy,
    get_global_coordinator,
    with_retry,
)
from acp_integration import (
    ACPHealthStatus,
    ACPIntegrationConfig,
    ACPIntegrationManager,
    get_global_manager,
    reset_global_manager,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_is_closed(self):
        """Test that circuit breaker starts in closed state."""
        cb = CircuitBreaker("test_service")
        assert cb.is_closed()
        assert not cb.is_open()
        assert not cb.is_half_open()

    def test_successful_calls_remain_closed(self):
        """Test that successful calls keep circuit closed."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=3))

        for _ in range(5):
            result = cb.call(lambda: "success")
            assert result == "success"

        assert cb.is_closed()
        assert cb._metrics.success_count == 5

    def test_circuit_opens_after_failures(self):
        """Test that circuit opens after threshold failures."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=3))

        # Fail 3 times
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open()
        assert cb._metrics.failure_count == 3

    def test_open_circuit_rejects_calls(self):
        """Test that open circuit rejects new calls."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=1))

        # Fail once to open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open()

        # Next call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not execute")

    def test_fallback_execution_when_open(self):
        """Test that fallback is executed when circuit is open."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=1))

        # Fail once to open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # Call with fallback should execute fallback
        result = cb.call(lambda: "primary", fallback=lambda: "fallback")
        assert result == "fallback"

    def test_half_open_after_recovery_timeout(self):
        """Test circuit transitions to half-open after recovery timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,  # Short timeout for testing
        )
        cb = CircuitBreaker("test_service", config)

        # Fail to open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open()

        # Wait for recovery timeout
        time.sleep(0.15)

        # Check state (should be half-open on next check)
        cb._check_auto_transition()
        assert cb.is_half_open()

    def test_circuit_closes_after_successes_in_half_open(self):
        """Test circuit closes after consecutive successes in half-open."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
            success_threshold=2,
            half_open_max_calls=3,
        )
        cb = CircuitBreaker("test_service", config)

        # Open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        time.sleep(0.15)
        cb._check_auto_transition()
        assert cb.is_half_open()

        # Successes should close circuit
        cb.call(lambda: "success1")
        cb.call(lambda: "success2")

        assert cb.is_closed()

    def test_half_open_failure_reopens_circuit(self):
        """Test that failure in half-open reopens circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker("test_service", config)

        # Open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        time.sleep(0.15)
        cb._check_auto_transition()
        assert cb.is_half_open()

        # Failure in half-open should reopen
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail again")))

        assert cb.is_open()

    def test_force_open_and_close(self):
        """Test manual force open and close."""
        cb = CircuitBreaker("test_service")

        cb.force_open("manual test")
        assert cb.is_open()

        cb.force_close("manual test")
        assert cb.is_closed()

    def test_metrics_tracking(self):
        """Test that metrics are tracked correctly."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=5))

        cb.call(lambda: "success1")
        cb.call(lambda: "success2")

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        metrics = cb.get_metrics()
        assert metrics["success_count"] == 2
        assert metrics["failure_count"] == 1
        assert metrics["state"] == "CLOSED"

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        cb = CircuitBreaker("test_service", CircuitBreakerConfig(failure_threshold=1))

        # Open circuit
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open()

        # Reset
        cb.reset()
        assert cb.is_closed()
        assert cb._metrics.failure_count == 0
        assert cb._metrics.success_count == 0


class TestPRCircuitBreakerRegistry:
    """Test PR circuit breaker registry."""

    def test_get_circuit_breaker_creates_new(self):
        """Test that get creates new circuit breaker."""
        registry = PRCircuitBreakerRegistry()
        cb = registry.get_circuit_breaker("gitea_api")

        assert cb.name == "gitea_api"
        assert cb.is_closed()

    def test_get_circuit_breaker_returns_existing(self):
        """Test that get returns existing circuit breaker."""
        registry = PRCircuitBreakerRegistry()
        cb1 = registry.get_circuit_breaker("gitea_api")
        cb2 = registry.get_circuit_breaker("gitea_api")

        assert cb1 is cb2

    def test_get_all_states(self):
        """Test getting all circuit breaker states."""
        registry = PRCircuitBreakerRegistry()
        registry.get_circuit_breaker("gitea_api")
        registry.get_circuit_breaker("discord_notifications")

        states = registry.get_all_states()
        assert "gitea_api" in states
        assert "discord_notifications" in states

    def test_force_open_and_close(self):
        """Test force open and close through registry."""
        registry = PRCircuitBreakerRegistry()
        registry.get_circuit_breaker("gitea_api")

        registry.force_open("gitea_api", "test")
        cb = registry.get_circuit_breaker("gitea_api")
        assert cb.is_open()

        registry.force_close("gitea_api", "test")
        assert cb.is_closed()

    def test_reset_all(self):
        """Test resetting all circuit breakers."""
        registry = PRCircuitBreakerRegistry()
        registry.get_circuit_breaker("gitea_api")
        registry.get_circuit_breaker("discord_notifications")

        registry.force_open("gitea_api", "test")
        registry.force_open("discord_notifications", "test")

        registry.reset_all()

        assert registry.get_circuit_breaker("gitea_api").is_closed()
        assert registry.get_circuit_breaker("discord_notifications").is_closed()


class TestRetryCoordinator:
    """Test retry coordinator functionality."""

    def test_successful_execution_no_retry(self):
        """Test that successful execution doesn't retry."""
        coordinator = PRRetryCoordinator()

        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = coordinator.execute_with_retry(
            service_name="test_service",
            operation_name="test_op",
            func=operation,
        )

        assert result == "success"
        assert call_count == 1

    def test_retry_on_failure(self):
        """Test that operation is retried on failure."""
        coordinator = PRRetryCoordinator()

        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary failure")
            return "success"

        result = coordinator.execute_with_retry(
            service_name="test_service",
            operation_name="test_op",
            func=operation,
            policy=RetryPolicy(max_attempts=5),
        )

        assert result == "success"
        assert call_count == 3

    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        coordinator = PRRetryCoordinator()

        def operation():
            raise ConnectionError("persistent failure")

        with pytest.raises(MaxRetriesExceededError):
            coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=operation,
                policy=RetryPolicy(max_attempts=3),
            )

    def test_non_retryable_exception(self):
        """Test that non-retryable exceptions fail immediately."""
        coordinator = PRRetryCoordinator()

        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("non-retryable")

        with pytest.raises(ValueError):
            coordinator.execute_with_retry(
                service_name="test_service",
                operation_name="test_op",
                func=operation,
            )

        assert call_count == 1

    def test_budget_enforcement(self):
        """Test that retry budget is enforced."""
        coordinator = PRRetryCoordinator()

        def failing_func():
            raise ConnectionError("fail")

        # Exhaust budget - use max_attempts=2 so budget is checked on retry
        for _ in range(10):
            try:
                coordinator.execute_with_retry(
                    service_name="budget_test",
                    operation_name="test_op",
                    func=failing_func,
                    policy=RetryPolicy(
                        max_attempts=2,  # Budget checked before 2nd attempt
                        budget_limit_per_minute=10,
                    ),
                )
            except Exception:
                pass

        # Next retry should exceed budget - use max_attempts=2 so budget is checked
        with pytest.raises(BudgetExceededError):
            coordinator.execute_with_retry(
                service_name="budget_test",
                operation_name="test_op",
                func=failing_func,
                policy=RetryPolicy(
                    max_attempts=2,  # Budget checked before 2nd attempt
                    budget_limit_per_minute=10,
                ),
            )

    def test_backoff_calculation(self):
        """Test backoff delay calculation."""
        coordinator = PRRetryCoordinator()
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0, jitter=False)

        delay1 = coordinator._calculate_backoff(1, policy)
        delay2 = coordinator._calculate_backoff(2, policy)
        delay3 = coordinator._calculate_backoff(3, policy)

        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 4.0

    def test_backoff_with_jitter(self):
        """Test that jitter adds randomness to backoff."""
        coordinator = PRRetryCoordinator()
        policy = RetryPolicy(base_delay=1.0, jitter=True, jitter_max=0.5)

        delays = [coordinator._calculate_backoff(1, policy) for _ in range(10)]

        # All delays should be >= base_delay
        assert all(d >= 1.0 for d in delays)

        # There should be some variation (unlikely all same with jitter)
        assert len(set(delays)) > 1

    def test_metrics_collection(self):
        """Test that metrics are collected."""
        coordinator = PRRetryCoordinator()

        # Successful operation
        coordinator.execute_with_retry(
            service_name="metrics_test",
            operation_name="success_op",
            func=lambda: "success",
        )

        # Failed operation
        try:
            coordinator.execute_with_retry(
                service_name="metrics_test",
                operation_name="fail_op",
                func=lambda: (_ for _ in ()).throw(ConnectionError("fail")),
                policy=RetryPolicy(max_attempts=1),
            )
        except Exception:
            pass

        metrics = coordinator.get_metrics()
        assert metrics["successes"].get("metrics_test", 0) >= 1
        assert len(metrics["failures"]) > 0


class TestRetryBudgetManager:
    """Test retry budget manager."""

    def test_budget_allows_within_limit(self):
        """Test that budget allows retries within limit."""
        manager = RetryBudgetManager(default_limit=5)

        for _ in range(5):
            allowed, remaining = manager.check_and_consume("test_service", 5)
            assert allowed
            assert remaining >= 0

    def test_budget_denies_over_limit(self):
        """Test that budget denies retries over limit."""
        manager = RetryBudgetManager(default_limit=3)

        # Use up budget
        for _ in range(3):
            manager.check_and_consume("test_service", 3)

        # Next should be denied
        allowed, remaining = manager.check_and_consume("test_service", 3)
        assert not allowed
        assert remaining == 0

    def test_budget_status(self):
        """Test getting budget status."""
        manager = RetryBudgetManager(default_limit=10)

        manager.check_and_consume("test_service", 10)
        manager.check_and_consume("test_service", 10)

        status = manager.get_budget_status("test_service")
        assert status["service"] == "test_service"
        assert status["current_count"] == 2
        assert status["limit"] == 10
        assert status["remaining"] == 8


class TestACPIntegrationManager:
    """Test ACP integration manager."""

    def setup_method(self):
        """Reset global manager before each test."""
        reset_global_manager()

    def test_initialization(self):
        """Test that manager initializes correctly."""
        config = ACPIntegrationConfig(
            enable_circuit_breaker=True,
            enable_retry_coordinator=True,
        )
        manager = ACPIntegrationManager(config=config)

        assert manager._config is config
        assert manager._circuit_registry is not None
        assert manager._retry_coordinator is not None

    def test_execute_with_resilience_success(self):
        """Test successful execution with resilience."""
        manager = ACPIntegrationManager()

        result = manager.execute_with_resilience(
            service_name="test_service",
            operation_name="test_op",
            func=lambda: "success",
        )

        assert result == "success"

    def test_execute_with_resilience_retry(self):
        """Test that resilience stack includes retry."""
        manager = ACPIntegrationManager()

        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "success"

        result = manager.execute_with_resilience(
            service_name="test_service",
            operation_name="test_op",
            func=operation,
        )

        assert result == "success"
        assert call_count == 2

    def test_execute_with_resilience_circuit_breaker(self):
        """Test that circuit breaker is checked."""
        manager = ACPIntegrationManager()

        # Open circuit
        cb = manager._circuit_registry.get_circuit_breaker("test_service")
        cb.force_open("test")

        # Operation should fail with circuit open
        with pytest.raises(CircuitBreakerOpenError):
            manager.execute_with_resilience(
                service_name="test_service",
                operation_name="test_op",
                func=lambda: "success",
            )

    def test_execute_with_resilience_fallback(self):
        """Test fallback execution on failure."""
        manager = ACPIntegrationManager()

        def failing_func():
            raise ValueError("fail")

        result = manager.execute_with_resilience(
            service_name="test_service",
            operation_name="test_op",
            func=failing_func,
            fallback=lambda: "fallback_result",
        )

        assert result == "fallback_result"

    def test_health_check(self):
        """Test health check functionality."""
        config = ACPIntegrationConfig(
            enable_circuit_breaker=True,
            enable_retry_coordinator=True,
            enable_self_healing=False,
            enable_incident_manager=False,
            enable_rollback_coordinator=False,
        )
        manager = ACPIntegrationManager(config=config)

        health = manager.check_health()

        assert isinstance(health, ACPHealthStatus)
        assert health.circuit_breaker_registry  # Local fallback is healthy
        assert health.retry_coordinator  # Local fallback is healthy
        assert not health.self_healing_engine  # Disabled

    def test_get_metrics(self):
        """Test metrics collection."""
        # Reset circuit registry to ensure clean state
        from circuit_breaker_pr import get_global_registry

        registry = get_global_registry()
        registry.reset_all()

        manager = ACPIntegrationManager()

        # Execute some operations
        manager.execute_with_resilience(
            service_name="test_service",
            operation_name="test_op",
            func=lambda: "success",
        )

        metrics = manager.get_metrics()

        assert "health_status" in metrics
        assert "circuit_breakers" in metrics
        assert "retry_operations" in metrics

    def test_graceful_degradation_when_acp_unavailable(self):
        """Test that local fallbacks work when ACP unavailable."""
        # Reset circuit registry to ensure clean state
        from circuit_breaker_pr import get_global_registry

        registry = get_global_registry()
        registry.reset_all()

        config = ACPIntegrationConfig(
            enable_circuit_breaker=True,
            enable_retry_coordinator=True,
            fallback_to_local=True,
        )

        # Create manager (will fail to connect to ACP but use local)
        manager = ACPIntegrationManager(config=config)

        # Should still work with local implementations
        result = manager.execute_with_resilience(
            service_name="test_service",
            operation_name="test_op",
            func=lambda: "success",
        )

        assert result == "success"

    def test_global_manager_singleton(self):
        """Test that global manager is a singleton."""
        manager1 = get_global_manager()
        manager2 = get_global_manager()

        assert manager1 is manager2


class TestACPHealthStatus:
    """Test ACP health status."""

    def test_all_healthy_true(self):
        """Test all_healthy when all components healthy."""
        status = ACPHealthStatus(
            circuit_breaker_registry=True,
            retry_coordinator=True,
            self_healing_engine=True,
            incident_manager=True,
            rollback_coordinator=True,
        )
        assert status.all_healthy
        assert status.healthy_count == 5

    def test_all_healthy_false(self):
        """Test all_healthy when some components unhealthy."""
        status = ACPHealthStatus(
            circuit_breaker_registry=True,
            retry_coordinator=False,
            self_healing_engine=True,
            incident_manager=True,
            rollback_coordinator=True,
        )
        assert not status.all_healthy
        assert status.healthy_count == 4

    def test_to_dict(self):
        """Test conversion to dictionary."""
        status = ACPHealthStatus(
            circuit_breaker_registry=True,
            retry_coordinator=True,
        )
        status.last_check = 12345.0

        d = status.to_dict()
        assert d["circuit_breaker_registry"] is True
        assert d["retry_coordinator"] is True
        assert d["all_healthy"] is False  # Not all components set
        assert d["healthy_count"] == 2
        assert d["last_check"] == 12345.0


class TestDecorators:
    """Test decorator functionality."""

    def test_with_circuit_breaker_decorator(self):
        """Test circuit breaker decorator."""
        registry = PRCircuitBreakerRegistry()

        @with_circuit_breaker("test_service", registry=registry)
        def my_operation():
            return "success"

        result = my_operation()
        assert result == "success"

    def test_with_retry_decorator(self):
        """Test retry decorator."""
        call_count = 0

        @with_retry("test_service")
        def my_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "success"

        result = my_operation()
        assert result == "success"
        assert call_count == 2


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_gitea_api_with_transient_failures(self):
        """Test Gitea API call with transient failures."""
        manager = ACPIntegrationManager()

        call_count = 0

        def gitea_api_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Attempt {call_count} failed")
            return {"pr_number": 123, "status": "created"}

        result = manager.execute_with_resilience(
            service_name="gitea_api",
            operation_name="create_pr",
            func=gitea_api_call,
        )

        assert result["pr_number"] == 123
        assert call_count == 3

    def test_discord_notification_with_circuit_breaker(self):
        """Test Discord notification with circuit breaker."""
        manager = ACPIntegrationManager()

        # Open circuit after failures
        cb = manager._circuit_registry.get_circuit_breaker("discord_notifications")
        cb.force_open("test")

        # Should use fallback
        result = manager.execute_with_resilience(
            service_name="discord_notifications",
            operation_name="send_notification",
            func=lambda: {"sent": True},
            fallback=lambda: {"queued": True, "note": "circuit_open"},
        )

        assert result["queued"] is True

    def test_pr_merge_with_full_stack(self):
        """Test PR merge with full resilience stack."""
        manager = ACPIntegrationManager()

        operations = []

        def merge_operation():
            operations.append("merge_attempt")
            if len(operations) < 2:
                raise TimeoutError("Merge timeout")
            return {"merged": True, "sha": "abc123"}

        result = manager.execute_with_resilience(
            service_name="pr_merge_operations",
            operation_name="merge_pr",
            func=merge_operation,
        )

        assert result["merged"] is True
        assert len(operations) == 2


@pytest.mark.asyncio
class TestAsyncOperations:
    """Test async operation support."""

    async def test_async_circuit_breaker_call(self):
        """Test async circuit breaker call."""
        cb = CircuitBreaker("test_service")

        async def async_operation():
            return "async_success"

        result = await cb.call_async(async_operation)
        assert result == "async_success"

    async def test_async_retry_execution(self):
        """Test async retry execution."""
        coordinator = PRRetryCoordinator()

        call_count = 0

        async def async_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temporary")
            return "async_success"

        result = await coordinator.execute_with_retry_async(
            service_name="test_service",
            operation_name="async_test",
            func=async_operation,
        )

        assert result == "async_success"
        assert call_count == 2

    async def test_async_resilience_execution(self):
        """Test async resilience execution."""
        # Reset circuit registry to ensure clean state
        from circuit_breaker_pr import get_global_registry

        registry = get_global_registry()
        registry.reset_all()

        manager = ACPIntegrationManager()

        async def async_operation():
            return "async_success"

        result = await manager.execute_with_resilience_async(
            service_name="test_service",
            operation_name="async_test",
            func=async_operation,
        )

        assert result == "async_success"
