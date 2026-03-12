"""Extended tests for retry budget manager with Redis mocking.

Tests:
- Redis unavailable scenarios (fail-open behavior)
- TTL handling for Redis keys
- Budget window transitions (minute boundaries)
- Concurrent budget operations
- Redis error handling paths
- Per-endpoint budgets with wildcard support
- Budget burst allowance
- Cross-service budget pools
- Budget analytics and forecasting

For ST-NS-039: Retry Coordinator with Budget Management - Coverage Improvement
For ST-SAFETY-002: Retry Budget Implementation
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from src.autonomous_control_plane.components.retry_budget_manager import (
    BudgetAnalytics,
    RetryBudgetManager,
)
from src.autonomous_control_plane.models.retry_policy import (
    BudgetBurstConfig,
    BudgetExhaustionStrategy,
    BudgetPool,
    EndpointRetryBudget,
)


class TestRetryBudgetManagerRedisErrors:
    """Tests for Redis error handling with fail-open behavior."""

    def test_redis_unavailable_check_and_consume_fails_open(self):
        """Test that budget check fails open when Redis is unavailable."""
        mock_redis = MagicMock()
        mock_redis.incr.side_effect = Exception("Redis connection failed")

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        # Should fail open (allow retry) when Redis errors
        allowed, remaining = manager.check_and_consume("test_service", limit=10)
        assert allowed is True
        assert remaining == 10  # Full budget available

    def test_redis_unavailable_get_budget_status_returns_safe_defaults(self):
        """Test budget status returns safe defaults when Redis unavailable."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        status = manager.get_budget_status("test_service", limit=10)
        assert status["budget_key"] == "test_service"
        assert status["current_count"] == 0
        assert status["remaining"] == 10
        assert status["is_exceeded"] is False
        assert "error" in status

    def test_redis_unavailable_reset_budget_logs_error(self):
        """Test budget reset logs error but doesn't raise when Redis unavailable."""
        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("Redis connection failed")

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        # Should not raise
        manager.reset_budget("test_service")

    def test_redis_unavailable_get_all_budgets_returns_empty(self):
        """Test getting all budgets returns empty list when Redis scan fails."""
        mock_redis = MagicMock()
        mock_redis.scan.side_effect = Exception("Redis connection failed")

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()
        assert budgets == []


