"""API module for ChiseAI.

Provides REST API endpoints for querying ECE metrics and other data.
"""

from api.ece_router import router as ece_router

__all__ = ["ece_router"]
