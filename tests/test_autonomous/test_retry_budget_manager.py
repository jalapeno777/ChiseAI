"""Tests for retry budget manager.

Tests:
- Budget tracking with local storage
- Budget enforcement
- Budget reset

For ST-NS-039: Retry Coordinator with Budget Management
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from src.autonomous_control_plane.components.retry_budget_manager import (
    RetryBudgetManager,
)
from src.autonomous_control_plane.models.retry_policy import RetryBudget


class TestRetryBudgetManager:
    """Tests for RetryBudgetManager."""

    @pytest.fixture
    def manager(self):
        """Create a budget manager without Redis."""
        return RetryBudgetManager(redis_client=None, default_limit=100)

    def test_initialization(self):
        """Test budget manager initialization."""
        manager = RetryBudgetManager()
        assert manager._redis is None
        assert manager._default_limit == 100
        assert manager._local_budgets == {}

    def test_custom_initialization(self):
        """Test budget manager with custom settings."""
        manager = RetryBudgetManager(
            redis_client=None,
            default_limit=50,
            ttl_seconds=60,
        )
        assert manager._default_limit == 50
        assert manager._ttl_seconds == 60

    def test_check_and_consume_within_limit(self, manager):
        """Test checking and consuming budget within limit."""
        allowed, remaining = manager.check_and_consume("test_service", limit=5)
        assert allowed is True
        assert remaining == 4

        allowed, remaining = manager.check_and_consume("test_service", limit=5)
        assert allowed is True
        assert remaining == 3

    def test_check_and_consume_exceeds_limit(self, manager):
        """Test budget enforcement when limit exceeded."""
        # Consume all budget
        for _ in range(5):
            allowed, _ = manager.check_and_consume("test_service", limit=5)
            assert allowed is True

        # Next attempt should be blocked
        allowed, remaining = manager.check_and_consume("test_service", limit=5)
        assert allowed is False
        assert remaining == 0

    def test_check_and_consume_default_limit(self, manager):
        """Test using default limit."""
        allowed, remaining = manager.check_and_consume("test_service")
        assert allowed is True
        assert remaining == 99  # Default is 100

    def test_get_budget_status(self, manager):
        """Test getting budget status."""
        # Use some budget
        manager.check_and_consume("test_service", limit=10)
        manager.check_and_consume("test_service", limit=10)

        status = manager.get_budget_status("test_service", limit=10)
        assert status["service_name"] == "test_service"
        assert status["current_count"] == 2
        assert status["limit"] == 10
        assert status["remaining"] == 8
        assert status["is_exceeded"] is False

    def test_get_budget_status_no_usage(self, manager):
        """Test getting status for service with no usage."""
        status = manager.get_budget_status("new_service", limit=10)
        assert status["service_name"] == "new_service"
        assert status["current_count"] == 0
        assert status["remaining"] == 10
        assert status["is_exceeded"] is False

    def test_reset_budget(self, manager):
        """Test resetting budget."""
        # Use budget
        manager.check_and_consume("test_service", limit=5)
        manager.check_and_consume("test_service", limit=5)

        # Reset
        manager.reset_budget("test_service")

        # Should be able to use budget again
        status = manager.get_budget_status("test_service", limit=5)
        assert status["current_count"] == 0
        assert status["remaining"] == 5

    def test_reset_budget_nonexistent(self, manager):
        """Test resetting budget for non-existent service."""
        # Should not raise error
        manager.reset_budget("nonexistent_service")

    def test_get_all_budgets(self, manager):
        """Test getting all budgets."""
        # Create some budgets
        manager.check_and_consume("service_a", limit=10)
        manager.check_and_consume("service_b", limit=10)
        manager.check_and_consume("service_c", limit=10)

        budgets = manager.get_all_budgets()
        assert len(budgets) == 3

        service_names = {b["service_name"] for b in budgets}
        assert service_names == {"service_a", "service_b", "service_c"}

    def test_get_all_budgets_empty(self, manager):
        """Test getting all budgets when none exist."""
        budgets = manager.get_all_budgets()
        assert budgets == []

    def test_cleanup_old_budgets(self, manager):
        """Test cleanup of old budgets."""
        # Cleanup should return 0 for local storage
        result = manager.cleanup_old_budgets()
        assert result == 0


class TestRetryBudgetKeyGeneration:
    """Tests for budget key generation."""

    @pytest.fixture
    def manager(self):
        """Create a budget manager."""
        return RetryBudgetManager()

    def test_get_budget_key_default(self, manager):
        """Test budget key generation with default time."""
        key = manager._get_budget_key("test_service")
        assert key.startswith("retry_budget:test_service:")
        # Should contain timestamp
        parts = key.split(":")
        assert len(parts) == 3

    def test_get_budget_key_specific_time(self, manager):
        """Test budget key generation with specific time."""
        dt = datetime(2026, 2, 20, 12, 30, 0)
        key = manager._get_budget_key("test_service", dt)
        assert key == "retry_budget:test_service:2026-02-20-12-30"

    def test_get_current_window(self, manager):
        """Test getting current window."""
        window = manager._get_current_window()
        assert window.second == 0
        assert window.microsecond == 0


class TestRetryBudgetWindowReset:
    """Tests for budget window reset behavior."""

    def test_window_reset_in_new_minute(self):
        """Test budget resets in new minute window."""
        manager = RetryBudgetManager()

        # Use budget in current window
        manager.check_and_consume("test_service", limit=2)
        manager.check_and_consume("test_service", limit=2)

        # Budget should be exceeded
        allowed, _ = manager.check_and_consume("test_service", limit=2)
        assert allowed is False

        # Manually reset window to simulate time passing
        old_window = manager._local_budgets["test_service"].window_start
        manager._local_budgets["test_service"].window_start = old_window - timedelta(
            minutes=2
        )

        # Should be able to use budget again
        allowed, remaining = manager.check_and_consume("test_service", limit=2)
        assert allowed is True
        assert remaining == 1