class TestRetryBudgetManagerRedisTTL:
    """Tests for Redis TTL handling."""

    def test_ttl_set_on_first_increment(self):
        """Test TTL is set only on first budget increment."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1  # First increment

        manager = RetryBudgetManager(
            redis_client=mock_redis, default_limit=100, ttl_seconds=120
        )

        manager.check_and_consume("test_service", limit=10)

        # TTL should be set on first increment
        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 120  # TTL seconds

    def test_ttl_not_set_on_subsequent_increments(self):
        """Test TTL is not set on subsequent budget increments."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 5  # Not first increment

        manager = RetryBudgetManager(
            redis_client=mock_redis, default_limit=100, ttl_seconds=120
        )

        manager.check_and_consume("test_service", limit=10)

        # TTL should not be set
        mock_redis.expire.assert_not_called()

    def test_custom_ttl_configuration(self):
        """Test custom TTL configuration is respected."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1

        manager = RetryBudgetManager(
            redis_client=mock_redis, default_limit=100, ttl_seconds=300
        )

        manager.check_and_consume("test_service", limit=10)

        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 300


class TestRetryBudgetManagerWindowTransitions:
    """Tests for budget window transitions at minute boundaries."""

    def test_budget_resets_at_minute_boundary(self):
        """Test budget resets when crossing minute boundary."""
        mock_redis = MagicMock()
        # Simulate budget usage in previous minute
        mock_redis.get.return_value = b"5"  # 5 attempts in previous window
        mock_redis.ttl.return_value = -1  # Key expired (new window)

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=10)

        # Use a specific time to control the window
        current_time = datetime(2026, 2, 20, 12, 30, 0)

        with patch.object(manager, "_get_current_window", return_value=current_time):
            status = manager._get_budget_status_redis("test_service", limit=10)

        # Should show current window status
        assert status["budget_key"] == "test_service"
        assert status["window_ttl_seconds"] == 120  # Default TTL

    def test_key_format_includes_minute_precision(self):
        """Test Redis key includes minute-level precision."""
        manager = RetryBudgetManager()

        dt = datetime(2026, 2, 20, 12, 30, 45)  # Has seconds
        key = manager._get_budget_key("test_service", dt=dt)

        # Key should be truncated to minute
        assert key == "retry_budget:test_service:2026-02-20-12-30"

    def test_different_minutes_different_keys(self):
        """Test different minutes produce different Redis keys."""
        manager = RetryBudgetManager()

        dt1 = datetime(2026, 2, 20, 12, 30, 0)
        dt2 = datetime(2026, 2, 20, 12, 31, 0)

        key1 = manager._get_budget_key("test_service", dt=dt1)
        key2 = manager._get_budget_key("test_service", dt=dt2)

        assert key1 != key2
        assert "12-30" in key1
        assert "12-31" in key2


class TestRetryBudgetManagerConcurrentOperations:
    """Tests for concurrent budget operations."""

    def test_concurrent_check_and_consume_with_redis(self):
        """Test concurrent budget checks use Redis atomic operations."""
        mock_redis = MagicMock()
        mock_redis.incr.side_effect = [1, 2, 3, 4, 5]  # Sequential increments

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=10)

        # Simulate concurrent calls
        results = []
        for _ in range(5):
            allowed, remaining = manager.check_and_consume("test_service", limit=10)
            results.append((allowed, remaining))

        # All should be allowed (within limit)
        assert all(r[0] for r in results)
        # Redis incr should be called 5 times
        assert mock_redis.incr.call_count == 5

    def test_concurrent_budget_exceeded_detection(self):
        """Test budget exceeded is correctly detected under concurrent load."""
        mock_redis = MagicMock()
        # Simulate budget exceeded after 10 calls
        mock_redis.incr.side_effect = list(range(1, 15))

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=10)

        results = []
        for _ in range(12):
            allowed, remaining = manager.check_and_consume("test_service", limit=10)
            results.append((allowed, remaining))

        # First 10 should be allowed
        assert all(r[0] for r in results[:10])
        # Last 2 should be blocked
        assert not any(r[0] for r in results[10:])


class TestRetryBudgetManagerRedisScan:
    """Tests for Redis scan operations in get_all_budgets."""

    def test_scan_with_multiple_batches(self):
        """Test scanning budgets across multiple Redis batches."""
        mock_redis = MagicMock()
        # Simulate two batches of results
        mock_redis.scan.side_effect = [
            (1, [b"retry_budget:service1:2026-02-20-12-30"]),  # First batch, cursor=1
            (0, [b"retry_budget:service2:2026-02-20-12-30"]),  # Second batch, cursor=0
        ]
        mock_redis.get.side_effect = [b"5", b"3"]
        mock_redis.ttl.side_effect = [60, 45]

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()

        assert len(budgets) == 2
        budget_keys = {b["budget_key"] for b in budgets}
        assert budget_keys == {"service1", "service2"}

    def test_scan_with_empty_results(self):
        """Test scanning with no matching keys."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [])  # Empty results

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()
        assert budgets == []

    def test_scan_with_malformed_keys(self):
        """Test scanning handles malformed keys gracefully."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (
            0,
            [
                b"retry_budget:service1:2026-02-20-12-30",  # Valid
                b"malformed_key",  # Invalid - no colons
                b"retry_budget:",  # Missing service - but still has 2 parts
            ],
        )
        mock_redis.get.return_value = b"5"
        mock_redis.ttl.return_value = 60

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()

        # The code processes any key with >= 2 parts separated by ":"
        # "malformed_key" has 1 part, so it's skipped
        # "retry_budget:" has 2 parts ("retry_budget" and ""), so it's processed
        # Valid key is always processed
        assert len(budgets) >= 1
        assert any(b["budget_key"] == "service1" for b in budgets)


class TestRetryBudgetManagerEdgeCases:
    """Tests for edge cases in budget management."""

    def test_bytes_key_conversion(self):
        """Test handling of bytes keys from Redis."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [b"retry_budget:test:2026-02-20-12-30"])
        mock_redis.get.return_value = b"5"
        mock_redis.ttl.return_value = 60

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()
        assert len(budgets) == 1
        assert budgets[0]["budget_key"] == "test"

    def test_string_key_handling(self):
        """Test handling of string keys from Redis."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["retry_budget:test:2026-02-20-12-30"])
        mock_redis.get.return_value = b"5"
        mock_redis.ttl.return_value = 60

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        budgets = manager.get_all_budgets()
        assert len(budgets) == 1

    def test_negative_ttl_handling(self):
        """Test handling of negative TTL from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"5"
        mock_redis.ttl.return_value = -2  # Key doesn't exist

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=100)

        status = manager._get_budget_status_redis("test_service", limit=10)

        # Should use default TTL when Redis returns negative
        assert status["window_ttl_seconds"] == 120  # Default TTL

    def test_zero_budget_limit(self):
        """Test behavior with zero budget limit (edge case)."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=0)

        allowed, remaining = manager._check_and_consume_redis("test_service", limit=0)

        # With limit=0, first attempt should exceed
        assert allowed is False
        assert remaining == 0

    def test_large_budget_values(self):
        """Test handling of large budget values."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 999999
        mock_redis.get.return_value = b"999999"

        manager = RetryBudgetManager(redis_client=mock_redis, default_limit=1000000)

        allowed, remaining = manager.check_and_consume("test_service", limit=1000000)
        assert allowed is True
        assert remaining == 1


