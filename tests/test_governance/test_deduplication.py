"""
Tests for Memory Deduplication Engine.

Story: ST-GOV-001
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.governance.deduplication import (
    AuditEntry,
    AuditTrail,
    DEDUPLICATION_PREFIX,
    DeduplicationAction,
    DeduplicationConfig,
    DeduplicationResult,
    DeduplicationStats,
    DeduplicationStrategy,
    DuplicateGroup,
    HashCache,
    HashCacheEntry,
    MemoryDeduplicationEngine,
)


class TestDeduplicationConfig:
    """Tests for DeduplicationConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DeduplicationConfig()
        assert config.similarity_threshold == 0.85
        assert config.qdrant_similarity_threshold == 0.85
        assert config.redis_hash_cache_ttl == 86400
        assert config.batch_size == 100
        assert config.dry_run is True
        assert config.strategy == DeduplicationStrategy.HYBRID
        assert config.collections == ["ChiseAI"]
        assert config.enabled is False
        assert config.hash_algorithm == "sha256"

    def test_validation_similarity_threshold_out_of_range(self):
        """Test validation of similarity threshold."""
        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            DeduplicationConfig(similarity_threshold=1.5)

        with pytest.raises(ValueError, match="similarity_threshold must be between"):
            DeduplicationConfig(similarity_threshold=-0.1)

    def test_validation_batch_size(self):
        """Test validation of batch size."""
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            DeduplicationConfig(batch_size=0)

    def test_to_dict(self):
        """Test serialization to dict."""
        config = DeduplicationConfig(
            similarity_threshold=0.9,
            dry_run=False,
        )
        data = config.to_dict()
        assert data["similarity_threshold"] == 0.9
        assert data["dry_run"] is False
        assert data["strategy"] == "hybrid"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "similarity_threshold": 0.92,
            "dry_run": False,
            "strategy": "exact_match",
            "collections": ["coll1", "coll2"],
        }
        config = DeduplicationConfig.from_dict(data)
        assert config.similarity_threshold == 0.92
        assert config.dry_run is False
        assert config.strategy == DeduplicationStrategy.EXACT_MATCH
        assert config.collections == ["coll1", "coll2"]

    def test_get_collection_threshold(self):
        """Test getting threshold for collection."""
        config = DeduplicationConfig(qdrant_similarity_threshold=0.88)
        assert config.get_collection_threshold("test") == 0.88


class TestHashCacheEntry:
    """Tests for HashCacheEntry."""

    def test_creation(self):
        """Test entry creation."""
        entry = HashCacheEntry(
            content_hash="abc123",
            source_id="point-1",
            collection="ChiseAI",
        )
        assert entry.content_hash == "abc123"
        assert entry.source_id == "point-1"
        assert entry.collection == "ChiseAI"
        assert entry.timestamp is not None

    def test_to_dict(self):
        """Test serialization."""
        ts = datetime.utcnow()
        entry = HashCacheEntry(
            content_hash="abc123",
            source_id="point-1",
            collection="ChiseAI",
            timestamp=ts,
            metadata={"key": "value"},
        )
        data = entry.to_dict()
        assert data["content_hash"] == "abc123"
        assert data["source_id"] == "point-1"
        assert data["timestamp"] == ts.isoformat()

    def test_from_dict(self):
        """Test deserialization."""
        ts = datetime.utcnow()
        data = {
            "content_hash": "abc123",
            "source_id": "point-1",
            "collection": "ChiseAI",
            "timestamp": ts.isoformat(),
            "metadata": {"key": "value"},
        }
        entry = HashCacheEntry.from_dict(data)
        assert entry.content_hash == "abc123"
        assert entry.metadata == {"key": "value"}


