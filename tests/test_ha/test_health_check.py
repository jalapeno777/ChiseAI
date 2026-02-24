"""Tests for Health Check System."""

import asyncio
import pytest
from datetime import datetime, timezone

from src.infrastructure.ha.health_check import (
    HealthStatus,
    HealthCheckResult,
    HealthCheckConfig,
    HealthChecker,
    HealthCheckRegistry,
    get_registry,
    reset_registry,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test that all expected status values exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_health_check_result_creation(self):
        """Test creating a health check result."""
        result = HealthCheckResult(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        assert result.name == "test"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "OK"
        assert isinstance(result.timestamp, datetime)

    def test_health_check_result_to_dict(self):
        """Test serializing result to dict."""
        result = HealthCheckResult(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
            latency_ms=10.5,
            details={"key": "value"},
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "healthy"
        assert d["message"] == "OK"
        assert d["latency_ms"] == 10.5
        assert d["details"]["key"] == "value"


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig dataclass."""

    def test_config_defaults(self):
        """Test default config values."""
        config = HealthCheckConfig(name="test", check_func=lambda: True)
        assert config.interval_seconds == 30.0
        assert config.timeout_seconds == 5.0
        assert config.unhealthy_threshold == 3
        assert config.healthy_threshold == 2
        assert config.critical is False

    def test_config_custom_values(self):
        """Test custom config values."""
        config = HealthCheckConfig(
            name="test",
            check_func=lambda: True,
            interval_seconds=10.0,
            timeout_seconds=2.0,
            unhealthy_threshold=5,
            critical=True,
            tags=["api", "database"],
        )
        assert config.interval_seconds == 10.0
        assert config.timeout_seconds == 2.0
        assert config.unhealthy_threshold == 5
        assert config.critical is True
        assert "api" in config.tags


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.mark.asyncio
    async def test_check_passes(self, health_checker):
        """Test a passing health check."""
        result = await health_checker.check()
        assert result.status == HealthStatus.HEALTHY
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_fails(self):
        """Test a failing health check."""
        config = HealthCheckConfig(name="fail", check_func=lambda: False)
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_timeout(self):
        """Test health check timeout."""

        async def slow_check():
            await asyncio.sleep(5)
            return True

        config = HealthCheckConfig(
            name="timeout",
            check_func=slow_check,
            timeout_seconds=0.1,
        )
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "timed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_exception(self):
        """Test health check with exception."""

        def error_check():
            raise ValueError("Test error")

        config = HealthCheckConfig(name="error", check_func=error_check)
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert (
            "exception" in result.message.lower() or "error" in result.message.lower()
        )

    def test_is_healthy_property(self, health_checker):
        """Test is_healthy property."""
        assert health_checker.is_healthy is False  # No result yet

    def test_is_critical_property(self, health_checker):
        """Test is_critical property."""
        assert health_checker.is_critical is False

    @pytest.mark.asyncio
    async def test_periodic_check(self, health_checker):
        """Test starting and stopping periodic checks."""
        await health_checker.start_periodic()
        assert health_checker._running is True
        await asyncio.sleep(0.1)
        await health_checker.stop()
        assert health_checker._running is False

    def test_get_last_result(self, health_checker):
        """Test getting last result."""
        assert health_checker.get_last_result() is None


class TestHealthCheckRegistry:
    """Tests for HealthCheckRegistry class."""

    def test_register(self, health_registry):
        """Test registering a health check."""
        config = HealthCheckConfig(name="test1", check_func=lambda: True)
        checker = health_registry.register(config)
        assert checker.name == "test1"
        assert health_registry.get("test1") is checker

    def test_register_duplicate(self, health_registry):
        """Test registering duplicate check raises error."""
        config = HealthCheckConfig(name="test1", check_func=lambda: True)
        health_registry.register(config)
        with pytest.raises(ValueError, match="already registered"):
            health_registry.register(config)

    def test_unregister(self, health_registry):
        """Test unregistering a health check."""
        config = HealthCheckConfig(name="test1", check_func=lambda: True)
        health_registry.register(config)
        assert health_registry.unregister("test1") is True
        assert health_registry.get("test1") is None

    def test_unregister_nonexistent(self, health_registry):
        """Test unregistering non-existent check."""
        assert health_registry.unregister("nonexistent") is False

    def test_get_all(self, health_registry):
        """Test getting all checkers."""
        config1 = HealthCheckConfig(name="test1", check_func=lambda: True)
        config2 = HealthCheckConfig(name="test2", check_func=lambda: True)
        health_registry.register(config1)
        health_registry.register(config2)
        all_checkers = health_registry.get_all()
        assert len(all_checkers) == 2
        assert "test1" in all_checkers
        assert "test2" in all_checkers

    def test_get_critical(self, health_registry):
        """Test getting critical checkers."""
        config1 = HealthCheckConfig(
            name="critical1", check_func=lambda: True, critical=True
        )
        config2 = HealthCheckConfig(
            name="normal1", check_func=lambda: True, critical=False
        )
        health_registry.register(config1)
        health_registry.register(config2)
        critical = health_registry.get_critical()
        assert len(critical) == 1
        assert critical[0].name == "critical1"

    @pytest.mark.asyncio
    async def test_check_all(self, health_registry):
        """Test checking all registered checks."""
        config1 = HealthCheckConfig(name="test1", check_func=lambda: True)
        config2 = HealthCheckConfig(name="test2", check_func=lambda: False)
        health_registry.register(config1)
        health_registry.register(config2)
        results = await health_registry.check_all()
        assert len(results) == 2
        assert results["test1"].status == HealthStatus.HEALTHY
        assert results["test2"].status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_parallel(self, health_registry):
        """Test parallel checking."""
        config1 = HealthCheckConfig(name="test1", check_func=lambda: True)
        config2 = HealthCheckConfig(name="test2", check_func=lambda: True)
        health_registry.register(config1)
        health_registry.register(config2)
        results = await health_registry.check_parallel()
        assert len(results) == 2

    def test_get_overall_status_empty(self, health_registry):
        """Test overall status with no checks."""
        assert health_registry.get_overall_status() == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_overall_status_healthy(self, health_registry):
        """Test overall status when all healthy."""
        config = HealthCheckConfig(name="test1", check_func=lambda: True)
        checker = health_registry.register(config)
        await checker.check()
        assert health_registry.get_overall_status() == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_overall_status_critical_unhealthy(self, health_registry):
        """Test overall status when critical check fails."""
        config1 = HealthCheckConfig(
            name="critical1", check_func=lambda: False, critical=True
        )
        checker = health_registry.register(config1)
        await checker.check()
        assert health_registry.get_overall_status() == HealthStatus.UNHEALTHY

    def test_callback_registration(self, health_registry):
        """Test callback registration."""
        called = []

        def callback(name, result):
            called.append(name)

        health_registry.add_callback(callback)
        assert callback in health_registry._callbacks

    def test_to_dict(self, health_registry):
        """Test serializing registry to dict."""
        d = health_registry.to_dict()
        assert "overall_status" in d
        assert "checks" in d
        assert "timestamp" in d


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_registry_singleton(self):
        """Test that get_registry returns singleton."""
        reset_registry()
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_reset_registry(self):
        """Test resetting the global registry."""
        r1 = get_registry()
        reset_registry()
        r2 = get_registry()
        assert r1 is not r2
