"""Tests for checkpoint state management module.

Tests the StateManager, CheckpointRecord, and state transitions.

Story: PAPER-GOVERNANCE-001
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.governance.checkpoint.gates import GateChecker, GateResult, GateSummary
from src.governance.checkpoint.state import (
    CheckpointRecord,
    CheckpointState,
    CheckpointStatus,
    RollbackState,
    StateManager,
    StateTransition,
)


class TestCheckpointState:
    """Tests for CheckpointState enum."""

    def test_state_values(self):
        """Test state enum values."""
        assert CheckpointState.PENDING.value == "pending"
        assert CheckpointState.RUNNING.value == "running"
        assert CheckpointState.COMPLETED.value == "completed"
        assert CheckpointState.FAILED.value == "failed"
        assert CheckpointState.ROLLED_BACK.value == "rolled_back"


class TestCheckpointStatus:
    """Tests for CheckpointStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert CheckpointStatus.HEALTHY.value == "healthy"
        assert CheckpointStatus.DEGRADED.value == "degraded"
        assert CheckpointStatus.CRITICAL.value == "critical"
        assert CheckpointStatus.UNKNOWN.value == "unknown"


class TestStateTransition:
    """Tests for StateTransition dataclass."""

    def test_transition_creation(self):
        """Test creating a state transition."""
        now = datetime.now(UTC)
        transition = StateTransition(
            from_state=CheckpointState.PENDING,
            to_state=CheckpointState.RUNNING,
            timestamp=now,
            reason="Test transition",
            triggered_by="test",
        )

        assert transition.from_state == CheckpointState.PENDING
        assert transition.to_state == CheckpointState.RUNNING
        assert transition.timestamp == now
        assert transition.reason == "Test transition"
        assert transition.triggered_by == "test"

    def test_transition_to_dict(self):
        """Test converting transition to dictionary."""
        now = datetime.now(UTC)
        transition = StateTransition(
            from_state=CheckpointState.PENDING,
            to_state=CheckpointState.RUNNING,
            timestamp=now,
            reason="Test",
        )

        data = transition.to_dict()

        assert data["from_state"] == "pending"
        assert data["to_state"] == "running"
        assert data["timestamp"] == now.isoformat()
        assert data["reason"] == "Test"
        assert data["triggered_by"] is None

    def test_transition_from_dict(self):
        """Test creating transition from dictionary."""
        now = datetime.now(UTC)
        data = {
            "from_state": "pending",
            "to_state": "running",
            "timestamp": now.isoformat(),
            "reason": "Test",
            "triggered_by": "user",
        }

        transition = StateTransition.from_dict(data)

        assert transition.from_state == CheckpointState.PENDING
        assert transition.to_state == CheckpointState.RUNNING
        assert transition.reason == "Test"
        assert transition.triggered_by == "user"


class TestRollbackState:
    """Tests for RollbackState dataclass."""

    def test_rollback_creation(self):
        """Test creating rollback state."""
        now = datetime.now(UTC)
        rollback = RollbackState(
            checkpoint_id="checkpoint-001",
            captured_at=now,
            system_state={"key": "value"},
            metadata={"source": "test"},
        )

        assert rollback.checkpoint_id == "checkpoint-001"
        assert rollback.captured_at == now
        assert rollback.system_state == {"key": "value"}
        assert rollback.metadata == {"source": "test"}

    def test_rollback_to_dict(self):
        """Test converting rollback to dictionary."""
        now = datetime.now(UTC)
        rollback = RollbackState(
            checkpoint_id="checkpoint-001",
            captured_at=now,
            system_state={"key": "value"},
        )

        data = rollback.to_dict()

        assert data["checkpoint_id"] == "checkpoint-001"
        assert data["captured_at"] == now.isoformat()
        assert data["system_state"] == {"key": "value"}

    def test_rollback_from_dict(self):
        """Test creating rollback from dictionary."""
        now = datetime.now(UTC)
        data = {
            "checkpoint_id": "checkpoint-001",
            "captured_at": now.isoformat(),
            "system_state": {"key": "value"},
            "metadata": {},
        }

        rollback = RollbackState.from_dict(data)

        assert rollback.checkpoint_id == "checkpoint-001"
        assert rollback.system_state == {"key": "value"}