class TestHashCache:
    """Tests for HashCache."""

    def test_compute_hash_string(self):
        """Test hash computation for string."""
        cache = HashCache()
        hash1 = cache.compute_hash("test content")
        hash2 = cache.compute_hash("test content")
        hash3 = cache.compute_hash("different content")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_hash_bytes(self):
        """Test hash computation for bytes."""
        cache = HashCache()
        hash1 = cache.compute_hash(b"test content")
        hash2 = cache.compute_hash("test content")

        assert hash1 == hash2

    @patch("redis.Redis")
    def test_is_duplicate_cache_hit(self, mock_redis):
        """Test duplicate detection with cache hit."""
        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps(
            {
                "source_id": "point-1",
                "content_hash": "abc123",
            }
        )
        mock_redis.return_value = mock_client

        cache = HashCache()
        is_dup, source_id = cache.is_duplicate("test content")

        assert is_dup is True
        assert source_id == "point-1"

    @patch("redis.Redis")
    def test_is_duplicate_cache_miss(self, mock_redis):
        """Test duplicate detection with cache miss."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis.return_value = mock_client

        cache = HashCache()
        is_dup, source_id = cache.is_duplicate("test content")

        assert is_dup is False
        assert source_id is None

    @patch("redis.Redis")
    def test_add_hash(self, mock_redis):
        """Test adding hash to cache."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client

        cache = HashCache()
        content_hash = cache.add_hash(
            content="test content",
            source_id="point-1",
            collection="ChiseAI",
        )

        assert len(content_hash) == 64
        mock_client.setex.assert_called_once()

    @patch("redis.Redis")
    def test_get_entry(self, mock_redis):
        """Test retrieving cache entry."""
        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps(
            {
                "content_hash": "abc123",
                "source_id": "point-1",
                "collection": "ChiseAI",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {},
            }
        )
        mock_redis.return_value = mock_client

        cache = HashCache()
        entry = cache.get_entry("abc123")

        assert entry is not None
        assert entry.source_id == "point-1"

    @patch("redis.Redis")
    def test_get_entry_not_found(self, mock_redis):
        """Test retrieving non-existent cache entry."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis.return_value = mock_client

        cache = HashCache()
        entry = cache.get_entry("nonexistent")

        assert entry is None

    @patch("redis.Redis")
    def test_remove_hash(self, mock_redis):
        """Test removing hash from cache."""
        mock_client = MagicMock()
        mock_client.delete.return_value = 1
        mock_redis.return_value = mock_client

        cache = HashCache()
        result = cache.remove_hash("abc123")

        assert result is True

    @patch("redis.Redis")
    def test_get_cache_stats(self, mock_redis):
        """Test getting cache statistics."""
        mock_client = MagicMock()
        mock_client.scan_iter.return_value = ["key1", "key2"]
        mock_redis.return_value = mock_client

        cache = HashCache()
        stats = cache.get_cache_stats()

        assert stats["entry_count"] == 2
        assert stats["ttl_seconds"] == 86400

    @patch("redis.Redis")
    def test_clear_cache(self, mock_redis):
        """Test clearing cache."""
        mock_client = MagicMock()
        mock_client.scan_iter.return_value = ["key1", "key2"]
        mock_client.delete.return_value = 2
        mock_redis.return_value = mock_client

        cache = HashCache()
        count = cache.clear_cache()

        assert count == 2


class TestAuditEntry:
    """Tests for AuditEntry."""

    def test_creation(self):
        """Test entry creation."""
        entry = AuditEntry(
            action=DeduplicationAction.DUPLICATE_DETECTED,
            result=DeduplicationResult.KEPT,
            source_id="point-1",
            collection="ChiseAI",
        )
        assert entry.entry_id is not None
        assert entry.action == DeduplicationAction.DUPLICATE_DETECTED
        assert entry.result == DeduplicationResult.KEPT

    def test_to_dict(self):
        """Test serialization."""
        entry = AuditEntry(
            action=DeduplicationAction.DUPLICATE_REMOVED,
            result=DeduplicationResult.REMOVED,
            source_id="point-1",
            collection="ChiseAI",
            similarity_score=0.92,
            reason="Duplicate detected",
        )
        data = entry.to_dict()
        assert data["action"] == "duplicate_removed"
        assert data["result"] == "removed"
        assert data["similarity_score"] == 0.92

    def test_from_dict(self):
        """Test deserialization."""
        ts = datetime.utcnow()
        data = {
            "entry_id": "test-id",
            "timestamp": ts.isoformat(),
            "action": "similarity_check",
            "result": "kept",
            "source_id": "point-1",
            "collection": "ChiseAI",
            "similarity_score": 0.88,
            "threshold_used": 0.85,
            "strategy": "hybrid",
            "metadata": {},
            "reason": "Test",
        }
        entry = AuditEntry.from_dict(data)
        assert entry.entry_id == "test-id"
        assert entry.action == DeduplicationAction.SIMILARITY_CHECK
        assert entry.similarity_score == 0.88


class TestAuditTrail:
    """Tests for AuditTrail."""

    @patch("redis.Redis")
    def test_log_entry(self, mock_redis):
        """Test logging an audit entry."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client

        trail = AuditTrail()
        entry = trail.log(
            action=DeduplicationAction.DUPLICATE_REMOVED,
            result=DeduplicationResult.REMOVED,
            source_id="point-1",
            collection="ChiseAI",
            similarity_score=0.92,
            reason="High similarity",
        )

        assert entry is not None
        assert entry.action == DeduplicationAction.DUPLICATE_REMOVED
        mock_client.hset.assert_called()
        mock_client.lpush.assert_called()

    @patch("redis.Redis")
    def test_get_entry(self, mock_redis):
        """Test retrieving audit entry."""
        mock_client = MagicMock()
        mock_client.hget.return_value = json.dumps(
            {
                "entry_id": "test-id",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "similarity_check",
                "result": "kept",
                "source_id": "point-1",
                "collection": "ChiseAI",
                "threshold_used": 0.85,
                "strategy": "hybrid",
                "metadata": {},
                "reason": "Test",
            }
        )
        mock_redis.return_value = mock_client

        trail = AuditTrail()
        entry = trail.get_entry("test-id")

        assert entry is not None
        assert entry.source_id == "point-1"

    @patch("redis.Redis")
    def test_get_recent_entries(self, mock_redis):
        """Test retrieving recent entries."""
        mock_client = MagicMock()
        mock_client.lrange.return_value = ["id1", "id2"]
        mock_client.hget.return_value = json.dumps(
            {
                "entry_id": "id1",
                "timestamp": datetime.utcnow().isoformat(),
                "action": "similarity_check",
                "result": "kept",
                "source_id": "point-1",
                "collection": "ChiseAI",
                "threshold_used": 0.85,
                "strategy": "hybrid",
                "metadata": {},
                "reason": "Test",
            }
        )
        mock_redis.return_value = mock_client

        trail = AuditTrail()
        entries = trail.get_recent_entries(limit=10)

        assert len(entries) == 2

    @patch("redis.Redis")
    def test_get_stats(self, mock_redis):
        """Test getting audit statistics."""
        mock_client = MagicMock()
        mock_client.scan_iter.return_value = ["key1", "key2"]
        mock_client.hget.return_value = json.dumps(
            {
                "action": "duplicate_detected",
                "result": "kept",
            }
        )
        mock_redis.return_value = mock_client

        trail = AuditTrail()
        stats = trail.get_stats()

        assert stats["total_entries"] == 2
        assert "duplicate_detected" in stats["action_counts"]

    @patch("redis.Redis")
    def test_clear(self, mock_redis):
        """Test clearing audit trail."""
        mock_client = MagicMock()
        mock_client.scan_iter.return_value = ["key1", "key2"]
        mock_client.delete.return_value = 2
        mock_redis.return_value = mock_client

        trail = AuditTrail()
        count = trail.clear()

        assert count == 2


