"""Shared fixtures for integration tests."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_redis():
    """Mock Redis client."""
    redis = Mock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
async def mock_influx():
    """Mock InfluxDB client."""
    influx = Mock()
    # Use regular Mock (not AsyncMock) since startup.py doesn't await health()
    health_mock = Mock()
    health_mock.status = "pass"
    influx.health = Mock(return_value=health_mock)
    return influx


@pytest.fixture
async def acp_container(mock_redis, mock_influx):
    """Create ACPContainer with mocked dependencies."""
    from unittest.mock import patch

    from src.autonomous_control_plane.startup import ACPContainer

    container = ACPContainer(
        trading_mode="paper",
        redis_client=mock_redis,
        influx_client=mock_influx,
    )

    # Mock dashboard sync to avoid port conflicts
    with patch.object(container, "_dashboard_sync"):
        # Manually initialize core components without full startup
        from src.autonomous_control_plane.components.circuit_breaker_registry import (
            CircuitBreakerRegistry,
        )
        from src.autonomous_control_plane.components.incident_manager import (
            IncidentManager,
        )
        from src.autonomous_control_plane.components.retry_coordinator import (
            RetryCoordinator,
        )
        from src.autonomous_control_plane.components.rollback_coordinator import (
            RollbackCoordinator,
        )
        from src.autonomous_control_plane.components.self_healing_engine import (
            SelfHealingEngine,
        )

        container._cb_registry = CircuitBreakerRegistry()
        container._retry_coordinator = RetryCoordinator()
        container._healing_engine = SelfHealingEngine(
            trading_mode="paper",
            redis_client=mock_redis,
            enable_approval_gates=True,
        )
        container._incident_manager = IncidentManager()
        container._rollback_coordinator = RollbackCoordinator(
            incident_manager=container._incident_manager,
        )

        yield container