class TestCheckpointRecord:
    """Tests for CheckpointRecord dataclass."""

    def test_record_creation(self):
        """Test creating a checkpoint record."""
        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.PENDING,
            status=CheckpointStatus.UNKNOWN,
            created_at=now,
            metadata={"source": "test"},
        )

        assert record.checkpoint_id == "checkpoint-001"
        assert record.state == CheckpointState.PENDING
        assert record.status == CheckpointStatus.UNKNOWN
        assert record.created_at == now
        assert record.started_at is None
        assert record.completed_at is None
        assert record.transitions == []

    def test_record_to_dict(self):
        """Test converting record to dictionary."""
        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
            completed_at=now,
            metadata={"source": "test"},
        )

        data = record.to_dict()

        assert data["checkpoint_id"] == "checkpoint-001"
        assert data["state"] == "completed"
        assert data["status"] == "healthy"
        assert data["created_at"] == now.isoformat()
        assert data["metadata"] == {"source": "test"}

    def test_record_to_dict_with_summary(self, sample_gate_summary):
        """Test converting record with summary to dictionary."""
        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
            summary=sample_gate_summary,
        )

        data = record.to_dict()

        assert data["summary"] is not None
        assert data["summary"]["pass_count"] == 8

    def test_record_from_dict(self):
        """Test creating record from dictionary."""
        now = datetime.now(UTC)
        data = {
            "checkpoint_id": "checkpoint-001",
            "state": "completed",
            "status": "healthy",
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": now.isoformat(),
            "summary": None,
            "transitions": [],
            "rollback_state": None,
            "metadata": {"source": "test"},
        }

        record = CheckpointRecord.from_dict(data)

        assert record.checkpoint_id == "checkpoint-001"
        assert record.state == CheckpointState.COMPLETED
        assert record.status == CheckpointStatus.HEALTHY
        assert record.metadata == {"source": "test"}

    def test_record_from_dict_with_summary(self):
        """Test creating record from dictionary with summary."""
        now = datetime.now(UTC)
        data = {
            "checkpoint_id": "checkpoint-001",
            "state": "completed",
            "status": "healthy",
            "created_at": now.isoformat(),
            "summary": {
                "results": [
                    {
                        "gate": "G1",
                        "status": "✅ PASS",
                        "detail": "Test",
                        "timestamp": now.isoformat(),
                    }
                ],
                "pass_count": 1,
                "fail_count": 0,
                "check_count": 0,
                "timestamp": now.isoformat(),
            },
            "transitions": [],
            "metadata": {},
        }

        record = CheckpointRecord.from_dict(data)

        assert record.summary is not None
        assert len(record.summary.results) == 1
        assert record.summary.results[0].gate == "G1"

    def test_transition_to_running(self):
        """Test transitioning to running state."""
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.PENDING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
        )

        record.transition_to(CheckpointState.RUNNING, reason="Started")

        assert record.state == CheckpointState.RUNNING
        assert record.started_at is not None
        assert len(record.transitions) == 1
        assert record.transitions[0].to_state == CheckpointState.RUNNING

    def test_transition_to_completed(self):
        """Test transitioning to completed state."""
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.RUNNING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )

        record.transition_to(CheckpointState.COMPLETED, reason="Finished")

        assert record.state == CheckpointState.COMPLETED
        assert record.completed_at is not None

    def test_transition_to_failed(self):
        """Test transitioning to failed state."""
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.RUNNING,
            status=CheckpointStatus.UNKNOWN,
            created_at=datetime.now(UTC),
        )

        record.transition_to(CheckpointState.FAILED, reason="Error occurred")

        assert record.state == CheckpointState.FAILED
        assert record.completed_at is not None


class TestStateManagerInitialization:
    """Tests for StateManager initialization."""

    def test_default_initialization(self):
        """Test StateManager with default values."""
        manager = StateManager()
        assert manager._redis is None
        assert manager._redis_host is not None
        assert manager._redis_port is not None

    def test_with_redis_client(self, mock_redis_client):
        """Test StateManager with provided Redis client."""
        manager = StateManager(redis_client=mock_redis_client)
        assert manager._redis == mock_redis_client


