"""Bybit WebSocket handler with circuit breaker integration.

ST-LAUNCH-002: WebSocket Circuit Breaker Implementation

Provides:
- WebSocket connection management with automatic circuit breaker
- Failure tracking (5 failures in 60s → OPEN)
- State transitions: CLOSED → OPEN → HALF_OPEN → CLOSED
- REST API fallback when circuit is open
- Metrics export to InfluxDB
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast, using REST fallback
    HALF_OPEN = "half_open"  # Testing recovery


class StateTransitionReason(Enum):
    """Reasons for state transitions."""

    FAILURE_THRESHOLD = "failure_threshold"
    TIMEOUT_ELAPSED = "timeout_elapsed"
    RECOVERY_CONFIRMED = "recovery_confirmed"
    MANUAL_FORCE = "manual_force"


@dataclass
class CircuitBreakerConfig:
    """Configuration for WebSocket circuit breaker.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        timeout_seconds: Time before transitioning to HALF_OPEN
        failure_window_seconds: Time window for counting failures
        half_open_max_calls: Max calls allowed in HALF_OPEN state
    """

    failure_threshold: int = 5
    timeout_seconds: float = 60.0
    failure_window_seconds: float = 60.0
    half_open_max_calls: int = 3


@dataclass
class WebSocketMetrics:
    """Metrics for WebSocket connection."""

    failure_count: int = 0
    success_count: int = 0
    rejection_count: int = 0
    rest_fallback_count: int = 0
    state_transition_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    half_open_calls: int = 0

    def record_success(self) -> None:
        """Record a successful operation."""
        self.success_count += 1
        self.last_success_time = time.time()
        self.consecutive_successes += 1
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_failures += 1
        self.consecutive_successes = 0

    def record_rejection(self) -> None:
        """Record a rejected call (circuit open)."""
        self.rejection_count += 1

    def record_rest_fallback(self) -> None:
        """Record a REST fallback usage."""
        self.rest_fallback_count += 1

    def record_state_transition(self) -> None:
        """Record a state transition."""
        self.state_transition_count += 1
        self.last_state_change = time.time()
        self.consecutive_successes = 0
        self.consecutive_failures = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "rejection_count": self.rejection_count,
            "rest_fallback_count": self.rest_fallback_count,
            "state_transition_count": self.state_transition_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change": self.last_state_change,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "half_open_calls": self.half_open_calls,
        }


@dataclass
class WebSocketCircuitBreakerState:
    """Complete state for WebSocket circuit breaker."""

    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    metrics: WebSocketMetrics = field(default_factory=WebSocketMetrics)
    last_error: str | None = None
    _failure_timestamps: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize failure timestamps list if not provided."""
        if self._failure_timestamps is None:
            self._failure_timestamps = []

    def _clean_old_failures(self, window: float) -> None:
        """Remove failures outside the time window."""
        now = time.time()
        self._failure_timestamps = [
            t for t in self._failure_timestamps if now - t <= window
        ]

    def get_recent_failure_count(self, window: float) -> int:
        """Get count of failures within time window."""
        self._clean_old_failures(window)
        return len(self._failure_timestamps)

    def record_failure(self, error: str | None = None) -> bool:
        """Record a failure and check if circuit should open.

        Args:
            error: Optional error message

        Returns:
            True if circuit transitioned to OPEN
        """
        self.last_error = error
        self._failure_timestamps.append(time.time())
        self._clean_old_failures(self.config.failure_window_seconds)
        self.metrics.record_failure()

        # Check if we should open the circuit
        if (
            self.state == CircuitBreakerState.CLOSED
            and len(self._failure_timestamps) >= self.config.failure_threshold
        ):
            self.state = CircuitBreakerState.OPEN
            self.metrics.record_state_transition()
            self.metrics.half_open_calls = 0
            logger.warning(
                f"Circuit breaker: CLOSED -> OPEN "
                f"(threshold={self.config.failure_threshold}, "
                f"failures={len(self._failure_timestamps)})"
            )
            return True

        # Any failure in HALF_OPEN immediately opens circuit
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.metrics.record_state_transition()
            logger.warning(
                "Circuit breaker: HALF_OPEN -> OPEN (failure in half-open state)"
            )
            return True

        return False

    def record_success(self) -> bool:
        """Record a success and check if circuit should close.

        Returns:
            True if circuit transitioned to CLOSED
        """
        self.metrics.record_success()

        # Check if we should close the circuit from HALF_OPEN
        if (
            self.state == CircuitBreakerState.HALF_OPEN
            and self.metrics.consecutive_successes >= self.config.half_open_max_calls
        ):
            self.state = CircuitBreakerState.CLOSED
            self.metrics.record_state_transition()
            self.metrics.half_open_calls = 0
            self.last_error = None
            logger.info(
                f"Circuit breaker: HALF_OPEN -> CLOSED "
                f"(recovered with {self.metrics.consecutive_successes} successes)"
            )
            return True

        return False

    def record_rejection(self) -> None:
        """Record a rejected call (circuit open)."""
        self.metrics.record_rejection()

    def record_rest_fallback(self) -> None:
        """Record REST fallback usage."""
        self.metrics.record_rest_fallback()

    def can_execute(self) -> bool:
        """Check if WebSocket call can execute.

        Returns:
            True if call should proceed, False if circuit is open
        """
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if timeout has elapsed for transition to HALF_OPEN
            elapsed = time.time() - self.metrics.last_state_change
            if elapsed >= self.config.timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                self.metrics.record_state_transition()
                self.metrics.half_open_calls = 0
                logger.info(
                    f"Circuit breaker: OPEN -> HALF_OPEN (timeout={elapsed:.1f}s elapsed)"
                )
                return True
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.metrics.half_open_calls < self.config.half_open_max_calls:
                self.metrics.half_open_calls += 1
                return True
            return False

        return False

    def force_open(self, reason: str = "manual") -> None:
        """Force circuit to open state."""
        if self.state != CircuitBreakerState.OPEN:
            self.state = CircuitBreakerState.OPEN
            self.metrics.record_state_transition()
            logger.warning(f"Circuit breaker: Forced OPEN ({reason})")

    def force_close(self, reason: str = "manual") -> None:
        """Force circuit to closed state."""
        if self.state != CircuitBreakerState.CLOSED:
            self.state = CircuitBreakerState.CLOSED
            self.metrics.record_state_transition()
            self.metrics.half_open_calls = 0
            self.last_error = None
            logger.info(f"Circuit breaker: Forced CLOSED ({reason})")

    def reset(self) -> None:
        """Reset circuit to initial state."""
        self.state = CircuitBreakerState.CLOSED
        self.metrics = WebSocketMetrics()
        self._failure_timestamps = []
        self.last_error = None
        logger.info("Circuit breaker: Reset to initial state")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.value,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "failure_window_seconds": self.config.failure_window_seconds,
                "half_open_max_calls": self.config.half_open_max_calls,
            },
            "metrics": self.metrics.to_dict(),
            "last_error": self.last_error,
            "recent_failure_count": len(self._failure_timestamps),
        }


