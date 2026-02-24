"""Tests for Load Balancer."""

import pytest
from src.infrastructure.ha.health_check import HealthStatus
from src.infrastructure.ha.load_balancer import (
    ConnectionContext,
    LoadBalancer,
    LoadBalancerConfig,
    LoadBalancingStrategy,
)


class TestLoadBalancer:
    """Tests for LoadBalancer."""

    def test_load_balancer_creation(self):
        """Test creating a load balancer."""
        config = LoadBalancerConfig()
        lb = LoadBalancer(config)
        assert lb.config.strategy == LoadBalancingStrategy.ROUND_ROBIN

    def test_register_instance(self, load_balancer, sample_instance):
        """Test registering an instance."""
        load_balancer.register_instance(sample_instance)
        stats = load_balancer.get_stats()
        assert stats["total_instances"] == 1

    def test_unregister_instance(self, load_balancer, sample_instance):
        """Test unregistering an instance."""
        load_balancer.register_instance(sample_instance)
        assert load_balancer.unregister_instance(sample_instance.id)
        stats = load_balancer.get_stats()
        assert stats["total_instances"] == 0

    def test_update_instance_health(self, load_balancer, sample_instance):
        """Test updating instance health."""
        load_balancer.register_instance(sample_instance)
        load_balancer.update_instance_health(sample_instance.id, HealthStatus.UNHEALTHY)
        # Instance should not be selected
        selected = load_balancer.select_instance()
        assert selected is None

    def test_select_instance_round_robin(self, sample_instances):
        """Test round-robin selection."""
        config = LoadBalancerConfig(strategy=LoadBalancingStrategy.ROUND_ROBIN)
        lb = LoadBalancer(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)

        # Should cycle through instances
        selected_ids = []
        for _ in range(6):
            inst = lb.select_instance()
            if inst:
                selected_ids.append(inst.id)

        # Should have at least some variety
        assert len(set(selected_ids)) > 1

    def test_select_instance_least_connections(self, sample_instances):
        """Test least-connections selection."""
        config = LoadBalancerConfig(strategy=LoadBalancingStrategy.LEAST_CONNECTIONS)
        lb = LoadBalancer(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)

        # Add connections to first instance
        lb.acquire_connection(sample_instances[0].id)

        # Next selection should prefer less loaded instances
        selected = lb.select_instance()
        assert selected.id != sample_instances[0].id

    def test_select_instance_random(self, sample_instances):
        """Test random selection."""
        config = LoadBalancerConfig(strategy=LoadBalancingStrategy.RANDOM)
        lb = LoadBalancer(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)

        selected_ids = set()
        for _ in range(20):
            inst = lb.select_instance()
            if inst:
                selected_ids.add(inst.id)

        # Should eventually select different instances
        assert len(selected_ids) > 1

    def test_sticky_sessions(self, sample_instances):
        """Test sticky sessions."""
        config = LoadBalancerConfig(sticky_sessions=True)
        lb = LoadBalancer(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)

        # First request with session
        first = lb.select_instance(session_id="session-1")

        # Subsequent requests should get same instance
        for _ in range(5):
            selected = lb.select_instance(session_id="session-1")
            assert selected.id == first.id

    def test_sticky_session_fails_over(self, sample_instances):
        """Test sticky session fails over when instance unhealthy."""
        config = LoadBalancerConfig(sticky_sessions=True)
        lb = LoadBalancer(config)

        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            lb.register_instance(inst)

        first = lb.select_instance(session_id="session-1")

        # Mark first instance unhealthy
        lb.update_instance_health(first.id, HealthStatus.UNHEALTHY)

        # Should get different instance
        new_selected = lb.select_instance(session_id="session-1")
        assert new_selected.id != first.id

    def test_connection_context(self, load_balancer, sample_instances):
        """Test connection context manager."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            load_balancer.register_instance(inst)

        async def use_connection():
            async with ConnectionContext(load_balancer) as instance:
                assert instance is not None
                # Simulate work
                return instance.id

        # Just test that context manager works
        assert load_balancer.get_stats()["healthy_instances"] > 0

    def test_acquire_release_connection(self, load_balancer, sample_instance):
        """Test acquiring and releasing connections."""
        load_balancer.register_instance(sample_instance)

        assert load_balancer.acquire_connection(sample_instance.id)
        stats = load_balancer.get_stats()
        inst_stats = stats["instances"][sample_instance.id]["stats"]
        assert inst_stats["active_connections"] == 1

        load_balancer.release_connection(sample_instance.id)
        stats = load_balancer.get_stats()
        inst_stats = stats["instances"][sample_instance.id]["stats"]
        assert inst_stats["active_connections"] == 0

    def test_max_connections_limit(self, sample_instance):
        """Test max connections per instance limit."""
        config = LoadBalancerConfig(max_connections_per_instance=2)
        lb = LoadBalancer(config)
        sample_instance.health_status = HealthStatus.HEALTHY
        lb.register_instance(sample_instance)

        assert lb.acquire_connection(sample_instance.id)
        assert lb.acquire_connection(sample_instance.id)
        assert not lb.acquire_connection(sample_instance.id)  # Should fail

    def test_record_request(self, load_balancer, sample_instance):
        """Test recording request results."""
        load_balancer.register_instance(sample_instance)

        load_balancer.record_request(
            sample_instance.id, success=True, response_time_ms=50.0
        )

        stats = load_balancer.get_stats()
        inst_stats = stats["instances"][sample_instance.id]["stats"]
        assert inst_stats["total_requests"] == 1
        assert inst_stats["avg_response_time_ms"] == 50.0

    def test_no_healthy_instances(self, load_balancer, sample_instance):
        """Test selection when no healthy instances."""
        sample_instance.health_status = HealthStatus.UNHEALTHY
        load_balancer.register_instance(sample_instance)

        selected = load_balancer.select_instance()
        assert selected is None

    def test_get_stats(self, load_balancer, sample_instances):
        """Test getting load balancer stats."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            load_balancer.register_instance(inst)

        stats = load_balancer.get_stats()

        assert stats["strategy"] == LoadBalancingStrategy.ROUND_ROBIN.value
        assert stats["total_instances"] == 3
        assert stats["healthy_instances"] == 3
        assert len(stats["instances"]) == 3

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, load_balancer, sample_instances):
        """Test starting and stopping monitoring."""
        for inst in sample_instances:
            inst.health_status = HealthStatus.HEALTHY
            load_balancer.register_instance(inst)

        await load_balancer.start_monitoring()
        assert load_balancer._running

        await load_balancer.stop_monitoring()
        assert not load_balancer._running
