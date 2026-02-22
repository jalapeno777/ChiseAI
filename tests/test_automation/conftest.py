"""Test configuration for automation tests."""

import asyncio

import pytest

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def orchestrator():
    """Create a recovery orchestrator."""
    from src.automation import RecoveryOrchestrator

    orch = RecoveryOrchestrator(
        max_attempts=3,
        recovery_timeout_seconds=5.0,
        cooldown_seconds=1.0,
    )
    yield orch


@pytest.fixture
def healing_engine():
    """Create a self-healing engine."""
    from src.automation import SelfHealingEngine

    return SelfHealingEngine()