class TestRetryBudgetManagerLocalFallback:
    """Tests for local storage fallback when Redis unavailable."""

    def test_local_budget_persistence(self):
        """Test local budgets persist across multiple operations."""
        manager = RetryBudgetManager(redis_client=None, default_limit=100)

        # Multiple operations on same service
        for _ in range(5):
            manager.check_and_consume("test_service", limit=10)

        status = manager.get_budget_status("test_service", limit=10)
        assert status["current_count"] == 5

    def test_local_budget_isolation(self):
        """Test budgets are isolated between services."""
        manager = RetryBudgetManager(redis_client=None, default_limit=100)

        # Use budget for service_a
        for _ in range(5):
            manager.check_and_consume("service_a", limit=10)

        # service_b should have full budget
        status = manager.get_budget_status("service_b", limit=10)
        assert status["current_count"] == 0
        assert status["remaining"] == 10

    def test_local_window_start_in_status(self):
        """Test local budget includes window start in status."""
        manager = RetryBudgetManager(redis_client=None, default_limit=100)

        manager.check_and_consume("test_service", limit=10)

        status = manager._get_budget_status_local("test_service", limit=10)
        assert "window_start" in status
        assert isinstance(status["window_start"], str)  # ISO format


class TestBudgetBurstConfig:
    """Tests for BudgetBurstConfig."""

    def test_default_burst_config(self):
        """Test default burst configuration."""
        config = BudgetBurstConfig()
        assert config.burst_percentage == 150.0
        assert config.cooldown_seconds == 60
        assert config.max_bursts_per_window == 3

    def test_calculate_burst_limit(self):
        """Test burst limit calculation."""
        config = BudgetBurstConfig(burst_percentage=200.0)
        assert config.calculate_burst_limit(100) == 200
        assert config.calculate_burst_limit(50) == 100

    def test_to_dict(self):
        """Test serialization to dict."""
        config = BudgetBurstConfig(
            burst_percentage=175.0,
            cooldown_seconds=120,
            max_bursts_per_window=5,
        )
        data = config.to_dict()
        assert data["burst_percentage"] == 175.0
        assert data["cooldown_seconds"] == 120
        assert data["max_bursts_per_window"] == 5


