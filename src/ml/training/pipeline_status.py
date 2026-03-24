"""Training Pipeline Status Tracking with Redis.

Provides Redis-based status tracking for training pipelines.
Follows the pattern: bmad:chiseai:training:{pipeline_id}:status

Status values: pending, running, completed, failed

For ST-LAUNCH-012: Training Pipeline Integration
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    """Status values for training pipeline.

    Values:
        PENDING: Pipeline is queued but not started
        RUNNING: Pipeline is currently executing
        COMPLETED: Pipeline finished successfully
        FAILED: Pipeline failed with error
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# Redis key prefix for training pipeline status
REDIS_KEY_PREFIX = "bmad:chiseai:training"


def _get_redis_key(pipeline_id: str) -> str:
    """Generate Redis key for pipeline status.

    Args:
        pipeline_id: Unique pipeline identifier

    Returns:
        Redis key string
    """
    return f"{REDIS_KEY_PREFIX}:{pipeline_id}:status"


def _get_redis_helpers():
    """Get Redis helper functions with fallback.

    Returns:
        Tuple of (hset, hget, hgetall, hdel) functions or None
    """
    try:
        from redis_state import (
            redis_state_hdel,
            redis_state_hget,
            redis_state_hgetall,
            redis_state_hset,
        )

        return redis_state_hset, redis_state_hget, redis_state_hgetall, redis_state_hdel
    except ImportError:
        try:
            from tools.redis_state import (
                redis_state_hdel,
                redis_state_hget,
                redis_state_hgetall,
                redis_state_hset,
            )

            return (
                redis_state_hset,
                redis_state_hget,
                redis_state_hgetall,
                redis_state_hdel,
            )
        except ImportError:
            logger.warning("Redis state tools not available")
            return None, None, None, None


