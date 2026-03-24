"""Unit tests for trend_rollups module.

Tests for TrendRollupEngine and TrendRollup classes.
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from evaluation.trend_rollups import TrendRollup, TrendRollupEngine


class TestTrendRollup:
    """Tests for TrendRollup dataclass."""

    def test_trend_rollup_creation(self):
        """Test creating a TrendRollup instance."""
        rollup = TrendRollup(
            window="24h",
            computed_at=datetime.now(UTC),
            source="test",
            kpis={"recurring_issue_rate": 0.5},
            data_points_count=100,
            provenance={"test": "data"},
        )

        assert rollup.window == "24h"
        assert rollup.source == "test"
        assert rollup.kpis["recurring_issue_rate"] == 0.5
        assert rollup.data_points_count == 100

    def test_trend_rollup_to_dict(self):
        """Test converting TrendRollup to dictionary."""
        timestamp = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
        rollup = TrendRollup(
            window="7d",
            computed_at=timestamp,
            source="brain-eval",
            kpis={"median_time_lost_minutes": 15.5},
            data_points_count=50,
        )

        data = rollup.to_dict()

        assert data["window"] == "7d"
        assert data["computed_at"] == "2026-03-02T12:00:00+00:00"
        assert data["source"] == "brain-eval"
        assert data["kpis"]["median_time_lost_minutes"] == 15.5
        assert data["data_points_count"] == 50
        assert "provenance" in data

    def test_trend_rollup_to_json(self):
        """Test converting TrendRollup to JSON."""
        rollup = TrendRollup(
            window="30d",
            computed_at=datetime.now(UTC),
            source="test",
            kpis={"test_kpi": 1.0},
            data_points_count=10,
        )

        json_str = rollup.to_json()
        data = json.loads(json_str)

        assert data["window"] == "30d"
        assert data["kpis"]["test_kpi"] == 1.0

    def test_trend_rollup_from_dict(self):
        """Test creating TrendRollup from dictionary."""
        data = {
            "window": "24h",
            "computed_at": "2026-03-02T12:00:00+00:00",
            "source": "test",
            "kpis": {"recurring_issue_rate": 0.75},
            "data_points_count": 200,
            "provenance": {"method": "test"},
        }

        rollup = TrendRollup.from_dict(data)

        assert rollup.window == "24h"
        assert rollup.computed_at == datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
        assert rollup.source == "test"
        assert rollup.kpis["recurring_issue_rate"] == 0.75
        assert rollup.data_points_count == 200


class TestTrendRollupEngine:
    """Tests for TrendRollupEngine class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = Mock()
        redis.scan = Mock(return_value=(0, []))
        redis.get = Mock(return_value=None)
        return redis

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def engine(self, mock_redis, temp_output_dir):
        """Create a TrendRollupEngine instance."""
        return TrendRollupEngine(redis_client=mock_redis, output_dir=temp_output_dir)

    def test_engine_initialization(self, temp_output_dir):
        """Test engine initialization."""
        engine = TrendRollupEngine(output_dir=temp_output_dir)

        assert engine.redis_client is None
        assert engine.output_dir == Path(temp_output_dir)
        assert engine.output_dir.exists()

    def test_engine_with_redis(self, mock_redis, temp_output_dir):
        """Test engine with Redis client."""
        engine = TrendRollupEngine(redis_client=mock_redis, output_dir=temp_output_dir)

        assert engine.redis_client == mock_redis

    def test_compute_24h_rollups_no_redis(self, temp_output_dir):
        """Test computing 24h rollups without Redis."""
        engine = TrendRollupEngine(output_dir=temp_output_dir)
        rollup = engine.compute_24h_rollups(source="test")

        assert rollup.window == "24h"
        assert rollup.source == "test"
        assert rollup.data_points_count == 0
        assert rollup.kpis["recurring_issue_rate"] == 0.0

    def test_compute_7d_rollups(self, engine):
        """Test computing 7d rollups."""
        rollup = engine.compute_7d_rollups(source="test")

        assert rollup.window == "7d"
        assert rollup.source == "test"

    def test_compute_30d_rollups(self, engine):
        """Test computing 30d rollups."""
        rollup = engine.compute_30d_rollups(source="test")

        assert rollup.window == "30d"
        assert rollup.source == "test"

    def test_compute_all_rollups(self, engine):
        """Test computing all rollups."""
        rollups = engine.compute_all_rollups(source="test")

        assert "24h" in rollups
        assert "7d" in rollups
        assert "30d" in rollups
        assert all(r.source == "test" for r in rollups.values())

    def test_collect_issues_with_redis(self, mock_redis, temp_output_dir):
        """Test collecting issues from Redis."""
        # Setup mock data
        now = datetime.now(UTC)
        issue1 = {
            "fingerprint": "abc123",
            "timestamp": now.isoformat(),
            "category": "db_connectivity",
        }
        issue2 = {
            "fingerprint": "def456",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "category": "file_access",
        }

        mock_redis.scan = Mock(side_effect=[(1, ["key1"]), (0, ["key2"])])
        mock_redis.get = Mock(side_effect=[json.dumps(issue1), json.dumps(issue2)])

        engine = TrendRollupEngine(redis_client=mock_redis, output_dir=temp_output_dir)
        issues = engine._collect_issues(hours=24)

        assert len(issues) == 2
        assert issues[0]["fingerprint"] == "abc123"

    def test_compute_recurring_issue_rate_empty(self, engine):
        """Test recurring issue rate with no issues."""
        rate = engine._compute_recurring_issue_rate([])
        assert rate == 0.0

    def test_compute_recurring_issue_rate_no_repeats(self, engine):
        """Test recurring issue rate with no repeated issues."""
        issues = [
            {"fingerprint": "a1"},
            {"fingerprint": "b2"},
            {"fingerprint": "c3"},
        ]
        rate = engine._compute_recurring_issue_rate(issues)
        assert rate == 0.0

    def test_compute_recurring_issue_rate_with_repeats(self, engine):
        """Test recurring issue rate with repeated issues."""
        issues = [
            {"fingerprint": "a1"},
            {"fingerprint": "a1"},
            {"fingerprint": "b2"},
            {"fingerprint": "b2"},
            {"fingerprint": "c3"},
        ]
        rate = engine._compute_recurring_issue_rate(issues)
        # 2 fingerprints out of 3 unique have repeats
        assert rate == pytest.approx(2 / 3, rel=1e-2)

    def test_compute_median_time_lost_empty(self, engine):
        """Test median time lost with no issues."""
        median = engine._compute_median_time_lost_minutes([])
        assert median == 0.0

    def test_compute_median_time_lost(self, engine):
        """Test median time lost computation."""
        issues = [
            {"metadata": {"time_lost_minutes": 10}},
            {"metadata": {"time_lost_minutes": 20}},
            {"metadata": {"time_lost_minutes": 30}},
        ]
        median = engine._compute_median_time_lost_minutes(issues)
        assert median == 20.0

    def test_compute_unresolved_issue_age_empty(self, engine):
        """Test unresolved issue age with no issues."""
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        age = engine._compute_unresolved_issue_age([], cutoff)
        assert age == 0.0

    def test_compute_unresolved_issue_age(self, engine):
        """Test unresolved issue age computation."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=24)

        issues = [
            {
                "timestamp": (now - timedelta(hours=5)).isoformat(),
                "metadata": {"resolved": False},
            },
            {
                "timestamp": (now - timedelta(hours=10)).isoformat(),
                "metadata": {"resolved": False},
            },
            {
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "metadata": {"resolved": True},  # Should be excluded
            },
        ]

        age = engine._compute_unresolved_issue_age(issues, cutoff)
        # Average of 5 and 10 hours
        assert age == pytest.approx(7.5, rel=1e-2)

    def test_compute_top_fingerprint_repeat_count_empty(self, engine):
        """Test top fingerprint count with no issues."""
        count = engine._compute_top_fingerprint_repeat_count([])
        assert count == 0

    def test_compute_top_fingerprint_repeat_count(self, engine):
        """Test top fingerprint count computation."""
        issues = [
            {"fingerprint": "a1"},
            {"fingerprint": "a1"},
            {"fingerprint": "a1"},
            {"fingerprint": "b2"},
            {"fingerprint": "b2"},
        ]
        count = engine._compute_top_fingerprint_repeat_count(issues)
        assert count == 3

    def test_compute_fix_reopen_rate(self, engine):
        """Test fix reopen rate (placeholder)."""
        rate = engine._compute_fix_reopen_rate([])
        # Should return 0.0 as placeholder
        assert rate == 0.0

    def test_export_rollup_artifact(self, engine):
        """Test exporting a rollup artifact."""
        rollup = TrendRollup(
            window="24h",
            computed_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
            source="test",
            kpis={"test_kpi": 0.5},
            data_points_count=100,
        )

        path = engine.export_rollup_artifact(rollup, "test-rollup.json")

        assert path.exists()
        assert path.name == "test-rollup.json"

        # Verify content
        data = json.loads(path.read_text())
        assert data["window"] == "24h"
        assert data["kpis"]["test_kpi"] == 0.5

    def test_export_rollup_artifact_auto_filename(self, engine):
        """Test exporting with auto-generated filename."""
        rollup = TrendRollup(
            window="7d",
            computed_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
            source="test",
            kpis={},
            data_points_count=0,
        )

        path = engine.export_rollup_artifact(rollup)

        assert path.exists()
        assert path.name.startswith("7d-")
        assert path.suffix == ".json"

    def test_export_all_rollups(self, engine):
        """Test exporting all rollups."""
        rollups = {
            "24h": TrendRollup(
                window="24h",
                computed_at=datetime.now(UTC),
                source="test",
                kpis={},
                data_points_count=10,
            ),
            "7d": TrendRollup(
                window="7d",
                computed_at=datetime.now(UTC),
                source="test",
                kpis={},
                data_points_count=20,
            ),
        }

        paths = engine.export_all_rollups(rollups)

        assert len(paths) == 2
        assert all(p.exists() for p in paths.values())

    def test_get_recent_rollups_empty(self, engine):
        """Test getting recent rollups when none exist."""
        rollups = engine.get_recent_rollups()
        assert rollups == []

    def test_get_recent_rollups(self, engine):
        """Test getting recent rollups."""
        # Create some rollup artifacts
        rollup1 = TrendRollup(
            window="24h",
            computed_at=datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC),
            source="test",
            kpis={},
            data_points_count=10,
        )
        rollup2 = TrendRollup(
            window="24h",
            computed_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC),
            source="test",
            kpis={},
            data_points_count=20,
        )

        engine.export_rollup_artifact(rollup1, "rollup1.json")
        engine.export_rollup_artifact(rollup2, "rollup2.json")

        rollups = engine.get_recent_rollups(limit=10)

        assert len(rollups) == 2
        # Should be sorted newest first
        assert rollups[0].computed_at > rollups[1].computed_at

    def test_full_integration(self, mock_redis, temp_output_dir):
        """Test full integration with Redis and artifact export."""
        # Setup mock Redis data
        now = datetime.now(UTC)
        issues = [
            {
                "fingerprint": "repeat1",
                "timestamp": now.isoformat(),
                "category": "db_connectivity",
                "metadata": {"time_lost_minutes": 10, "resolved": False},
            },
            {
                "fingerprint": "repeat1",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "category": "db_connectivity",
                "metadata": {"time_lost_minutes": 20, "resolved": False},
            },
            {
                "fingerprint": "unique1",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "category": "file_access",
                "metadata": {"time_lost_minutes": 30, "resolved": True},
            },
        ]

        mock_redis.scan = Mock(side_effect=[(0, ["key1", "key2", "key3"])])
        mock_redis.get = Mock(side_effect=[json.dumps(i) for i in issues])

        engine = TrendRollupEngine(redis_client=mock_redis, output_dir=temp_output_dir)

        # Compute all rollups
        rollups = engine.compute_all_rollups(source="integration-test")

        # Export all
        paths = engine.export_all_rollups(rollups)

        # Verify
        assert len(paths) == 3
        assert all(p.exists() for p in paths.values())

        # Check 24h rollup
        rollup_24h = rollups["24h"]
        assert rollup_24h.data_points_count == 3
        assert rollup_24h.kpis["top_fingerprint_repeat_count"] == 2
        assert rollup_24h.kpis["median_time_lost_minutes"] == 20.0


class TestTrendRollupEngineEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def engine(self):
        """Create engine with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield TrendRollupEngine(output_dir=tmpdir)

    def test_collect_issues_redis_error(self, engine):
        """Test handling Redis errors during issue collection."""
        mock_redis = Mock()
        mock_redis.scan = Mock(side_effect=Exception("Redis error"))
        engine.redis_client = mock_redis

        issues = engine._collect_issues(24)
        assert issues == []

    def test_collect_issues_invalid_json(self, engine):
        """Test handling invalid JSON from Redis."""
        mock_redis = Mock()
        mock_redis.scan = Mock(side_effect=[(0, ["key1"])])
        mock_redis.get = Mock(return_value="invalid json{{{")
        engine.redis_client = mock_redis

        issues = engine._collect_issues(24)
        assert issues == []

    def test_collect_issues_old_timestamps(self, engine):
        """Test filtering out old timestamps."""
        now = datetime.now(UTC)
        old_issue = {
            "fingerprint": "old",
            "timestamp": (now - timedelta(hours=48)).isoformat(),
        }
        new_issue = {
            "fingerprint": "new",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
        }

        mock_redis = Mock()
        mock_redis.scan = Mock(side_effect=[(0, ["key1", "key2"])])
        mock_redis.get = Mock(
            side_effect=[json.dumps(old_issue), json.dumps(new_issue)]
        )
        engine.redis_client = mock_redis

        issues = engine._collect_issues(hours=24)
        assert len(issues) == 1
        assert issues[0]["fingerprint"] == "new"

    def test_compute_kpis_with_missing_data(self, engine):
        """Test computing KPIs with missing or malformed data."""
        issues = [
            {"fingerprint": ""},  # Empty fingerprint
            {"metadata": {"time_lost_minutes": "invalid"}},  # Invalid time_lost
            {
                "timestamp": "invalid",
                "metadata": {"resolved": False},
            },  # Invalid timestamp
        ]

        # Should not raise exceptions
        engine._compute_recurring_issue_rate(issues)
        engine._compute_median_time_lost_minutes(issues)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        engine._compute_unresolved_issue_age(issues, cutoff)
        engine._compute_top_fingerprint_repeat_count(issues)

    def test_export_to_nested_path(self, engine):
        """Test exporting to a nested directory path."""
        rollup = TrendRollup(
            window="24h",
            computed_at=datetime.now(UTC),
            source="test",
            kpis={},
            data_points_count=0,
        )

        path = engine.export_rollup_artifact(rollup, "nested/dir/rollup.json")

        assert path.exists()
        assert path.parent.name == "dir"
        assert path.parent.parent.name == "nested"

    def test_get_recent_rollups_with_invalid_files(self, engine):
        """Test handling invalid files when loading recent rollups."""
        # Create valid rollup
        rollup = TrendRollup(
            window="24h",
            computed_at=datetime.now(UTC),
            source="test",
            kpis={},
            data_points_count=0,
        )
        engine.export_rollup_artifact(rollup, "valid.json")

        # Create invalid file
        invalid_path = engine.output_dir / "invalid.json"
        invalid_path.write_text("not valid json")

        # Should return only valid rollup
        rollups = engine.get_recent_rollups()
        assert len(rollups) == 1
        assert rollups[0].window == "24h"
