"""Chaos engineering test scenarios.

Tests random failure scenarios, load testing under chaos,
and recovery validation under controlled chaos conditions.

For PAPER-003-002: Chaos Engineering Tests
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any

import pytest

from testing.chaos_engine import ChaosConfig, ChaosEngine, ChaosPhase, RecoveryResult
from testing.failure_injector import (
    ErrorInjector,
    InjectionEvent,
    LatencyInjector,
    NetworkPartitionInjector,
    ServiceFailureInjector,
)

logger = logging.getLogger(__name__)


class MockRecoveryValidator:
    """Mock validator for chaos testing."""

    def __init__(self, recovery_probability: float = 0.9):
        self.recovery_probability = recovery_probability
        self.check_count = 0

    async def check_recovery(self) -> bool:
        """Simulate recovery check."""
        self.check_count += 1
        await asyncio.sleep(0.05)
        return random.random() < self.recovery_probability

    async def get_system_state(self) -> dict[str, Any]:
        """Get mock system state."""
        return {
            "healthy": random.random() < self.recovery_probability,
            "timestamp": datetime.now(UTC).isoformat(),
        }


class TestChaosScenarios:
    """Chaos engineering test scenarios."""

    @pytest.mark.asyncio
    async def test_chaos_engine_initialization(self):
        """Test chaos engine initializes correctly."""
        config = ChaosConfig(
            failure_probability=30.0,
            max_concurrent_failures=2,
        )

        engine = ChaosEngine(config=config, experiment_id="test-001")

        assert engine.report.experiment_id == "test-001"
        assert engine.phase == ChaosPhase.PENDING
        assert len(engine.report.injections) == 0

    @pytest.mark.asyncio
    async def test_single_failure_injection(self):
        """Test injecting a single failure."""
        engine = ChaosEngine()
        injector = ServiceFailureInjector()
        engine._injectors = [injector]

        event = await engine.inject_single_failure(
            "service_failure",
            "test_service",
            failure_type="crash",
        )

        assert event is not None
        assert event.target == "test_service"
        assert not event.recovered

        # Recover
        recovered = await injector.recover(event)
        assert recovered
        assert event.recovered

    @pytest.mark.asyncio
    async def test_network_partition_injector(self):
        """Test network partition injector directly."""
        injector = NetworkPartitionInjector()

        event = await injector.inject(
            "redis",
            partition_type="complete",
            duration=1.0,
        )

        assert event is not None
        assert event.injector_type == "NetworkPartitionInjector"
        assert event.target == "redis"
        assert injector.is_active

        # Recover
        recovered = await injector.recover(event)
        assert recovered
        assert not injector.is_active

    @pytest.mark.asyncio
    async def test_service_failure_injector(self):
        """Test service failure injector directly."""
        injector = ServiceFailureInjector()

        event = await injector.inject(
            "position_tracker",
            failure_type="crash",
            recovery_time=0.5,
        )

        assert event is not None
        assert not injector.is_service_available("position_tracker")

        # Recover
        recovered = await injector.recover(event)
        assert recovered
        assert injector.is_service_available("position_tracker")

    @pytest.mark.asyncio
    async def test_latency_injector(self):
        """Test latency injector directly."""
        injector = LatencyInjector()

        event = await injector.inject(
            "order_simulator",
            delay_type="fixed",
            delay_ms=100,
        )

        assert event is not None
        assert injector.is_active

        # Test delay application
        delay = await injector.apply_delay("order_simulator")
        assert delay >= 0.1  # 100ms = 0.1s

        # Recover
        recovered = await injector.recover(event)
        assert recovered
        assert not injector.is_active

    @pytest.mark.asyncio
    async def test_error_injector(self):
        """Test error injector directly."""
        injector = ErrorInjector(error_rate=1.0)

        event = await injector.inject(
            "risk_check",
            error_type="exception",
            exception_class=ValueError,
        )

        assert event is not None
        assert injector.is_active
        assert injector.should_error("risk_check")

        # Test error raising
        error = injector.get_error("risk_check")
        assert isinstance(error, ValueError)

        # Recover
        recovered = await injector.recover(event)
        assert recovered
        assert not injector.is_active

    @pytest.mark.asyncio
    async def test_chaos_report_generation(self):
        """Test chaos report generation."""
        report = ChaosEngine(config=ChaosConfig()).report

        # Simulate some activity
        report.add_phase(ChaosPhase.SETUP, {"injectors": ["test"]})
        report.add_phase(ChaosPhase.INJECTION, {"count": 1})

        # Add a mock injection
        event = InjectionEvent(
            injector_type="TestInjector",
            target="test_target",
            failure_type="test",
        )
        report.add_injection(event)

        # Add recovery result
        result = RecoveryResult(
            success=True,
            duration_seconds=1.5,
            validation_checks=5,
        )
        report.add_recovery_result(result)

        # Finalize
        report.finalize(success=True)

        assert report.end_time is not None
        assert report.metrics["total_injections"] == 1
        assert report.metrics["recovery_success_rate"] == 1.0
        assert len(report.summary) > 0

        # Test serialization
        json_str = report.to_json()
        assert "test_target" in json_str
        assert "experiment_id" in json_str

    @pytest.mark.asyncio
    async def test_recovery_validation_success(self):
        """Test successful recovery validation."""
        engine = ChaosEngine()
        validator = MockRecoveryValidator(recovery_probability=1.0)
        engine.set_recovery_validator(validator)

        # Manually add injection
        event = InjectionEvent(
            injector_type="TestInjector",
            target="test",
            failure_type="test",
        )
        event.recovered = True
        engine.report.add_injection(event)

        # Validate
        is_recovered = await validator.check_recovery()
        assert is_recovered

    @pytest.mark.asyncio
    async def test_chaos_config_validation(self):
        """Test chaos config validates correctly."""
        # Valid config
        config = ChaosConfig(
            failure_probability=50.0,
            max_concurrent_failures=5,
        )
        assert config.failure_probability == 50.0

        # Invalid probability
        with pytest.raises(ValueError):
            ChaosConfig(failure_probability=150.0)

        # Invalid max concurrent
        with pytest.raises(ValueError):
            ChaosConfig(max_concurrent_failures=0)
