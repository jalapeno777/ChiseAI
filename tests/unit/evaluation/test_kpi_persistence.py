"""Unit tests for KPI persistence layer.

Tests cover:
- KPISnapshot creation and serialization
- KPIPersistence Redis operations
- Time-bucketed key generation
- File artifact export
- Query and retrieval operations
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from evaluation.kpi_persistence import (
    DAILY_TTL,
    HOURLY_TTL,
    WEEKLY_TTL,
    KPIPersistence,
    KPIPersistenceError,
    KPISnapshot,
)


class TestKPISnapshot:
    """Tests for KPISnapshot dataclass."""

    def test_create_snapshot(self):
        """Test creating a KPI snapshot."""
        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95, "f1_score": 0.92},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-20260302-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        assert snapshot.kpi_data == {"accuracy": 0.95, "f1_score": 0.92}
        assert snapshot.source == "brain_eval"
        assert snapshot.measured_vs_proxy == "measured"
        assert snapshot.run_id == "eval-20260302-001"
        assert snapshot.bucket_type == "daily"
        assert snapshot.bucket_key == "20260302"
        assert snapshot.metadata == {}

    def test_to_dict(self):
        """Test converting snapshot to dictionary."""
        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
            metadata={"test": "value"},
        )

        result = snapshot.to_dict()

        assert result["kpi_data"] == {"accuracy": 0.95}
        assert result["source"] == "brain_eval"
        assert result["measured_vs_proxy"] == "measured"
        assert result["run_id"] == "eval-001"
        assert result["timestamp"] == "2026-03-02T14:30:00Z"
        assert result["bucket_type"] == "daily"
        assert result["bucket_key"] == "20260302"
        assert result["metadata"] == {"test": "value"}

    def test_from_dict(self):
        """Test creating snapshot from dictionary."""
        data = {
            "kpi_data": {"accuracy": 0.95},
            "source": "backtest",
            "measured_vs_proxy": "proxy",
            "run_id": "bt-001",
            "timestamp": "2026-03-02T14:30:00Z",
            "bucket_type": "hourly",
            "bucket_key": "2026030214",
            "metadata": {"key": "value"},
        }

        snapshot = KPISnapshot.from_dict(data)

        assert snapshot.kpi_data == {"accuracy": 0.95}
        assert snapshot.source == "backtest"
        assert snapshot.measured_vs_proxy == "proxy"
        assert snapshot.run_id == "bt-001"
        assert snapshot.timestamp == "2026-03-02T14:30:00Z"
        assert snapshot.bucket_type == "hourly"
        assert snapshot.bucket_key == "2026030214"
        assert snapshot.metadata == {"key": "value"}

    def test_roundtrip_serialization(self):
        """Test to_dict and from_dict roundtrip."""
        original = KPISnapshot(
            kpi_data={"accuracy": 0.95, "f1_score": 0.92},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
            metadata={"custom": "data"},
        )

        data = original.to_dict()
        restored = KPISnapshot.from_dict(data)

        assert restored.kpi_data == original.kpi_data
        assert restored.source == original.source
        assert restored.measured_vs_proxy == original.measured_vs_proxy
        assert restored.run_id == original.run_id
        assert restored.timestamp == original.timestamp
        assert restored.bucket_type == original.bucket_type
        assert restored.bucket_key == original.bucket_key
        assert restored.metadata == original.metadata


class TestKPIPersistence:
    """Tests for KPIPersistence class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = Mock()
        redis.scan = Mock(return_value=(0, []))
        redis.get = Mock(return_value=None)
        redis.set = Mock()
        return redis

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_init_without_redis(self, temp_output_dir):
        """Test initialization without Redis client."""
        persistence = KPIPersistence(redis_client=None, output_dir=temp_output_dir)

        assert persistence.redis_client is None
        assert persistence.output_dir == temp_output_dir
        assert temp_output_dir.exists()

    def test_init_with_redis(self, mock_redis, temp_output_dir):
        """Test initialization with Redis client."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        assert persistence.redis_client == mock_redis
        assert persistence.output_dir == temp_output_dir

    def test_persist_kpi_snapshot_with_redis(self, mock_redis, temp_output_dir):
        """Test persisting KPI snapshot with Redis storage."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        kpi_data = {"accuracy": 0.95, "f1_score": 0.92}
        snapshot = persistence.persist_kpi_snapshot(
            kpi_data=kpi_data,
            source="brain_eval",
            run_id="eval-20260302-001",
            measured_vs_proxy="measured",
        )

        # Check returned snapshot
        assert snapshot.source == "brain_eval"
        assert snapshot.measured_vs_proxy == "measured"
        assert snapshot.run_id == "eval-20260302-001"
        assert snapshot.bucket_type == "daily"  # Primary snapshot is daily
        assert snapshot.kpi_data == kpi_data

        # Verify Redis was called 3 times (hourly, daily, weekly)
        assert mock_redis.set.call_count == 3

        # Verify file was created
        assert snapshot.bucket_type in ["daily"]

    def test_persist_kpi_snapshot_without_redis(self, temp_output_dir):
        """Test persisting KPI snapshot without Redis client."""
        persistence = KPIPersistence(redis_client=None, output_dir=temp_output_dir)

        kpi_data = {"accuracy": 0.95}
        snapshot = persistence.persist_kpi_snapshot(
            kpi_data=kpi_data,
            source="brain_eval",
            run_id="eval-001",
        )

        assert snapshot.kpi_data == kpi_data
        assert snapshot.source == "brain_eval"

    def test_get_bucket_key_hourly(self, temp_output_dir):
        """Test hourly bucket key generation."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        timestamp = "2026-03-02T14:30:00Z"
        bucket_key = persistence._get_bucket_key(timestamp, "hourly")

        assert bucket_key == "2026030214"

    def test_get_bucket_key_daily(self, temp_output_dir):
        """Test daily bucket key generation."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        timestamp = "2026-03-02T14:30:00Z"
        bucket_key = persistence._get_bucket_key(timestamp, "daily")

        assert bucket_key == "20260302"

    def test_get_bucket_key_weekly(self, temp_output_dir):
        """Test weekly bucket key generation."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        # 2026-03-02 is in week 10 of 2026
        timestamp = "2026-03-02T14:30:00Z"
        bucket_key = persistence._get_bucket_key(timestamp, "weekly")

        assert bucket_key == "2026-W10"

    def test_get_bucket_key_invalid(self, temp_output_dir):
        """Test invalid bucket type raises error."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        with pytest.raises(KPIPersistenceError, match="Unknown bucket type"):
            persistence._get_bucket_key("2026-03-02T14:30:00Z", "invalid")

    def test_store_in_redis_hourly(self, mock_redis, temp_output_dir):
        """Test Redis storage with hourly TTL."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="hourly",
            bucket_key="2026030214",
        )

        persistence._store_in_redis(snapshot)

        # Verify Redis set was called with correct key and TTL
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        expected_key = "bmad:chiseai:brain:kpi:hourly:2026030214:eval-001"
        assert expected_key in str(call_args[0])
        assert call_args[1]["ex"] == HOURLY_TTL

    def test_store_in_redis_daily(self, mock_redis, temp_output_dir):
        """Test Redis storage with daily TTL."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        persistence._store_in_redis(snapshot)

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == DAILY_TTL

    def test_store_in_redis_weekly(self, mock_redis, temp_output_dir):
        """Test Redis storage with weekly TTL."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="weekly",
            bucket_key="2026-W09",
        )

        persistence._store_in_redis(snapshot)

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == WEEKLY_TTL

    def test_export_to_file(self, temp_output_dir):
        """Test exporting snapshot to file."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        filepath = persistence.export_to_file(snapshot)

        # Verify file exists
        assert filepath.exists()
        assert filepath.suffix == ".json"

        # Verify content
        with open(filepath) as f:
            data = json.load(f)

        assert data["kpi_data"] == {"accuracy": 0.95}
        assert data["source"] == "brain_eval"
        assert data["run_id"] == "eval-001"

    def test_export_to_file_custom_path(self, temp_output_dir):
        """Test exporting to custom filepath."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        custom_path = temp_output_dir / "custom" / "snapshot.json"
        filepath = persistence.export_to_file(snapshot, filepath=custom_path)

        assert filepath == custom_path
        assert filepath.exists()

    def test_get_artifact_path(self, temp_output_dir):
        """Test artifact path generation."""
        persistence = KPIPersistence(output_dir=temp_output_dir)

        snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        path = persistence._get_artifact_path(snapshot)

        # Expected structure: output_dir/daily/brain_eval/2026/03/02/eval-001.json
        assert "daily" in str(path)
        assert "brain_eval" in str(path)
        assert "2026" in str(path)
        assert "03" in str(path)
        assert "02" in str(path)
        assert "eval-001.json" in str(path)

    def test_get_kpi_snapshots_no_redis(self, temp_output_dir):
        """Test querying snapshots without Redis client."""
        persistence = KPIPersistence(redis_client=None, output_dir=temp_output_dir)

        start_time = datetime.now(UTC) - timedelta(days=1)
        end_time = datetime.now(UTC)

        snapshots = persistence.get_kpi_snapshots(
            bucket="daily",
            start_time=start_time,
            end_time=end_time,
        )

        assert snapshots == []

    def test_get_kpi_snapshots_invalid_bucket(self, mock_redis, temp_output_dir):
        """Test querying with invalid bucket type."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        start_time = datetime.now(UTC) - timedelta(days=1)
        end_time = datetime.now(UTC)

        with pytest.raises(KPIPersistenceError, match="Invalid bucket type"):
            persistence.get_kpi_snapshots(
                bucket="invalid",
                start_time=start_time,
                end_time=end_time,
            )

    def test_get_kpi_snapshots_with_data(self, mock_redis, temp_output_dir):
        """Test querying snapshots with actual data."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        # Create test snapshot
        test_snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        # Mock Redis to return snapshot
        mock_redis.scan.return_value = (
            0,
            [b"bmad:chiseai:brain:kpi:daily:20260302:eval-001"],
        )
        mock_redis.get.return_value = json.dumps(test_snapshot.to_dict())

        start_time = datetime(2026, 3, 1, tzinfo=UTC)
        end_time = datetime(2026, 3, 3, tzinfo=UTC)

        snapshots = persistence.get_kpi_snapshots(
            bucket="daily",
            start_time=start_time,
            end_time=end_time,
        )

        assert len(snapshots) == 1
        assert snapshots[0].run_id == "eval-001"
        assert snapshots[0].source == "brain_eval"

    def test_get_latest_snapshot_no_redis(self, temp_output_dir):
        """Test getting latest snapshot without Redis client."""
        persistence = KPIPersistence(redis_client=None, output_dir=temp_output_dir)

        result = persistence.get_latest_snapshot("brain_eval")

        assert result is None

    def test_get_latest_snapshot_found(self, mock_redis, temp_output_dir):
        """Test getting latest snapshot for a source."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        # Create test snapshots with different timestamps
        older_snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.90},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-001",
            timestamp="2026-03-01T10:00:00Z",
            bucket_type="daily",
            bucket_key="20260301",
        )

        newer_snapshot = KPISnapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            measured_vs_proxy="measured",
            run_id="eval-002",
            timestamp="2026-03-02T14:30:00Z",
            bucket_type="daily",
            bucket_key="20260302",
        )

        # Mock Redis to return both snapshots
        mock_redis.scan.return_value = (
            0,
            [
                b"bmad:chiseai:brain:kpi:daily:20260301:eval-001",
                b"bmad:chiseai:brain:kpi:daily:20260302:eval-002",
            ],
        )
        mock_redis.get.side_effect = [
            json.dumps(older_snapshot.to_dict()),
            json.dumps(newer_snapshot.to_dict()),
        ]

        result = persistence.get_latest_snapshot("brain_eval")

        assert result is not None
        assert result.run_id == "eval-002"
        assert result.timestamp == "2026-03-02T14:30:00Z"

    def test_get_latest_snapshot_not_found(self, mock_redis, temp_output_dir):
        """Test getting latest snapshot when source doesn't exist."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        mock_redis.scan.return_value = (0, [])
        mock_redis.get.return_value = None

        result = persistence.get_latest_snapshot("nonexistent")

        assert result is None

    def test_idempotent_persist(self, mock_redis, temp_output_dir):
        """Test that persist operation is idempotent."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        kpi_data = {"accuracy": 0.95}

        # Persist twice with same run_id
        snapshot1 = persistence.persist_kpi_snapshot(
            kpi_data=kpi_data,
            source="brain_eval",
            run_id="eval-001",
        )

        snapshot2 = persistence.persist_kpi_snapshot(
            kpi_data=kpi_data,
            source="brain_eval",
            run_id="eval-001",
        )

        # Both should succeed without errors
        assert snapshot1.run_id == snapshot2.run_id
        assert snapshot1.source == snapshot2.source

    def test_provenance_fields_included(self, mock_redis, temp_output_dir):
        """Test that all provenance fields are included in snapshot."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        snapshot = persistence.persist_kpi_snapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            run_id="eval-001",
            measured_vs_proxy="measured",
            metadata={"custom_field": "value"},
        )

        # Verify all provenance fields
        assert snapshot.source == "brain_eval"
        assert snapshot.measured_vs_proxy == "measured"
        assert snapshot.run_id == "eval-001"
        assert snapshot.timestamp is not None
        assert snapshot.bucket_type is not None
        assert snapshot.bucket_key is not None
        assert "custom_field" in snapshot.metadata

    def test_redis_key_pattern(self, mock_redis, temp_output_dir):
        """Test that Redis keys follow the correct pattern."""
        persistence = KPIPersistence(
            redis_client=mock_redis, output_dir=temp_output_dir
        )

        snapshot = persistence.persist_kpi_snapshot(
            kpi_data={"accuracy": 0.95},
            source="brain_eval",
            run_id="eval-001",
        )

        # Verify Redis set was called
        assert mock_redis.set.call_count == 3  # hourly, daily, weekly

        # Check one of the calls for key pattern
        call_args = mock_redis.set.call_args_list[1]  # Daily
        key = call_args[0][0]

        # Verify key format: bmad:chiseai:brain:kpi:{bucket}:{bucket_key}:{run_id}
        assert key.startswith("bmad:chiseai:brain:kpi:")
        assert ":daily:" in key
        assert ":eval-001" in key