class TestStateManagerCreate:
    """Tests for creating checkpoint records."""

    def test_create_checkpoint(self, mock_redis_client):
        """Test creating a checkpoint record."""
        manager = StateManager(redis_client=mock_redis_client)

        record = manager.create_checkpoint(
            checkpoint_id="custom-id",
            metadata={"source": "test"},
        )

        assert record.checkpoint_id == "custom-id"
        assert record.state == CheckpointState.PENDING
        assert record.status == CheckpointStatus.UNKNOWN
        assert record.metadata == {"source": "test"}
        mock_redis_client.hset.assert_called_once()
        mock_redis_client.set.assert_called_once()

    def test_create_checkpoint_auto_id(self, mock_redis_client):
        """Test creating checkpoint with auto-generated ID."""
        manager = StateManager(redis_client=mock_redis_client)

        record = manager.create_checkpoint()

        assert record.checkpoint_id.startswith("checkpoint-")

    def test_create_checkpoint_no_redis(self):
        """Test creating checkpoint when Redis fails."""
        manager = StateManager()
        manager._redis = None

        record = manager.create_checkpoint(checkpoint_id="test-id")

        assert record.checkpoint_id == "test-id"
        assert record.state == CheckpointState.PENDING


class TestStateManagerStart:
    """Tests for starting checkpoints."""

    def test_start_checkpoint(self, mock_redis_client, sample_checkpoint_record):
        """Test starting a checkpoint."""
        manager = StateManager(redis_client=mock_redis_client)

        # Setup mock to return the record
        mock_redis_client.hget.return_value = json.dumps(
            sample_checkpoint_record.to_dict()
        )

        result = manager.start_checkpoint("checkpoint-001")

        assert result is not None
        assert result.state == CheckpointState.RUNNING
        assert result.started_at is not None

    def test_start_checkpoint_not_found(self, mock_redis_client):
        """Test starting non-existent checkpoint."""
        mock_redis_client.hget.return_value = None
        manager = StateManager(redis_client=mock_redis_client)

        result = manager.start_checkpoint("non-existent")

        assert result is None


class TestStateManagerComplete:
    """Tests for completing checkpoints."""

    def test_complete_checkpoint_success(self, mock_redis_client, sample_gate_summary):
        """Test completing a successful checkpoint."""
        manager = StateManager(redis_client=mock_redis_client)

        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.RUNNING,
            status=CheckpointStatus.UNKNOWN,
            created_at=now,
            started_at=now,
        )
        mock_redis_client.hget.return_value = json.dumps(record.to_dict())

        result = manager.complete_checkpoint("checkpoint-001", sample_gate_summary)

        assert result is not None
        assert result.state == CheckpointState.COMPLETED
        assert result.status == CheckpointStatus.HEALTHY
        assert result.summary == sample_gate_summary

    def test_complete_checkpoint_with_failures(
        self, mock_redis_client, sample_gate_summary_with_failures
    ):
        """Test completing checkpoint with failures."""
        manager = StateManager(redis_client=mock_redis_client)

        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.RUNNING,
            status=CheckpointStatus.UNKNOWN,
            created_at=now,
            started_at=now,
        )
        mock_redis_client.hget.return_value = json.dumps(record.to_dict())

        result = manager.complete_checkpoint(
            "checkpoint-001", sample_gate_summary_with_failures
        )

        assert result is not None
        assert result.state == CheckpointState.FAILED
        assert result.status == CheckpointStatus.CRITICAL


class TestStateManagerFail:
    """Tests for failing checkpoints."""

    def test_fail_checkpoint(self, mock_redis_client):
        """Test failing a checkpoint."""
        manager = StateManager(redis_client=mock_redis_client)

        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.RUNNING,
            status=CheckpointStatus.UNKNOWN,
            created_at=now,
        )
        mock_redis_client.hget.return_value = json.dumps(record.to_dict())

        result = manager.fail_checkpoint("checkpoint-001", "Test failure reason")

        assert result is not None
        assert result.state == CheckpointState.FAILED
        assert result.status == CheckpointStatus.CRITICAL