class TestDeduplicationStats:
    """Tests for DeduplicationStats."""

    def test_creation(self):
        """Test stats creation."""
        stats = DeduplicationStats(
            entries_scanned=100,
            duplicate_groups=5,
            entries_removed=10,
        )
        assert stats.entries_scanned == 100
        assert stats.duplicate_groups == 5
        assert stats.entries_removed == 10
        assert stats.timestamp is not None

    def test_to_dict(self):
        """Test serialization."""
        stats = DeduplicationStats(
            entries_scanned=100,
            cache_hits=20,
            cache_misses=80,
        )
        data = stats.to_dict()
        assert data["entries_scanned"] == 100
        assert data["cache_hits"] == 20
        assert data["cache_misses"] == 80
        assert "timestamp" in data


class TestDuplicateGroup:
    """Tests for DuplicateGroup."""

    def test_creation(self):
        """Test group creation."""
        group = DuplicateGroup(
            canonical_id="point-1",
            duplicate_ids=["point-2", "point-3"],
            collection="ChiseAI",
            similarity_score=0.92,
            reason="High similarity",
        )
        assert group.canonical_id == "point-1"
        assert len(group.duplicate_ids) == 2
        assert group.similarity_score == 0.92

    def test_to_dict(self):
        """Test serialization."""
        group = DuplicateGroup(
            canonical_id="point-1",
            duplicate_ids=["point-2"],
            collection="ChiseAI",
            similarity_score=0.92,
        )
        data = group.to_dict()
        assert data["canonical_id"] == "point-1"
        assert data["duplicate_ids"] == ["point-2"]


