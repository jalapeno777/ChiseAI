"""Improvement cycle orchestration for autonomous cognition.

This module provides the ImprovementCycleOrchestrator which manages phase-based
improvement cycles with checkpoint and rollback support.

Phases: IDLE -> ASSESSING -> PROPOSING -> VALIDATING -> APPLYING -> VERIFYING -> COMPLETED/FAILED/ROLLED_BACK
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ImprovementPhase(str, Enum):
    """Phases of an improvement cycle."""

    IDLE = "idle"
    ASSESSING = "assessing"
    PROPOSING = "proposing"
    VALIDATING = "validating"
    APPLYING = "applying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# Allowed transitions
_ALLOWED_TRANSITIONS: dict[ImprovementPhase, set[ImprovementPhase]] = {
    ImprovementPhase.IDLE: {ImprovementPhase.ASSESSING},
    ImprovementPhase.ASSESSING: {ImprovementPhase.PROPOSING, ImprovementPhase.FAILED},
    ImprovementPhase.PROPOSING: {ImprovementPhase.VALIDATING, ImprovementPhase.FAILED},
    ImprovementPhase.VALIDATING: {ImprovementPhase.APPLYING, ImprovementPhase.FAILED},
    ImprovementPhase.APPLYING: {
        ImprovementPhase.VERIFYING,
        ImprovementPhase.FAILED,
        ImprovementPhase.ROLLED_BACK,
    },
    ImprovementPhase.VERIFYING: {
        ImprovementPhase.COMPLETED,
        ImprovementPhase.FAILED,
        ImprovementPhase.ROLLED_BACK,
    },
    ImprovementPhase.COMPLETED: set(),
    ImprovementPhase.FAILED: set(),
    ImprovementPhase.ROLLED_BACK: set(),
}


@dataclass
class ImprovementProposal:
    """A proposal for improvement generated during the PROPOSING phase.

    Attributes:
        proposal_id: Unique identifier
        description: Human-readable description
        files: List of files to modify
        risk_level: Risk assessment (low/medium/high/critical)
        changes: Dict mapping file -> description of changes
        line_counts: Dict mapping file -> number of lines changed
        metadata: Additional context
    """

    proposal_id: str
    description: str
    files: list[str] = field(default_factory=list)
    risk_level: str = "low"
    changes: dict[str, str] = field(default_factory=dict)
    line_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "description": self.description,
            "files": self.files,
            "risk_level": self.risk_level,
            "changes": self.changes,
            "line_counts": self.line_counts,
            "metadata": self.metadata,
        }


@dataclass
class CycleCheckpoint:
    """A checkpoint saved at each phase boundary for resume capability.

    Attributes:
        checkpoint_id: Unique identifier
        phase: Phase at checkpoint
        timestamp: When checkpoint was created
        state: Captured state data
        proposal: The active proposal (if any)
    """

    checkpoint_id: str
    phase: ImprovementPhase
    timestamp: float
    state: dict[str, Any] = field(default_factory=dict)
    proposal: ImprovementProposal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "phase": self.phase.value,
            "timestamp": self.timestamp,
            "state": self.state,
            "proposal": self.proposal.to_dict() if self.proposal else None,
        }


@dataclass
class ImprovementCycleResult:
    """Result of a complete improvement cycle.

    Attributes:
        cycle_id: Unique identifier for this cycle
        started_at: When the cycle started
        completed_at: When the cycle completed
        final_phase: The final phase reached
        proposal: The proposal that was processed
        checkpoints: List of checkpoints taken
        error: Error message if failed
        metrics: Performance metrics
    """

    cycle_id: str
    started_at: str
    completed_at: str = ""
    final_phase: ImprovementPhase = ImprovementPhase.IDLE
    proposal: ImprovementProposal | None = None
    checkpoints: list[CycleCheckpoint] = field(default_factory=list)
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "final_phase": self.final_phase.value,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "error": self.error,
            "metrics": self.metrics,
        }

    @classmethod
    def create(cls, cycle_id: str | None = None) -> ImprovementCycleResult:
        """Create a new cycle result."""
        now = datetime.now(UTC).isoformat()
        return cls(
            cycle_id=cycle_id or str(uuid.uuid4()),
            started_at=now,
        )


class ImprovementCycleOrchestrator:
    """Orchestrates phase-based improvement cycles.

    Manages the lifecycle of improvement cycles through phases:
    IDLE -> ASSESSING -> PROPOSING -> VALIDATING -> APPLYING -> VERIFYING -> COMPLETED

    Supports:
    - Phase transition validation
    - Checkpoint creation at phase boundaries
    - Rollback to previous checkpoints
    - Emergency stop integration

    Example:
        >>> orchestrator = ImprovementCycleOrchestrator()
        >>> result = orchestrator.start_cycle()
        >>> orchestrator.assess(lambda: {"score": 0.8})
        >>> orchestrator.propose(ImprovementProposal(...))
        >>> # ... continue through phases
    """

    def __init__(self, boundary_enforcer: Any | None = None):
        """Initialize the orchestrator.

        Args:
            boundary_enforcer: Optional BoundaryEnforcer for safety checks
        """
        self._boundary_enforcer = boundary_enforcer
        self._phase = ImprovementPhase.IDLE
        self._cycle_result: ImprovementCycleResult | None = None
        self._checkpoints: list[CycleCheckpoint] = []
        self._proposal: ImprovementProposal | None = None
        self._emergency_stop = False

    @property
    def current_phase(self) -> ImprovementPhase:
        """Current phase of the cycle."""
        return self._phase

    @property
    def is_active(self) -> bool:
        """Whether a cycle is currently active."""
        return self._phase not in (
            ImprovementPhase.IDLE,
            ImprovementPhase.COMPLETED,
            ImprovementPhase.FAILED,
            ImprovementPhase.ROLLED_BACK,
        )

    @property
    def proposal(self) -> ImprovementProposal | None:
        """Current active proposal."""
        return self._proposal

    def start_cycle(self, cycle_id: str | None = None) -> ImprovementCycleResult:
        """Start a new improvement cycle.

        Args:
            cycle_id: Optional cycle ID (auto-generated if not provided)

        Returns:
            The cycle result (will be populated as phases complete)

        Raises:
            ValueError: If a cycle is already active
        """
        if self.is_active:
            raise ValueError(f"Cycle already active in phase {self._phase.value}")

        self._cycle_result = ImprovementCycleResult.create(cycle_id)
        self._checkpoints = []
        self._proposal = None
        self._emergency_stop = False
        self._transition(ImprovementPhase.ASSESSING)
        self._create_checkpoint("cycle_started")

        logger.info("Improvement cycle started: %s", self._cycle_result.cycle_id)
        return self._cycle_result

    def assess(self, assessment_fn: Any | None = None) -> dict[str, Any]:
        """Run the assessment phase.

        Args:
            assessment_fn: Optional callable that returns assessment data

        Returns:
            Assessment results

        Raises:
            ValueError: If not in ASSESSING phase
        """
        self._check_emergency_stop()
        self._require_phase(ImprovementPhase.ASSESSING)

        assessment = {}
        if assessment_fn:
            assessment = assessment_fn()

        self._create_checkpoint("assessment_complete", {"assessment": assessment})
        self._transition(ImprovementPhase.PROPOSING)

        logger.info("Assessment complete: %s", assessment)
        return assessment

    def propose(self, proposal: ImprovementProposal) -> ImprovementProposal:
        """Submit a proposal during the PROPOSING phase.

        Args:
            proposal: The improvement proposal

        Returns:
            The validated proposal

        Raises:
            ValueError: If not in PROPOSING phase or proposal blocked
        """
        self._check_emergency_stop()
        self._require_phase(ImprovementPhase.PROPOSING)

        # Check boundaries if enforcer available
        if self._boundary_enforcer:
            violations = self._boundary_enforcer.check_proposal(
                {
                    "files": proposal.files,
                    "risk_level": proposal.risk_level,
                    "changes": {
                        f: proposal.line_counts.get(f, 0) for f in proposal.files
                    },
                }
            )
            if violations:
                blocked = [v for v in violations if v.blocked]
                if blocked:
                    raise ValueError(
                        f"Proposal blocked by boundaries: "
                        f"{[v.description for v in blocked]}"
                    )

        self._proposal = proposal
        self._create_checkpoint("proposal_accepted", {"proposal": proposal.to_dict()})
        self._transition(ImprovementPhase.VALIDATING)

        logger.info("Proposal accepted: %s", proposal.proposal_id)
        return proposal

    def validate(self, validation_fn: Any | None = None) -> bool:
        """Run the validation phase.

        Args:
            validation_fn: Optional callable that returns True if valid

        Returns:
            True if validation passed

        Raises:
            ValueError: If not in VALIDATING phase
        """
        self._check_emergency_stop()
        self._require_phase(ImprovementPhase.VALIDATING)

        is_valid = True
        if validation_fn:
            is_valid = validation_fn()

        if not is_valid:
            self._fail("Validation failed")
            return False

        self._create_checkpoint("validation_passed")
        self._transition(ImprovementPhase.APPLYING)

        logger.info(
            "Validation passed for proposal: %s",
            self._proposal.proposal_id if self._proposal else "none",
        )
        return True

    def apply(self, apply_fn: Any | None = None) -> bool:
        """Run the applying phase.

        Args:
            apply_fn: Optional callable that applies changes, returns True on success

        Returns:
            True if apply succeeded

        Raises:
            ValueError: If not in APPLYING phase
        """
        self._check_emergency_stop()
        self._require_phase(ImprovementPhase.APPLYING)

        self._create_checkpoint("pre_apply")

        success = True
        if apply_fn:
            try:
                success = apply_fn()
            except Exception as e:
                logger.error("Apply failed: %s", e)
                self._rollback(f"Apply exception: {e}")
                return False

        if not success:
            self._rollback("Apply returned False")
            return False

        self._create_checkpoint("apply_complete")
        self._transition(ImprovementPhase.VERIFYING)

        logger.info("Apply complete")
        return True

    def verify(self, verify_fn: Any | None = None) -> bool:
        """Run the verification phase.

        Args:
            verify_fn: Optional callable that verifies changes, returns True on success

        Returns:
            True if verification passed

        Raises:
            ValueError: If not in VERIFYING phase
        """
        self._check_emergency_stop()
        self._require_phase(ImprovementPhase.VERIFYING)

        is_verified = True
        if verify_fn:
            is_verified = verify_fn()

        if not is_verified:
            self._rollback("Verification failed")
            return False

        self._complete()
        return True

    def rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Roll back to a specific checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint to roll back to

        Returns:
            True if rollback succeeded
        """
        checkpoint = None
        for cp in self._checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break

        if not checkpoint:
            logger.error("Checkpoint not found: %s", checkpoint_id)
            return False

        # Restore state
        self._phase = checkpoint.phase
        self._proposal = checkpoint.proposal

        # Remove checkpoints after the target
        idx = self._checkpoints.index(checkpoint)
        self._checkpoints = self._checkpoints[: idx + 1]

        logger.info(
            "Rolled back to checkpoint: %s (phase: %s)",
            checkpoint_id,
            checkpoint.phase.value,
        )
        return True

    def activate_emergency_stop(self, reason: str = "") -> None:
        """Activate emergency stop."""
        self._emergency_stop = True
        if self.is_active:
            self._fail(f"Emergency stop: {reason}")
        logger.warning("Emergency stop activated: %s", reason)

    def get_checkpoints(self) -> list[CycleCheckpoint]:
        """Get all checkpoints for the current cycle."""
        return list(self._checkpoints)

    def _transition(self, new_phase: ImprovementPhase) -> None:
        """Transition to a new phase with validation."""
        allowed = _ALLOWED_TRANSITIONS.get(self._phase, set())
        if new_phase not in allowed:
            raise ValueError(
                f"Invalid transition: {self._phase.value} -> {new_phase.value}"
            )
        self._phase = new_phase

    def _require_phase(self, expected: ImprovementPhase) -> None:
        """Raise if not in expected phase."""
        if self._phase != expected:
            raise ValueError(
                f"Expected phase {expected.value}, got {self._phase.value}"
            )

    def _check_emergency_stop(self) -> None:
        """Check emergency stop and fail if active."""
        if self._emergency_stop:
            raise ValueError("Emergency stop is active")

    def _create_checkpoint(
        self, label: str, state: dict[str, Any] | None = None
    ) -> CycleCheckpoint:
        """Create a checkpoint at the current phase."""
        checkpoint = CycleCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            phase=self._phase,
            timestamp=time.time(),
            state=state or {},
            proposal=self._proposal,
        )
        self._checkpoints.append(checkpoint)
        logger.debug("Checkpoint created: %s at %s", label, self._phase.value)
        return checkpoint

    def _fail(self, reason: str) -> None:
        """Mark the cycle as failed."""
        self._transition(ImprovementPhase.FAILED)
        if self._cycle_result:
            self._cycle_result.final_phase = ImprovementPhase.FAILED
            self._cycle_result.error = reason
            self._cycle_result.completed_at = datetime.now(UTC).isoformat()
            self._cycle_result.checkpoints = list(self._checkpoints)
        logger.error("Cycle failed: %s", reason)

    def _rollback(self, reason: str) -> None:
        """Roll back the cycle."""
        self._transition(ImprovementPhase.ROLLED_BACK)
        if self._cycle_result:
            self._cycle_result.final_phase = ImprovementPhase.ROLLED_BACK
            self._cycle_result.error = reason
            self._cycle_result.completed_at = datetime.now(UTC).isoformat()
            self._cycle_result.checkpoints = list(self._checkpoints)
        logger.warning("Cycle rolled back: %s", reason)

    def _complete(self) -> None:
        """Mark the cycle as completed."""
        self._transition(ImprovementPhase.COMPLETED)
        if self._cycle_result:
            self._cycle_result.final_phase = ImprovementPhase.COMPLETED
            self._cycle_result.completed_at = datetime.now(UTC).isoformat()
            self._cycle_result.checkpoints = list(self._checkpoints)
        logger.info(
            "Cycle completed: %s",
            self._cycle_result.cycle_id if self._cycle_result else "unknown",
        )
