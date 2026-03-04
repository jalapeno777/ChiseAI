"""Signal provenance tracking for paper trading.

Provides dataclasses and enums for tracking signal lineage from generation
through execution, with reason codes for all decision points.

For PAPER-2025-002: Signal Provenance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DecisionReason(Enum):
    """Reason codes for execution decisions.

    All accept/reject/skip decisions must have a reason code for
    auditability and debugging. These codes are normalized across
    the provenance tracking system.

    Reasons:
        SIGNAL_ACCEPTED: Signal passed all validation and was accepted
        RISK_REJECTED: Signal rejected due to risk constraints
        LOW_CONFIDENCE: Signal confidence below threshold
        SYMBOL_OCCUPIED: Symbol already has an active position
        KILL_SWITCH_ACTIVE: Kill switch is active, blocking all signals
        MAX_POSITION_LIMIT: Maximum position limit reached
        INVALID_SIGNAL: Signal validation failed (malformed data)
        SYSTEM_ERROR: Internal system error during processing
    """

    SIGNAL_ACCEPTED = "signal_accepted"
    RISK_REJECTED = "risk_rejected"
    LOW_CONFIDENCE = "low_confidence"
    SYMBOL_OCCUPIED = "symbol_occupied"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    MAX_POSITION_LIMIT = "max_position_limit"
    INVALID_SIGNAL = "invalid_signal"
    SYSTEM_ERROR = "system_error"


class ProvenanceStage(Enum):
    """Stages in the signal provenance pipeline.

    Tracks the progression of a signal through the execution pipeline,
    from initial receipt through final disposition.

    Stages:
        RECEIVED: Signal received from signal generator
        KILL_SWITCH_CHECK: Checking kill switch status
        SYMBOL_REGISTRY_CHECK: Checking symbol availability
        RISK_VALIDATION: Validating against risk constraints
        ORDER_PLACEMENT: Placing order with exchange/simulator
        COMPLETED: Execution completed successfully
        REJECTED: Signal rejected at some stage
    """

    RECEIVED = "received"
    KILL_SWITCH_CHECK = "kill_switch_check"
    SYMBOL_REGISTRY_CHECK = "symbol_registry_check"
    RISK_VALIDATION = "risk_validation"
    ORDER_PLACEMENT = "order_placement"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass
class SignalProvenance:
    """Complete provenance record for a trading signal.

    Captures the origin and context of a signal at the moment it
    was generated, including confidence factors and market conditions.

    Attributes:
        provenance_id: Unique identifier for this provenance record
        signal_id: Reference to the original signal
        generation_timestamp: When the signal was generated (UTC)
        source_strategy: Name of the strategy that generated the signal
        source_version: Version of the strategy code
        confidence_factors: Dict of factor names to confidence scores (0.0-1.0)
            e.g., {"rsi": 0.85, "macd": 0.72, "markov": 0.91}
        market_conditions: Dict describing market state at generation
            e.g., {"volatility_regime": "high", "trend_state": "uptrend"}
    """

    provenance_id: str
    signal_id: str
    generation_timestamp: datetime
    source_strategy: str
    source_version: str
    confidence_factors: dict[str, float] = field(default_factory=dict)
    market_conditions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize provenance data."""
        # Ensure timestamp is timezone-aware
        if self.generation_timestamp.tzinfo is None:
            self.generation_timestamp = self.generation_timestamp.replace(tzinfo=UTC)

        # Validate confidence factors are in valid range
        for factor, score in self.confidence_factors.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Confidence factor '{factor}' must be between 0.0 and 1.0, "
                    f"got {score}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert provenance record to dictionary for serialization.

        Returns:
            Dictionary representation of the provenance record
        """
        return {
            "provenance_id": self.provenance_id,
            "signal_id": self.signal_id,
            "generation_timestamp": self.generation_timestamp.isoformat(),
            "source_strategy": self.source_strategy,
            "source_version": self.source_version,
            "confidence_factors": self.confidence_factors,
            "market_conditions": self.market_conditions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalProvenance:
        """Create SignalProvenance from dictionary.

        Args:
            data: Dictionary with provenance data

        Returns:
            SignalProvenance instance
        """
        return cls(
            provenance_id=data["provenance_id"],
            signal_id=data["signal_id"],
            generation_timestamp=datetime.fromisoformat(data["generation_timestamp"]),
            source_strategy=data["source_strategy"],
            source_version=data["source_version"],
            confidence_factors=data.get("confidence_factors", {}),
            market_conditions=data.get("market_conditions", {}),
        )


@dataclass
class ExecutionDecision:
    """Record of a decision made during signal execution.

    Captures the outcome of each decision point in the execution
    pipeline with standardized reason codes for auditability.

    Attributes:
        decision_id: Unique identifier for this decision record
        signal_id: Reference to the signal being processed
        decision_timestamp: When the decision was made (UTC)
        decision_reason: Standardized reason code for the decision
        decision_details: Additional context about the decision
            e.g., {"risk_violation": "max_position_size", "current_size": 10.5}
    """

    decision_id: str
    signal_id: str
    decision_timestamp: datetime
    decision_reason: DecisionReason
    decision_details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize decision data."""
        # Ensure timestamp is timezone-aware
        if self.decision_timestamp.tzinfo is None:
            self.decision_timestamp = self.decision_timestamp.replace(tzinfo=UTC)

        # Normalize decision_reason to enum if string
        if isinstance(self.decision_reason, str):
            self.decision_reason = DecisionReason(self.decision_reason)

    def to_dict(self) -> dict[str, Any]:
        """Convert decision record to dictionary for serialization.

        Returns:
            Dictionary representation of the decision record
        """
        return {
            "decision_id": self.decision_id,
            "signal_id": self.signal_id,
            "decision_timestamp": self.decision_timestamp.isoformat(),
            "decision_reason": self.decision_reason.value,
            "decision_details": self.decision_details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionDecision:
        """Create ExecutionDecision from dictionary.

        Args:
            data: Dictionary with decision data

        Returns:
            ExecutionDecision instance
        """
        return cls(
            decision_id=data["decision_id"],
            signal_id=data["signal_id"],
            decision_timestamp=datetime.fromisoformat(data["decision_timestamp"]),
            decision_reason=DecisionReason(data["decision_reason"]),
            decision_details=data.get("decision_details", {}),
        )


@dataclass
class ProvenanceRecord:
    """Container for all provenance data related to a signal.

    Aggregates signal provenance and execution decisions into a
    complete audit trail for a single signal.

    Attributes:
        signal_id: The signal being tracked
        provenance: The signal's generation provenance
        decisions: List of decisions made during execution
        stages: List of stages the signal passed through
        created_at: When this record was created
        updated_at: When this record was last updated
    """

    signal_id: str
    provenance: SignalProvenance | None = None
    decisions: list[ExecutionDecision] = field(default_factory=list)
    stages: list[ProvenanceStage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate and normalize record data."""
        # Ensure timestamps are timezone-aware
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=UTC)

    def capture_signal(
        self,
        provenance: SignalProvenance,
        stage: ProvenanceStage = ProvenanceStage.RECEIVED,
    ) -> SignalProvenance:
        """Capture signal provenance and record the initial stage.

        Args:
            provenance: The signal provenance to capture
            stage: The initial stage (default: RECEIVED)

        Returns:
            The captured SignalProvenance
        """
        self.provenance = provenance
        self.stages.append(stage)
        self.updated_at = datetime.now(UTC)
        return provenance

    def capture_decision(
        self,
        signal_id: str,
        decision: ExecutionDecision,
        details: dict[str, Any] | None = None,
    ) -> ExecutionDecision:
        """Capture an execution decision.

        Args:
            signal_id: The signal ID (must match this record's signal_id)
            decision: The decision to capture
            details: Optional additional details to merge into decision

        Returns:
            The captured ExecutionDecision

        Raises:
            ValueError: If signal_id doesn't match this record
        """
        if signal_id != self.signal_id:
            raise ValueError(f"Signal ID mismatch: {signal_id} != {self.signal_id}")

        # Merge additional details if provided
        if details:
            decision.decision_details.update(details)

        self.decisions.append(decision)
        self.updated_at = datetime.now(UTC)
        return decision

    def add_stage(self, stage: ProvenanceStage) -> None:
        """Add a provenance stage to the record.

        Args:
            stage: The stage to add
        """
        self.stages.append(stage)
        self.updated_at = datetime.now(UTC)

    def get_provenance(self, signal_id: str) -> dict[str, Any]:
        """Get complete provenance data for a signal.

        Args:
            signal_id: The signal ID to look up

        Returns:
            Dictionary with complete provenance data

        Raises:
            ValueError: If signal_id doesn't match this record
        """
        if signal_id != self.signal_id:
            raise ValueError(f"Signal ID mismatch: {signal_id} != {self.signal_id}")

        return {
            "signal_id": self.signal_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "stages": [s.value for s in self.stages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for serialization.

        Returns:
            Dictionary representation of the record
        """
        return {
            "signal_id": self.signal_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "stages": [s.value for s in self.stages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceRecord:
        """Create ProvenanceRecord from dictionary.

        Args:
            data: Dictionary with record data

        Returns:
            ProvenanceRecord instance
        """
        record = cls(
            signal_id=data["signal_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

        if data.get("provenance"):
            record.provenance = SignalProvenance.from_dict(data["provenance"])

        record.decisions = [
            ExecutionDecision.from_dict(d) for d in data.get("decisions", [])
        ]
        record.stages = [ProvenanceStage(s) for s in data.get("stages", [])]

        return record
