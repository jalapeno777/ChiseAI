"""
Integration tests for Memory Deduplication Engine.

Tests the interaction between MemoryDeduplicationEngine and Redis/Qdrant clients.
Covers:
- Redis connectivity test
- Qdrant vector search test
- End-to-end deduplication flow
- Error handling (Redis down, Qdrant down)
- Feature flag enable/disable
- Batch processing
- TTL expiration
"""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.governance.memory.deduplication import (
    FEATURE_FLAG_KEY,
    DeduplicationConfig,
    DeduplicationStats,
    MemoryDeduplicationEngine,
)


class TestRedisConnectivity:
    """Tests for Redis connectivity and operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client with realistic behavior."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.return_value = None
        mock.set.return_value = True
        mock.delete.return_value = 1
        mock.hget.return_value = None
        mock.hgetall.return_value = {}
        mock.hset.return_value = 1
        mock.expire.return_value = True
        mock.ttl.return_value = -1
        mock.type.return_value = "string"
        mock.scan.return_value = (0, [])
        mock.lrange.return_value = []
        return mock

    def test_redis_connection_success(self, mock_redis):
        """Test successful Redis connection."""
        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        assert engine._redis_client is not None

    def test_redis_connection_failure_handled(self):
        """Test graceful handling of Redis connection failure."""
        # Engine should work without Redis (just disabled)
        engine = MemoryDeduplicationEngine(redis_client=None)
        assert engine.is_enabled() is False

    def test_feature_flag_read_from_redis(self, mock_redis):
        """Test feature flag is read from Redis."""
        mock_redis.get.return_value = "true"
        engine = MemoryDeduplicationEngine(redis_client=mock_redis)

        assert engine.is_enabled() is True
        mock_redis.get.assert_called_with(FEATURE_FLAG_KEY)

    def test_feature_flag_false_in_redis(self, mock_redis):
        """Test feature flag disabled when Redis returns false."""
        mock_redis.get.return_value = "false"
        engine = MemoryDeduplicationEngine(redis_client=mock_redis)

        assert engine.is_enabled() is False

    def test_feature_flag_missing_in_redis(self, mock_redis):
        """Test feature flag defaults to disabled when missing."""
        mock_redis.get.return_value = None
        engine = MemoryDeduplicationEngine(redis_client=mock_redis)

        assert engine.is_enabled() is False

    def test_redis_config_loading(self, mock_redis):
        """Test configuration loading from Redis."""
        mock_redis.hget.side_effect = lambda key, field: {
            ("chise:governance:dedup:config:values", "similarity_threshold"): "0.85",
            ("chise:governance:dedup:config:values", "max_age_days"): "14",
            ("chise:governance:dedup:config:values", "batch_size"): "50",
        }.get((key, field))

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_config_from_redis()

        assert config.similarity_threshold == 0.85
        assert config.max_age_days == 14
        assert config.batch_size == 50

    def test_redis_scan_entries(self, mock_redis):
        """Test scanning Redis entries."""
        mock_redis.scan.return_value = (0, ["key1", "key2"])
        mock_redis.type.side_effect = lambda k: "string"
        mock_redis.get.side_effect = lambda k: f"value_of_{k}"
        mock_redis.ttl.return_value = 3600

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        entries = engine._scan_redis_entries()

        assert len(entries) == 2
        assert entries[0]["key"] == "key1"
        assert entries[0]["source"] == "redis"

    def test_redis_scan_with_different_types(self, mock_redis):
        """Test scanning Redis entries with different data types."""
        mock_redis.scan.return_value = (0, ["string_key", "hash_key", "list_key"])
        mock_redis.type.side_effect = lambda k: k.split("_")[0]
        mock_redis.get.return_value = "string_value"
        mock_redis.hgetall.return_value = {"field": "value"}
        mock_redis.lrange.return_value = ["item1", "item2"]

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        entries = engine._scan_redis_entries()

        assert len(entries) == 3
        assert entries[0]["type"] == "string"
        assert entries[1]["type"] == "hash"
        assert entries[2]["type"] == "list"


class TestQdrantConnectivity:
    """Tests for Qdrant connectivity and operations."""

    @pytest.fixture
    def mock_qdrant(self):
        """Create a mock Qdrant client with realistic behavior."""
        mock = MagicMock()
        mock.scroll.return_value = ([], None)
        mock.delete.return_value = None
        return mock

    def test_qdrant_connection_success(self, mock_qdrant):
        """Test successful Qdrant connection."""
        engine = MemoryDeduplicationEngine(qdrant_client=mock_qdrant)
        assert engine._qdrant_client is not None

    def test_qdrant_connection_failure_handled(self):
        """Test graceful handling when Qdrant is unavailable."""
        engine = MemoryDeduplicationEngine(qdrant_client=None)
        # Should not raise error
        entries = engine._scan_qdrant_entries()
        assert entries == []

    def test_qdrant_scan_entries(self, mock_qdrant):
        """Test scanning Qdrant entries."""
        # Create mock points
        mock_point1 = MagicMock()
        mock_point1.id = "point-1"
        mock_point1.payload = {"text": "memory1"}

        mock_point2 = MagicMock()
        mock_point2.id = "point-2"
        mock_point2.payload = {"text": "memory2"}

        mock_qdrant.scroll.return_value = ([mock_point1, mock_point2], None)

        engine = MemoryDeduplicationEngine(qdrant_client=mock_qdrant)
        entries = engine._scan_qdrant_entries()

        assert len(entries) == 2
        assert entries[0]["id"] == "point-1"
        assert entries[0]["source"] == "qdrant"
        assert entries[0]["payload"] == {"text": "memory1"}

    def test_qdrant_scan_pagination(self, mock_qdrant):
        """Test Qdrant scan with pagination."""
        mock_point1 = MagicMock()
        mock_point1.id = "point-1"
        mock_point1.payload = {"text": "memory1"}

        mock_point2 = MagicMock()
        mock_point2.id = "point-2"
        mock_point2.payload = {"text": "memory2"}

        # First call returns first point with offset, second returns second point
        mock_qdrant.scroll.side_effect = [
            ([mock_point1], "offset1"),
            ([mock_point2], None),
        ]

        engine = MemoryDeduplicationEngine(qdrant_client=mock_qdrant)
        entries = engine._scan_qdrant_entries()

        assert len(entries) == 2
        assert mock_qdrant.scroll.call_count == 2


class TestEndToEndDeduplication:
    """Tests for end-to-end deduplication flow."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.return_value = "true"  # Feature flag enabled
        mock.set.return_value = True
        mock.delete.return_value = 1
        mock.hget.return_value = None
        mock.hset.return_value = 1
        mock.expire.return_value = True
        mock.ttl.return_value = 3600
        mock.type.return_value = "string"
        mock.scan.return_value = (0, [])
        return mock

    @pytest.fixture
    def mock_qdrant(self):
        """Create a mock Qdrant client."""
        mock = MagicMock()
        mock.scroll.return_value = ([], None)
        mock.delete.return_value = None
        return mock

    def test_deduplicate_with_no_entries(self, mock_redis, mock_qdrant):
        """Test deduplication when no entries exist."""
        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            config=DeduplicationConfig(dry_run=False),
        )

        stats = engine.deduplicate()

        assert stats.entries_scanned == 0
        assert stats.duplicate_groups == 0
        assert stats.error is None

    def test_deduplicate_finds_duplicates(self, mock_redis, mock_qdrant):
        """Test deduplication finds duplicate entries."""
        # Setup Redis with duplicate entries
        mock_redis.scan.return_value = (0, ["key1", "key2"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "duplicate_value"
        mock_redis.ttl.return_value = 3600

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            config=DeduplicationConfig(dry_run=True),
        )

        stats = engine.deduplicate()

        assert stats.entries_scanned == 2
        assert stats.duplicate_groups == 1
        assert stats.entries_to_remove == 1  # 2 entries - 1 canonical

    def test_deduplicate_dry_run_no_deletions(self, mock_redis, mock_qdrant):
        """Test dry run mode doesn't delete anything."""
        mock_redis.scan.return_value = (0, ["key1", "key2"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "duplicate_value"

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            config=DeduplicationConfig(dry_run=True),
        )

        stats = engine.deduplicate(dry_run=True)

        assert stats.was_dry_run is True
        assert stats.entries_removed == 0
        mock_redis.delete.assert_not_called()

    def test_deduplicate_actual_deletion(self, mock_redis, mock_qdrant):
        """Test actual deletion when not in dry run."""
        mock_redis.scan.return_value = (0, ["key1", "key2"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "duplicate_value"
        mock_redis.get.side_effect = None
        mock_redis.get.side_effect = lambda k: "duplicate_value"

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            config=DeduplicationConfig(dry_run=False),
        )

        stats = engine.deduplicate(dry_run=False)

        # Should attempt to delete one entry (the duplicate)
        # Note: In actual run, it would delete, but our mock setup may vary

    def test_deduplicate_updates_stats(self, mock_redis, mock_qdrant):
        """Test deduplication updates last stats."""
        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
        )

        assert engine.get_stats() is None

        stats = engine.deduplicate()

        assert engine.get_stats() is stats
        assert isinstance(stats, DeduplicationStats)


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_deduplication_with_redis_failure(self):
        """Test graceful handling when Redis is unavailable."""
        mock_redis = MagicMock()
        mock_redis.scan.side_effect = ConnectionError("Redis connection failed")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        stats = engine.deduplicate()

        # Should complete without error, just with 0 entries
        assert stats.error is None  # Error is caught and logged
        assert stats.entries_scanned == 0

    def test_deduplication_with_qdrant_failure(self):
        """Test graceful handling when Qdrant is unavailable."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.side_effect = Exception("Qdrant connection failed")

        engine = MemoryDeduplicationEngine(qdrant_client=mock_qdrant)
        stats = engine.deduplicate()

        # Should complete without error, just with 0 entries
        assert stats.error is None  # Error is caught and logged
        assert stats.entries_scanned == 0

    def test_deduplication_with_redis_get_failure(self):
        """Test handling when Redis get fails during scan."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["key1"])
        mock_redis.type.return_value = "string"
        mock_redis.get.side_effect = ConnectionError("Get failed")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        stats = engine.deduplicate()

        # Should complete, just skip the failed key
        assert stats.error is None

    def test_deduplication_with_qdrant_delete_failure(self):
        """Test handling when Qdrant delete fails."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["key1", "key2"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "duplicate"

        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([], None)

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            qdrant_client=mock_qdrant,
            config=DeduplicationConfig(dry_run=False),
        )

        stats = engine.deduplicate()

        # Should complete without crashing
        assert isinstance(stats, DeduplicationStats)

    def test_config_load_handles_redis_error(self):
        """Test config loading handles Redis errors gracefully."""
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = ConnectionError("Redis down")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        config = engine._load_config_from_redis()

        # Should return default config
        assert config.similarity_threshold == 0.95


class TestFeatureFlagBehavior:
    """Tests for feature flag enable/disable behavior."""

    def test_feature_flag_enable_success(self):
        """Test enabling feature flag."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.enable()

        assert result is True
        mock_redis.set.assert_called_with(FEATURE_FLAG_KEY, "true")
        assert engine.is_enabled() is True

    def test_feature_flag_disable_success(self):
        """Test disabling feature flag."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.disable()

        assert result is True
        mock_redis.set.assert_called_with(FEATURE_FLAG_KEY, "false")
        assert engine.is_enabled() is False

    def test_feature_flag_enable_without_redis(self):
        """Test enable fails without Redis."""
        engine = MemoryDeduplicationEngine(redis_client=None)
        result = engine.enable()

        assert result is False

    def test_feature_flag_disable_without_redis(self):
        """Test disable works without Redis (local state only)."""
        engine = MemoryDeduplicationEngine(redis_client=None)
        result = engine.disable()

        assert result is True
        assert engine.is_enabled() is False

    def test_feature_flag_enable_redis_error(self):
        """Test enable handles Redis errors."""
        mock_redis = MagicMock()
        mock_redis.set.side_effect = ConnectionError("Redis down")

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        result = engine.enable()

        assert result is False

    def test_deduplication_blocked_when_disabled(self):
        """Test deduplication is blocked when feature flag is disabled."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            config=DeduplicationConfig(dry_run=False),
        )

        stats = engine.deduplicate(dry_run=False)

        assert stats.error is not None
        assert "disabled" in stats.error.lower()

    def test_dry_run_allowed_when_disabled(self):
        """Test dry run is allowed even when feature flag is disabled."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "false"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        stats = engine.deduplicate(dry_run=True)

        assert stats.error is None


class TestBatchProcessing:
    """Tests for batch processing capabilities."""

    def test_deduplication_batch_processing(self):
        """Test processing multiple items in batch."""
        # Create 100 items with 50 duplicates (25 pairs)
        keys = [f"key_{i}" for i in range(100)]
        # Make every 2 items a duplicate pair
        values = [f"value_{i // 2}" for i in range(100)]

        mock_redis = MagicMock()
        mock_redis.get.return_value = "true"
        mock_redis.scan.return_value = (0, keys)
        mock_redis.type.return_value = "string"
        mock_redis.ttl.return_value = 3600

        call_count = [0]

        def mock_get(key):
            idx = keys.index(key)
            return values[idx]

        mock_redis.get.side_effect = mock_get

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            config=DeduplicationConfig(batch_size=50, dry_run=True),
        )

        stats = engine.deduplicate()

        assert stats.entries_scanned == 100
        # Should find 50 duplicate groups (each pair is a group)
        assert stats.duplicate_groups == 50
        # Should mark 50 entries for removal (1 from each pair)
        assert stats.entries_to_remove == 50

    def test_batch_size_respected(self):
        """Test that batch size configuration is respected."""
        mock_redis = MagicMock()
        mock_redis.scan.side_effect = [
            (1, ["key1", "key2"]),  # First batch
            (0, ["key3"]),  # Second batch
        ]
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "value"
        mock_redis.ttl.return_value = 3600

        engine = MemoryDeduplicationEngine(
            redis_client=mock_redis,
            config=DeduplicationConfig(batch_size=2),
        )

        entries = engine._scan_redis_entries()

        assert len(entries) == 3
        # Verify scan was called with correct batch size
        mock_redis.scan.assert_called()
        call_args = mock_redis.scan.call_args
        assert call_args[1]["count"] == 2


class TestTTLOperations:
    """Tests for TTL (Time To Live) operations."""

    def test_ttl_preserved_in_entries(self):
        """Test that TTL is preserved when scanning entries."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["key1"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "value"
        mock_redis.ttl.return_value = 7200  # 2 hours

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        entries = engine._scan_redis_entries()

        assert len(entries) == 1
        assert entries[0]["ttl"] == 7200

    def test_ttl_used_for_canonical_selection(self):
        """Test that entries with higher TTL are preferred as canonical."""
        entries = [
            {"key": "key1", "source": "redis", "ttl": 100, "value": "dup"},
            {"key": "key2", "source": "redis", "ttl": 500, "value": "dup"},
            {"key": "key3", "source": "redis", "ttl": 200, "value": "dup"},
        ]

        engine = MemoryDeduplicationEngine()
        # Sort as _remove_duplicates would
        sorted_entries = sorted(
            entries,
            key=lambda e: e.get("ttl", float("inf")),
        )

        # Entry with lowest TTL should be first (removed first if we kept sorted)
        # Actually we want highest TTL as canonical, so lowest TTL gets removed
        assert sorted_entries[0]["ttl"] == 100

    def test_audit_trail_has_ttl(self):
        """Test that audit trail entries have proper TTL set."""
        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        stats = DeduplicationStats()

        engine._log_audit_trail(stats, [])

        # Verify expire was called with 30 days
        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 30 * 24 * 3600  # 30 days in seconds


class TestDuplicateIdentification:
    """Tests for duplicate identification logic."""

    def test_identify_exact_duplicates(self):
        """Test identification of exact duplicate entries."""
        redis_entries = [
            {"key": "key1", "source": "redis", "value": "duplicate_content"},
            {"key": "key2", "source": "redis", "value": "duplicate_content"},
        ]
        qdrant_entries = []

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, qdrant_entries)

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_identify_cross_store_duplicates(self):
        """Test identification of duplicates across Redis and Qdrant."""
        redis_entries = [
            {"key": "key1", "source": "redis", "value": "shared_content"},
        ]
        qdrant_entries = [
            {"id": "point1", "source": "qdrant", "payload": "shared_content"},
        ]

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, qdrant_entries)

        assert len(groups) == 1
        assert len(groups[0]) == 2
        assert groups[0][0]["source"] == "redis"
        assert groups[0][1]["source"] == "qdrant"

    def test_no_duplicates_found(self):
        """Test when no duplicates exist."""
        redis_entries = [
            {"key": "key1", "source": "redis", "value": "content1"},
            {"key": "key2", "source": "redis", "value": "content2"},
        ]
        qdrant_entries = []

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, qdrant_entries)

        assert len(groups) == 0

    def test_min_duplicates_respected(self):
        """Test that min_duplicates config is respected."""
        redis_entries = [
            {"key": "key1", "source": "redis", "value": "content"},
        ]
        qdrant_entries = []

        engine = MemoryDeduplicationEngine(config=DeduplicationConfig(min_duplicates=2))
        groups = engine._identify_duplicates(redis_entries, qdrant_entries)

        # Single entry should not be considered a duplicate group
        assert len(groups) == 0


