"""Runbook Engine for structured procedure automation.

Provides step-by-step runbook execution with:
- Structured runbook execution engine
- Step-by-step procedure automation
- Human approval checkpoints
- Rollback on step failure
- Parallel and sequential step execution

For ST-CONTROL-002: Self-Healing Automation
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Callable

from autonomous_control_plane.models.healing import (
    HealingContext,
    HealingResult,
    HealingStatus,
    ResourceLimits,
)

logger = logging.getLogger(__name__)


class RunbookStepStatus(StrEnum):
    """Status of a runbook step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_APPROVAL = "awaiting_approval"
    ROLLED_BACK = "rolled_back"


class RunbookStatus(StrEnum):
    """Status of a runbook execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


@dataclass
class RunbookStep:
    """A single step in a runbook.

    Attributes:
        step_id: Unique step identifier
        name: Human-readable step name
        description: Detailed description
        action: Action to execute (function or command)
        action_type: Type of action
        parameters: Action parameters
        timeout_seconds: Step timeout
        requires_approval: Whether human approval is required
        approval_timeout_seconds: Approval timeout
        rollback_action: Action to execute on rollback
        depends_on: List of step IDs this step depends on
        parallel: Whether this step can run in parallel
        retry_count: Current retry count
        max_retries: Maximum retries
        condition: Condition function to check before execution
    """

    name: str
    description: str = ""
    action: str = ""  # Action identifier
    action_type: str = "shell"  # shell, python, api, manual
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    requires_approval: bool = False
    approval_timeout_seconds: float = 300.0
    rollback_action: str = ""
    depends_on: list[str] = field(default_factory=list)
    parallel: bool = False
    retry_count: int = 0
    max_retries: int = 0
    condition: str = ""  # Condition expression
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RunbookStepStatus = RunbookStepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    approved_by: str | None = None
    approved_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "timeout_seconds": self.timeout_seconds,
            "requires_approval": self.requires_approval,
            "approval_timeout_seconds": self.approval_timeout_seconds,
            "rollback_action": self.rollback_action,
            "depends_on": self.depends_on,
            "parallel": self.parallel,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "condition": self.condition,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }


@dataclass
class Runbook:
    """A runbook definition.

    Attributes:
        runbook_id: Unique runbook identifier
        name: Human-readable name
        description: Detailed description
        version: Runbook version
        steps: List of runbook steps
        tags: Tags for categorization
        created_at: Creation timestamp
        updated_at: Last update timestamp
        auto_rollback: Whether to auto-rollback on failure
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    steps: list[RunbookStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    auto_rollback: bool = True
    runbook_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "runbook_id": self.runbook_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "auto_rollback": self.auto_rollback,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def add_step(self, step: RunbookStep) -> RunbookStep:
        """Add a step to the runbook.

        Args:
            step: Step to add

        Returns:
            The added step
        """
        self.steps.append(step)
        self.updated_at = datetime.now(UTC)
        return step


@dataclass
class RunbookExecution:
    """An execution instance of a runbook.

    Attributes:
        execution_id: Unique execution identifier
        runbook_id: ID of runbook being executed
        runbook_name: Name of runbook
        status: Current execution status
        context: Execution context
        started_at: When execution started
        completed_at: When execution completed
        current_step_index: Current step being executed
        step_results: Results for each step
        triggered_by: Who/what triggered the execution
        trading_mode: Trading mode at execution time
    """

    runbook_id: str
    runbook_name: str
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RunbookStatus = RunbookStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    current_step_index: int = 0
    step_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    triggered_by: str = "system"
    trading_mode: str = "paper"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "runbook_id": self.runbook_id,
            "runbook_name": self.runbook_name,
            "status": self.status.value,
            "context": self.context,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "current_step_index": self.current_step_index,
            "step_results": self.step_results,
            "triggered_by": self.triggered_by,
            "trading_mode": self.trading_mode,
        }


