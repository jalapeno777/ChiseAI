"""
Unit tests for tempmemory deduplication.

Tests the DeduplicationEngine and EmbeddingGenerator classes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

# Check if sentence-transformers model is available for embedding-dependent tests
try:
    from governance.tempmemory.deduplication import EmbeddingGenerator

    _gen = EmbeddingGenerator()
    _ST_MODEL_AVAILABLE = _gen._model_available
    del _gen
except Exception:
    _ST_MODEL_AVAILABLE = False

from governance.tempmemory.deduplication import (
    DEFAULT_SIMILARITY_THRESHOLD,
    DeduplicationAction,
    DeduplicationEngine,
    DeduplicationResult,
    DuplicateMatch,
    EmbeddingGenerator,
)


class TestEmbeddingGenerator:
    """Test EmbeddingGenerator class."""

    def test_init(self):
        """Test initialization."""
        gen = EmbeddingGenerator()
        assert gen.EMBEDDING_DIM == 384
        assert gen.MODEL_NAME == "all-MiniLM-L6-v2"

    def test_generate_empty_text(self):
        """Test generating embedding for empty text."""
        gen = EmbeddingGenerator()
        embedding = gen.generate("")

        assert len(embedding) == gen.EMBEDDING_DIM
        assert all(v == 0.0 for v in embedding)

    def test_generate_with_text(self):
        """Test generating embedding for text."""
        gen = EmbeddingGenerator()
        embedding = gen.generate("This is a test sentence.")

        assert len(embedding) == gen.EMBEDDING_DIM
        # Should have non-zero values
        assert any(v != 0.0 for v in embedding)

    def test_generate_consistency(self):
        """Test that same text produces same embedding."""
        gen = EmbeddingGenerator()
        text = "Test content"

        embedding1 = gen.generate(text)
        embedding2 = gen.generate(text)

        assert embedding1 == embedding2

    def test_compute_similarity_identical(self):
        """Test similarity of identical embeddings."""
        gen = EmbeddingGenerator()
        embedding = gen.generate("Test content")

        similarity = gen.compute_similarity(embedding, embedding)

        assert similarity == pytest.approx(1.0, abs=0.001)

    def test_compute_similarity_different(self):
        """Test similarity of different embeddings."""
        gen = EmbeddingGenerator()
        embedding1 = gen.generate("Machine learning is fascinating.")
        embedding2 = gen.generate("The weather is nice today.")

        similarity = gen.compute_similarity(embedding1, embedding2)

        # Different content should have lower similarity
        assert 0.0 <= similarity < 0.9

    @pytest.mark.skipif(
        not _ST_MODEL_AVAILABLE,
        reason="sentence-transformers model not available; fallback embeddings produce low similarity",
    )
    def test_compute_similarity_similar_content(self):
        """Test similarity of similar content."""
        gen = EmbeddingGenerator()
        embedding1 = gen.generate("Machine learning is fascinating.")
        embedding2 = gen.generate("Machine learning is interesting.")

        similarity = gen.compute_similarity(embedding1, embedding2)

        # Similar content should have high similarity
        assert similarity > 0.8

    def test_compute_similarity_zero_magnitude(self):
        """Test similarity with zero magnitude vectors."""
        gen = EmbeddingGenerator()
        embedding1 = [0.0] * gen.EMBEDDING_DIM
        embedding2 = gen.generate("Test")

        similarity = gen.compute_similarity(embedding1, embedding2)

        assert similarity == 0.0


class TestDuplicateMatch:
    """Test DuplicateMatch dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        match = DuplicateMatch(
            memory_id="test-memory",
            similarity=0.95,
            content="Test content preview",
            metadata={"story_id": "ST-001"},
        )

        data = match.to_dict()

        assert data["memory_id"] == "test-memory"
        assert data["similarity"] == 0.95
        assert data["content"] == "Test content preview"
        assert data["metadata"] == {"story_id": "ST-001"}


