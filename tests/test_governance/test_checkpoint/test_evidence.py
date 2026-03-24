"""Tests for checkpoint evidence module.

Tests the EvidenceCollector and CheckpointEvidence classes.

Story: PAPER-GOVERNANCE-001
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.governance.checkpoint.evidence import CheckpointEvidence, EvidenceCollector


class TestCheckpointEvidence:
    """Tests for CheckpointEvidence dataclass."""

    def test_evidence_creation(self, sample_gate_summary):
        """Test creating CheckpointEvidence."""
        now = datetime.now(UTC)
        evidence = CheckpointEvidence(
            checkpoint_id="test-checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
            metadata={"source": "test"},
            archived_path="/path/to/archive.json",
        )

        assert evidence.checkpoint_id == "test-checkpoint-001"
        assert evidence.timestamp == now
        assert evidence.summary == sample_gate_summary
        assert evidence.metadata == {"source": "test"}
        assert evidence.archived_path == "/path/to/archive.json"

    def test_evidence_to_dict(self, sample_gate_summary):
        """Test converting evidence to dictionary."""
        now = datetime.now(UTC)
        evidence = CheckpointEvidence(
            checkpoint_id="test-checkpoint-001",
            timestamp=now,
            summary=sample_gate_summary,
            metadata={"source": "test"},
        )

        data = evidence.to_dict()

        assert data["checkpoint_id"] == "test-checkpoint-001"
        assert data["timestamp"] == now.isoformat()
        assert data["metadata"] == {"source": "test"}
        assert "summary" in data
        assert "results" in data["summary"]

    def test_evidence_from_dict(self):
        """Test creating evidence from dictionary."""
        now = datetime.now(UTC)
        data = {
            "checkpoint_id": "test-checkpoint-001",
            "timestamp": now.isoformat(),
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
            "metadata": {"source": "test"},
            "archived_path": None,
        }

        evidence = CheckpointEvidence.from_dict(data)

        assert evidence.checkpoint_id == "test-checkpoint-001"
        assert evidence.timestamp.isoformat() == now.isoformat()
        assert len(evidence.summary.results) == 1
        assert evidence.summary.results[0].gate == "G1"

    def test_evidence_from_dict_with_none_timestamp(self):
        """Test creating evidence from dict with None timestamps.

        Note: GateResult.__post_init__ sets default timestamp if None,
        so None gets replaced with current time.
        """
        data = {
            "checkpoint_id": "test-checkpoint-001",
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "results": [
                    {
                        "gate": "G1",
                        "status": "✅ PASS",
                        "detail": "Test",
                        "timestamp": None,
                    }
                ],
                "pass_count": 1,
                "fail_count": 0,
                "check_count": 0,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "metadata": {},
            "archived_path": None,
        }

        evidence = CheckpointEvidence.from_dict(data)
        # GateResult.__post_init__ sets a default timestamp if None
        assert evidence.summary.results[0].timestamp is not None


class TestEvidenceCollectorInitialization:
    """Tests for EvidenceCollector initialization."""

    def test_default_initialization(self):
        """Test EvidenceCollector with default values."""
        collector = EvidenceCollector()
        assert collector._redis is None
        assert collector._redis_host is not None
        assert collector._redis_port is not None
        assert collector._archive_dir is not None

    def test_with_redis_client(self, mock_redis_client):
        """Test EvidenceCollector with provided Redis client."""
        collector = EvidenceCollector(redis_client=mock_redis_client)
        assert collector._redis == mock_redis_client

    def test_with_custom_params(self):
        """Test EvidenceCollector with custom parameters."""
        collector = EvidenceCollector(
            redis_host="custom-host",
            redis_port=1234,
            archive_dir="/custom/archive",
        )
        assert collector._redis_host == "custom-host"
        assert collector._redis_port == 1234
        assert collector._archive_dir == "/custom/archive"


class TestEvidenceCollectorCollect:
    """Tests for evidence collection."""

    def test_collect(self, sample_gate_summary):
        """Test collecting evidence from gate summary."""
        collector = EvidenceCollector()

        evidence = collector.collect(
            summary=sample_gate_summary,
            metadata={"trigger": "test"},
        )

        assert evidence.checkpoint_id.startswith("checkpoint-")
        assert evidence.summary == sample_gate_summary
        assert evidence.metadata == {"trigger": "test"}
        assert evidence.timestamp is not None

    def test_collect_without_metadata(self, sample_gate_summary):
        """Test collecting evidence without metadata."""
        collector = EvidenceCollector()

        evidence = collector.collect(summary=sample_gate_summary)

        assert evidence.metadata == {}


class TestEvidenceCollectorStore:
    """Tests for storing evidence in Redis."""

    def test_store_in_redis_success(self, mock_redis_client, sample_gate_summary):
        """Test successful storage in Redis."""
        collector = EvidenceCollector(redis_client=mock_redis_client)
        evidence = collector.collect(summary=sample_gate_summary)

        result = collector.store_in_redis(evidence)

        assert result is True
        mock_redis_client.set.assert_called_once()
        mock_redis_client.lpush.assert_called_once()
        mock_redis_client.ltrim.assert_called_once()

    def test_store_in_redis_no_redis(self, sample_gate_summary):
        """Test storage when Redis is unavailable."""
        collector = EvidenceCollector()
        with patch.object(collector, "_get_redis", return_value=None):
            evidence = collector.collect(summary=sample_gate_summary)
            result = collector.store_in_redis(evidence)

        assert result is False

    def test_store_in_redis_failure(self, mock_redis_client, sample_gate_summary):
        """Test storage when Redis operation fails."""
        mock_redis_client.set.side_effect = Exception("Redis error")
        collector = EvidenceCollector(redis_client=mock_redis_client)
        evidence = collector.collect(summary=sample_gate_summary)

        result = collector.store_in_redis(evidence)

        assert result is False


class TestEvidenceCollectorArchive:
    """Tests for archiving evidence to files."""

    def test_archive_to_file_success(self, tmp_path, sample_gate_summary):
        """Test successful file archiving."""
        archive_dir = tmp_path / "checkpoints"
        collector = EvidenceCollector(archive_dir=str(archive_dir))
        evidence = collector.collect(summary=sample_gate_summary)

        path = collector.archive_to_file(evidence)

        assert path is not None
        assert evidence.archived_path == path
        assert Path(path).exists()
        assert Path(path).suffix == ".json"

    def test_archive_creates_directories(self, tmp_path, sample_gate_summary):
        """Test that archive creates necessary directories."""
        archive_dir = tmp_path / "checkpoints" / "deep" / "nested"
        collector = EvidenceCollector(archive_dir=str(archive_dir))
        evidence = collector.collect(summary=sample_gate_summary)

        path = collector.archive_to_file(evidence)

        assert path is not None
        assert Path(path).parent.exists()

    def test_archive_content(self, tmp_path, sample_gate_summary):
        """Test archived file content."""
        archive_dir = tmp_path / "checkpoints"
        collector = EvidenceCollector(archive_dir=str(archive_dir))
        evidence = collector.collect(summary=sample_gate_summary)

        path = collector.archive_to_file(evidence)

        with open(path) as f:  # type: ignore
            data = json.load(f)

        assert data["checkpoint_id"] == evidence.checkpoint_id
        assert "summary" in data
        assert "results" in data["summary"]


class TestEvidenceCollectorFormat:
    """Tests for evidence formatting."""

    def test_format_for_discord(self, sample_gate_summary):
        """Test Discord formatting."""
        collector = EvidenceCollector()
        evidence = collector.collect(
            summary=sample_gate_summary,
            metadata={"trigger": "scheduled"},
        )

        message = collector.format_for_discord(evidence)

        assert "Burn-in Checkpoint" in message
        assert evidence.checkpoint_id in message
        assert "G1:" in message
        assert "G8:" in message
        assert "scheduled" in message

    def test_format_for_discord_no_metadata(self, sample_gate_summary):
        """Test Discord formatting without metadata."""
        collector = EvidenceCollector()
        evidence = collector.collect(summary=sample_gate_summary)

        message = collector.format_for_discord(evidence)

        # Should not have metadata section
        assert "**Metadata:**" not in message

    def test_format_compact(self, sample_gate_summary):
        """Test compact formatting."""
        collector = EvidenceCollector()
        evidence = collector.collect(summary=sample_gate_summary)

        compact = collector.format_compact(evidence)

        assert evidence.checkpoint_id in compact
        assert "8 pass" in compact

    def test_format_compact_with_failures(self, sample_gate_summary_with_failures):
        """Test compact formatting with failures."""
        collector = EvidenceCollector()
        evidence = collector.collect(summary=sample_gate_summary_with_failures)

        compact = collector.format_compact(evidence)

        assert "1 fail" in compact


class TestEvidenceCollectorRetrieve:
    """Tests for retrieving evidence from Redis."""

    def test_get_latest_from_redis_success(
        self, mock_redis_client, sample_gate_summary
    ):
        """Test retrieving latest evidence."""
        collector = EvidenceCollector(redis_client=mock_redis_client)
        evidence = collector.collect(summary=sample_gate_summary)

        mock_redis_client.get.return_value = json.dumps(evidence.to_dict())

        retrieved = collector.get_latest_from_redis()

        assert retrieved is not None
        assert retrieved.checkpoint_id == evidence.checkpoint_id

    def test_get_latest_from_redis_no_data(self, mock_redis_client):
        """Test retrieving when no data exists."""
        mock_redis_client.get.return_value = None
        collector = EvidenceCollector(redis_client=mock_redis_client)

        retrieved = collector.get_latest_from_redis()

        assert retrieved is None

    def test_get_latest_from_redis_no_redis(self):
        """Test retrieving when Redis is unavailable."""
        collector = EvidenceCollector()
        with patch.object(collector, "_get_redis", return_value=None):
            retrieved = collector.get_latest_from_redis()

        assert retrieved is None

    def test_get_history_from_redis(self, mock_redis_client, sample_gate_summary):
        """Test retrieving evidence history."""
        collector = EvidenceCollector(redis_client=mock_redis_client)
        evidence = collector.collect(summary=sample_gate_summary)

        mock_redis_client.lrange.return_value = [
            json.dumps(evidence.to_dict()),
            json.dumps(evidence.to_dict()),
        ]

        history = collector.get_history_from_redis(limit=2)

        assert len(history) == 2
        assert all(h.checkpoint_id == evidence.checkpoint_id for h in history)

    def test_get_history_from_redis_empty(self, mock_redis_client):
        """Test retrieving empty history."""
        mock_redis_client.lrange.return_value = []
        collector = EvidenceCollector(redis_client=mock_redis_client)

        history = collector.get_history_from_redis()

        assert history == []

    def test_get_history_parse_error(self, mock_redis_client):
        """Test handling parse errors in history."""
        mock_redis_client.lrange.return_value = [
            "invalid json",
            json.dumps(
                {
                    "checkpoint_id": "test",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "summary": {
                        "results": [],
                        "pass_count": 0,
                        "fail_count": 0,
                        "check_count": 0,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    "metadata": {},
                }
            ),
        ]
        collector = EvidenceCollector(redis_client=mock_redis_client)

        history = collector.get_history_from_redis(limit=2)

        # Should skip invalid entry and return valid one
        assert len(history) == 1


class TestEvidenceCollectorCollectAndStore:
    """Tests for collect_and_store convenience method."""

    def test_collect_and_store(self, mock_redis_client, tmp_path, sample_gate_summary):
        """Test complete collect and store flow."""
        collector = EvidenceCollector(
            redis_client=mock_redis_client,
            archive_dir=str(tmp_path),
        )

        evidence = collector.collect_and_store(
            summary=sample_gate_summary,
            metadata={"trigger": "test"},
            archive=True,
        )

        assert evidence.checkpoint_id is not None
        assert evidence.archived_path is not None
        mock_redis_client.set.assert_called_once()
        mock_redis_client.lpush.assert_called_once()

    def test_collect_and_store_no_archive(self, mock_redis_client, sample_gate_summary):
        """Test collect and store without archiving."""
        collector = EvidenceCollector(redis_client=mock_redis_client)

        evidence = collector.collect_and_store(
            summary=sample_gate_summary,
            archive=False,
        )

        assert evidence.checkpoint_id is not None
        assert evidence.archived_path is None
