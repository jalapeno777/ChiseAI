"""Dashboard synchronization server for real-time ACP telemetry updates.

Provides WebSocket server for pushing real-time updates to Grafana dashboard
and fallback polling mechanism for clients without WebSocket support.

For ST-NS-043: Unified Dashboard & Alerting Integration
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# Optional WebSocket support
try:
    import websockets
    from websockets.server import WebSocketServerProtocol

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketServerProtocol = Any

if TYPE_CHECKING:
    from autonomous_control_plane.components.incident_manager import IncidentManager
    from autonomous_control_plane.components.rollback_coordinator import (
        RollbackCoordinator,
    )
    from autonomous_control_plane.components.self_healing_engine import (
        SelfHealingEngine,
    )
    from common.circuit_breaker import CircuitBreakerRegistry


@dataclass
class ACPStateSnapshot:
    """Snapshot of Autonomous Control Plane state."""

    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    circuit_breakers: dict[str, Any] = field(default_factory=dict)
    incidents: dict[str, Any] = field(default_factory=dict)
    healing_actions: dict[str, Any] = field(default_factory=dict)
    rollbacks: dict[str, Any] = field(default_factory=dict)
    retry_activity: dict[str, Any] = field(default_factory=dict)
    system_health: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "timestamp": self.timestamp,
            "circuit_breakers": self.circuit_breakers,
            "incidents": self.incidents,
            "healing_actions": self.healing_actions,
            "rollbacks": self.rollbacks,
            "retry_activity": self.retry_activity,
            "system_health": self.system_health,
        }


class DashboardSyncServer:
    """WebSocket server for real-time dashboard updates.

    Pushes state changes to connected dashboard clients every 5 seconds.
    Provides fallback HTTP polling endpoint for non-WebSocket clients.

    Example:
        >>> server = DashboardSyncServer()
        >>> await server.start()
        >>> # Clients connect to ws://localhost:8765/acp-dashboard
        >>> await server.stop()
    """

    DEFAULT_HOST = "0.0.0.0"  # nosec: B104 - Dashboard server intentionally binds to all interfaces for containerized deployment
    DEFAULT_PORT = 8765
    UPDATE_INTERVAL = 5.0  # 5-second refresh as per AC

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        incident_manager: IncidentManager | None = None,
        healing_engine: SelfHealingEngine | None = None,
        rollback_coordinator: RollbackCoordinator | None = None,
    ):
        """Initialize dashboard sync server.

        Args:
            host: Host to bind WebSocket server
            port: Port to bind WebSocket server
            circuit_breaker_registry: Registry for circuit breaker states
            incident_manager: Incident manager for incident data
            healing_engine: Self-healing engine for healing metrics
            rollback_coordinator: Rollback coordinator for rollback history
        """
        self.host = host
        self.port = port
        self.circuit_breaker_registry = circuit_breaker_registry
        self.incident_manager = incident_manager
        self.healing_engine = healing_engine
        self.rollback_coordinator = rollback_coordinator

        self._server: asyncio.Task | None = None
        self._clients: set[WebSocketServerProtocol] = set()
        self._running = False
        self._update_task: asyncio.Task | None = None

        if not WEBSOCKETS_AVAILABLE:
            logger.warning(
                "websockets package not available. "
                "DashboardSyncServer will use polling fallback only."
            )

    async def start(self) -> None:
        """Start the WebSocket server and update loop."""
        if self._running:
            logger.warning("DashboardSyncServer already running")
            return

        self._running = True
        logger.info(f"Starting DashboardSyncServer on {self.host}:{self.port}")

        if WEBSOCKETS_AVAILABLE:
            self._server = asyncio.create_task(self._run_websocket_server())

        self._update_task = asyncio.create_task(self._update_loop())

    async def stop(self) -> None:
        """Stop the WebSocket server and update loop."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping DashboardSyncServer")

        if self._update_task:
            self._update_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._update_task

        if self._server:
            self._server.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._server

        # Close all client connections
        if WEBSOCKETS_AVAILABLE:
            for client in list(self._clients):
                await client.close()
            self._clients.clear()

    async def _run_websocket_server(self) -> None:
        """Run the WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            return

        try:
            async with websockets.serve(self._handle_client, self.host, self.port):
                logger.info(
                    f"WebSocket server listening on ws://{self.host}:{self.port}"
                )
                # Keep server running until cancelled
                while self._running:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("WebSocket server cancelled")
            raise
        except Exception as e:
            logger.error(f"WebSocket server error: {e}")

    async def _handle_client(
        self, websocket: WebSocketServerProtocol, path: str
    ) -> None:
        """Handle a new WebSocket client connection.

        Args:
            websocket: WebSocket connection
            path: Connection path (should be /acp-dashboard)
        """
        if path != "/acp-dashboard":
            logger.warning(f"Client connected to unknown path: {path}")
            await websocket.close(1000, "Invalid path")
            return

        self._clients.add(websocket)
        logger.info(f"Dashboard client connected. Total clients: {len(self._clients)}")

        try:
            # Send initial state
            state = await self._get_current_state()
            await websocket.send(json.dumps(state.to_dict()))

            # Keep connection alive and handle client messages
            async for message in websocket:
                # Handle any client requests (e.g., refresh, filter changes)
                try:
                    data = json.loads(message)
                    await self._handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {message}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("Dashboard client disconnected")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            self._clients.discard(websocket)
            logger.info(f"Client removed. Total clients: {len(self._clients)}")

    async def _handle_client_message(
        self, websocket: WebSocketServerProtocol, data: dict[str, Any]
    ) -> None:
        """Handle a message from a client.

        Args:
            websocket: Client WebSocket
            data: Parsed JSON message
        """
        msg_type = data.get("type", "")

        if msg_type == "refresh":
            # Client requested immediate refresh
            state = await self._get_current_state()
            await websocket.send(json.dumps(state.to_dict()))
        elif msg_type == "ping":
            # Keep-alive ping
            await websocket.send(json.dumps({"type": "pong"}))
        else:
            logger.debug(f"Unknown message type: {msg_type}")

    async def _update_loop(self) -> None:
        """Main update loop - broadcasts state to all clients every 5 seconds."""
        while self._running:
            try:
                if self._clients:
                    state = await self._get_current_state()
                    message = json.dumps(state.to_dict())

                    # Send to all connected clients
                    disconnected = []
                    for client in self._clients:
                        try:
                            await client.send(message)
                        except websockets.exceptions.ConnectionClosed:
                            disconnected.append(client)
                        except Exception as e:
                            logger.error(f"Error sending to client: {e}")
                            disconnected.append(client)

                    # Remove disconnected clients
                    for client in disconnected:
                        self._clients.discard(client)

                await asyncio.sleep(self.UPDATE_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Update loop error: {e}")
                await asyncio.sleep(self.UPDATE_INTERVAL)

    async def _get_current_state(self) -> ACPStateSnapshot:
        """Get current state snapshot from all ACP components.

        Returns:
            ACPStateSnapshot with current metrics
        """
        snapshot = ACPStateSnapshot()

        # Circuit breaker states
        if self.circuit_breaker_registry:
            try:
                snapshot.circuit_breakers = (
                    self.circuit_breaker_registry.get_all_states()
                )
            except Exception as e:
                logger.error(f"Error getting circuit breaker states: {e}")

        # Incident data
        if self.incident_manager:
            try:
                snapshot.incidents = await self._get_incident_metrics()
            except Exception as e:
                logger.error(f"Error getting incident metrics: {e}")

        # Healing action data
        if self.healing_engine:
            try:
                snapshot.healing_actions = await self._get_healing_metrics()
            except Exception as e:
                logger.error(f"Error getting healing metrics: {e}")

        # Rollback data
        if self.rollback_coordinator:
            try:
                snapshot.rollbacks = await self._get_rollback_metrics()
            except Exception as e:
                logger.error(f"Error getting rollback metrics: {e}")

        # System health
        snapshot.system_health = {
            "status": "healthy",
            "uptime_seconds": 0,  # Would track actual uptime
            "version": "1.0.0",
            "websocket_clients": len(self._clients),
        }

        return snapshot

    async def _get_incident_metrics(self) -> dict[str, Any]:
        """Get incident metrics from incident manager.

        Returns:
            Dictionary with incident counts and status
        """
        if not self.incident_manager:
            return {}

        # Get incident statistics
        # This would integrate with the actual incident manager
        return {
            "total": 0,
            "open": 0,
            "by_severity": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "recent": [],
        }

    async def _get_healing_metrics(self) -> dict[str, Any]:
        """Get healing metrics from self-healing engine.

        Returns:
            Dictionary with healing action statistics
        """
        if not self.healing_engine:
            return {}

        return {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "pending_approval": 0,
            "success_rate": 0.0,
        }

    async def _get_rollback_metrics(self) -> dict[str, Any]:
        """Get rollback metrics from rollback coordinator.

        Returns:
            Dictionary with rollback statistics
        """
        if not self.rollback_coordinator:
            return {}

        return {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "in_progress": 0,
            "success_rate": 0.0,
        }

    def get_poll_state(self) -> dict[str, Any]:
        """Get current state for HTTP polling fallback.

        Returns:
            State dictionary for JSON response
        """
        # Run async get_current_state in sync context
        try:
            loop = asyncio.get_event_loop()
            state = loop.run_until_complete(self._get_current_state())
            return state.to_dict()
        except Exception as e:
            logger.error(f"Error getting poll state: {e}")
            return {"error": str(e), "timestamp": asyncio.get_event_loop().time()}


class DashboardSyncClient:
    """Client for connecting to dashboard sync server.

    Used by dashboard frontends to receive real-time updates.

    Example:
        >>> client = DashboardSyncClient("ws://localhost:8765/acp-dashboard")
        >>> await client.connect()
        >>> async for state in client.updates():
        ...     print(f"Open incidents: {state['incidents']['open']}")
    """

    def __init__(self, uri: str):
        """Initialize client.

        Args:
            uri: WebSocket URI of the sync server
        """
        self.uri = uri
        self._websocket: WebSocketServerProtocol | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to the sync server."""
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets package not available")

        self._websocket = await websockets.connect(self.uri)
        self._connected = True
        logger.info(f"Connected to dashboard sync server at {self.uri}")

    async def disconnect(self) -> None:
        """Disconnect from the sync server."""
        if self._websocket:
            await self._websocket.close()
            self._connected = False
            logger.info("Disconnected from dashboard sync server")

    async def updates(self):
        """Async generator for state updates.

        Yields:
            State dictionary on each update
        """
        if not self._connected or not self._websocket:
            raise RuntimeError("Not connected")

        async for message in self._websocket:
            try:
                yield json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {message}")

    async def request_refresh(self) -> None:
        """Request an immediate state refresh."""
        if self._connected and self._websocket:
            await self._websocket.send(json.dumps({"type": "refresh"}))


# Singleton instance for global access
_sync_server: DashboardSyncServer | None = None


def get_sync_server() -> DashboardSyncServer | None:
    """Get the global sync server instance.

    Returns:
        DashboardSyncServer instance or None if not initialized
    """
    return _sync_server


def set_sync_server(server: DashboardSyncServer) -> None:
    """Set the global sync server instance.

    Args:
        server: DashboardSyncServer instance
    """
    global _sync_server
    _sync_server = server