class TestStateManagerRollback:
    """Tests for rollback state capture."""

    def test_capture_rollback_state(self, mock_redis_client):
        """Test capturing rollback state."""
        manager = StateManager(redis_client=mock_redis_client)

        now = datetime.now(UTC)
        record = CheckpointRecord(
            checkpoint_id="checkpoint-001",
            state=CheckpointState.COMPLETED,
            status=CheckpointStatus.HEALTHY,
            created_at=now,
        )
        mock_redis_client.hget.return_value = json.dumps(record.to_dict())

        rollback = manager.capture_rollback_state(
            "checkpoint-001",
            system_state={"config": "test"},
        )

        assert rollback is not None
        assert rollback.checkpoint_id == "checkpoint-001"
        assert rollback.system_state == {"config": "test"}


class TestStateManagerRetrieve:
    """Tests for retrieving checkpoint records."""

    def test_get_checkpoint(self, mock_redis_client, sample_checkpoint_record):
        """Test retrieving a checkpoint by ID."""
        manager = StateManager(redis_client=mock_redis_client)
        mock_redis_client.hget.return_value = json.dumps(
            sample_checkpoint_record.to_dict()
        )

        result = manager.get_checkpoint("checkpoint-001")

        assert result is not None
        assert result.checkpoint_id == sample_checkpoint_record.checkpoint_id

    def test_get_checkpoint_not_found(self, mock_redis_client):
        """Test retrieving non-existent checkpoint."""
        mock_redis_client.hget.return_value = None
        manager = StateManager(redis_client=mock_redis_client)

        result = manager.get_checkpoint("non-existent")

        assert result is None

    def test_get_active_checkpoint(self, mock_redis_client, sample_checkpoint_record):
        """Test retrieving active checkpoint."""
        manager = StateManager(redis_client=mock_redis_client)
        # Use the sample_checkpoint_record's actual ID
        checkpoint_id = sample_checkpoint_record.checkpoint_id
        mock_redis_client.get.return_value = checkpoint_id
        mock_redis_client.hget.return_value = json.dumps(
            sample_checkpoint_record.to_dict()
        )

        result = manager.get_active_checkpoint()

        assert result is not None
        assert result.checkpoint_id == checkpoint_id

    def test_get_checkpoint_history(self, mock_redis_client, sample_checkpoint_record):
        """Test retrieving checkpoint history."""
        manager = StateManager(redis_client=mock_redis_client)
        mock_redis_client.lrange.return_value = [
            json.dumps(sample_checkpoint_record.to_dict()),
        ]

        history = manager.get_checkpoint_history(limit=1)

        assert len(history) == 1
        assert history[0].checkpoint_id == sample_checkpoint_record.checkpoint_id

    def test_get_checkpoint_history_empty(self, mock_redis_client):
        """Test retrieving empty history."""
        mock_redis_client.lrange.return_value = []
        manager = StateManager(redis_client=mock_redis_client)

        history = manager.get_checkpoint_history()

        assert history == []


class TestStateManagerDetermineStatus:
    """Tests for status determination."""

    def test_determine_status_healthy(self):
        """Test determining healthy status."""
        manager = StateManager()
        now = datetime.now(UTC)
        summary = GateSummary(
            results=[GateResult(gate="G1", status="✅ PASS", detail="", timestamp=now)],
            pass_count=1,
            fail_count=0,
            check_count=0,
            timestamp=now,
        )

        status = manager._determine_status(summary)

        assert status == CheckpointStatus.HEALTHY

    def test_determine_status_degraded(self):
        """Test determining degraded status."""
        manager = StateManager()
        now = datetime.now(UTC)
        summary = GateSummary(
            results=[GateResult(gate="G1", status="⚠️ CHECK", detail="", timestamp=now)],
            pass_count=0,
            fail_count=0,
            check_count=1,
            timestamp=now,
        )

        status = manager._determine_status(summary)

        assert status == CheckpointStatus.DEGRADED

    def test_determine_status_critical(self):
        """Test determining critical status."""
        manager = StateManager()
        now = datetime.now(UTC)
        summary = GateSummary(
            results=[GateResult(gate="G1", status="❌ FAIL", detail="", timestamp=now)],
            pass_count=0,
            fail_count=1,
            check_count=0,
            timestamp=now,
        )

        status = manager._determine_status(summary)

        assert status == CheckpointStatus.CRITICAL

    def test_determine_status_none(self):
        """Test determining status with None summary."""
        manager = StateManager()

        status = manager._determine_status(None)

        assert status == CheckpointStatus.UNKNOWN
