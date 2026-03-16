"""Tests for BeliefSearchIndex and vector search functionality."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from src.strong_system.belief_embeddings import (
    BeliefMetadata,
    BeliefSearchIndex,
    BeliefVector,
    InMemoryBackend,
    SearchResult,
    ValidationError,
)
from src.strong_system.belief_embeddings.search import QDRANT_AVAILABLE

if QDRANT_AVAILABLE:
    from src.strong_system.belief_embeddings.search import QdrantBackend


class TestSearchResult:
    """Tests for SearchResult class."""

    def test_default_creation(self) -> None:
        """Test creating search result with minimum required fields."""
        result = SearchResult(belief_id="test_001", score=0.95)
        assert result.belief_id == "test_001"
        assert result.score == 0.95
        assert result.vector is None
        assert result.metadata is None

    def test_full_creation(self) -> None:
        """Test creating search result with all fields."""
        vector = np.array([1.0, 2.0, 3.0])
        metadata = BeliefMetadata(confidence=0.9, source="test")
        result = SearchResult(
            belief_id="test_002",
            score=0.85,
            vector=vector,
            metadata=metadata,
        )
        assert result.belief_id == "test_002"
        assert result.score == 0.85
        assert np.array_equal(result.vector, vector)
        assert result.metadata.confidence == 0.9

    def test_to_dict_minimal(self) -> None:
        """Test converting result to dict with minimal fields."""
        result = SearchResult(belief_id="test_003", score=0.75)
        data = result.to_dict()
        assert data == {"belief_id": "test_003", "score": 0.75}

    def test_to_dict_full(self) -> None:
        """Test converting result to dict with all fields."""
        vector = np.array([1.0, 2.0])
        metadata = BeliefMetadata(confidence=0.8)
        result = SearchResult(
            belief_id="test_004",
            score=0.90,
            vector=vector,
            metadata=metadata,
        )
        data = result.to_dict()
        assert data["belief_id"] == "test_004"
        assert data["score"] == 0.90
        assert data["vector"] == [1.0, 2.0]
        assert data["metadata"]["confidence"] == 0.8

    def test_repr(self) -> None:
        """Test string representation."""
        result = SearchResult(belief_id="test_005", score=0.1234)
        repr_str = repr(result)
        assert "test_005" in repr_str
        assert "0.1234" in repr_str


class TestInMemoryBackend:
    """Tests for InMemoryBackend class."""

    def test_add_belief(self) -> None:
        """Test adding a belief to the index."""
        backend = InMemoryBackend()
        belief = BeliefVector(
            vector=np.array([1.0, 2.0, 3.0]),
            belief_id="belief_001",
        )
        backend.add_belief(belief)
        assert len(backend._beliefs) == 1
        assert "belief_001" in backend._beliefs

    def test_add_multiple_beliefs(self) -> None:
        """Test adding multiple beliefs."""
        backend = InMemoryBackend()
        for i in range(5):
            belief = BeliefVector(
                vector=np.random.randn(10),
                belief_id=f"belief_{i}",
            )
            backend.add_belief(belief)
        assert len(backend._beliefs) == 5

    def test_search_empty_index(self) -> None:
        """Test searching in empty index returns empty list."""
        backend = InMemoryBackend()
        results = backend.search(np.array([1.0, 2.0, 3.0]), k=5)
        assert results == []

    def test_search_returns_correct_number(self) -> None:
        """Test search returns requested number of results."""
        backend = InMemoryBackend()
        for i in range(10):
            belief = BeliefVector(
                vector=np.random.randn(5),
                belief_id=f"belief_{i}",
            )
            backend.add_belief(belief)

        results = backend.search(np.random.randn(5), k=3)
        assert len(results) == 3

    def test_search_returns_sorted_results(self) -> None:
        """Test search results are sorted by similarity descending."""
        backend = InMemoryBackend()
        # Add beliefs with known similarities
        beliefs = [
            BeliefVector(vector=np.array([1.0, 0.0, 0.0]), belief_id="a"),
            BeliefVector(vector=np.array([0.0, 1.0, 0.0]), belief_id="b"),
            BeliefVector(vector=np.array([0.9, 0.1, 0.0]), belief_id="c"),
        ]
        for belief in beliefs:
            backend.add_belief(belief)

        # Search with vector close to [1, 0, 0]
        results = backend.search(np.array([1.0, 0.0, 0.0]), k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_dimension_mismatch_skips(self) -> None:
        """Test search skips beliefs with different dimensions."""
        backend = InMemoryBackend()
        backend.add_belief(BeliefVector(vector=np.array([1.0, 2.0]), belief_id="dim2"))
        backend.add_belief(
            BeliefVector(vector=np.array([1.0, 2.0, 3.0]), belief_id="dim3")
        )

        results = backend.search(np.array([1.0, 0.0, 0.0]), k=5)
        assert len(results) == 1
        assert results[0].belief_id == "dim3"

    def test_delete_belief_exists(self) -> None:
        """Test deleting an existing belief."""
        backend = InMemoryBackend()
        backend.add_belief(BeliefVector(vector=np.array([1.0]), belief_id="to_delete"))

        result = backend.delete_belief("to_delete")
        assert result is True
        assert len(backend._beliefs) == 0

    def test_delete_belief_not_exists(self) -> None:
        """Test deleting a non-existent belief returns False."""
        backend = InMemoryBackend()
        result = backend.delete_belief("nonexistent")
        assert result is False

    def test_get_belief_exists(self) -> None:
        """Test getting an existing belief."""
        backend = InMemoryBackend()
        original = BeliefVector(vector=np.array([1.0, 2.0]), belief_id="get_test")
        backend.add_belief(original)

        retrieved = backend.get_belief("get_test")
        assert retrieved is not None
        assert retrieved.belief_id == "get_test"
        assert np.array_equal(retrieved.vector, np.array([1.0, 2.0]))

    def test_get_belief_not_exists(self) -> None:
        """Test getting a non-existent belief returns None."""
        backend = InMemoryBackend()
        result = backend.get_belief("nonexistent")
        assert result is None

    def test_to_dict(self) -> None:
        """Test serializing backend to dict."""
        backend = InMemoryBackend()
        backend.add_belief(BeliefVector(vector=np.array([1.0, 2.0]), belief_id="b1"))
        backend.add_belief(BeliefVector(vector=np.array([3.0, 4.0]), belief_id="b2"))

        data = backend.to_dict()
        assert "beliefs" in data
        assert len(data["beliefs"]) == 2

    def test_from_dict(self) -> None:
        """Test deserializing backend from dict."""
        data = {
            "beliefs": [
                {
                    "belief_id": "b1",
                    "vector": [1.0, 2.0],
                    "metadata": {"confidence": 0.9},
                },
                {
                    "belief_id": "b2",
                    "vector": [3.0, 4.0],
                    "metadata": {"confidence": 0.8},
                },
            ]
        }

        backend = InMemoryBackend.from_dict(data)
        assert len(backend._beliefs) == 2
        assert "b1" in backend._beliefs
        assert "b2" in backend._beliefs


class TestBeliefSearchIndex:
    """Tests for BeliefSearchIndex class."""

    def test_default_creation(self) -> None:
        """Test creating index with defaults."""
        index = BeliefSearchIndex()
        assert isinstance(index.backend, InMemoryBackend)
        assert index.auto_persist is False
        assert index.persist_path is None

    def test_add_belief(self) -> None:
        """Test adding a belief to the index."""
        index = BeliefSearchIndex()
        belief = BeliefVector(vector=np.array([1.0, 2.0, 3.0]), belief_id="test_add")
        index.add_belief(belief)
        assert len(index) == 1

    def test_add_belief_with_auto_persist(self) -> None:
        """Test that auto-persist saves on add."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "index.json")
            index = BeliefSearchIndex(
                auto_persist=True,
                persist_path=filepath,
            )
            belief = BeliefVector(vector=np.array([1.0]), belief_id="persist_test")
            index.add_belief(belief)

            # Check file was created
            assert os.path.exists(filepath)

    def test_search_basic(self) -> None:
        """Test basic search functionality."""
        index = BeliefSearchIndex()
        for i in range(5):
            belief = BeliefVector(
                vector=np.random.randn(10),
                belief_id=f"belief_{i}",
            )
            index.add_belief(belief)

        results = index.search(np.random.randn(10), k=3)
        assert len(results) <= 3

    def test_search_validation_not_array(self) -> None:
        """Test search validates query is numpy array."""
        index = BeliefSearchIndex()
        with pytest.raises(ValidationError, match="must be numpy.ndarray"):
            index.search([1.0, 2.0, 3.0], k=5)  # type: ignore[arg-type]

    def test_search_validation_wrong_dims(self) -> None:
        """Test search validates 1D array."""
        index = BeliefSearchIndex()
        with pytest.raises(ValidationError, match="must be 1-dimensional"):
            index.search(np.array([[1.0, 2.0], [3.0, 4.0]]), k=5)

    def test_search_validation_empty(self) -> None:
        """Test search validates non-empty array."""
        index = BeliefSearchIndex()
        with pytest.raises(ValidationError, match="cannot be empty"):
            index.search(np.array([]), k=5)

    def test_search_by_similarity(self) -> None:
        """Test searching by existing belief."""
        index = BeliefSearchIndex()
        query = BeliefVector(vector=np.array([1.0, 0.0]), belief_id="query")
        for i in range(5):
            belief = BeliefVector(
                vector=np.random.randn(2),
                belief_id=f"belief_{i}",
            )
            index.add_belief(belief)

        results = index.search_by_similarity(query, k=3)
        # Should not include the query belief itself
        assert all(r.belief_id != "query" for r in results)

    def test_search_by_similarity_excludes_self(self) -> None:
        """Test search_by_similarity excludes the query belief."""
        index = BeliefSearchIndex()
        belief = BeliefVector(vector=np.array([1.0, 0.0]), belief_id="self_test")
        index.add_belief(belief)

        # Add more beliefs
        for i in range(5):
            index.add_belief(
                BeliefVector(
                    vector=np.random.randn(2),
                    belief_id=f"other_{i}",
                )
            )

        results = index.search_by_similarity(belief, k=5)
        assert "self_test" not in [r.belief_id for r in results]

    def test_delete_belief(self) -> None:
        """Test deleting a belief."""
        index = BeliefSearchIndex()
        index.add_belief(BeliefVector(vector=np.array([1.0]), belief_id="to_delete"))

        result = index.delete_belief("to_delete")
        assert result is True
        assert len(index) == 0

    def test_delete_belief_with_auto_persist(self) -> None:
        """Test auto-persist on delete."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "index.json")
            index = BeliefSearchIndex(
                auto_persist=True,
                persist_path=filepath,
            )
            index.add_belief(
                BeliefVector(vector=np.array([1.0]), belief_id="to_delete")
            )
            mtime_before = os.path.getmtime(filepath)

            index.delete_belief("to_delete")
            mtime_after = os.path.getmtime(filepath)
            assert mtime_after >= mtime_before

    def test_delete_nonexistent(self) -> None:
        """Test deleting non-existent belief returns False."""
        index = BeliefSearchIndex()
        result = index.delete_belief("nonexistent")
        assert result is False

    def test_get_belief(self) -> None:
        """Test getting a belief by ID."""
        index = BeliefSearchIndex()
        original = BeliefVector(vector=np.array([1.0, 2.0]), belief_id="get_test")
        index.add_belief(original)

        retrieved = index.get_belief("get_test")
        assert retrieved is not None
        assert retrieved.belief_id == "get_test"

    def test_get_belief_nonexistent(self) -> None:
        """Test getting non-existent belief returns None."""
        index = BeliefSearchIndex()
        result = index.get_belief("nonexistent")
        assert result is None

    def test_save_and_load(self) -> None:
        """Test saving and loading index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "index.json")
            index = BeliefSearchIndex()
            index.add_belief(BeliefVector(vector=np.array([1.0]), belief_id="b1"))
            index.add_belief(BeliefVector(vector=np.array([2.0]), belief_id="b2"))

            index.save(filepath)
            assert os.path.exists(filepath)

            # Load and verify
            loaded = BeliefSearchIndex.load(filepath)
            assert len(loaded) == 2
            assert loaded.get_belief("b1") is not None
            assert loaded.get_belief("b2") is not None

    def test_save_invalid_backend(self) -> None:
        """Test save raises error for non-serializable backend."""
        if not QDRANT_AVAILABLE:
            pytest.skip("Qdrant not available")

        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = "QdrantBackend"
        index = BeliefSearchIndex(backend=mock_backend)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="only supported for InMemoryBackend"):
            index.save("/tmp/test.json")

    def test_len_empty(self) -> None:
        """Test len on empty index."""
        index = BeliefSearchIndex()
        assert len(index) == 0

    def test_len_with_beliefs(self) -> None:
        """Test len with beliefs."""
        index = BeliefSearchIndex()
        for i in range(5):
            index.add_belief(BeliefVector(vector=np.array([1.0]), belief_id=f"b{i}"))
        assert len(index) == 5

    def test_repr(self) -> None:
        """Test string representation."""
        index = BeliefSearchIndex()
        repr_str = repr(index)
        assert "BeliefSearchIndex" in repr_str
        assert "InMemoryBackend" in repr_str


