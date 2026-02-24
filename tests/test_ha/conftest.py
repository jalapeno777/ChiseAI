"""Shared fixtures for HA infrastructure tests."""

import asyncio
from collections.abc import Callable, Generator

import pytest
from src.infrastructure.ha.failover import FailoverConfig, FailoverManager, InstanceInfo
from src.infrastructure.ha.health_check import (
    HealthCheckRegistry,
)
from src.infrastructure.ha.load_balancer import LoadBalancer, LoadBalancerConfig
from src.infrastructure.ha.uptime_monitor import UptimeMonitor
from src.redundancy.manager import (
    DataReplicator,
    RedundancyConfig,
    RedundancyLevel,
    ReplicaInfo,
)


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_instance() -> InstanceInfo:
    """Create a sample instance for testing."""
    return InstanceInfo(
        id="test-instance-1",
        host="localhost",
        port=8080,
        priority=0,
        weight=100,
        is_primary=True,
    )


@pytest.fixture
def sample_instances() -> list[InstanceInfo]:
    """Create sample instances for testing."""
    return [
        InstanceInfo(
            id="primary-1",
            host="primary.local",
            port=8080,
            priority=0,
            weight=100,
            is_primary=True,
        ),
        InstanceInfo(
            id="secondary-1",
            host="secondary.local",
            port=8080,
            priority=1,
            weight=100,
            is_primary=False,
        ),
        InstanceInfo(
            id="secondary-2",
            host="secondary2.local",
            port=8080,
            priority=2,
            weight=50,
            is_primary=False,
        ),
    ]


@pytest.fixture
def sample_replica() -> ReplicaInfo:
    """Create a sample replica for testing."""
    return ReplicaInfo(
        id="replica-1",
        location="us-east-1",
        is_primary=True,
    )


@pytest.fixture
def sample_replicas() -> list[ReplicaInfo]:
    """Create sample replicas for testing."""
    return [
        ReplicaInfo(
            id="replica-primary",
            location="us-east-1",
            is_primary=True,
        ),
        ReplicaInfo(
            id="replica-secondary-1",
            location="us-west-2",
            is_primary=False,
        ),
        ReplicaInfo(
            id="replica-secondary-2",
            location="eu-west-1",
            is_primary=False,
        ),
    ]


@pytest.fixture
def health_registry() -> Generator[HealthCheckRegistry, None, None]:
    """Create a health check registry."""
    registry = HealthCheckRegistry()
    yield registry


@pytest.fixture
def failover_manager() -> Generator[FailoverManager, None, None]:
    """Create a failover manager."""
    config = FailoverConfig(
        health_check_interval_seconds=1.0,
        failure_threshold=2,
        recovery_threshold=1,
    )
    manager = FailoverManager(config)
    yield manager


@pytest.fixture
def load_balancer() -> Generator[LoadBalancer, None, None]:
    """Create a load balancer."""
    config = LoadBalancerConfig()
    lb = LoadBalancer(config)
    yield lb


@pytest.fixture
def uptime_monitor() -> Generator[UptimeMonitor, None, None]:
    """Create an uptime monitor."""
    monitor = UptimeMonitor()
    yield monitor


@pytest.fixture
def data_replicator() -> Generator[DataReplicator, None, None]:
    """Create a data replicator."""
    config = RedundancyConfig(
        level=RedundancyLevel.ACTIVE_PASSIVE,
        min_replicas=2,
    )
    replicator = DataReplicator(config)
    yield replicator


@pytest.fixture
def healthy_check_func() -> Callable[[], bool]:
    """Create a health check function that always returns healthy."""
    return lambda: True


@pytest.fixture
def unhealthy_check_func() -> Callable[[], bool]:
    """Create a health check function that always returns unhealthy."""
    return lambda: False


@pytest.fixture
def flapping_check_func() -> Callable[[], bool]:
    """Create a health check function that alternates between healthy and unhealthy."""
    state = [True]

    def check():
        state[0] = not state[0]
        return state[0]

    return check
