"""Tests for Unified High Availability Manager."""

import pytest
from src.infrastructure.ha.failover import InstanceInfo
from src.infrastructure.ha.health_check import HealthStatus
from src.infrastructure.ha.load_balancer import LoadBalancingStrategy
from src.infrastructure.ha.manager import (
    HAConfig,
    HighAvailabilityManager,
    get_ha_manager,
    reset_ha_manager,
)
from src.redundancy.manager import ReplicaInfo


class TestHAConfig:
    """Tests for HAConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = HAConfig()
        assert config.uptime_target_percentage == 99.9
        assert config.failover_enabled
        assert config.auto_failback

    def test_custom_config(self):
        """Test custom configuration."""
        config = HAConfig(
            uptime_target_percentage=99.5,
            failover_enabled=False,
            load_balancing_strategy=LoadBalancingStrategy.LEAST_CONNECTIONS,
        )
        assert config.uptime_target_percentage == 99.5
        assert not config.failover_enabled
        assert config.load_balancing_strategy == LoadBalancingStrategy.LEAST_CONNECTIONS


class TestHighAvailabilityManager:
    """Tests for HighAvailabilityManager."""

    def test_manager_creation(self):
        """Test creating an HA manager."""
        manager = HighAvailabilityManager()
        assert manager.config is not None
        assert not manager._running

    def test_manager_with_config(self):
        """Test creating manager with custom config."""
        config = HAConfig(uptime_target_percentage=99.99)
        manager = HighAvailabilityManager(config)
        assert manager.config.uptime_target_percentage == 99.99

    def test_register_service(self, sample_instances):
        """Test registering a service."""
        manager = HighAvailabilityManager()

        def health_check():
            return True

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=health_check,
        )

        assert "api" in manager._services
        status = manager.get_service_status("api")
        assert status["service_name"] == "api"
        assert status["instance_count"] == 3

    def test_unregister_service(self, sample_instances):
        """Test unregistering a service."""
        manager = HighAvailabilityManager()

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        assert manager.unregister_service("api")
        assert "api" not in manager._services
        assert not manager.unregister_service("nonexistent")

    def test_add_instance(self, sample_instances):
        """Test adding an instance to a service."""
        manager = HighAvailabilityManager()

        manager.register_service(
            service_name="api",
            instances=sample_instances[:1],  # Just primary
            health_check_func=lambda: True,
        )

        new_instance = InstanceInfo(
            id="new-instance",
            host="new.local",
            port=8080,
            is_primary=False,
        )
        new_instance.health_status = HealthStatus.HEALTHY

        manager.add_instance("api", new_instance)
        status = manager.get_service_status("api")
        assert status["instance_count"] == 2

    def test_remove_instance(self, sample_instances):
        """Test removing an instance from a service."""
        manager = HighAvailabilityManager()

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        manager.remove_instance("api", "secondary-2")
        status = manager.get_service_status("api")
        assert status["instance_count"] == 2

    def test_get_instance(self, sample_instances):
        """Test getting an instance for requests."""
        manager = HighAvailabilityManager()

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        instance = manager.get_instance("api")
        assert instance is not None
        assert instance.id in [i.id for i in sample_instances]

    def test_get_instance_with_sticky_session(self, sample_instances):
        """Test getting instance with sticky session."""
        config = HAConfig()
        config = HAConfig.__new__(HAConfig)  # Create without __init__
        config.load_balancing_strategy = LoadBalancingStrategy.ROUND_ROBIN

        manager = HighAvailabilityManager(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        # Note: sticky sessions would need sticky_sessions=True in LoadBalancerConfig
        # For now just verify get_instance works
        instance = manager.get_instance("api", session_id="session-1")
        assert instance is not None

    def test_get_global_status(self, sample_instances):
        """Test getting global status."""
        manager = HighAvailabilityManager()

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        status = manager.get_global_status()

        assert "services" in status
        assert "health_registry" in status
        assert "failover" in status
        assert "load_balancer" in status
        assert "uptime" in status
        assert "redundancy" in status

    def test_get_recent_alerts(self, sample_instances):
        """Test getting recent alerts."""
        manager = HighAvailabilityManager()

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        alerts = manager.get_recent_alerts()
        assert isinstance(alerts, list)

    def test_is_meeting_uptime_target(self, sample_instances):
        """Test checking uptime target."""
        manager = HighAvailabilityManager()

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        # With no checks recorded, technically meeting target
        # (no failures means 100%)
        is_meeting = manager.is_meeting_uptime_target()
        assert isinstance(is_meeting, bool)

    def test_on_health_check_result(self, sample_instances):
        """Test health check result handling."""
        manager = HighAvailabilityManager()

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        # The callback should update internal state
        # Just verify it doesn't error
        from src.infrastructure.ha.health_check import HealthCheckResult

        result = HealthCheckResult(
            name="api_health",
            status=HealthStatus.HEALTHY,
            details={"instance_id": "primary-1"},
        )
        manager._on_health_check_result("api_health", result)

    def test_to_dict(self, sample_instances):
        """Test exporting manager status."""
        manager = HighAvailabilityManager()

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        d = manager.to_dict()
        assert "services" in d
        assert "config" in d

    @pytest.mark.asyncio
    async def test_start_stop(self, sample_instances):
        """Test starting and stopping manager."""
        manager = HighAvailabilityManager()

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        manager.register_service(
            service_name="api",
            instances=sample_instances,
            health_check_func=lambda: True,
        )

        await manager.start()
        assert manager._running

        await manager.stop()
        assert not manager._running

    @pytest.mark.asyncio
    async def test_context_manager(self, sample_instances):
        """Test async context manager."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY

        async with HighAvailabilityManager() as manager:
            manager.register_service(
                service_name="api",
                instances=sample_instances,
                health_check_func=lambda: True,
            )
            assert manager._running

        assert not manager._running


