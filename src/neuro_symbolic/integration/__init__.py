"""Integration module for neuro-symbolic components.

This module provides the integration layer that connects all neuro-symbolic
components together into a unified system.

Components:
    - ComponentRegistry: Registry of all available components
    - IntegrationLayer: Adapter interfaces and event bus
    - NeuroSymbolicOrchestrator: Central orchestration (in orchestrator package)
"""

from src.neuro_symbolic.integration.adapters import (
    AdaptiveLearningAdapter,
    ExplainabilityAdapter,
    FusionAdapter,
    HybridReasoningAdapter,
    KnowledgeGraphAdapter,
    PatternRecognitionAdapter,
)
from src.neuro_symbolic.integration.layer import (
    ComponentAdapter,
    DataConverter,
    EventBus,
    EventType,
    IntegrationError,
    IntegrationLayer,
)
from src.neuro_symbolic.integration.registry import (
    ComponentInfo,
    ComponentRegistry,
    ComponentStatus,
    ComponentType,
)

__all__ = [
    # Registry
    "ComponentRegistry",
    "ComponentInfo",
    "ComponentStatus",
    "ComponentType",
    # Integration Layer
    "IntegrationLayer",
    "ComponentAdapter",
    "DataConverter",
    "EventBus",
    "EventType",
    "IntegrationError",
    # Adapters
    "HybridReasoningAdapter",
    "ExplainabilityAdapter",
    "AdaptiveLearningAdapter",
    "KnowledgeGraphAdapter",
    "PatternRecognitionAdapter",
    "FusionAdapter",
]
