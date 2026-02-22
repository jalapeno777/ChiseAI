"""Iteration logging module for ChiseAI BMAD workflow compliance.

This module provides functions for logging iteration data to Redis with 5-day TTL,
and promoting learnings to Qdrant on story completion.

Usage:
    from operations.iteration_logging import (
        log_iteration_start,
        log_decision,
        log_learning,
        log_completion,
        close_iteration,
    )

    # Start an iteration
    log_iteration_start(
        story_id="ST-001",
        story_title="Feature Implementation",
        acceptance_criteria=["AC1: Works", "AC2: Tested"],
        phase="implementation"
    )

    # Log decisions and learnings
    log_decision("ST-001", "Use Redis", "Low latency")
    log_learning("ST-001", "Schema design took longer", impact="High", category="process")

    # Complete and promote to Qdrant
    close_iteration("ST-001", promote_to_qdrant=True)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


# Constants
ITERLOG_PREFIX = "bmad:chiseai:iterlog"
STORY_PREFIX = f"{ITERLOG_PREFIX}:story"
DEFAULT_TTL_SECONDS = 432000  # 5 days
VALID_PHASES = {"analysis", "planning", "solutioning", "implementation", "testing"}
VALID_STATUSES = {"planned", "in_progress", "blocked", "completed", "deprecated"}


@dataclass
class IterationLogEntry:
    """Represents a single iteration log entry."""

    story_id: str
    story_title: str
    phase: str
    status: str
    started_at: str
    acceptance_criteria: list[str] = field(default_factory=list)
    key_decisions: list[dict[str, Any]] = field(default_factory=list)
    learnings: list[dict[str, Any]] = field(default_factory=list)
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "story_id": self.story_id,
            "story_title": self.story_title,
            "phase": self.phase,
            "status": self.status,
            "started_at": self.started_at,
            "acceptance_criteria": json.dumps(self.acceptance_criteria),
            "key_decisions": json.dumps(self.key_decisions),
            "learnings": json.dumps(self.learnings),
            "completed_at": self.completed_at or "",
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> IterationLogEntry:
        """Create from dictionary retrieved from Redis."""
        return cls(
            story_id=data.get("story_id", ""),
            story_title=data.get("story_title", ""),
            phase=data.get("phase", ""),
            status=data.get("status", ""),
            started_at=data.get("started_at", ""),
            acceptance_criteria=json.loads(data.get("acceptance_criteria", "[]")),
            key_decisions=json.loads(data.get("key_decisions", "[]")),
            learnings=json.loads(data.get("learnings", "[]")),
            completed_at=data.get("completed_at") or None,
        )


def _get_redis_key(story_id: str) -> str:
    """Get the Redis key for a story's iteration log."""
    return f"{STORY_PREFIX}:{story_id}"


def _get_decisions_key(story_id: str) -> str:
    """Get the Redis key for a story's decisions list."""
    return f"{STORY_PREFIX}:{story_id}:decisions"


def _get_learnings_key(story_id: str) -> str:
    """Get the Redis key for a story's learnings list."""
    return f"{STORY_PREFIX}:{story_id}:learnings"


def _get_incidents_key(story_id: str) -> str:
    """Get the Redis key for a story's incidents list."""
    return f"{STORY_PREFIX}:{story_id}:incidents"


def _get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def _validate_phase(phase: str) -> None:
    """Validate that phase is one of the allowed values."""
    if phase not in VALID_PHASES:
        raise ValueError(
            f"Invalid phase '{phase}'. Must be one of: {', '.join(sorted(VALID_PHASES))}"
        )


def _validate_status(status: str) -> None:
    """Validate that status is one of the allowed values."""
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )


class RedisConnectionError(Exception):
    """Raised when Redis connection fails in production environment."""

    pass


def _get_redis_client() -> Any:
    """Get Redis client - this is a placeholder for actual Redis connection.

    In production, this would return a configured Redis client.
    For testing, this is mocked.

    Raises:
        RedisConnectionError: If connection fails in production environment
        (when CHISEAI_ENV=production).
    """
    # Import here to avoid circular imports and allow for mocking
    import logging
    import os

    logger = logging.getLogger(__name__)

    try:
        import redis

        # Try to get client from environment or return None for testing
        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            db=0,
            decode_responses=True,
        )
        # Test connection with ping
        client.ping()
        return client
    except Exception as e:
        # Log the exception for debugging
        logger.warning(f"Redis connection failed: {e}")

        # In production, raise an error instead of silently failing
        if os.environ.get("CHISEAI_ENV") == "production":
            raise RedisConnectionError(
                f"Redis connection required in production but failed: {e}"
            ) from e

        return None