class TestEndpointRetryBudget:
    """Tests for EndpointRetryBudget."""

    def test_endpoint_budget_creation(self):
        """Test creating endpoint budget."""
        budget = EndpointRetryBudget(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
            limit=50,
            exhaustion_strategy=BudgetExhaustionStrategy.DEGRADED,
        )
        assert budget.service_name == "api_service"
        assert budget.endpoint_pattern == "api/v1/orders/*"
        assert budget.limit == 50
        assert budget.exhaustion_strategy == BudgetExhaustionStrategy.DEGRADED

    def test_get_full_key(self):
        """Test full key generation."""
        budget = EndpointRetryBudget(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
        )
        assert budget.get_full_key() == "api_service:api/v1/orders/*"

    def test_record_attempt(self):
        """Test recording attempts."""
        budget = EndpointRetryBudget(
            service_name="api_service",
            endpoint_pattern="api/v1/users/*",
            limit=5,
        )

        # First 5 attempts should succeed
        for i in range(5):
            assert budget.record_attempt() is True
            assert budget.current_count == i + 1

        # 6th attempt should fail
        assert budget.record_attempt() is False
        assert budget.is_exceeded is True

    def test_to_dict(self):
        """Test serialization."""
        budget = EndpointRetryBudget(
            service_name="api_service",
            endpoint_pattern="api/v1/items/*",
            limit=100,
            exhaustion_strategy=BudgetExhaustionStrategy.QUEUE,
        )
        data = budget.to_dict()
        assert data["service_name"] == "api_service"
        assert data["endpoint_pattern"] == "api/v1/items/*"
        assert data["full_key"] == "api_service:api/v1/items/*"
        assert data["exhaustion_strategy"] == "QUEUE"


class TestBudgetPool:
    """Tests for BudgetPool."""

    def test_pool_creation(self):
        """Test creating budget pool."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="API Services Pool",
            services=["service-a", "service-b"],
            total_budget=1000,
            emergency_reserve=200,
        )
        assert pool.pool_id == "pool-1"
        assert pool.name == "API Services Pool"
        assert pool.services == ["service-a", "service-b"]
        assert pool.total_budget == 1000
        assert pool.emergency_reserve == 200

    def test_get_available_budget(self):
        """Test available budget calculation."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            total_budget=1000,
            used_budget=300,
            emergency_reserve=100,
        )
        assert pool.get_available_budget() == 700

        # Unlock emergency reserve
        pool.unlock_emergency_reserve()
        assert pool.get_available_budget() == 800

    def test_consume_budget(self):
        """Test budget consumption."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            total_budget=100,
            used_budget=0,
        )

        # Consume within limit
        assert pool.consume_budget(30) is True
        assert pool.used_budget == 30

        # Consume more
        assert pool.consume_budget(50) is True
        assert pool.used_budget == 80

        # Try to exceed
        assert pool.consume_budget(30) is False
        assert pool.used_budget == 80

    def test_release_budget(self):
        """Test budget release."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            total_budget=100,
            used_budget=50,
        )

        pool.release_budget(20)
        assert pool.used_budget == 30

        # Don't go below 0
        pool.release_budget(50)
        assert pool.used_budget == 0

    def test_get_service_allocation_equal(self):
        """Test equal allocation when no priorities set."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            services=["a", "b", "c"],
            total_budget=99,
        )
        assert pool.get_service_allocation("a") == 33
        assert pool.get_service_allocation("b") == 33
        assert pool.get_service_allocation("c") == 33

    def test_get_service_allocation_priority(self):
        """Test priority-based allocation."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            services=["a", "b", "c"],
            total_budget=1000,
            priority_allocation={"a": 500, "b": 300, "c": 200},
        )
        assert pool.get_service_allocation("a") == 500
        assert pool.get_service_allocation("b") == 300
        assert pool.get_service_allocation("c") == 200

    def test_to_dict(self):
        """Test serialization."""
        pool = BudgetPool(
            pool_id="pool-1",
            name="Test Pool",
            services=["a", "b"],
            total_budget=500,
            used_budget=100,
        )
        data = pool.to_dict()
        assert data["pool_id"] == "pool-1"
        assert data["name"] == "Test Pool"
        assert data["services"] == ["a", "b"]
        assert data["total_budget"] == 500
        assert data["used_budget"] == 100
        assert data["available_budget"] == 400