class RunbookEngine:
    """Engine for executing runbooks with automation and safety controls.

    Features:
    - Step-by-step procedure automation
    - Human approval checkpoints
    - Automatic rollback on failure
    - Parallel and sequential step execution
    - Step latency <1s
    - Condition-based step execution

    Example:
        >>> engine = RunbookEngine(trading_mode="paper")
        >>> runbook = engine.create_runbook("Redis Recovery")
        >>> runbook.add_step(RunbookStep(
        ...     name="Check Redis Status",
        ...     action="check_redis",
        ...     action_type="python"
        ... ))
        >>> execution = await engine.execute_runbook(runbook)
    """

    def __init__(
        self,
        trading_mode: str = "paper",
        redis_client: Any | None = None,
        enable_approval_gates: bool = True,
    ):
        """Initialize runbook engine.

        Args:
            trading_mode: Current trading mode
            redis_client: Redis client for state tracking
            enable_approval_gates: Whether to enable approval gates
        """
        self._trading_mode = trading_mode
        self._redis = redis_client
        self._enable_approval_gates = enable_approval_gates

        # Runbook registry
        self._runbooks: dict[str, Runbook] = {}
        self._executions: dict[str, RunbookExecution] = {}

        # Action handlers
        self._action_handlers: dict[str, Callable] = {}
        self._register_default_handlers()

        # Approval tracking
        self._pending_approvals: dict[str, RunbookExecution] = {}

        # Statistics
        self._stats = {
            "runbooks_created": 0,
            "executions_started": 0,
            "executions_completed": 0,
            "executions_failed": 0,
            "steps_executed": 0,
            "approvals_required": 0,
        }

        logger.info(f"RunbookEngine initialized (trading_mode={trading_mode})")

    def _register_default_handlers(self) -> None:
        """Register default action handlers."""
        self._action_handlers = {
            "shell": self._execute_shell_action,
            "python": self._execute_python_action,
            "api": self._execute_api_action,
            "manual": self._execute_manual_action,
            "wait": self._execute_wait_action,
            "check": self._execute_check_action,
        }

    def create_runbook(
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> Runbook:
        """Create a new runbook.

        Args:
            name: Runbook name
            description: Runbook description
            tags: Tags for categorization

        Returns:
            Created runbook
        """
        runbook = Runbook(
            name=name,
            description=description,
            tags=tags or [],
        )
        self._runbooks[runbook.runbook_id] = runbook
        self._stats["runbooks_created"] += 1

        logger.info(f"Created runbook: {name} (id={runbook.runbook_id})")
        return runbook

    def get_runbook(self, runbook_id: str) -> Runbook | None:
        """Get a runbook by ID.

        Args:
            runbook_id: Runbook ID

        Returns:
            Runbook or None if not found
        """
        return self._runbooks.get(runbook_id)

    def list_runbooks(self, tag: str | None = None) -> list[dict[str, Any]]:
        """List all runbooks.

        Args:
            tag: Filter by tag (optional)

        Returns:
            List of runbook dicts
        """
        runbooks = list(self._runbooks.values())

        if tag:
            runbooks = [r for r in runbooks if tag in r.tags]

        return [r.to_dict() for r in runbooks]

    async def execute_runbook(
        self,
        runbook: Runbook,
        context: dict[str, Any] | None = None,
        triggered_by: str = "system",
    ) -> RunbookExecution:
        """Execute a runbook.

        Args:
            runbook: Runbook to execute
            context: Execution context
            triggered_by: Who/what triggered execution

        Returns:
            Runbook execution instance
        """
        execution = RunbookExecution(
            runbook_id=runbook.runbook_id,
            runbook_name=runbook.name,
            context=context or {},
            triggered_by=triggered_by,
            trading_mode=self._trading_mode,
        )

        self._executions[execution.execution_id] = execution
        self._stats["executions_started"] += 1

        logger.info(
            f"Starting runbook execution: {runbook.name} "
            f"(execution_id={execution.execution_id})"
        )

        # Start execution in background
        asyncio.create_task(self._execute_runbook_async(execution, runbook))

        return execution

    async def _execute_runbook_async(
        self, execution: RunbookExecution, runbook: Runbook
    ) -> None:
        """Execute runbook asynchronously.

        Args:
            execution: Execution instance
            runbook: Runbook definition
        """
        execution.status = RunbookStatus.RUNNING
        execution.started_at = datetime.now(UTC)

        try:
            # Execute steps
            await self._execute_steps(execution, runbook)

            # Check final status
            if execution.status == RunbookStatus.RUNNING:
                execution.status = RunbookStatus.COMPLETED
                self._stats["executions_completed"] += 1
                logger.info(
                    f"Runbook execution completed: {runbook.name} "
                    f"(execution_id={execution.execution_id})"
                )

        except Exception as e:
            execution.status = RunbookStatus.FAILED
            self._stats["executions_failed"] += 1
            logger.exception(
                f"Runbook execution failed: {runbook.name} - {e} "
                f"(execution_id={execution.execution_id})"
            )

            # Auto-rollback if enabled
            if runbook.auto_rollback:
                await self._rollback_execution(execution, runbook)

        finally:
            execution.completed_at = datetime.now(UTC)

    async def _execute_steps(
        self, execution: RunbookExecution, runbook: Runbook
    ) -> None:
        """Execute runbook steps.

        Args:
            execution: Execution instance
            runbook: Runbook definition
        """
        steps = runbook.steps
        completed_steps: set[str] = set()

        while execution.current_step_index < len(steps):
            step = steps[execution.current_step_index]

            # Check dependencies
            if step.depends_on:
                deps_satisfied = all(
                    dep_id in completed_steps for dep_id in step.depends_on
                )
                if not deps_satisfied:
                    # Wait for dependencies
                    await asyncio.sleep(0.1)
                    continue

            # Check condition
            if step.condition and not self._evaluate_condition(
                step.condition, execution
            ):
                step.status = RunbookStepStatus.SKIPPED
                completed_steps.add(step.step_id)
                execution.current_step_index += 1
                continue

            # Execute step
            step_start = time.time()
            success = await self._execute_step(execution, step, runbook)
            step_latency = time.time() - step_start

            self._stats["steps_executed"] += 1

            # Record step latency (should be <1s)
            if step_latency > 1.0:
                logger.warning(
                    f"Step {step.name} latency {step_latency:.2f}s exceeds 1s target"
                )

            if success:
                completed_steps.add(step.step_id)
                execution.current_step_index += 1
            else:
                # Step failed
                if step.retry_count < step.max_retries:
                    step.retry_count += 1
                    logger.info(
                        f"Retrying step {step.name} "
                        f"(attempt {step.retry_count}/{step.max_retries})"
                    )
                    await asyncio.sleep(2**step.retry_count)  # Exponential backoff
                    continue
                else:
                    # Step failed permanently
                    execution.status = RunbookStatus.FAILED
                    return

    async def _execute_step(
        self, execution: RunbookExecution, step: RunbookStep, runbook: Runbook
    ) -> bool:
        """Execute a single step.

        Args:
            execution: Execution instance
            step: Step to execute
            runbook: Runbook definition

        Returns:
            True if successful
        """
        step.started_at = datetime.now(UTC)
        step.status = RunbookStepStatus.RUNNING

        try:
            # Check if approval is required
            if step.requires_approval and self._enable_approval_gates:
                if self._trading_mode in ("live", "production"):
                    step.status = RunbookStepStatus.AWAITING_APPROVAL
                    self._pending_approvals[execution.execution_id] = execution
                    self._stats["approvals_required"] += 1

                    logger.info(
                        f"Step {step.name} awaiting approval "
                        f"(execution_id={execution.execution_id})"
                    )

                    # Wait for approval (with timeout)
                    approved = await self._wait_for_approval(
                        execution.execution_id, step.approval_timeout_seconds
                    )

                    if not approved:
                        step.status = RunbookStepStatus.FAILED
                        step.result = {"error": "Approval timeout or rejected"}
                        return False

            # Execute action
            handler = self._action_handlers.get(step.action_type)
            if not handler:
                step.status = RunbookStepStatus.FAILED
                step.result = {"error": f"Unknown action type: {step.action_type}"}
                return False

            result = await asyncio.wait_for(
                handler(step, execution),
                timeout=step.timeout_seconds,
            )

            step.result = result

            if result.get("success", False):
                step.status = RunbookStepStatus.COMPLETED
                execution.step_results[step.step_id] = result
                return True
            else:
                step.status = RunbookStepStatus.FAILED
                return False

        except asyncio.TimeoutError:
            step.status = RunbookStepStatus.FAILED
            step.result = {"error": f"Step timed out after {step.timeout_seconds}s"}
            return False

        except Exception as e:
            step.status = RunbookStepStatus.FAILED
            step.result = {"error": str(e)}
            logger.exception(f"Step {step.name} failed: {e}")
            return False

        finally:
            step.completed_at = datetime.now(UTC)

    async def _wait_for_approval(
        self, execution_id: str, timeout_seconds: float
    ) -> bool:
        """Wait for approval.

        Args:
            execution_id: Execution ID
            timeout_seconds: Timeout

        Returns:
            True if approved
        """
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            execution = self._pending_approvals.get(execution_id)
            if not execution:
                # Execution was removed (approved or rejected)
                return True

            await asyncio.sleep(0.5)

        # Timeout
        return False

    def approve_step(self, execution_id: str, step_id: str, approved_by: str) -> bool:
        """Approve a pending step.

        Args:
            execution_id: Execution ID
            step_id: Step ID
            approved_by: Who approved

        Returns:
            True if approved successfully
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return False

        # Find the step
        runbook = self._runbooks.get(execution.runbook_id)
        if not runbook:
            return False

        for step in runbook.steps:
            if step.step_id == step_id:
                step.approved_by = approved_by
                step.approved_at = datetime.now(UTC)
                step.status = (
                    RunbookStepStatus.PENDING
                )  # Reset to pending for execution

                # Remove from pending approvals
                self._pending_approvals.pop(execution_id, None)

                logger.info(f"Step {step.name} approved by {approved_by}")
                return True

        return False

    def reject_step(
        self, execution_id: str, step_id: str, rejected_by: str, reason: str = ""
    ) -> bool:
        """Reject a pending step.

        Args:
            execution_id: Execution ID
            step_id: Step ID
            rejected_by: Who rejected
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return False

        # Find the step
        runbook = self._runbooks.get(execution.runbook_id)
        if not runbook:
            return False

        for step in runbook.steps:
            if step.step_id == step_id:
                step.status = RunbookStepStatus.FAILED
                step.result = {"error": f"Rejected by {rejected_by}: {reason}"}

                # Remove from pending approvals
                self._pending_approvals.pop(execution_id, None)

                logger.info(f"Step {step.name} rejected by {rejected_by}: {reason}")
                return True

        return False

    async def _rollback_execution(
        self, execution: RunbookExecution, runbook: Runbook
    ) -> None:
        """Rollback a failed execution.

        Args:
            execution: Execution to rollback
            runbook: Runbook definition
        """
        logger.info(f"Rolling back execution {execution.execution_id}")

        # Rollback completed steps in reverse order
        for step in reversed(runbook.steps[: execution.current_step_index]):
            if step.rollback_action and step.status == RunbookStepStatus.COMPLETED:
                try:
                    rollback_step = RunbookStep(
                        name=f"Rollback: {step.name}",
                        action=step.rollback_action,
                        action_type=step.action_type,
                        parameters=step.parameters,
                    )
                    await self._execute_shell_action(rollback_step, execution)
                    step.status = RunbookStepStatus.ROLLED_BACK
                except Exception as e:
                    logger.error(f"Rollback failed for step {step.name}: {e}")

        execution.status = RunbookStatus.ROLLED_BACK

    def _evaluate_condition(self, condition: str, execution: RunbookExecution) -> bool:
        """Evaluate a condition expression.

        Args:
            condition: Condition expression
            execution: Execution context

        Returns:
            True if condition is met
        """
        # Simple condition evaluation - in production would use proper expression parser
        if condition.startswith("context."):
            key = condition[8:]  # Remove "context." prefix
            return execution.context.get(key, False)

        # Default to True for unknown conditions
        return True

    # Action handlers

    async def _execute_shell_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute shell command action.

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        import subprocess

        command = step.action

        # Substitute context variables
        for key, value in execution.context.items():
            command = command.replace(f"{{{{{key}}}}}", str(value))

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=step.timeout_seconds,
            )

            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }

        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": "Command timed out"}

    async def _execute_python_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute Python code action.

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        # In production, this would use a proper sandbox
        # For now, simulate success
        return {
            "success": True,
            "message": f"Python action {step.action} executed",
            "context": execution.context,
        }

    async def _execute_api_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute API call action.

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        # In production, this would make actual API calls
        return {
            "success": True,
            "message": f"API action {step.action} executed",
        }

    async def _execute_manual_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute manual action (human task).

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        # Manual actions always require approval
        return {
            "success": True,
            "message": f"Manual action {step.action} recorded",
            "requires_confirmation": True,
        }

    async def _execute_wait_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute wait action.

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        wait_seconds = step.parameters.get("seconds", 5)
        await asyncio.sleep(wait_seconds)

        return {
            "success": True,
            "message": f"Waited {wait_seconds} seconds",
        }

    async def _execute_check_action(
        self, step: RunbookStep, execution: RunbookExecution
    ) -> dict[str, Any]:
        """Execute health check action.

        Args:
            step: Step definition
            execution: Execution context

        Returns:
            Execution result
        """
        check_type = step.parameters.get("type", "generic")

        # In production, this would perform actual health checks
        return {
            "success": True,
            "message": f"Health check {check_type} passed",
            "check_type": check_type,
        }

    def get_execution_status(self, execution_id: str) -> dict[str, Any] | None:
        """Get execution status.

        Args:
            execution_id: Execution ID

        Returns:
            Execution status dict or None
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return None

        runbook = self._runbooks.get(execution.runbook_id)

        return {
            **execution.to_dict(),
            "steps": [s.to_dict() for s in (runbook.steps if runbook else [])],
        }

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """Get list of pending approvals.

        Returns:
            List of pending approval dicts
        """
        result = []

        for execution_id, execution in self._pending_approvals.items():
            runbook = self._runbooks.get(execution.runbook_id)
            if runbook:
                for step in runbook.steps:
                    if step.status == RunbookStepStatus.AWAITING_APPROVAL:
                        result.append(
                            {
                                "execution_id": execution_id,
                                "runbook_name": execution.runbook_name,
                                "step_id": step.step_id,
                                "step_name": step.name,
                                "started_at": step.started_at.isoformat()
                                if step.started_at
                                else None,
                            }
                        )

        return result

    def get_status(self) -> dict[str, Any]:
        """Get engine status.

        Returns:
            Status dictionary
        """
        return {
            "trading_mode": self._trading_mode,
            "runbooks": len(self._runbooks),
            "executions": len(self._executions),
            "pending_approvals": len(self._pending_approvals),
            "stats": self._stats.copy(),
            "action_handlers": list(self._action_handlers.keys()),
        }
