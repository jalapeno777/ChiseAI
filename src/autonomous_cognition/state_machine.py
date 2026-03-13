"""State machine for autonomous cognition cycle execution."""

from __future__ import annotations

from enum import Enum


class CycleState(str, Enum):
    """Allowed states for cycle execution."""

    IDLE = "idle"
    SELF_ASSESSING = "self_assessing"
    BELIEF_CHECK = "belief_check"
    IMPROVEMENT = "improvement"
    RUNTIME_INTEGRATION = "runtime_integration"
    TUNING = "tuning"
    GOVERNANCE_AUDIT = "governance_audit"
    COMPLETED = "completed"
    FAILED = "failed"


class AutonomousCycleStateMachine:
    """Simple transition validator for autonomous cycle states."""

    _allowed: dict[CycleState, set[CycleState]] = {
        CycleState.IDLE: {CycleState.SELF_ASSESSING},
        CycleState.SELF_ASSESSING: {CycleState.BELIEF_CHECK, CycleState.FAILED},
        CycleState.BELIEF_CHECK: {CycleState.IMPROVEMENT, CycleState.FAILED},
        CycleState.IMPROVEMENT: {CycleState.RUNTIME_INTEGRATION, CycleState.FAILED},
        CycleState.RUNTIME_INTEGRATION: {CycleState.TUNING, CycleState.FAILED},
        CycleState.TUNING: {CycleState.GOVERNANCE_AUDIT, CycleState.FAILED},
        CycleState.GOVERNANCE_AUDIT: {CycleState.COMPLETED, CycleState.FAILED},
        CycleState.COMPLETED: set(),
        CycleState.FAILED: set(),
    }

    def __init__(self) -> None:
        self.state = CycleState.IDLE

    def transition(self, new_state: CycleState) -> None:
        """Transition to a new state or raise if invalid."""
        if new_state not in self._allowed[self.state]:
            raise ValueError(f"Invalid transition: {self.state} -> {new_state}")
        self.state = new_state

