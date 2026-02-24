"""Shared fixtures for HA tests."""
import asyncio
import pytest
from datetime import datetime, timezone

from src.infrastructure.ha.health_check import (
    HealthCheckConfig, HealthChecker, HealthCheckRegistry, HealthStatus
)
from src.infrastructure.ha.failover import (
    FailoverConfig, FailoverManager, InstanceInfo
)
from src.infrastructure.ha.load_balancer import (
    LoadBalancer, LoadBalancerConfig, LoadBalancingStrategy
)
from src.infrastructure.ha.uptime_monitor import (
    UptimeMonitor, UptimeMonitorConfig, UptimeTarget
)
from src.infrastructure.ha.manager import HAConfig, HighAvailabilityManager
from src.redundancy.manager import (
    RedundancyConfig, DataReplicator, ServiceRedundancyManager,
    RedundancyLevel, ReplicaInfo
)


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def health_check_config():
    """Basic health check config."""
    return HealthCheckConfig(
        name="test_check",
        check_func=lambda: True,
        interval_seconds=1.0,
        timeout_seconds=1.0,
    )


@pytest.fixture
def health_checker(health_check_config):
    """Basic health checker instance."""
    return HealthChecker(health_check_config)


@pytest.fixture
def health_registry():
    """Fresh health check registry."""
    return HealthCheckRegistry()


@pytest.fixture
def failover_config():
    """Basic failover config."""
    return FailoverConfig(
        health_check_interval_seconds=1.0,
        failure_threshold=2,
        recovery_threshold=2,
    )


@pytest.fixture
def failover_manager(failover_config):
    """Basic failover manager instance."""
    return FailoverManager(failover_config)


@pytest.fixture
def instance_info():
    """Sample instance info."""
    return InstanceInfo(
        id="test-instance-1",
        host="localhost",
        port=8080,
        is_primary=True,
    )


@pytest.fixture
def backup_instance():
    """Sample backup instance."""
    return InstanceInfo(
        id="test-backup-1",
        host="localhost",
        port=8081,
        is_primary=False,
    )


@pytest.fixture
def load_balancer_config():
    """Basic load balancer config."""
    return LoadBalancerConfig(
        strategy=LoadBalancingStrategy.ROUND_ROBIN,
    )


@pytest.fixture
def load_balancer(load_balancer_config):
    """Basic load balancer instance."""
    return LoadBalancer(load_balancer_config)


@pytest.fixture
def uptime_monitor():
    """Basic uptime monitor instance."""
    return UptimeMonitor()


@pytest.fixture
def uptime_target():
    """Sample uptime target."""
    return UptimeTarget(
        service_name="test-service",
        target_percentage=99.9,
    )


@pytest.fixture
def ha_config():
    """Basic HA config."""
    return HAConfig(
        health_check_interval_seconds=1.0,
        uptime_target_percentage=99.9,
    )


@pytest.fixture
def ha_manager(ha_config):
    """Basic HA manager instance."""
    return HighAvailabilityManager(ha_config)


@pytest.fixture
def redundancy_config():
    """Basic redundancy config."""
    return RedundancyConfig(
        level=RedundancyLevel.ACTIVE_PASSIVE,
        min_replicas=2,
    )


@pytest.fixture
def data_replicator(redundancy_config):
    """Basic data replicator instance."""
    return DataReplicator(redundancy_config)


@pytest.fixture
def replica_info():
    """Sample replica info."""
    return ReplicaInfo(
        id="replica-1",
        location="us-east-1",
        is_primary=True,
    )


@pytest.fixture
def backup_replica():
    """Sample backup replica."""
    return ReplicaInfo(
        id="replica-2",
        location="us-west-1",
        is_primary=False,
    )
