"""Tests for BeliefIndex and related classes."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.strong_system.belief_embeddings import (
    BeliefClusteringEngine,
    BeliefIndex,
    BeliefSearchIndex,
    BeliefVector,
    ClusterInfo,
    HierarchicalLevel,
    IndexError,
    InMemoryBackend,
    ValidationError,
)


class TestClusterInfo:
    """Tests for ClusterInfo class."""

    def test_default_creation(self) -> None:
        """Test creating cluster info with defaults."""
        info = ClusterInfo(cluster_id=5)
        assert info.cluster_id == 5
        assert info.size == 0
        assert info.centroid is None
        assert info.belief_ids == []
        assert info.parent_cluster is None
        assert info.metadata == {}

    def test_custom_creation(self) -> None:
        """Test creating cluster info with custom values."""
        centroid = np.array([1.0, 2.0, 3.0])
        info = ClusterInfo(
            cluster_id=1,
            size=25,
            centroid=centroid,
            belief_ids=["b1", "b2", "b3"],
            parent_cluster=0,
            metadata={"source": "test"},
        )
        assert info.cluster_id == 1
        assert info.size == 25
        assert np.allclose(info.centroid, centroid)
        assert info.belief_ids == ["b1", "b2", "b3"]
        assert info.parent_cluster == 0
        assert info.metadata == {"source": "test"}

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        centroid = np.array([1.0, 2.0])
        info = ClusterInfo(
            cluster_id=2,
            size=10,
            centroid=centroid,
            belief_ids=["a", "b"],
        )
        data = info.to_dict()
        assert data["cluster_id"] == 2
        assert data["size"] == 10
        assert data["centroid"] == [1.0, 2.0]
        assert data["belief_ids"] == ["a", "b"]

    def test_to_dict_no_centroid(self) -> None:
        """Test conversion without centroid."""
        info = ClusterInfo(cluster_id=1)
        data = info.to_dict()
        assert data["centroid"] is None

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "cluster_id": 3,
            "size": 15,
            "centroid": [1.0, 2.0, 3.0],
            "belief_ids": ["id1", "id2"],
            "parent_cluster": 0,
            "metadata": {"test": True},
        }
        info = ClusterInfo.from_dict(data)
        assert info.cluster_id == 3
        assert info.size == 15
        assert np.allclose(info.centroid, [1.0, 2.0, 3.0])
        assert info.belief_ids == ["id1", "id2"]
        assert info.parent_cluster == 0
        assert info.metadata == {"test": True}

    def test_from_dict_no_centroid(self) -> None:
        """Test creation from dictionary without centroid."""
        data = {"cluster_id": 1, "size": 5}
        info = ClusterInfo.from_dict(data)
        assert info.centroid is None


class TestHierarchicalLevel:
    """Tests for HierarchicalLevel class."""

    def test_creation(self) -> None:
        """Test creating hierarchical level."""
        engine = BeliefClusteringEngine(n_clusters=3)
        level = HierarchicalLevel(level=0, engine=engine)
        assert level.level == 0
        assert level.engine == engine
        assert level.clusters == {}

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        engine = BeliefClusteringEngine(n_clusters=2)
        level = HierarchicalLevel(level=1, engine=engine)
        level.clusters[0] = ClusterInfo(cluster_id=0, size=5)

        data = level.to_dict()
        assert data["level"] == 1
        assert "engine" in data
        assert "clusters" in data

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "level": 2,
            "engine": {"algorithm": "kmeans", "n_clusters": 3},
            "clusters": {
                "0": {"cluster_id": 0, "size": 10},
                "1": {"cluster_id": 1, "size": 5},
            },
        }
        level = HierarchicalLevel.from_dict(data)
        assert level.level == 2
        assert level.engine.algorithm == "kmeans"
        assert len(level.clusters) == 2


class TestBeliefIndexInitialization:
    """Tests for BeliefIndex initialization."""

    def test_default_creation(self) -> None:
        """Test creating index with defaults."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        assert index.enable_hierarchy is False
        assert index.hierarchy_depth == 2
        assert index.get_cluster_count() == 0
        assert index.get_belief_count() == 0

    def test_custom_creation(self) -> None:
        """Test creating index with custom parameters."""
        engine = BeliefClusteringEngine(n_clusters=5)
        search_index = BeliefSearchIndex.create_with_fallback()

        index = BeliefIndex(
            clustering_engine=engine,
            search_index=search_index,
            enable_hierarchy=True,
            hierarchy_depth=3,
        )

        assert index.clustering_engine == engine
        assert index.search_index == search_index
        assert index.enable_hierarchy is True
        assert index.hierarchy_depth == 3

    def test_repr(self) -> None:
        """Test string representation."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        repr_str = repr(index)
        assert "BeliefIndex" in repr_str
        assert "clusters=0" in repr_str
        assert "beliefs=0" in repr_str


class TestBeliefIndexBuild:
    """Tests for building the index."""

    def _create_sample_beliefs(self, n: int = 30, dim: int = 10) -> list[BeliefVector]:
        """Create sample beliefs for testing."""
        np.random.seed(42)
        beliefs = []
        for i in range(n):
            vector = np.random.randn(dim)
            belief = BeliefVector(
                vector=vector,
                belief_id=f"belief_{i:03d}",
            )
            beliefs.append(belief)
        return beliefs

    def test_build_index(self) -> None:
        """Test building the index."""
        beliefs = self._create_sample_beliefs(n=50)
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)

        metrics = index.build(beliefs, min_k=2, max_k=5)

        assert index.get_cluster_count() > 0
        assert index.get_belief_count() == 50
        assert metrics is not None
        assert index.get_metrics() == metrics

    def test_build_empty_beliefs(self) -> None:
        """Test that building with empty beliefs raises error."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        with pytest.raises(IndexError, match="empty beliefs"):
            index.build([])

    def test_build_dimension_mismatch(self) -> None:
        """Test that dimension mismatch raises error."""
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id="b1"),
            BeliefVector(vector=np.random.randn(20), belief_id="b2"),
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        with pytest.raises(ValidationError, match="same dimension"):
            index.build(beliefs)

    def test_build_creates_clusters(self) -> None:
        """Test that build creates cluster info."""
        beliefs = self._create_sample_beliefs(n=40)
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        engine = BeliefClusteringEngine(n_clusters=3, auto_select_k=False)
        index = BeliefIndex(clustering_engine=engine, search_index=search_index)
        index.build(beliefs)

        clusters = index.get_all_clusters()
        assert len(clusters) == 3

        for cluster_id in clusters:
            info = index.get_cluster(cluster_id)
            assert info is not None
            assert info.cluster_id == cluster_id
            assert info.size > 0


