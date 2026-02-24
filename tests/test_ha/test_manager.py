"""Tests for High Availability Manager."""
import pytest
from datetime import datetime, timezone

from src.infrastructure.ha.manager import (
    HAConfig, HighAvailabilityManager, get_ha_manager, reset_ha_manager
)
from src.infrastructure.ha.failover import InstanceInfo
from src.infrastructure.ha.health_check import HealthStatus
from src.infrastructure.ha.load_balancer import LoadBalancingStrategy


class TestHAConfig:
    """Tests for HAConfig dataclass."""
    
    def test_config_defaults(self):
        """Test default config values."""
        config = HAConfig()
        assert config.health_check_interval_seconds == 30.0
        assert config.failover_enabled is True
        assert config.uptime_target_percentage == 99.9
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = HAConfig(
            health_check_interval_seconds=15.0,
            failover_enabled=False,
            load_balancing_strategy=LoadBalancingStrategy.LEAST_CONNECTIONS,
        )
        assert config.health_check_interval_seconds == 15.0
        assert config.failover_enabled is False


class TestHighAvailabilityManager:
    """Tests for HighAvailabilityManager class."""
    
    def test_initial_state(self, ha_manager):
        """Test initial manager state."""
        assert ha_manager._running is False
        assert len(ha_manager._services) == 0
    
    def test_register_service(self, ha_manager):
        """Test registering a service."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        assert "test-service" in ha_manager._services
    
    def test_unregister_service(self, ha_manager):
        """Test unregistering a service."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        result = ha_manager.unregister_service("test-service")
        assert result is True
        assert "test-service" not in ha_manager._services
    
    def test_unregister_nonexistent(self, ha_manager):
        """Test unregistering non-existent service."""
        result = ha_manager.unregister_service("nonexistent")
        assert result is False
    
    def test_get_instance(self, ha_manager):
        """Test getting an instance from load balancer."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        instances[0].health_status = HealthStatus.HEALTHY
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        instance = ha_manager.get_instance("test-service")
        assert instance is not None
    
    def test_get_service_status(self, ha_manager):
        """Test getting service status."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        status = ha_manager.get_service_status("test-service")
        assert status is not None
        assert status["service_name"] == "test-service"
    
    def test_get_service_status_nonexistent(self, ha_manager):
        """Test getting status of non-existent service."""
        status = ha_manager.get_service_status("nonexistent")
        assert status is None
    
    def test_get_global_status(self, ha_manager):
        """Test getting global status."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        status = ha_manager.get_global_status()
        assert "services" in status
        assert "health_registry" in status
        assert "failover" in status
        assert "load_balancer" in status
    
    def test_get_recent_alerts(self, ha_manager):
        """Test getting recent alerts."""
        alerts = ha_manager.get_recent_alerts()
        assert isinstance(alerts, list)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, ha_manager):
        """Test starting and stopping manager."""
        await ha_manager.start()
        assert ha_manager._running is True
        await ha_manager.stop()
        assert ha_manager._running is False
    
    @pytest.mark.asyncio
    async def test_context_manager(self, ha_config):
        """Test using manager as context manager."""
        async with HighAvailabilityManager(ha_config) as manager:
            assert manager._running is True
        assert manager._running is False
    
    def test_to_dict(self, ha_manager):
        """Test serializing manager to dict."""
        instances = [
            InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True),
        ]
        ha_manager.register_service(
            service_name="test-service",
            instances=instances,
            health_check_func=lambda: True,
        )
        d = ha_manager.to_dict()
        assert "services" in d


class TestGlobalManager:
    """Tests for global manager functions."""
    
    def test_get_ha_manager_singleton(self):
        """Test that get_ha_manager returns singleton."""
        reset_ha_manager()
        m1 = get_ha_manager()
        m2 = get_ha_manager()
        assert m1 is m2
    
    def test_reset_ha_manager(self):
        """Test resetting the global manager."""
        m1 = get_ha_manager()
        reset_ha_manager()
        m2 = get_ha_manager()
        assert m1 is not m2


class TestHAIntegration:
    """Integration tests for HA Manager."""
    
    @pytest.mark.asyncio
    async def test_full_failover_flow(self):
        """Test complete failover flow."""
        config = HAConfig(
            unhealthy_threshold=2,
            healthy_threshold=2,
        )
        manager = HighAvailabilityManager(config)
        
        primary = InstanceInfo(id="primary", host="h1", port=8080, is_primary=True)
        backup = InstanceInfo(id="backup", host="h2", port=8081, is_primary=False)
        backup.health_status = HealthStatus.HEALTHY
        
        manager.register_service(
            service_name="test-service",
            instances=[primary, backup],
            health_check_func=lambda: True,
        )
        
        # Simulate primary failure
        for _ in range(2):
            manager._failover_manager.update_instance_health("primary", HealthStatus.UNHEALTHY)
        
        # Verify failover occurred
        assert manager._failover_manager.state.value == "secondary_active"
    
    @pytest.mark.asyncio
    async def test_health_check_propagation(self):
        """Test that health checks propagate to all components."""
        manager = HighAvailabilityManager()
        
        instance = InstanceInfo(id="inst-1", host="h1", port=8080, is_primary=True)
        manager.register_service(
            service_name="test-service",
            instances=[instance],
            health_check_func=lambda: True,
        )
        
        # Trigger health check callback
        from src.infrastructure.ha.health_check import HealthCheckResult
        result = HealthCheckResult(
            name="test-service_health",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        manager._on_health_check_result("test-service_health", result)
        
        # Verify status was recorded in uptime monitor
        status = manager._uptime_monitor.get_service_status("test-service")
        assert status["current_status"] == "healthy"
