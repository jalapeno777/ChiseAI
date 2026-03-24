"""Tests for healing actions.

For ST-CONTROL-002: Self-Healing Automation
"""


import pytest

from autonomous_control_plane.healing_actions.cache_flush import CacheFlushAction
from autonomous_control_plane.healing_actions.config_reload import ConfigReloadAction
from autonomous_control_plane.healing_actions.connection_pool_reset import (
    ConnectionPoolResetAction,
)
from autonomous_control_plane.healing_actions.health_check import HealthCheckAction
from autonomous_control_plane.healing_actions.service_restart import (
    ServiceRestartAction,
)
from autonomous_control_plane.models.healing import (
    ActionPriority,
    HealingContext,
    ResourceLimits,
)


class TestServiceRestartAction:
    """Test suite for ServiceRestartAction."""

    @pytest.fixture
    def context(self):
        """Create healing context fixture."""
        return HealingContext(
            service="test_service",
            action_id="test_action_123",
        )

    def test_action_initialization(self):
        """Test action initialization."""
        action = ServiceRestartAction(service_name="my_service")

        assert action.action_type == "service_restart"
        assert action.priority == ActionPriority.P1
        assert action._service_name == "my_service"

    def test_get_resource_limits(self):
        """Test resource limits."""
        action = ServiceRestartAction()
        limits = action.get_resource_limits()

        assert isinstance(limits, ResourceLimits)
        assert limits.max_cpu_seconds == 10.0
        assert limits.max_memory_mb == 50
        assert limits.max_execution_seconds == 120.0

    def test_capture_state(self, context):
        """Test state capture."""
        action = ServiceRestartAction(service_name="my_service")
        state = action._capture_state(context)

        assert state["service"] == "my_service"
        assert state["action_type"] == "service_restart"
        assert "timestamp" in state

    def test_execute_impl(self, context):
        """Test execution."""
        action = ServiceRestartAction(service_name="my_service")
        result = action._execute_impl(context)

        assert result["success"] is True
        assert "steps" in result
        assert result["service"] == "my_service"
        assert "restarted successfully" in result["message"]

    def test_rollback_impl(self, context):
        """Test rollback."""
        action = ServiceRestartAction()
        pre_state = {
            "service": "my_service",
            "status": "running",
        }

        result = action._rollback_impl(context, pre_state)

        assert result["success"] is True
        assert "restored" in result["message"]

    def test_validate(self):
        """Test validation."""
        action = ServiceRestartAction(service_name="test")
        errors = action.validate()

        assert len(errors) == 0


class TestConfigReloadAction:
    """Test suite for ConfigReloadAction."""

    @pytest.fixture
    def context(self):
        """Create healing context fixture."""
        return HealingContext(
            service="test_service",
            action_id="test_action_123",
        )

    def test_action_initialization(self):
        """Test action initialization."""
        action = ConfigReloadAction(
            service_name="my_service",
            config_path="/etc/config.yaml",
        )

        assert action.action_type == "config_reload"
        assert action.priority == ActionPriority.P2
        assert action._config_path == "/etc/config.yaml"

    def test_get_resource_limits(self):
        """Test resource limits."""
        action = ConfigReloadAction()
        limits = action.get_resource_limits()

        assert limits.max_cpu_seconds == 5.0
        assert limits.max_memory_mb == 20
        assert limits.max_execution_seconds == 30.0

    def test_execute_impl(self, context):
        """Test execution."""
        action = ConfigReloadAction(service_name="my_service")
        result = action._execute_impl(context)

        assert result["success"] is True
        assert "steps" in result
        assert "validated_new_config" in result["steps"]
        assert "reloaded_configuration" in result["steps"]


class TestConnectionPoolResetAction:
    """Test suite for ConnectionPoolResetAction."""

    @pytest.fixture
    def context(self):
        """Create healing context fixture."""
        return HealingContext(
            service="test_service",
            action_id="test_action_123",
        )

    def test_action_initialization(self):
        """Test action initialization."""
        action = ConnectionPoolResetAction(
            service_name="my_service",
            db_type="postgres",
        )

        assert action.action_type == "connection_pool_reset"
        assert action.priority == ActionPriority.P2
        assert action._db_type == "postgres"

    def test_get_resource_limits(self):
        """Test resource limits."""
        action = ConnectionPoolResetAction()
        limits = action.get_resource_limits()

        assert limits.max_cpu_seconds == 5.0
        assert limits.max_memory_mb == 30
        assert limits.max_execution_seconds == 45.0

    def test_execute_impl(self, context):
        """Test execution."""
        action = ConnectionPoolResetAction(service_name="my_service")
        result = action._execute_impl(context)

        assert result["success"] is True
        assert result["db_type"] == "postgres"
        assert "closed_idle_connections" in result["steps"]
        assert "tested_new_connections" in result["steps"]


