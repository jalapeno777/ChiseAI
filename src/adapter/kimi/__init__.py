"""Kimi Adapter package.

Provides OpenAI-compatible FastAPI wrapper for Kimi Coding API.

For ST-KIMI-ADAPTER-001: Kimi Adapter Wiring
"""

from src.adapter.kimi.main import app

__all__ = ["app"]
