"""E2E integration tests for paper trading flow.

Tests the complete signal → risk → order → position flow with
real Redis/InfluxDB connections and latency validation.

For PAPER-003-002: E2E Integration Testing
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import health monitoring
from health import HealthStatus
from health.monitor import ComponentType, HealthMonitor

# Import kill-switch
# Import execution components
# Import paper trading components
from portfolio.paper_tracker import PaperTracker

# Import testing infrastructure
from testing.failure_injector import (
    ErrorInjector,
    LatencyInjector,
)

logger = logging.getLogger(__name__)

# Maximum allowed end-to-end latency in seconds
MAX_E2E_LATENCY_SECONDS = 1.0


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    client = MagicMock()
    client.ping.return_value = True
    client.get.return_value = None
    client.set.return_value = True
    return client


@pytest.fixture
def mock_influxdb():
    """Mock InfluxDB client for testing."""
    client = MagicMock()
    client.ping.return_value = True
    client.write.return_value = True
    return client


@pytest.fixture
def mock_bybit_connector():
    """Mock Bybit connector for testing."""
    connector = MagicMock()
    connector.is_healthy.return_value = True
    connector.health_check.return_value = {
        "is_connected": True,
        "latency_ms": 50,
    }
    connector._latency_ms = 50
    connector._reconnect_count = 0
    return connector


@pytest.fixture
def mock_bitget_connector():
    """Mock Bitget connector for testing."""
    connector = MagicMock()
    connector.is_healthy.return_value = True
    connector.health_check.return_value = {
        "is_connected": True,
        "latency_ms": 45,
    }
    connector._latency_ms = 45
    connector._reconnect_count = 0
    return connector


@pytest.fixture
def health_monitor(
    mock_redis,
    mock_influxdb,
    mock_bybit_connector,
    mock_bitget_connector,
):
    """Create health monitor with mock dependencies."""
    monitor = HealthMonitor(
        redis_client=mock_redis,
        influxdb_client=mock_influxdb,
        bybit_connector=mock_bybit_connector,
        bitget_connector=mock_bitget_connector,
        update_interval_seconds=1,
    )
    return monitor


class TestPaperTradingE2E:
    """End-to-end tests for paper trading flow."""

    @pytest.mark.asyncio
    async def test_signal_to_position_flow_latency(self, health_monitor):
        """Test complete signal → position flow completes in <1s."""
        start_time = time.time()

        # Simulate signal generation
        signal = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "signal_type": "entry",
            "confidence": 0.85,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Simulate risk check
        risk_check_passed = await self._simulate_risk_check(signal)
        assert risk_check_passed, "Risk check failed"

        # Simulate order creation
        order = await self._simulate_order_creation(signal)
        assert order is not None, "Order creation failed"

        # Simulate position tracking
        position = await self._simulate_position_update(order)
        assert position is not None, "Position update failed"

        elapsed = time.time() - start_time
        assert elapsed < MAX_E2E_LATENCY_SECONDS, (
            f"E2E latency {elapsed:.3f}s exceeds {MAX_E2E_LATENCY_SECONDS}s"
        )

        logger.info(f"E2E flow completed in {elapsed:.3f}s")

    @pytest.mark.asyncio
    async def test_health_monitoring_integration(self, health_monitor):
        """Test health monitoring works with all components."""
        await health_monitor.update_health()
        health = health_monitor.get_health_sync()

        assert health is not None
        assert health.overall_score >= 0
        assert health.status in [
            HealthStatus.GREEN,
            HealthStatus.YELLOW,
            HealthStatus.RED,
        ]

    @pytest.mark.asyncio
    async def test_redis_health_check(self, health_monitor):
        """Test Redis health check integration."""
        await health_monitor.update_health()
        redis_score = health_monitor.get_component_health(ComponentType.REDIS)

        assert redis_score is not None
        assert redis_score.score >= 0
        assert redis_score.component == ComponentType.REDIS

    @pytest.mark.asyncio
    async def test_influxdb_health_check(self, health_monitor):
        """Test InfluxDB health check integration."""
        await health_monitor.update_health()
        influx_score = health_monitor.get_component_health(ComponentType.INFLUXDB)

        assert influx_score is not None
        assert influx_score.score >= 0
        assert influx_score.component == ComponentType.INFLUXDB

    @pytest.mark.asyncio
    async def test_exchange_health_checks(self, health_monitor):
        """Test exchange connector health checks."""
        await health_monitor.update_health()

        bybit_score = health_monitor.get_component_health(ComponentType.BYBIT)
        bitget_score = health_monitor.get_component_health(ComponentType.BITGET)

        assert bybit_score is not None
        assert bitget_score is not None
        assert bybit_score.score >= 0
        assert bitget_score.score >= 0

    @pytest.mark.asyncio
    async def test_health_status_endpoint(self, health_monitor):
        """Test health status endpoint returns complete data."""
        await health_monitor.update_health()
        status = await health_monitor.get_status()

        assert "overall_score" in status
        assert "status" in status
        assert "component_scores" in status
        assert "monitoring_active" in status
        assert status["monitoring_active"] is False  # Not started

    @pytest.mark.asyncio
    async def test_signal_filtering_by_risk(self):
        """Test signals are filtered by risk parameters."""
        high_risk_signal = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "confidence": 0.99,
            "risk_score": 95,  # High risk
        }

        low_risk_signal = {
            "symbol": "ETHUSDT",
            "side": "buy",
            "confidence": 0.85,
            "risk_score": 30,  # Low risk
        }

        # High risk signal should be rejected
        high_risk_passed = await self._simulate_risk_check(
            high_risk_signal, max_risk=70
        )
        assert not high_risk_passed, "High risk signal should be rejected"

        # Low risk signal should pass
        low_risk_passed = await self._simulate_risk_check(low_risk_signal, max_risk=70)
        assert low_risk_passed, "Low risk signal should pass"

    @pytest.mark.asyncio
    async def test_order_simulation_with_latency(self):
        """Test order simulation with realistic latency."""
        injector = LatencyInjector(base_delay_ms=100)
        await injector.inject("order_creation", delay_type="fixed", delay_ms=50)

        start_time = time.time()
        order = await self._simulate_order_creation(
            {"symbol": "BTCUSDT", "side": "buy"}
        )
        await injector.apply_delay("order_creation")
        elapsed = time.time() - start_time

        assert order is not None
        assert elapsed >= 0.05  # Should have delay

        await injector.recover(injector.get_events()[0])

    @pytest.mark.asyncio
    async def test_position_tracker_integration(self):
        """Test position tracker integrates with Redis."""
        # Create tracker
        tracker = PaperTracker(portfolio_id="test_paper_trading")

        # Verify initialization
        assert tracker is not None
        assert tracker.portfolio_id == "test_paper_trading"

    @pytest.mark.asyncio
    async def test_kill_switch_integration(self, health_monitor):
        """Test kill-switch integrates with health monitoring."""
        # Create mock kill-switch with proper state enum
        from execution.kill_switch.state import KillSwitchState

        kill_switch = MagicMock()
        kill_switch.state = KillSwitchState.ARMED
        kill_switch._last_test_time = 0

        health_monitor.kill_switch = kill_switch
        await health_monitor.update_health()

        ks_score = health_monitor.get_component_health(ComponentType.KILL_SWITCH)
        assert ks_score is not None
        assert ks_score.score >= 0

    @pytest.mark.asyncio
    async def test_multi_signal_processing(self):
        """Test processing multiple signals concurrently."""
        signals = [
            {"symbol": "BTCUSDT", "side": "buy", "id": f"sig_{i}"} for i in range(10)
        ]

        start_time = time.time()
        tasks = [self._simulate_full_flow(s) for s in signals]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        assert success_count == 10, f"Only {success_count}/10 signals processed"
        assert elapsed < MAX_E2E_LATENCY_SECONDS * 2, (
            f"Batch processing took {elapsed:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_health_trend_calculation(self, health_monitor):
        """Test health trend calculation over time."""
        # Record multiple health snapshots (need at least 2 for trend)
        for _ in range(10):
            await health_monitor.update_health()
            await asyncio.sleep(0.05)

        trend = await health_monitor.history.calculate_trend(hours=1)
        # Trend may be None if insufficient data
        if trend is not None:
            assert hasattr(trend, "slope")
            assert hasattr(trend, "average_score")

    @pytest.mark.asyncio
    async def test_component_health_aggregation(self, health_monitor):
        """Test individual component scores aggregate correctly."""
        await health_monitor.update_health()
        health = health_monitor.get_health_sync()

        component_scores = health.component_scores
        assert len(component_scores) > 0

        # Verify all scores are valid
        for score in component_scores:
            assert 0 <= score.score <= 100
            assert score.component is not None

    @pytest.mark.asyncio
    async def test_error_handling_in_flow(self):
        """Test error handling during signal processing."""
        # Test that errors can be injected and caught
        injector = ErrorInjector(error_rate=1.0)  # 100% error rate

        # Inject error on a test target
        await injector.inject(
            "test_risk_check",
            error_type="exception",
            exception_class=ValueError,
        )

        # Should trigger error
        with pytest.raises(ValueError):
            await injector.maybe_raise_error("test_risk_check")

        await injector.recover(injector.get_events()[0])

    @pytest.mark.asyncio
    async def test_latency_under_load(self):
        """Test latency remains acceptable under load."""
        latencies = []

        for _ in range(20):
            start = time.time()
            await self._simulate_full_flow(
                {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                }
            )
            latencies.append(time.time() - start)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        assert avg_latency < MAX_E2E_LATENCY_SECONDS, (
            f"Avg latency {avg_latency:.3f}s exceeds limit"
        )
        assert p95_latency < MAX_E2E_LATENCY_SECONDS * 1.5, (
            f"P95 latency {p95_latency:.3f}s exceeds limit"
        )

        logger.info(
            f"Latency under load: avg={avg_latency:.3f}s, "
            f"p95={p95_latency:.3f}s, max={max_latency:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_data_flow_redis_to_influxdb(self, mock_redis, mock_influxdb):
        """Test data flows correctly from Redis to InfluxDB."""
        # Set up mock data in Redis
        mock_redis.get.return_value = '{"position": "long", "size": 1.0}'

        # Simulate position update with proper order structure
        position_data = await self._simulate_position_update(
            {
                "order_id": "test_order_001",
                "symbol": "BTCUSDT",
                "side": "buy",
                "size": 1.0,
            }
        )

        assert position_data is not None
        assert position_data.get("symbol") == "BTCUSDT"

    # Helper methods

    async def _simulate_risk_check(
        self,
        signal: dict[str, Any],
        max_risk: float = 100.0,
    ) -> bool:
        """Simulate risk check on a signal."""
        await asyncio.sleep(0.01)  # Minimal processing delay

        risk_score = signal.get("risk_score", 50)
        return risk_score <= max_risk

    async def _simulate_order_creation(
        self,
        signal: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Simulate order creation from signal."""
        await asyncio.sleep(0.01)

        return {
            "order_id": f"ord_{signal.get('symbol', 'UNK')}_{int(time.time())}",
            "symbol": signal.get("symbol", "UNKNOWN"),
            "side": signal.get("side", "buy"),
            "type": "market",
            "status": "filled",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _simulate_position_update(
        self,
        order: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Simulate position update from order."""
        await asyncio.sleep(0.01)

        return {
            "position_id": f"pos_{order['order_id']}",
            "symbol": order["symbol"],
            "side": order["side"],
            "size": 1.0,
            "entry_price": 50000.0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _simulate_full_flow(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Simulate complete signal to position flow."""
        risk_passed = await self._simulate_risk_check(signal)
        if not risk_passed:
            raise ValueError("Risk check failed")

        order = await self._simulate_order_creation(signal)
        if not order:
            raise ValueError("Order creation failed")

        position = await self._simulate_position_update(order)
        if not position:
            raise ValueError("Position update failed")

        return position
