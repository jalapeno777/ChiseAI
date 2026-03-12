"""
Tests for Week 1 Audit Snapshot script.

ST-GOV-MINI-001: Week 1 Audit Snapshot Tests
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.governance.week1_audit_snapshot import (
    Week1Snapshot,
    StoryInfo,
    MemoryStats,
    GovernanceMetrics,
    capture_active_stories,
    capture_memory_stats,
    capture_governance_metrics,
    capture_agent_activity,
    create_week1_snapshot,
    save_snapshot,
)


class TestStoryInfo:
    """Tests for StoryInfo dataclass."""

    def test_story_info_creation(self):
        """Test creating a StoryInfo instance."""
        story = StoryInfo(
            story_id="ST-001",
            story_title="Test Story",
            started_at="2026-01-01T00:00:00Z",
            agent="dev",
            branch="feature/ST-001-test",
            status="active",
        )

        assert story.story_id == "ST-001"
        assert story.story_title == "Test Story"
        assert story.started_at == "2026-01-01T00:00:00Z"
        assert story.agent == "dev"
        assert story.branch == "feature/ST-001-test"
        assert story.status == "active"


class TestMemoryStats:
    """Tests for MemoryStats dataclass."""

    def test_memory_stats_defaults(self):
        """Test MemoryStats default values."""
        stats = MemoryStats()

        assert stats.redis_keys_total == 0
        assert stats.redis_keys_by_db == {}
        assert stats.redis_memory_used_mb == 0.0
        assert stats.qdrant_collections == []
        assert stats.qdrant_total_vectors == 0

    def test_memory_stats_with_values(self):
        """Test MemoryStats with values."""
        stats = MemoryStats(
            redis_keys_total=1000,
            redis_keys_by_db={"db0": 800, "db1": 200},
            redis_memory_used_mb=50.5,
            qdrant_collections=["ChiseAI", "test"],
            qdrant_total_vectors=5000,
        )

        assert stats.redis_keys_total == 1000
        assert stats.redis_keys_by_db == {"db0": 800, "db1": 200}
        assert stats.redis_memory_used_mb == 50.5
        assert stats.qdrant_collections == ["ChiseAI", "test"]
        assert stats.qdrant_total_vectors == 5000


class TestGovernanceMetrics:
    """Tests for GovernanceMetrics dataclass."""

    def test_governance_metrics_defaults(self):
        """Test GovernanceMetrics default values."""
        metrics = GovernanceMetrics()

        assert metrics.retrieval_latency_ms == 0.0
        assert metrics.memory_hit_rate == 0.0
        assert metrics.deduplication_ratio == 0.0
        assert metrics.active_ownership_locks == 0
        assert metrics.parallel_workers == 0


class TestWeek1Snapshot:
    """Tests for Week1Snapshot dataclass."""

    def test_snapshot_to_dict(self):
        """Test converting snapshot to dictionary."""
        snapshot = Week1Snapshot()
        snapshot.metadata = {"capture_time": "2026-01-01T00:00:00Z"}
        snapshot.active_stories = [
            StoryInfo(story_id="ST-001", story_title="Test Story"),
        ]
        snapshot.memory_stats = MemoryStats(redis_keys_total=100)
        snapshot.governance_metrics = GovernanceMetrics(retrieval_latency_ms=25.0)

        data = snapshot.to_dict()

        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"
        assert len(data["active_stories"]) == 1
        assert data["active_stories"][0]["story_id"] == "ST-001"
        assert data["memory_stats"]["redis_keys_total"] == 100
        assert data["governance_metrics"]["retrieval_latency_ms"] == 25.0

    def test_snapshot_to_json(self):
        """Test converting snapshot to JSON."""
        snapshot = Week1Snapshot()
        snapshot.metadata = {"capture_time": "2026-01-01T00:00:00Z"}

        json_str = snapshot.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"


class TestCaptureActiveStories:
    """Tests for capture_active_stories function."""

    def test_capture_active_stories_no_redis(self):
        """Test capturing stories with no Redis client."""
        stories = capture_active_stories(None)
        assert stories == []

    def test_capture_active_stories_with_mock(self):
        """Test capturing stories with mock Redis."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["bmad:chiseai:iterlog:story:ST-001"])
        mock_redis.hgetall.return_value = {
            "story_title": "Test Story",
            "started_at": "2026-01-01T00:00:00Z",
            "agent": "dev",
            "branch": "feature/ST-001-test",
            "status": "active",
        }

        stories = capture_active_stories(mock_redis)

        assert len(stories) == 1
        assert stories[0].story_id == "ST-001"
        assert stories[0].story_title == "Test Story"


