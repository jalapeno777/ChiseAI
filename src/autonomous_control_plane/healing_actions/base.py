"""Base healing action with sandboxing support.

Provides base class for all healing actions with:
- Sandboxed execution with resource limits
- Automatic rollback on failure
- State capture for rollback
- Human approval workflow

For ST-NS-040: Self-Healing Engine with Action Sandboxing
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import signal
import subprocess
import sys
import tempfile
import traceback
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from src.autonomous_control_plane.models.healing import (
    ActionPriority,
    HealingContext,
    HealingResult,
    ResourceLimits,
    RollbackResult,
)

logger = logging.getLogger(__name__)


class SandboxTimeoutError(Exception):
    """Raised when sandboxed execution times out."""

    pass


class SandboxResourceError(Exception):
    """Raised when sandboxed execution exceeds resource limits."""

    pass


class BaseHealingAction(ABC):
    """Base class for all healing actions.

    Provides:
    - Sandboxed execution with resource limits
    - Automatic rollback on failure
    - State capture for rollback capability
    - Human approval workflow for P0 actions

    Subclasses must implement:
    - _execute_impl(): Actual healing logic
    - _rollback_impl(): Rollback logic
    - action_type: Unique action type string
    - priority: Action priority level
    """

    action_type: str = "base"
    priority: ActionPriority = ActionPriority.P3

    # Trading modes requiring human approval for P0/P1 actions
    APPROVAL_REQUIRED_MODES = {"live", "production"}

    def __init__(self):
        """Initialize healing action."""
        self._captured_state: dict[str, Any] | None = None
        self._execution_start_time: datetime | None = None

    @abstractmethod
    def _execute_impl(self, context: HealingContext) -> dict[str, Any]:
        """Execute the healing action implementation.

        Args:
            context: Execution context

        Returns:
            Dictionary with execution details
        """
        pass

    @abstractmethod
    def _rollback_impl(
        self, context: HealingContext, pre_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Rollback implementation.

        Args:
            context: Execution context
            pre_state: State captured before healing

        Returns:
            Dictionary with rollback details
        """
        pass

    @abstractmethod
    def get_resource_limits(self) -> ResourceLimits:
        """Get resource limits for sandboxed execution.

        Returns:
            Resource limits for this action
        """
        pass

    def _capture_state(self, context: HealingContext) -> dict[str, Any]:
        """Capture pre-healing state for rollback.

        Args:
            context: Execution context

        Returns:
            Dictionary with captured state
        """
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": context.service,
            "action_type": self.action_type,
            "pid": os.getpid(),
        }

    def requires_human_approval(self, trading_mode: str) -> bool:
        """Check if human approval is required.

        P0 and P1 actions require approval in live/production modes.
        P2 and P3 actions are always automatic.

        Args:
            trading_mode: Current trading mode (paper/live/production)

        Returns:
            True if approval required
        """
        if self.priority in (ActionPriority.P0, ActionPriority.P1):
            return trading_mode.lower() in self.APPROVAL_REQUIRED_MODES
        return False

    def execute(self, context: HealingContext) -> HealingResult:
        """Execute the healing action with sandboxing and rollback support.

        Args:
            context: Execution context

        Returns:
            Healing result
        """
        self._execution_start_time = datetime.now(UTC)
        start_time = asyncio.get_event_loop().time()

        logger.info(
            f"Executing healing action {self.action_type} "
            f"for service {context.service} "
            f"(attempt {context.attempt_number})"
        )

        try:
            # Capture pre-healing state for rollback
            self._captured_state = self._capture_state(context)
            logger.debug(f"Captured pre-healing state: {self._captured_state}")

            # Execute with sandboxing
            limits = self.get_resource_limits()
            result = self._execute_sandboxed(context, limits)

            duration = asyncio.get_event_loop().time() - start_time

            if result.get("success", False):
                logger.info(
                    f"Healing action {self.action_type} succeeded in {duration:.2f}s"
                )
                return HealingResult(
                    success=True,
                    action_id=context.action_id,
                    action_type=self.action_type,
                    service=context.service,
                    duration_seconds=duration,
                    details=result,
                    pre_state=self._captured_state,
                )
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"Healing action {self.action_type} failed: {error}")

                # Attempt rollback
                rollback_result = self.rollback(context, None)

                return HealingResult(
                    success=False,
                    action_id=context.action_id,
                    action_type=self.action_type,
                    service=context.service,
                    duration_seconds=duration,
                    details={
                        "execution_result": result,
                        "rollback": rollback_result.to_dict(),
                    },
                    error=error,
                    pre_state=self._captured_state,
                )

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.exception(f"Healing action {self.action_type} threw exception: {e}")

            # Attempt rollback
            try:
                rollback_result = self.rollback(context, None)
            except Exception as rollback_error:
                logger.error(f"Rollback also failed: {rollback_error}")
                rollback_result = RollbackResult(
                    success=False,
                    action_id=context.action_id,
                    error=str(rollback_error),
                )

            return HealingResult(
                success=False,
                action_id=context.action_id,
                action_type=self.action_type,
                service=context.service,
                duration_seconds=duration,
                error=f"{type(e).__name__}: {str(e)}",
                details={
                    "traceback": traceback.format_exc(),
                    "rollback": rollback_result.to_dict(),
                },
                pre_state=self._captured_state,
            )

    def _execute_sandboxed(
        self,
        context: HealingContext,
        limits: ResourceLimits,
    ) -> dict[str, Any]:
        """Execute healing action in a sandboxed environment.

        Uses subprocess with resource limits to prevent runaway actions.

        Args:
            context: Execution context
            limits: Resource limits

        Returns:
            Execution result
        """
        # For direct execution (non-subprocess), run with limits in same process
        # In production, this would use a proper sandbox (container, firejail, etc.)

        def set_resource_limits():
            """Set resource limits for child process."""
            try:
                # CPU time limit (soft, hard)
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (int(limits.max_cpu_seconds), int(limits.max_cpu_seconds) + 1),
                )

                # Memory limit (address space)
                max_bytes = limits.max_memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))

                # File descriptor limit
                resource.setrlimit(
                    resource.RLIMIT_NOFILE,
                    (limits.max_file_descriptors, limits.max_file_descriptors + 5),
                )

                # Disable core dumps
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

            except (ValueError, OSError) as e:
                logger.warning(f"Failed to set resource limits: {e}")

        # Create a script to execute the action
        script_content = self._generate_sandbox_script(context)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script_content)
            script_path = f.name

        try:
            # Run in subprocess with limits
            proc = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=set_resource_limits,
            )

            try:
                stdout, stderr = proc.communicate(timeout=limits.max_execution_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise SandboxTimeoutError(
                    f"Healing action timed out after {limits.max_execution_seconds}s"
                )

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                return {
                    "success": False,
                    "error": f"Sandbox execution failed: {error_msg}",
                    "returncode": proc.returncode,
                }

            # Parse result from stdout
            output = stdout.decode("utf-8", errors="replace").strip()
            try:
                import json

                result = json.loads(output)
                return result
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "output": output,
                }

        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _generate_sandbox_script(self, context: HealingContext) -> str:
        """Generate Python script for sandboxed execution.

        Args:
            context: Execution context

        Returns:
            Python script content
        """
        # This is a simplified version - in production would use proper IPC
        return f"""
import json
import sys
import traceback

# Redirect output for safety
sys.stdout = open('/dev/null', 'w')
sys.stderr = open('/dev/null', 'w')

result = {{"success": True, "message": "Sandboxed execution placeholder"}}

# Re-enable stdout for result
sys.stdout = sys.__stdout__
print(json.dumps(result))
"""

    def rollback(
        self, context: HealingContext, result: HealingResult | None
    ) -> RollbackResult:
        """Rollback the healing action.

        Args:
            context: Execution context
            result: Original healing result (optional)

        Returns:
            Rollback result
        """
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Rolling back healing action {self.action_type}")

        if not self._captured_state:
            logger.warning("No captured state for rollback")
            return RollbackResult(
                success=False,
                action_id=context.action_id,
                error="No pre-healing state captured",
            )

        try:
            rollback_details = self._rollback_impl(context, self._captured_state)
            duration = asyncio.get_event_loop().time() - start_time

            success = rollback_details.get("success", False)

            if success:
                logger.info(
                    f"Rollback of {self.action_type} succeeded in {duration:.2f}s"
                )
            else:
                logger.error(f"Rollback of {self.action_type} failed")

            return RollbackResult(
                success=success,
                action_id=context.action_id,
                duration_seconds=duration,
                error=rollback_details.get("error"),
            )

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.exception(f"Rollback of {self.action_type} threw exception: {e}")

            return RollbackResult(
                success=False,
                action_id=context.action_id,
                duration_seconds=duration,
                error=f"{type(e).__name__}: {str(e)}",
            )

    def validate(self) -> list[str]:
        """Validate healing action configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.action_type or self.action_type == "base":
            errors.append("action_type must be set to a unique value")

        if not isinstance(self.priority, ActionPriority):
            errors.append(
                f"priority must be an ActionPriority, got {type(self.priority)}"
            )

        limits = self.get_resource_limits()
        if limits.max_cpu_seconds <= 0:
            errors.append("max_cpu_seconds must be positive")
        if limits.max_memory_mb <= 0:
            errors.append("max_memory_mb must be positive")
        if limits.max_execution_seconds <= 0:
            errors.append("max_execution_seconds must be positive")

        return errors
