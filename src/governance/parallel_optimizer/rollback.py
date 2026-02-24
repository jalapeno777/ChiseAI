"""
Rollback Mechanism for Parallel Execution Optimizer (ST-GOV-010).

Provides rollback capabilities for failed batch executions,
allowing safe recovery and retry.

Story: ST-GOV-010
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from src.governance.parallel_optimizer.models import (
    BatchStatus,
    OptimizableTask,
    RollbackResult,
    TaskBatch,
)

logger = logging.getLogger(__name__)


@dataclass
class RollbackCheckpoint:
    """
    A checkpoint that captures state before batch execution.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        batch_id: ID of the batch this checkpoint is for
        timestamp: When the checkpoint was created
        task_states: State of each task before execution
        git_state: Git-related state (branch, commit)
        file_states: Tracked file states before modification
        custom_data: Additional custom checkpoint data
    """

    checkpoint_id: str
    batch_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    task_states: dict[str, str] = field(default_factory=dict)
    git_state: dict[str, str] = field(default_factory=dict)
    file_states: dict[str, str] = field(default_factory=dict)
    custom_data: dict[str, any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize checkpoint to JSON."""
        return json.dumps(
            {
                "checkpoint_id": self.checkpoint_id,
                "batch_id": self.batch_id,
                "timestamp": self.timestamp.isoformat(),
                "task_states": self.task_states,
                "git_state": self.git_state,
                "file_states": self.file_states,
                "custom_data": self.custom_data,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> "RollbackCheckpoint":
        """Deserialize checkpoint from JSON."""
        data = json.loads(json_str)
        return cls(
            checkpoint_id=data["checkpoint_id"],
            batch_id=data["batch_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            task_states=data.get("task_states", {}),
            git_state=data.get("git_state", {}),
            file_states=data.get("file_states", {}),
            custom_data=data.get("custom_data", {}),
        )


# Type for rollback handlers
RollbackHandler = Callable[[OptimizableTask, RollbackCheckpoint], bool]


class RollbackManager:
    """
    Manages rollback operations for failed batch executions.

    Features:
    - Create checkpoints before batch execution
    - Register custom rollback handlers
    - Execute rollback on failure
    - Track rollback history

    Usage:
        manager = RollbackManager()

        # Before execution
        checkpoint = manager.create_checkpoint(batch)

        # On failure
        result = manager.rollback(batch, checkpoint)
        if result.success:
            print("Rollback successful!")
    """

    def __init__(self, redis_client=None):
        """
        Initialize the rollback manager.

        Args:
            redis_client: Optional Redis client for checkpoint persistence
        """
        self.redis_client = redis_client
        self._handlers: dict[str, RollbackHandler] = {}
        self._checkpoints: dict[str, RollbackCheckpoint] = {}
        self._rollback_history: list[RollbackResult] = []

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default rollback handlers for common operations."""
        # Default handler that just logs
        self.register_handler("default", self._default_rollback_handler)

    def _default_rollback_handler(
        self, task: OptimizableTask, checkpoint: RollbackCheckpoint
    ) -> bool:
        """Default rollback handler that logs and returns success."""
        logger.info(
            f"Default rollback for task {task.task_id} (no specific handler registered)"
        )
        return True

    def register_handler(self, task_type: str, handler: RollbackHandler) -> None:
        """
        Register a rollback handler for a specific task type.

        Args:
            task_type: Type identifier for tasks this handler applies to
            handler: Function that performs rollback for this task type
        """
        self._handlers[task_type] = handler
        logger.debug(f"Registered rollback handler for task type: {task_type}")

    def create_checkpoint(
        self,
        batch: TaskBatch,
        git_state: dict[str, str] | None = None,
        file_states: dict[str, str] | None = None,
        custom_data: dict | None = None,
    ) -> RollbackCheckpoint:
        """
        Create a checkpoint before batch execution.

        Args:
            batch: The batch to create a checkpoint for
            git_state: Optional git state (branch, commit)
            file_states: Optional file state tracking
            custom_data: Optional custom data for rollback handlers

        Returns:
            RollbackCheckpoint that can be used for rollback
        """
        import uuid

        checkpoint = RollbackCheckpoint(
            checkpoint_id=f"cp-{batch.batch_id}-{uuid.uuid4().hex[:8]}",
            batch_id=batch.batch_id,
            task_states={task.task_id: "pending" for task in batch.tasks},
            git_state=git_state or {},
            file_states=file_states or {},
            custom_data=custom_data or {},
        )

        self._checkpoints[checkpoint.checkpoint_id] = checkpoint

        # Persist to Redis if available
        if self.redis_client:
            try:
                self.redis_client.hset(
                    "bmad:chiseai:rollback_checkpoints",
                    checkpoint.checkpoint_id,
                    checkpoint.to_json(),
                )
            except Exception as e:
                logger.warning(f"Failed to persist checkpoint to Redis: {e}")

        logger.debug(
            f"Created checkpoint {checkpoint.checkpoint_id} for batch {batch.batch_id}"
        )
        return checkpoint

    def rollback(
        self,
        batch: TaskBatch,
        checkpoint: RollbackCheckpoint | None = None,
        reason: str = "Execution failed",
    ) -> RollbackResult:
        """
        Execute rollback for a failed batch.

        Args:
            batch: The batch to rollback
            checkpoint: Optional checkpoint to use (uses latest if not provided)
            reason: Reason for the rollback

        Returns:
            RollbackResult with outcome details
        """
        # Find checkpoint if not provided
        if checkpoint is None:
            checkpoint = self._find_checkpoint_for_batch(batch.batch_id)

        if checkpoint is None:
            logger.error(
                f"No checkpoint found for batch {batch.batch_id}, cannot rollback"
            )
            return RollbackResult(
                success=False,
                message=f"No checkpoint found for batch {batch.batch_id}",
                rolled_back_tasks=[],
                failed_rollbacks=[t.task_id for t in batch.tasks],
            )

        rolled_back: list[str] = []
        failed: list[str] = []

        for task in batch.tasks:
            # Get the appropriate handler
            task_type = task.metadata.get("task_type", "default")
            handler = self._handlers.get(task_type, self._handlers["default"])

            try:
                success = handler(task, checkpoint)
                if success:
                    rolled_back.append(task.task_id)
                    logger.info(f"Rolled back task {task.task_id}")
                else:
                    failed.append(task.task_id)
                    logger.warning(
                        f"Rollback handler returned False for task {task.task_id}"
                    )
            except Exception as e:
                failed.append(task.task_id)
                logger.error(f"Rollback failed for task {task.task_id}: {e}")

        # Update batch status
        batch.status = BatchStatus.ROLLED_BACK

        # Create result
        result = RollbackResult(
            success=len(failed) == 0,
            rolled_back_tasks=rolled_back,
            failed_rollbacks=failed,
            message=(
                f"Rollback completed: {len(rolled_back)} succeeded, "
                f"{len(failed)} failed. Reason: {reason}"
            ),
        )

        # Record in history
        self._rollback_history.append(result)

        # Clean up checkpoint
        self._cleanup_checkpoint(checkpoint)

        return result

    def _find_checkpoint_for_batch(self, batch_id: str) -> RollbackCheckpoint | None:
        """Find the most recent checkpoint for a batch."""
        for cp in reversed(list(self._checkpoints.values())):
            if cp.batch_id == batch_id:
                return cp
        return None

    def _cleanup_checkpoint(self, checkpoint: RollbackCheckpoint) -> None:
        """Remove a checkpoint after successful rollback."""
        if checkpoint.checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint.checkpoint_id]

        if self.redis_client:
            try:
                self.redis_client.hdel(
                    "bmad:chiseai:rollback_checkpoints",
                    checkpoint.checkpoint_id,
                )
            except Exception as e:
                logger.warning(f"Failed to clean up checkpoint from Redis: {e}")

    def get_rollback_history(self) -> list[RollbackResult]:
        """Get the history of rollback operations."""
        return self._rollback_history.copy()

    def get_rollback_count(self) -> int:
        """Get the total number of rollbacks performed."""
        return len(self._rollback_history)

    def get_rollback_success_rate(self) -> float:
        """
        Calculate the rollback success rate.

        Returns:
            Success rate as percentage (0-100)
        """
        if not self._rollback_history:
            return 100.0

        successful = sum(1 for r in self._rollback_history if r.success)
        return (successful / len(self._rollback_history)) * 100


class BatchRollbackExecutor:
    """
    Executes batches with automatic rollback on failure.

    This class wraps batch execution with checkpoint creation and
    automatic rollback when tasks fail.

    Usage:
        executor = BatchRollbackExecutor(rollback_manager)

        def execute_task(task):
            # Do work
            return True  # Success

        result = executor.execute_batch_with_rollback(
            batch, execute_task
        )
    """

    def __init__(self, rollback_manager: RollbackManager):
        """
        Initialize the batch rollback executor.

        Args:
            rollback_manager: RollbackManager instance to use
        """
        self.rollback_manager = rollback_manager

    def execute_batch_with_rollback(
        self,
        batch: TaskBatch,
        task_executor: Callable[[OptimizableTask], bool],
        stop_on_failure: bool = True,
    ) -> tuple[bool, RollbackResult | None]:
        """
        Execute a batch with automatic rollback on failure.

        Args:
            batch: The batch to execute
            task_executor: Function to execute each task
            stop_on_failure: Whether to stop and rollback on first failure

        Returns:
            Tuple of (success, rollback_result_if_any)
        """
        # Create checkpoint before execution
        checkpoint = self.rollback_manager.create_checkpoint(batch)

        # Mark batch as running
        batch.status = BatchStatus.RUNNING
        batch.started_at = datetime.utcnow()

        failed_tasks: list[OptimizableTask] = []
        completed_task_ids: list[str] = []

        for task in batch.tasks:
            try:
                success = task_executor(task)
                if success:
                    completed_task_ids.append(task.task_id)
                else:
                    failed_tasks.append(task)
                    if stop_on_failure:
                        break
            except Exception as e:
                logger.error(f"Task {task.task_id} raised exception: {e}")
                failed_tasks.append(task)
                if stop_on_failure:
                    break

        # Check if we need to rollback
        if failed_tasks:
            logger.warning(
                f"Batch {batch.batch_id} failed with {len(failed_tasks)} "
                f"failed tasks, initiating rollback"
            )
            rollback_result = self.rollback_manager.rollback(
                batch,
                checkpoint,
                reason=f"{len(failed_tasks)} tasks failed: "
                f"{[t.task_id for t in failed_tasks]}",
            )
            return False, rollback_result

        # Success
        batch.status = BatchStatus.COMPLETED
        batch.completed_at = datetime.utcnow()
        self.rollback_manager._cleanup_checkpoint(checkpoint)

        return True, None
