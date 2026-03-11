"""State management for checkpoint operations.

This module provides the StateManager class for:
- Managing checkpoint state in Redis
- Tracking checkpoint history
- State transitions
- Rollback state capture
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.governance.checkpoint.gates import GateSummary

logger = logging.getLogger(__name__)


class CheckpointState(Enum):
    """Possible states for a checkpoint."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CheckpointStatus(Enum):
    """Overall status derived from gate results."""

    HEALTHY = "healthy"  # All gates passing
    DEGRADED = "degraded"  # Some gates in CHECK state
    CRITICAL = "critical"  # Some gates failing
    UNKNOWN = "unknown"  # Unable to determine status


@dataclass
class StateTransition:
    """Record of a state transition."""

    from_state: CheckpointState
    to_state: CheckpointState
    timestamp: datetime
    reason: str | None = None
    triggered_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateTransition:
        """Create from dictionary."""
        return cls(
            from_state=CheckpointState(data.get("from_state", "pending")),
            to_state=CheckpointState(data.get("to_state", "pending")),
            timestamp=datetime.fromisoformat(
                data.get("timestamp", datetime.now(UTC).isoformat())
            ),
            reason=data.get("reason"),
            triggered_by=data.get("triggered_by"),
        )


@dataclass
class RollbackState:
    """State captured for potential rollback."""

    checkpoint_id: str
    captured_at: datetime
    system_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "captured_at": self.captured_at.isoformat(),
            "system_state": self.system_state,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackState:
        """Create from dictionary."""
        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            captured_at=datetime.fromisoformat(
                data.get("captured_at", datetime.now(UTC).isoformat())
            ),
            system_state=data.get("system_state", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CheckpointRecord:
    """Complete record of a checkpoint execution."""

    checkpoint_id: str
    state: CheckpointState
    status: CheckpointStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: GateSummary | None = None
    transitions: list[StateTransition] = field(default_factory=list)
    rollback_state: RollbackState | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "state": self.state.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "summary": self._summary_to_dict() if self.summary else None,
            "transitions": [t.to_dict() for t in self.transitions],
            "rollback_state": (
                self.rollback_state.to_dict() if self.rollback_state else None
            ),
            "metadata": self.metadata,
        }

    def _summary_to_dict(self) -> dict[str, Any]:
        """Convert summary to dictionary."""
        if not self.summary:
            return {}
        return {
            "results": [
                {
                    "gate": r.gate,
                    "status": r.status,
                    "detail": r.detail,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in self.summary.results
            ],
            "pass_count": self.summary.pass_count,
            "fail_count": self.summary.fail_count,
            "check_count": self.summary.check_count,
            "timestamp": self.summary.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointRecord:
        """Create from dictionary."""
        from src.governance.checkpoint.gates import GateResult, GateSummary

        summary_data = data.get("summary")
        summary = None
        if summary_data:
            results = [
                GateResult(
                    gate=r["gate"],
                    status=r["status"],
                    detail=r["detail"],
                    timestamp=(
                        datetime.fromisoformat(r["timestamp"])
                        if r.get("timestamp")
                        else None
                    ),
                )
                for r in summary_data.get("results", [])
            ]
            summary = GateSummary(
                results=results,
                pass_count=summary_data.get("pass_count", 0),
                fail_count=summary_data.get("fail_count", 0),
                check_count=summary_data.get("check_count", 0),
                timestamp=datetime.fromisoformat(
                    summary_data.get("timestamp", datetime.now(UTC).isoformat())
                ),
            )

        rollback_data = data.get("rollback_state")
        rollback_state = (
            RollbackState.from_dict(rollback_data) if rollback_data else None
        )

        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            state=CheckpointState(data.get("state", "pending")),
            status=CheckpointStatus(data.get("status", "unknown")),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now(UTC).isoformat())
            ),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            summary=summary,
            transitions=[
                StateTransition.from_dict(t) for t in data.get("transitions", [])
            ],
            rollback_state=rollback_state,
            metadata=data.get("metadata", {}),
        )

    def transition_to(
        self,
        new_state: CheckpointState,
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> None:
        """Record a state transition."""
        transition = StateTransition(
            from_state=self.state,
            to_state=new_state,
            timestamp=datetime.now(UTC),
            reason=reason,
            triggered_by=triggered_by,
        )
        self.transitions.append(transition)
        self.state = new_state

        # Update timestamps based on state
        if new_state == CheckpointState.RUNNING and not self.started_at:
            self.started_at = transition.timestamp
        elif new_state in (CheckpointState.COMPLETED, CheckpointState.FAILED):
            self.completed_at = transition.timestamp


class StateManager:
    """Manages checkpoint state in Redis.

    This class handles:
    - Creating and tracking checkpoint records
    - State transitions with audit trail
    - Rollback state capture
    - Historical checkpoint queries
    """

    # Redis key prefixes
    REDIS_KEY_PREFIX = "bmad:chiseai:checkpoint:state"
    REDIS_RECORDS_KEY = f"{REDIS_KEY_PREFIX}:records"
    REDIS_ACTIVE_KEY = f"{REDIS_KEY_PREFIX}:active"
    REDIS_HISTORY_KEY = f"{REDIS_KEY_PREFIX}:history"
    REDIS_ROLLBACK_KEY = f"{REDIS_KEY_PREFIX}:rollback"

    def __init__(
        self,
        redis_client: Any | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
    ):
        """Initialize the state manager.

        Args:
            redis_client: Optional Redis client instance
            redis_host: Redis host (defaults to env or host.docker.internal)
            redis_port: Redis port (defaults to env or 6380)
        """
        self._redis = redis_client
        self._redis_host = redis_host or os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        self._redis_port = redis_port or int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )

    def _get_redis(self) -> Any | None:
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            return self._redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def _generate_checkpoint_id(self) -> str:
        """Generate unique checkpoint ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"checkpoint-{timestamp}"

    def _determine_status(self, summary: GateSummary | None) -> CheckpointStatus:
        """Determine overall status from gate summary."""
        if not summary:
            return CheckpointStatus.UNKNOWN

        if summary.fail_count > 0:
            return CheckpointStatus.CRITICAL
        elif summary.check_count > 0:
            return CheckpointStatus.DEGRADED
        elif summary.pass_count > 0:
            return CheckpointStatus.HEALTHY
        return CheckpointStatus.UNKNOWN

    def create_checkpoint(
        self,
        checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        """Create a new checkpoint record.

        Args:
            checkpoint_id: Optional checkpoint ID (generated if not provided)
            metadata: Optional metadata to attach

        Returns:
            New CheckpointRecord
        """
        checkpoint_id = checkpoint_id or self._generate_checkpoint_id()

        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            state=CheckpointState.PENDING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )

        # Store in Redis
        self._store_record(record)
        self._set_active_checkpoint(checkpoint_id)

        logger.info(f"Created checkpoint record {checkpoint_id}")
        return record

    def start_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        """Mark a checkpoint as started.

        Args:
            checkpoint_id: ID of the checkpoint to start

        Returns:
            Updated CheckpointRecord if found, None otherwise
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            return None

        record.transition_to(
            CheckpointState.RUNNING, reason="Checkpoint execution started"
        )
        self._store_record(record)

        logger.info(f"Started checkpoint {checkpoint_id}")
        return record

    def complete_checkpoint(
        self,
        checkpoint_id: str,
        summary: GateSummary,
    ) -> CheckpointRecord | None:
        """Mark a checkpoint as completed with results.

        Args:
            checkpoint_id: ID of the checkpoint to complete
            summary: GateSummary with checkpoint results

        Returns:
            Updated CheckpointRecord if found, None otherwise
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            return None

        record.summary = summary
        record.status = self._determine_status(summary)

        if summary.fail_count > 0:
            record.transition_to(
                CheckpointState.FAILED, reason="One or more gates failed"
            )
        else:
            record.transition_to(CheckpointState.COMPLETED, reason="All gates passed")

        self._store_record(record)
        self._add_to_history(record)

        logger.info(
            f"Completed checkpoint {checkpoint_id} with status {record.status.value}"
        )
        return record

    def fail_checkpoint(
        self, checkpoint_id: str, reason: str
    ) -> CheckpointRecord | None:
        """Mark a checkpoint as failed.

        Args:
            checkpoint_id: ID of the checkpoint to fail
            reason: Reason for failure

        Returns:
            Updated CheckpointRecord if found, None otherwise
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            return None

        record.transition_to(CheckpointState.FAILED, reason=reason)
        record.status = CheckpointStatus.CRITICAL

        self._store_record(record)
        self._add_to_history(record)

        logger.info(f"Marked checkpoint {checkpoint_id} as failed: {reason}")
        return record

    def capture_rollback_state(
        self,
        checkpoint_id: str,
        system_state: dict[str, Any] | None = None,
    ) -> RollbackState | None:
        """Capture rollback state for a checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint
            system_state: Optional system state to capture

        Returns:
            RollbackState if captured, None otherwise
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            return None

        rollback = RollbackState(
            checkpoint_id=checkpoint_id,
            captured_at=datetime.now(UTC),
            system_state=system_state or {},
            metadata={"captured_by": "StateManager"},
        )

        record.rollback_state = rollback
        self._store_record(record)
        self._store_rollback_state(rollback)

        logger.info(f"Captured rollback state for checkpoint {checkpoint_id}")
        return rollback

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        """Retrieve a checkpoint record by ID.

        Args:
            checkpoint_id: ID of the checkpoint to retrieve

        Returns:
            CheckpointRecord if found, None otherwise
        """
        r = self._get_redis()
        if not r:
            return None

        try:
            data = r.hget(self.REDIS_RECORDS_KEY, checkpoint_id)
            if data:
                return CheckpointRecord.from_dict(json.loads(data))
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve checkpoint {checkpoint_id}: {e}")
            return None

    def get_active_checkpoint(self) -> CheckpointRecord | None:
        """Get the currently active checkpoint.

        Returns:
            CheckpointRecord if active checkpoint exists, None otherwise
        """
        r = self._get_redis()
        if not r:
            return None

        try:
            checkpoint_id = r.get(self.REDIS_ACTIVE_KEY)
            if checkpoint_id:
                return self.get_checkpoint(checkpoint_id)
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve active checkpoint: {e}")
            return None

    def get_checkpoint_history(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CheckpointRecord]:
        """Get checkpoint history.

        Args:
            limit: Maximum number of records to retrieve
            offset: Offset for pagination

        Returns:
            List of CheckpointRecord objects
        """
        r = self._get_redis()
        if not r:
            return []

        try:
            data_list = r.lrange(self.REDIS_HISTORY_KEY, offset, offset + limit - 1)
            records = []
            for data in data_list:
                try:
                    records.append(CheckpointRecord.from_dict(json.loads(data)))
                except Exception as e:
                    logger.warning(f"Failed to parse history entry: {e}")
            return records
        except Exception as e:
            logger.error(f"Failed to retrieve checkpoint history: {e}")
            return []

    def _store_record(self, record: CheckpointRecord) -> bool:
        """Store a checkpoint record in Redis."""
        r = self._get_redis()
        if not r:
            return False

        try:
            r.hset(
                self.REDIS_RECORDS_KEY,
                record.checkpoint_id,
                json.dumps(record.to_dict()),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store checkpoint record: {e}")
            return False

    def _set_active_checkpoint(self, checkpoint_id: str) -> bool:
        """Set the active checkpoint ID."""
        r = self._get_redis()
        if not r:
            return False

        try:
            r.set(self.REDIS_ACTIVE_KEY, checkpoint_id)
            return True
        except Exception as e:
            logger.error(f"Failed to set active checkpoint: {e}")
            return False

    def _add_to_history(self, record: CheckpointRecord) -> bool:
        """Add a checkpoint to the history list."""
        r = self._get_redis()
        if not r:
            return False

        try:
            r.lpush(self.REDIS_HISTORY_KEY, json.dumps(record.to_dict()))
            r.ltrim(self.REDIS_HISTORY_KEY, 0, 99)  # Keep last 100
            return True
        except Exception as e:
            logger.error(f"Failed to add checkpoint to history: {e}")
            return False

    def _store_rollback_state(self, rollback: RollbackState) -> bool:
        """Store rollback state in Redis."""
        r = self._get_redis()
        if not r:
            return False

        try:
            r.hset(
                self.REDIS_ROLLBACK_KEY,
                rollback.checkpoint_id,
                json.dumps(rollback.to_dict()),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to store rollback state: {e}")
            return False
