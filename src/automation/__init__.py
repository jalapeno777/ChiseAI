"""Self-healing automation system for ChiseAI.

Provides event-driven recovery orchestration, self-healing capabilities,
and automated recovery actions for system resilience.

Components:
- RecoveryOrchestrator: Manages recovery workflows
- SelfHealingEngine: Executes healing actions
- EventHandlers: Process health events and trigger recoveries
"""

from __future__ import annotations

from .event_handlers import (
    EventHandler,
    EventType,
    HealthEvent,
    OnHealthCritical,
    OnHealthWarning,
    OnRecoveryFailure,
    OnRecoverySuccess,
)
from .recovery_orchestrator import (
    HealthLevel,
    RecoveryAttempt,
    RecoveryContext,
    RecoveryOrchestrator,
    RecoveryResult,
    RecoveryState,
    RecoveryType,
)
from .self_healing_engine import (
    DeploymentHealth,
    HealingAction,
    HealingStatus,
    SelfHealingEngine,
    SelfHealingResult,
)

__all__ = [
    # Recovery orchestration
    "RecoveryOrchestrator",
    "RecoveryAttempt",
    "RecoveryContext",
    "RecoveryResult",
    "RecoveryState",
    "RecoveryType",
    "HealthLevel",
    # Self-healing
    "SelfHealingEngine",
    "HealingAction",
    "HealingStatus",
    "SelfHealingResult",
    "DeploymentHealth",
    # Event handling
    "EventHandler",
    "EventType",
    "HealthEvent",
    "OnHealthCritical",
    "OnHealthWarning",
    "OnRecoverySuccess",
    "OnRecoveryFailure",
]
