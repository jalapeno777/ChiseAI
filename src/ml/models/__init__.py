"""ML Models module for ChiseAI.

This module provides data models used across the ML pipeline.

Components:
- signal_outcome: Trade outcome models for signal-to-fill matching
- model_registry: Model versioning, storage, and retrieval with metadata

Usage:
    from ml.models import (
        SignalOutcome,
        OutcomeType,
        BybitFillEvent,
        ModelRegistry,
        ModelMetadata,
        ModelVersion,
    )
"""

from __future__ import annotations

# Use relative import to avoid circular import through src.ml prefix
# When src/ is in sys.path, src.ml resolves to ml package, causing cycle
from ml.models.signal_outcome import (
    BybitFillEvent,
    OutcomeMatchResult,
    OutcomeType,
    SignalOutcome,
    SignalOutcomeStatus,
)

from ml.models.model_registry import (
    ModelRegistry,
    ModelRegistryFactory,
    SemanticVersion,
)
from ml.models.model_storage import (
    FilesystemBackend,
    ModelMetadata,
    ModelVersion,
    S3Backend,
    StorageBackend,
)

__all__ = [
    # Signal Outcome
    "SignalOutcome",
    "OutcomeType",
    "SignalOutcomeStatus",
    "BybitFillEvent",
    "OutcomeMatchResult",
    # Registry
    "ModelRegistry",
    "ModelRegistryFactory",
    "SemanticVersion",
    # Storage
    "FilesystemBackend",
    "S3Backend",
    "StorageBackend",
    # Data classes
    "ModelMetadata",
    "ModelVersion",
]
