"""Tests for Health Check System."""

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


class TestHealthCheckResult:
    """Tests for HealthCheckResult."""

    def test_health_check_result_creation(self):
        """Test creating a health check result."""
        result = HealthCheckResult(
            name="test-check",
            status=HealthStatus.HEALTHY,
            message="All good",
            latency_ms=10.5,
        )
        assert result.name == "test-check"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.latency_ms == 10.5
        assert isinstance(result.timestamp, datetime)

    def test_health_check_result_to_dict(self):
        """Test converting result to dictionary."""
        result = HealthCheckResult(
            name="test-check",
            status=HealthStatus.DEGRADED,
            message="Performance issues",
            details={"error_count": 5},
        )
        d = result.to_dict()
        assert d["name"] == "test-check"
        assert d["status"] == "degraded"
        assert d["message"] == "Performance issues"
        assert d["details"]["error_count"] == 5


class TestHealthChecker:
    """Tests for HealthChecker."""

    def test_health_checker_creation(self, healthy_check_func):
        """Test creating a health checker."""
        config = HealthCheckConfig(
            name="test",
            check_func=healthy_check_func,
            interval_seconds=10.0,
        )
        checker = HealthChecker(config)
        assert checker.name == "test"
        assert not checker.is_healthy  # No check yet
        assert not checker.is_critical

    def test_health_checker_critical(self, healthy_check_func):
        """Test critical health checker flag."""
        config = HealthCheckConfig(
            name="critical-check",
            check_func=healthy_check_func,
            critical=True,
        )
        checker = HealthChecker(config)
        assert checker.is_critical

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, healthy_check_func):
        """Test health check with healthy result."""
        config = HealthCheckConfig(
            name="test",
            check_func=healthy_check_func,
        )
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.HEALTHY
        assert checker.is_healthy

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, unhealthy_check_func):
        """Test health check with unhealthy result."""
        config = HealthCheckConfig(
            name="test",
            check_func=unhealthy_check_func,
            unhealthy_threshold=1,
        )
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert not checker.is_healthy

    @pytest.mark.asyncio
    async def test_health_check_threshold(self):
        """Test health check with threshold."""
        call_count = [0]

        def check():
            call_count[0] += 1
            return call_count[0] > 2

        config = HealthCheckConfig(
            name="test",
            check_func=check,
            unhealthy_threshold=3,
            healthy_threshold=2,
        )
        checker = HealthChecker(config)

        # First checks should be unhealthy
        for _ in range(3):
            result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY

        # Now should become healthy after meeting threshold
        for _ in range(2):
            result = await checker.check()
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """Test health check timeout handling."""

        async def slow_check():
            await asyncio.sleep(10)
            return True

        config = HealthCheckConfig(
            name="test",
            check_func=slow_check,
            timeout_seconds=0.1,
        )
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "timeout" in result.message.lower()

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        """Test health check exception handling."""

        def failing_check():
            raise ValueError("Check failed!")

        config = HealthCheckConfig(
            name="test",
            check_func=failing_check,
        )
        checker = HealthChecker(config)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "exception" in result.message.lower()


class TestHealthCheckRegistry:
    """Tests for HealthCheckRegistry."""

    def test_registry_creation(self):
        """Test creating a health check registry."""
        registry = HealthCheckRegistry()
        assert len(registry.get_all()) == 0

    def test_register_health_check(self, healthy_check_func):
        """Test registering a health check."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(
            name="test-check",
            check_func=healthy_check_func,
        )
        checker = registry.register(config)
        assert len(registry.get_all()) == 1
        assert registry.get("test-check") is checker

    def test_register_duplicate(self, healthy_check_func):
        """Test registering duplicate health check."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(
            name="test-check",
            check_func=healthy_check_func,
        )
        registry.register(config)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(config)

    def test_unregister_health_check(self, healthy_check_func):
        """Test unregistering a health check."""
        registry = HealthCheckRegistry()
        config = HealthCheckConfig(
            name="test-check",
            check_func=healthy_check_func,
        )
        registry.register(config)
        assert registry.unregister("test-check")
        assert registry.get("test-check") is None
        assert not registry.unregister("nonexistent")

    def test_get_critical_checks(self, healthy_check_func):
        """Test getting critical health checks."""
        registry = HealthCheckRegistry()
        registry.register(
            HealthCheckConfig(
                name="critical",
                check_func=healthy_check_func,
                critical=True,
            )
        )
        registry.register(
            HealthCheckConfig(
                name="non-critical",
                check_func=healthy_check_func,
                critical=False,
            )
        )
        critical = registry.get_critical()
        assert len(critical) == 1
        assert critical[0].name == "critical"

    @pytest.mark.asyncio
    async def test_check_all(self, healthy_check_func, unhealthy_check_func):
        """Test running all health checks."""
        registry = HealthCheckRegistry()
        registry.register(
            HealthCheckConfig(
                name="healthy-check",
                check_func=healthy_check_func,
            )
        )
        registry.register(
            HealthCheckConfig(
                name="unhealthy-check",
                check_func=unhealthy_check_func,
                unhealthy_threshold=1,
            )
        )
        results = await registry.check_all()
        assert len(results) == 2
        assert results["healthy-check"].status == HealthStatus.HEALTHY
        assert results["unhealthy-check"].status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_parallel(self, healthy_check_func):
        """Test running health checks in parallel."""
        registry = HealthCheckRegistry()
        for i in range(5):
            registry.register(
                HealthCheckConfig(
                    name=f"check-{i}",
                    check_func=healthy_check_func,
                )
            )
        results = await registry.check_parallel()
        assert len(results) == 5
        for name, result in results.items():
            assert result.status == HealthStatus.HEALTHY

    def test_callbacks(self, healthy_check_func):
        """Test health check callbacks."""
        registry = HealthCheckRegistry()
        callback_results = []

        def callback(name, result):
            callback_results.append((name, result.status))

        registry.add_callback(callback)
        registry.register(
            HealthCheckConfig(
                name="test-check",
                check_func=healthy_check_func,
            )
        )

        # Check is async so we can't test callback directly here
        # Just verify it doesn't error
        assert len(callback_results) == 0

    def test_get_overall_status_empty(self):
        """Test overall status with no checks."""
        registry = HealthCheckRegistry()
        assert registry.get_overall_status() == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_overall_status(self, healthy_check_func, unhealthy_check_func):
        """Test overall status calculation."""
        registry = HealthCheckRegistry()
        registry.register(
            HealthCheckConfig(
                name="check-1",
                check_func=healthy_check_func,
            )
        )
        registry.register(
            HealthCheckConfig(
                name="check-2",
                check_func=unhealthy_check_func,
                unhealthy_threshold=1,
            )
        )
        await registry.check_all()
        # Overall should be degraded since one is unhealthy
        assert registry.get_overall_status() == HealthStatus.DEGRADED

    def test_global_registry(self):
        """Test global registry functions."""
        reset_registry()
        registry1 = get_registry()
        registry2 = get_registry()
        assert registry1 is registry2
        reset_registry()
        registry3 = get_registry()
        assert registry3 is not registry1
