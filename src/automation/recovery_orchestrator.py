"""Recovery orchestrator for self-healing automation.

Manages recovery workflows, tracks recovery state machines,
and prevents recovery loops through attempt limiting.

For PAPER-003-004: Event-Driven Self-Healing Automation
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class RecoveryState(Enum):
    """Recovery state machine states."""

    IDLE = "idle"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MAX_ATTEMPTS_REACHED = "max_attempts_reached"
    CANCELLED = "cancelled"


class RecoveryType(StrEnum):
    """Types of recovery actions."""

    REDIS_RECONNECT = "redis_reconnect"
    EXCHANGE_FAILOVER = "exchange_failover"
    SERVICE_RESTART = "service_restart"
    DATA_BACKFILL = "data_backfill"
    DEPLOYMENT_ROLLBACK = "deployment_rollback"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"


class HealthLevel(StrEnum):
    """Health severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class RecoveryContext:
    """Context for a recovery attempt.

    Attributes:
        source: Component or service that needs recovery
        recovery_type: Type of recovery to attempt
        trigger_event: Event that triggered recovery
        metadata: Additional context data
    """

    source: str
    recovery_type: RecoveryType
    trigger_event: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryAttempt:
    """A single recovery attempt.

    Attributes:
        attempt_id: Unique identifier
        context: Recovery context
        state: Current recovery state
        attempt_number: Which attempt this is (1-indexed)
        started_at: When attempt started
        completed_at: When attempt completed (if finished)
        duration_seconds: How long attempt took
        error_message: Error if failed
        recovery_output: Output from recovery action
    """

    attempt_id: str
    context: RecoveryContext
    state: RecoveryState = RecoveryState.IDLE
    attempt_number: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None
    recovery_output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_id": self.attempt_id,
            "source": self.context.source,
            "recovery_type": self.context.recovery_type.value,
            "trigger_event": self.context.trigger_event,
            "state": self.state.value,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "recovery_output": self.recovery_output,
        }


@dataclass
class RecoveryResult:
    """Result of a recovery operation.

    Attributes:
        success: Whether recovery succeeded
        attempt: The recovery attempt
        next_action: Recommended next action
        escalation_required: Whether human escalation is needed
    """

    success: bool
    attempt: RecoveryAttempt
    next_action: str = "continue"
    escalation_required: bool = False


# Type alias for recovery action functions
RecoveryAction = Callable[[RecoveryContext], Awaitable[dict[str, Any]]]


