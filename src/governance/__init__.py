"""
Governance module for ChiseAI.

This module provides governance capabilities including:
- Memory deduplication engine
- Audit and compliance utilities
- Retrieval baseline metrics
- Feature flag management
"""

from src.governance.audit import AuditSnapshot, RetrievalBaseline
from src.governance.memory import MemoryDeduplicationEngine

__all__ = [
    "AuditSnapshot",
    "RetrievalBaseline",
    "MemoryDeduplicationEngine",
]
