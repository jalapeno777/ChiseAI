"""Knowledge transfer protocols for cross-system learning."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class TransferStatus(Enum):
    """Status of a knowledge transfer operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATED = "validated"
    ROLLED_BACK = "rolled_back"


class TransferPriority(Enum):
    """Priority levels for knowledge transfer."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TransferEvent:
    """Represents a knowledge transfer event between systems."""

    transfer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_system: str = ""
    target_system: str = ""
    knowledge_type: str = ""
    knowledge_item_id: str = ""
    operation: str = "transfer"  # transfer, update, delete
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: TransferStatus = TransferStatus.PENDING
    priority: TransferPriority = TransferPriority.MEDIUM
    retry_count: int = 0
    validation_result: dict[str, Any] | None = None
    error: str | None = None

    def mark_in_progress(self) -> None:
        """Mark transfer as in progress."""
        self.status = TransferStatus.IN_PROGRESS

    def mark_completed(self) -> None:
        """Mark transfer as completed."""
        self.status = TransferStatus.COMPLETED

    def mark_failed(self, error: str) -> None:
        """Mark transfer as failed."""
        self.status = TransferStatus.FAILED
        self.error = error

    def mark_validated(self) -> None:
        """Mark transfer as validated."""
        self.status = TransferStatus.VALIDATED


@dataclass
class ValidationResult:
    """Result of knowledge validation."""

    is_valid: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        """Add validation error."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add validation warning."""
        self.warnings.append(warning)


class KnowledgeTransferProtocol:
    """
    Protocol for transferring knowledge between AUTOCOG and STRONG systems.

    Provides:
    - Standardized transfer formats
    - Validation and verification
    - Retry and rollback mechanisms
    - Transfer metadata tracking
    """

    def __init__(self, max_retries: int = 3, enable_validation: bool = True):
        self.max_retries = max_retries
        self.enable_validation = enable_validation
        self._transfer_history: dict[str, TransferEvent] = {}

    def create_transfer_event(
        self,
        source_system: str,
        target_system: str,
        knowledge_type: str,
        knowledge_item_id: str,
        payload: dict[str, Any],
        operation: str = "transfer",
        priority: TransferPriority = TransferPriority.MEDIUM,
        metadata: dict[str, Any] | None = None,
    ) -> TransferEvent:
        """Create a new transfer event."""
        event = TransferEvent(
            source_system=source_system,
            target_system=target_system,
            knowledge_type=knowledge_type,
            knowledge_item_id=knowledge_item_id,
            operation=operation,
            payload=payload,
            priority=priority,
            metadata=metadata or {},
        )
        self._transfer_history[event.transfer_id] = event
        return event

    def validate_transfer(self, event: TransferEvent) -> ValidationResult:
        """Validate a transfer event."""
        result = ValidationResult()

        if not self.enable_validation:
            result.is_valid = True
            return result

        # Basic validation
        if not event.source_system:
            result.add_error("Source system is required")

        if not event.target_system:
            result.add_error("Target system is required")

        if not event.knowledge_type:
            result.add_error("Knowledge type is required")

        if not event.knowledge_item_id:
            result.add_error("Knowledge item ID is required")

        if not event.payload:
            result.add_warning("Payload is empty")

        # System-specific validation
        if event.source_system == "autocog":
            self._validate_autocog_payload(event, result)
        elif event.source_system == "strong":
            self._validate_strong_payload(event, result)

        if not result.errors:
            result.is_valid = True

        event.validation_result = {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
        }

        return result

    def _validate_autocog_payload(
        self, event: TransferEvent, result: ValidationResult
    ) -> None:
        """Validate AUTOCOG-specific payload."""
        if event.knowledge_type == "action":
            required_fields = ["action_id", "action_type", "parameters"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(f"Missing required field for action: {field}")

        elif event.knowledge_type == "assessment":
            required_fields = ["artifact_id", "confidence_score", "recommendations"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(f"Missing required field for assessment: {field}")

        elif event.knowledge_type == "validation_result":
            required_fields = ["validation_id", "is_valid", "findings"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(f"Missing required field for validation: {field}")

    def _validate_strong_payload(
        self, event: TransferEvent, result: ValidationResult
    ) -> None:
        """Validate STRONG-specific payload."""
        if event.knowledge_type == "belief_embedding":
            required_fields = ["embedding_id", "vector", "metadata"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(
                        f"Missing required field for belief embedding: {field}"
                    )

        elif event.knowledge_type == "learning_update":
            required_fields = ["update_id", "gradient_info", "loss_value"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(
                        f"Missing required field for learning update: {field}"
                    )

        elif event.knowledge_type == "symbolic_rule":
            required_fields = ["rule_id", "rule_expression", "confidence"]
            for field in required_fields:
                if field not in event.payload:
                    result.add_error(
                        f"Missing required field for symbolic rule: {field}"
                    )

    def can_retry(self, event: TransferEvent) -> bool:
        """Check if transfer can be retried."""
        return event.retry_count < self.max_retries

    def record_retry(self, event: TransferEvent) -> None:
        """Record a retry attempt."""
        event.retry_count += 1

    def get_transfer_history(self, transfer_id: str) -> TransferEvent | None:
        """Get transfer event from history."""
        return self._transfer_history.get(transfer_id)

    def get_transfers_by_system(self, system_id: str) -> list:
        """Get all transfers involving a system."""
        return [
            event
            for event in self._transfer_history.values()
            if event.source_system == system_id or event.target_system == system_id
        ]

    def get_transfers_by_status(self, status: TransferStatus) -> list:
        """Get all transfers with a specific status."""
        return [
            event for event in self._transfer_history.values() if event.status == status
        ]
