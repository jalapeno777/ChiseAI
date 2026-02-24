"""Tests for Bybit WebSocket Circuit Breaker.

ST-LAUNCH-002: WebSocket Circuit Breaker Implementation

Tests:
- Circuit opens after 5 failures in 60 seconds
- REST fallback activates when circuit is open
- Recovery after cooldown period (HALF_OPEN)
- State transitions work correctly (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Telemetry export to InfluxDB
- Manual control methods (force_open, force_close, reset)
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data.exchange.bybit_connector import BybitConfig, BybitConnector
from data.exchange.bybit_websocket import (
    BybitWebSocketManager,
    CircuitBreakerConfig,
    CircuitBreakerState,
    WebSocketCircuitBreakerState,
    WebSocketMetrics,
    create_websocket_manager_with_registry,
)


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.timeout_seconds == 60.0
        assert config.failure_window_seconds == 60.0
        assert config.half_open_max_calls == 3

    def test_custom_config(self):
        """Test custom configuration."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=30.0,
            failure_window_seconds=30.0,
            half_open_max_calls=1,
        )
        assert config.failure_threshold == 3
        assert config.timeout_seconds == 30.0
        assert config.failure_window_seconds == 30.0
        assert config.half_open_max_calls == 1


class TestWebSocketMetrics:
    """Test WebSocketMetrics tracking."""

    def test_record_success(self):
        """Test recording successful operations."""
        metrics = WebSocketMetrics()

        metrics.record_success()
        assert metrics.success_count == 1
        assert metrics.consecutive_successes == 1
        assert metrics.consecutive_failures == 0
        assert metrics.last_success_time > 0

        metrics.record_success()
        assert metrics.success_count == 2
        assert metrics.consecutive_successes == 2

    def test_record_failure(self):
        """Test recording failed operations."""
        metrics = WebSocketMetrics()

        metrics.record_failure()
        assert metrics.failure_count == 1
        assert metrics.consecutive_failures == 1
        assert metrics.consecutive_successes == 0
        assert metrics.last_failure_time > 0

        metrics.record_failure()
        assert metrics.failure_count == 2
        assert metrics.consecutive_failures == 2

    def test_record_rejection(self):
        """Test recording rejected calls."""
        metrics = WebSocketMetrics()

        metrics.record_rejection()
        assert metrics.rejection_count == 1

        metrics.record_rejection()
        assert metrics.rejection_count == 2

    def test_record_rest_fallback(self):
        """Test recording REST fallback usage."""
        metrics = WebSocketMetrics()

        metrics.record_rest_fallback()
        assert metrics.rest_fallback_count == 1

    def test_record_state_transition(self):
        """Test recording state transitions."""
        metrics = WebSocketMetrics()

        metrics.record_state_transition()
        assert metrics.state_transition_count == 1
        assert metrics.consecutive_successes == 0
        assert metrics.consecutive_failures == 0

    def test_to_dict(self):
        """Test metrics serialization."""
        metrics = WebSocketMetrics()
        metrics.record_success()
        metrics.record_failure()
        metrics.record_rejection()

        data = metrics.to_dict()
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert data["rejection_count"] == 1


