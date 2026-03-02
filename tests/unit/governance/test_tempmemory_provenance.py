"""
Unit tests for tempmemory provenance tracking.

Tests the ProvenanceTracker class and related functionality.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from governance.tempmemory.provenance import (
    ProvenanceRecord,
    ProvenanceChain,
    ProvenanceSource,
    ProvenanceTracker,
    get_current_commit_sha,
    compute_content_hash,
)


class TestProvenanceRecord:
    """Test ProvenanceRecord dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        record = ProvenanceRecord(
            memory_id="test-memory",
            source_type="tempmemory_file",
            source_path="docs/tempmemories/test.md",
            commit_sha="abc123",
            timestamp="2026-03-01T00:00:00Z",
            agent="test-agent",
            story_id="ST-TEST-001",
            content_hash="hash123",
            parent_ids=["parent-1", "parent-2"],
            metadata={"key": "value"},
        )

        data = record.to_dict()

        assert data["memory_id"] == "test-memory"
        assert data["source_type"] == "tempmemory_file"
        assert data["source_path"] == "docs/tempmemories/test.md"
        assert data["commit_sha"] == "abc123"
        assert data["timestamp"] == "2026-03-01T00:00:00Z"
        assert data["agent"] == "test-agent"
        assert data["story_id"] == "ST-TEST-001"
        assert data["content_hash"] == "hash123"
        assert data["parent_ids"] == ["parent-1", "parent-2"]
        assert data["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "story_id": "ST-TEST-001",
            "content_hash": "hash123",
            "parent_ids": ["parent-1"],
            "metadata": {"key": "value"},
        }

        record = ProvenanceRecord.from_dict(data)

        assert record.memory_id == "test-memory"
        assert record.source_type == "tempmemory_file"
        assert record.story_id == "ST-TEST-001"

    def test_create(self):
        """Test creating a new record with auto-generated fields."""
        with patch(
            "governance.tempmemory.provenance.get_current_commit_sha",
            return_value="abc123",
        ):
            record = ProvenanceRecord.create(
                memory_id="test-memory",
                source_type=ProvenanceSource.TEMPMEMORY_FILE,
                source_path="docs/tempmemories/test.md",
                agent="test-agent",
                content="Test content",
                story_id="ST-TEST-001",
            )

        assert record.memory_id == "test-memory"
        assert record.source_type == "tempmemory_file"
        assert record.commit_sha == "abc123"
        assert record.agent == "test-agent"
        assert record.story_id == "ST-TEST-001"
        assert record.content_hash == compute_content_hash("Test content")
        assert record.timestamp is not None


class TestProvenanceChain:
    """Test ProvenanceChain dataclass."""

    def test_get_origin(self):
        """Test getting the origin record."""
        chain = ProvenanceChain(memory_id="test")

        record1 = ProvenanceRecord.create(
            memory_id="parent",
            source_type=ProvenanceSource.TEMPMEMORY_FILE,
            source_path="parent.md",
            agent="agent1",
        )
        record2 = ProvenanceRecord.create(
            memory_id="child",
            source_type=ProvenanceSource.MIGRATION_IMPORT,
            source_path="child.md",
            agent="agent2",
        )

        chain.chain = [record1, record2]

        origin = chain.get_origin()
        assert origin.memory_id == "parent"

    def test_get_latest(self):
        """Test getting the latest record."""
        chain = ProvenanceChain(memory_id="test")

        record1 = ProvenanceRecord.create(
            memory_id="parent",
            source_type=ProvenanceSource.TEMPMEMORY_FILE,
            source_path="parent.md",
            agent="agent1",
        )
        record2 = ProvenanceRecord.create(
            memory_id="child",
            source_type=ProvenanceSource.MIGRATION_IMPORT,
            source_path="child.md",
            agent="agent2",
        )

        chain.chain = [record1, record2]

        latest = chain.get_latest()
        assert latest.memory_id == "child"

    def test_empty_chain(self):
        """Test with empty chain."""
        chain = ProvenanceChain(memory_id="test")

        assert chain.get_origin() is None
        assert chain.get_latest() is None


