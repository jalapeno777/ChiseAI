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
from .llm_integration import (
    LLMInsightResult,
    LLMCallTelemetry,
    ReflectionLLMIntegration,
    generate_llm_insights,
    summarize_weekly_reflection,
    analyze_bottleneck_root_cause,
    get_llm_telemetry,
    reset_llm_telemetry,
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
    # LLM Integration
    "LLMInsightResult",
    "LLMCallTelemetry",
    "ReflectionLLMIntegration",
    "generate_llm_insights",
    "summarize_weekly_reflection",
    "analyze_bottleneck_root_cause",
    "get_llm_telemetry",
    "reset_llm_telemetry",
]
