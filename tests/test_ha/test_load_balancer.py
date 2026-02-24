"""Tests for Load Balancer."""
import pytest

from src.infrastructure.ha.load_balancer import (
    LoadBalancingStrategy, ConnectionStats, LoadBalancerConfig,
    LoadBalancer, ConnectionContext
)
from src.infrastructure.ha.failover import InstanceInfo
from src.infrastructure.ha.health_check import HealthStatus


class TestLoadBalancingStrategy:
    """Tests for LoadBalancingStrategy enum."""
    
    def test_strategy_values(self):
        """Test that all expected strategy values exist."""
        assert LoadBalancingStrategy.ROUND_ROBIN.value == "round_robin"
        assert LoadBalancingStrategy.LEAST_CONNECTIONS.value == "least_connections"
        assert LoadBalancingStrategy.RANDOM.value == "random"


class TestConnectionStats:
    """Tests for ConnectionStats dataclass."""
    
    def test_stats_defaults(self):
        """Test default stats values."""
        stats = ConnectionStats()
        assert stats.active_connections == 0
        assert stats.total_connections == 0
        assert stats.total_requests == 0
    
    def test_stats_to_dict(self):
        """Test serializing stats to dict."""
        stats = ConnectionStats(
            active_connections=5,
            total_connections=100,
            total_requests=500,
        )
        d = stats.to_dict()
        assert d["active_connections"] == 5
        assert d["total_connections"] == 100
        assert d["total_requests"] == 500


class TestLoadBalancerConfig:
    """Tests for LoadBalancerConfig dataclass."""
    
    def test_config_defaults(self):
        """Test default config values."""
        config = LoadBalancerConfig()
        assert config.strategy == LoadBalancingStrategy.ROUND_ROBIN
        assert config.max_connections_per_instance == 1000
        assert config.sticky_sessions is False