class TestWebSocketCircuitBreakerState:
    """Test WebSocketCircuitBreakerState state machine."""

    def test_initial_state(self):
        """Test initial state is CLOSED."""
        cb = WebSocketCircuitBreakerState()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.success_count == 0

    def test_record_failure_no_transition(self):
        """Test recording failures without triggering open."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5)
        )

        # Record 4 failures (below threshold)
        for _ in range(4):
            transitioned = cb.record_failure("test error")
            assert not transitioned
            assert cb.state == CircuitBreakerState.CLOSED

        assert cb.metrics.failure_count == 4

    def test_circuit_opens_after_threshold(self):
        """Test circuit opens after 5 failures."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5)
        )

        # Record 5 failures
        for i in range(4):
            transitioned = cb.record_failure(f"error {i}")
            assert not transitioned

        # 5th failure should trigger transition
        transitioned = cb.record_failure("error 5")
        assert transitioned
        assert cb.state == CircuitBreakerState.OPEN
        # Note: consecutive_failures is reset during state transition
        assert cb.metrics.failure_count == 5

    def test_failure_window_cleanup(self):
        """Test old failures are cleaned from window."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5, failure_window_seconds=0.1)
        )

        # Record 5 failures
        for i in range(5):
            cb.record_failure(f"error {i}")

        assert cb.state == CircuitBreakerState.OPEN

        # Wait for window to expire
        time.sleep(0.15)

        # Old failures should be cleaned
        assert cb.get_recent_failure_count(0.1) == 0

        # Can_execute should transition to HALF_OPEN after timeout
        cb.config.timeout_seconds = 0.05
        time.sleep(0.1)
        assert cb.can_execute()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_to_closed_recovery(self):
        """Test recovery from HALF_OPEN to CLOSED."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5, half_open_max_calls=3)
        )

        # Force to HALF_OPEN state
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.metrics.half_open_calls = 0

        # Record 3 successes to recover
        for i in range(3):
            transitioned = cb.record_success()
            if i < 2:
                assert not transitioned
            else:
                assert transitioned

        assert cb.state == CircuitBreakerState.CLOSED
        # Note: consecutive_successes is reset during state transition
        assert cb.metrics.success_count == 3

    def test_half_open_failure_reopens(self):
        """Test failure in HALF_OPEN reopens circuit."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(half_open_max_calls=3)
        )

        # Force to HALF_OPEN state
        cb.state = CircuitBreakerState.HALF_OPEN

        # Record a failure
        transitioned = cb.record_failure("test error")
        assert transitioned
        assert cb.state == CircuitBreakerState.OPEN

    def test_can_execute_closed_state(self):
        """Test can_execute in CLOSED state."""
        cb = WebSocketCircuitBreakerState()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True

    def test_can_execute_open_state(self):
        """Test can_execute in OPEN state."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(timeout_seconds=60.0)
        )
        cb.state = CircuitBreakerState.OPEN
        cb.metrics.last_state_change = time.time()

        # Should not allow execution before timeout
        assert cb.can_execute() is False
        assert cb.state == CircuitBreakerState.OPEN

    def test_can_execute_open_to_half_open_transition(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(timeout_seconds=0.05)
        )
        cb.state = CircuitBreakerState.OPEN
        cb.metrics.last_state_change = time.time()

        # Wait for timeout
        time.sleep(0.1)

        # Should transition to HALF_OPEN and allow execution
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_can_execute_half_open_limit(self):
        """Test can_execute respects half_open_max_calls limit."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(half_open_max_calls=2)
        )
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.metrics.half_open_calls = 0

        # First call should succeed
        assert cb.can_execute() is True
        assert cb.metrics.half_open_calls == 1

        # Second call should succeed
        assert cb.can_execute() is True
        assert cb.metrics.half_open_calls == 2

        # Third call should fail (limit reached)
        assert cb.can_execute() is False
        assert cb.metrics.half_open_calls == 2

    def test_force_open(self):
        """Test manual force_open."""
        cb = WebSocketCircuitBreakerState()
        assert cb.state == CircuitBreakerState.CLOSED

        cb.force_open("manual test")
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.metrics.state_transition_count == 1

    def test_force_close(self):
        """Test manual force_close."""
        cb = WebSocketCircuitBreakerState()
        cb.state = CircuitBreakerState.OPEN

        cb.force_close("manual test")
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.metrics.state_transition_count == 1

    def test_reset(self):
        """Test reset to initial state."""
        cb = WebSocketCircuitBreakerState()
        cb.state = CircuitBreakerState.OPEN
        cb.record_failure("test")
        cb.record_success()

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.success_count == 0

    def test_to_dict(self):
        """Test state serialization."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5)
        )
        cb.record_failure("test error")

        data = cb.to_dict()
        assert data["state"] == "closed"
        assert data["config"]["failure_threshold"] == 5
        assert data["metrics"]["failure_count"] == 1
        assert data["last_error"] == "test error"