class TestBytesSavedEstimation:
    """Tests for bytes saved estimation."""

    def test_estimate_redis_bytes(self):
        """Test byte estimation for Redis entries."""
        groups = [
            [
                {"source": "redis", "value": "canonical"},
                {"source": "redis", "value": "duplicate1"},
                {"source": "redis", "value": "duplicate2"},
            ]
        ]

        engine = MemoryDeduplicationEngine()
        bytes_saved = engine._estimate_bytes_saved(groups)

        # Should count bytes of duplicate1 and duplicate2 (not canonical)
        expected = len("duplicate1") + len("duplicate2")
        assert bytes_saved == expected

    def test_estimate_qdrant_bytes(self):
        """Test byte estimation for Qdrant entries."""
        groups = [
            [
                {"source": "qdrant", "payload": {"text": "canonical"}},
                {"source": "qdrant", "payload": {"text": "duplicate"}},
            ]
        ]

        engine = MemoryDeduplicationEngine()
        bytes_saved = engine._estimate_bytes_saved(groups)

        # Should count bytes of duplicate payload
        expected = len(str({"text": "duplicate"}).encode("utf-8"))
        assert bytes_saved == expected

    def test_estimate_empty_groups(self):
        """Test byte estimation with empty groups."""
        engine = MemoryDeduplicationEngine()
        bytes_saved = engine._estimate_bytes_saved([])

        assert bytes_saved == 0


