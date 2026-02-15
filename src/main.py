"""Main FastAPI application for ChiseAI API.

Provides the main FastAPI application with mounted routers for various
API endpoints including ECE (Expected Calibration Error) queries.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.ece_router import router as ece_router

# Create FastAPI application
app = FastAPI(
    title="ChiseAI API",
    description="API for ChiseAI trading strategy platform",
    version="1.0.0",
)

# Mount ECE router at /api/v1/ece
app.include_router(ece_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        dict with status "ok" when the API is healthy
    """
    return {"status": "ok"}
