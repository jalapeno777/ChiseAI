"""Main FastAPI application for ChiseAI API.

Provides the main FastAPI application with mounted routers for various
API endpoints including ECE (Expected Calibration Error) queries.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.ece_router import router as ece_router
from src.api.health_router import router as health_router

# ACP (Autonomous Control Plane) routes - EP-NS-008
from src.autonomous_control_plane.api.v1.incidents import router as incidents_router
from src.autonomous_control_plane.api.v1.healing import router as healing_router
from src.autonomous_control_plane.api.v1.rollback import router as rollback_router

# Create FastAPI application
app = FastAPI(
    title="ChiseAI API",
    description="API for ChiseAI trading strategy platform with Autonomous Control Plane",
    version="1.1.0",
)

# Mount routers
app.include_router(ece_router)
app.include_router(health_router)

# Mount ACP routers - EP-NS-008
app.include_router(incidents_router)
app.include_router(healing_router)
app.include_router(rollback_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        dict with status "ok" when the API is healthy
    """
    return {"status": "ok"}
