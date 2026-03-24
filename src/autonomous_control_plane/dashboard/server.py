"""Dashboard server - FastAPI-based dashboard server.

Provides REST API and WebSocket endpoints for the control plane dashboard
with static file serving and authentication hooks.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from autonomous_control_plane.dashboard.api import DashboardAPI
from autonomous_control_plane.telemetry.dashboard_sync import (
    DashboardSyncServer,
)

logger = logging.getLogger(__name__)

# Optional FastAPI support
try:
    from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class DashboardServer:
    """Dashboard server with REST API and WebSocket support.

    Provides:
    - REST API for dashboard data queries
    - WebSocket endpoint for real-time updates
    - Static file serving for dashboard UI
    - Authentication/authorization hooks

    Example:
        >>> server = DashboardServer(
        ...     circuit_breaker_registry=cb_registry,
        ...     incident_manager=incident_manager,
        ...     automation_controller=controller,
        ... )
        >>> await server.start()
        >>> # Access at http://localhost:8080
        >>> await server.stop()
    """

    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 8080
    DEFAULT_WS_PORT = 8765

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        ws_port: int = DEFAULT_WS_PORT,
        static_dir: str | None = None,
        enable_auth: bool = False,
        circuit_breaker_registry: Any | None = None,
        incident_manager: Any | None = None,
        self_healing_engine: Any | None = None,
        rollback_coordinator: Any | None = None,
        automation_controller: Any | None = None,
    ):
        """Initialize dashboard server.

        Args:
            host: Host to bind server
            port: HTTP port
            ws_port: WebSocket port
            static_dir: Directory for static files
            enable_auth: Enable authentication
            circuit_breaker_registry: Circuit breaker registry
            incident_manager: Incident manager
            self_healing_engine: Self-healing engine
            rollback_coordinator: Rollback coordinator
            automation_controller: Automation controller
        """
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self.static_dir = static_dir
        self.enable_auth = enable_auth

        # Initialize API
        self._api = DashboardAPI(
            circuit_breaker_registry=circuit_breaker_registry,
            incident_manager=incident_manager,
            self_healing_engine=self_healing_engine,
            rollback_coordinator=rollback_coordinator,
            automation_controller=automation_controller,
        )

        # Initialize WebSocket sync server
        self._ws_server = DashboardSyncServer(
            host=host,
            port=ws_port,
            circuit_breaker_registry=circuit_breaker_registry,
            incident_manager=incident_manager,
            healing_engine=self_healing_engine,
            rollback_coordinator=rollback_coordinator,
        )

        # FastAPI app
        self._app: FastAPI | None = None
        self._server_task: asyncio.Task | None = None
        self._running = False

        if not HAS_FASTAPI:
            logger.warning("FastAPI not available, dashboard server will not function")

    def _create_app(self) -> FastAPI:
        """Create FastAPI application."""
        if not HAS_FASTAPI:
            raise RuntimeError("FastAPI not available")

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Lifespan context manager."""
            # Startup
            logger.info("Dashboard server starting up")
            await self._ws_server.start()
            yield
            # Shutdown
            logger.info("Dashboard server shutting down")
            await self._ws_server.stop()

        app = FastAPI(
            title="ChiseAI Control Plane Dashboard",
            description="Real-time dashboard for autonomous control plane",
            version="1.0.0",
            lifespan=lifespan,
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # API routes
        self._setup_routes(app)

        # Static files
        if self.static_dir and Path(self.static_dir).exists():
            app.mount(
                "/", StaticFiles(directory=self.static_dir, html=True), name="static"
            )

        return app

    def _setup_routes(self, app: FastAPI) -> None:
        """Setup API routes."""

        @app.get("/api/v1/dashboard/health")
        async def health() -> dict[str, Any]:
            """Get API health status."""
            return await self._api.get_health()

        @app.get("/api/v1/dashboard/state")
        async def get_state() -> dict[str, Any]:
            """Get complete dashboard state."""
            state = await self._api.get_full_state()
            return state.to_dict()

        @app.get("/api/v1/dashboard/panels/circuit-breakers")
        async def get_circuit_breakers(
            group: str | None = Query(None, description="Filter by group"),
        ) -> dict[str, Any]:
            """Get circuit breaker panel data."""
            data = await self._api.get_circuit_breakers_panel(group=group)
            return data.to_dict()

        @app.get("/api/v1/dashboard/panels/incidents")
        async def get_incidents(
            status: str | None = Query(None, description="Filter by status"),
            severity: str | None = Query(
                None, description="Filter by severity (P0-P3)"
            ),
            limit: int = Query(50, ge=1, le=1000),
        ) -> dict[str, Any]:
            """Get incident panel data."""
            data = await self._api.get_incidents_panel(
                status=status, severity=severity, limit=limit
            )
            return data.to_dict()

        @app.get("/api/v1/dashboard/panels/self-healing")
        async def get_self_healing() -> dict[str, Any]:
            """Get self-healing panel data."""
            data = await self._api.get_self_healing_panel()
            return data.to_dict()

        @app.get("/api/v1/dashboard/panels/rollbacks")
        async def get_rollbacks() -> dict[str, Any]:
            """Get rollback panel data."""
            data = await self._api.get_rollbacks_panel()
            return data.to_dict()

        @app.get("/api/v1/dashboard/panels/system-health")
        async def get_system_health() -> dict[str, Any]:
            """Get system health panel data."""
            data = await self._api.get_system_health_panel()
            return data.to_dict()

        @app.get("/api/v1/dashboard/charts/incident-trend")
        async def get_incident_trend(
            hours: int = Query(24, ge=1, le=168),
            resolution: str = Query("hour", regex="^(hour|day)$"),
        ) -> dict[str, Any]:
            """Get incident trend chart data."""
            from autonomous_control_plane.dashboard.visualization import (
                DashboardVisualization,
            )

            viz = DashboardVisualization(
                incident_manager=self._api._incident_manager,
            )
            chart = await viz.generate_incident_trend_chart(
                hours=hours, resolution=resolution
            )
            return chart.to_dict()

        @app.get("/api/v1/dashboard/charts/health-gauge")
        async def get_health_gauge() -> dict[str, Any]:
            """Get health gauge chart data."""
            from autonomous_control_plane.dashboard.visualization import (
                DashboardVisualization,
            )

            viz = DashboardVisualization(
                circuit_breaker_registry=self._api._cb_registry,
                incident_manager=self._api._incident_manager,
                automation_controller=self._api._automation_controller,
            )
            chart = await viz.generate_health_gauge()
            return chart.to_dict()

        @app.get("/api/v1/dashboard/charts/cb-status")
        async def get_cb_status_chart() -> dict[str, Any]:
            """Get circuit breaker status chart."""
            from autonomous_control_plane.dashboard.visualization import (
                DashboardVisualization,
            )

            viz = DashboardVisualization(
                circuit_breaker_registry=self._api._cb_registry,
            )
            chart = await viz.generate_circuit_breaker_status_chart()
            return chart.to_dict()

        @app.get("/api/v1/dashboard/charts/severity-distribution")
        async def get_severity_chart() -> dict[str, Any]:
            """Get incident severity distribution chart."""
            from autonomous_control_plane.dashboard.visualization import (
                DashboardVisualization,
            )

            viz = DashboardVisualization(
                incident_manager=self._api._incident_manager,
            )
            chart = await viz.generate_severity_distribution_chart()
            return chart.to_dict()

        @app.post("/api/v1/dashboard/incidents/{incident_id}/acknowledge")
        async def acknowledge_incident(
            incident_id: str,
            request: dict[str, Any],
        ) -> dict[str, Any]:
            """Acknowledge an incident."""
            acknowledged_by = request.get("acknowledged_by", "dashboard")
            result = await self._api.acknowledge_incident(incident_id, acknowledged_by)
            if result is None:
                raise HTTPException(status_code=404, detail="Incident not found")
            return result

        @app.post("/api/v1/dashboard/rollbacks/trigger")
        async def trigger_rollback(
            request: dict[str, Any],
        ) -> dict[str, Any]:
            """Trigger a rollback."""
            service = request.get("service")
            reason = request.get("reason", "Manual trigger from dashboard")
            triggered_by = request.get("triggered_by", "dashboard")

            if not service:
                raise HTTPException(status_code=400, detail="Service is required")

            result = await self._api.trigger_rollback(service, reason, triggered_by)
            if result is None:
                raise HTTPException(
                    status_code=500, detail="Failed to trigger rollback"
                )
            return result

        @app.get("/api/v1/dashboard/incidents/search")
        async def search_incidents(
            q: str = Query(..., description="Search query"),
            status: str | None = Query(None),
            severity: str | None = Query(None),
            limit: int = Query(50, ge=1, le=1000),
        ) -> dict[str, Any]:
            """Search incidents."""
            results = await self._api.search_incidents(
                query=q, status=status, severity=severity, limit=limit
            )
            return {"results": results, "count": len(results)}

        @app.websocket("/api/v1/dashboard/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            logger.info(f"WebSocket client connected from {websocket.client}")

            try:
                # Send initial state
                state = await self._api.get_full_state()
                await websocket.send_json(state.to_dict())

                # Send updates every 5 seconds
                while True:
                    await asyncio.sleep(5.0)
                    state = await self._api.get_full_state()
                    await websocket.send_json(state.to_dict())

            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected: {websocket.client}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

    async def start(self) -> None:
        """Start the dashboard server."""
        if not HAS_FASTAPI:
            raise RuntimeError("FastAPI not available")

        if self._running:
            logger.warning("Dashboard server already running")
            return

        self._running = True

        # Create app
        self._app = self._create_app()

        # Start server
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        self._server_task = asyncio.create_task(server.serve())

        logger.info(f"Dashboard server started on http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the dashboard server."""
        if not self._running:
            return

        self._running = False

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        # WebSocket server is stopped by lifespan

        logger.info("Dashboard server stopped")

    def get_app(self) -> FastAPI | None:
        """Get the FastAPI app (for testing or mounting).

        Returns:
            FastAPI application or None if not created
        """
        if self._app is None and HAS_FASTAPI:
            self._app = self._create_app()
        return self._app
