"""Tests for Failover Manager."""
import asyncio
import pytest
from datetime import datetime, timezone

from src.infrastructure.ha.failover import (
    FailoverState, InstanceInfo, FailoverConfig, FailoverManager
)
from src.infrastructure.ha.health_check import HealthStatus


class TestFailoverState:
    """Tests for FailoverState enum."""
    
    def test_state_values(self):
        """Test that all expected state values exist."""
        assert FailoverState.PRIMARY_ACTIVE.value == "primary_active"
        assert FailoverState.FAILOVER_IN_PROGRESS.value == "failover_in_progress"
        assert FailoverState.SECONDARY_ACTIVE.value == "secondary_active"
        assert FailoverState.UNAVAILABLE.value == "unavailable"


class TestInstanceInfo:
    """Tests for InstanceInfo dataclass."""
    
    def test_instance_creation(self):
        """Test creating an instance."""
        instance = InstanceInfo(
            id="inst-1",
            host="localhost",
            port=8080,
        )
        assert instance.id == "inst-1"
        assert instance.host == "localhost"
        assert instance.port == 8080
        assert instance.is_primary is False
    
    def test_instance_to_dict(self):
        """Test serializing instance to dict."""
        instance = InstanceInfo(
            id="inst-1",
            host="localhost",
            port=8080,
            is_primary=True,
            health_status=HealthStatus.HEALTHY,
        )
        d = instance.to_dict()
        assert d["id"] == "inst-1"
        assert d["host"] == "localhost"
        assert d["port"] == 8080
        assert d["is_primary"] is True
        assert d["health_status"] == "healthy"


class TestFailoverConfig:
    """Tests for FailoverConfig dataclass."""
    
    def test_config_defaults(self):
        """Test default config values."""
        config = FailoverConfig()
        assert config.health_check_interval_seconds == 10.0
        assert config.failure_threshold == 3
        assert config.recovery_threshold == 2
        assert config.auto_failback is True
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = FailoverConfig(
            failure_threshold=5,
            auto_failback=False,
            failback_delay_seconds=120.0,
        )
        assert config.failure_threshold == 5
        assert config.auto_failback is False
        assert config.failback_delay_seconds == 120.0


class TestFailoverManager:
    """Tests for FailoverManager class."""
    
    def test_initial_state(self, failover_manager):
        """Test initial failover state."""
        assert failover_manager.state == FailoverState.UNAVAILABLE
        assert failover_manager.active_instance is None
    
    def test_register_instance(self, failover_manager, instance_info):
        """Test registering an instance."""
        failover_manager.register_instance(instance_info)
        assert "test-instance-1" in failover_manager._instances
        assert failover_manager.state == FailoverState.PRIMARY_ACTIVE
        assert failover_manager.active_instance.id == "test-instance-1"
    
    def test_unregister_instance(self, failover_manager, instance_info):
        """Test unregistering an instance."""
        failover_manager.register_instance(instance_info)
        result = failover_manager.unregister_instance("test-instance-1")
        assert result is True
        assert "test-instance-1" not in failover_manager._instances
    
    def test_unregister_nonexistent(self, failover_manager):
        """Test unregistering non-existent instance."""
        result = failover_manager.unregister_instance("nonexistent")
        assert result is False
    
    def test_update_instance_health_healthy(self, failover_manager, instance_info):
        """Test updating instance health to healthy."""
        failover_manager.register_instance(instance_info)
        failover_manager.update_instance_health("test-instance-1", HealthStatus.HEALTHY)
        assert failover_manager._instances["test-instance-1"].health_status == HealthStatus.HEALTHY
    
    def test_update_instance_health_unhealthy(self, failover_manager, instance_info, backup_instance):
        """Test updating instance health to unhealthy triggers failover."""
        failover_manager.register_instance(instance_info)
        backup_instance.health_status = HealthStatus.HEALTHY
        failover_manager.register_instance(backup_instance)
        
        # Trigger failures
        for _ in range(failover_manager.config.failure_threshold):
            failover_manager.update_instance_health("test-instance-1", HealthStatus.UNHEALTHY)
        
        assert failover_manager.state == FailoverState.SECONDARY_ACTIVE
        assert failover_manager.active_instance.id == "test-backup-1"
    
    def test_no_failover_without_backup(self, failover_manager, instance_info):
        """Test that failover fails without healthy backup."""
        failover_manager.register_instance(instance_info)
        
        for _ in range(failover_manager.config.failure_threshold):
            failover_manager.update_instance_health("test-instance-1", HealthStatus.UNHEALTHY)
        
        assert failover_manager.state == FailoverState.UNAVAILABLE
    
    def test_force_failover(self, failover_manager, instance_info, backup_instance):
        """Test forced failover."""
        failover_manager.register_instance(instance_info)
        backup_instance.health_status = HealthStatus.HEALTHY
        failover_manager.register_instance(backup_instance)
        
        result = failover_manager.force_failover("test-backup-1")
        assert result is True
        assert failover_manager.active_instance.id == "test-backup-1"
    
    def test_force_failover_unhealthy_target(self, failover_manager, instance_info, backup_instance):
        """Test forced failover to unhealthy target fails."""
        failover_manager.register_instance(instance_info)
        backup_instance.health_status = HealthStatus.UNHEALTHY
        failover_manager.register_instance(backup_instance)
        
        result = failover_manager.force_failover("test-backup-1")
        assert result is False
    
    def test_callback_registration(self, failover_manager):
        """Test callback registration."""
        called = []
        def callback(event, data):
            called.append(event)
        
        failover_manager.add_callback(callback)
        assert callback in failover_manager._callbacks
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, failover_manager):
        """Test starting and stopping monitoring."""
        await failover_manager.start_monitoring()
        assert failover_manager._running is True
        await failover_manager.stop_monitoring()
        assert failover_manager._running is False
    
    def test_get_status(self, failover_manager, instance_info):
        """Test getting failover status."""
        failover_manager.register_instance(instance_info)
        status = failover_manager.get_status()
        assert "state" in status
        assert "active_instance" in status
        assert "instances" in status
        assert status["state"] == "primary_active"