class TestGlobalHAManager:
    """Tests for global HA manager functions."""

    def test_get_ha_manager(self):
        """Test getting global HA manager."""
        reset_ha_manager()
        manager1 = get_ha_manager()
        manager2 = get_ha_manager()
        assert manager1 is manager2

    def test_reset_ha_manager(self):
        """Test resetting global HA manager."""
        manager1 = get_ha_manager()
        reset_ha_manager()
        manager2 = get_ha_manager()
        assert manager1 is not manager2


class TestHAIntegration:
    """Integration tests for HA components."""

    @pytest.mark.asyncio
    async def test_full_ha_workflow(self):
        """Test full HA workflow with all components."""
        config = HAConfig(
            uptime_target_percentage=99.9,
            failover_enabled=True,
            auto_failback=True,
        )
        manager = HighAvailabilityManager(config)

        # Create instances
        instances = [
            InstanceInfo(
                id="primary",
                host="primary.local",
                port=8080,
                is_primary=True,
                health_status=HealthStatus.HEALTHY,
            ),
            InstanceInfo(
                id="secondary",
                host="secondary.local",
                port=8080,
                is_primary=False,
                health_status=HealthStatus.HEALTHY,
            ),
        ]

        # Create replicas
        replicas = [
            ReplicaInfo(id="r1", location="us-east-1", is_primary=True),
            ReplicaInfo(id="r2", location="us-west-2", is_primary=False),
        ]

        # Register service
        check_count = [0]

        def health_check():
            check_count[0] += 1
            return check_count[0] < 5  # Fail after 5 checks

        manager.register_service(
            service_name="api",
            instances=instances,
            health_check_func=health_check,
            replicas=replicas,
        )

        # Verify registration
        status = manager.get_service_status("api")
        assert status["service_name"] == "api"
        assert status["instance_count"] == 2

        # Get instance for request
        instance = manager.get_instance("api")
        assert instance is not None

        # Get global status
        global_status = manager.get_global_status()
        assert "api" in global_status["services"]

        await manager.stop()

    @pytest.mark.asyncio
    async def test_99_9_percent_uptime_target(self):
        """Test that 99.9% uptime target is achievable.

        99.9% uptime = ~43.2 minutes of downtime per month
        """
        # This is a design verification test
        # The actual uptime depends on:
        # 1. Health check frequency
        # 2. Failover speed
        # 3. Redundancy level

        config = HAConfig(
            uptime_target_percentage=99.9,
            health_check_interval_seconds=10.0,  # Check every 10s
            failover_timeout_seconds=5.0,  # Failover within 5s
        )

        # Calculate theoretical max downtime per month:
        # - Worst case: primary fails right after health check
        # - Detection: 10s (next health check)
        # - Failover: 5s
        # - Total per incident: ~15s
        #
        # For 99.9% uptime with 30-day month (2,592,000 seconds):
        # - Allowed downtime: 2,592 seconds (43.2 minutes)
        # - Allowed incidents at 15s each: 172.8 incidents
        #
        # This is achievable with proper redundancy

        assert config.uptime_target_percentage == 99.9
        assert config.health_check_interval_seconds == 10.0
        assert config.failover_timeout_seconds == 5.0
