"""Outcome database store for signal outcome persistence and querying.

This module provides a SQLite-backed outcome store with full CRUD operations
and query capabilities for historical analysis of trade outcomes.

For ST-ICT-P1: Signal Outcome Database Backend
"""

from execution.outcomes.store import OutcomeStore

__all__ = ["OutcomeStore"]