class TestFailback:
    """Tests for automatic failback functionality."""
    
    def test_automatic_failback(self):
        """Test automatic failback when primary recovers."""
        config = FailoverConfig(
            failure_threshold=2,
            recovery_threshold=2,
            auto_failback=True,
            failback_delay_seconds=0,  # Immediate for testing
        )
        manager = FailoverManager(config)
        
        primary = InstanceInfo(id="primary", host="h1", port=8080, is_primary=True)
        backup = InstanceInfo(id="backup", host="h2", port=8081, is_primary=False)
        backup.health_status = HealthStatus.HEALTHY
        
        manager.register_instance(primary)
        manager.register_instance(backup)
        
        # Failover
        for _ in range(2):
            manager.update_instance_health("primary", HealthStatus.UNHEALTHY)
        
        assert manager.state == FailoverState.SECONDARY_ACTIVE
        
        # Primary recovers
        primary.health_status = HealthStatus.HEALTHY
        for _ in range(2):
            manager.update_instance_health("primary", HealthStatus.HEALTHY)
        
        assert manager.state == FailoverState.PRIMARY_ACTIVE
    
    def test_failback_disabled(self):
        """Test that failback can be disabled."""
        config = FailoverConfig(
            failure_threshold=2,
            recovery_threshold=2,
            auto_failback=False,
        )
        manager = FailoverManager(config)
        
        primary = InstanceInfo(id="primary", host="h1", port=8080, is_primary=True)
        backup = InstanceInfo(id="backup", host="h2", port=8081, is_primary=False)
        backup.health_status = HealthStatus.HEALTHY
        
        manager.register_instance(primary)
        manager.register_instance(backup)
        
        # Failover
        for _ in range(2):
            manager.update_instance_health("primary", HealthStatus.UNHEALTHY)
        
        # Primary recovers
        primary.health_status = HealthStatus.HEALTHY
        for _ in range(2):
            manager.update_instance_health("primary", HealthStatus.HEALTHY)
        
        # Should still be on backup
        assert manager.state == FailoverState.SECONDARY_ACTIVE


class TestPriorityBasedFailover:
    """Tests for priority-based backup selection."""
    
    def test_selects_lower_priority(self):
        """Test that lower priority backup is selected."""
        manager = FailoverManager(FailoverConfig(failure_threshold=1))
        
        primary = InstanceInfo(id="primary", host="h1", port=8080, is_primary=True)
        backup1 = InstanceInfo(id="backup1", host="h2", port=8081, priority=10)
        backup2 = InstanceInfo(id="backup2", host="h3", port=8082, priority=5)
        backup1.health_status = HealthStatus.HEALTHY
        backup2.health_status = HealthStatus.HEALTHY
        
        manager.register_instance(primary)
        manager.register_instance(backup1)
        manager.register_instance(backup2)
        
        manager.update_instance_health("primary", HealthStatus.UNHEALTHY)
        
        # backup2 should be selected (lower priority value)
        assert manager.active_instance.id == "backup2"
