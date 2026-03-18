"""Action execution framework for autonomous cognition.

This module provides the ActionExecutor class which executes actions with:
- Pre-execution validation
- Configurable timeout and retry logic
- Async support for non-blocking execution
- Priority queue integration
- Outcome tracking (success/fail/rollback)
- Comprehensive audit logging
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, TypeVar

from autonomous_cognition.rollback import ActionSnapshot, RollbackManager
from autonomous_cognition.validation import ActionValidator, ValidationResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ActionStatus(Enum):
    """Status of an action execution."""

    PENDING = auto()
    VALIDATING = auto()
    EXECUTING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    ROLLING_BACK = auto()
    ROLLED_BACK = auto()
    TIMEOUT = auto()
    CANCELLED = auto()


class ActionPriority(Enum):
    """Priority levels for action execution."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class ActionOutcome:
    """Outcome of an action execution.

    Attributes:
        action_id: Unique identifier for the action
        status: Final status of the action
        result: The result data if successful
        error: Error message if failed
        execution_time_ms: Time taken to execute in milliseconds
        validation_time_ms: Time taken for validation in milliseconds
        rollback_time_ms: Time taken for rollback if applicable
        audit_log_id: ID of the audit log entry
    """

    action_id: str
    status: ActionStatus
    result: Any = None
    error: str = ""
    execution_time_ms: float = 0.0
    validation_time_ms: float = 0.0
    rollback_time_ms: float = 0.0
    audit_log_id: str = ""

    @property
    def success(self) -> bool:
        """Check if the action succeeded."""
        return self.status == ActionStatus.SUCCEEDED

    @property
    def failed(self) -> bool:
        """Check if the action failed."""
        return self.status in (ActionStatus.FAILED, ActionStatus.TIMEOUT)

    @property
    def rolled_back(self) -> bool:
        """Check if the action was rolled back."""
        return self.status == ActionStatus.ROLLED_BACK


