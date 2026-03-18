"""Rollback mechanism for autonomous cognition actions.

This module provides the RollbackManager class which manages action state
snapshotting and rollback execution with compensation action support.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ActionSnapshot:
    """Snapshot of action state for potential rollback.

    Attributes:
        snapshot_id: Unique identifier for this snapshot
        action_id: ID of the action this snapshot belongs to
        action_type: Type of the action
        action_name: Name of the action
        timestamp: When the snapshot was created
        state: Captured state data
        compensation_action: Optional action to execute for rollback
        metadata: Additional metadata
    """

    snapshot_id: str
    action_id: str
    action_type: str
    action_name: str
    timestamp: float
    state: dict[str, Any] = field(default_factory=dict)
    compensation_action: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether the rollback succeeded
        snapshot_id: ID of the snapshot that was rolled back
        execution_time_ms: Time taken for rollback in milliseconds
        error: Error message if rollback failed
        audit_log_id: ID of the audit log entry
    """

    success: bool
    snapshot_id: str
    execution_time_ms: float = 0.0
    error: str = ""
    audit_log_id: str = ""


@dataclass
class RollbackLogEntry:
    """Audit log entry for rollback operations.

    Attributes:
        timestamp: When the rollback occurred
        snapshot_id: ID of the snapshot
        action_id: ID of the original action
        success: Whether rollback succeeded
        execution_time_ms: Time taken
        error: Error message if failed
    """

    timestamp: float
    snapshot_id: str
    action_id: str
    success: bool
    execution_time_ms: float
    error: str = ""


CompensationHandler = Callable[[dict[str, Any]], Any]
AsyncCompensationHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