class RecoveryOrchestrator:
    """Orchestrates recovery actions with state management.

    Features:
    - Tracks recovery state machine
    - Limits recovery attempts (max 3 by default)
    - Prevents cascading failures through circuit breaker integration
    - Maintains recovery history
    - Provides audit logging

    For PAPER-003-004: Event-Driven Self-Healing Automation
    """

    DEFAULT_MAX_ATTEMPTS = 3
    DEFAULT_RECOVERY_TIMEOUT_SECONDS = 120.0
    DEFAULT_COOLDOWN_SECONDS = 60.0

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        recovery_timeout_seconds: float = DEFAULT_RECOVERY_TIMEOUT_SECONDS,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        audit_logger: Any | None = None,
    ):
        """Initialize recovery orchestrator.

        Args:
            max_attempts: Maximum recovery attempts before giving up
            recovery_timeout_seconds: Timeout for recovery actions
            cooldown_seconds: Cooldown between recovery attempts
            audit_logger: Optional audit logger (InfluxDB client, etc.)
        """
        self.max_attempts = max_attempts
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self._audit_logger = audit_logger

        # Recovery action registry
        self._recovery_actions: dict[RecoveryType, RecoveryAction] = {}

        # Track recovery attempts by source
        self._recovery_history: dict[str, list[RecoveryAttempt]] = {}

        # Current recovery attempts
        self._active_recoveries: dict[str, RecoveryAttempt] = {}

        # Recovery event handlers
        self._on_recovery_success: list[
            Callable[[RecoveryAttempt], Awaitable[None]]
        ] = []
        self._on_recovery_failure: list[
            Callable[[RecoveryAttempt], Awaitable[None]]
        ] = []
        self._on_escalation: list[Callable[[RecoveryAttempt], Awaitable[None]]] = []

        # Running state
        self._running = False
        self._lock = asyncio.Lock()

        logger.info(
            f"RecoveryOrchestrator initialized: max_attempts={max_attempts}, "
            f"timeout={recovery_timeout_seconds}s, cooldown={cooldown_seconds}s"
        )

    def register_recovery_action(
        self,
        recovery_type: RecoveryType,
        action: RecoveryAction,
    ) -> None:
        """Register a recovery action for a type.

        Args:
            recovery_type: Type of recovery
            action: Async function that performs recovery
        """
        self._recovery_actions[recovery_type] = action
        logger.info(f"Registered recovery action: {recovery_type.value}")

    def unregister_recovery_action(self, recovery_type: RecoveryType) -> None:
        """Unregister a recovery action."""
        if recovery_type in self._recovery_actions:
            del self._recovery_actions[recovery_type]
            logger.info(f"Unregistered recovery action: {recovery_type.value}")

    def add_success_handler(
        self,
        handler: Callable[[RecoveryAttempt], Awaitable[None]],
    ) -> None:
        """Add handler for successful recoveries."""
        self._on_recovery_success.append(handler)
        logger.debug(f"Added success handler: {handler.__name__}")

    def add_failure_handler(
        self,
        handler: Callable[[RecoveryAttempt], Awaitable[None]],
    ) -> None:
        """Add handler for failed recoveries."""
        self._on_recovery_failure.append(handler)
        logger.debug(f"Added failure handler: {handler.__name__}")

    def add_escalation_handler(
        self,
        handler: Callable[[RecoveryAttempt], Awaitable[None]],
    ) -> None:
        """Add handler for escalations."""
        self._on_escalation.append(handler)
        logger.debug(f"Added escalation handler: {handler.__name__}")

    async def start(self) -> None:
        """Start the orchestrator."""
        self._running = True
        logger.info("RecoveryOrchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator and cancel active recoveries."""
        self._running = False

        # Cancel active recoveries
        async with self._lock:
            for attempt_id, attempt in list(self._active_recoveries.items()):
                attempt.state = RecoveryState.CANCELLED
                logger.warning(f"Cancelled recovery: {attempt_id}")

        self._active_recoveries.clear()
        logger.info("RecoveryOrchestrator stopped")

    async def trigger_recovery(
        self,
        context: RecoveryContext,
        priority: HealthLevel = HealthLevel.WARNING,
    ) -> RecoveryResult:
        """Trigger a recovery for the given context.

        Args:
            context: Recovery context
            priority: Priority level of the recovery

        Returns:
            Recovery result
        """
        source = context.source

        # Phase 1: Check and prepare (with lock)
        async with self._lock:
            # Check if already recovering this source
            if source in self._active_recoveries:
                active = self._active_recoveries[source]
                logger.warning(
                    f"Recovery already in progress for {source}: {active.attempt_id}"
                )
                return RecoveryResult(
                    success=False,
                    attempt=active,
                    next_action="wait",
                    escalation_required=False,
                )

            # Get recovery history for this source
            history = self._recovery_history.get(source, [])

            # Count recent attempts
            recent_attempts = self._count_recent_attempts(history)

            if recent_attempts >= self.max_attempts:
                # Max attempts reached - escalate
                attempt = RecoveryAttempt(
                    attempt_id=str(uuid.uuid4()),
                    context=context,
                    state=RecoveryState.MAX_ATTEMPTS_REACHED,
                    attempt_number=len(history) + 1,
                    error_message=f"Max attempts ({self.max_attempts}) reached",
                )

                logger.error(
                    f"Recovery for {source} blocked: max attempts reached ({self.max_attempts})"
                )

                # Log to audit (outside lock to prevent deadlock)
                pass  # Will log after releasing lock

                # Escalate
                await self._escalate(attempt)

                return RecoveryResult(
                    success=False,
                    attempt=attempt,
                    next_action="escalate",
                    escalation_required=True,
                )

            # Create recovery attempt
            attempt = RecoveryAttempt(
                attempt_id=str(uuid.uuid4()),
                context=context,
                state=RecoveryState.PENDING,
                attempt_number=len(history) + 1,
            )

            # Track as active
            self._active_recoveries[source] = attempt

        # Phase 2: Execute recovery (without lock to prevent deadlock)
        return await self._execute_recovery(attempt, context, priority)

    async def _execute_recovery(
        self,
        attempt: RecoveryAttempt,
        context: RecoveryContext,
        priority: HealthLevel,
    ) -> RecoveryResult:
        """Execute the recovery action."""
        attempt.state = RecoveryState.IN_PROGRESS
        attempt.started_at = datetime.now(UTC)

        logger.info(
            f"Starting recovery {attempt.attempt_id} for {context.source}: "
            f"{context.recovery_type.value} (attempt {attempt.attempt_number}/{self.max_attempts})"
        )

        # Get recovery action
        action = self._recovery_actions.get(context.recovery_type)

        if not action:
            # No action registered - fail
            attempt.state = RecoveryState.FAILED
            attempt.completed_at = datetime.now(UTC)
            attempt.error_message = (
                f"No recovery action registered for {context.recovery_type.value}"
            )

            logger.error(f"No recovery action for {context.recovery_type.value}")

            # Clean up
            async with self._lock:
                if context.source in self._active_recoveries:
                    del self._active_recoveries[context.source]
                self._add_to_history(context.source, attempt)

            # Log
            await self._log_recovery_attempt(attempt)

            return RecoveryResult(
                success=False,
                attempt=attempt,
                next_action="escalate",
                escalation_required=True,
            )

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                action(context),
                timeout=self.recovery_timeout_seconds,
            )

            # Success
            attempt.state = RecoveryState.SUCCEEDED
            attempt.completed_at = datetime.now(UTC)
            attempt.recovery_output = result

            duration = (attempt.completed_at - attempt.started_at).total_seconds()
            attempt.duration_seconds = duration

            logger.info(f"Recovery succeeded for {context.source}: {duration:.2f}s")

            # Clean up
            async with self._lock:
                if context.source in self._active_recoveries:
                    del self._active_recoveries[context.source]
                self._add_to_history(context.source, attempt)

            # Log and notify
            await self._log_recovery_attempt(attempt)
            await self._notify_success(attempt)

            return RecoveryResult(
                success=True,
                attempt=attempt,
                next_action="monitor",
                escalation_required=False,
            )

        except asyncio.TimeoutError:
            # Timeout
            attempt.state = RecoveryState.FAILED
            attempt.completed_at = datetime.now(UTC)
            attempt.error_message = (
                f"Recovery timed out after {self.recovery_timeout_seconds}s"
            )

            duration = (attempt.completed_at - attempt.started_at).total_seconds()
            attempt.duration_seconds = duration

            logger.error(f"Recovery timed out for {context.source}: {duration:.2f}s")

            # Clean up
            async with self._lock:
                if context.source in self._active_recoveries:
                    del self._active_recoveries[context.source]
                self._add_to_history(context.source, attempt)

            # Log and notify
            await self._log_recovery_attempt(attempt)
            await self._notify_failure(attempt)

            return RecoveryResult(
                success=False,
                attempt=attempt,
                next_action="retry_or_escalate",
                escalation_required=False,
            )

        except Exception as e:
            # Failure
            attempt.state = RecoveryState.FAILED
            attempt.completed_at = datetime.now(UTC)
            attempt.error_message = str(e)

            duration = (attempt.completed_at - attempt.started_at).total_seconds()
            attempt.duration_seconds = duration

            logger.error(f"Recovery failed for {context.source}: {e}")

            # Clean up
            async with self._lock:
                if context.source in self._active_recoveries:
                    del self._active_recoveries[context.source]
                self._add_to_history(context.source, attempt)

            # Log and notify
            await self._log_recovery_attempt(attempt)
            await self._notify_failure(attempt)

            # Check if max attempts reached
            source_history = self._recovery_history.get(context.source, [])
            recent_failures = sum(
                1
                for a in source_history[-self.max_attempts :]
                if a.state == RecoveryState.FAILED
            )

            escalation_required = recent_failures >= self.max_attempts
            if escalation_required:
                await self._escalate(attempt)

            return RecoveryResult(
                success=False,
                attempt=attempt,
                next_action="retry_or_escalate",
                escalation_required=escalation_required,
            )

    def _count_recent_attempts(self, history: list[RecoveryAttempt]) -> int:
        """Count recent recovery attempts (within cooldown window)."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.cooldown_seconds * 10)
        return sum(
            1
            for attempt in history
            if attempt.started_at and attempt.started_at > cutoff
        )

    def _add_to_history(self, source: str, attempt: RecoveryAttempt) -> None:
        """Add attempt to history."""
        if source not in self._recovery_history:
            self._recovery_history[source] = []
        self._recovery_history[source].append(attempt)

        # Keep only last 100 attempts per source
        if len(self._recovery_history[source]) > 100:
            self._recovery_history[source] = self._recovery_history[source][-100:]

    async def _log_recovery_attempt(self, attempt: RecoveryAttempt) -> None:
        """Log recovery attempt to audit log."""
        if self._audit_logger:
            try:
                await self._audit_logger.log_recovery(attempt)
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")

        # Always log to standard logger
        logger.info(
            f"Recovery audit: {attempt.attempt_id} - {attempt.context.source} - "
            f"{attempt.state.value} - attempt {attempt.attempt_number}"
        )

    async def _notify_success(self, attempt: RecoveryAttempt) -> None:
        """Notify success handlers."""
        for handler in self._on_recovery_success:
            try:
                await handler(attempt)
            except Exception as e:
                logger.error(f"Success handler failed: {e}")

    async def _notify_failure(self, attempt: RecoveryAttempt) -> None:
        """Notify failure handlers."""
        for handler in self._on_recovery_failure:
            try:
                await handler(attempt)
            except Exception as e:
                logger.error(f"Failure handler failed: {e}")

    async def _escalate(self, attempt: RecoveryAttempt) -> None:
        """Escalate to human operators."""
        logger.critical(
            f"ESCALATION: Recovery failed for {attempt.context.source} - "
            f"{attempt.attempt_id} - human intervention required"
        )

        for handler in self._on_escalation:
            try:
                await handler(attempt)
            except Exception as e:
                logger.error(f"Escalation handler failed: {e}")

    def get_recovery_history(
        self,
        source: str | None = None,
        limit: int = 50,
    ) -> list[RecoveryAttempt] | dict[str, list[RecoveryAttempt]]:
        """Get recovery history.

        Args:
            source: Filter by source, or None for all
            limit: Maximum history items per source

        Returns:
            Recovery history
        """
        if source:
            history = self._recovery_history.get(source, [])
            return history[-limit:]

        return {
            src: attempts[-limit:] for src, attempts in self._recovery_history.items()
        }

    def get_active_recoveries(self) -> dict[str, RecoveryAttempt]:
        """Get currently active recoveries."""
        return dict(self._active_recoveries)

    def get_recovery_stats(self) -> dict[str, Any]:
        """Get recovery statistics."""
        total_attempts = sum(
            len(attempts) for attempts in self._recovery_history.values()
        )
        successful = sum(
            sum(1 for a in attempts if a.state == RecoveryState.SUCCEEDED)
            for attempts in self._recovery_history.values()
        )
        failed = sum(
            sum(1 for a in attempts if a.state == RecoveryState.FAILED)
            for attempts in self._recovery_history.values()
        )
        escalated = sum(
            sum(1 for a in attempts if a.state == RecoveryState.MAX_ATTEMPTS_REACHED)
            for attempts in self._recovery_history.values()
        )

        return {
            "total_attempts": total_attempts,
            "successful": successful,
            "failed": failed,
            "escalated": escalated,
            "active_recoveries": len(self._active_recoveries),
            "success_rate": successful / total_attempts if total_attempts > 0 else 0.0,
            "max_attempts_config": self.max_attempts,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def clear_history(self, source: str | None = None) -> None:
        """Clear recovery history.

        Args:
            source: Specific source to clear, or None for all
        """
        if source:
            if source in self._recovery_history:
                del self._recovery_history[source]
                logger.info(f"Cleared recovery history for {source}")
        else:
            self._recovery_history.clear()
            logger.info("Cleared all recovery history")
