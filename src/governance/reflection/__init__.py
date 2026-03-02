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
from .bottleneck_reflection import (
    BottleneckKPI,
    BottleneckReflectionGenerator,
    DailyReflectionArtifact,
    FrameworkImprovement,
    ImpactScore,
    RemediationAction,
    TrendDelta,
    WeeklyReflectionArtifact,
    create_daily_reflection,
    create_weekly_reflection,
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
    # Bottleneck Reflection
    "BottleneckKPI",
    "BottleneckReflectionGenerator",
    "DailyReflectionArtifact",
    "FrameworkImprovement",
    "ImpactScore",
    "RemediationAction",
    "TrendDelta",
    "WeeklyReflectionArtifact",
    "create_daily_reflection",
    "create_weekly_reflection",
]
