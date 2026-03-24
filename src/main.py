"""Main FastAPI application for ChiseAI API.

Provides the main FastAPI application with mounted routers for various
API endpoints including ECE (Expected Calibration Error) queries.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.ece_router import router as ece_router
from src.api.health_router import router as health_router
from src.api.health_router import set_health_monitor
from src.api.paper_router import router as paper_router
from src.autonomous_control_plane.api.v1.circuit_breakers import (
    router as circuit_breakers_router,
)
from src.autonomous_control_plane.api.v1.circuit_breakers import (
    set_registry as set_circuit_breaker_registry,
)
from src.autonomous_control_plane.api.v1.healing import router as healing_router

# ACP (Autonomous Control Plane) routes - EP-NS-008
from src.autonomous_control_plane.api.v1.incidents import router as incidents_router
from src.autonomous_control_plane.api.v1.retry import (
    router as retry_router,
)
from src.autonomous_control_plane.api.v1.retry import (
    set_retry_coordinator,
)
from src.autonomous_control_plane.api.v1.rollback import (
    router as rollback_router,
)
from src.autonomous_control_plane.api.v1.rollback import (
    set_coordinator as set_rollback_coordinator,
)

# ACP startup and dependency verification - PM-BATCH-1
from src.autonomous_control_plane.startup import (
    create_acp_container,
    get_acp_container,
)
from src.health.monitor import HealthMonitor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles ACP container initialization and dependency verification.
    Fails closed if critical dependencies are unavailable.
    """
    logger.info("Starting ChiseAI API...")

    try:
        # Create and initialize ACP container
        # This will verify Redis and InfluxDB connectivity
        container = create_acp_container()
        await container.startup()

        # Verify container is properly initialized
        _ = get_acp_container()
        logger.info("ACP container initialized successfully")

        # Inject coordinators into API routers
        logger.info("Injecting coordinators into API routers...")
        set_circuit_breaker_registry(container.circuit_breaker_registry)
        set_retry_coordinator(container.retry_coordinator)
        set_rollback_coordinator(container.rollback_coordinator)
        logger.info("Coordinators injected successfully")

        # Create and register HealthMonitor
        logger.info("Initializing HealthMonitor...")
        health_monitor = HealthMonitor(
            redis_client=container._redis_client,
            influxdb_client=container._influx_client,
        )
        set_health_monitor(health_monitor)

        # Start health monitoring
        await health_monitor.start()
        logger.info("HealthMonitor started successfully")

    except RuntimeError as e:
        # Dependency verification failed - log critical error and re-raise
        logger.critical(f"Failed to start API: {e}")
        raise
    except Exception as e:
        # Unexpected error during startup
        logger.critical(f"Unexpected error during API startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down ChiseAI API...")


# Create FastAPI application with lifespan
app = FastAPI(
    title="ChiseAI API",
    description="API for ChiseAI trading strategy platform with Autonomous Control Plane",
    version="1.1.0",
    lifespan=lifespan,
)

# Mount routers
app.include_router(ece_router)
app.include_router(health_router)
app.include_router(paper_router)

# Mount ACP routers - EP-NS-008
# Note: healing, incidents, and retry routers already have /api/v1 prefix in their definitions
app.include_router(circuit_breakers_router, prefix="/api/v1")
app.include_router(incidents_router)
app.include_router(healing_router)
app.include_router(retry_router)
app.include_router(rollback_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        dict with status "ok" when the API is healthy
    """
    return {"status": "ok"}
