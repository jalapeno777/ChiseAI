"""Shared fixtures for autonomous_cognition tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from autonomous_cognition.action_executor import (
    Action,
    ActionExecutor,
    ActionPriority,
)
from autonomous_cognition.rollback import RollbackManager
from autonomous_cognition.validation import (
    ActionValidator,
    BudgetConfig,
    RateLimitConfig,
)


@pytest.fixture
def sample_action():
    """Create a sample action for testing."""
    return Action(
        name="test_action",
        action_type="test",
        payload={"key": "value"},
        priority=ActionPriority.MEDIUM,
        timeout_seconds=5.0,
        max_retries=0,
    )


@pytest.fixture
def high_priority_action():
    """Create a high priority action for testing."""
    return Action(
        name="high_priority_action",
        action_type="test",
        payload={"urgent": True},
        priority=ActionPriority.HIGH,
        timeout_seconds=5.0,
    )


@pytest.fixture
def critical_action():
    """Create a critical priority action for testing."""
    return Action(
        name="critical_action",
        action_type="critical",
        payload={"critical": True},
        priority=ActionPriority.CRITICAL,
        timeout_seconds=1.0,
    )


@pytest.fixture
def slow_action():
    """Create an action that takes time to execute."""
    return Action(
        name="slow_action",
        action_type="slow",
        payload={"delay": 0.1},
        priority=ActionPriority.LOW,
        timeout_seconds=10.0,
    )


@pytest.fixture
def failing_action():
    """Create an action that will fail."""
    return Action(
        name="failing_action",
        action_type="failing",
        payload={"should_fail": True},
        priority=ActionPriority.MEDIUM,
        timeout_seconds=5.0,
    )


@pytest.fixture
def action_executor():
    """Create an ActionExecutor instance."""
    executor = ActionExecutor()
    yield executor
    # Cleanup
    try:
        asyncio.get_event_loop().run_until_complete(executor.shutdown())
    except Exception:
        pass


@pytest.fixture
async def async_action_executor():
    """Create an async ActionExecutor instance."""
    executor = ActionExecutor()
    yield executor
    await executor.shutdown()


@pytest.fixture
def validator():
    """Create an ActionValidator instance."""
    return ActionValidator()


@pytest.fixture
def validator_with_limits():
    """Create an ActionValidator with custom rate limits."""
    rate_limits = RateLimitConfig(
        max_requests_per_minute=10,
        max_requests_per_hour=100,
        burst_size=5,
    )
    budget = BudgetConfig(
        max_daily_actions=100,
        max_concurrent_actions=5,
    )
    return ActionValidator(rate_limits=rate_limits, budget=budget)


@pytest.fixture
def rollback_manager():
    """Create a RollbackManager instance."""
    return RollbackManager()


@pytest.fixture
def mock_handler():
    """Create a mock action handler."""
    handler = MagicMock()
    handler.return_value = {"result": "success"}
    return handler


@pytest.fixture
def async_mock_handler():
    """Create an async mock action handler."""

    async def handler(action):
        return {"result": "async_success"}

    return handler


@pytest.fixture
def failing_handler():
    """Create a handler that raises an exception."""

    def handler(action):
        raise ValueError("Handler failed")

    return handler


@pytest.fixture
def slow_handler():
    """Create a handler that takes time."""

    async def handler(action):
        delay = action.payload.get("delay", 0.1)
        await asyncio.sleep(delay)
        return {"result": "completed_after_delay"}

    return handler


@pytest.fixture
def timeout_handler():
    """Create a handler that exceeds timeout."""

    async def handler(action):
        await asyncio.sleep(10.0)  # Longer than any reasonable timeout
        return {"result": "should_not_reach"}

    return handler