class TestDeduplicationResult:
    """Test DeduplicationResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        match = DuplicateMatch(
            memory_id="test-memory",
            similarity=0.95,
        )

        result = DeduplicationResult(
            is_duplicate=True,
            action=DeduplicationAction.FLAG,
            matches=[match],
            selected_match=match,
            message="Duplicate detected",
        )

        data = result.to_dict()

        assert data["is_duplicate"] is True
        assert data["action"] == "flag"
        assert len(data["matches"]) == 1
        assert data["selected_match"] is not None
        assert data["message"] == "Duplicate detected"


class TestDeduplicationEngine:
    """Test DeduplicationEngine class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.smembers.return_value = set()
        redis.hgetall.return_value = {}
        redis.sadd.return_value = True
        redis.hset.return_value = True
        redis.expire.return_value = True
        return redis

    @pytest.fixture
    def engine(self, mock_redis):
        """Create a DeduplicationEngine instance."""
        return DeduplicationEngine(
            redis_client=mock_redis,
            similarity_threshold=0.92,
            default_action=DeduplicationAction.FLAG,
            dry_run=False,
        )

    def test_init(self, engine, mock_redis):
        """Test initialization."""
        assert engine._redis_client == mock_redis
        assert engine._similarity_threshold == 0.92
        assert engine._default_action == DeduplicationAction.FLAG
        assert engine._dry_run is False

    def test_check_duplicate_no_duplicates(self, engine, mock_redis):
        """Test checking for duplicates when none exist."""
        result = engine.check_duplicate("Unique content that doesn't exist yet")

        assert result.is_duplicate is False
        assert result.action == DeduplicationAction.SKIP  # No action needed
        assert "No duplicates found" in result.message

    def test_check_duplicate_empty_content(self, engine):
        """Test checking with empty content."""
        result = engine.check_duplicate("")

        assert result.is_duplicate is False
        assert "Empty content" in result.message

    def test_index_memory(self, engine, mock_redis):
        """Test indexing a memory."""
        success = engine.index_memory(
            memory_id="test-memory",
            content="Test content",
            metadata={"story_id": "ST-001"},
        )

        assert success is True
        mock_redis.hset.assert_called()
        mock_redis.sadd.assert_called()

    def test_index_memory_dry_run(self, mock_redis):
        """Test indexing in dry-run mode."""
        engine = DeduplicationEngine(
            redis_client=mock_redis,
            dry_run=True,
        )

        success = engine.index_memory(
            memory_id="test-memory",
            content="Test content",
        )

        assert success is True
        mock_redis.hset.assert_not_called()

    def test_remove_from_index(self, engine, mock_redis):
        """Test removing from index."""
        success = engine.remove_from_index("test-memory")

        assert success is True
        mock_redis.delete.assert_called()
        mock_redis.srem.assert_called()

    def test_get_index_stats(self, engine, mock_redis):
        """Test getting index statistics."""
        mock_redis.scard.return_value = 42

        stats = engine.get_index_stats()

        assert stats["total_indexed"] == 42
        assert stats["similarity_threshold"] == 0.92
        assert stats["default_action"] == "flag"
        assert stats["status"] == "active"

    def test_get_index_stats_no_redis(self):
        """Test getting stats without Redis."""
        engine = DeduplicationEngine(redis_client=None)

        stats = engine.get_index_stats()

        assert stats["total_indexed"] == 0
        assert stats["status"] == "no_redis_client"

    def test_clear_index(self, engine, mock_redis):
        """Test clearing the index."""
        mock_redis.smembers.return_value = {b"memory-1", b"memory-2"}

        success = engine.clear_index()

        assert success is True
        assert mock_redis.delete.call_count == 3  # 2 memories + index

    def test_clear_index_dry_run(self, mock_redis):
        """Test clearing in dry-run mode."""
        engine = DeduplicationEngine(
            redis_client=mock_redis,
            dry_run=True,
        )

        success = engine.clear_index()

        assert success is True
        mock_redis.delete.assert_not_called()

    def test_similarity_threshold_default(self):
        """Test default similarity threshold."""
        assert DEFAULT_SIMILARITY_THRESHOLD == 0.92

    @pytest.mark.skipif(
        not _ST_MODEL_AVAILABLE,
        reason="sentence-transformers model not available; fallback embeddings produce low similarity",
    )
    def test_check_duplicate_with_similar_content(self, engine, mock_redis):
        """Test detecting similar content as duplicate."""
        # First index some content
        content1 = "Machine learning is a subset of artificial intelligence."
        gen = EmbeddingGenerator()
        embedding1 = gen.generate(content1)

        # Mock Redis to return the indexed content
        mock_redis.smembers.return_value = {b"memory-1"}
        mock_redis.hgetall.return_value = {
            b"embedding": json.dumps(embedding1).encode(),
            b"content_preview": b"Machine learning is a subset...",
            b"metadata": json.dumps({"story_id": "ST-001"}).encode(),
        }

        # Check very similar content
        content2 = "Machine learning is a subset of AI technology."
        result = engine.check_duplicate(content2)

        # Should detect as duplicate (similar content)
        assert result.is_duplicate is True
        assert len(result.matches) > 0
        assert result.selected_match is not None

    def test_deduplication_actions(self):
        """Test all deduplication actions."""
        assert DeduplicationAction.SKIP.value == "skip"
        assert DeduplicationAction.MERGE.value == "merge"
        assert DeduplicationAction.FLAG.value == "flag"
        assert DeduplicationAction.REPLACE.value == "replace"

    def test_embedding_dimension(self):
        """Test embedding dimension constant."""
        gen = EmbeddingGenerator()
        assert gen.EMBEDDING_DIM == 384

        embedding = gen.generate("Test")
        assert len(embedding) == 384