class BybitWebSocketManager:
    """WebSocket connection manager with circuit breaker integration.

    Provides:
    - Automatic circuit breaker with configurable thresholds
    - REST API fallback when WebSocket circuit is open
    - Telemetry export to InfluxDB
    - Exponential backoff reconnection

    Example:
        >>> manager = BybitWebSocketManager(config, connector)
        >>> await manager.start(["BTCUSDT", "ETHUSDT"])
        >>> # Circuit breaker automatically handles failures
        >>> await manager.stop()
    """

    # Exponential backoff delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s max
    RECONNECT_DELAYS = [1, 2, 4, 8, 16, 32, 60]
    HEARTBEAT_INTERVAL = 30  # seconds
    REST_FALLBACK_INTERVAL = 5  # seconds between REST polls when WS is open

    def __init__(
        self,
        ws_url: str,
        connector: Any,  # BybitConnector for REST fallback
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        influxdb_client: Any | None = None,
    ) -> None:
        """Initialize WebSocket manager.

        Args:
            ws_url: WebSocket endpoint URL
            connector: BybitConnector instance for REST fallback
            circuit_breaker_config: Circuit breaker configuration
            influxdb_client: Optional InfluxDB client for telemetry
        """
        self.ws_url = ws_url
        self.connector = connector
        self.circuit_breaker = WebSocketCircuitBreakerState(
            config=circuit_breaker_config or CircuitBreakerConfig()
        )
        self._influxdb = influxdb_client

        # Connection state
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._reconnect_attempt = 0
        self._symbols: list[str] = []
        self._last_price: dict[str, Decimal] = {}
        self._last_orderbook: dict[str, dict] = {}

        # Background tasks
        self._ws_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._rest_fallback_task: asyncio.Task | None = None

        # Callbacks
        self._price_callbacks: list[Callable[[str, Decimal], None]] = []
        self._message_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._state_change_callbacks: list[
            Callable[[CircuitBreakerState, CircuitBreakerState], None]
        ] = []

        # Connection health
        self._last_message_time: float = 0.0
        self._is_connected: bool = False

    def register_price_callback(self, callback: Callable[[str, Decimal], None]) -> None:
        """Register callback for price updates."""
        self._price_callbacks.append(callback)

    def register_message_callback(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register callback for all messages."""
        self._message_callbacks.append(callback)

    def register_state_change_callback(
        self, callback: Callable[[CircuitBreakerState, CircuitBreakerState], None]
    ) -> None:
        """Register callback for circuit breaker state changes.

        Args:
            callback: Function receiving (previous_state, new_state)
        """
        self._state_change_callbacks.append(callback)

    async def start(self, symbols: list[str] | None = None) -> None:
        """Start WebSocket connection with circuit breaker.

        Args:
            symbols: List of symbols to subscribe to
        """
        self._running = True
        self._symbols = symbols or ["BTCUSDT"]

        # Start WebSocket task
        self._ws_task = asyncio.create_task(self._websocket_loop())

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start REST fallback task
        self._rest_fallback_task = asyncio.create_task(self._rest_fallback_loop())

        logger.info(f"BybitWebSocketManager started with {len(self._symbols)} symbols")

    async def stop(self) -> None:
        """Stop all connections and tasks."""
        self._running = False

        # Cancel tasks
        for task in [self._ws_task, self._heartbeat_task, self._rest_fallback_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        self._is_connected = False
        logger.info("BybitWebSocketManager stopped")

    async def _websocket_loop(self) -> None:
        """Main WebSocket loop with circuit breaker and reconnection."""
        while self._running:
            try:
                # Check if circuit breaker allows WebSocket connection
                if not self.circuit_breaker.can_execute():
                    # Circuit is open - wait and retry
                    await asyncio.sleep(1)
                    continue

                # Attempt WebSocket connection
                await self._connect_and_listen()

                # Connection closed normally - record success for HALF_OPEN recovery
                if self.circuit_breaker.state == CircuitBreakerState.HALF_OPEN:
                    transitioned = self.circuit_breaker.record_success()
                    if transitioned:
                        self._emit_state_change(
                            CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED
                        )

                # Reset reconnect attempt on successful connection cycle
                self._reconnect_attempt = 0

            except Exception as e:
                error_msg = str(e)
                logger.error(f"WebSocket error: {error_msg}")

                # Record failure in circuit breaker
                transitioned = self.circuit_breaker.record_failure(error_msg)
                if transitioned:
                    self._emit_state_change(
                        CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN
                    )
                    logger.warning("Circuit breaker opened due to WebSocket failure")

            if not self._running:
                break

            # Exponential backoff for reconnection
            delay = self.RECONNECT_DELAYS[
                min(self._reconnect_attempt, len(self.RECONNECT_DELAYS) - 1)
            ]
            logger.warning(
                f"WebSocket reconnecting in {delay}s (attempt {self._reconnect_attempt + 1})"
            )
            await asyncio.sleep(delay)
            self._reconnect_attempt += 1

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages."""
        try:
            async with websockets.connect(self.ws_url) as ws:
                self._ws = ws
                self._is_connected = True
                self._last_message_time = time.time()

                # Subscribe to tickers
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {"channel": "tickers", "symbol": s} for s in self._symbols
                    ],
                }
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"WebSocket subscribed to tickers: {self._symbols}")

                # Listen for messages
                async for message in ws:
                    if not self._running:
                        break

                    try:
                        data = json.loads(message)
                        await self._handle_message(data)

                        # Record success for circuit breaker in HALF_OPEN state
                        if self.circuit_breaker.state == CircuitBreakerState.HALF_OPEN:
                            transitioned = self.circuit_breaker.record_success()
                            if transitioned:
                                self._emit_state_change(
                                    CircuitBreakerState.HALF_OPEN,
                                    CircuitBreakerState.CLOSED,
                                )

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {message[:200]}")

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            raise
        except InvalidStatusCode as e:
            logger.error(f"WebSocket connection failed with status: {e}")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise
        finally:
            self._is_connected = False
            self._ws = None

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        self._last_message_time = time.time()

        msg_type = data.get("topic", "")

        if "tickers" in msg_type:
            # Price update
            ticker_data = data.get("data", {})
            symbol = ticker_data.get("symbol", "")
            last_price = ticker_data.get("lastPrice", "0")

            if symbol and last_price:
                price = Decimal(last_price)
                self._last_price[symbol] = price

                for callback in self._price_callbacks:
                    try:
                        callback(symbol, price)
                    except Exception as e:
                        logger.error(f"Price callback error: {e}")

        elif "orderbook" in msg_type:
            # Order book update
            orderbook_data = data.get("data", {})
            symbol = orderbook_data.get("s", "")
            if symbol:
                self._last_orderbook[symbol] = orderbook_data

        elif data.get("op") == "pong":
            # Heartbeat response
            pass

        # Call general message callbacks
        for callback in self._message_callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Message callback error: {e}")

        # Emit telemetry
        await self._emit_telemetry("websocket_message", data)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep connection alive."""
        while self._running:
            try:
                if self._ws and self._is_connected:
                    await self._ws.send(json.dumps({"op": "ping"}))
                    logger.debug("Sent WebSocket heartbeat ping")

                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    async def _rest_fallback_loop(self) -> None:
        """REST API fallback loop when WebSocket circuit is open."""
        while self._running:
            try:
                # Check if circuit breaker allows REST fallback
                if self.circuit_breaker.state == CircuitBreakerState.OPEN:
                    # Circuit is open - use REST API for market data
                    await self._poll_rest_market_data()
                    self.circuit_breaker.record_rest_fallback()

                await asyncio.sleep(self.REST_FALLBACK_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"REST fallback error: {e}")
                await asyncio.sleep(self.REST_FALLBACK_INTERVAL)

    async def _poll_rest_market_data(self) -> None:
        """Poll market data via REST API when WebSocket is unavailable."""
        if not self.connector:
            return

        for symbol in self._symbols:
            try:
                # Get ticker data via REST
                ticker_data = await self.connector.get_ticker(symbol)

                if ticker_data and ticker_data.get("retCode") == 0:
                    result = ticker_data.get("result", {}).get("list", [])
                    if result:
                        ticker = result[0]
                        last_price = ticker.get("lastPrice", "0")
                        if last_price:
                            price = Decimal(last_price)
                            self._last_price[symbol] = price

                            # Notify price callbacks
                            for callback in self._price_callbacks:
                                try:
                                    callback(symbol, price)
                                except Exception as e:
                                    logger.error(f"REST price callback error: {e}")

                logger.debug(f"REST fallback: Polled {symbol} via REST API")

            except Exception as e:
                logger.warning(f"REST fallback failed for {symbol}: {e}")

    def _emit_state_change(
        self, previous_state: CircuitBreakerState, new_state: CircuitBreakerState
    ) -> None:
        """Emit circuit breaker state change event."""
        for callback in self._state_change_callbacks:
            try:
                callback(previous_state, new_state)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    async def _emit_telemetry(
        self, event_type: str, data: dict[str, Any] | None = None
    ) -> None:
        """Emit telemetry to InfluxDB.

        Args:
            event_type: Type of telemetry event
            data: Additional event data
        """
        if self._influxdb is None:
            return

        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self._influxdb.write_api(write_options=SYNCHRONOUS)

            point = {
                "measurement": "bybit_websocket_circuit_breaker",
                "tags": {
                    "circuit_state": self.circuit_breaker.state.value,
                    "event_type": event_type,
                },
                "fields": {
                    "failure_count": self.circuit_breaker.metrics.failure_count,
                    "success_count": self.circuit_breaker.metrics.success_count,
                    "rejection_count": self.circuit_breaker.metrics.rejection_count,
                    "rest_fallback_count": self.circuit_breaker.metrics.rest_fallback_count,
                    "state_transition_count": self.circuit_breaker.metrics.state_transition_count,
                    "consecutive_successes": self.circuit_breaker.metrics.consecutive_successes,
                    "consecutive_failures": self.circuit_breaker.metrics.consecutive_failures,
                    "half_open_calls": self.circuit_breaker.metrics.half_open_calls,
                    "is_connected": 1 if self._is_connected else 0,
                },
                "time": int(time.time() * 1e9),  # Nanoseconds
            }

            # Add bucket/org from settings if available
            bucket = "chiseai_metrics"
            org = "chiseai"

            write_api.write(bucket=bucket, org=org, record=point)
            logger.debug(f"Emitted telemetry: {event_type}")

        except Exception as e:
            logger.warning(f"Failed to emit telemetry: {e}")

    def get_state(self) -> dict[str, Any]:
        """Get current circuit breaker state.

        Returns:
            Dictionary with circuit breaker state and metrics
        """
        return {
            "circuit_breaker": self.circuit_breaker.to_dict(),
            "is_connected": self._is_connected,
            "last_message_time": self._last_message_time,
            "reconnect_attempt": self._reconnect_attempt,
            "symbols": self._symbols,
            "last_prices": {k: str(v) for k, v in self._last_price.items()},
        }

    def force_open(self, reason: str = "manual") -> None:
        """Manually force circuit breaker to open."""
        previous = self.circuit_breaker.state
        self.circuit_breaker.force_open(reason)
        if previous != CircuitBreakerState.OPEN:
            self._emit_state_change(previous, CircuitBreakerState.OPEN)

    def force_close(self, reason: str = "manual") -> None:
        """Manually force circuit breaker to closed."""
        previous = self.circuit_breaker.state
        self.circuit_breaker.force_close(reason)
        if previous != CircuitBreakerState.CLOSED:
            self._emit_state_change(previous, CircuitBreakerState.CLOSED)

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        previous = self.circuit_breaker.state
        self.circuit_breaker.reset()
        self._emit_state_change(previous, CircuitBreakerState.CLOSED)

    def is_healthy(self) -> bool:
        """Check if WebSocket connection is healthy.

        Returns:
            True if connected and circuit is closed or half-open
        """
        if not self._is_connected:
            return False

        if self.circuit_breaker.state == CircuitBreakerState.OPEN:
            return False

        # Check if we've received messages recently
        if time.time() - self._last_message_time > self.HEARTBEAT_INTERVAL * 2:
            return False

        return True


# Convenience function for integration with CircuitBreakerRegistry
def create_websocket_manager_with_registry(
    ws_url: str,
    connector: Any,
    registry: Any | None = None,
    name: str = "bybit_websocket",
) -> BybitWebSocketManager:
    """Create WebSocket manager integrated with CircuitBreakerRegistry.

    Args:
        ws_url: WebSocket endpoint URL
        connector: BybitConnector instance
        registry: CircuitBreakerRegistry instance (optional)
        name: Circuit breaker name in registry

    Returns:
        Configured BybitWebSocketManager
    """
    manager = BybitWebSocketManager(ws_url, connector)

    # Register with CircuitBreakerRegistry if provided
    if registry is not None:
        try:
            from autonomous_control_plane.models.circuit_breaker import (
                CircuitBreakerConfig as RegistryConfig,
            )

            cb_config = RegistryConfig(
                failure_threshold=5,
                timeout_seconds=60.0,
                half_open_max_calls=3,
            )
            registry.register(name, cb_config)

            # Set up state change callback to sync with registry
            def on_state_change(
                previous: CircuitBreakerState, new: CircuitBreakerState
            ) -> None:
                # Update registry state
                pass  # Registry polls for state

            manager.register_state_change_callback(on_state_change)

        except ImportError:
            logger.warning(
                "CircuitBreakerRegistry not available, using standalone mode"
            )

    return manager