class TestLoadBalancer:
    """Tests for LoadBalancer class."""
    
    def test_register_instance(self, load_balancer, instance_info):
        """Test registering an instance."""
        instance_info.health_status = HealthStatus.HEALTHY
        load_balancer.register_instance(instance_info)
        assert "test-instance-1" in load_balancer._instances
    
    def test_unregister_instance(self, load_balancer, instance_info):
        """Test unregistering an instance."""
        load_balancer.register_instance(instance_info)
        result = load_balancer.unregister_instance("test-instance-1")
        assert result is True
        assert "test-instance-1" not in load_balancer._instances
    
    def test_unregister_nonexistent(self, load_balancer):
        """Test unregistering non-existent instance."""
        result = load_balancer.unregister_instance("nonexistent")
        assert result is False
    
    def test_select_instance_no_healthy(self, load_balancer, instance_info):
        """Test selecting instance when none are healthy."""
        instance_info.health_status = HealthStatus.UNHEALTHY
        load_balancer.register_instance(instance_info)
        selected = load_balancer.select_instance()
        assert selected is None
    
    def test_select_instance_round_robin(self, load_balancer):
        """Test round-robin selection strategy."""
        load_balancer.config.strategy = LoadBalancingStrategy.ROUND_ROBIN
        for i in range(3):
            inst = InstanceInfo(id=f"inst-{i}", host="h", port=8080 + i)
            inst.health_status = HealthStatus.HEALTHY
            load_balancer.register_instance(inst)
        
        # Round-robin should cycle through instances
        selected1 = load_balancer.select_instance()
        selected2 = load_balancer.select_instance()
        selected3 = load_balancer.select_instance()
        
        # All should be valid selections
        assert selected1 is not None
        assert selected2 is not None
        assert selected3 is not None
    
    def test_select_instance_least_connections(self):
        """Test least-connections selection strategy."""
        config = LoadBalancerConfig(strategy=LoadBalancingStrategy.LEAST_CONNECTIONS)
        lb = LoadBalancer(config)
        
        for i in range(3):
            inst = InstanceInfo(id=f"inst-{i}", host="h", port=8080 + i)
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)
        
        # Give first instance more connections
        lb._connection_stats["inst-0"].active_connections = 10
        lb._connection_stats["inst-1"].active_connections = 5
        lb._connection_stats["inst-2"].active_connections = 2
        
        selected = lb.select_instance()
        assert selected.id == "inst-2"  # Has least connections
    
    def test_sticky_sessions(self):
        """Test sticky sessions."""
        config = LoadBalancerConfig(sticky_sessions=True)
        lb = LoadBalancer(config)
        
        inst = InstanceInfo(id="inst-1", host="h", port=8080)
        inst.health_status = HealthStatus.HEALTHY
        lb.register_instance(inst)
        
        # First request
        selected1 = lb.select_instance(session_id="session-1")
        # Second request with same session should get same instance
        selected2 = lb.select_instance(session_id="session-1")
        
        assert selected1.id == selected2.id
    
    def test_sticky_session_fails_over(self):
        """Test that sticky session fails over when instance becomes unhealthy."""
        config = LoadBalancerConfig(sticky_sessions=True)
        lb = LoadBalancer(config)
        
        inst1 = InstanceInfo(id="inst-1", host="h1", port=8080)
        inst2 = InstanceInfo(id="inst-2", host="h2", port=8081)
        inst1.health_status = HealthStatus.HEALTHY
        inst2.health_status = HealthStatus.HEALTHY
        lb.register_instance(inst1)
        lb.register_instance(inst2)
        
        lb.select_instance(session_id="session-1")
        
        # First instance becomes unhealthy
        inst1.health_status = HealthStatus.UNHEALTHY
        
        # Should select different instance
        selected = lb.select_instance(session_id="session-1")
        assert selected.id == "inst-2"
    
    def test_acquire_connection(self, load_balancer, instance_info):
        """Test acquiring a connection."""
        load_balancer.register_instance(instance_info)
        result = load_balancer.acquire_connection("test-instance-1")
        assert result is True
        assert load_balancer._connection_stats["test-instance-1"].active_connections == 1
    
    def test_acquire_connection_nonexistent(self, load_balancer):
        """Test acquiring connection for non-existent instance."""
        result = load_balancer.acquire_connection("nonexistent")
        assert result is False
    
    def test_acquire_connection_max_reached(self):
        """Test acquiring connection when max is reached."""
        config = LoadBalancerConfig(max_connections_per_instance=2)
        lb = LoadBalancer(config)
        
        inst = InstanceInfo(id="inst-1", host="h", port=8080)
        lb.register_instance(inst)
        
        assert lb.acquire_connection("inst-1") is True
        assert lb.acquire_connection("inst-1") is True
        assert lb.acquire_connection("inst-1") is False  # Max reached
    
    def test_release_connection(self, load_balancer, instance_info):
        """Test releasing a connection."""
        load_balancer.register_instance(instance_info)
        load_balancer.acquire_connection("test-instance-1")
        load_balancer.release_connection("test-instance-1")
        assert load_balancer._connection_stats["test-instance-1"].active_connections == 0
    
    def test_record_request(self, load_balancer, instance_info):
        """Test recording request stats."""
        load_balancer.register_instance(instance_info)
        load_balancer.record_request("test-instance-1", success=True, response_time_ms=50.0)
        
        stats = load_balancer._connection_stats["test-instance-1"]
        assert stats.total_requests == 1
        assert stats.total_response_time_ms == 50.0
    
    def test_record_failed_request(self, load_balancer, instance_info):
        """Test recording failed request."""
        load_balancer.register_instance(instance_info)
        load_balancer.record_request("test-instance-1", success=False, response_time_ms=100.0)
        
        stats = load_balancer._connection_stats["test-instance-1"]
        assert stats.failed_requests == 1
    
    def test_get_stats(self, load_balancer, instance_info):
        """Test getting load balancer stats."""
        instance_info.health_status = HealthStatus.HEALTHY
        load_balancer.register_instance(instance_info)
        stats = load_balancer.get_stats()
        
        assert "strategy" in stats
        assert "total_instances" in stats
        assert "healthy_instances" in stats
        assert stats["total_instances"] == 1


class TestConnectionContext:
    """Tests for ConnectionContext context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using connection context manager."""
        lb = LoadBalancer()
        inst = InstanceInfo(id="inst-1", host="h", port=8080)
        inst.health_status = HealthStatus.HEALTHY
        lb.register_instance(inst)
        
        async with ConnectionContext(lb) as instance:
            assert instance is not None
            assert instance.id == "inst-1"
            # Connection should be acquired
            assert lb._connection_stats["inst-1"].active_connections == 1
        
        # Connection should be released after context
        assert lb._connection_stats["inst-1"].active_connections == 0
    
    @pytest.mark.asyncio
    async def test_context_manager_records_request(self):
        """Test that context manager records request stats."""
        lb = LoadBalancer()
        inst = InstanceInfo(id="inst-1", host="h", port=8080)
        inst.health_status = HealthStatus.HEALTHY
        lb.register_instance(inst)
        
        async with ConnectionContext(lb) as instance:
            pass  # Successful request
        
        assert lb._connection_stats["inst-1"].total_requests == 1
    
    @pytest.mark.asyncio
    async def test_context_manager_no_instance(self):
        """Test context manager when no instance available."""
        lb = LoadBalancer()
        
        async with ConnectionContext(lb) as instance:
            assert instance is None
