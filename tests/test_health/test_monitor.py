"""Additional tests for health monitor module.

For PAPER-003-001: Unified Health Monitoring System
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import Mock, AsyncMock, MagicMock
import asyncio

from src.health.monitor import HealthMonitor
from src.health import ComponentType, HealthStatus
from src.health.score_calculator import HealthScore, ComponentScore


class TestHealthMonitorExtended:
    """Extended tests for HealthMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create a health monitor instance."""
        return HealthMonitor()

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator."""
        mock = Mock()
        mock.running = True
        mock._last_latency_ms = 500
        mock._error_rate = 0.5
        mock._last_success_time = 30
        return mock

    @pytest.fixture
    def mock_position_tracker(self):
        """Create a mock position tracker."""
        mock = Mock()
        mock._positions = {"pos1": {}, "pos2": {}}
        redis_health = Mock()
        redis_health.error_rate = 1.0
        redis_health.circuit_breaker_open = False
        mock._redis_health = redis_health
        return mock

    @pytest.fixture
    def mock_order_simulator(self):
        """Create a mock order simulator."""
        mock = Mock()
        mock._orders = {"order1": {}, "order2": {}}
        return mock

    @pytest.fixture
    def mock_bybit_connector(self):
        """Create a mock Bybit connector."""
        mock = Mock()
        mock.is_healthy.return_value = True
        mock._latency_ms = 100
        mock._reconnect_count = 1
        # health_check returns a dict or None to avoid update() errors
        mock.health_check.return_value = {}
        return mock

    @pytest.fixture
    def mock_bitget_connector(self):
        """Create a mock Bitget connector."""
        mock = Mock()
        mock.is_healthy.return_value = True
        mock._latency_ms = 120
        mock._reconnect_count = 0
        # health_check returns a dict or None to avoid update() errors
        mock.health_check.return_value = {}
        return mock

    @pytest.fixture
    def mock_kill_switch(self):
        """Create a mock kill switch."""
        mock = Mock()
        mock.state = Mock()
        mock.state.value = "ARMED"
        mock._last_test_time = 0
        return mock

    def test_monitor_with_components(
        self,
        mock_orchestrator,
        mock_position_tracker,
        mock_order_simulator,
        mock_bybit_connector,
        mock_bitget_connector,
        mock_kill_switch,
    ):
        """Test monitor initialization with all components."""
        monitor = HealthMonitor(
            orchestrator=mock_orchestrator,
            position_tracker=mock_position_tracker,
            order_simulator=mock_order_simulator,
            bybit_connector=mock_bybit_connector,
            bitget_connector=mock_bitget_connector,
            kill_switch=mock_kill_switch,
        )

        assert monitor.orchestrator == mock_orchestrator
        assert monitor.position_tracker == mock_position_tracker
        assert monitor.order_simulator == mock_order_simulator
        assert monitor.bybit_connector == mock_bybit_connector
        assert monitor.bitget_connector == mock_bitget_connector
        assert monitor.kill_switch == mock_kill_switch

    @pytest.mark.asyncio
    async def test_start_idempotent(self, monitor):
        """Test that start is idempotent."""
        await monitor.start()
        assert monitor._running

        # Try to start again
        await monitor.start()
        assert monitor._running  # Should still be running

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, monitor):
        """Test stopping when not running."""
        # Should not raise
        await monitor.stop()
        assert not monitor._running

    def test_check_orchestrator_health_running(self, mock_orchestrator):
        """Test orchestrator health when running."""
        monitor = HealthMonitor(orchestrator=mock_orchestrator)
        score = monitor._check_orchestrator_health()

        assert score.component == ComponentType.ORCHESTRATOR
        assert score.score > 0
        assert "is_running" in score.details

    def test_check_orchestrator_health_none(self):
        """Test orchestrator health when None."""
        monitor = HealthMonitor(orchestrator=None)
        score = monitor._check_orchestrator_health()

        assert score.component == ComponentType.ORCHESTRATOR
        assert not score.details["is_running"]

    def test_check_position_tracker_with_redis_health(self, mock_position_tracker):
        """Test position tracker with Redis health."""
        monitor = HealthMonitor(position_tracker=mock_position_tracker)
        score = monitor._check_position_tracker_health()

        assert score.component == ComponentType.POSITION_TRACKER
        assert score.score > 0

    def test_check_position_tracker_none(self):
        """Test position tracker when None."""
        monitor = HealthMonitor(position_tracker=None)
        score = monitor._check_position_tracker_health()

        assert score.component == ComponentType.POSITION_TRACKER
        assert not score.details["is_running"]

    def test_check_order_simulator_with_orders(self, mock_order_simulator):
        """Test order simulator with orders."""
        monitor = HealthMonitor(order_simulator=mock_order_simulator)
        score = monitor._check_order_simulator_health()

        assert score.component == ComponentType.ORDER_SIMULATOR
        assert score.details["order_count"] == 2

    def test_check_order_simulator_none(self):
        """Test order simulator when None."""
        monitor = HealthMonitor(order_simulator=None)
        score = monitor._check_order_simulator_health()

        assert score.component == ComponentType.ORDER_SIMULATOR
        assert not score.details["is_running"]

    def test_check_redis_health_connected(self):
        """Test Redis health when connected."""
        mock_redis = Mock()
        mock_redis.ping.return_value = True

        monitor = HealthMonitor(redis_client=mock_redis)
        score = monitor._check_redis_health()

        assert score.component == ComponentType.REDIS
        mock_redis.ping.assert_called_once()

    def test_check_redis_health_exception(self):
        """Test Redis health when exception occurs."""
        mock_redis = Mock()
        mock_redis.ping.side_effect = Exception("Connection refused")

        monitor = HealthMonitor(redis_client=mock_redis)
        score = monitor._check_redis_health()

        assert score.component == ComponentType.REDIS
        assert not score.details["is_connected"]
        assert "error" in score.details

    def test_check_redis_health_none(self):
        """Test Redis health when None."""
        monitor = HealthMonitor(redis_client=None)
        score = monitor._check_redis_health()

        assert score.component == ComponentType.REDIS
        assert not score.details["is_connected"]

    def test_check_influxdb_health_connected(self):
        """Test InfluxDB health when connected."""
        mock_influx = Mock()
        mock_influx.ping.return_value = True

        monitor = HealthMonitor(influxdb_client=mock_influx)
        score = monitor._check_influxdb_health()

        assert score.component == ComponentType.INFLUXDB

    def test_check_influxdb_health_exception(self):
        """Test InfluxDB health when exception occurs."""
        mock_influx = Mock()
        mock_influx.ping.side_effect = Exception("Connection refused")

        monitor = HealthMonitor(influxdb_client=mock_influx)
        score = monitor._check_influxdb_health()

        assert score.component == ComponentType.INFLUXDB
        assert "error" in score.details

    def test_check_postgresql_health_connected(self):
        """Test PostgreSQL health when connected."""
        mock_pg = Mock()
        mock_pg.execute = Mock()  # Has execute method

        monitor = HealthMonitor(postgres_client=mock_pg)
        score = monitor._check_postgresql_health()

        assert score.component == ComponentType.POSTGRESQL

    def test_check_bybit_health_healthy(self, mock_bybit_connector):
        """Test Bybit health when healthy."""
        monitor = HealthMonitor(bybit_connector=mock_bybit_connector)
        score = monitor._check_bybit_health()

        assert score.component == ComponentType.BYBIT
        # The is_connected should be set from is_healthy() return value
        assert score.details.get("is_connected") is True
        mock_bybit_connector.is_healthy.assert_called_once()

    def test_check_bybit_health_exception(self, mock_bybit_connector):
        """Test Bybit health when exception occurs."""
        mock_bybit_connector.is_healthy.side_effect = Exception("Error")

        monitor = HealthMonitor(bybit_connector=mock_bybit_connector)
        score = monitor._check_bybit_health()

        assert score.component == ComponentType.BYBIT
        assert not score.details["is_connected"]

    def test_check_bybit_health_none(self):
        """Test Bybit health when None."""
        monitor = HealthMonitor(bybit_connector=None)
        score = monitor._check_bybit_health()

        assert score.component == ComponentType.BYBIT
        assert not score.details["is_connected"]

    def test_check_bitget_health_healthy(self, mock_bitget_connector):
        """Test Bitget health when healthy."""
        monitor = HealthMonitor(bitget_connector=mock_bitget_connector)
        score = monitor._check_bitget_health()

        assert score.component == ComponentType.BITGET
        assert score.details["is_connected"]

    def test_check_bitget_health_exception(self, mock_bitget_connector):
        """Test Bitget health when exception occurs."""
        mock_bitget_connector.is_healthy.side_effect = Exception("Error")

        monitor = HealthMonitor(bitget_connector=mock_bitget_connector)
        score = monitor._check_bitget_health()

        assert score.component == ComponentType.BITGET
        assert not score.details["is_connected"]

    def test_check_kill_switch_health_armed(self, mock_kill_switch):
        """Test kill-switch health when armed."""
        monitor = HealthMonitor(kill_switch=mock_kill_switch)
        score = monitor._check_kill_switch_health()

        assert score.component == ComponentType.KILL_SWITCH
        assert score.details["state"] == "ARMED"
        assert score.details["is_armed"]

    def test_check_kill_switch_health_none(self):
        """Test kill-switch health when None."""
        monitor = HealthMonitor(kill_switch=None)
        score = monitor._check_kill_switch_health()

        assert score.component == ComponentType.KILL_SWITCH
        assert score.details["state"] == "NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_get_health_with_update(self, monitor):
        """Test get_health triggers update when stale."""
        # First update
        await monitor.update_health()
        initial_time = monitor._last_update

        # Wait a bit (but not enough to trigger update)
        # Since update_interval is 30s, this should not trigger update
        health = await monitor.get_health()
        assert health is not None

    @pytest.mark.asyncio
    async def test_get_status(self, monitor):
        """Test getting full status."""
        await monitor.update_health()
        status = await monitor.get_status()

        assert "overall_score" in status
        assert "status" in status
        assert "component_scores" in status
        assert "trend" in status
        assert "recent_alerts" in status
        assert "monitoring_active" in status

    def test_is_healthy_with_score(self, monitor):
        """Test is_healthy with valid score."""
        # Manually set a good score
        from src.health.score_calculator import HealthScore

        monitor._current_score = HealthScore(
            overall_score=85.0,
            component_scores=[],
        )

        assert monitor.is_healthy()  # YELLOW is healthy

    def test_is_healthy_critical(self, monitor):
        """Test is_healthy when critical."""
        monitor._current_score = HealthScore(
            overall_score=50.0,
            component_scores=[],
        )

        assert not monitor.is_healthy()

    def test_is_healthy_no_score(self, monitor):
        """Test is_healthy when no score."""
        monitor._current_score = None
        assert not monitor.is_healthy()

    def test_is_critical_with_score(self, monitor):
        """Test is_critical with RED score."""
        monitor._current_score = HealthScore(
            overall_score=50.0,
            component_scores=[],
        )

        assert monitor.is_critical()

    def test_is_critical_not_critical(self, monitor):
        """Test is_critical when not critical."""
        monitor._current_score = HealthScore(
            overall_score=85.0,
            component_scores=[],
        )

        assert not monitor.is_critical()

    def test_is_critical_no_score(self, monitor):
        """Test is_critical when no score."""
        monitor._current_score = None
        assert monitor.is_critical()

    def test_get_component_health_found(self, monitor):
        """Test get_component_health when found."""
        redis_score = ComponentScore(ComponentType.REDIS, 90.0, 0.1)
        monitor._current_score = HealthScore(
            overall_score=85.0,
            component_scores=[redis_score],
        )

        found = monitor.get_component_health(ComponentType.REDIS)
        assert found is not None
        assert found.score == 90.0

    def test_get_component_health_not_found(self, monitor):
        """Test get_component_health when not found."""
        monitor._current_score = HealthScore(
            overall_score=85.0,
            component_scores=[],
        )

        found = monitor.get_component_health(ComponentType.REDIS)
        assert found is None

    def test_get_component_health_no_score(self, monitor):
        """Test get_component_health when no score."""
        monitor._current_score = None
        found = monitor.get_component_health(ComponentType.REDIS)
        assert found is None

    @pytest.mark.asyncio
    async def test_record_alert_integration(self, monitor):
        """Test record_alert integrates with history."""
        await monitor.record_alert(
            component="test",
            severity="warning",
            message="Test message",
            details={"key": "value"},
        )

        alerts = await monitor.history.get_alert_history(hours=1)
        assert len(alerts) == 1
        assert alerts[0]["component"] == "test"
        assert alerts[0]["details"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_monitor_loop_error_handling(self, monitor):
        """Test monitor loop error handling."""
        # Make update_health raise an exception
        monitor.update_health = AsyncMock(side_effect=Exception("Test error"))

        await monitor.start()
        # Let it run briefly
        await asyncio.sleep(0.1)
        await monitor.stop()

        # Should have handled the error gracefully
        assert not monitor._running

    @pytest.mark.asyncio
    async def test_full_update_cycle(self, mock_orchestrator, mock_position_tracker):
        """Test a full health update cycle with mocks."""
        monitor = HealthMonitor(
            orchestrator=mock_orchestrator,
            position_tracker=mock_position_tracker,
        )

        health = await monitor.update_health()

        assert health is not None
        assert health.overall_score >= 0
        assert len(health.component_scores) > 0

        # Check that components are included
        components = [cs.component for cs in health.component_scores]
        assert ComponentType.ORCHESTRATOR in components
        assert ComponentType.POSITION_TRACKER in components
