"""Rollback models for Rollback Coordinator.

Provides dataclasses for rollback operations, steps, and validation.

For ST-NS-042: Rollback Coordinator with Pre-flight Validation
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class RollbackStatus(StrEnum):
    """Status of a rollback operation."""

    PENDING = "pending"
    VALIDATING = "validating"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationCheckStatus(StrEnum):
    """Status of a validation check."""

    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class RollbackStepStatus(StrEnum):
    """Status of a rollback step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class HealthCheckStatus(StrEnum):
    """Status of a health check."""

    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


@dataclass
class ValidationCheck:
    """Single validation check for pre-flight validation.

    Attributes:
        check_id: Unique check identifier
        name: Human-readable check name
        description: Detailed description of what is checked
        status: Current status (pending, pass, fail, skipped)
        message: Result message
        details: Additional structured data
        executed_at: When check was executed
        duration_seconds: How long the check took
    """

    name: str
    description: str
    check_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ValidationCheckStatus = ValidationCheckStatus.PENDING
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    executed_at: datetime | None = None
    duration_seconds: float = 0.0

    def mark_pass(
        self, message: str = "", details: dict[str, Any] | None = None
    ) -> None:
        """Mark check as passed."""
        self.status = ValidationCheckStatus.PASS
        self.message = message or "Check passed"
        if details:
            self.details.update(details)
        self.executed_at = datetime.now(UTC)

    def mark_fail(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Mark check as failed."""
        self.status = ValidationCheckStatus.FAIL
        self.message = message
        if details:
            self.details.update(details)
        self.executed_at = datetime.now(UTC)

    def mark_skipped(self, message: str = "") -> None:
        """Mark check as skipped (e.g., for force rollback)."""
        self.status = ValidationCheckStatus.SKIPPED
        self.message = message or "Check skipped"
        self.executed_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_id": self.check_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ValidationResult:
    """Result of pre-flight validation.

    Attributes:
        valid: Whether all checks passed
        checks: List of individual validation checks
        errors: List of error messages if validation failed
        warnings: List of warnings (non-blocking)
        executed_at: When validation was executed
        duration_seconds: Total validation time
    """

    checks: list[ValidationCheck] = field(default_factory=list)
    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    executed_at: datetime | None = None
    duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool:
        """Check if all non-skipped checks passed."""
        return all(
            c.status in (ValidationCheckStatus.PASS, ValidationCheckStatus.SKIPPED)
            for c in self.checks
        )

    @property
    def failed_checks(self) -> list[ValidationCheck]:
        """Get list of failed checks."""
        return [c for c in self.checks if c.status == ValidationCheckStatus.FAIL]

    def add_check(self, check: ValidationCheck) -> None:
        """Add a validation check."""
        self.checks.append(check)

    def finalize(self) -> None:
        """Finalize validation result."""
        self.valid = self.all_passed
        self.errors = [c.message for c in self.failed_checks]
        if self.executed_at:
            self.duration_seconds = (
                datetime.now(UTC) - self.executed_at
            ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "checks": [c.to_dict() for c in self.checks],
            "errors": self.errors,
            "warnings": self.warnings,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class RollbackStep:
    """Single step in a rollback operation.

    Attributes:
        step_id: Unique step identifier
        name: Human-readable step name
        description: Detailed description
        action: Action to execute (callable name or action type)
        validation_check: Validation to run after step execution
        rollback_action: Action to rollback this step if needed
        status: Current step status
        order: Execution order (1-indexed)
        started_at: When step started
        completed_at: When step completed
        error_message: Error message if step failed
        execution_result: Result data from step execution
        timeout_seconds: Maximum time allowed for this step
    """

    name: str
    description: str
    action: str
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    validation_check: str | None = None
    rollback_action: str | None = None
    status: RollbackStepStatus = RollbackStepStatus.PENDING
    order: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    execution_result: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0

    def mark_in_progress(self) -> None:
        """Mark step as in progress."""
        self.status = RollbackStepStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC)

    def mark_completed(self, result: dict[str, Any] | None = None) -> None:
        """Mark step as completed."""
        self.status = RollbackStepStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if result:
            self.execution_result = result

    def mark_failed(
        self, error_message: str, result: dict[str, Any] | None = None
    ) -> None:
        """Mark step as failed."""
        self.status = RollbackStepStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message
        if result:
            self.execution_result = result

    def mark_rolled_back(self) -> None:
        """Mark step as rolled back."""
        self.status = RollbackStepStatus.ROLLED_BACK

    def mark_skipped(self) -> None:
        """Mark step as skipped."""
        self.status = RollbackStepStatus.SKIPPED
        self.completed_at = datetime.now(UTC)

    @property
    def duration_seconds(self) -> float:
        """Get step duration in seconds."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "validation_check": self.validation_check,
            "rollback_action": self.rollback_action,
            "status": self.status.value,
            "order": self.order,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "execution_result": self.execution_result,
            "timeout_seconds": self.timeout_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class HealthCheck:
    """Health check for post-rollback verification.

    Attributes:
        check_id: Unique check identifier
        name: Human-readable check name
        description: Detailed description
        status: Current status (pending, pass, fail, warning)
        message: Result message
        details: Additional structured data
        executed_at: When check was executed
        duration_seconds: How long the check took
    """

    name: str
    description: str
    check_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: HealthCheckStatus = HealthCheckStatus.PENDING
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    executed_at: datetime | None = None
    duration_seconds: float = 0.0

    def mark_pass(
        self, message: str = "", details: dict[str, Any] | None = None
    ) -> None:
        """Mark check as passed."""
        self.status = HealthCheckStatus.PASS
        self.message = message or "Health check passed"
        if details:
            self.details.update(details)
        self.executed_at = datetime.now(UTC)

    def mark_fail(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Mark check as failed."""
        self.status = HealthCheckStatus.FAIL
        self.message = message
        if details:
            self.details.update(details)
        self.executed_at = datetime.now(UTC)

    def mark_warning(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Mark check as warning (non-blocking)."""
        self.status = HealthCheckStatus.WARNING
        self.message = message
        if details:
            self.details.update(details)
        self.executed_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_id": self.check_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class PostRollbackHealth:
    """Post-rollback health verification result.

    Attributes:
        healthy: Whether all critical health checks passed
        checks: List of individual health checks
        warnings: List of warnings (non-blocking)
        executed_at: When health check was executed
        duration_seconds: Total health check time
    """

    checks: list[HealthCheck] = field(default_factory=list)
    healthy: bool = False
    warnings: list[str] = field(default_factory=list)
    executed_at: datetime | None = None
    duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool:
        """Check if all health checks passed (warnings allowed)."""
        return all(
            c.status in (HealthCheckStatus.PASS, HealthCheckStatus.WARNING)
            for c in self.checks
        )

    @property
    def failed_checks(self) -> list[HealthCheck]:
        """Get list of failed health checks."""
        return [c for c in self.checks if c.status == HealthCheckStatus.FAIL]

    def add_check(self, check: HealthCheck) -> None:
        """Add a health check."""
        self.checks.append(check)

    def finalize(self) -> None:
        """Finalize health check result."""
        self.healthy = self.all_passed
        self.warnings = [
            f"{c.name}: {c.message}"
            for c in self.checks
            if c.status == HealthCheckStatus.WARNING
        ]
        if self.executed_at:
            self.duration_seconds = (
                datetime.now(UTC) - self.executed_at
            ).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": self.warnings,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class AuditLogEntry:
    """Single audit log entry for rollback operations.

    Attributes:
        entry_id: Unique entry identifier
        timestamp: When entry was created
        level: Log level (INFO, WARN, ERROR)
        message: Log message
        actor: Who/what performed the action
        metadata: Additional structured data
    """

    message: str
    level: str = "INFO"
    actor: str = "system"
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "actor": self.actor,
            "metadata": self.metadata,
        }


@dataclass
class RollbackOperation:
    """Main rollback operation record.

    Attributes:
        operation_id: Unique operation identifier
        target_state: Target state to rollback to
        status: Current operation status
        steps: List of rollback steps
        validation_result: Pre-flight validation result
        post_rollback_health: Post-rollback health verification
        created_at: When operation was created
        started_at: When execution started
        completed_at: When execution completed
        duration_seconds: Total execution time
        initiated_by: Who/what initiated the rollback
        force: Whether validation was bypassed
        error_message: Error message if operation failed
        audit_log: Immutable audit log of all operations
        metadata: Additional structured data
    """

    target_state: str
    steps: list[RollbackStep] = field(default_factory=list)
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RollbackStatus = RollbackStatus.PENDING
    validation_result: ValidationResult | None = None
    post_rollback_health: PostRollbackHealth | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    initiated_by: str = "system"
    force: bool = False
    error_message: str | None = None
    audit_log: list[AuditLogEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: RollbackStep) -> None:
        """Add a rollback step."""
        step.order = len(self.steps) + 1
        self.steps.append(step)

    def add_audit_entry(
        self,
        message: str,
        level: str = "INFO",
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add an audit log entry."""
        entry = AuditLogEntry(
            message=message,
            level=level,
            actor=actor,
            metadata=metadata or {},
        )
        self.audit_log.append(entry)

    def mark_started(self) -> None:
        """Mark operation as started."""
        self.status = RollbackStatus.EXECUTING
        self.started_at = datetime.now(UTC)
        self.add_audit_entry(
            f"Rollback operation started (force={self.force})",
            actor=self.initiated_by,
        )

    def mark_validating(self) -> None:
        """Mark operation as validating."""
        self.status = RollbackStatus.VALIDATING
        self.add_audit_entry("Pre-flight validation started")

    def mark_verifying(self) -> None:
        """Mark operation as verifying."""
        self.status = RollbackStatus.VERIFYING
        self.add_audit_entry("Post-rollback verification started")

    def mark_completed(self) -> None:
        """Mark operation as completed."""
        self.status = RollbackStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()
        self.add_audit_entry(
            f"Rollback operation completed in {self.duration_seconds:.2f}s"
        )

    def mark_failed(self, error_message: str) -> None:
        """Mark operation as failed."""
        self.status = RollbackStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()
        self.add_audit_entry(
            f"Rollback operation failed: {error_message}",
            level="ERROR",
        )

    def mark_cancelled(self, reason: str) -> None:
        """Mark operation as cancelled."""
        self.status = RollbackStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.add_audit_entry(f"Rollback operation cancelled: {reason}", level="WARN")

    @property
    def current_step(self) -> RollbackStep | None:
        """Get the current step being executed."""
        for step in self.steps:
            if step.status == RollbackStepStatus.IN_PROGRESS:
                return step
        return None

    @property
    def completed_steps(self) -> list[RollbackStep]:
        """Get list of completed steps."""
        return [s for s in self.steps if s.status == RollbackStepStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[RollbackStep]:
        """Get list of failed steps."""
        return [s for s in self.steps if s.status == RollbackStepStatus.FAILED]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation_id": self.operation_id,
            "target_state": self.target_state,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "validation_result": (
                self.validation_result.to_dict() if self.validation_result else None
            ),
            "post_rollback_health": (
                self.post_rollback_health.to_dict()
                if self.post_rollback_health
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "initiated_by": self.initiated_by,
            "force": self.force,
            "error_message": self.error_message,
            "audit_log": [e.to_dict() for e in self.audit_log],
            "metadata": self.metadata,
        }


class RollbackStore(Protocol):
    """Protocol for rollback operation storage backends."""

    def save(self, operation: RollbackOperation) -> None:
        """Save or update a rollback operation."""
        ...

    def get(self, operation_id: str) -> RollbackOperation | None:
        """Get operation by ID."""
        ...

    def list(
        self,
        status: RollbackStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RollbackOperation]:
        """List rollback operations with optional filtering."""
        ...

    def delete(self, operation_id: str) -> bool:
        """Delete a rollback operation."""
        ...


@dataclass
class RollbackMetrics:
    """Metrics for rollback operations.

    Attributes:
        total_operations: Total rollback operations executed
        successful: Number of successful rollbacks
        failed: Number of failed rollbacks
        avg_duration_seconds: Average rollback duration
        p95_duration_seconds: 95th percentile duration
        by_target_state: Breakdown by target state
    """

    total_operations: int = 0
    successful: int = 0
    failed: int = 0
    avg_duration_seconds: float = 0.0
    p95_duration_seconds: float = 0.0
    by_target_state: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_operation(self, operation: RollbackOperation) -> None:
        """Record a rollback operation."""
        self.total_operations += 1

        if operation.status == RollbackStatus.COMPLETED:
            self.successful += 1
        elif operation.status == RollbackStatus.FAILED:
            self.failed += 1

        # Track by target state
        target = operation.target_state
        if target not in self.by_target_state:
            self.by_target_state[target] = {"success": 0, "failure": 0}

        if operation.status == RollbackStatus.COMPLETED:
            self.by_target_state[target]["success"] += 1
        elif operation.status == RollbackStatus.FAILED:
            self.by_target_state[target]["failure"] += 1

    def update_stats(self, operations: list[RollbackOperation]) -> None:
        """Update duration statistics."""
        if not operations:
            return

        durations = [
            op.duration_seconds for op in operations if op.duration_seconds > 0
        ]
        if durations:
            self.avg_duration_seconds = sum(durations) / len(durations)
            sorted_durations = sorted(durations)
            idx = int(len(sorted_durations) * 0.95)
            if idx < len(sorted_durations):
                self.p95_duration_seconds = sorted_durations[idx]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_operations": self.total_operations,
            "successful": self.successful,
            "failed": self.failed,
            "avg_duration_seconds": self.avg_duration_seconds,
            "p95_duration_seconds": self.p95_duration_seconds,
            "by_target_state": self.by_target_state,
        }


# =============================================================================
# Pydantic API Models (for FastAPI request/response schemas)
# =============================================================================


class RollbackRequest(BaseModel):
    """Request model for rollback operations.

    Attributes:
        target_state: Target state to rollback to
        force: If True, bypass pre-flight validation
        initiated_by: Who/what initiated the rollback
        metadata: Additional metadata for the operation
    """

    target_state: str = Field(..., description="Target state to rollback to")
    force: bool = Field(
        default=False, description="Bypass pre-flight validation if True"
    )
    initiated_by: str = Field(
        default="api", description="Who/what initiated the rollback"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ValidationCheckItem(BaseModel):
    """Validation check item for API responses.

    Attributes:
        check_id: Unique check identifier
        name: Human-readable check name
        description: Detailed description
        status: Check status (pending, pass, fail, skipped)
        message: Result message
        details: Additional structured data
        executed_at: ISO format timestamp
        duration_seconds: How long the check took
    """

    check_id: str
    name: str
    description: str
    status: str
    message: str
    details: dict[str, Any]
    executed_at: str | None
    duration_seconds: float


class RollbackValidationResponse(BaseModel):
    """Response model for rollback validation endpoint.

    Attributes:
        can_rollback: Whether rollback is possible
        reason: Human-readable explanation
        validation_checks: List of individual validation checks
        errors: List of error messages if validation failed
        warnings: List of warnings (non-blocking)
        executed_at: ISO format timestamp
        duration_seconds: Total validation time
    """

    can_rollback: bool = Field(..., description="Whether rollback is possible")
    reason: str = Field(..., description="Human-readable explanation")
    validation_checks: list[ValidationCheckItem] = Field(
        default_factory=list, description="Individual validation checks"
    )
    errors: list[str] = Field(
        default_factory=list, description="Error messages if validation failed"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warnings (non-blocking)"
    )
    executed_at: str | None = Field(default=None, description="ISO format timestamp")
    duration_seconds: float = Field(default=0.0, description="Total validation time")


class RollbackStepItem(BaseModel):
    """Rollback step item for API responses.

    Attributes:
        step_id: Unique step identifier
        name: Human-readable step name
        description: Detailed description
        action: Action type identifier
        status: Step status
        order: Execution order
        started_at: ISO format timestamp
        completed_at: ISO format timestamp
        error_message: Error message if failed
        execution_result: Result data
        timeout_seconds: Maximum time allowed
        duration_seconds: Actual duration
    """

    step_id: str
    name: str
    description: str
    action: str
    status: str
    order: int
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    execution_result: dict[str, Any]
    timeout_seconds: float
    duration_seconds: float


class RollbackResponse(BaseModel):
    """Response model for rollback execution endpoint.

    Attributes:
        rollback_id: Unique operation identifier
        target_state: Target state rolled back to
        status: Operation status
        steps: List of rollback steps
        validation_result: Pre-flight validation result
        post_rollback_health: Post-rollback health verification
        created_at: ISO format timestamp
        started_at: ISO format timestamp
        completed_at: ISO format timestamp
        duration_seconds: Total execution time
        initiated_by: Who initiated the rollback
        force: Whether validation was bypassed
        error_message: Error message if failed
        audit_log: List of audit log entries
    """

    rollback_id: str = Field(..., description="Unique operation identifier")
    target_state: str = Field(..., description="Target state rolled back to")
    status: str = Field(..., description="Operation status")
    steps: list[RollbackStepItem] = Field(
        default_factory=list, description="Rollback steps"
    )
    validation_result: RollbackValidationResponse | None = Field(
        default=None, description="Pre-flight validation result"
    )
    post_rollback_health: dict[str, Any] | None = Field(
        default=None, description="Post-rollback health verification"
    )
    created_at: str = Field(..., description="ISO format timestamp")
    started_at: str | None = Field(default=None, description="ISO format timestamp")
    completed_at: str | None = Field(default=None, description="ISO format timestamp")
    duration_seconds: float = Field(default=0.0, description="Total execution time")
    initiated_by: str = Field(
        default="system", description="Who initiated the rollback"
    )
    force: bool = Field(default=False, description="Whether validation was bypassed")
    error_message: str | None = Field(
        default=None, description="Error message if failed"
    )
    audit_log: list[dict[str, Any]] = Field(
        default_factory=list, description="Audit log entries"
    )


class RollbackHistoryItem(BaseModel):
    """History item for rollback operations.

    Attributes:
        rollback_id: Unique operation identifier
        target_state: Target state rolled back to
        status: Operation status
        created_at: ISO format timestamp
        completed_at: ISO format timestamp
        duration_seconds: Total execution time
        initiated_by: Who initiated the rollback
        force: Whether validation was bypassed
        error_message: Error message if failed
    """

    rollback_id: str = Field(..., description="Unique operation identifier")
    target_state: str = Field(..., description="Target state rolled back to")
    status: str = Field(..., description="Operation status")
    created_at: str = Field(..., description="ISO format timestamp")
    completed_at: str | None = Field(default=None, description="ISO format timestamp")
    duration_seconds: float = Field(default=0.0, description="Total execution time")
    initiated_by: str = Field(
        default="system", description="Who initiated the rollback"
    )
    force: bool = Field(default=False, description="Whether validation was bypassed")
    error_message: str | None = Field(
        default=None, description="Error message if failed"
    )


class RollbackHistoryResponse(BaseModel):
    """Response model for rollback history endpoint.

    Attributes:
        operations: List of rollback operations
        total: Total number of operations
        limit: Maximum results per page
        offset: Pagination offset
    """

    operations: list[RollbackHistoryItem] = Field(
        default_factory=list, description="Rollback operations"
    )
    total: int = Field(default=0, description="Total number of operations")
    limit: int = Field(default=100, description="Maximum results per page")
    offset: int = Field(default=0, description="Pagination offset")


class RollbackMetricsResponse(BaseModel):
    """Response model for rollback metrics endpoint.

    Attributes:
        total_operations: Total rollback operations executed
        successful: Number of successful rollbacks
        failed: Number of failed rollbacks
        avg_duration_seconds: Average rollback duration
        p95_duration_seconds: 95th percentile duration
        by_target_state: Breakdown by target state
    """

    total_operations: int = Field(
        default=0, description="Total rollback operations executed"
    )
    successful: int = Field(default=0, description="Number of successful rollbacks")
    failed: int = Field(default=0, description="Number of failed rollbacks")
    avg_duration_seconds: float = Field(
        default=0.0, description="Average rollback duration"
    )
    p95_duration_seconds: float = Field(
        default=0.0, description="95th percentile duration"
    )
    by_target_state: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Breakdown by target state"
    )


class RollbackScheduleRequest(BaseModel):
    """Request model for scheduling a rollback.

    Attributes:
        target_state: Target state to rollback to
        scheduled_at: ISO format timestamp when to execute
        force: If True, bypass pre-flight validation
        initiated_by: Who/what initiated the rollback
        metadata: Additional metadata
    """

    target_state: str = Field(..., description="Target state to rollback to")
    scheduled_at: str = Field(..., description="ISO format timestamp when to execute")
    force: bool = Field(
        default=False, description="Bypass pre-flight validation if True"
    )
    initiated_by: str = Field(
        default="api", description="Who/what initiated the rollback"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