class TestBeliefSearchIndexFactoryMethods:
    """Tests for factory methods."""

    def test_create_with_qdrant(self) -> None:
        """Test creating index with Qdrant backend."""
        if not QDRANT_AVAILABLE:
            pytest.skip("qdrant-client not installed")

        with patch.object(QdrantBackend, "_get_client") as mock_client:
            mock_client.return_value = MagicMock()
            index = BeliefSearchIndex.create_with_qdrant()
            assert isinstance(index.backend, QdrantBackend)

    def test_create_with_qdrant_import_error(self) -> None:
        """Test that ImportError is raised if qdrant not available."""
        if QDRANT_AVAILABLE:
            pytest.skip("qdrant-client is installed")

        with pytest.raises(ImportError, match="qdrant-client is required"):
            BeliefSearchIndex.create_with_qdrant()

    def test_create_with_fallback_success(self) -> None:
        """Test fallback when Qdrant is available."""
        if not QDRANT_AVAILABLE:
            pytest.skip("qdrant-client not installed")

        with patch.object(QdrantBackend, "_get_client") as mock_client:
            mock_client.return_value = MagicMock()
            index = BeliefSearchIndex.create_with_fallback()
            assert isinstance(index.backend, QdrantBackend)

    def test_create_with_fallback_to_memory(self) -> None:
        """Test fallback to in-memory when Qdrant fails."""
        if not QDRANT_AVAILABLE:
            # Without qdrant, should always return in-memory
            index = BeliefSearchIndex.create_with_fallback()
            assert isinstance(index.backend, InMemoryBackend)
        else:
            # With qdrant but failing connection
            with patch.object(
                QdrantBackend, "_get_client", side_effect=Exception("Connection failed")
            ):
                index = BeliefSearchIndex.create_with_fallback()
                assert isinstance(index.backend, InMemoryBackend)

    def test_create_with_fallback_no_qdrant(self) -> None:
        """Test fallback when Qdrant is not installed."""
        if QDRANT_AVAILABLE:
            pytest.skip("qdrant-client is installed")

        index = BeliefSearchIndex.create_with_fallback()
        assert isinstance(index.backend, InMemoryBackend)