class TestBeliefIndexClusterLookup:
    """Tests for cluster lookup operations."""

    def _create_and_build_index(self, n: int = 30) -> BeliefIndex:
        """Create and build index with sample data."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"belief_{i:03d}")
            for i in range(n)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        index.build(beliefs)
        return index, beliefs

    def test_get_cluster(self) -> None:
        """Test getting cluster info."""
        index, _ = self._create_and_build_index()
        cluster_id = index.get_all_clusters()[0]

        info = index.get_cluster(cluster_id)

        assert info is not None
        assert info.cluster_id == cluster_id
        assert info.size > 0

    def test_get_cluster_not_found(self) -> None:
        """Test getting non-existent cluster."""
        index, _ = self._create_and_build_index()
        info = index.get_cluster(999)
        assert info is None

    def test_get_belief_cluster(self) -> None:
        """Test getting cluster for a belief."""
        index, beliefs = self._create_and_build_index()
        belief_id = beliefs[0].belief_id

        cluster_id = index.get_belief_cluster(belief_id)

        assert cluster_id is not None
        assert cluster_id in index.get_all_clusters()

    def test_get_belief_cluster_not_found(self) -> None:
        """Test getting cluster for non-existent belief."""
        index, _ = self._create_and_build_index()
        cluster_id = index.get_belief_cluster("nonexistent")
        assert cluster_id is None

    def test_get_cluster_beliefs(self) -> None:
        """Test getting beliefs in a cluster."""
        index, _ = self._create_and_build_index()
        cluster_id = index.get_all_clusters()[0]

        beliefs = index.get_cluster_beliefs(cluster_id)

        assert isinstance(beliefs, list)
        assert len(beliefs) > 0

    def test_get_all_clusters(self) -> None:
        """Test getting all cluster IDs."""
        index, _ = self._create_and_build_index(n=50)
        clusters = index.get_all_clusters()

        assert isinstance(clusters, list)
        assert len(clusters) > 0
        for cluster_id in clusters:
            assert isinstance(cluster_id, int)

    def test_get_cluster_count(self) -> None:
        """Test getting cluster count."""
        index, _ = self._create_and_build_index()
        count = index.get_cluster_count()

        assert isinstance(count, int)
        assert count > 0
        assert count == len(index.get_all_clusters())

    def test_get_belief_count(self) -> None:
        """Test getting belief count."""
        index, beliefs = self._create_and_build_index(n=40)
        count = index.get_belief_count()

        assert count == 40
        assert count == len(beliefs)


class TestBeliefIndexClusterStatistics:
    """Tests for cluster statistics."""

    def _create_and_build_index(self) -> BeliefIndex:
        """Create and build index."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(30)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        index.build(beliefs)
        return index

    def test_get_cluster_statistics(self) -> None:
        """Test getting cluster statistics."""
        index = self._create_and_build_index()
        cluster_id = index.get_all_clusters()[0]

        stats = index.get_cluster_statistics(cluster_id)

        assert "cluster_id" in stats
        assert "size" in stats
        assert "belief_count" in stats
        assert stats["cluster_id"] == cluster_id

    def test_get_cluster_statistics_not_found(self) -> None:
        """Test statistics for non-existent cluster."""
        index = self._create_and_build_index()
        stats = index.get_cluster_statistics(999)

        assert "error" in stats

    def test_get_metrics(self) -> None:
        """Test getting cluster metrics."""
        index = self._create_and_build_index()
        metrics = index.get_metrics()

        assert metrics is not None
        assert metrics.num_clusters > 0


