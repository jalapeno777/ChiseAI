"""
Governance module for ChiseAI.

This module provides governance capabilities including:
- Memory deduplication engine
- Audit and compliance utilities
- Retrieval baseline metrics
- Feature flag management
- Task sentinel enforcement utilities
"""

from src.governance.audit import AuditSnapshot, RetrievalBaseline
from src.governance.memory import MemoryDeduplicationEngine
from src.governance.sentinel import SentinelConfig, TaskSentinel

__all__ = [
    "AuditSnapshot",
    "RetrievalBaseline",
    "MemoryDeduplicationEngine",
    "TaskSentinel",
    "SentinelConfig",
]
