"""Bybit WebSocket Fill Listener for real-time trade outcome capture.

This module provides WebSocket connection management for Bybit private
execution channel, handling fill events with automatic reconnection,
deduplication, and error recovery.

For ST-LAUNCH-018: Outcome Capture Service Implementation
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import websockets
from src.ml.models.signal_outcome import BybitFillEvent, SignalOutcome
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger(__name__)


class FreshnessReason(Enum):
    """Reason codes for freshness status."""

    FRESH = "fresh"
    STALE_NO_COLLECTION = "stale_no_collection"
    STALE_OLD = "stale_old"
    STALE_API_ERROR = "stale_api_error"
    STALE_REDIS_ERROR = "stale_redis_error"


@dataclass
class BybitListenerConfig:
    """Configuration for Bybit WebSocket listener.

    Attributes:
        api_key: Bybit API key
        api_secret: Bybit API secret
        ws_url: WebSocket endpoint URL
        reconnect_delays: Exponential backoff delays in seconds
        heartbeat_interval: Heartbeat interval in seconds
        dedup_ttl_hours: Redis deduplication TTL in hours
        max_reconnect_attempts: Maximum reconnection attempts (0 = infinite)
    """

    api_key: str = ""
    api_secret: str = ""
    ws_url: str = "wss://stream-demo.bybit.com/v5/private"
    reconnect_delays: list[int] = field(
        default_factory=lambda: [1, 2, 4, 8, 16, 32, 60]
    )
    heartbeat_interval: int = 30
    dedup_ttl_hours: int = 24
    max_reconnect_attempts: int = 0  # 0 = infinite


@dataclass
class ConnectionState:
    """Current connection state.

    Attributes:
        is_connected: Whether WebSocket is connected
        is_authenticated: Whether authentication succeeded
        last_heartbeat: Timestamp of last heartbeat
        last_message: Timestamp of last message received
        reconnect_count: Number of reconnections
        messages_received: Total messages received
        fills_received: Total fill events received
        last_fill_timestamp: ISO timestamp of last fill event
        freshness_status: Current freshness status
    """

    is_connected: bool = False
    is_authenticated: bool = False
    last_heartbeat: float = 0.0
    last_message: float = 0.0
    reconnect_count: int = 0
    messages_received: int = 0
    fills_received: int = 0
    last_fill_timestamp: str = ""
    freshness_status: str = "unknown"

    @property
    def time_since_last_message(self) -> float:
        """Time since last message in seconds."""
        if self.last_message == 0:
            return float("inf")
        return time.time() - self.last_message

    @property
    def time_since_last_fill(self) -> float:
        """Time since last fill in seconds."""
        if not self.last_fill_timestamp:
            return float("inf")
        try:
            last_fill = datetime.fromisoformat(
                self.last_fill_timestamp.replace("Z", "+00:00")
            )
            return (datetime.now(UTC) - last_fill).total_seconds()
        except (ValueError, TypeError):
            return float("inf")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_connected": self.is_connected,
            "is_authenticated": self.is_authenticated,
            "last_heartbeat": self.last_heartbeat,
            "last_message": self.last_message,
            "time_since_last_message": self.time_since_last_message,
            "reconnect_count": self.reconnect_count,
            "messages_received": self.messages_received,
            "fills_received": self.fills_received,
            "last_fill_timestamp": self.last_fill_timestamp,
            "time_since_last_fill": self.time_since_last_fill,
            "freshness_status": self.freshness_status,
        }


class BybitFillListener:
    """WebSocket listener for Bybit execution/fill events.

    This class manages the WebSocket connection to Bybit's private
    execution channel, handling authentication, subscriptions,
    reconnection with exponential backoff, and fill event parsing.

    Usage:
        config = BybitListenerConfig(api_key="...", api_secret="...")
        listener = BybitFillListener(config)

        # Register callback for fill events
        listener.on_fill(lambda outcome: print(f"Fill: {outcome}"))

        # Start listening
        await listener.start()

        # Run until stopped
        await listener.run_forever()
    """

    def __init__(
        self,
        config: BybitListenerConfig | None = None,
        redis_client: Any | None = None,
    ):
        """Initialize the listener.

        Args:
            config: Listener configuration
            redis_client: Optional Redis client for deduplication
        """
        self.config = config or BybitListenerConfig()
        self.redis = redis_client
        self.state = ConnectionState()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._reconnect_attempt = 0
        self._ws_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._fill_callbacks: list[Callable[[SignalOutcome], None]] = []
        self._raw_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._error_callbacks: list[Callable[[Exception], None]] = []

    async def start(self) -> None:
        """Start the WebSocket listener."""
        if self._running:
            logger.warning("Listener already running")
            return

        self._running = True
        self._ws_task = asyncio.create_task(self._websocket_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Bybit fill listener started")

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._running = False

        # Cancel tasks
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        self.state.is_connected = False
        self.state.is_authenticated = False
        logger.info("Bybit fill listener stopped")

    async def run_forever(self) -> None:
        """Run until explicitly stopped."""
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await self.stop()
            raise

    def on_fill(self, callback: Callable[[SignalOutcome], None]) -> None:
        """Register callback for parsed fill events.

        Args:
            callback: Function receiving SignalOutcome
        """
        self._fill_callbacks.append(callback)

    def on_raw_message(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for raw WebSocket messages.

        Args:
            callback: Function receiving raw message dict
        """
        self._raw_callbacks.append(callback)

    def on_error(self, callback: Callable[[Exception], None]) -> None:
        """Register callback for errors.

        Args:
            callback: Function receiving Exception
        """
        self._error_callbacks.append(callback)

    def get_state(self) -> ConnectionState:
        """Get current connection state."""
        return self.state

    def is_healthy(self) -> bool:
        """Check if connection is healthy.

        Returns:
            True if connected and receiving messages
        """
        if not self.state.is_connected:
            return False

        # Check message timeout (2x heartbeat interval)
        timeout_threshold = self.config.heartbeat_interval * 2
        return self.state.time_since_last_message <= timeout_threshold

    async def _websocket_loop(self) -> None:
        """Main WebSocket connection loop with reconnection."""
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket loop error: {e}")
                self._notify_error(e)

            if not self._running:
                break

            # Check max reconnection attempts
            if (
                self.config.max_reconnect_attempts > 0
                and self._reconnect_attempt >= self.config.max_reconnect_attempts
            ):
                logger.error("Max reconnection attempts exceeded")
                break

            # Exponential backoff
            delay = self.config.reconnect_delays[
                min(self._reconnect_attempt, len(self.config.reconnect_delays) - 1)
            ]
            logger.warning(
                f"Reconnecting in {delay}s (attempt {self._reconnect_attempt + 1})"
            )
            await asyncio.sleep(delay)
            self._reconnect_attempt += 1
            self.state.reconnect_count += 1

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages."""
        try:
            async with websockets.connect(self.config.ws_url) as ws:
                self._ws = ws
                self.state.is_connected = True
                self._reconnect_attempt = 0  # Reset on successful connection

                # Authenticate
                if await self._authenticate():
                    self.state.is_authenticated = True
                    # Subscribe to execution channel
                    await self._subscribe_execution()
                else:
                    logger.error("Authentication failed")
                    return

                # Listen for messages
                async for message in ws:
                    if not self._running:
                        break

                    try:
                        data = json.loads(message)
                        await self._handle_message(data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON received: {e}")

        except ConnectionClosed as e:
            logger.warning(f"WebSocket closed: {e}")
        except InvalidStatus as e:
            logger.error(f"WebSocket connection failed: HTTP {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.state.is_connected = False
            self.state.is_authenticated = False
            self._ws = None

    async def _authenticate(self) -> bool:
        """Authenticate with Bybit WebSocket.

        Returns:
            True if authentication succeeded
        """
        assert self._ws is not None, (
            "_authenticate should only be called when connected"
        )
        if not self.config.api_key or not self.config.api_secret:
            logger.error("API key and secret required for authentication")
            return False

        # Generate authentication signature
        expires = int(time.time() * 1000) + 10000  # 10 seconds from now
        signature = hmac.new(
            self.config.api_secret.encode(),
            f"GET/realtime{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()

        auth_msg = {
            "op": "auth",
            "args": [self.config.api_key, expires, signature],
        }

        try:
            await self._ws.send(json.dumps(auth_msg))
            # Wait for auth response
            response = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get("success") is True or data.get("ret_msg") == "OK":
                logger.info("WebSocket authentication successful")
                return True
            else:
                logger.error(f"Authentication failed: {data}")
                return False

        except TimeoutError:
            logger.error("Authentication timeout")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    async def _subscribe_execution(self) -> None:
        """Subscribe to execution channel."""
        assert self._ws is not None, (
            "_subscribe_execution should only be called when connected"
        )
        subscribe_msg = {
            "op": "subscribe",
            "args": [{"channel": "execution"}],
        }

        try:
            await self._ws.send(json.dumps(subscribe_msg))
            logger.info("Subscribed to execution channel")
        except Exception as e:
            logger.error(f"Subscription error: {e}")
            raise

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message.

        Args:
            data: Parsed JSON message
        """
        self.state.last_message = time.time()
        self.state.messages_received += 1

        # Notify raw message callbacks
        for callback in self._raw_callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Raw callback error: {e}")

        msg_type = data.get("op", "")
        topic = data.get("topic", "")

        if msg_type == "pong":
            # Heartbeat response
            self.state.last_heartbeat = time.time()

        elif topic == "execution":
            # Fill execution event
            await self._handle_execution(data)

        elif msg_type == "auth":
            # Auth response (handled in _authenticate)
            pass

        elif "success" in data and data.get("success") is not True:
            # Subscription response
            logger.warning(f"Operation failed: {data}")

    async def _handle_execution(self, data: dict[str, Any]) -> None:
        """Handle execution/fill event.

        Args:
            data: Execution event data
        """
        execution_data = data.get("data", [])

        if not isinstance(execution_data, list):
            logger.warning(f"Unexpected execution data format: {type(execution_data)}")
            return

        for fill_data in execution_data:
            try:
                # Parse fill event
                fill_event = BybitFillEvent.from_websocket_data(fill_data)
                outcome = fill_event.to_signal_outcome()

                # Check for duplicates if Redis is available
                if await self._is_duplicate(outcome.order_id):
                    logger.debug(f"Duplicate fill ignored: {outcome.order_id}")
                    continue

                # Mark as processed
                await self._mark_processed(outcome.order_id)

                self.state.fills_received += 1

                # Update freshness tracking
                self.state.last_fill_timestamp = datetime.now(UTC).isoformat()
                self.state.freshness_status = FreshnessReason.FRESH.value
                await self._update_redis_freshness(outcome)

                # Notify callbacks
                for callback in self._fill_callbacks:
                    try:
                        callback(outcome)
                    except Exception as e:
                        logger.error(f"Fill callback error: {e}")

            except Exception as e:
                logger.error(f"Error processing fill: {e}")
                self._notify_error(e)

    async def _update_redis_freshness(self, outcome: SignalOutcome) -> None:
        """Update Redis with freshness timestamp on fill event.

        Args:
            outcome: Signal outcome from fill event
        """
        if not self.redis:
            return

        try:
            timestamp = datetime.now(UTC).isoformat()
            redis_key = "bmad:chiseai:bybit_truth:websocket_last_fill"
            await self.redis.set(redis_key, timestamp)
            logger.debug(f"Updated Redis freshness timestamp: {timestamp}")
        except Exception as e:
            logger.warning(f"Failed to update Redis freshness: {e}")

    def get_freshness_status(self, threshold_hours: float = 24.0) -> dict[str, Any]:
        """Get current freshness status.

        Args:
            threshold_hours: Hours before data is considered stale

        Returns:
            Dictionary with freshness status information
        """
        now = datetime.now(UTC)

        # Check if we have any fill data
        if not self.state.last_fill_timestamp:
            return {
                "is_fresh": False,
                "status": "stale",
                "reason": FreshnessReason.STALE_NO_COLLECTION.value,
                "hours_since_last_fill": float("inf"),
                "last_fill_timestamp": None,
                "fills_received": self.state.fills_received,
            }

        # Calculate hours since last fill
        try:
            last_fill = datetime.fromisoformat(
                self.state.last_fill_timestamp.replace("Z", "+00:00")
            )
            hours_since = (now - last_fill).total_seconds() / 3600
        except (ValueError, TypeError):
            return {
                "is_fresh": False,
                "status": "error",
                "reason": FreshnessReason.STALE_REDIS_ERROR.value,
                "hours_since_last_fill": float("inf"),
                "last_fill_timestamp": self.state.last_fill_timestamp,
                "fills_received": self.state.fills_received,
            }

        # Determine freshness
        if hours_since > threshold_hours:
            is_fresh = False
            status = "stale"
            reason = FreshnessReason.STALE_OLD.value
        else:
            is_fresh = True
            status = "fresh"
            reason = FreshnessReason.FRESH.value

        return {
            "is_fresh": is_fresh,
            "status": status,
            "reason": reason,
            "hours_since_last_fill": round(hours_since, 2),
            "last_fill_timestamp": self.state.last_fill_timestamp,
            "fills_received": self.state.fills_received,
            "threshold_hours": threshold_hours,
        }

    async def _is_duplicate(self, order_id: str) -> bool:
        """Check if order_id has been processed (deduplication).

        Args:
            order_id: Order ID to check

        Returns:
            True if already processed
        """
        if not self.redis or not order_id:
            return False

        try:
            key = f"bybit:fill:dedup:{order_id}"
            exists = await self.redis.exists(key)
            return bool(exists)
        except Exception as e:
            logger.warning(f"Dedup check failed: {e}")
            return False

    async def _mark_processed(self, order_id: str) -> None:
        """Mark order_id as processed.

        Args:
            order_id: Order ID to mark
        """
        if not self.redis or not order_id:
            return

        try:
            key = f"bybit:fill:dedup:{order_id}"
            ttl = self.config.dedup_ttl_hours * 3600  # Convert to seconds
            await self.redis.setex(key, ttl, "1")
        except Exception as e:
            logger.warning(f"Failed to mark processed: {e}")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep connection alive."""
        while self._running:
            try:
                if self._ws and self.state.is_connected:
                    await self._ws.send(json.dumps({"op": "ping"}))
                    logger.debug("Sent heartbeat ping")

                await asyncio.sleep(self.config.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    def _notify_error(self, error: Exception) -> None:
        """Notify error callbacks.

        Args:
            error: Exception that occurred
        """
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")

    async def __aenter__(self) -> BybitFillListener:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.stop()