class TestCaptureMemoryStats:
    """Tests for capture_memory_stats function."""

    def test_capture_memory_stats_no_clients(self):
        """Test capturing stats with no clients."""
        stats = capture_memory_stats(None, None)

        assert stats.redis_keys_total == 0
        assert stats.qdrant_total_vectors == 0

    def test_capture_memory_stats_with_redis(self):
        """Test capturing stats with mock Redis."""
        mock_redis = MagicMock()
        mock_redis.info.side_effect = [
            {"db0": {"keys": 100}, "db1": {"keys": 50}},  # keyspace
            {"used_memory": 52_428_800},  # memory (50 MB)
        ]

        stats = capture_memory_stats(mock_redis, None)

        assert stats.redis_keys_total == 150
        assert stats.redis_keys_by_db == {"db0": 100, "db1": 50}
        assert stats.redis_memory_used_mb == 50.0


class TestCaptureGovernanceMetrics:
    """Tests for capture_governance_metrics function."""

    def test_capture_governance_metrics_no_clients(self):
        """Test capturing metrics with no clients."""
        metrics = capture_governance_metrics(None, None)

        assert metrics.retrieval_latency_ms == 0.0
        assert metrics.active_ownership_locks == 0


class TestCaptureAgentActivity:
    """Tests for capture_agent_activity function."""

    def test_capture_agent_activity_no_redis(self):
        """Test capturing activity with no Redis client."""
        activity = capture_agent_activity(None)

        assert activity["active_agents"] == []
        assert activity["total_stories_tracked"] == 0

    def test_capture_agent_activity_with_mock(self):
        """Test capturing activity with mock Redis."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "src:test": "ST-001/dev/2026-01-01T00:00:00Z",
        }
        mock_redis.scan.return_value = (0, ["bmad:chiseai:iterlog:story:ST-001"])

        activity = capture_agent_activity(mock_redis)

        assert activity["total_stories_tracked"] == 1
        assert len(activity["active_agents"]) == 1
        assert activity["active_agents"][0]["agent"] == "dev"


class TestSaveSnapshot:
    """Tests for save_snapshot function."""

    def test_save_snapshot_json(self, tmp_path):
        """Test saving snapshot as JSON."""
        snapshot = Week1Snapshot()
        snapshot.metadata = {"capture_time": "2026-01-01T00:00:00Z"}

        filepath = save_snapshot(snapshot, tmp_path, "json")

        assert filepath.exists()
        assert filepath.suffix == ".json"

        with open(filepath) as f:
            data = json.load(f)
        assert data["metadata"]["capture_time"] == "2026-01-01T00:00:00Z"

    def test_save_snapshot_creates_directory(self, tmp_path):
        """Test that save_snapshot creates output directory."""
        snapshot = Week1Snapshot()
        output_dir = tmp_path / "nested" / "dir"

        filepath = save_snapshot(snapshot, output_dir, "json")

        assert output_dir.exists()
        assert filepath.exists()


class TestCreateWeek1Snapshot:
    """Tests for create_week1_snapshot function."""

    def test_create_week1_snapshot_no_clients(self):
        """Test creating snapshot with no clients."""
        snapshot = create_week1_snapshot(None, None)

        assert snapshot.metadata["snapshot_type"] == "week1_audit"
        assert snapshot.metadata["story_id"] == "ST-GOV-MINI-001"
        assert "capture_time" in snapshot.metadata
        assert "data_sources" in snapshot.metadata

    @patch("scripts.governance.week1_audit_snapshot.capture_active_stories")
    @patch("scripts.governance.week1_audit_snapshot.capture_memory_stats")
    @patch("scripts.governance.week1_audit_snapshot.capture_governance_metrics")
    @patch("scripts.governance.week1_audit_snapshot.capture_agent_activity")
    def test_create_week1_snapshot_with_mocks(
        self,
        mock_capture_activity,
        mock_capture_governance,
        mock_capture_memory,
        mock_capture_stories,
    ):
        """Test creating snapshot with mocked capture functions."""
        mock_capture_stories.return_value = [
            StoryInfo(story_id="ST-001", story_title="Test"),
        ]
        mock_capture_memory.return_value = MemoryStats(redis_keys_total=100)
        mock_capture_governance.return_value = GovernanceMetrics(
            retrieval_latency_ms=25.0
        )
        mock_capture_activity.return_value = {"active_agents": []}

        snapshot = create_week1_snapshot(MagicMock(), MagicMock())

        assert len(snapshot.active_stories) == 1
        assert snapshot.memory_stats.redis_keys_total == 100
        assert snapshot.governance_metrics.retrieval_latency_ms == 25.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