class TestCacheFlushAction:
    """Test suite for CacheFlushAction."""

    @pytest.fixture
    def context(self):
        """Create healing context fixture."""
        return HealingContext(
            service="test_service",
            action_id="test_action_123",
        )

    def test_action_initialization(self):
        """Test action initialization."""
        action = CacheFlushAction(
            service_name="my_service",
            cache_types=["redis", "memory"],
        )

        assert action.action_type == "cache_flush"
        assert action.priority == ActionPriority.P2
        assert action._cache_types == ["redis", "memory"]

    def test_default_cache_types(self):
        """Test default cache types."""
        action = CacheFlushAction()
        assert action._cache_types == ["redis", "memory"]

    def test_get_resource_limits(self):
        """Test resource limits."""
        action = CacheFlushAction()
        limits = action.get_resource_limits()

        assert limits.max_cpu_seconds == 10.0
        assert limits.max_memory_mb == 100
        assert limits.max_execution_seconds == 60.0

    def test_execute_impl_redis_only(self, context):
        """Test execution with Redis only."""
        action = CacheFlushAction(
            service_name="my_service",
            cache_types=["redis"],
        )
        result = action._execute_impl(context)

        assert result["success"] is True
        assert "flushed_redis_cache" in result["steps"]
        assert "flushed_memory_cache" not in result["steps"]
        assert result["flushed_caches"] == ["redis"]

    def test_execute_impl_all_caches(self, context):
        """Test execution with all cache types."""
        action = CacheFlushAction(
            service_name="my_service",
            cache_types=["redis", "memory", "disk"],
        )
        result = action._execute_impl(context)

        assert result["success"] is True
        assert "flushed_redis_cache" in result["steps"]
        assert "flushed_memory_cache" in result["steps"]
        assert "flushed_disk_cache" in result["steps"]
        assert set(result["flushed_caches"]) == {"redis", "memory", "disk"}

    def test_rollback_impl(self, context):
        """Test rollback (should be no-op for cache flush)."""
        action = CacheFlushAction()
        pre_state = {
            "service": "my_service",
            "cache_types": ["redis", "memory"],
        }

        result = action._rollback_impl(context, pre_state)

        assert result["success"] is True
        # Cache flush rollback acknowledges what was flushed
        assert "caches were flushed" in result["message"]
        assert "ephemeral" in result["note"]


class TestHealthCheckAction:
    """Test suite for HealthCheckAction."""

    @pytest.fixture
    def context(self):
        """Create healing context fixture."""
        return HealingContext(
            service="test_service",
            action_id="test_action_123",
        )

    def test_action_initialization(self):
        """Test action initialization."""
        action = HealthCheckAction(
            service_name="my_service",
            check_types=["endpoint", "dependencies"],
            endpoint="/health",
        )

        assert action.action_type == "health_check"
        assert action.priority == ActionPriority.P3
        assert action._check_types == ["endpoint", "dependencies"]
        assert action._endpoint == "/health"

    def test_get_resource_limits(self):
        """Test resource limits."""
        action = HealthCheckAction()
        limits = action.get_resource_limits()

        assert limits.max_cpu_seconds == 5.0
        assert limits.max_memory_mb == 20
        assert limits.max_execution_seconds == 30.0

    def test_execute_impl_all_checks(self, context):
        """Test execution with all check types."""
        action = HealthCheckAction(
            service_name="my_service",
            check_types=["endpoint", "dependencies", "resources", "config"],
        )
        result = action._execute_impl(context)

        assert result["success"] is True
        assert result["status"] == "healthy"
        assert "checks" in result
        assert "endpoint" in result["checks"]
        assert "dependencies" in result["checks"]
        assert "resources" in result["checks"]
        assert "config" in result["checks"]

    def test_execute_impl_partial_checks(self, context):
        """Test execution with partial check types."""
        action = HealthCheckAction(
            service_name="my_service",
            check_types=["endpoint"],
        )
        result = action._execute_impl(context)

        assert result["success"] is True
        assert "endpoint" in result["checks"]
        assert "dependencies" not in result["checks"]

    def test_rollback_impl(self, context):
        """Test rollback (should be no-op for health checks)."""
        action = HealthCheckAction()
        pre_state = {}

        result = action._rollback_impl(context, pre_state)

        assert result["success"] is True
        assert "no action needed" in result["message"]
        assert "read-only" in result["message"]
