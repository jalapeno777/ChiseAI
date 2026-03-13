"""
ChiseAI API Routes

TEMPO-2026-001: API routes with OpenTelemetry instrumentation
"""

from .trades import router as trades_router

__all__ = ["trades_router"]
