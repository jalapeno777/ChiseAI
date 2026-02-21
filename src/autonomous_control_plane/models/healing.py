"""Healing models for self-healing engine.

Provides dataclasses for healing actions, results, and pattern matching.

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any, Protocol


class HealingStatus(StrEnum):
    """Status of a healing action."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    ROLLED_BACK = "rolled_back"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"


class FailurePatternType(StrEnum):
    """Types of failure patterns."""

    REDIS_DISCONNECT = "redis_disconnect"
    API_TIMEOUT = "api_timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    DATABASE_CONNECTION = "database_connection"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    DISK_SPACE = "disk_space"
    CPU_SPIKE = "cpu_spike"
    INFLUXDB_WRITE = "influxdb_write"
    DEAD_LETTER_QUEUE = "dead_letter_queue"
    SERVICE_UNHEALTHY = "service_unhealthy"


class ActionPriority(StrEnum):
    """Priority levels for healing actions."""

    P0 = "p0"  # Critical - requires human approval for live trading
    P1 = "p1"  # High - automated with monitoring
    P2 = "p2"  # Medium - automated
    P3 = "p3"  # Low - automated


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed execution.

    Attributes:
        max_cpu_seconds: Maximum CPU time allowed
        max_memory_mb: Maximum memory in MB
        max_execution_seconds: Maximum wall-clock time
        max_file_descriptors: Maximum file descriptors
    """

    max_cpu_seconds: float = 5.0
    max_memory_mb: int = 100
    max_execution_seconds: float = 30.0
    max_file_descriptors: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_execution_seconds": self.max_execution_seconds,
            "max_file_descriptors": self.max_file_descriptors,
        }


@dataclass
class HealingResult:
    """Result of a healing action execution.

    Attributes:
        success: Whether the healing succeeded
        action_id: Unique identifier for this healing action
        action_type: Type of healing action performed
        service: Service that was healed
        duration_seconds: Time taken to execute
        details: Additional output from the action
        error: Error message if failed
        timestamp: When healing completed
        pre_state: State captured before healing (for rollback)
    """

    success: bool
    action_id: str
    action_type: str
    service: str
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    pre_state: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "service": self.service,
            "duration_seconds": self.duration_seconds,
            "details": self.details,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "pre_state": self.pre_state,
        }


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether rollback succeeded
        action_id: ID of the action being rolled back
        duration_seconds: Time taken
        error: Error message if failed
        timestamp: When rollback completed
    """

    success: bool
    action_id: str
    duration_seconds: float = 0.0
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "action_id": self.action_id,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HealingAttempt:
    """Record of a healing attempt for tracking and anti-flap.

    Attributes:
        attempt_id: Unique identifier
        service: Service being healed
        action_type: Type of healing action
        status: Current status
        started_at: When attempt started
        completed_at: When attempt completed
        attempt_number: Which attempt this is (1-3 for anti-flap)
        requires_approval: Whether human approval is required
        approved_by: Who approved the action
        approved_at: When approved
    """

    service: str
    action_type: str
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: HealingStatus = HealingStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    attempt_number: int = 1
    requires_approval: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    result: HealingResult | None = None
    rollback_result: RollbackResult | None = None

    def complete(self, result: HealingResult) -> None:
        """Mark attempt as completed."""
        self.status = (
            HealingStatus.SUCCEEDED if result.success else HealingStatus.FAILED
        )
        self.result = result
        self.completed_at = datetime.now(UTC)

    def mark_rolled_back(self, rollback_result: RollbackResult) -> None:
        """Mark as rolled back."""
        self.rollback_result = rollback_result
        if rollback_result.success:
            self.status = HealingStatus.ROLLED_BACK

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_id": self.attempt_id,
            "service": self.service,
            "action_type": self.action_type,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "attempt_number": self.attempt_number,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "result": self.result.to_dict() if self.result else None,
            "rollback_result": (
                self.rollback_result.to_dict() if self.rollback_result else None
            ),
        }


@dataclass
class FailurePatternMatch:
    """Result of pattern matching.

    Attributes:
        matched: Whether pattern matched
        pattern_type: Type of pattern that matched
        confidence: Match confidence (0.0-1.0)
        extracted_fields: Fields extracted from log entry
        priority: Priority of the matched pattern
    """

    matched: bool
    pattern_type: FailurePatternType | None = None
    confidence: float = 0.0
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    @classmethod
    def no_match(cls) -> FailurePatternMatch:
        """Create a no-match result."""
        return cls(matched=False)