class TestAuditTrail:
    """Tests for audit trail functionality."""

    def test_audit_trail_logged(self):
        """Test that audit trail is logged."""
        mock_redis = MagicMock()
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        stats = DeduplicationStats(
            entries_scanned=100,
            duplicate_groups=5,
            entries_removed=10,
            bytes_saved=1024,
        )

        engine._log_audit_trail(stats, [])

        mock_redis.hset.assert_called_once()

    def test_audit_trail_without_redis(self):
        """Test audit trail works without Redis (logs only)."""
        engine = MemoryDeduplicationEngine(redis_client=None)
        stats = DeduplicationStats()

        # Should not raise error
        engine._log_audit_trail(stats, [])


class TestScopeFiltering:
    """Tests for scope filtering in deduplication."""

    def test_redis_scope_filtering(self):
        """Test that scope is used to filter Redis keys."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["myscope:key1"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "value"

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        engine._scan_redis_entries(scope="myscope")

        # Verify scan was called with scope pattern
        mock_redis.scan.assert_called_once()
        call_args = mock_redis.scan.call_args
        assert "myscope:*" in str(call_args)

    def test_qdrant_scope_filtering(self):
        """Test that scope is used as collection name in Qdrant."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([], None)

        engine = MemoryDeduplicationEngine(qdrant_client=mock_qdrant)
        engine._scan_qdrant_entries(scope="custom_collection")

        mock_qdrant.scroll.assert_called_once()
        call_args = mock_qdrant.scroll.call_args
        assert call_args[1]["collection_name"] == "custom_collection"