class TestMemoryDeduplicationEngine:
    """Tests for MemoryDeduplicationEngine."""

    def test_initialization(self):
        """Test engine initialization."""
        engine = MemoryDeduplicationEngine()
        assert engine.config is not None
        assert engine.hash_cache is not None
        assert engine.audit_trail is not None

    def test_initialization_with_config(self):
        """Test engine initialization with custom config."""
        config = DeduplicationConfig(similarity_threshold=0.9)
        engine = MemoryDeduplicationEngine(config)
        assert engine.config.similarity_threshold == 0.9

    @patch("redis.Redis")
    def test_is_enabled_true(self, mock_redis):
        """Test checking if enabled when true."""
        mock_client = MagicMock()
        mock_client.get.return_value = b"true"
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        assert engine.is_enabled() is True

    @patch("redis.Redis")
    def test_is_enabled_false(self, mock_redis):
        """Test checking if enabled when false."""
        mock_client = MagicMock()
        mock_client.get.return_value = b"false"
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        assert engine.is_enabled() is False

    @patch("redis.Redis")
    def test_enable(self, mock_redis):
        """Test enabling deduplication."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        engine.enable()

        mock_client.set.assert_called_with(
            "chise:feature_flags:governance:memory_dedup_enabled",
            "true",
        )
        assert engine.config.enabled is True

    @patch("redis.Redis")
    def test_disable(self, mock_redis):
        """Test disabling deduplication."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        engine.disable()

        mock_client.set.assert_called_with(
            "chise:feature_flags:governance:memory_dedup_enabled",
            "false",
        )
        assert engine.config.enabled is False

    @patch("redis.Redis")
    def test_check_duplicate_cache_hit(self, mock_redis):
        """Test duplicate check with cache hit."""
        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps(
            {
                "source_id": "point-1",
                "content_hash": "abc123",
            }
        )
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        is_dup, score, source_id = engine.check_duplicate("test content")

        assert is_dup is True
        assert score == 1.0
        assert source_id == "point-1"

    @patch("redis.Redis")
    def test_check_duplicate_cache_miss(self, mock_redis):
        """Test duplicate check with cache miss."""
        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        is_dup, score, source_id = engine.check_duplicate("test content")

        assert is_dup is False
        assert score is None
        assert source_id is None

    def test_exact_match_similarity(self):
        """Test exact match similarity calculation."""
        engine = MemoryDeduplicationEngine()

        # Create mock points
        point_a = MagicMock()
        point_a.payload = {"content": "test content"}

        point_b = MagicMock()
        point_b.payload = {"content": "test content"}

        point_c = MagicMock()
        point_c.payload = {"content": "different content"}

        assert engine._exact_match_similarity(point_a, point_b) == 1.0
        assert engine._exact_match_similarity(point_a, point_c) == 0.0

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        engine = MemoryDeduplicationEngine()

        # Create mock points with vectors
        point_a = MagicMock()
        point_a.vector = [1.0, 0.0, 0.0]

        point_b = MagicMock()
        point_b.vector = [1.0, 0.0, 0.0]

        point_c = MagicMock()
        point_c.vector = [0.0, 1.0, 0.0]

        # Same vectors should have similarity 1.0
        assert abs(engine._cosine_similarity(point_a, point_b) - 1.0) < 0.001

        # Orthogonal vectors should have similarity 0.0
        assert abs(engine._cosine_similarity(point_a, point_c) - 0.0) < 0.001

    def test_temporal_similarity(self):
        """Test temporal similarity calculation."""
        engine = MemoryDeduplicationEngine(
            config=DeduplicationConfig(temporal_window_seconds=3600)
        )

        now = datetime.utcnow()

        point_a = MagicMock()
        point_a.payload = {
            "content": "test",
            "timestamp": now.isoformat(),
        }

        point_b = MagicMock()
        point_b.payload = {
            "content": "test",
            "timestamp": (now + timedelta(minutes=30)).isoformat(),
        }

        point_c = MagicMock()
        point_c.payload = {
            "content": "test",
            "timestamp": (now + timedelta(hours=2)).isoformat(),
        }

        # Within window, same content = match
        assert engine._temporal_similarity(point_a, point_b) == 1.0

        # Outside window = no match
        assert engine._temporal_similarity(point_a, point_c) == 0.0

    def test_hybrid_similarity(self):
        """Test hybrid similarity calculation."""
        engine = MemoryDeduplicationEngine()

        point_a = MagicMock()
        point_a.payload = {"content": "test"}
        point_a.vector = [1.0, 0.0, 0.0]

        point_b = MagicMock()
        point_b.payload = {"content": "test"}
        point_b.vector = [0.0, 1.0, 0.0]

        point_c = MagicMock()
        point_c.payload = {"content": "different"}
        point_c.vector = [0.0, 1.0, 0.0]

        # Same content should match via exact match
        assert engine._hybrid_similarity(point_a, point_b) == 1.0

        # Different content but similar vectors
        similarity = engine._hybrid_similarity(point_b, point_c)
        assert similarity == 1.0  # Vector similarity

    def test_calculate_max_similarity(self):
        """Test max similarity calculation in group."""
        engine = MemoryDeduplicationEngine()

        ref = MagicMock()
        ref.vector = [1.0, 0.0, 0.0]
        ref.payload = {"content": "test"}

        similar = [
            MagicMock(vector=[0.9, 0.1, 0.0], payload={"content": "a"}),
            MagicMock(vector=[0.5, 0.5, 0.0], payload={"content": "b"}),
        ]

        max_sim = engine._calculate_max_similarity(ref, similar)
        assert max_sim > 0.9  # Should be high due to first similar point

    @patch("redis.Redis")
    @patch("qdrant_client.QdrantClient")
    def test_deduplicate_dry_run(self, mock_qdrant, mock_redis):
        """Test deduplication in dry run mode."""
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client

        mock_qdrant_client = MagicMock()
        mock_qdrant_client.scroll.return_value = ([], None)
        mock_qdrant.return_value = mock_qdrant_client

        engine = MemoryDeduplicationEngine(config=DeduplicationConfig(dry_run=True))
        stats = engine.deduplicate()

        assert stats.was_dry_run is True
        assert stats.collections_scanned == 1  # Default collection

    @patch("redis.Redis")
    @patch("qdrant_client.QdrantClient")
    def test_deduplicate_with_duplicates(self, mock_qdrant, mock_redis):
        """Test deduplication finding duplicates."""
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client

        # Create mock points with duplicates
        point1 = MagicMock()
        point1.id = "id1"
        point1.payload = {"content": "duplicate content"}
        point1.vector = [1.0, 0.0, 0.0]

        point2 = MagicMock()
        point2.id = "id2"
        point2.payload = {"content": "duplicate content"}
        point2.vector = [1.0, 0.0, 0.0]

        mock_qdrant_client = MagicMock()
        mock_qdrant_client.scroll.return_value = ([point1, point2], None)
        mock_qdrant.return_value = mock_qdrant_client

        engine = MemoryDeduplicationEngine(
            config=DeduplicationConfig(
                dry_run=True,
                strategy=DeduplicationStrategy.EXACT_MATCH,
            )
        )
        stats = engine.deduplicate()

        assert stats.entries_scanned == 2
        assert stats.duplicate_groups == 1
        assert stats.entries_to_remove == 1

    def test_find_duplicates(self):
        """Test finding duplicate groups."""
        engine = MemoryDeduplicationEngine(
            config=DeduplicationConfig(strategy=DeduplicationStrategy.EXACT_MATCH)
        )

        point1 = MagicMock()
        point1.id = "id1"
        point1.payload = {"content": "test content"}
        point1.vector = [1.0, 0.0]

        point2 = MagicMock()
        point2.id = "id2"
        point2.payload = {"content": "test content"}
        point2.vector = [1.0, 0.0]

        point3 = MagicMock()
        point3.id = "id3"
        point3.payload = {"content": "different"}
        point3.vector = [0.0, 1.0]

        points = [point1, point2, point3]
        groups = engine._find_duplicates(points, 0.85, "test")

        assert len(groups) == 1
        assert groups[0].canonical_id == "id1"
        assert groups[0].duplicate_ids == ["id2"]

    def test_find_similar_points(self):
        """Test finding similar points."""
        engine = MemoryDeduplicationEngine(
            config=DeduplicationConfig(strategy=DeduplicationStrategy.EXACT_MATCH)
        )

        ref = MagicMock()
        ref.id = "ref"
        ref.payload = {"content": "test"}
        ref.vector = [1.0, 0.0]

        candidates = [
            MagicMock(id="a", payload={"content": "test"}, vector=[1.0, 0.0]),
            MagicMock(id="b", payload={"content": "different"}, vector=[0.0, 1.0]),
        ]

        similar = engine._find_similar_points(ref, candidates, 0.85, "test")

        assert len(similar) == 1
        assert similar[0].id == "a"

    @patch("redis.Redis")
    def test_get_stats(self, mock_redis):
        """Test retrieving deduplication stats."""
        mock_client = MagicMock()
        mock_client.scan_iter.return_value = ["stats:1", "stats:2"]
        mock_client.hgetall.side_effect = [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "collections_scanned": "1",
                "entries_scanned": "100",
                "duplicate_groups": "5",
                "entries_to_remove": "10",
                "entries_removed": "0",
                "cache_hits": "20",
                "cache_misses": "80",
                "similarity_checks": "50",
                "processing_time_seconds": "1.5",
                "was_dry_run": "true",
                "errors": "[]",
            },
            {
                "timestamp": datetime.utcnow().isoformat(),
                "collections_scanned": "1",
                "entries_scanned": "50",
                "duplicate_groups": "2",
                "entries_to_remove": "4",
                "entries_removed": "4",
                "cache_hits": "10",
                "cache_misses": "40",
                "similarity_checks": "20",
                "processing_time_seconds": "0.8",
                "was_dry_run": "false",
                "errors": "[]",
            },
        ]
        mock_redis.return_value = mock_client

        engine = MemoryDeduplicationEngine()
        stats = engine.get_stats(limit=2)

        assert len(stats) == 2
        assert stats[0].entries_scanned == 100
        assert stats[1].entries_scanned == 50
