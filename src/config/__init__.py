"""Configuration module for ChiseAI.

Provides centralized configuration loading and environment variable management.
"""

from src.config.bootstrap import bootstrap as bootstrap_environment
from src.config.bootstrap import get_bootstrap_state

__all__ = [
    "bootstrap_environment",
    "get_bootstrap_state",
]
