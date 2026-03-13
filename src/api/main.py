"""
ChiseAI API Main Application

TEMPO-2026-001: Instrumented with OpenTelemetry tracing
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import tracing from observability module
from src.observability import init_tracing, instrument_fastapi, shutdown_tracing

# Import routers
from src.api.health_router import router as health_router
from src.api.routes import trades_router

# Initialize tracing before creating FastAPI app
tracer = init_tracing("chiseai-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    with tracer.start_as_current_span("api_startup") as span:
        span.set_attribute("chiseai.api.startup", True)
        span.set_attribute("chiseai.service.name", "chiseai-api")

    yield

    # Shutdown
    with tracer.start_as_current_span("api_shutdown") as span:
        span.set_attribute("chiseai.api.shutdown", True)
        shutdown_tracing()


# Create FastAPI application
app = FastAPI(
    title="ChiseAI API",
    description="API for ChiseAI trading platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry
instrument_fastapi(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(trades_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    with tracer.start_as_current_span("health_check") as span:
        span.set_attribute("chiseai.endpoint", "/health")
        span.set_attribute("chiseai.api.version", "1.0.0")
        return {"status": "healthy", "service": "chiseai-api"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    with tracer.start_as_current_span("readiness_check") as span:
        span.set_attribute("chiseai.endpoint", "/ready")
        return {"status": "ready", "service": "chiseai-api"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
