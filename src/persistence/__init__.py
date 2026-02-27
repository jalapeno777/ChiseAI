"""Persistence module for canonical data storage.

Provides unified persistence layer for signals, orders, fills, and outcomes
with dedicated keys and proper linkage.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

from __future__ import annotations

from persistence.unified import UnifiedPersistence

__all__ = ["UnifiedPersistence"]
