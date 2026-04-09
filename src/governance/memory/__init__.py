"""
Memory governance module.

Provides tools for memory management, deduplication, and optimization.
"""

from .deduplication import MemoryDeduplicationEngine
from .observer import Observer
from .reflector_agent import Reflector, SupersededObservation

__all__ = [
    "MemoryDeduplicationEngine",
    "Observer",
    "Reflector",
    "SupersededObservation",
]