class TestBybitWebSocketManager:
    """Test BybitWebSocketManager with circuit breaker."""

    @pytest.fixture
    def mock_connector(self):
        """Create mock connector for REST fallback."""
        connector = MagicMock()
        connector.get_ticker = AsyncMock(
            return_value={
                "retCode": 0,
                "result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "65000.00"}]},
            }
        )
        return connector

    @pytest.fixture
    def manager(self, mock_connector):
        """Create WebSocket manager with test config."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=1.0,
            failure_window_seconds=60.0,
            half_open_max_calls=2,
        )
        return BybitWebSocketManager(
            ws_url="wss://stream-testnet.bybit.com/v5/public/linear",
            connector=mock_connector,
            circuit_breaker_config=config,
        )

    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert manager.ws_url == "wss://stream-testnet.bybit.com/v5/public/linear"
        assert manager.circuit_breaker.state == CircuitBreakerState.CLOSED
        assert manager.circuit_breaker.config.failure_threshold == 3

    def test_register_callbacks(self, manager):
        """Test callback registration."""
        price_cb = MagicMock()
        message_cb = MagicMock()
        state_cb = MagicMock()

        manager.register_price_callback(price_cb)
        manager.register_message_callback(message_cb)
        manager.register_state_change_callback(state_cb)

        assert price_cb in manager._price_callbacks
        assert message_cb in manager._message_callbacks
        assert state_cb in manager._state_change_callbacks

    @pytest.mark.asyncio
    async def test_start_stop(self, manager):
        """Test starting and stopping manager."""
        # Mock the WebSocket connection to avoid actual network calls
        with patch.object(manager, "_websocket_loop", new_callable=AsyncMock):
            with patch.object(manager, "_heartbeat_loop", new_callable=AsyncMock):
                with patch.object(
                    manager, "_rest_fallback_loop", new_callable=AsyncMock
                ):
                    await manager.start(["BTCUSDT"])
                    assert manager._running is True
                    assert manager._symbols == ["BTCUSDT"]

                    await manager.stop()
                    assert manager._running is False

    def test_get_state(self, manager):
        """Test getting manager state."""
        state = manager.get_state()
        assert "circuit_breaker" in state
        assert "is_connected" in state
        assert "symbols" in state

    def test_force_open(self, manager):
        """Test manual force_open."""
        assert manager.circuit_breaker.state == CircuitBreakerState.CLOSED

        manager.force_open("test")
        assert manager.circuit_breaker.state == CircuitBreakerState.OPEN

    def test_force_close(self, manager):
        """Test manual force_close."""
        manager.force_open("test")
        assert manager.circuit_breaker.state == CircuitBreakerState.OPEN

        manager.force_close("test")
        assert manager.circuit_breaker.state == CircuitBreakerState.CLOSED

    def test_reset(self, manager):
        """Test reset."""
        manager.force_open("test")
        manager.reset()
        assert manager.circuit_breaker.state == CircuitBreakerState.CLOSED

    def test_is_healthy(self, manager):
        """Test health check."""
        # Initially not connected
        assert manager.is_healthy() is False

        # Simulate connected state
        manager._is_connected = True
        manager._last_message_time = time.time()
        assert manager.is_healthy() is True

        # Circuit open should be unhealthy
        manager.force_open("test")
        assert manager.is_healthy() is False

    def test_state_change_callback_emission(self, manager):
        """Test state change callbacks are emitted."""
        callback = MagicMock()
        manager.register_state_change_callback(callback)

        manager.force_open("test")
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == CircuitBreakerState.CLOSED
        assert args[1] == CircuitBreakerState.OPEN


class TestCircuitBreakerIntegrationWithConnector:
    """Test circuit breaker integration with BybitConnector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return BybitConfig(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

    @pytest.fixture
    def connector(self, config):
        """Create test connector."""
        return BybitConnector(config)

    def test_connector_has_circuit_breaker_config(self, connector):
        """Test connector has circuit breaker configuration."""
        assert connector._circuit_breaker_config is not None
        assert connector._circuit_breaker_config.failure_threshold == 5
        assert connector._circuit_breaker_config.timeout_seconds == 60.0

    def test_get_circuit_breaker_state_not_initialized(self, connector):
        """Test getting state before WebSocket starts."""
        state = connector.get_circuit_breaker_state()
        assert state is None

    @pytest.mark.asyncio
    async def test_start_websocket_with_circuit_breaker(self, connector):
        """Test starting WebSocket with circuit breaker enabled."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start = AsyncMock()
            mock_manager_class.return_value = mock_manager

            await connector.start_websocket(["BTCUSDT"], use_circuit_breaker=True)

            assert connector._ws_manager is not None
            mock_manager_class.assert_called_once()
            mock_manager.start.assert_called_once_with(["BTCUSDT"])

    @pytest.mark.asyncio
    async def test_start_websocket_without_circuit_breaker(self, connector):
        """Test starting WebSocket without circuit breaker (legacy mode)."""
        with patch.object(connector, "_websocket_loop", new_callable=AsyncMock):
            with patch.object(connector, "_heartbeat_loop", new_callable=AsyncMock):
                await connector.start_websocket(["BTCUSDT"], use_circuit_breaker=False)

                assert connector._ws_manager is None
                assert connector._ws_task is not None

    @pytest.mark.asyncio
    async def test_close_stops_websocket_manager(self, connector):
        """Test close() stops WebSocket manager."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start = AsyncMock()
            mock_manager.stop = AsyncMock()
            mock_manager_class.return_value = mock_manager

            await connector.start_websocket(["BTCUSDT"], use_circuit_breaker=True)
            await connector.close()

            mock_manager.stop.assert_called_once()
            assert connector._ws_manager is None

    def test_force_circuit_open(self, connector):
        """Test manual force_open through connector."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Simulate manager creation
            connector._ws_manager = mock_manager

            connector.force_circuit_open("test")
            mock_manager.force_open.assert_called_once_with("test")

    def test_force_circuit_closed(self, connector):
        """Test manual force_close through connector."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Simulate manager creation
            connector._ws_manager = mock_manager

            connector.force_circuit_closed("test")
            mock_manager.force_close.assert_called_once_with("test")

    def test_reset_circuit_breaker(self, connector):
        """Test reset through connector."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Simulate manager creation
            connector._ws_manager = mock_manager

            connector.reset_circuit_breaker()
            mock_manager.reset.assert_called_once()

    def test_is_websocket_healthy(self, connector):
        """Test websocket health check through connector."""
        with patch(
            "data.exchange.bybit_connector.BybitWebSocketManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.is_healthy.return_value = True
            mock_manager_class.return_value = mock_manager

            # Initially no manager
            assert connector.is_websocket_healthy() is False

            # Simulate manager creation
            connector._ws_manager = mock_manager
            assert connector.is_websocket_healthy() is True


class TestCircuitBreakerStateTransitions:
    """Test complete state transition scenarios."""

    def test_closed_to_open_transition(self):
        """Test transition from CLOSED to OPEN after failures."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5)
        )

        assert cb.state == CircuitBreakerState.CLOSED

        # Record failures
        for i in range(5):
            cb.record_failure(f"error {i}")

        assert cb.state == CircuitBreakerState.OPEN

    def test_open_to_half_open_transition(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(timeout_seconds=0.05)
        )
        cb.state = CircuitBreakerState.OPEN
        cb.metrics.last_state_change = time.time()

        # Wait for timeout
        time.sleep(0.1)

        # can_execute triggers transition
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_to_closed_transition(self):
        """Test transition from HALF_OPEN to CLOSED after successes."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(half_open_max_calls=3)
        )
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.metrics.half_open_calls = 0

        # Record successes
        for _i in range(3):
            cb.record_success()

        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_to_open_transition(self):
        """Test transition from HALF_OPEN to OPEN on failure."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(half_open_max_calls=3)
        )
        cb.state = CircuitBreakerState.HALF_OPEN

        # Record failure
        cb.record_failure("test error")

        assert cb.state == CircuitBreakerState.OPEN

    def test_full_recovery_cycle(self):
        """Test full recovery cycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(
                failure_threshold=3, timeout_seconds=0.05, half_open_max_calls=2
            )
        )

        # CLOSED → OPEN
        assert cb.state == CircuitBreakerState.CLOSED
        for i in range(3):
            cb.record_failure(f"error {i}")
        assert cb.state == CircuitBreakerState.OPEN

        # OPEN → HALF_OPEN (after timeout)
        time.sleep(0.1)
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # HALF_OPEN → CLOSED (after successes)
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED


class TestRESTFallback:
    """Test REST API fallback functionality."""

    @pytest.fixture
    def mock_connector(self):
        """Create mock connector."""
        connector = MagicMock()
        connector.get_ticker = AsyncMock(
            return_value={
                "retCode": 0,
                "result": {
                    "list": [
                        {"symbol": "BTCUSDT", "lastPrice": "65000.00"},
                        {"symbol": "ETHUSDT", "lastPrice": "3500.00"},
                    ]
                },
            }
        )
        return connector

    @pytest.fixture
    def manager(self, mock_connector):
        """Create WebSocket manager."""
        return BybitWebSocketManager(
            ws_url="wss://test.bybit.com",
            connector=mock_connector,
            circuit_breaker_config=CircuitBreakerConfig(),
        )

    @pytest.mark.asyncio
    async def test_rest_fallback_polling(self, manager, mock_connector):
        """Test REST fallback polls market data."""
        manager._symbols = ["BTCUSDT", "ETHUSDT"]
        manager._running = True

        # Simulate one iteration of REST fallback
        await manager._poll_rest_market_data()

        # Should have called get_ticker for each symbol
        assert mock_connector.get_ticker.call_count == 2
        mock_connector.get_ticker.assert_any_call("BTCUSDT")
        mock_connector.get_ticker.assert_any_call("ETHUSDT")

    @pytest.mark.asyncio
    async def test_rest_fallback_updates_prices(self, manager, mock_connector):
        """Test REST fallback updates last_price cache."""
        manager._symbols = ["BTCUSDT"]
        manager._running = True

        # Add price callback
        price_updates = []

        def on_price(symbol, price):
            price_updates.append((symbol, price))

        manager.register_price_callback(on_price)

        # Poll REST
        await manager._poll_rest_market_data()

        # Should have updated prices
        assert "BTCUSDT" in manager._last_price
        assert manager._last_price["BTCUSDT"] == Decimal("65000.00")

        # Should have triggered callback
        assert len(price_updates) > 0
        assert price_updates[0][0] == "BTCUSDT"
        assert price_updates[0][1] == Decimal("65000.00")

    @pytest.mark.asyncio
    async def test_rest_fallback_handles_errors(self, manager, mock_connector):
        """Test REST fallback handles errors gracefully."""
        manager._symbols = ["BTCUSDT"]
        manager._running = True

        # Make get_ticker raise an exception
        mock_connector.get_ticker.side_effect = Exception("API error")

        # Should not raise
        await manager._poll_rest_market_data()


class TestTelemetryExport:
    """Test telemetry export to InfluxDB."""

    @pytest.fixture
    def mock_influxdb(self):
        """Create mock InfluxDB client."""
        client = MagicMock()
        write_api = MagicMock()
        client.write_api.return_value = write_api
        return client, write_api

    @pytest.fixture
    def manager(self, mock_influxdb):
        """Create WebSocket manager with mock InfluxDB."""
        client, _ = mock_influxdb
        return BybitWebSocketManager(
            ws_url="wss://test.bybit.com",
            connector=MagicMock(),
            circuit_breaker_config=CircuitBreakerConfig(),
            influxdb_client=client,
        )

    @pytest.mark.asyncio
    async def test_telemetry_emission(self, manager, mock_influxdb):
        """Test telemetry is emitted to InfluxDB."""
        client, write_api = mock_influxdb

        # Trigger telemetry emission
        await manager._emit_telemetry("test_event", {"test": "data"})

        # Should have called write_api
        client.write_api.assert_called_once()
        write_api.write.assert_called_once()

        # Check the point structure
        call_args = write_api.write.call_args
        point = call_args[1]["record"]
        assert point["measurement"] == "bybit_websocket_circuit_breaker"
        assert point["tags"]["event_type"] == "test_event"
        assert "fields" in point

    @pytest.mark.asyncio
    async def test_telemetry_handles_errors(self, manager, mock_influxdb):
        """Test telemetry handles InfluxDB errors gracefully."""
        client, write_api = mock_influxdb

        # Make write raise an exception
        write_api.write.side_effect = Exception("InfluxDB error")

        # Should not raise
        await manager._emit_telemetry("test_event", {})


class TestIntegrationWithRegistry:
    """Test integration with CircuitBreakerRegistry."""

    def test_create_manager_with_registry(self):
        """Test create_websocket_manager_with_registry function."""
        mock_connector = MagicMock()
        mock_registry = MagicMock()

        manager = create_websocket_manager_with_registry(
            ws_url="wss://test.bybit.com",
            connector=mock_connector,
            registry=mock_registry,
            name="test_websocket",
        )

        assert isinstance(manager, BybitWebSocketManager)
        mock_registry.register.assert_called_once()

    def test_create_manager_without_registry(self):
        """Test manager creation without registry."""
        mock_connector = MagicMock()

        manager = create_websocket_manager_with_registry(
            ws_url="wss://test.bybit.com",
            connector=mock_connector,
            registry=None,
            name="test_websocket",
        )

        assert isinstance(manager, BybitWebSocketManager)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_circuit_breaker_with_zero_threshold(self):
        """Test circuit breaker with zero threshold (immediate open)."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=0)
        )

        # First failure should open circuit
        transitioned = cb.record_failure("test")
        assert transitioned
        assert cb.state == CircuitBreakerState.OPEN

    def test_circuit_breaker_with_very_short_timeout(self):
        """Test circuit breaker with very short timeout."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(timeout_seconds=0.001)
        )
        cb.state = CircuitBreakerState.OPEN
        cb.metrics.last_state_change = time.time()

        # Wait for timeout
        time.sleep(0.01)

        # Should transition immediately
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_concurrent_failure_recording(self):
        """Test concurrent failure recording."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=10)
        )

        # Record failures from multiple "threads"
        for _ in range(5):
            cb.record_failure("test")

        assert cb.metrics.failure_count == 5
        assert cb.get_recent_failure_count(60.0) == 5

    def test_state_persistence_through_reset(self):
        """Test that reset clears all state."""
        cb = WebSocketCircuitBreakerState(
            config=CircuitBreakerConfig(failure_threshold=5)
        )

        # Record some activity
        cb.record_failure("error 1")
        cb.record_success()
        cb.record_failure("error 2")

        assert cb.metrics.failure_count == 2
        assert cb.metrics.success_count == 1

        # Reset
        cb.reset()

        # All state should be cleared
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.success_count == 0
        assert cb.last_error is None