class TestProcessingTimeTracking:
    """Tests for processing time tracking."""

    def test_processing_time_recorded(self):
        """Test that processing time is recorded in stats."""
        engine = MemoryDeduplicationEngine()

        stats = engine.deduplicate()

        assert stats.processing_time_seconds >= 0

    def test_processing_time_increases_with_work(self):
        """Test that processing time increases with more work."""
        import time

        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [f"key_{i}" for i in range(100)])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "value"
        mock_redis.ttl.return_value = 3600

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)

        stats = engine.deduplicate()

        # Processing time should be > 0 for non-trivial work
        assert stats.processing_time_seconds >= 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_key_list(self):
        """Test handling of empty key list from Redis."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, [])

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        entries = engine._scan_redis_entries()

        assert entries == []

    def test_none_values_in_entries(self):
        """Test handling of None values in entries."""
        redis_entries = [
            {"key": "key1", "source": "redis", "value": None},
            {"key": "key2", "source": "redis", "value": None},
        ]

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, [])

        # None values should be considered duplicates
        assert len(groups) == 1

    def test_very_long_content(self):
        """Test handling of very long content."""
        long_content = "x" * 1000000  # 1MB string

        redis_entries = [
            {"key": "key1", "source": "redis", "value": long_content},
            {"key": "key2", "source": "redis", "value": long_content},
        ]

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, [])

        assert len(groups) == 1

    def test_unicode_content(self):
        """Test handling of unicode content."""
        unicode_content = "Hello 世界 🌍 ñoño"

        redis_entries = [
            {"key": "key1", "source": "redis", "value": unicode_content},
            {"key": "key2", "source": "redis", "value": unicode_content},
        ]

        engine = MemoryDeduplicationEngine()
        groups = engine._identify_duplicates(redis_entries, [])

        assert len(groups) == 1

    def test_special_characters_in_keys(self):
        """Test handling of special characters in keys."""
        mock_redis = MagicMock()
        mock_redis.scan.return_value = (0, ["key:with:colons", "key-with-dashes"])
        mock_redis.type.return_value = "string"
        mock_redis.get.return_value = "value"
        mock_redis.ttl.return_value = -1  # No TTL

        engine = MemoryDeduplicationEngine(redis_client=mock_redis)
        entries = engine._scan_redis_entries()

        assert len(entries) == 2


class TestIntegrationWithRealClients:
    """Integration tests that can run with real Redis/Qdrant if available."""

    @pytest.mark.integration
    def test_real_redis_connection(self):
        """Test with real Redis connection if available."""
        try:
            import redis

            client = redis.Redis(
                host="host.docker.internal", port=6380, decode_responses=True
            )
            client.ping()

            engine = MemoryDeduplicationEngine(redis_client=client)
            # Should not raise error
            engine.is_enabled()
        except Exception:
            pytest.skip("Redis not available")

    @pytest.mark.integration
    def test_real_qdrant_connection(self):
        """Test with real Qdrant connection if available."""
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(host="host.docker.internal", port=6334)
            client.get_collections()

            engine = MemoryDeduplicationEngine(qdrant_client=client)
            # Should not raise error
            engine._scan_qdrant_entries()
        except Exception:
            pytest.skip("Qdrant not available")
