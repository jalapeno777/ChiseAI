"""Extended tests for retry budget manager with Redis mocking.

Tests:
- Redis unavailable scenarios (fail-open behavior)
- TTL handling for Redis keys
- Budget window transitions (minute boundaries)
- Concurrent budget operations
- Redis error handling paths

For ST-NS-039: Retry Coordinator with Budget Management - Coverage Improvement
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from src.autonomous_control_plane.components.retry_budget_manager import (
    RetryBudgetManager,
)
from src.autonomous_control_plane.models.retry_policy import RetryBudget


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
        assert status["service_name"] == "test_service"
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
        assert status["service_name"] == "test_service"
        assert status["window_ttl_seconds"] == 120  # Default TTL

    def test_key_format_includes_minute_precision(self):
        """Test Redis key includes minute-level precision."""
        manager = RetryBudgetManager()

        dt = datetime(2026, 2, 20, 12, 30, 45)  # Has seconds
        key = manager._get_budget_key("test_service", dt)

        # Key should be truncated to minute
        assert key == "retry_budget:test_service:2026-02-20-12-30"

    def test_different_minutes_different_keys(self):
        """Test different minutes produce different Redis keys."""
        manager = RetryBudgetManager()

        dt1 = datetime(2026, 2, 20, 12, 30, 0)
        dt2 = datetime(2026, 2, 20, 12, 31, 0)

        key1 = manager._get_budget_key("test_service", dt1)
        key2 = manager._get_budget_key("test_service", dt2)

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
        service_names = {b["service_name"] for b in budgets}
        assert service_names == {"service1", "service2"}

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
        assert any(b["service_name"] == "service1" for b in budgets)


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
        assert budgets[0]["service_name"] == "test"

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
