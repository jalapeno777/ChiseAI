"""Tests for High Availability Infrastructure (NFR-006)."""

import asyncio
from datetime import datetime

import pytest
from src.infrastructure.ha.health_check import (
    HealthCheckConfig,
    HealthChecker,
    HealthCheckRegistry,
    HealthCheckResult,
    HealthStatus,
    get_registry,
    reset_registry,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test that all expected health statuses exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_health_check_result_creation(self):
        """Test creating a health check result."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            latency_ms=10.5,
        )
        assert result.name == "test_check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.latency_ms == 10.5
        assert isinstance(result.timestamp, datetime)

    def test_health_check_result_to_dict(self):
        """Test converting result to dictionary."""
        result = HealthCheckResult(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            latency_ms=10.5,
        )
        data = result.to_dict()
        assert data["name"] == "test_check"
        assert data["status"] == "healthy"
        assert data["message"] == "All good"
        assert data["latency_ms"] == 10.5


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HealthCheckConfig(name="test", check_func=lambda: True)
        assert config.name == "test"
        assert config.interval_seconds == 30.0
        assert config.timeout_seconds == 5.0
        assert config.unhealthy_threshold == 3
        assert config.healthy_threshold == 2
        assert config.critical is False

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HealthCheckConfig(
            name="critical_check",
            check_func=lambda: True,
            interval_seconds=60.0,
            timeout_seconds=10.0,
            critical=True,
        )
        assert config.name == "critical_check"
        assert config.interval_seconds == 60.0
        assert config.timeout_seconds == 10.0
        assert config.critical is True


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.mark.asyncio
    async def test_successful_check(self):
        """Test a successful health check."""
        config = HealthCheckConfig(name="success_check", check_func=lambda: True)
        checker = HealthChecker(config)

        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY
        assert checker.is_healthy is True

    @pytest.mark.asyncio
    async def test_failed_check(self):
        """Test a failed health check."""
        config = HealthCheckConfig(name="fail_check", check_func=lambda: False)
        checker = HealthChecker(config)

        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert checker.is_healthy is False

    @pytest.mark.asyncio
    async def test_async_check_function(self):
        """Test with async check function."""

        async def async_check():
            return True

        config = HealthCheckConfig(name="async_check", check_func=async_check)
        checker = HealthChecker(config)

        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_timeout_check(self):
        """Test check that times out."""

        async def slow_check():
            await asyncio.sleep(10)
            return True

        config = HealthCheckConfig(
            name="timeout_check",
            check_func=slow_check,
            timeout_seconds=0.1,
        )
        checker = HealthChecker(config)

        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.message.lower()

    def test_is_critical_property(self):
        """Test is_critical property."""
        critical_config = HealthCheckConfig(
            name="critical", check_func=lambda: True, critical=True
        )
        non_critical_config = HealthCheckConfig(
            name="non_critical", check_func=lambda: True, critical=False
        )

        assert HealthChecker(critical_config).is_critical is True
        assert HealthChecker(non_critical_config).is_critical is False


class TestHealthCheckRegistry:
    """Tests for HealthCheckRegistry class."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_register_health_check(self):
        """Test registering a health check."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(name="test_check", check_func=lambda: True)

        checker = registry.register(config)

        assert checker.name == "test_check"
        assert "test_check" in registry.get_all()

    def test_duplicate_registration_raises(self):
        """Test that duplicate registration raises error."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(name="duplicate", check_func=lambda: True)

        registry.register(config)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(config)

    def test_unregister_health_check(self):
        """Test unregistering a health check."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(name="to_remove", check_func=lambda: True)

        registry.register(config)
        result = registry.unregister("to_remove")

        assert result is True
        assert "to_remove" not in registry.get_all()

    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent check."""
        registry = HealthCheckRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_critical_checkers(self):
        """Test getting critical checkers."""
        registry = HealthCheckRegistry()

        registry.register(
            HealthCheckConfig(name="critical1", check_func=lambda: True, critical=True)
        )
        registry.register(
            HealthCheckConfig(
                name="non_critical", check_func=lambda: True, critical=False
            )
        )
        registry.register(
            HealthCheckConfig(name="critical2", check_func=lambda: True, critical=True)
        )

        critical = registry.get_critical()
        assert len(critical) == 2

    @pytest.mark.asyncio
    async def test_check_all(self):
        """Test checking all registered health checks."""
        registry = HealthCheckRegistry()
        registry.register(HealthCheckConfig(name="check1", check_func=lambda: True))
        registry.register(HealthCheckConfig(name="check2", check_func=lambda: False))

        results = await registry.check_all()

        assert len(results) == 2
        assert results["check1"].status == HealthStatus.HEALTHY
        assert results["check2"].status == HealthStatus.UNHEALTHY

    def test_get_overall_status_all_healthy(self):
        """Test overall status when all checks are healthy."""
        registry = HealthCheckRegistry()
        checker1 = registry.register(
            HealthCheckConfig(name="check1", check_func=lambda: True)
        )
        checker2 = registry.register(
            HealthCheckConfig(name="check2", check_func=lambda: True)
        )

        # Manually set healthy results
        checker1._last_result = HealthCheckResult(
            name="check1", status=HealthStatus.HEALTHY
        )
        checker2._last_result = HealthCheckResult(
            name="check2", status=HealthStatus.HEALTHY
        )

        assert registry.get_overall_status() == HealthStatus.HEALTHY

    def test_get_overall_status_no_checks(self):
        """Test overall status with no checks registered."""
        registry = HealthCheckRegistry()
        assert registry.get_overall_status() == HealthStatus.UNKNOWN


class TestGetRegistry:
    """Tests for global registry functions."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()

    def test_get_registry_singleton(self):
        """Test that get_registry returns singleton."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_reset_registry(self):
        """Test resetting the global registry."""
        registry1 = get_registry()
        reset_registry()
        registry2 = get_registry()

        assert registry1 is not registry2
