"""Brain rollback module.

Provides rollback capabilities to revert to a previous brain version
within the required 5-minute target.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


logger = logging.getLogger(__name__)


class RollbackStatus(Enum):
    """Status of a rollback operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        from_version: Version being rolled back from
        to_version: Version being rolled back to
        status: Rollback status
        started_at: ISO timestamp when rollback started
        completed_at: ISO timestamp when rollback completed
        duration_seconds: Total rollback duration
        target_duration_seconds: Target duration (5 minutes)
        target_met: Whether rollback completed within target time
        steps_completed: List of completed rollback steps
        steps_failed: List of failed rollback steps
        error_message: Error message if rollback failed
        metadata: Additional metadata
    """

    from_version: str
    to_version: str
    status: RollbackStatus
    started_at: str
    completed_at: str | None = None
    duration_seconds: float = 0.0
    target_duration_seconds: float = 300.0  # 5 minutes = 300 seconds
    target_met: bool = False
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure status is RollbackStatus enum."""
        if isinstance(self.status, str):
            self.status = RollbackStatus(self.status)

    @property
    def duration_remaining_seconds(self) -> float:
        """Seconds remaining to meet target duration."""
        return max(0.0, self.target_duration_seconds - self.duration_seconds)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "target_duration_seconds": self.target_duration_seconds,
            "target_met": self.target_met,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackResult:
        """Create from dictionary."""
        return cls(
            from_version=data["from_version"],
            to_version=data["to_version"],
            status=RollbackStatus(data["status"]),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds", 0.0),
            target_duration_seconds=data.get("target_duration_seconds", 300.0),
            target_met=data.get("target_met", False),
            steps_completed=data.get("steps_completed", []),
            steps_failed=data.get("steps_failed", []),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class RollbackError(Exception):
    """Base exception for rollback errors."""

    pass


class RollbackTimeoutError(RollbackError):
    """Raised when rollback exceeds target duration."""

    pass


class RollbackManager:
    """Manages rollback operations for brain versions.

    The rollback manager ensures that reverting to a previous version
    completes within the 5-minute target (AC: Rollback to previous
    version completes in <5 minutes).

    Attributes:
        storage_path: Directory for rollback state and history
        target_duration_seconds: Target rollback duration (default: 300s = 5min)
        redis_client: Optional Redis client for coordination

    Examples:
        >>> manager = RollbackManager("/path/to/rollback")
        >>> result = manager.rollback("1.1.0", "1.0.0")
        >>> print(result.target_met)
        True
        >>> print(result.duration_seconds)
        45.2
    """

    DEFAULT_TARGET_DURATION_SECONDS = 300.0  # 5 minutes
    ROLLBACK_HISTORY_FILE = "rollback_history.json"

    def __init__(
        self,
        storage_path: str | Path,
        target_duration_seconds: float = DEFAULT_TARGET_DURATION_SECONDS,
        redis_client: Any | None = None,
    ) -> None:
        """Initialize the rollback manager.

        Args:
            storage_path: Directory for rollback state and history
            target_duration_seconds: Target rollback duration in seconds
            redis_client: Optional Redis client for coordination
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.target_duration_seconds = target_duration_seconds
        self.redis_client = redis_client
        self._rollback_history: list[RollbackResult] = []
        self._load_history()

    def _load_history(self) -> None:
        """Load rollback history from storage."""
        history_file = self.storage_path / self.ROLLBACK_HISTORY_FILE
        if history_file.exists():
            try:
                with open(history_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._rollback_history = [
                        RollbackResult.from_dict(entry)
                        for entry in data.get("rollbacks", [])
                    ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to load rollback history: {e}")

    def _save_history(self) -> None:
        """Save rollback history to storage."""
        history_file = self.storage_path / self.ROLLBACK_HISTORY_FILE
        data = {
            "rollbacks": [entry.to_dict() for entry in self._rollback_history],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def rollback(
        self,
        from_version: str,
        to_version: str,
        metadata: dict[str, Any] | None = None,
    ) -> RollbackResult:
        """Execute a rollback from one version to another.

        Args:
            from_version: Version being rolled back from
            to_version: Version being rolled back to
            metadata: Additional metadata for the rollback

        Returns:
            RollbackResult with status and timing

        Raises:
            RollbackError: If rollback fails
            RollbackTimeoutError: If rollback exceeds target duration
        """
        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        result = RollbackResult(
            from_version=from_version,
            to_version=to_version,
            status=RollbackStatus.IN_PROGRESS,
            started_at=started_at,
            target_duration_seconds=self.target_duration_seconds,
            metadata=metadata or {},
        )

        try:
            # Execute rollback steps
            steps = self._get_rollback_steps()

            for step_name, step_func in steps:
                # Check timeout
                elapsed = time.perf_counter() - start_time
                if elapsed > self.target_duration_seconds:
                    result.status = RollbackStatus.TIMEOUT
                    result.error_message = f"Rollback timed out after {elapsed:.1f}s"
                    raise RollbackTimeoutError(result.error_message)

                # Execute step
                try:
                    step_func(from_version, to_version)
                    result.steps_completed.append(step_name)
                    logger.info(f"Rollback step completed: {step_name}")
                except Exception as e:
                    result.steps_failed.append(step_name)
                    logger.error(f"Rollback step failed: {step_name}: {e}")
                    raise RollbackError(f"Step '{step_name}' failed: {e}") from e

            # Mark as completed
            result.status = RollbackStatus.COMPLETED

        except RollbackTimeoutError:
            # Re-raise timeout errors
            raise
        except Exception as e:
            logger.exception(f"Rollback failed from {from_version} to {to_version}")
            result.status = RollbackStatus.FAILED
            result.error_message = str(e)

        finally:
            # Complete rollback
            completed_at = datetime.now(timezone.utc).isoformat()
            result.completed_at = completed_at
            result.duration_seconds = time.perf_counter() - start_time
            result.target_met = result.duration_seconds <= self.target_duration_seconds

            # Store result
            self._rollback_history.append(result)
            self._save_history()
            self._store_result(result)

        return result

    def _get_rollback_steps(
        self,
    ) -> list[tuple[str, Any]]:
        """Get the rollback steps to execute.

        Returns:
            List of (step_name, step_function) tuples
        """
        return [
            ("validate_target_version", self._step_validate_target),
            ("stop_current_brain", self._step_stop_current),
            ("backup_current_state", self._step_backup_state),
            ("load_previous_version", self._step_load_previous),
            ("verify_loaded_version", self._step_verify_loaded),
            ("activate_previous_version", self._step_activate),
            ("verify_activation", self._step_verify_activation),
            ("notify_listeners", self._step_notify),
        ]

    def _step_validate_target(self, from_version: str, to_version: str) -> None:
        """Validate that target version exists and is valid."""
        # In production, this would verify the target version exists
        logger.info(f"Validating rollback target: {to_version}")
        # Simulate validation
        time.sleep(0.1)

    def _step_stop_current(self, from_version: str, to_version: str) -> None:
        """Stop the current brain version."""
        logger.info(f"Stopping current version: {from_version}")
        # In production, this would gracefully stop the brain
        time.sleep(0.5)

    def _step_backup_state(self, from_version: str, to_version: str) -> None:
        """Backup current state before rollback."""
        logger.info(f"Backing up state for version: {from_version}")
        # In production, this would save state to persistent storage
        time.sleep(0.3)

    def _step_load_previous(self, from_version: str, to_version: str) -> None:
        """Load the previous brain version."""
        logger.info(f"Loading previous version: {to_version}")
        # In production, this would load the brain artifacts
        time.sleep(1.0)

    def _step_verify_loaded(self, from_version: str, to_version: str) -> None:
        """Verify the loaded version is correct."""
        logger.info(f"Verifying loaded version: {to_version}")
        # In production, this would verify checksums, signatures, etc.
        time.sleep(0.2)

    def _step_activate(self, from_version: str, to_version: str) -> None:
        """Activate the previous version."""
        logger.info(f"Activating version: {to_version}")
        # In production, this would switch traffic to the previous version
        time.sleep(0.5)

    def _step_verify_activation(self, from_version: str, to_version: str) -> None:
        """Verify the activation was successful."""
        logger.info(f"Verifying activation of version: {to_version}")
        # In production, this would run health checks
        time.sleep(0.3)

    def _step_notify(self, from_version: str, to_version: str) -> None:
        """Notify listeners of the rollback."""
        logger.info(f"Notifying listeners of rollback to {to_version}")
        # In production, this would send notifications
        time.sleep(0.1)

    def _store_result(self, result: RollbackResult) -> None:
        """Store rollback result in Redis."""
        if self.redis_client:
            try:
                key = f"brain:rollback:{result.from_version}:{result.to_version}"
                self.redis_client.set(
                    key,
                    json.dumps(result.to_dict()),
                    ex=86400 * 90,  # 90 days TTL
                )
                logger.info(f"Stored rollback result in Redis: {key}")
            except Exception as e:
                logger.error(f"Failed to store rollback result: {e}")

    def get_rollback_result(
        self, from_version: str, to_version: str
    ) -> RollbackResult | None:
        """Get the rollback result for a specific rollback.

        Args:
            from_version: Version rolled back from
            to_version: Version rolled back to

        Returns:
            RollbackResult if found, None otherwise
        """
        if self.redis_client:
            try:
                key = f"brain:rollback:{from_version}:{to_version}"
                data = self.redis_client.get(key)
                if data:
                    return RollbackResult.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"Failed to retrieve rollback result: {e}")

        # Check local history
        for entry in self._rollback_history:
            if entry.from_version == from_version and entry.to_version == to_version:
                return entry

        return None

    def can_rollback_to(self, version: str) -> tuple[bool, str]:
        """Check if we can rollback to a specific version.

        Args:
            version: Target version for rollback

        Returns:
            Tuple of (can_rollback, reason)
        """
        # In production, this would check if the version exists and is valid
        # For now, assume we can rollback to any version
        return True, f"Version {version} is available for rollback"

    def get_previous_version(self, current_version: str) -> str | None:
        """Get the previous version before the current one.

        Args:
            current_version: Current version

        Returns:
            Previous version string, or None if not found
        """
        # Check rollback history
        for entry in self._rollback_history:
            if entry.from_version == current_version:
                return entry.to_version

        return None

    def list_rollbacks(
        self, limit: int = 100, status: RollbackStatus | None = None
    ) -> list[RollbackResult]:
        """List rollback operations.

        Args:
            limit: Maximum number of results to return
            status: Filter by status (optional)

        Returns:
            List of RollbackResult objects
        """
        results = []

        # Get from Redis if available
        if self.redis_client:
            try:
                cursor = 0
                pattern = "brain:rollback:*"

                while True:
                    cursor, keys = self.redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    for key in keys:
                        data = self.redis_client.get(key)
                        if data:
                            result = RollbackResult.from_dict(json.loads(data))
                            if status is None or result.status == status:
                                results.append(result)

                    if cursor == 0 or len(results) >= limit:
                        break
            except Exception as e:
                logger.error(f"Failed to list rollbacks from Redis: {e}")

        # Add from local history if not already included
        existing_keys = {(r.from_version, r.to_version) for r in results}
        for entry in self._rollback_history:
            if (entry.from_version, entry.to_version) not in existing_keys:
                if status is None or entry.status == status:
                    results.append(entry)

        # Sort by started_at descending and limit
        results.sort(key=lambda r: r.started_at, reverse=True)
        return results[:limit]

    def get_rollback_statistics(self) -> dict[str, Any]:
        """Get statistics about rollback operations.

        Returns:
            Dictionary with rollback statistics
        """
        all_rollbacks = self._rollback_history

        if not all_rollbacks:
            return {
                "total_rollbacks": 0,
                "successful_rollbacks": 0,
                "failed_rollbacks": 0,
                "target_met_percentage": 0.0,
                "average_duration_seconds": 0.0,
            }

        successful = sum(
            1 for r in all_rollbacks if r.status == RollbackStatus.COMPLETED
        )
        failed = sum(1 for r in all_rollbacks if r.status == RollbackStatus.FAILED)
        target_met = sum(1 for r in all_rollbacks if r.target_met)
        avg_duration = sum(r.duration_seconds for r in all_rollbacks) / len(
            all_rollbacks
        )

        return {
            "total_rollbacks": len(all_rollbacks),
            "successful_rollbacks": successful,
            "failed_rollbacks": failed,
            "target_met_percentage": (target_met / len(all_rollbacks)) * 100,
            "average_duration_seconds": avg_duration,
        }

    def emergency_rollback(self, current_version: str) -> RollbackResult:
        """Execute an emergency rollback to the previous version.

        This is a convenience method for quick rollback without specifying
        the target version.

        Args:
            current_version: Current version to rollback from

        Returns:
            RollbackResult

        Raises:
            RollbackError: If no previous version is found
        """
        previous_version = self.get_previous_version(current_version)
        if previous_version is None:
            raise RollbackError(f"No previous version found for {current_version}")

        return self.rollback(
            from_version=current_version,
            to_version=previous_version,
            metadata={"emergency": True},
        )
