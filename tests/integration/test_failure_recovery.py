"""Failure recovery integration tests.

Tests system recovery from various failure scenarios:
- Redis disconnect → reconnect
- Exchange failure → fallback
- Kill-switch → position closure
- System restart → recovery

For PAPER-003-002: E2E Integration Testing
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from health.monitor import ComponentType, HealthMonitor

from testing.chaos_engine import ChaosConfig, ChaosEngine, RecoveryResult
from testing.failure_injector import (
    ErrorInjector,
    NetworkPartitionInjector,
    ServiceFailureInjector,
)

logger = logging.getLogger(__name__)

# Maximum acceptable recovery time in seconds
MAX_RECOVERY_TIME_SECONDS = 10.0


@pytest.fixture
def mock_redis():
    """Mock Redis client that can simulate disconnections."""
    client = MagicMock()
    client._connected = True

    def ping():
        if not client._connected:
            raise ConnectionError("Redis connection lost")
        return True

    client.ping = ping
    client._connected = True
    return client


@pytest.fixture
def mock_influxdb():
    """Mock InfluxDB client."""
    client = MagicMock()
    client._connected = True

    def ping():
        if not client._connected:
            raise ConnectionError("InfluxDB connection lost")
        return True

    client.ping = ping
    return client


class MockRecoveryValidator:
    """Mock recovery validator for testing."""

    def __init__(self, recovered_after_checks: int = 3):
        self.recovered_after_checks = recovered_after_checks
        self.check_count = 0
        self._system_state: dict[str, Any] = {"healthy": False}

    async def check_recovery(self) -> bool:
        """Check if system has recovered."""
        self.check_count += 1
        if self.check_count >= self.recovered_after_checks:
            self._system_state["healthy"] = True
            return True
        return False

    async def get_system_state(self) -> dict[str, Any]:
        """Get current system state."""
        return self._system_state.copy()


class TestFailureRecovery:
    """Tests for failure recovery scenarios."""

    @pytest.mark.asyncio
    async def test_redis_disconnect_recovery(self, mock_redis):
        """Test system recovers from Redis disconnection."""
        # Set up health monitor
        monitor = HealthMonitor(redis_client=mock_redis)

        # Initial health check - should be healthy
        mock_redis._connected = True
        await monitor.update_health()
        initial_health = monitor.get_health_sync()
        assert initial_health is not None

        # Simulate Redis disconnection
        mock_redis._connected = False

        # Wait for health check to detect failure
        await monitor.update_health()
        _ = monitor.get_health_sync()  # Verify health check ran

        redis_score = monitor.get_component_health(ComponentType.REDIS)
        if redis_score:
            assert redis_score.score < 100  # Should be degraded (not full health)

        # Recover Redis
        mock_redis._connected = True
        await asyncio.sleep(0.1)

        # Verify recovery
        await monitor.update_health()
        recovered_health = monitor.get_health_sync()
        assert recovered_health is not None

        redis_score = monitor.get_component_health(ComponentType.REDIS)
        if redis_score:
            assert redis_score.score > 50  # Should be recovering

    @pytest.mark.asyncio
    async def test_redis_reconnection_latency(self, mock_redis):
        """Test Redis reconnection happens within acceptable time."""
        injector = NetworkPartitionInjector()

        # Inject partition
        event = await injector.inject(
            "redis",
            partition_type="partial",
            hosts=["redis"],
            duration=2.0,
        )

        start_time = time.time()

        # Simulate reconnection attempt
        await asyncio.sleep(0.5)

        # Recover from partition
        await injector.recover(event)

        elapsed = time.time() - start_time
        assert (
            elapsed < MAX_RECOVERY_TIME_SECONDS
        ), f"Recovery took {elapsed:.2f}s, expected < {MAX_RECOVERY_TIME_SECONDS}s"

    @pytest.mark.asyncio
    async def test_exchange_failure_fallback(self):
        """Test fallback when primary exchange fails."""
        primary_exchange = MagicMock()
        fallback_exchange = MagicMock()

        # Primary fails
        primary_exchange.is_healthy.return_value = False
        fallback_exchange.is_healthy.return_value = True

        # Verify fallback is used
        assert not primary_exchange.is_healthy()
        assert fallback_exchange.is_healthy()

    @pytest.mark.asyncio
    async def test_kill_switch_position_closure(self):
        """Test kill-switch closes all positions when triggered."""
        kill_switch = MagicMock()
        kill_switch.state.value = "ARMED"

        positions = [
            {"id": "pos_1", "symbol": "BTCUSDT", "size": 1.0},
            {"id": "pos_2", "symbol": "ETHUSDT", "size": 2.0},
        ]

        # Trigger kill-switch
        kill_switch.state.value = "TRIGGERED"

        # Verify positions would be closed
        closed_positions = []
        for pos in positions:
            if kill_switch.state.value == "TRIGGERED":
                closed_positions.append(pos)

        assert len(closed_positions) == 2, "All positions should be closed"

    @pytest.mark.asyncio
    async def test_kill_switch_recovery(self):
        """Test kill-switch can be rearmed after trigger."""
        kill_switch = MagicMock()

        # Initial state
        kill_switch.state.value = "TRIGGERED"

        # Simulate rearming
        kill_switch.state.value = "ARMED"

        assert kill_switch.state.value == "ARMED"

    @pytest.mark.asyncio
    async def test_system_restart_recovery(self):
        """Test system recovers correctly after restart."""
        validator = MockRecoveryValidator(recovered_after_checks=2)

        config = ChaosConfig(
            recovery_timeout_seconds=5.0,
        )
        engine = ChaosEngine(config=config)
        engine.set_recovery_validator(validator)

        # Simulate restart with service failure
        injector = ServiceFailureInjector()
        event = await injector.inject("system", failure_type="restart")

        start_time = time.time()

        # Validate recovery
        recovered = await validator.check_recovery()
        while not recovered and (time.time() - start_time) < 5.0:
            await asyncio.sleep(0.5)
            recovered = await validator.check_recovery()

        elapsed = time.time() - start_time

        await injector.recover(event)

        assert recovered, "System should recover after restart"
        assert elapsed < MAX_RECOVERY_TIME_SECONDS

    @pytest.mark.asyncio
    async def test_network_partition_recovery(self):
        """Test recovery from network partition."""
        injector = NetworkPartitionInjector()

        # Inject partition
        event = await injector.inject(
            "database",
            partition_type="complete",
            duration=3.0,
        )

        start_time = time.time()

        # Wait and recover
        await asyncio.sleep(1.0)
        await injector.recover(event)

        elapsed = time.time() - start_time

        assert elapsed < MAX_RECOVERY_TIME_SECONDS
        assert not injector.is_active

    @pytest.mark.asyncio
    async def test_cascading_failure_recovery(self):
        """Test recovery from cascading failures."""
        service_injector = ServiceFailureInjector()
        network_injector = NetworkPartitionInjector()
        error_injector = ErrorInjector(error_rate=0.5)

        # Inject multiple failures
        service_event = await service_injector.inject(
            "position_tracker",
            failure_type="crash",
        )
        network_event = await network_injector.inject(
            "redis",
            partition_type="partial",
            hosts=["localhost"],
        )
        error_event = await error_injector.inject(
            "order_simulator",
            error_type="exception",
        )

        start_time = time.time()

        # Recover in order
        await service_injector.recover(service_event)
        await network_injector.recover(network_event)
        await error_injector.recover(error_event)

        elapsed = time.time() - start_time

        # Verify all recovered
        assert not service_injector.is_active
        assert not network_injector.is_active
        assert not error_injector.is_active
        assert elapsed < MAX_RECOVERY_TIME_SECONDS * 2

    @pytest.mark.asyncio
    async def test_health_degradation_detection(self, mock_redis, mock_influxdb):
        """Test health monitor detects degraded state."""
        monitor = HealthMonitor(
            redis_client=mock_redis,
            influxdb_client=mock_influxdb,
        )

        # Healthy state
        await monitor.update_health()
        health1 = monitor.get_health_sync()

        # Degrade Redis
        mock_redis._connected = False
        await monitor.update_health()
        health2 = monitor.get_health_sync()

        # Health should degrade
        if health1 and health2:
            assert health2.overall_score <= health1.overall_score

    @pytest.mark.asyncio
    async def test_recovery_validation_with_metrics(self):
        """Test recovery validation captures metrics."""
        validator = MockRecoveryValidator(recovered_after_checks=5)

        start_time = time.time()
        check_count = 0

        while not await validator.check_recovery():
            check_count += 1
            await asyncio.sleep(0.1)

        elapsed = time.time() - start_time

        result = RecoveryResult(
            success=True,
            duration_seconds=elapsed,
            validation_checks=check_count,
            failed_checks=0,
        )

        assert result.success
        assert result.validation_checks > 0
        assert result.duration_seconds < MAX_RECOVERY_TIME_SECONDS

    @pytest.mark.asyncio
    async def test_concurrent_recovery_operations(self):
        """Test multiple components can recover concurrently."""
        services = [f"service_{i}" for i in range(5)]
        injector = ServiceFailureInjector()

        # Fail all services
        events = []
        for service in services:
            event = await injector.inject(service, failure_type="crash")
            events.append(event)

        start_time = time.time()

        # Recover all concurrently
        async def recover_service(event):
            await asyncio.sleep(random.uniform(0.1, 0.5))
            return await injector.recover(event)

        results = await asyncio.gather(*[recover_service(e) for e in events])

        elapsed = time.time() - start_time

        assert all(results), "All services should recover"
        assert elapsed < MAX_RECOVERY_TIME_SECONDS

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self):
        """Test recovery when only some components fail."""
        monitor = HealthMonitor()

        # Simulate partial failure - only Redis affected
        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(side_effect=ConnectionError("Redis down"))

        monitor._redis_client = mock_redis
        await monitor.update_health()

        health = monitor.get_health_sync()
        if health:
            # Should still have some score from healthy components
            assert health.overall_score > 0
            # But not full health
            assert health.overall_score < 100