class TestBudgetAnalytics:
    """Tests for BudgetAnalytics."""

    def test_record_consumption(self):
        """Test recording consumption events."""
        analytics = BudgetAnalytics()

        analytics.record_consumption("service-a", amount=1, success=True)
        analytics.record_consumption("service-a", amount=1, success=True)
        analytics.record_consumption("service-a", amount=1, success=False)

        metrics = analytics._local_metrics["service-a"]
        assert metrics["total_retries"] == 3
        assert metrics["success_count"] == 2
        assert metrics["failure_count"] == 1

    def test_get_consumption_rate(self):
        """Test consumption rate calculation."""
        analytics = BudgetAnalytics()

        # No data
        assert analytics.get_consumption_rate("service-a") == 0.0

        # Add consumption
        for _ in range(60):
            analytics.record_consumption("service-a", amount=1, success=True)

        rate = analytics.get_consumption_rate("service-a", window_seconds=60)
        assert rate == 1.0  # 60 per 60 seconds

    def test_predict_time_to_exhaustion(self):
        """Test time-to-exhaustion prediction."""
        analytics = BudgetAnalytics()

        # No data - can't predict
        assert analytics.predict_time_to_exhaustion("service-a", 100) is None

        # Add consumption at 1 per second
        for _ in range(60):
            analytics.record_consumption("service-a", amount=1, success=True)

        # At 1/sec, 100 remaining should take 100 seconds
        prediction = analytics.predict_time_to_exhaustion("service-a", 100)
        assert prediction is not None
        assert 90 <= prediction <= 110  # Allow some variance

    def test_get_efficiency_metrics(self):
        """Test efficiency metrics."""
        analytics = BudgetAnalytics()

        # No data
        metrics = analytics.get_efficiency_metrics("service-a")
        assert metrics["retries_per_success"] == 0.0
        assert metrics["success_rate"] == 0.0

        # Add data: 10 retries, 8 successes, 2 failures
        for _ in range(8):
            analytics.record_consumption("service-a", amount=1, success=True)
        for _ in range(2):
            analytics.record_consumption("service-a", amount=1, success=False)

        metrics = analytics.get_efficiency_metrics("service-a")
        assert metrics["retries_per_success"] == 1.25  # 10/8
        assert metrics["success_rate"] == 0.8  # 8/10