def set_pipeline_status(
    pipeline_id: str,
    status: PipelineStatus | str,
    metadata: dict[str, Any] | None = None,
    expire_seconds: int | None = None,
) -> bool:
    """Set the status of a training pipeline.

    Args:
        pipeline_id: Unique pipeline identifier
        status: Pipeline status (PipelineStatus enum or string)
        metadata: Optional metadata to store with status
        expire_seconds: Optional TTL for the Redis key

    Returns:
        True if successful, False otherwise
    """
    hset, _, _, _ = _get_redis_helpers()
    if hset is None:
        logger.warning("Cannot set pipeline status: Redis not available")
        return False

    key = _get_redis_key(pipeline_id)

    # Convert status to string if enum
    status_value = status.value if isinstance(status, PipelineStatus) else status

    # Build data payload
    data = {
        "status": status_value,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    if metadata:
        data["metadata"] = json.dumps(metadata)

    try:
        # Store each field
        for field, value in data.items():
            if expire_seconds:
                hset(key, field, value, expire_seconds=expire_seconds)
            else:
                hset(key, field, value)

        logger.debug(f"Set pipeline {pipeline_id} status to {status_value}")
        return True
    except Exception as e:
        logger.error(f"Failed to set pipeline status: {e}")
        return False


def get_pipeline_status(pipeline_id: str) -> dict[str, Any] | None:
    """Get the status of a training pipeline.

    Args:
        pipeline_id: Unique pipeline identifier

    Returns:
        Dictionary with status info or None if not found
    """
    _, _, hgetall, _ = _get_redis_helpers()
    if hgetall is None:
        logger.warning("Cannot get pipeline status: Redis not available")
        return None

    key = _get_redis_key(pipeline_id)

    try:
        data = hgetall(key)
        if not data:
            return None

        # Parse metadata if present
        result = dict(data)
        if "metadata" in result:
            with contextlib.suppress(json.JSONDecodeError):
                result["metadata"] = json.loads(result["metadata"])

        return result
    except Exception as e:
        logger.error(f"Failed to get pipeline status: {e}")
        return None


def get_pipeline_status_value(pipeline_id: str) -> str | None:
    """Get just the status value of a training pipeline.

    Args:
        pipeline_id: Unique pipeline identifier

    Returns:
        Status string (pending, running, completed, failed) or None
    """
    status_info = get_pipeline_status(pipeline_id)
    if status_info:
        return status_info.get("status")
    return None


def delete_pipeline_status(pipeline_id: str) -> bool:
    """Delete the status entry for a training pipeline.

    Args:
        pipeline_id: Unique pipeline identifier

    Returns:
        True if successful or not found, False on error
    """
    _, _, _, hdel = _get_redis_helpers()
    if hdel is None:
        logger.warning("Cannot delete pipeline status: Redis not available")
        return False

    key = _get_redis_key(pipeline_id)

    try:
        # Delete common fields
        for field in ["status", "updated_at", "metadata"]:
            hdel(key, field)
        return True
    except Exception as e:
        logger.error(f"Failed to delete pipeline status: {e}")
        return False


def is_pipeline_active(pipeline_id: str) -> bool:
    """Check if a pipeline is currently active (pending or running).

    Args:
        pipeline_id: Unique pipeline identifier

    Returns:
        True if pipeline is pending or running
    """
    status = get_pipeline_status_value(pipeline_id)
    return status in (PipelineStatus.PENDING.value, PipelineStatus.RUNNING.value)


def list_pipeline_statuses() -> dict[str, dict[str, Any]]:
    """List all pipeline statuses (requires Redis scan).

    Note: This is a potentially expensive operation.

    Returns:
        Dictionary mapping pipeline_id to status info
    """
    try:
        from redis_state import redis_state_scan_keys
    except ImportError:
        try:
            from tools.redis_state import redis_state_scan_keys
        except ImportError:
            logger.warning("Cannot list pipeline statuses: Redis not available")
            return {}

    try:
        # Scan for keys matching the pattern
        pattern = f"{REDIS_KEY_PREFIX}:*:status"
        keys = redis_state_scan_keys(pattern=pattern)

        results = {}
        for key in keys:
            # Extract pipeline_id from key
            parts = key.split(":")
            if len(parts) >= 4:
                pipeline_id = parts[3]
                status_info = get_pipeline_status(pipeline_id)
                if status_info:
                    results[pipeline_id] = status_info

        return results
    except Exception as e:
        logger.error(f"Failed to list pipeline statuses: {e}")
        return {}


class PipelineStatusTracker:
    """Context manager for tracking pipeline status.

    Automatically sets status to running on enter and
    completed/failed on exit based on success.

    Example:
        with PipelineStatusTracker("my-pipeline"):
            # Pipeline execution code here
            run_training()
    """

    def __init__(
        self,
        pipeline_id: str,
        metadata: dict[str, Any] | None = None,
        expire_seconds: int = 86400,  # 24 hours default
    ):
        """Initialize status tracker.

        Args:
            pipeline_id: Unique pipeline identifier
            metadata: Optional metadata to store
            expire_seconds: TTL for Redis keys
        """
        self.pipeline_id = pipeline_id
        self.metadata = metadata or {}
        self.expire_seconds = expire_seconds

    def __enter__(self) -> PipelineStatusTracker:
        """Set status to running when entering context."""
        set_pipeline_status(
            self.pipeline_id,
            PipelineStatus.RUNNING,
            metadata=self.metadata,
            expire_seconds=self.expire_seconds,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Set status to completed or failed when exiting context."""
        if exc_type is None:
            # Success
            set_pipeline_status(
                self.pipeline_id,
                PipelineStatus.COMPLETED,
                metadata=self.metadata,
                expire_seconds=self.expire_seconds,
            )
        else:
            # Failure
            error_metadata = {
                **self.metadata,
                "error": str(exc_val),
                "error_type": exc_type.__name__ if exc_type else None,
            }
            set_pipeline_status(
                self.pipeline_id,
                PipelineStatus.FAILED,
                metadata=error_metadata,
                expire_seconds=self.expire_seconds,
            )
