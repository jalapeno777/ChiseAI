"""Model rollback module for ChiseAI.

Provides automatic rollback on validation failure.
"""

from ml.rollback.automatic import (
    RollbackConfig as AutoRollbackConfig,
    RollbackManager as AutoRollbackManager,
    RollbackReason,
    RollbackResult,
    RollbackState,
)
from ml.rollback.model_rollback import (
    AuditStorage,
    DegradationAlert,
    DegradationMonitor,
    DiscordNotifier,
    InMemoryAuditStorage,
    Notifier,
    RollbackConfig,
    RollbackEvent,
    RollbackManager,
    RollbackStatus,
    RollbackTrigger,
    ValidationHistoryAPI,
)

__all__ = [
    # From automatic.py
    "AutoRollbackConfig",
    "AutoRollbackManager",
    "RollbackReason",
    "RollbackResult",
    "RollbackState",
    # From model_rollback.py
    "AuditStorage",
    "DegradationAlert",
    "DegradationMonitor",
    "DiscordNotifier",
    "InMemoryAuditStorage",
    "Notifier",
    "RollbackConfig",
    "RollbackEvent",
    "RollbackManager",
    "RollbackStatus",
    "RollbackTrigger",
    "ValidationHistoryAPI",
]