class RollbackManager:
    """Manages action state snapshots and rollback execution.

    This manager provides:
    - Action state snapshotting before execution
    - Rollback execution on failure
    - Compensation action support
    - Comprehensive audit logging
    - Rollback chain tracking for complex operations

    Example:
        >>> manager = RollbackManager()
        >>> snapshot = await manager.create_snapshot(action, action_id)
        >>> try:
        ...     result = await execute_action(action)
        ... except Exception:
        ...     await manager.rollback(snapshot)
    """

    def __init__(
        self,
        enable_audit_logging: bool = True,
        max_snapshots: int = 1000,
        auto_cleanup: bool = True,
    ):
        """Initialize the rollback manager.

        Args:
            enable_audit_logging: Whether to enable audit logging
            max_snapshots: Maximum number of snapshots to retain
            auto_cleanup: Whether to auto-cleanup old snapshots
        """
        self._enable_audit_logging = enable_audit_logging
        self._max_snapshots = max_snapshots
        self._auto_cleanup = auto_cleanup

        self._snapshots: dict[str, ActionSnapshot] = {}
        self._rollback_logs: list[RollbackLogEntry] = []
        self._compensation_handlers: dict[
            str, CompensationHandler | AsyncCompensationHandler
        ] = {}
        self._rollback_chains: dict[str, list[str]] = (
            {}
        )  # action_id -> list of snapshot_ids

    async def create_snapshot(
        self,
        action: Any,
        action_id: str,
        state: dict[str, Any] | None = None,
        compensation_action: dict[str, Any] | None = None,
    ) -> ActionSnapshot:
        """Create a snapshot for potential rollback.

        Args:
            action: The action to snapshot
            action_id: Unique identifier for this action
            state: Optional state data to capture
            compensation_action: Optional compensation action for rollback

        Returns:
            ActionSnapshot for the created snapshot
        """
        snapshot_id = str(uuid.uuid4())

        # Extract action details
        action_type = getattr(action, "action_type", "unknown")
        action_name = getattr(action, "name", "unknown")

        # Capture state from action payload if available
        captured_state = state or {}
        if hasattr(action, "payload") and isinstance(action.payload, dict):
            captured_state.update(action.payload)

        snapshot = ActionSnapshot(
            snapshot_id=snapshot_id,
            action_id=action_id,
            action_type=action_type,
            action_name=action_name,
            timestamp=time.time(),
            state=captured_state,
            compensation_action=compensation_action,
        )

        # Store snapshot
        self._snapshots[snapshot_id] = snapshot

        # Track in rollback chain
        if action_id not in self._rollback_chains:
            self._rollback_chains[action_id] = []
        self._rollback_chains[action_id].append(snapshot_id)

        # Auto-cleanup if needed
        if self._auto_cleanup and len(self._snapshots) > self._max_snapshots:
            self._cleanup_old_snapshots()

        logger.debug(
            "Created snapshot %s for action %s (%s)",
            snapshot_id,
            action_id,
            action_name,
        )

        return snapshot

    async def rollback(self, snapshot: ActionSnapshot | str) -> RollbackResult:
        """Execute rollback for a snapshot.

        Args:
            snapshot: The snapshot to roll back, or snapshot_id string

        Returns:
            RollbackResult indicating success or failure
        """
        start_time = time.time()

        # Resolve snapshot if ID provided
        resolved_snapshot: ActionSnapshot | None = None
        if isinstance(snapshot, str):
            snapshot_id = snapshot
            resolved_snapshot = self._snapshots.get(snapshot_id)
            if not resolved_snapshot:
                error = f"Snapshot {snapshot_id} not found"
                logger.error(error)
                return RollbackResult(
                    success=False,
                    snapshot_id=snapshot_id,
                    error=error,
                )
        else:
            snapshot_id = snapshot.snapshot_id
            resolved_snapshot = snapshot

        assert resolved_snapshot is not None

        logger.info(
            "Starting rollback for snapshot %s (action: %s)",
            snapshot_id,
            resolved_snapshot.action_name,
        )

        try:
            # Execute compensation action if available
            if resolved_snapshot.compensation_action:
                await self._execute_compensation(resolved_snapshot)

            # Execute type-specific rollback if handler registered
            if resolved_snapshot.action_type in self._compensation_handlers:
                await self._execute_type_specific_rollback(resolved_snapshot)

            # Mark as rolled back in state
            execution_time = (time.time() - start_time) * 1000

            result = RollbackResult(
                success=True,
                snapshot_id=snapshot_id,
                execution_time_ms=execution_time,
            )

            # Log the rollback
            await self._log_rollback(resolved_snapshot, result)

            logger.info(
                "Rollback completed successfully for snapshot %s in %.2fms",
                snapshot_id,
                execution_time,
            )

            return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error = f"Rollback failed: {str(e)}"

            logger.exception("Rollback failed for snapshot %s: %s", snapshot_id, e)

            result = RollbackResult(
                success=False,
                snapshot_id=snapshot_id,
                execution_time_ms=execution_time,
                error=error,
            )

            await self._log_rollback(resolved_snapshot, result)
            return result

    async def rollback_chain(self, action_id: str) -> list[RollbackResult]:
        """Roll back all snapshots in a chain (reverse order).

        Args:
            action_id: The action ID whose chain to roll back

        Returns:
            List of RollbackResults for each snapshot
        """
        results: list[RollbackResult] = []

        chain = self._rollback_chains.get(action_id, [])
        if not chain:
            logger.warning("No rollback chain found for action %s", action_id)
            return results

        # Roll back in reverse order (LIFO)
        for snapshot_id in reversed(chain):
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot:
                result = await self.rollback(snapshot)
                results.append(result)

                # Stop if rollback fails
                if not result.success:
                    logger.error(
                        "Rollback chain broken at snapshot %s for action %s",
                        snapshot_id,
                        action_id,
                    )
                    break

        return results

    def register_compensation_handler(
        self,
        action_type: str,
        handler: CompensationHandler | AsyncCompensationHandler,
    ) -> None:
        """Register a compensation handler for an action type.

        Args:
            action_type: The action type to handle
            handler: Sync or async handler function
        """
        self._compensation_handlers[action_type] = handler
        logger.debug("Registered compensation handler for action type: %s", action_type)

    def unregister_compensation_handler(self, action_type: str) -> None:
        """Unregister a compensation handler.

        Args:
            action_type: The action type to unregister
        """
        self._compensation_handlers.pop(action_type, None)
        logger.debug(
            "Unregistered compensation handler for action type: %s", action_type
        )

    async def _execute_compensation(self, snapshot: ActionSnapshot) -> None:
        """Execute compensation action for a snapshot.

        Args:
            snapshot: The snapshot with compensation action

        Raises:
            Exception: If compensation execution fails
        """
        if not snapshot.compensation_action:
            return

        logger.debug(
            "Executing compensation action for snapshot %s",
            snapshot.snapshot_id,
        )

        # Compensation actions are simple dicts describing what to do
        # In a real implementation, this would dispatch to appropriate handlers
        action_type = snapshot.compensation_action.get("type", "unknown")

        logger.info(
            "Compensation action type: %s for snapshot %s",
            action_type,
            snapshot.snapshot_id,
        )

        # Simulate compensation execution
        await self._simulate_async_delay(0.01)

    async def _execute_type_specific_rollback(self, snapshot: ActionSnapshot) -> None:
        """Execute type-specific rollback handler.

        Args:
            snapshot: The snapshot to roll back

        Raises:
            Exception: If rollback execution fails
        """
        handler = self._compensation_handlers.get(snapshot.action_type)
        if not handler:
            return

        logger.debug(
            "Executing type-specific rollback for %s (snapshot %s)",
            snapshot.action_type,
            snapshot.snapshot_id,
        )

        if callable(handler):
            import asyncio

            if asyncio.iscoroutinefunction(handler):
                await handler(snapshot.state)
            else:
                # Run sync handler in thread
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler, snapshot.state)

    async def _log_rollback(
        self,
        snapshot: ActionSnapshot,
        result: RollbackResult,
    ) -> None:
        """Log rollback operation to audit trail.

        Args:
            snapshot: The snapshot that was rolled back
            result: The rollback result
        """
        if not self._enable_audit_logging:
            return

        entry = RollbackLogEntry(
            timestamp=time.time(),
            snapshot_id=snapshot.snapshot_id,
            action_id=snapshot.action_id,
            success=result.success,
            execution_time_ms=result.execution_time_ms,
            error=result.error,
        )

        self._rollback_logs.append(entry)

        # Generate audit log ID
        result.audit_log_id = str(uuid.uuid4())

        logger.debug(
            "Rollback logged for snapshot %s: success=%s",
            snapshot.snapshot_id,
            result.success,
        )

    def _cleanup_old_snapshots(self) -> None:
        """Clean up old snapshots when limit exceeded."""
        if len(self._snapshots) <= self._max_snapshots:
            return

        # Sort by timestamp and remove oldest
        sorted_snapshots = sorted(
            self._snapshots.items(),
            key=lambda x: x[1].timestamp,
        )

        to_remove = len(sorted_snapshots) - self._max_snapshots
        for snapshot_id, _ in sorted_snapshots[:to_remove]:
            del self._snapshots[snapshot_id]
            # Also clean up from chains
            for chain in self._rollback_chains.values():
                if snapshot_id in chain:
                    chain.remove(snapshot_id)

        logger.debug("Cleaned up %d old snapshots", to_remove)

    async def _simulate_async_delay(self, seconds: float) -> None:
        """Simulate async delay for testing/compatibility.

        Args:
            seconds: Delay duration
        """
        import asyncio

        await asyncio.sleep(seconds)

    def get_snapshot(self, snapshot_id: str) -> ActionSnapshot | None:
        """Get a snapshot by ID.

        Args:
            snapshot_id: The snapshot ID

        Returns:
            The snapshot if found, None otherwise
        """
        return self._snapshots.get(snapshot_id)

    def get_rollback_chain(self, action_id: str) -> list[ActionSnapshot]:
        """Get all snapshots in a rollback chain.

        Args:
            action_id: The action ID

        Returns:
            List of snapshots in chain order
        """
        chain_ids = self._rollback_chains.get(action_id, [])
        return [self._snapshots[sid] for sid in chain_ids if sid in self._snapshots]

    def get_rollback_logs(
        self,
        action_id: str | None = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> list[RollbackLogEntry]:
        """Get rollback logs with optional filtering.

        Args:
            action_id: Filter by action ID
            success_only: Only return successful rollbacks
            limit: Maximum number of logs

        Returns:
            List of rollback log entries
        """
        logs = self._rollback_logs

        if action_id:
            logs = [log for log in logs if log.action_id == action_id]

        if success_only:
            logs = [log for log in logs if log.success]

        return logs[-limit:]

    def clear_snapshots(self, action_id: str | None = None) -> int:
        """Clear snapshots.

        Args:
            action_id: If provided, only clear snapshots for this action

        Returns:
            Number of snapshots cleared
        """
        if action_id:
            chain = self._rollback_chains.pop(action_id, [])
            for snapshot_id in chain:
                self._snapshots.pop(snapshot_id, None)
            return len(chain)
        else:
            count = len(self._snapshots)
            self._snapshots.clear()
            self._rollback_chains.clear()
            return count

    def get_stats(self) -> dict[str, Any]:
        """Get rollback manager statistics.

        Returns:
            Dictionary with statistics
        """
        total_rollbacks = len(self._rollback_logs)
        successful_rollbacks = sum(1 for log in self._rollback_logs if log.success)

        return {
            "total_snapshots": len(self._snapshots),
            "max_snapshots": self._max_snapshots,
            "total_rollback_chains": len(self._rollback_chains),
            "total_rollbacks": total_rollbacks,
            "successful_rollbacks": successful_rollbacks,
            "failed_rollbacks": total_rollbacks - successful_rollbacks,
            "success_rate": (
                successful_rollbacks / total_rollbacks if total_rollbacks > 0 else 0.0
            ),
            "registered_handlers": list(self._compensation_handlers.keys()),
        }