@dataclass
class Action:
    """Definition of an action to be executed.

    Attributes:
        name: Human-readable name of the action
        action_type: Type identifier for the action
        payload: Data required to execute the action
        priority: Priority level for execution ordering
        timeout_seconds: Maximum time allowed for execution
        max_retries: Number of retry attempts on failure
        retry_delay_seconds: Delay between retry attempts
        require_validation: Whether to run pre-execution validation
        enable_rollback: Whether to enable rollback on failure
        metadata: Additional metadata for the action
    """

    name: str
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: ActionPriority = ActionPriority.MEDIUM
    timeout_seconds: float = 30.0
    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    require_validation: bool = True
    enable_rollback: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate action configuration."""
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")


@dataclass(order=True)
class PrioritizedAction:
    """Action wrapper for priority queue.

        Uses priority value for ordering, with tie-breaker by timestamp
    to ensure FIFO ordering for same-priority actions.
    """

    priority_value: int = field(compare=True)
    timestamp: float = field(compare=True)
    action: Action = field(compare=False)
    action_id: str = field(compare=False)
    future: asyncio.Future[ActionOutcome] = field(compare=False)


ActionHandler = Callable[[Action], Any]
AsyncActionHandler = Callable[[Action], Coroutine[Any, Any, Any]]


class ActionExecutor:
    """Executes actions with validation, retry, and rollback support.

    This executor provides:
    - Pre-execution validation via ActionValidator
    - Configurable timeout and retry logic
    - Async execution with priority queues
    - Automatic rollback on failure
    - Comprehensive audit logging
    - <100ms latency target for critical actions

    Example:
        >>> executor = ActionExecutor()
        >>> action = Action(
        ...     name="update_config",
        ...     action_type="config_update",
        ...     payload={"key": "value"},
        ...     priority=ActionPriority.HIGH,
        ... )
        >>> outcome = await executor.execute(action)
        >>> if outcome.success:
        ...     print(f"Success: {outcome.result}")
        >>> else:
        ...     print(f"Failed: {outcome.error}")
    """  # noqa: E501

    def __init__(
        self,
        validator: ActionValidator | None = None,
        rollback_manager: RollbackManager | None = None,
        max_concurrent: int = 10,
        default_timeout: float = 30.0,
        enable_audit_logging: bool = True,
    ):
        """Initialize the action executor.

        Args:
            validator: Validator for pre-execution checks
            rollback_manager: Manager for rollback operations
            max_concurrent: Maximum concurrent executions
            default_timeout: Default timeout in seconds
            enable_audit_logging: Whether to enable audit logging
        """
        self._validator = validator or ActionValidator()
        self._rollback_manager = rollback_manager or RollbackManager()
        self._max_concurrent = max_concurrent
        self._default_timeout = default_timeout
        self._enable_audit_logging = enable_audit_logging

        self._handlers: dict[str, ActionHandler | AsyncActionHandler] = {}
        self._queue: asyncio.PriorityQueue[PrioritizedAction] = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._worker_task: asyncio.Task[None] | None = None
        self._audit_logs: deque[dict[str, Any]] = deque(maxlen=10000)

    def register_handler(
        self,
        action_type: str,
        handler: ActionHandler | AsyncActionHandler,
    ) -> None:
        """Register a handler for an action type.

        Args:
            action_type: The action type to handle
            handler: Sync or async handler function

        Raises:
            ValueError: If handler already registered for action_type
        """
        if action_type in self._handlers:
            raise ValueError(f"Handler already registered for {action_type}")
        self._handlers[action_type] = handler
        logger.debug("Registered handler for action type: %s", action_type)

    def unregister_handler(self, action_type: str) -> None:
        """Unregister a handler for an action type.

        Args:
            action_type: The action type to unregister
        """
        self._handlers.pop(action_type, None)
        logger.debug("Unregistered handler for action type: %s", action_type)

    async def execute(self, action: Action) -> ActionOutcome:
        """Execute an action asynchronously.

        Args:
            action: The action to execute

        Returns:
            ActionOutcome with execution results
        """
        action_id = str(uuid.uuid4())
        future: asyncio.Future[ActionOutcome] = asyncio.get_event_loop().create_future()

        prioritized = PrioritizedAction(
            priority_value=action.priority.value,
            timestamp=time.time(),
            action=action,
            action_id=action_id,
            future=future,
        )

        await self._queue.put(prioritized)
        logger.debug("Queued action %s: %s", action_id, action.name)

        if not self._running:
            self._start_worker()

        return await future

    def execute_sync(self, action: Action) -> ActionOutcome:
        """Execute an action synchronously.

        Args:
            action: The action to execute

        Returns:
            ActionOutcome with execution results
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, use run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(self.execute(action), loop)
                return future.result(timeout=action.timeout_seconds + 5)
            else:
                return loop.run_until_complete(self.execute(action))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.execute(action))

    async def execute_batch(
        self,
        actions: list[Action],
        continue_on_error: bool = True,
    ) -> list[ActionOutcome]:
        """Execute multiple actions as a batch.

        Args:
            actions: List of actions to execute
            continue_on_error: Whether to continue after failures

        Returns:
            List of ActionOutcomes in same order as input
        """
        tasks = [self.execute(action) for action in actions]

        if continue_on_error:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            outcomes: list[ActionOutcome] = []
            for result in results:
                if isinstance(result, Exception):
                    outcomes.append(
                        ActionOutcome(
                            action_id=str(uuid.uuid4()),
                            status=ActionStatus.FAILED,
                            error=str(result),
                        )
                    )
                elif isinstance(result, ActionOutcome):
                    outcomes.append(result)
                else:
                    # Handle unexpected type
                    outcomes.append(
                        ActionOutcome(
                            action_id=str(uuid.uuid4()),
                            status=ActionStatus.FAILED,
                            error=f"Unexpected result type: {type(result)}",
                        )
                    )
            return outcomes
        else:
            results = await asyncio.gather(*tasks)
            # Results should all be ActionOutcome when not continuing on error
            return [
                (
                    r
                    if isinstance(r, ActionOutcome)
                    else ActionOutcome(
                        action_id=str(uuid.uuid4()),
                        status=ActionStatus.FAILED,
                        error=f"Unexpected result type: {type(r)}",
                    )
                )
                for r in results
            ]

    def _start_worker(self) -> None:
        """Start the worker task if not running."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.debug("Started action executor worker")

    async def _worker_loop(self) -> None:
        """Main worker loop processing actions from queue."""
        while self._running:
            prioritized = await self._queue.get()
            outcome: ActionOutcome | None = None
            try:
                async with self._semaphore:
                    outcome = await self._execute_single(
                        prioritized.action,
                        prioritized.action_id,
                    )
            except asyncio.CancelledError:
                # Create failure outcome for cancelled actions
                outcome = ActionOutcome(
                    action_id=prioritized.action_id,
                    status=ActionStatus.CANCELLED,
                    error="Action cancelled due to executor shutdown",
                )
                prioritized.future.set_result(outcome)
                break
            except Exception as e:
                logger.exception("Error in worker loop: %s", e)
                # Create failure outcome for unexpected errors
                outcome = ActionOutcome(
                    action_id=prioritized.action_id,
                    status=ActionStatus.FAILED,
                    error=f"Worker loop error: {str(e)}",
                )
                await asyncio.sleep(0.1)
            finally:
                # Always set the future result if not already set
                if outcome and not prioritized.future.done():
                    prioritized.future.set_result(outcome)

    async def _execute_single(self, action: Action, action_id: str) -> ActionOutcome:
        """Execute a single action with full lifecycle.

        Args:
            action: The action to execute
            action_id: Unique identifier for this execution

        Returns:
            ActionOutcome with execution results
        """
        start_time = time.time()
        validation_time = 0.0
        execution_time = 0.0
        rollback_time = 0.0

        logger.info("Starting execution of action %s: %s", action_id, action.name)

        try:
            # Phase 1: Validation
            if action.require_validation:
                validation_start = time.time()
                validation_result = await self._validate_action(action, action_id)
                validation_time = (time.time() - validation_start) * 1000

                if not validation_result.valid:
                    outcome = ActionOutcome(
                        action_id=action_id,
                        status=ActionStatus.FAILED,
                        error=f"Validation failed: {validation_result.error}",
                        validation_time_ms=validation_time,
                    )
                    await self._log_audit(action, action_id, outcome)
                    return outcome

            # Phase 2: Create snapshot for rollback
            snapshot: ActionSnapshot | None = None
            if action.enable_rollback:
                snapshot = await self._rollback_manager.create_snapshot(
                    action, action_id
                )

            # Phase 3: Execute with retries
            last_error = ""
            for attempt in range(action.max_retries + 1):
                execution_start = time.time()
                try:
                    result = await self._execute_with_timeout(action, action_id)
                    execution_time = (time.time() - execution_start) * 1000

                    outcome = ActionOutcome(
                        action_id=action_id,
                        status=ActionStatus.SUCCEEDED,
                        result=result,
                        execution_time_ms=execution_time,
                        validation_time_ms=validation_time,
                    )
                    await self._log_audit(action, action_id, outcome)

                    total_time = (time.time() - start_time) * 1000
                    logger.info(
                        "Action %s completed successfully in %.2fms "
                        "(validation: %.2fms, execution: %.2fms)",
                        action_id,
                        total_time,
                        validation_time,
                        execution_time,
                    )

                    return outcome

                except TimeoutError:
                    execution_time = (time.time() - execution_start) * 1000
                    last_error = f"Timeout after {action.timeout_seconds}s"
                    logger.warning(
                        "Action %s timed out (attempt %d)", action_id, attempt + 1
                    )

                except Exception as e:
                    execution_time = (time.time() - execution_start) * 1000
                    last_error = str(e)
                    logger.exception(
                        "Action %s failed (attempt %d): %s",
                        action_id,
                        attempt + 1,
                        e,
                    )

                # Retry delay (except on last attempt)
                if attempt < action.max_retries:
                    await asyncio.sleep(action.retry_delay_seconds)

            # All retries exhausted
            outcome = ActionOutcome(
                action_id=action_id,
                status=ActionStatus.FAILED,
                error=last_error,
                execution_time_ms=execution_time,
                validation_time_ms=validation_time,
            )

            # Phase 4: Rollback if enabled
            if action.enable_rollback and snapshot:
                rollback_start = time.time()
                rollback_success = await self._rollback_manager.rollback(snapshot)
                rollback_time = (time.time() - rollback_start) * 1000

                if rollback_success:
                    outcome.status = ActionStatus.ROLLED_BACK
                    outcome.rollback_time_ms = rollback_time
                    logger.info("Action %s rolled back successfully", action_id)
                else:
                    logger.error("Action %s rollback failed", action_id)

            await self._log_audit(action, action_id, outcome)
            return outcome
        finally:
            # Always release the concurrent slot
            self._validator.release_concurrent_slot()

    async def _validate_action(
        self,
        action: Action,
        action_id: str,
    ) -> ValidationResult:
        """Validate an action before execution.

        Args:
            action: The action to validate
            action_id: Unique identifier for this execution

        Returns:
            ValidationResult from the validator
        """
        return await self._validator.validate(action, action_id)

    async def _execute_with_timeout(
        self,
        action: Action,
        action_id: str,
    ) -> Any:
        """Execute action handler with timeout.

        Args:
            action: The action to execute
            action_id: Unique identifier for this execution

        Returns:
            Result from the handler

        Raises:
            TimeoutError: If execution exceeds timeout
            ValueError: If no handler registered for action type
        """
        handler = self._handlers.get(action.action_type)
        if not handler:
            raise ValueError(
                f"No handler registered for action type: {action.action_type}"
            )

        return await asyncio.wait_for(
            self._run_handler(handler, action),
            timeout=action.timeout_seconds,
        )

    async def _run_handler(
        self,
        handler: ActionHandler | AsyncActionHandler,
        action: Action,
    ) -> Any:
        """Run handler (sync or async).

        Args:
            handler: The handler function
            action: The action to process

        Returns:
            Handler result
        """
        if asyncio.iscoroutinefunction(handler):
            return await handler(action)
        else:
            # Run sync handler in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, handler, action)

    async def _log_audit(
        self,
        action: Action,
        action_id: str,
        outcome: ActionOutcome,
    ) -> None:
        """Log action execution to audit trail.

        Args:
            action: The action that was executed
            action_id: Unique identifier for this execution
            outcome: The execution outcome
        """
        if not self._enable_audit_logging:
            return

        audit_entry = {
            "timestamp": time.time(),
            "action_id": action_id,
            "action_name": action.name,
            "action_type": action.action_type,
            "status": outcome.status.name,
            "execution_time_ms": outcome.execution_time_ms,
            "validation_time_ms": outcome.validation_time_ms,
            "rollback_time_ms": outcome.rollback_time_ms,
            "error": outcome.error if outcome.failed else None,
        }

        self._audit_logs.append(audit_entry)  # type: ignore[arg-type]
        logger.debug("Audit log entry created for action %s", action_id)

    def get_audit_logs(
        self,
        action_type: str | None = None,
        status: ActionStatus | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get audit logs with optional filtering.

        Args:
            action_type: Filter by action type
            status: Filter by action status
            limit: Maximum number of logs to return

        Returns:
            List of audit log entries
        """
        logs: list[dict[str, Any]] = list(self._audit_logs)

        if action_type:
            logs = [log for log in logs if log["action_type"] == action_type]

        if status:
            logs = [log for log in logs if log["status"] == status.name]

        return logs[-limit:]

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Shutdown the executor gracefully.

        Args:
            timeout: Time to wait for pending actions
        """
        logger.info("Shutting down action executor...")
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._worker_task, timeout=timeout)

        logger.info("Action executor shutdown complete")

    def __enter__(self) -> ActionExecutor:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        if not self._running:
            return

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.shutdown())
            else:
                loop.run_until_complete(self.shutdown())
        except Exception:
            pass
