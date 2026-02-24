"""
Tests for Audit Snapshot and Retrieval Baseline.

ST-GOV-MINI-001: Audit Snapshot + Retrieval Baseline

Test coverage:
- Snapshot capture
- Baseline metrics collection
- Redis storage integration
- Latency measurement
- Memory hit rate calculation
- Deduplication ratio calculation
- Week 1 baseline capture
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.governance.audit.baseline import (
    BASELINE_CURRENT_KEY,
    METRIC_THRESHOLDS,
    SNAPSHOT_KEY_PREFIX,
    SNAPSHOT_TTL_SECONDS,
    AuditSnapshot,
    RetrievalBaseline,
    capture_week1_baseline,
    evaluate_metric,
    get_all_metric_ratings,
)


class TestAuditSnapshot:
    """Test cases for AuditSnapshot class."""

    def test_snapshot_creation_default_values(self) -> None:
        """Test creating a snapshot with default values."""
        snapshot = AuditSnapshot()

        assert snapshot.component == "system"
        assert snapshot.metrics == {}
        assert snapshot.metadata == {}
        assert snapshot.snapshot_id is not None
        assert snapshot.timestamp is not None

    def test_snapshot_creation_custom_values(self) -> None:
        """Test creating a snapshot with custom values."""
        custom_time = datetime(2026, 2, 22, 12, 0, 0, tzinfo=UTC)
        snapshot = AuditSnapshot(
            timestamp=custom_time,
            component="memory",
            metrics={"heap_size": 1024},
            metadata={"source": "test"},
        )

        assert snapshot.component == "memory"
        assert snapshot.metrics == {"heap_size": 1024}
        assert snapshot.metadata == {"source": "test"}
        assert snapshot.timestamp == custom_time

    def test_snapshot_capture(self) -> None:
        """Test capturing a snapshot with additional metrics."""
        snapshot = AuditSnapshot()
        result = snapshot.capture(
            component="retrieval",
            latency_ms=42.5,
            hit_count=100,
        )

        # Should return self for chaining
        assert result is snapshot
        assert snapshot.component == "retrieval"
        assert snapshot.metrics["latency_ms"] == 42.5
        assert snapshot.metrics["hit_count"] == 100
        assert snapshot.snapshot_id is not None
        assert "retrieval-" in snapshot.snapshot_id

    def test_snapshot_to_dict(self) -> None:
        """Test converting snapshot to dictionary."""
        snapshot = AuditSnapshot(
            component="test",
            metrics={"value": 123},
            metadata={"key": "val"},
        )
        data = snapshot.to_dict()

        assert "snapshot_id" in data
        assert "timestamp" in data
        assert data["component"] == "test"
        assert data["metrics"] == {"value": 123}
        assert data["metadata"] == {"key": "val"}

    def test_snapshot_to_json(self) -> None:
        """Test converting snapshot to JSON."""
        snapshot = AuditSnapshot(component="test", metrics={"count": 1})
        json_str = snapshot.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["component"] == "test"
        assert parsed["metrics"]["count"] == 1

    def test_snapshot_from_dict(self) -> None:
        """Test creating snapshot from dictionary."""
        data = {
            "snapshot_id": "test-123",
            "timestamp": "2026-02-22T12:00:00+00:00",
            "component": "memory",
            "metrics": {"size": 100},
            "metadata": {},
        }
        snapshot = AuditSnapshot.from_dict(data)

        assert snapshot.snapshot_id == "test-123"
        assert snapshot.component == "memory"
        assert snapshot.metrics == {"size": 100}

    def test_snapshot_store_to_redis(self) -> None:
        """Test storing snapshot to Redis."""
        snapshot = AuditSnapshot(
            component="test",
            metrics={"value": 42},
            metadata={"source": "unit_test"},
        )

        # Create mock Redis client
        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        result_key = snapshot.store_to_redis(mock_redis)

        # Verify key format
        assert result_key.startswith(SNAPSHOT_KEY_PREFIX)

        # Verify hset was called for each field
        assert mock_redis.hset.call_count == 3

        # Verify expire was called with 30-day TTL
        mock_redis.expire.assert_called_once_with(result_key, SNAPSHOT_TTL_SECONDS)


class TestRetrievalBaseline:
    """Test cases for RetrievalBaseline class."""

    def test_baseline_creation_default_values(self) -> None:
        """Test creating a baseline with default values."""
        baseline = RetrievalBaseline()

        assert baseline.baseline_id == "default"
        assert baseline.samples == 0
        assert "retrieval_latency_ms" in baseline.metrics
        assert "memory_hit_rate" in baseline.metrics
        assert "deduplication_ratio" in baseline.metrics

    def test_baseline_creation_custom_values(self) -> None:
        """Test creating a baseline with custom values."""
        baseline = RetrievalBaseline(
            baseline_id="custom-001",
            metrics={
                "retrieval_latency_ms": 25.5,
                "memory_hit_rate": 85.0,
                "deduplication_ratio": 0.75,
            },
            samples=100,
        )

        assert baseline.baseline_id == "custom-001"
        assert baseline.metrics["retrieval_latency_ms"] == 25.5
        assert baseline.samples == 100

    def test_get_metrics(self) -> None:
        """Test getting baseline metrics."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 30.0,
                "memory_hit_rate": 90.0,
                "deduplication_ratio": 0.8,
            }
        )
        metrics = baseline.get_metrics()

        assert metrics["retrieval_latency_ms"] == 30.0
        assert metrics["memory_hit_rate"] == 90.0
        assert metrics["deduplication_ratio"] == 0.8

    def test_update_metrics(self) -> None:
        """Test updating baseline metrics."""
        baseline = RetrievalBaseline()

        baseline.update_metrics(
            retrieval_latency_ms=50.0,
            memory_hit_rate=75.0,
            deduplication_ratio=0.6,
        )

        assert baseline.metrics["retrieval_latency_ms"] == 50.0
        assert baseline.metrics["memory_hit_rate"] == 75.0
        assert baseline.metrics["deduplication_ratio"] == 0.6
        assert baseline.samples == 1

    def test_update_metrics_partial(self) -> None:
        """Test partial metric updates."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 100.0,
                "memory_hit_rate": 50.0,
                "deduplication_ratio": 0.5,
            }
        )

        baseline.update_metrics(retrieval_latency_ms=50.0)

        assert baseline.metrics["retrieval_latency_ms"] == 50.0
        assert baseline.metrics["memory_hit_rate"] == 50.0  # Unchanged

    def test_update_metrics_bounds(self) -> None:
        """Test that metrics are bounded to valid ranges."""
        baseline = RetrievalBaseline()

        # memory_hit_rate should be clamped to 0-100
        baseline.update_metrics(memory_hit_rate=150.0)
        assert baseline.metrics["memory_hit_rate"] == 100.0

        baseline.update_metrics(memory_hit_rate=-10.0)
        assert baseline.metrics["memory_hit_rate"] == 0.0

        # deduplication_ratio should be clamped to 0-1
        baseline.update_metrics(deduplication_ratio=2.0)
        assert baseline.metrics["deduplication_ratio"] == 1.0

    def test_export_to_redis_keys(self) -> None:
        """Test Redis export returns correct key structure."""
        baseline = RetrievalBaseline()
        result = baseline.export_to_redis()

        assert "baseline_key" in result
        assert "snapshot_key" in result
        assert result["baseline_key"] == BASELINE_CURRENT_KEY
        assert SNAPSHOT_KEY_PREFIX.rstrip(":") in result["snapshot_key"]

    def test_export_to_redis_data(self) -> None:
        """Test Redis export contains valid JSON data."""
        baseline = RetrievalBaseline(
            baseline_id="test-001",
            metrics={
                "retrieval_latency_ms": 25.0,
                "memory_hit_rate": 80.0,
                "deduplication_ratio": 0.7,
            },
        )
        result = baseline.export_to_redis()

        # baseline_data should be valid JSON
        baseline_data = json.loads(result["baseline_data"])
        assert baseline_data["baseline_id"] == "test-001"

        # snapshot_data should be valid JSON
        snapshot_data = json.loads(result["snapshot_data"])
        assert "timestamp" in snapshot_data
        assert "metrics" in snapshot_data

    def test_export_to_redis_with_client(self) -> None:
        """Test Redis export with actual client performs storage."""
        baseline = RetrievalBaseline(baseline_id="redis-test-001")

        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        result = baseline.export_to_redis(redis_client=mock_redis)

        # Verify hset was called for baseline data
        assert (
            mock_redis.hset.call_count >= 4
        )  # baseline_id, created_at, metrics, samples, updated_at

        # Verify expire was called for snapshot
        mock_redis.expire.assert_called()

        # Should not have error
        assert "error" not in result

    def test_create_snapshot(self) -> None:
        """Test creating an AuditSnapshot from baseline."""
        baseline = RetrievalBaseline(
            baseline_id="test-snapshot",
            metrics={
                "retrieval_latency_ms": 15.0,
                "memory_hit_rate": 95.0,
                "deduplication_ratio": 0.9,
            },
            samples=50,
        )
        snapshot = baseline.create_snapshot()

        assert isinstance(snapshot, AuditSnapshot)
        assert snapshot.component == "retrieval_baseline"
        assert snapshot.metrics["retrieval_latency_ms"] == 15.0
        assert snapshot.metadata["baseline_id"] == "test-snapshot"
        assert snapshot.metadata["samples"] == 50

    def test_baseline_to_dict(self) -> None:
        """Test converting baseline to dictionary."""
        baseline = RetrievalBaseline(baseline_id="dict-test", samples=25)
        data = baseline.to_dict()

        assert data["baseline_id"] == "dict-test"
        assert data["samples"] == 25
        assert "created_at" in data
        assert "metrics" in data

    def test_baseline_from_dict(self) -> None:
        """Test creating baseline from dictionary."""
        data = {
            "baseline_id": "restore-test",
            "created_at": "2026-02-22T10:00:00+00:00",
            "metrics": {
                "retrieval_latency_ms": 20.0,
                "memory_hit_rate": 85.0,
                "deduplication_ratio": 0.75,
            },
            "samples": 100,
        }
        baseline = RetrievalBaseline.from_dict(data)

        assert baseline.baseline_id == "restore-test"
        assert baseline.samples == 100
        assert isinstance(baseline.created_at, datetime)

    def test_record_latency_sample(self) -> None:
        """Test recording latency samples for averaging."""
        baseline = RetrievalBaseline()

        baseline.record_latency_sample(10.0)
        baseline.record_latency_sample(20.0)
        baseline.record_latency_sample(30.0)

        assert baseline.metrics["retrieval_latency_ms"] == 20.0  # Average

    def test_record_memory_access(self) -> None:
        """Test recording memory access hits and misses."""
        baseline = RetrievalBaseline()

        # Record 8 hits and 2 misses
        for _ in range(8):
            baseline.record_memory_access(hit=True)
        for _ in range(2):
            baseline.record_memory_access(hit=False)

        assert baseline.metrics["memory_hit_rate"] == 80.0  # 8/10 * 100

    def test_record_dedup_sample(self) -> None:
        """Test recording deduplication samples."""
        baseline = RetrievalBaseline()

        # First batch: 100 total, 70 unique
        baseline.record_dedup_sample(total_items=100, unique_items=70)
        assert baseline.metrics["deduplication_ratio"] == 0.7

        # Second batch: 50 total, 30 unique
        # Cumulative: 150 total, 100 unique
        baseline.record_dedup_sample(total_items=50, unique_items=30)
        assert baseline.metrics["deduplication_ratio"] == 100 / 150

    def test_measure_retrieval_latency(self) -> None:
        """Test measuring retrieval latency via Redis."""
        baseline = RetrievalBaseline()

        mock_redis = MagicMock()
        mock_redis.hget.return_value = None

        latency = baseline.measure_retrieval_latency(mock_redis)

        # Should return a positive latency
        assert latency >= 0.0
        # Should have recorded the sample
        assert len(baseline._latency_samples) == 1

    def test_calculate_memory_hit_rate(self) -> None:
        """Test calculating memory hit rate."""
        baseline = RetrievalBaseline()
        mock_redis = MagicMock()

        # No accesses yet
        rate = baseline.calculate_memory_hit_rate(mock_redis)
        assert rate == 0.0

        # Add some accesses
        baseline.record_memory_access(hit=True)
        baseline.record_memory_access(hit=True)
        baseline.record_memory_access(hit=False)

        rate = baseline.calculate_memory_hit_rate(mock_redis)
        assert rate == pytest.approx(66.666, rel=0.01)

    def test_calculate_deduplication_ratio_with_internal_tracking(self) -> None:
        """Test calculating dedup ratio from internal tracking."""
        baseline = RetrievalBaseline()
        baseline.record_dedup_sample(total_items=100, unique_items=80)

        ratio = baseline.calculate_deduplication_ratio()
        assert ratio == 0.8

    def test_calculate_deduplication_ratio_with_engine(self) -> None:
        """Test calculating dedup ratio from dedup engine."""
        baseline = RetrievalBaseline()

        # Create mock dedup engine
        mock_stats = MagicMock()
        mock_stats.entries_scanned = 1000
        mock_stats.entries_to_remove = 200  # 200 duplicates, 800 unique

        mock_engine = MagicMock()
        mock_engine.get_stats.return_value = mock_stats

        ratio = baseline.calculate_deduplication_ratio(mock_engine)
        assert ratio == 0.8  # 800/1000

    def test_load_from_redis(self) -> None:
        """Test loading baseline from Redis."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            b"baseline_id": b"loaded-001",
            b"created_at": b"2026-02-22T10:00:00+00:00",
            b"metrics": b'{"retrieval_latency_ms": 25.0, "memory_hit_rate": 80.0, "deduplication_ratio": 0.7}',
            b"samples": b"50",
        }

        baseline = RetrievalBaseline.load_from_redis(mock_redis)

        assert baseline is not None
        assert baseline.baseline_id == "loaded-001"
        assert baseline.samples == 50
        assert baseline.metrics["retrieval_latency_ms"] == 25.0

    def test_load_from_redis_not_found(self) -> None:
        """Test loading baseline from Redis when not found."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}

        baseline = RetrievalBaseline.load_from_redis(mock_redis)

        assert baseline is None


class TestEvaluateMetric:
    """Test cases for metric evaluation function."""

    def test_evaluate_latency_excellent(self) -> None:
        """Test latency evaluation for excellent performance."""
        assert evaluate_metric("retrieval_latency_ms", 5.0) == "excellent"
        assert evaluate_metric("retrieval_latency_ms", 10.0) == "excellent"

    def test_evaluate_latency_good(self) -> None:
        """Test latency evaluation for good performance."""
        assert evaluate_metric("retrieval_latency_ms", 25.0) == "good"
        assert evaluate_metric("retrieval_latency_ms", 50.0) == "good"

    def test_evaluate_latency_acceptable(self) -> None:
        """Test latency evaluation for acceptable performance."""
        assert evaluate_metric("retrieval_latency_ms", 75.0) == "acceptable"
        assert evaluate_metric("retrieval_latency_ms", 100.0) == "acceptable"

    def test_evaluate_latency_needs_improvement(self) -> None:
        """Test latency evaluation for poor performance."""
        assert evaluate_metric("retrieval_latency_ms", 150.0) == "needs_improvement"

    def test_evaluate_memory_hit_rate(self) -> None:
        """Test memory hit rate evaluation."""
        assert evaluate_metric("memory_hit_rate", 98.0) == "excellent"
        assert evaluate_metric("memory_hit_rate", 85.0) == "good"
        assert evaluate_metric("memory_hit_rate", 65.0) == "acceptable"
        assert evaluate_metric("memory_hit_rate", 40.0) == "needs_improvement"

    def test_evaluate_deduplication_ratio(self) -> None:
        """Test deduplication ratio evaluation."""
        assert evaluate_metric("deduplication_ratio", 0.95) == "excellent"
        assert evaluate_metric("deduplication_ratio", 0.75) == "good"
        assert evaluate_metric("deduplication_ratio", 0.55) == "acceptable"
        assert evaluate_metric("deduplication_ratio", 0.3) == "needs_improvement"

    def test_evaluate_unknown_metric(self) -> None:
        """Test evaluation for unknown metric."""
        assert evaluate_metric("unknown_metric", 100.0) == "unknown"


class TestMetricThresholds:
    """Test cases for metric thresholds constants."""

    def test_thresholds_exist(self) -> None:
        """Test that all expected thresholds are defined."""
        assert "retrieval_latency_ms" in METRIC_THRESHOLDS
        assert "memory_hit_rate" in METRIC_THRESHOLDS
        assert "deduplication_ratio" in METRIC_THRESHOLDS

    def test_threshold_levels_exist(self) -> None:
        """Test that all threshold levels are defined."""
        for _metric_name, thresholds in METRIC_THRESHOLDS.items():
            assert "excellent" in thresholds
            assert "good" in thresholds
            assert "acceptable" in thresholds

    def test_snapshot_ttl_is_30_days(self) -> None:
        """Test that snapshot TTL is 30 days."""
        expected_ttl = 30 * 24 * 60 * 60  # 30 days in seconds
        assert expected_ttl == SNAPSHOT_TTL_SECONDS

    def test_baseline_key_constant(self) -> None:
        """Test that baseline key constant is correct."""
        assert BASELINE_CURRENT_KEY == "governance:audit:baseline:current"

    def test_snapshot_key_prefix_constant(self) -> None:
        """Test that snapshot key prefix is correct."""
        assert SNAPSHOT_KEY_PREFIX == "governance:audit:snapshot:"


class TestCaptureWeek1Baseline:
    """Test cases for Week 1 baseline capture function."""

    def test_capture_week1_baseline_without_clients(self) -> None:
        """Test capturing Week 1 baseline without Redis/dedup clients."""
        baseline = capture_week1_baseline()

        assert baseline.baseline_id.startswith("week1-")
        assert baseline.metrics["retrieval_latency_ms"] > 0
        assert baseline.metrics["memory_hit_rate"] > 0
        assert baseline.metrics["deduplication_ratio"] > 0

    def test_capture_week1_baseline_with_redis(self) -> None:
        """Test capturing Week 1 baseline with Redis client."""
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        baseline = capture_week1_baseline(redis_client=mock_redis)

        assert baseline.baseline_id.startswith("week1-")
        # Should have measured latency
        assert len(baseline._latency_samples) > 0

    def test_capture_week1_baseline_with_dedup_engine(self) -> None:
        """Test capturing Week 1 baseline with dedup engine."""
        mock_engine = MagicMock()
        mock_stats = MagicMock()
        mock_stats.entries_scanned = 1000
        mock_stats.entries_to_remove = 100
        mock_engine.get_stats.return_value = mock_stats

        baseline = capture_week1_baseline(dedup_engine=mock_engine)

        assert baseline.baseline_id.startswith("week1-")


class TestGetAllMetricRatings:
    """Test cases for get_all_metric_ratings function."""

    def test_get_all_metric_ratings_excellent(self) -> None:
        """Test getting ratings for excellent metrics."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 5.0,
                "memory_hit_rate": 98.0,
                "deduplication_ratio": 0.95,
            }
        )
        ratings = get_all_metric_ratings(baseline)

        assert ratings["retrieval_latency_ms"] == "excellent"
        assert ratings["memory_hit_rate"] == "excellent"
        assert ratings["deduplication_ratio"] == "excellent"

    def test_get_all_metric_ratings_mixed(self) -> None:
        """Test getting ratings for mixed metrics."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 75.0,
                "memory_hit_rate": 65.0,
                "deduplication_ratio": 0.3,
            }
        )
        ratings = get_all_metric_ratings(baseline)

        assert ratings["retrieval_latency_ms"] == "acceptable"
        assert ratings["memory_hit_rate"] == "acceptable"
        assert ratings["deduplication_ratio"] == "needs_improvement"


class TestRedisIntegration:
    """Test cases for Redis storage integration with actual MCP tools."""

    @pytest.mark.integration
    def test_store_snapshot_to_redis_real(self) -> None:
        """Test storing snapshot to Redis using MCP tools."""
        snapshot = AuditSnapshot(
            component="integration_test",
            metrics={"test_value": 42},
            metadata={"source": "integration_test"},
        )

        # Use the MCP redis tools if available
        try:
            from redis import Redis

            redis_client = Redis(
                host="chiseai-redis", port=6380, decode_responses=False
            )
            redis_client.ping()

            key = snapshot.store_to_redis(redis_client)  # type: ignore[arg-type]

            # Verify data was stored
            stored_data = redis_client.hget(key, "data")
            assert stored_data is not None

            # Verify TTL was set
            ttl = int(redis_client.ttl(key))  # type: ignore[assignment]
            assert ttl > 0
            assert ttl <= SNAPSHOT_TTL_SECONDS

            # Cleanup
            redis_client.delete(key)

        except Exception:
            pytest.skip("Redis not available for integration test")

    @pytest.mark.integration
    def test_retrieve_baseline_from_redis_real(self) -> None:
        """Test storing and retrieving baseline from Redis."""
        baseline = RetrievalBaseline(
            baseline_id="integration-test-001",
            metrics={
                "retrieval_latency_ms": 25.0,
                "memory_hit_rate": 85.0,
                "deduplication_ratio": 0.75,
            },
            samples=100,
        )

        try:
            from redis import Redis

            redis_client = Redis(
                host="chiseai-redis", port=6380, decode_responses=False
            )
            redis_client.ping()

            # Store
            baseline.export_to_redis(redis_client=redis_client)  # type: ignore[arg-type]

            # Retrieve
            loaded = RetrievalBaseline.load_from_redis(redis_client)  # type: ignore[arg-type]

            assert loaded is not None
            assert loaded.baseline_id == "integration-test-001"
            assert loaded.metrics["retrieval_latency_ms"] == 25.0
            assert loaded.samples == 100

            # Cleanup
            redis_client.delete(BASELINE_CURRENT_KEY)

        except Exception:
            pytest.skip("Redis not available for integration test")

    @pytest.mark.integration
    def test_redis_key_expiration_real(self) -> None:
        """Test that Redis snapshot keys have proper TTL."""
        snapshot = AuditSnapshot(component="ttl_test")

        try:
            from redis import Redis

            redis_client = Redis(
                host="chiseai-redis", port=6380, decode_responses=False
            )
            redis_client.ping()

            key = snapshot.store_to_redis(redis_client)  # type: ignore[arg-type]

            # Verify TTL is set
            ttl = int(redis_client.ttl(key))  # type: ignore[assignment]
            assert ttl > 0
            assert ttl <= SNAPSHOT_TTL_SECONDS

            # Cleanup
            redis_client.delete(key)

        except Exception:
            pytest.skip("Redis not available for integration test")

    def test_store_snapshot_to_redis_mock(self) -> None:
        """Test storing snapshot to Redis with mock client."""
        snapshot = AuditSnapshot(
            component="mock_test",
            metrics={"mock_value": 123},
            metadata={"source": "unit_test"},
        )

        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        key = snapshot.store_to_redis(mock_redis)

        assert key.startswith(SNAPSHOT_KEY_PREFIX)
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called_once_with(key, SNAPSHOT_TTL_SECONDS)

    def test_retrieve_baseline_from_redis_mock(self) -> None:
        """Test retrieving baseline from Redis with mock client."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            b"baseline_id": b"mock-test-001",
            b"created_at": b"2026-02-22T12:00:00+00:00",
            b"metrics": b'{"retrieval_latency_ms": 30.0, "memory_hit_rate": 85.0, "deduplication_ratio": 0.75}',
            b"samples": b"50",
        }

        baseline = RetrievalBaseline.load_from_redis(mock_redis)

        assert baseline is not None
        assert baseline.baseline_id == "mock-test-001"
        assert baseline.metrics["retrieval_latency_ms"] == 30.0

    def test_redis_key_expiration_mock(self) -> None:
        """Test that Redis keys have proper TTL with mock client."""
        snapshot = AuditSnapshot(component="ttl_mock_test")

        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        snapshot.store_to_redis(mock_redis)

        # Verify expire was called with 30-day TTL
        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == SNAPSHOT_TTL_SECONDS


# Integration test markers
pytestmark = [
    pytest.mark.unit,
]