class TestProvenanceTracker:
    """Test ProvenanceTracker class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.hset.return_value = True
        redis.expire.return_value = True
        redis.sadd.return_value = True
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create a ProvenanceTracker instance."""
        return ProvenanceTracker(redis_client=mock_redis, dry_run=False)

    def test_init(self, tracker, mock_redis):
        """Test initialization."""
        assert tracker._redis_client == mock_redis
        assert tracker._dry_run is False

    def test_record_provenance(self, tracker, mock_redis):
        """Test recording provenance."""
        with patch(
            "governance.tempmemory.provenance.get_current_commit_sha",
            return_value="abc123",
        ):
            record = tracker.record_provenance(
                memory_id="test-memory",
                source_type=ProvenanceSource.TEMPMEMORY_FILE,
                source_path="docs/tempmemories/test.md",
                agent="test-agent",
                content="Test content",
                story_id="ST-TEST-001",
            )

        assert record is not None
        assert record.memory_id == "test-memory"
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()

    def test_record_provenance_dry_run(self, mock_redis):
        """Test recording provenance in dry-run mode."""
        tracker = ProvenanceTracker(redis_client=mock_redis, dry_run=True)

        record = tracker.record_provenance(
            memory_id="test-memory",
            source_type=ProvenanceSource.TEMPMEMORY_FILE,
            source_path="docs/tempmemories/test.md",
            agent="test-agent",
        )

        assert record is not None
        mock_redis.hset.assert_not_called()

    def test_get_provenance(self, tracker, mock_redis):
        """Test retrieving provenance."""
        record_data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "story_id": "ST-TEST-001",
            "content_hash": "hash123",
            "parent_ids": json.dumps(["parent-1"]),
            "metadata": json.dumps({"key": "value"}),
        }
        mock_redis.hgetall.return_value = record_data

        record = tracker.get_provenance("test-memory")

        assert record is not None
        assert record.memory_id == "test-memory"

    def test_get_provenance_chain(self, tracker, mock_redis):
        """Test retrieving provenance chain."""
        record_data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "story_id": "ST-TEST-001",
            "content_hash": "hash123",
            "parent_ids": json.dumps([]),
            "metadata": json.dumps({}),
        }
        mock_redis.lrange.return_value = [json.dumps(record_data)]

        chain = tracker.get_provenance_chain("test-memory")

        assert chain.memory_id == "test-memory"
        assert len(chain.chain) == 1

    def test_query_by_source(self, tracker, mock_redis):
        """Test querying by source type."""
        mock_redis.smembers.return_value = {b"memory-1", b"memory-2"}

        memory_ids = tracker.query_by_source(ProvenanceSource.TEMPMEMORY_FILE)

        assert len(memory_ids) == 2
        assert "memory-1" in memory_ids
        assert "memory-2" in memory_ids

    def test_query_by_story(self, tracker, mock_redis):
        """Test querying by story ID."""
        mock_redis.smembers.return_value = {b"memory-1", b"memory-2"}

        memory_ids = tracker.query_by_story("ST-TEST-001")

        assert len(memory_ids) == 2
        assert "memory-1" in memory_ids

    def test_verify_integrity(self, tracker, mock_redis):
        """Test content integrity verification."""
        content = "Test content"
        content_hash = compute_content_hash(content)

        record_data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "content_hash": content_hash,
            "parent_ids": json.dumps([]),
            "metadata": json.dumps({}),
        }
        mock_redis.hgetall.return_value = record_data

        is_valid = tracker.verify_integrity("test-memory", content)

        assert is_valid is True

    def test_verify_integrity_invalid(self, tracker, mock_redis):
        """Test content integrity verification with invalid content."""
        record_data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "content_hash": "wrong-hash",
            "parent_ids": json.dumps([]),
            "metadata": json.dumps({}),
        }
        mock_redis.hgetall.return_value = record_data

        is_valid = tracker.verify_integrity("test-memory", "Different content")

        assert is_valid is False

    def test_generate_audit_report(self, tracker, mock_redis):
        """Test generating audit report."""
        record_data = {
            "memory_id": "test-memory",
            "source_type": "tempmemory_file",
            "source_path": "docs/tempmemories/test.md",
            "commit_sha": "abc123",
            "timestamp": "2026-03-01T00:00:00Z",
            "agent": "test-agent",
            "story_id": "ST-TEST-001",
            "content_hash": "hash123",
            "parent_ids": json.dumps([]),
            "metadata": json.dumps({}),
        }
        mock_redis.scan.return_value = (
            0,
            [b"bmad:chiseai:tempmemory:provenance:test-memory"],
        )
        mock_redis.hgetall.return_value = record_data

        report = tracker.generate_audit_report()

        assert report["statistics"]["total_records"] == 1
        assert "tempmemory_file" in report["statistics"]["by_source"]
        assert "test-agent" in report["statistics"]["by_agent"]


class TestUtilityFunctions:
    """Test utility functions."""

    def test_get_current_commit_sha(self):
        """Test getting current Git commit SHA."""
        sha = get_current_commit_sha()

        # Should return a SHA or "unknown"
        assert sha is not None
        assert len(sha) == 40 or sha == "unknown"

    def test_compute_content_hash(self):
        """Test computing content hash."""
        content = "Test content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

        # Different content should produce different hash
        hash3 = compute_content_hash("Different content")
        assert hash1 != hash3


class TestProvenanceSource:
    """Test ProvenanceSource enum."""

    def test_source_values(self):
        """Test that all sources have correct values."""
        assert ProvenanceSource.TEMPMEMORY_FILE.value == "tempmemory_file"
        assert ProvenanceSource.ITERLOG_DECISION.value == "iterlog_decision"
        assert ProvenanceSource.REDIS_STATE.value == "redis_state"
        assert ProvenanceSource.QDRANT_VECTOR.value == "qdrant_vector"
        assert ProvenanceSource.MANUAL_ENTRY.value == "manual_entry"
        assert ProvenanceSource.MIGRATION_IMPORT.value == "migration_import"