@pytest.mark.skipif(not QDRANT_AVAILABLE, reason="qdrant-client not installed")
class TestQdrantBackend:
    """Tests for QdrantBackend (requires qdrant-client)."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        backend = QdrantBackend()
        assert backend.host == "host.docker.internal"
        assert backend.port == 6334
        assert backend.collection_name == "ChiseAI"
        assert backend.dimension == 384

    def test_init_custom_values(self) -> None:
        """Test initialization with custom values."""
        backend = QdrantBackend(
            host="localhost",
            port=8080,
            collection_name="custom",
            dimension=768,
        )
        assert backend.host == "localhost"
        assert backend.port == 8080
        assert backend.collection_name == "custom"
        assert backend.dimension == 768

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization from environment variables."""
        monkeypatch.setenv("QDRANT_HOST", "qdrant.example.com")
        monkeypatch.setenv("QDRANT_PORT", "9999")
        backend = QdrantBackend()
        assert backend.host == "qdrant.example.com"
        assert backend.port == 9999

    def test_add_belief_dimension_mismatch(self) -> None:
        """Test that dimension mismatch raises error."""
        with patch.object(QdrantBackend, "_ensure_collection"):
            backend = QdrantBackend(dimension=10)
            backend._client = MagicMock()

            belief = BeliefVector(vector=np.array([1.0] * 5), belief_id="test")
            with pytest.raises(ValidationError, match="dimension"):
                backend.add_belief(belief)

    def test_search_dimension_mismatch(self) -> None:
        """Test that search dimension mismatch raises error."""
        with patch.object(QdrantBackend, "_ensure_collection"):
            backend = QdrantBackend(dimension=10)
            backend._client = MagicMock()

            with pytest.raises(ValidationError, match="dimension"):
                backend.search(np.array([1.0] * 5), k=5)


