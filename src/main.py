"""Main FastAPI application for ChiseAI API.

Provides the main FastAPI application with mounted routers for various
API endpoints including ECE (Expected Calibration Error) queries.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.ece_router import router as ece_router
from api.health_router import router as health_router
from autonomous_control_plane.startup import (
    create_acp_container,
    get_acp_container,
)

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
    description="API for ChiseAI trading strategy platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount routers
app.include_router(ece_router)
app.include_router(health_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        dict with status "ok" when the API is healthy
    """
    return {"status": "ok"}