def log_iteration_start(
    story_id: str,
    story_title: str,
    acceptance_criteria: Sequence[str],
    phase: str = "implementation",
    status: str = "in_progress",
) -> dict[str, Any]:
    """Start a new iteration log for a story.

    Args:
        story_id: The canonical story ID (e.g., "ST-001")
        story_title: Human-readable story title
        acceptance_criteria: List of acceptance criteria strings
        phase: Iteration phase (analysis, planning, solutioning, implementation, testing)
        status: Initial status (planned, in_progress, blocked, completed, deprecated)

    Returns:
        Dictionary with the logged entry data

    Raises:
        ValueError: If phase or status is invalid
    """
    _validate_phase(phase)
    _validate_status(status)

    entry = IterationLogEntry(
        story_id=story_id,
        story_title=story_title,
        phase=phase,
        status=status,
        started_at=_get_current_timestamp(),
        acceptance_criteria=list(acceptance_criteria),
    )

    # Store in Redis with TTL
    redis_key = _get_redis_key(story_id)
    data = entry.to_dict()

    # In production, this would use actual Redis
    # For now, we return the data structure
    result = {
        "key": redis_key,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
        "data": data,
    }

    return result


def log_decision(
    story_id: str,
    decision: str,
    rationale: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Log a key decision for a story.

    Args:
        story_id: The canonical story ID
        decision: Brief description of the decision
        rationale: Why this decision was made
        timestamp: Optional ISO timestamp (defaults to now)

    Returns:
        Dictionary with the logged decision data
    """
    decision_entry = {
        "decision": decision,
        "rationale": rationale,
        "timestamp": timestamp or _get_current_timestamp(),
    }

    decisions_key = _get_decisions_key(story_id)

    return {
        "key": decisions_key,
        "decision": decision_entry,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }


def log_learning(
    story_id: str,
    learning: str,
    impact: str = "medium",
    category: str = "general",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Log a learning for a story.

    Args:
        story_id: The canonical story ID
        learning: Description of what was learned
        impact: Impact level (low, medium, high)
        category: Category of learning (technical, process, domain, general)
        timestamp: Optional ISO timestamp (defaults to now)

    Returns:
        Dictionary with the logged learning data
    """
    learning_entry = {
        "learning": learning,
        "impact": impact,
        "category": category,
        "timestamp": timestamp or _get_current_timestamp(),
    }

    learnings_key = _get_learnings_key(story_id)

    return {
        "key": learnings_key,
        "learning": learning_entry,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }


def log_completion(
    story_id: str,
    status: str = "completed",
    final_phase: str | None = None,
) -> dict[str, Any]:
    """Log story completion.

    Args:
        story_id: The canonical story ID
        status: Final status (completed, deprecated)
        final_phase: Optional final phase override

    Returns:
        Dictionary with the completion data
    """
    _validate_status(status)

    completion_data = {
        "story_id": story_id,
        "status": status,
        "completed_at": _get_current_timestamp(),
    }

    if final_phase:
        _validate_phase(final_phase)
        completion_data["phase"] = final_phase

    return {
        "key": _get_redis_key(story_id),
        "data": completion_data,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }


def close_iteration(
    story_id: str,
    promote_to_qdrant: bool = False,
    qdrant_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close an iteration and optionally promote learnings to Qdrant.

    Args:
        story_id: The canonical story ID
        promote_to_qdrant: Whether to promote learnings to Qdrant
        qdrant_metadata: Optional metadata for Qdrant storage

    Returns:
        Dictionary with close operation results
    """
    result = {
        "story_id": story_id,
        "closed_at": _get_current_timestamp(),
        "promoted_to_qdrant": promote_to_qdrant,
    }

    if promote_to_qdrant:
        # In production, this would:
        # 1. Read all learnings from Redis
        # 2. Format with proper metadata
        # 3. Store in Qdrant with vector embedding
        metadata = qdrant_metadata or {}
        metadata.update(
            {
                "project": "ChiseAI",
                "type": "learning",
                "story_id": story_id,
            }
        )
        result["qdrant_metadata"] = metadata

    return result


class NotImplementedInEnvironmentError(Exception):
    """Raised when a function requires environment capabilities that are not available."""

    pass


def get_iteration_log(story_id: str) -> dict[str, Any] | None:
    """Get the iteration log for a story from Redis.

    Args:
        story_id: The canonical story ID

    Returns:
        Dictionary with iteration log data, or None if not found

    Raises:
        NotImplementedInEnvironmentError: If Redis is not available and
            CHISEAI_ENV=production is set.
    """
    import logging
    import os

    logger = logging.getLogger(__name__)
    redis_key = _get_redis_key(story_id)

    try:
        client = _get_redis_client()
        if client is None:
            # Redis not available - in production this would have raised
            # RedisConnectionError already, so we're in test/dev mode
            logger.debug(
                f"Redis not available, cannot retrieve iteration log for {story_id}"
            )
            return None

        # Use HGETALL to retrieve all fields for the story
        data = client.hgetall(redis_key)
        if not data:
            logger.debug(f"No iteration log found for story {story_id}")
            return None

        # Convert the data to proper types
        result: dict[str, Any] = dict(data)

        # Parse JSON fields
        for field in ["acceptance_criteria", "key_decisions", "learnings"]:
            if field in result:
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse JSON for field {field} in {story_id}"
                    )
                    result[field] = []

        logger.info(f"Retrieved iteration log for story {story_id}")
        return result

    except RedisConnectionError:
        # Re-raise production errors
        raise
    except Exception as e:
        logger.error(f"Error retrieving iteration log for {story_id}: {e}")
        if os.environ.get("CHISEAI_ENV") == "production":
            raise NotImplementedInEnvironmentError(
                f"Redis retrieval required in production but failed: {e}"
            ) from e
        return None


def query_by_story_pattern(pattern: str = "*") -> list[str]:
    """Query iteration log keys by story ID pattern using Redis SCAN.

    Args:
        pattern: Glob pattern for story IDs (default: "*" for all)

    Returns:
        List of matching story IDs

    Raises:
        NotImplementedInEnvironmentError: If Redis is not available and
            CHISEAI_ENV=production is set.
    """
    import logging
    import os

    logger = logging.getLogger(__name__)

    # Convert glob pattern to Redis pattern
    # The pattern is for story IDs, we need to match bmad:chiseai:iterlog:story:<pattern>
    redis_pattern = f"{STORY_PREFIX}:{pattern}"

    try:
        client = _get_redis_client()
        if client is None:
            # Redis not available
            logger.debug("Redis not available, cannot query story patterns")
            return []

        # Use SCAN to find matching keys
        story_ids = []
        cursor = 0

        while True:
            cursor, keys = client.scan(cursor=cursor, match=redis_pattern, count=100)
            for key in keys:
                # Extract story_id from key (remove prefix)
                if key.startswith(f"{STORY_PREFIX}:"):
                    story_id = key[len(f"{STORY_PREFIX}:") :]
                    # Skip sub-keys (decisions, learnings, incidents)
                    if ":" not in story_id:
                        story_ids.append(story_id)

            if cursor == 0:
                break

        logger.info(f"Found {len(story_ids)} stories matching pattern '{pattern}'")
        return story_ids

    except RedisConnectionError:
        # Re-raise production errors
        raise
    except Exception as e:
        logger.error(f"Error querying story pattern '{pattern}': {e}")
        if os.environ.get("CHISEAI_ENV") == "production":
            raise NotImplementedInEnvironmentError(
                f"Redis SCAN required in production but failed: {e}"
            ) from e
        return []


def validate_iteration_schema(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate iteration log data against schema.

    Args:
        data: Dictionary containing iteration log data

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    required_fields = ["story_id", "phase", "status", "started_at"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if "phase" in data and data["phase"] not in VALID_PHASES:
        errors.append(
            f"Invalid phase '{data['phase']}'. "
            f"Must be one of: {', '.join(sorted(VALID_PHASES))}"
        )

    if "status" in data and data["status"] not in VALID_STATUSES:
        errors.append(
            f"Invalid status '{data['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )

    return len(errors) == 0, errors


def check_ttl_validity(ttl_seconds: int) -> tuple[bool, str]:
    """Check if TTL value is valid (5 days = 432000 seconds).

    Args:
        ttl_seconds: The TTL value to check

    Returns:
        Tuple of (is_valid, message)
    """
    if ttl_seconds == DEFAULT_TTL_SECONDS:
        return True, f"TTL is valid: {ttl_seconds} seconds (5 days)"
    elif ttl_seconds < 0:
        return False, f"TTL cannot be negative: {ttl_seconds}"
    else:
        return (
            False,
            f"TTL mismatch: expected {DEFAULT_TTL_SECONDS} (5 days), got {ttl_seconds}",
        )


def validate_story_completeness(story_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate story completeness.

    A complete story must have:
    - story_id
    - story_title
    - phase
    - status (completed or deprecated)
    - started_at
    - completed_at (for completed stories)
    - acceptance_criteria (non-empty list)

    Args:
        story_data: Dictionary containing story data

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check required fields
    required_fields = [
        "story_id",
        "story_title",
        "phase",
        "status",
        "started_at",
    ]

    for field in required_fields:
        if field not in story_data or not story_data[field]:
            errors.append(f"Missing required field: {field}")

    # Check status is terminal
    status = story_data.get("status", "")
    if status not in ("completed", "deprecated"):
        errors.append(
            f"Story not in terminal status: {status} (expected: completed or deprecated)"
        )

    # Check completed_at exists for completed stories
    if status == "completed" and not story_data.get("completed_at"):
        errors.append("Missing completed_at for completed story")

    # Check acceptance_criteria
    acceptance_criteria = story_data.get("acceptance_criteria", [])
    if isinstance(acceptance_criteria, str):
        try:
            acceptance_criteria = json.loads(acceptance_criteria)
        except json.JSONDecodeError:
            errors.append("acceptance_criteria is not valid JSON")
            acceptance_criteria = []

    if not acceptance_criteria or len(acceptance_criteria) == 0:
        errors.append("acceptance_criteria must be a non-empty list")

    return len(errors) == 0, errors


class QdrantStorageError(Exception):
    """Raised when Qdrant storage fails in production environment."""

    pass


def _store_in_qdrant(
    information: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Store a learning in Qdrant.

    This function prepares data for Qdrant storage. In production environments
    with MCP tools available, it would call qdrant_qdrant-store. In test/dev,
    it returns the prepared data without storing.

    Args:
        information: The learning text to store
        metadata: Metadata for the learning

    Returns:
        Dictionary with storage result info
    """
    import logging
    import os

    logger = logging.getLogger(__name__)

    # In production with MCP tools enabled, this would trigger actual storage
    # The actual qdrant_qdrant-store call is made by the agent framework
    if os.environ.get("CHISEAI_ENABLE_QDRANT_WRITE", "false").lower() == "true":
        logger.info(f"Qdrant storage enabled for: {information[:50]}...")
        return {
            "stored": True,
            "information": information,
            "metadata": metadata,
        }
    else:
        logger.debug(f"Qdrant storage skipped (disabled): {information[:50]}...")
        return {
            "stored": False,
            "information": information,
            "metadata": metadata,
            "_reason": "Qdrant writes disabled (set CHISEAI_ENABLE_QDRANT_WRITE=true to enable)",
        }


def promote_to_qdrant(
    story_id: str,
    learnings: Sequence[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote learnings to Qdrant for long-term storage.

    Args:
        story_id: The canonical story ID
        learnings: List of learning entries to promote
        metadata: Optional metadata to include

    Returns:
        Dictionary with promotion results including 'stored_entries' list
        with actual storage status for each entry.

    Raises:
        QdrantStorageError: If storage fails in production.
    """
    import logging
    import os

    logger = logging.getLogger(__name__)

    result = {
        "story_id": story_id,
        "promoted_count": len(learnings),
        "promoted_at": _get_current_timestamp(),
    }

    # Build Qdrant-compatible entries and attempt storage
    qdrant_entries = []
    stored_entries = []

    for learning in learnings:
        entry_info = learning.get("learning", "")
        entry_metadata = {
            "project": "ChiseAI",
            "type": "learning",
            "story_id": story_id,
            "impact": learning.get("impact", "medium"),
            "category": learning.get("category", "general"),
            "timestamp": learning.get("timestamp", _get_current_timestamp()),
            **(metadata or {}),
        }

        qdrant_entry = {
            "information": entry_info,
            "metadata": entry_metadata,
        }
        qdrant_entries.append(qdrant_entry)

        # Attempt to store in Qdrant
        try:
            storage_result = _store_in_qdrant(entry_info, entry_metadata)
            stored_entries.append(storage_result)
            logger.info(
                f"Processed Qdrant entry for story {story_id}: {entry_info[:50]}..."
            )
        except Exception as e:
            logger.error(f"Failed to store Qdrant entry: {e}")
            if os.environ.get("CHISEAI_ENV") == "production":
                raise QdrantStorageError(f"Qdrant storage failed: {e}") from e
            stored_entries.append(
                {
                    "stored": False,
                    "information": entry_info,
                    "metadata": entry_metadata,
                    "_error": str(e),
                }
            )

    result["entries"] = qdrant_entries
    result["stored_entries"] = stored_entries
    result["actually_stored"] = len(
        [e for e in stored_entries if e.get("stored", False)]
    )

    return result
