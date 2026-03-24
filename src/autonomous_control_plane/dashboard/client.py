"""Dashboard WebSocket client.

Client for connecting to dashboard sync server for real-time updates.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Optional WebSocket support
try:
    import websockets
    from websockets.client import WebSocketClientProtocol

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketClientProtocol = Any


class DashboardClient:
    """Client for connecting to dashboard sync server.

    Provides real-time updates from the ACP dashboard server via WebSocket.
    Falls back to polling if WebSocket is unavailable.

    Example:
        >>> client = DashboardClient("ws://localhost:8765/acp-dashboard")
        >>> await client.connect()
        >>> async for state in client.updates():
        ...     print(f"Open incidents: {state['incidents']['open']}")
        >>> await client.disconnect()
    """

    def __init__(
        self,
        uri: str = "ws://localhost:8765/acp-dashboard",
        api_url: str = "http://localhost:8080/api/v1/dashboard",
    ):
        """Initialize dashboard client.

        Args:
            uri: WebSocket URI for real-time updates
            api_url: REST API URL for fallback polling
        """
        self.uri = uri
        self.api_url = api_url
        self._websocket: WebSocketClientProtocol | None = None
        self._connected = False
        self._poll_task: asyncio.Task | None = None
        self._use_polling = False

    async def connect(self) -> bool:
        """Connect to the dashboard server.

        Returns:
            True if connected successfully
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("websockets package not available, using polling fallback")
            self._use_polling = True
            self._start_polling()
            return True

        try:
            self._websocket = await websockets.connect(self.uri)
            self._connected = True
            logger.info(f"Connected to dashboard server at {self.uri}")

            # Receive initial state
            try:
                message = await asyncio.wait_for(self._websocket.recv(), timeout=5.0)
                initial_state = json.loads(message)
                logger.debug(f"Received initial state: {initial_state}")
            except TimeoutError:
                logger.warning("Timeout waiting for initial state")

            return True

        except Exception as e:
            logger.warning(f"WebSocket connection failed: {e}, falling back to polling")
            self._use_polling = True
            self._start_polling()
            return True

    async def disconnect(self) -> None:
        """Disconnect from the dashboard server."""
        self._connected = False

        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            finally:
                self._websocket = None

        logger.info("Disconnected from dashboard server")

    async def updates(self):
        """Async generator for state updates.

        Yields:
            State dictionary on each update (every 5 seconds)

        Example:
            >>> async for state in client.updates():
            ...     print(f"Health: {state['system_health']['health_score']['overall_score']}%")
        """
        if self._use_polling:
            async for state in self._poll_updates():
                yield state
        else:
            async for state in self._websocket_updates():
                yield state

    async def _websocket_updates(self):
        """Yield updates from WebSocket connection."""
        if not self._connected or not self._websocket:
            raise RuntimeError("Not connected")

        try:
            async for message in self._websocket:
                try:
                    state = json.loads(message)
                    yield state
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {message}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
            self._connected = False

            # Fallback to polling
            self._use_polling = True
            async for state in self._poll_updates():
                yield state

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self._connected = False

    async def _poll_updates(self):
        """Yield updates from polling fallback."""
        import aiohttp

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_url}/state") as response:
                        if response.status == 200:
                            state = await response.json()
                            yield state
                        else:
                            logger.warning(f"Polling error: HTTP {response.status}")

            except Exception as e:
                logger.warning(f"Polling error: {e}")

            # Poll every 5 seconds (matching WebSocket interval)
            await asyncio.sleep(5.0)

    def _start_polling(self) -> None:
        """Start polling task."""
        if self._poll_task is None:
            # Polling is handled by the updates() generator
            pass

    async def request_refresh(self) -> None:
        """Request an immediate state refresh."""
        if self._connected and self._websocket and not self._use_polling:
            await self._websocket.send(json.dumps({"type": "refresh"}))

    async def ping(self) -> bool:
        """Ping the server to check connectivity.

        Returns:
            True if server responds
        """
        if self._connected and self._websocket and not self._use_polling:
            try:
                await self._websocket.send(json.dumps({"type": "ping"}))
                # Wait for pong with timeout
                message = await asyncio.wait_for(self._websocket.recv(), timeout=5.0)
                data = json.loads(message)
                return data.get("type") == "pong"
            except Exception:
                return False
        else:
            # Try HTTP ping
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_url}/health") as response:
                        return response.status == 200
            except Exception:
                return False

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if connected
        """
        return self._connected or self._use_polling

    @property
    def using_polling(self) -> bool:
        """Check if using polling fallback.

        Returns:
            True if using polling instead of WebSocket
        """
        return self._use_polling