class TestBeliefIndexSearch:
    """Tests for cluster-based search."""

    def _create_and_build_index(
        self, n: int = 40
    ) -> tuple[BeliefIndex, list[BeliefVector]]:
        """Create and build index with sample data."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(n)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        index.build(beliefs)
        return index, beliefs

    def test_search_in_cluster(self) -> None:
        """Test searching within a cluster."""
        index, _ = self._create_and_build_index()
        cluster_id = index.get_all_clusters()[0]
        query = np.random.randn(10)

        results = index.search_in_cluster(query, cluster_id, k=3)

        assert isinstance(results, list)
        assert len(results) <= 3

    def test_search_in_cluster_not_found(self) -> None:
        """Test searching in non-existent cluster."""
        index, _ = self._create_and_build_index()
        query = np.random.randn(10)

        with pytest.raises(IndexError, match="Cluster 999 not found"):
            index.search_in_cluster(query, 999)

    def test_search_with_cluster_refinement(self) -> None:
        """Test search with cluster refinement."""
        index, _ = self._create_and_build_index(n=50)
        query = np.random.randn(10)

        results = index.search_with_cluster_refinement(query, k=5, n_clusters=2)

        assert isinstance(results, list)
        assert len(results) <= 5

    def test_search_with_cluster_refinement_unbuilt(self) -> None:
        """Test refinement when index not built falls back to regular search."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        # Add some beliefs to search index without building
        for i in range(10):
            belief = BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            index.search_index.add_belief(belief)

        query = np.random.randn(10)
        results = index.search_with_cluster_refinement(query, k=3)

        assert isinstance(results, list)


class TestBeliefIndexBeliefManagement:
    """Tests for adding and removing beliefs."""

    def _create_and_build_index(self) -> BeliefIndex:
        """Create and build index."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(30)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        index.build(beliefs)
        return index

    def test_add_belief(self) -> None:
        """Test adding a new belief."""
        index = self._create_and_build_index()
        initial_count = index.get_belief_count()

        new_belief = BeliefVector(vector=np.random.randn(10), belief_id="new_belief")
        cluster_id = index.add_belief(new_belief)

        assert index.get_belief_count() == initial_count + 1
        assert cluster_id in index.get_all_clusters()
        assert index.get_belief_cluster("new_belief") == cluster_id

    def test_add_belief_before_build(self) -> None:
        """Test that add before build raises error."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        belief = BeliefVector(vector=np.random.randn(10))

        with pytest.raises(IndexError, match="Index not built"):
            index.add_belief(belief)

    def test_add_belief_dimension_mismatch(self) -> None:
        """Test that dimension mismatch raises error."""
        index = self._create_and_build_index()
        wrong_belief = BeliefVector(vector=np.random.randn(20))

        with pytest.raises(ValidationError, match="Dimension mismatch"):
            index.add_belief(wrong_belief)

    def test_remove_belief(self) -> None:
        """Test removing a belief."""
        index = self._create_and_build_index()
        initial_count = index.get_belief_count()

        result = index.remove_belief("b_0")

        assert result is True
        assert index.get_belief_count() == initial_count - 1
        assert index.get_belief_cluster("b_0") is None

    def test_remove_belief_not_found(self) -> None:
        """Test removing non-existent belief."""
        index = self._create_and_build_index()
        result = index.remove_belief("nonexistent")
        assert result is False


