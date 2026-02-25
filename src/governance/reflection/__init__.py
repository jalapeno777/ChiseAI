"""
Reflection module initialization.
"""

from .artifacts import (
    AutomationTarget,
    FailureObservation,
    FailureType,
    KPISnapshot,
    Priority,
    PromotionCandidate,
    ReflectionArtifact,
    ReflectionType,
    ReflectionValidator,
    RootCause,
    RootCauseCategory,
    Severity,
    create_reflection_artifact,
)
from .loops import ReflectionLoops, ReflectionStorage

__all__ = [
    # Artifacts
    "AutomationTarget",
    "FailureObservation",
    "FailureType",
    "KPISnapshot",
    "Priority",
    "PromotionCandidate",
    "ReflectionArtifact",
    "ReflectionType",
    "ReflectionValidator",
    "RootCause",
    "RootCauseCategory",
    "Severity",
    "create_reflection_artifact",
    # Loops
    "ReflectionLoops",
    "ReflectionStorage",
]
