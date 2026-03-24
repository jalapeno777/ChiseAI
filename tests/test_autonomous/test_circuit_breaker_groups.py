"""Tests for circuit breaker groups feature.

ST-SAFETY-001: Circuit Breaker Groups Enhancement
"""

from __future__ import annotations

from autonomous_control_plane.models.circuit_breaker import (
    CircuitBreakerGroup,
    CircuitBreakerGroupMetrics,
    CircuitBreakerHealth,
    CircuitBreakerState,
)


class TestCircuitBreakerGroup:
    """Test CircuitBreakerGroup class."""

    def test_initial_state(self):
        """Group starts with empty members."""
        group = CircuitBreakerGroup(name="test-group")
        assert group.name == "test-group"
        assert group.member_names == []
        assert group.cascade_open is True
        assert group.cascade_close is False

    def test_add_member(self):
        """Add member to group."""
        group = CircuitBreakerGroup(name="test-group")
        group.add_member("cb1")
        assert "cb1" in group.member_names
        assert len(group.member_names) == 1

    def test_add_duplicate_member(self):
        """Adding duplicate member is ignored."""
        group = CircuitBreakerGroup(name="test-group")
        group.add_member("cb1")
        group.add_member("cb1")
        assert len(group.member_names) == 1

    def test_remove_member(self):
        """Remove member from group."""
        group = CircuitBreakerGroup(name="test-group")
        group.add_member("cb1")
        group.add_member("cb2")

        result = group.remove_member("cb1")
        assert result is True
        assert "cb1" not in group.member_names
        assert "cb2" in group.member_names

    def test_remove_nonexistent_member(self):
        """Removing nonexistent member returns False."""
        group = CircuitBreakerGroup(name="test-group")
        result = group.remove_member("cb1")
        assert result is False

    def test_to_dict(self):
        """Convert to dictionary."""
        group = CircuitBreakerGroup(
            name="test-group",
            member_names=["cb1", "cb2"],
            cascade_open=True,
            cascade_close=False,
        )
        data = group.to_dict()
        assert data["name"] == "test-group"
        assert data["member_names"] == ["cb1", "cb2"]
        assert data["cascade_open"] is True
        assert data["cascade_close"] is False

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "name": "test-group",
            "member_names": ["cb1", "cb2", "cb3"],
            "cascade_open": False,
            "cascade_close": True,
            "created_at": "2026-03-12T10:00:00",
            "updated_at": "2026-03-12T11:00:00",
        }

        group = CircuitBreakerGroup.from_dict(data)
        assert group.name == "test-group"
        assert group.member_names == ["cb1", "cb2", "cb3"]
        assert group.cascade_open is False
        assert group.cascade_close is True


class TestCircuitBreakerGroupMetrics:
    """Test CircuitBreakerGroupMetrics class."""

    def test_initial_state(self):
        """Initial metrics state."""
        metrics = CircuitBreakerGroupMetrics(group_name="test-group")
        assert metrics.group_name == "test-group"
        assert metrics.total_members == 0
        assert metrics.open_count == 0
        assert metrics.closed_count == 0
        assert metrics.half_open_count == 0
        assert metrics.total_failures == 0
        assert metrics.total_successes == 0
        assert metrics.total_rejections == 0
        assert metrics.overall_health_percent == 100.0
        assert metrics.member_health == {}

    def test_to_dict(self):
        """Convert to dictionary."""
        metrics = CircuitBreakerGroupMetrics(
            group_name="test-group",
            total_members=3,
            open_count=1,
            closed_count=2,
            overall_health_percent=66.7,
        )

        data = metrics.to_dict()
        assert data["group_name"] == "test-group"
        assert data["total_members"] == 3
        assert data["open_count"] == 1
        assert data["closed_count"] == 2
        assert data["overall_health_percent"] == 66.7

    def test_to_dict_with_member_health(self):
        """Convert to dictionary with member health."""
        metrics = CircuitBreakerGroupMetrics(group_name="test-group")
        metrics.member_health["cb1"] = CircuitBreakerHealth(
            name="cb1",
            state=CircuitBreakerState.CLOSED,
            is_healthy=True,
            failure_rate=0.05,
            rejection_rate=0.0,
        )

        data = metrics.to_dict()
        assert "member_health" in data
        assert "cb1" in data["member_health"]
        assert data["member_health"]["cb1"]["is_healthy"] is True


class TestCircuitBreakerGroupIntegration:
    """Integration tests for circuit breaker groups."""

    def test_group_with_multiple_members(self):
        """Group with multiple members."""
        group = CircuitBreakerGroup(name="api-services")
        group.add_member("api-gateway")
        group.add_member("auth-service")
        group.add_member("user-service")

        assert len(group.member_names) == 3
        assert group.member_names == ["api-gateway", "auth-service", "user-service"]

    def test_cascade_configuration(self):
        """Group with custom cascade configuration."""
        group = CircuitBreakerGroup(
            name="critical-services",
            cascade_open=True,
            cascade_close=True,
        )

        assert group.cascade_open is True
        assert group.cascade_close is True

    def test_member_management(self):
        """Add and remove members."""
        group = CircuitBreakerGroup(name="test-group")

        # Add members
        group.add_member("cb1")
        group.add_member("cb2")
        group.add_member("cb3")
        assert len(group.member_names) == 3

        # Remove member
        group.remove_member("cb2")
        assert len(group.member_names) == 2
        assert "cb2" not in group.member_names

        # Add duplicate
        group.add_member("cb1")
        assert len(group.member_names) == 2

    def test_group_metrics_aggregation(self):
        """Aggregate metrics for group members."""
        metrics = CircuitBreakerGroupMetrics(group_name="test-group")
        metrics.total_members = 5
        metrics.open_count = 1
        metrics.closed_count = 3
        metrics.half_open_count = 1
        metrics.total_failures = 50
        metrics.total_successes = 200
        metrics.total_rejections = 25

        assert metrics.total_members == 5
        assert metrics.open_count + metrics.closed_count + metrics.half_open_count == 5
        assert metrics.total_failures + metrics.total_successes == 250

    def test_overall_health_calculation(self):
        """Calculate overall health percentage."""
        metrics = CircuitBreakerGroupMetrics(group_name="test-group")
        metrics.total_members = 4

        # Add member health
        metrics.member_health["cb1"] = CircuitBreakerHealth(
            name="cb1",
            state=CircuitBreakerState.CLOSED,
            is_healthy=True,
            failure_rate=0.05,
            rejection_rate=0.0,
        )
        metrics.member_health["cb2"] = CircuitBreakerHealth(
            name="cb2",
            state=CircuitBreakerState.CLOSED,
            is_healthy=True,
            failure_rate=0.02,
            rejection_rate=0.0,
        )
        metrics.member_health["cb3"] = CircuitBreakerHealth(
            name="cb3",
            state=CircuitBreakerState.OPEN,
            is_healthy=False,
            failure_rate=0.5,
            rejection_rate=0.3,
        )
        metrics.member_health["cb4"] = CircuitBreakerHealth(
            name="cb4",
            state=CircuitBreakerState.HALF_OPEN,
            is_healthy=False,
            failure_rate=0.2,
            rejection_rate=0.1,
        )

        # Calculate health
        healthy_count = sum(1 for h in metrics.member_health.values() if h.is_healthy)
        metrics.overall_health_percent = (healthy_count / metrics.total_members) * 100

        assert metrics.overall_health_percent == 50.0  # 2 out of 4 healthy