class TestBeliefIndexHierarchical:
    """Tests for hierarchical index structure."""

    def test_build_with_hierarchy(self) -> None:
        """Test building index with hierarchy enabled."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(50)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(
            search_index=search_index,
            enable_hierarchy=True,
            hierarchy_depth=3,
        )
        index.build(beliefs)

        levels = index.get_hierarchy_levels()
        assert len(levels) > 0

    def test_get_level_info(self) -> None:
        """Test getting level information."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(40)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(
            search_index=search_index,
            enable_hierarchy=True,
            hierarchy_depth=2,
        )
        index.build(beliefs)

        level_info = index.get_level_info(0)
        assert level_info is not None
        assert level_info.level == 0

    def test_get_level_info_not_found(self) -> None:
        """Test getting info for non-existent level."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        level_info = index.get_level_info(99)
        assert level_info is None


class TestBeliefIndexSerialization:
    """Tests for index serialization."""

    def _create_and_build_index(self) -> BeliefIndex:
        """Create and build index."""
        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(30)
        ]
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        index.build(beliefs)
        return index

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        index = self._create_and_build_index()

        data = index.to_dict()

        assert data["is_built"] is True
        assert data["cluster_count"] == index.get_cluster_count()
        assert data["belief_count"] == index.get_belief_count()
        assert "clusters" in data
        assert "metrics" in data

    def test_save_and_load(self) -> None:
        """Test saving and loading index."""
        index = self._create_and_build_index()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            index.save(filepath)

            # Load the index
            loaded = BeliefIndex.load(filepath)

            assert loaded.get_cluster_count() == index.get_cluster_count()
            assert loaded.get_belief_count() == index.get_belief_count()
            assert loaded._is_built is True
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_save_creates_directory(self) -> None:
        """Test that save creates parent directories."""
        index = self._create_and_build_index()

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "index.json"
            index.save(str(filepath))
            assert filepath.exists()

    def test_load_not_found(self) -> None:
        """Test loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            BeliefIndex.load("/nonexistent/path.json")

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip serialization preserves data."""
        index = self._create_and_build_index()
        original_clusters = set(index.get_all_clusters())
        original_belief_count = index.get_belief_count()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            index.save(filepath)
            loaded = BeliefIndex.load(filepath)

            assert set(loaded.get_all_clusters()) == original_clusters
            assert loaded.get_belief_count() == original_belief_count
        finally:
            Path(filepath).unlink(missing_ok=True)


class TestBeliefIndexIntegration:
    """Integration tests for BeliefIndex."""

    def test_end_to_end_workflow(self) -> None:
        """Test complete workflow."""
        np.random.seed(42)

        # Create beliefs
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"belief_{i}")
            for i in range(50)
        ]

        # Build index with explicit engine for fixed cluster count
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        engine = BeliefClusteringEngine(n_clusters=3, auto_select_k=False)
        index = BeliefIndex(
            clustering_engine=engine,
            search_index=search_index,
            enable_hierarchy=True,
            hierarchy_depth=2,
        )
        metrics = index.build(beliefs)

        assert metrics.num_clusters == 3
        assert index.get_belief_count() == 50

        # Search
        query = np.random.randn(10)
        results = index.search_with_cluster_refinement(query, k=5)
        assert len(results) > 0

        # Add new belief
        new_belief = BeliefVector(vector=np.random.randn(10), belief_id="new_one")
        cluster_id = index.add_belief(new_belief)
        assert cluster_id is not None

        # Verify added
        assert index.get_belief_cluster("new_one") == cluster_id

        # Remove belief
        result = index.remove_belief("belief_0")
        assert result is True
        assert index.get_belief_cluster("belief_0") is None

        # Get statistics
        stats = index.get_cluster_statistics(cluster_id)
        assert "cluster_id" in stats

    def test_len_method(self) -> None:
        """Test __len__ method."""
        search_index = BeliefSearchIndex(backend=InMemoryBackend())
        index = BeliefIndex(search_index=search_index)
        assert len(index) == 0

        np.random.seed(42)
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(20)
        ]
        index.build(beliefs)

        assert len(index) == 20
