"""
Memory governance module.

Provides tools for memory management, deduplication, and optimization.
"""

from .deduplication import MemoryDeduplicationEngine
from .observer import Observer

__all__ = ["MemoryDeduplicationEngine", "Observer"]