class TestRetryBudgetManagerEndpoints:
    """Tests for RetryBudgetManager endpoint features."""

    def test_register_endpoint_pattern(self):
        """Test registering endpoint patterns."""
        manager = RetryBudgetManager()

        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
            limit=50,
            exhaustion_strategy=BudgetExhaustionStrategy.DEGRADED,
        )

        assert "api_service" in manager._endpoint_patterns
        assert "api/v1/orders/*" in manager._endpoint_patterns["api_service"]

    def test_match_endpoint_pattern(self):
        """Test endpoint pattern matching."""
        manager = RetryBudgetManager()

        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
        )
        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/users/*",
        )

        # Match specific paths
        assert (
            manager._match_endpoint_pattern("api_service", "api/v1/orders/123")
            == "api/v1/orders/*"
        )
        assert (
            manager._match_endpoint_pattern("api_service", "api/v1/users/456")
            == "api/v1/users/*"
        )
        assert (
            manager._match_endpoint_pattern("api_service", "api/v1/items/789") is None
        )

    def test_check_and_consume_endpoint(self):
        """Test endpoint budget consumption."""
        manager = RetryBudgetManager()

        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
            limit=5,
            exhaustion_strategy=BudgetExhaustionStrategy.FAIL_FAST,
        )

        # Consume budget
        allowed, remaining, strategy = manager.check_and_consume_endpoint(
            "api_service", "api/v1/orders/123", limit=5
        )
        assert allowed is True
        assert remaining == 4
        assert strategy == BudgetExhaustionStrategy.FAIL_FAST

        # Exhaust budget
        for _ in range(4):
            manager.check_and_consume_endpoint(
                "api_service", "api/v1/orders/123", limit=5
            )

        # Check with hierarchy disabled to test endpoint budget exhaustion
        allowed, remaining, strategy = manager.check_and_consume_endpoint(
            "api_service", "api/v1/orders/123", limit=5, check_hierarchy=False
        )
        assert allowed is False
        assert remaining == 0

    def test_get_endpoint_budget_status(self):
        """Test getting endpoint budget status."""
        manager = RetryBudgetManager()

        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
            limit=100,
        )

        # Consume some budget (use check_hierarchy=False to ensure endpoint budget is used)
        manager.check_and_consume_endpoint(
            "api_service", "api/v1/orders/123", limit=100, check_hierarchy=False
        )

        status = manager.get_endpoint_budget_status("api_service", "api/v1/orders/*")
        assert status["budget_key"] == "api_service:api/v1/orders/*"
        assert status["endpoint_pattern"] == "api/v1/orders/*"
        assert status["limit"] == 100
        assert status["current_count"] == 1
        assert status["remaining"] == 99


class TestRetryBudgetManagerPools:
    """Tests for RetryBudgetManager pool features."""

    def test_create_budget_pool(self):
        """Test creating budget pool."""
        manager = RetryBudgetManager()

        pool = manager.create_budget_pool(
            pool_id="pool-1",
            name="API Pool",
            services=["service-a", "service-b"],
            total_budget=1000,
            emergency_reserve=200,
        )

        assert pool.pool_id == "pool-1"
        assert "pool-1" in manager._budget_pools

    def test_consume_from_pool(self):
        """Test consuming from pool."""
        manager = RetryBudgetManager()

        manager.create_budget_pool(
            pool_id="pool-1",
            name="API Pool",
            services=["service-a", "service-b"],
            total_budget=100,
        )

        # Consume from pool
        assert manager.consume_from_pool("pool-1", "service-a", amount=30) is True
        assert manager.consume_from_pool("pool-1", "service-b", amount=50) is True

        pool = manager._budget_pools["pool-1"]
        assert pool.used_budget == 80

        # Try to exceed
        assert manager.consume_from_pool("pool-1", "service-a", amount=30) is False

    def test_consume_from_nonexistent_pool(self):
        """Test consuming from non-existent pool."""
        manager = RetryBudgetManager()
        assert manager.consume_from_pool("nonexistent", "service-a") is False

    def test_consume_from_pool_unauthorized_service(self):
        """Test consuming from pool with unauthorized service."""
        manager = RetryBudgetManager()

        manager.create_budget_pool(
            pool_id="pool-1",
            name="API Pool",
            services=["service-a"],
        )

        assert manager.consume_from_pool("pool-1", "service-b") is False

    def test_unlock_emergency_reserve(self):
        """Test unlocking emergency reserve."""
        manager = RetryBudgetManager()

        manager.create_budget_pool(
            pool_id="pool-1",
            name="API Pool",
            services=["service-a"],
            total_budget=100,
            emergency_reserve=50,
        )

        # Use all regular budget
        manager.consume_from_pool("pool-1", "service-a", amount=100)
        assert manager.consume_from_pool("pool-1", "service-a", amount=1) is False

        # Unlock emergency reserve
        assert manager.unlock_emergency_reserve("pool-1") is True

        # Now should be able to consume
        assert manager.consume_from_pool("pool-1", "service-a", amount=30) is True

    def test_get_pool_status(self):
        """Test getting pool status."""
        manager = RetryBudgetManager()

        manager.create_budget_pool(
            pool_id="pool-1",
            name="API Pool",
            services=["service-a", "service-b"],
            total_budget=1000,
        )

        # Consume some budget
        manager.consume_from_pool("pool-1", "service-a", amount=200)

        status = manager.get_pool_status("pool-1")
        assert status is not None
        assert status["pool_id"] == "pool-1"
        assert status["name"] == "API Pool"
        assert status["total_budget"] == 1000
        assert status["used_budget"] == 200
        assert status["available_budget"] == 800

    def test_get_all_pools(self):
        """Test getting all pools."""
        manager = RetryBudgetManager()

        manager.create_budget_pool(
            pool_id="pool-1",
            name="Pool 1",
            services=["a"],
        )
        manager.create_budget_pool(
            pool_id="pool-2",
            name="Pool 2",
            services=["b"],
        )

        pools = manager.get_all_pools()
        assert len(pools) == 2
        pool_ids = {p["pool_id"] for p in pools}
        assert pool_ids == {"pool-1", "pool-2"}


class TestRetryBudgetManagerBurst:
    """Tests for RetryBudgetManager burst features."""

    def test_burst_allowance_local(self):
        """Test burst allowance with local storage."""
        manager = RetryBudgetManager()

        config = BudgetBurstConfig(
            burst_percentage=150.0,
            cooldown_seconds=60,
            max_bursts_per_window=3,
        )

        # First 15 attempts should succeed (150% of 10 = 15)
        for i in range(15):
            allowed, remaining = manager.check_and_consume(
                "service-a", limit=10, burst_config=config
            )
            assert allowed is True, f"Attempt {i + 1} should be allowed"

        # 16th should fail
        allowed, remaining = manager.check_and_consume(
            "service-a", limit=10, burst_config=config
        )
        assert allowed is False

    def test_burst_config_defaults(self):
        """Test burst config defaults."""
        config = BudgetBurstConfig()
        assert config.burst_percentage == 150.0
        assert config.cooldown_seconds == 60
        assert config.max_bursts_per_window == 3


class TestRetryBudgetManagerAnalytics:
    """Tests for RetryBudgetManager analytics integration."""

    def test_get_analytics(self):
        """Test getting analytics instance."""
        manager = RetryBudgetManager()
        analytics = manager.get_analytics()
        assert isinstance(analytics, BudgetAnalytics)

    def test_analytics_integration_with_endpoint(self):
        """Test analytics integration with endpoint budgets."""
        manager = RetryBudgetManager()

        manager.register_endpoint_pattern(
            service_name="api_service",
            endpoint_pattern="api/v1/orders/*",
            limit=100,
        )

        # Consume budget
        manager.check_and_consume_endpoint(
            "api_service", "api/v1/orders/123", limit=100
        )

        # Check analytics were recorded
        analytics = manager.get_analytics()
        assert "api_service:api/v1/orders/*" in analytics._local_metrics


class TestRetryBudgetManagerGlobalBudget:
    """Tests for global budget limit."""

    def test_global_budget_limit(self):
        """Test global budget enforcement."""
        manager = RetryBudgetManager(global_limit=10)

        # First 10 should succeed
        for _ in range(10):
            allowed, _ = manager.check_and_consume("service-a", limit=100)
            assert allowed is True

        # 11th should fail due to global limit
        allowed, remaining = manager.check_and_consume("service-b", limit=100)
        assert allowed is False
        assert remaining == 0

    def test_no_global_limit(self):
        """Test without global budget."""
        manager = RetryBudgetManager(global_limit=None)

        # Should not enforce global limit
        for _ in range(20):
            allowed, _ = manager.check_and_consume("service-a", limit=100)
            assert allowed is True
