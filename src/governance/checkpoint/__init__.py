"""Governance Checkpoint Automation Module.

This module provides automated checkpoint auditing and governance gate validation
to ensure system health and compliance during trading operations.

Features:
- G1-G8 gate validation (Scheduler, Signals, Data Flow, Kill Switch, Cron, Bybit, Observability, Pipeline)
- Evidence collection and storage in Redis
- Discord notifications for checkpoint results
- State management and history tracking
- Rollback state capture

Story: PAPER-GOVERNANCE-001
Epic: EP-GOV-001
"""

from src.governance.checkpoint.alerts import ActionableZeroAlert, AlertResult
from src.governance.checkpoint.checkpoint import CheckpointManager
from src.governance.checkpoint.evidence import EvidenceCollector
from src.governance.checkpoint.gates import GateChecker
from src.governance.checkpoint.integrity import IntegrityResult, MetricIntegrityChecker
from src.governance.checkpoint.state import StateManager

__all__ = [
    "ActionableZeroAlert",
    "AlertResult",
    "CheckpointManager",
    "GateChecker",
    "EvidenceCollector",
    "IntegrityResult",
    "MetricIntegrityChecker",
    "StateManager",
]