class TestSearchIntegration:
    """Integration tests for search functionality."""

    def test_end_to_end_search_workflow(self) -> None:
        """Test complete workflow: add, search, delete."""
        index = BeliefSearchIndex()

        # Add beliefs
        beliefs = [
            BeliefVector(vector=np.array([1.0, 0.0, 0.0]), belief_id="belief_a"),
            BeliefVector(vector=np.array([0.9, 0.1, 0.0]), belief_id="belief_b"),
            BeliefVector(vector=np.array([0.0, 1.0, 0.0]), belief_id="belief_c"),
            BeliefVector(vector=np.array([0.0, 0.0, 1.0]), belief_id="belief_d"),
        ]
        for belief in beliefs:
            index.add_belief(belief)

        assert len(index) == 4

        # Search for similar beliefs
        query = np.array([1.0, 0.0, 0.0])
        results = index.search(query, k=2)

        assert len(results) == 2
        # Most similar should be belief_a (exact match) or belief_b (close)
        assert results[0].belief_id in ["belief_a", "belief_b"]
        assert results[0].score > results[1].score

        # Delete a belief
        deleted = index.delete_belief("belief_c")
        assert deleted is True
        assert len(index) == 3

        # Verify deletion
        assert index.get_belief("belief_c") is None

    def test_search_by_similarity_integration(self) -> None:
        """Test search_by_similarity in integration."""
        index = BeliefSearchIndex()

        # Create query belief
        query_belief = BeliefVector(
            vector=np.array([1.0, 0.5, 0.0]),
            belief_id="query",
            metadata=BeliefMetadata(confidence=0.95),
        )

        # Create target beliefs
        targets = [
            BeliefVector(vector=np.array([1.0, 0.4, 0.1]), belief_id="target_1"),
            BeliefVector(vector=np.array([0.1, 0.9, 0.0]), belief_id="target_2"),
            BeliefVector(vector=np.array([0.8, 0.3, 0.2]), belief_id="target_3"),
        ]

        for target in targets:
            index.add_belief(target)
        index.add_belief(query_belief)

        # Search by similarity
        results = index.search_by_similarity(query_belief, k=2)

        # Should not include query itself
        assert len(results) <= 2
        assert "query" not in [r.belief_id for r in results]

    def test_persistence_round_trip(self) -> None:
        """Test full save and load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "round_trip.json")

            # Create and populate index
            original = BeliefSearchIndex()
            beliefs = [
                BeliefVector(
                    vector=np.array([1.0, 2.0, 3.0]),
                    belief_id=f"belief_{i}",
                    metadata=BeliefMetadata(confidence=0.5 + i * 0.05),
                )
                for i in range(10)
            ]
            for belief in beliefs:
                original.add_belief(belief)

            # Save
            original.save(filepath)

            # Load and verify
            loaded = BeliefSearchIndex.load(filepath)
            assert len(loaded) == 10

            # Verify all beliefs are preserved
            for i in range(10):
                belief_id = f"belief_{i}"
                retrieved = loaded.get_belief(belief_id)
                assert retrieved is not None
                assert retrieved.belief_id == belief_id

    def test_search_with_metadata(self) -> None:
        """Test that metadata is preserved in search results."""
        backend = InMemoryBackend()
        index = BeliefSearchIndex(backend=backend)

        belief = BeliefVector(
            vector=np.array([1.0, 0.0]),
            belief_id="meta_test",
            metadata=BeliefMetadata(
                confidence=0.88,
                source="integration_test",
                custom={"test_key": "test_value"},
            ),
        )
        index.add_belief(belief)

        results = index.search(np.array([1.0, 0.0]), k=1)
        assert len(results) == 1
        assert results[0].metadata is not None
        assert results[0].metadata.confidence == 0.88
        assert results[0].metadata.source == "integration_test"

    def test_cosine_similarity_accuracy(self) -> None:
        """Test that search uses accurate cosine similarity."""
        index = BeliefSearchIndex()

        # Add orthogonal vectors
        index.add_belief(BeliefVector(vector=np.array([1.0, 0.0]), belief_id="x_axis"))
        index.add_belief(BeliefVector(vector=np.array([0.0, 1.0]), belief_id="y_axis"))
        index.add_belief(
            BeliefVector(vector=np.array([1.0, 1.0]), belief_id="diagonal")
        )

        # Search with x-axis
        results = index.search(np.array([1.0, 0.0]), k=3)

        # x_axis should be most similar (cosine = 1.0)
        assert results[0].belief_id == "x_axis"
        assert results[0].score > 0.99  # Close to 1.0

        # diagonal should be second (cosine ≈ 0.707)
        assert results[1].belief_id == "diagonal"
        assert 0.7 < results[1].score < 0.8

        # y_axis should be last (cosine = 0.0)
        assert results[2].belief_id == "y_axis"
        assert results[2].score < 0.1  # Close to 0.0