@dataclass
class LogEntry:
    """Log entry for pattern matching.

    Attributes:
        timestamp: When log was generated
        level: Log level (ERROR, WARN, INFO, etc.)
        source: Component that generated the log
        message: Log message
        metadata: Additional structured data
    """

    timestamp: datetime
    level: str
    source: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass
class HealingContext:
    """Context passed to healing actions during execution.

    Attributes:
        service: Service being healed
        action_id: Unique action identifier
        attempt_number: Which attempt this is
        triggered_by: What triggered the healing (pattern type)
        log_entry: Original log entry that triggered healing
        resource_limits: Resource limits for sandboxed execution
        timeout_seconds: Execution timeout
    """

    service: str
    action_id: str
    attempt_number: int = 1
    triggered_by: str | None = None
    log_entry: LogEntry | None = None
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    timeout_seconds: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "service": self.service,
            "action_id": self.action_id,
            "attempt_number": self.attempt_number,
            "triggered_by": self.triggered_by,
            "log_entry": self.log_entry.to_dict() if self.log_entry else None,
            "resource_limits": self.resource_limits.to_dict(),
            "timeout_seconds": self.timeout_seconds,
        }


class FailurePattern(Protocol):
    """Protocol for failure pattern matchers."""

    pattern_type: FailurePatternType
    priority: int

    def match(self, log_entry: LogEntry) -> FailurePatternMatch:
        """Match log entry against this pattern.

        Args:
            log_entry: Log entry to match

        Returns:
            Match result with confidence and extracted fields
        """
        ...


class HealingAction(Protocol):
    """Protocol for healing actions."""

    action_type: str
    priority: ActionPriority

    def execute(self, context: HealingContext) -> HealingResult:
        """Execute the healing action.

        Args:
            context: Execution context

        Returns:
            Healing result
        """
        ...

    def rollback(
        self, context: HealingContext, result: HealingResult
    ) -> RollbackResult:
        """Rollback the healing action.

        Args:
            context: Execution context
            result: Original healing result

        Returns:
            Rollback result
        """
        ...

    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits for sandboxed execution.

        Returns:
            Resource limits
        """
        ...

    def requires_human_approval(self, trading_mode: str) -> bool:
        """Check if human approval is required.

        Args:
            trading_mode: Current trading mode (paper/live)

        Returns:
            True if approval required
        """
        ...


@dataclass
class HealingStats:
    """Statistics for healing operations.

    Attributes:
        total_attempts: Total healing attempts
        successful: Number of successful healings
        failed: Number of failed healings
        rolled_back: Number of rolled back healings
        rejected: Number of rejected healings
        by_service: Breakdown by service
        by_pattern: Breakdown by pattern type
    """

    total_attempts: int = 0
    successful: int = 0
    failed: int = 0
    rolled_back: int = 0
    rejected: int = 0
    by_service: dict[str, dict[str, int]] = field(default_factory=dict)
    by_pattern: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_attempt(
        self, service: str, pattern_type: str, status: HealingStatus
    ) -> None:
        """Record a healing attempt."""
        self.total_attempts += 1

        if status == HealingStatus.SUCCEEDED:
            self.successful += 1
        elif status == HealingStatus.FAILED:
            self.failed += 1
        elif status == HealingStatus.ROLLED_BACK:
            self.rolled_back += 1
        elif status == HealingStatus.REJECTED:
            self.rejected += 1

        # Track by service
        if service not in self.by_service:
            self.by_service[service] = {}
        self.by_service[service][status.value] = (
            self.by_service[service].get(status.value, 0) + 1
        )

        # Track by pattern
        if pattern_type not in self.by_pattern:
            self.by_pattern[pattern_type] = {}
        self.by_pattern[pattern_type][status.value] = (
            self.by_pattern[pattern_type].get(status.value, 0) + 1
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_attempts": self.total_attempts,
            "successful": self.successful,
            "failed": self.failed,
            "rolled_back": self.rolled_back,
            "rejected": self.rejected,
            "by_service": self.by_service,
            "by_pattern": self.by_pattern,
        }
