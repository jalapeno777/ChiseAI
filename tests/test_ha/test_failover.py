"""Tests for Failover Manager."""

import pytest
from src.infrastructure.ha.failover import (
    FailoverConfig,
    FailoverManager,
    FailoverState,
    InstanceInfo,
)
from src.infrastructure.ha.health_check import HealthStatus


class TestInstanceInfo:
    """Tests for InstanceInfo."""

    def test_instance_creation(self):
        """Test creating an instance info."""
        instance = InstanceInfo(
            id="test-1",
            host="localhost",
            port=8080,
            is_primary=True,
        )
        assert instance.id == "test-1"
        assert instance.host == "localhost"
        assert instance.port == 8080
        assert instance.is_primary
        assert not instance.is_active

    def test_instance_to_dict(self):
        """Test converting instance to dictionary."""
        instance = InstanceInfo(
            id="test-1",
            host="localhost",
            port=8080,
            priority=5,
            weight=50,
        )
        d = instance.to_dict()
        assert d["id"] == "test-1"
        assert d["host"] == "localhost"
        assert d["port"] == 8080
        assert d["priority"] == 5
        assert d["weight"] == 50


class TestFailoverManager:
    """Tests for FailoverManager."""

    def test_failover_manager_creation(self):
        """Test creating a failover manager."""
        config = FailoverConfig()
        manager = FailoverManager(config)
        assert manager.state == FailoverState.UNAVAILABLE
        assert manager.active_instance is None

    def test_register_instance(self, failover_manager, sample_instance):
        """Test registering an instance."""
        failover_manager.register_instance(sample_instance)
        assert failover_manager.active_instance is not None
        assert failover_manager.active_instance.id == sample_instance.id
        assert failover_manager.state == FailoverState.PRIMARY_ACTIVE

    def test_unregister_instance(self, failover_manager, sample_instance):
        """Test unregistering an instance."""
        failover_manager.register_instance(sample_instance)
        assert failover_manager.unregister_instance(sample_instance.id)
        assert failover_manager.active_instance is None
        assert not failover_manager.unregister_instance("nonexistent")

    def test_update_health_triggers_failover(self, failover_manager, sample_instances):
        """Test that health update can trigger failover."""
        config = FailoverConfig(
            failure_threshold=1,
            cooldown_seconds=0,
        )
        manager = FailoverManager(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            manager.register_instance(inst)

        assert manager.state == FailoverState.PRIMARY_ACTIVE

        # Mark primary as unhealthy
        manager.update_instance_health("primary-1", HealthStatus.UNHEALTHY)

        # Should have failed over to secondary
        assert manager.state == FailoverState.SECONDARY_ACTIVE
        assert manager.active_instance.id in ("secondary-1", "secondary-2")

    def test_failback_to_primary(self, failover_manager, sample_instances):
        """Test failback to primary when it recovers."""
        config = FailoverConfig(
            failure_threshold=1,
            recovery_threshold=1,
            auto_failback=True,
            failback_delay_seconds=0,
            cooldown_seconds=0,
        )
        manager = FailoverManager(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            manager.register_instance(inst)

        # Failover
        manager.update_instance_health("primary-1", HealthStatus.UNHEALTHY)
        assert manager.state == FailoverState.SECONDARY_ACTIVE

        # Recover primary
        manager.update_instance_health("primary-1", HealthStatus.HEALTHY)
        manager.update_instance_health(
            "primary-1", HealthStatus.HEALTHY
        )  # Meet threshold

        # Should failback
        assert manager.state == FailoverState.PRIMARY_ACTIVE

    def test_no_failback_when_disabled(self, sample_instances):
        """Test that failback doesn't happen when disabled."""
        config = FailoverConfig(
            failure_threshold=1,
            recovery_threshold=1,
            auto_failback=False,
            cooldown_seconds=0,
        )
        manager = FailoverManager(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            manager.register_instance(inst)

        # Failover
        manager.update_instance_health("primary-1", HealthStatus.UNHEALTHY)
        assert manager.state == FailoverState.SECONDARY_ACTIVE

        # Recover primary - should NOT failback
        manager.update_instance_health("primary-1", HealthStatus.HEALTHY)
        manager.update_instance_health("primary-1", HealthStatus.HEALTHY)

        assert manager.state == FailoverState.SECONDARY_ACTIVE

    def test_cooldown_prevents_failover(self, sample_instances):
        """Test that cooldown prevents rapid failovers."""
        config = FailoverConfig(
            failure_threshold=1,
            cooldown_seconds=60,
        )
        manager = FailoverManager(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            manager.register_instance(inst)

        # First failover should work
        manager.update_instance_health("primary-1", HealthStatus.UNHEALTHY)
        assert manager.state == FailoverState.SECONDARY_ACTIVE

        # Get current active
        active_id = manager.active_instance.id

        # Mark current as unhealthy - should NOT failover due to cooldown
        manager.update_instance_health(active_id, HealthStatus.UNHEALTHY)
        # Still on the same instance (failover blocked)
        assert manager.active_instance.id == active_id

    def test_force_failover(self, failover_manager, sample_instances):
        """Test forced failover."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            failover_manager.register_instance(inst)

        assert failover_manager.force_failover("secondary-1")
        assert failover_manager.active_instance.id == "secondary-1"

    def test_force_failover_to_unhealthy_fails(
        self, failover_manager, sample_instances
    ):
        """Test that force failover to unhealthy instance fails."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            failover_manager.register_instance(inst)

        sample_instances[1].health_status = HealthStatus.UNHEALTHY
        assert not failover_manager.force_failover("secondary-1")

    def test_callbacks(self, failover_manager, sample_instances):
        """Test failover callbacks."""
        events = []

        def callback(event_type, data):
            events.append((event_type, data))

        failover_manager.add_callback(callback)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            failover_manager.register_instance(inst)

        failover_manager._perform_failover()

        assert len(events) >= 2
        assert events[0][0] == "failover_start"

    def test_get_status(self, failover_manager, sample_instance):
        """Test getting failover status."""
        failover_manager.register_instance(sample_instance)
        status = failover_manager.get_status()

        assert status["state"] == FailoverState.PRIMARY_ACTIVE.value
        assert status["active_instance"]["id"] == sample_instance.id
        assert status["failover_count"] == 0

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, failover_manager, sample_instances):
        """Test starting and stopping monitoring."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            failover_manager.register_instance(inst)

        await failover_manager.start_monitoring()
        assert failover_manager._running

        await failover_manager.stop_monitoring()
        assert not failover_manager._running
