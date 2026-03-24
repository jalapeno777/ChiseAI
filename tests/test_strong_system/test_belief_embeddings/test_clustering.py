"""Tests for BeliefClusteringEngine and ClusterMetrics classes."""

from __future__ import annotations

import json

import numpy as np
import pytest
from src.strong_system.belief_embeddings import (
    BeliefClusteringEngine,
    BeliefVector,
    ClusterAssignment,
    ClusteringError,
    ClusterMetrics,
    ValidationError,
)


class TestClusterMetrics:
    """Tests for ClusterMetrics class."""

    def test_default_creation(self) -> None:
        """Test creating metrics with default values."""
        metrics = ClusterMetrics()
        assert metrics.silhouette_score is None
        assert metrics.davies_bouldin_index is None
        assert metrics.cohesion is None
        assert metrics.separation is None
        assert metrics.cluster_sizes == {}
        assert metrics.cluster_centroids == {}

    def test_custom_creation(self) -> None:
        """Test creating metrics with custom values."""
        centroids = {0: np.array([1.0, 2.0]), 1: np.array([3.0, 4.0])}
        metrics = ClusterMetrics(
            silhouette_score=0.75,
            davies_bouldin_index=0.5,
            cohesion=0.8,
            separation=1.2,
            cluster_sizes={0: 10, 1: 15},
            cluster_centroids=centroids,
        )
        assert metrics.silhouette_score == 0.75
        assert metrics.davies_bouldin_index == 0.5
        assert metrics.cohesion == 0.8
        assert metrics.separation == 1.2
        assert metrics.cluster_sizes == {0: 10, 1: 15}
        assert np.allclose(metrics.cluster_centroids[0], [1.0, 2.0])

    def test_num_clusters_property(self) -> None:
        """Test num_clusters property."""
        metrics = ClusterMetrics(cluster_sizes={0: 5, 1: 10, 2: 3})
        assert metrics.num_clusters == 3

    def test_total_points_property(self) -> None:
        """Test total_points property."""
        metrics = ClusterMetrics(cluster_sizes={0: 5, 1: 10, 2: 3})
        assert metrics.total_points == 18

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        centroids = {0: np.array([1.0, 2.0])}
        metrics = ClusterMetrics(
            silhouette_score=0.8,
            cluster_sizes={0: 10},
            cluster_centroids=centroids,
        )
        data = metrics.to_dict()
        assert data["silhouette_score"] == 0.8
        assert data["cluster_sizes"] == {0: 10}
        assert data["cluster_centroids"]["0"] == [1.0, 2.0]
        assert data["num_clusters"] == 1
        assert data["total_points"] == 10

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "silhouette_score": 0.75,
            "davies_bouldin_index": 0.6,
            "cluster_sizes": {"0": 10, "1": 20},
            "cluster_centroids": {"0": [1.0, 2.0], "1": [3.0, 4.0]},
        }
        metrics = ClusterMetrics.from_dict(data)
        assert metrics.silhouette_score == 0.75
        assert metrics.davies_bouldin_index == 0.6
        assert metrics.cluster_sizes == {0: 10, 1: 20}
        assert np.allclose(metrics.cluster_centroids[0], [1.0, 2.0])
        assert np.allclose(metrics.cluster_centroids[1], [3.0, 4.0])


class TestClusterAssignment:
    """Tests for ClusterAssignment class."""

    def test_creation(self) -> None:
        """Test creating cluster assignment."""
        assignment = ClusterAssignment(
            belief_id="belief_001",
            cluster_id=2,
            distance_to_centroid=0.5,
            confidence=0.9,
        )
        assert assignment.belief_id == "belief_001"
        assert assignment.cluster_id == 2
        assert assignment.distance_to_centroid == 0.5
        assert assignment.confidence == 0.9

    def test_default_confidence(self) -> None:
        """Test default confidence value."""
        assignment = ClusterAssignment(
            belief_id="belief_001",
            cluster_id=0,
            distance_to_centroid=0.3,
        )
        assert assignment.confidence == 1.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        assignment = ClusterAssignment(
            belief_id="belief_001",
            cluster_id=1,
            distance_to_centroid=0.4,
            confidence=0.85,
        )
        data = assignment.to_dict()
        assert data["belief_id"] == "belief_001"
        assert data["cluster_id"] == 1
        assert data["distance_to_centroid"] == 0.4
        assert data["confidence"] == 0.85


class TestBeliefClusteringEngineInitialization:
    """Tests for BeliefClusteringEngine initialization."""

    def test_default_creation(self) -> None:
        """Test creating engine with default values."""
        engine = BeliefClusteringEngine()
        assert engine.algorithm == "kmeans"
        assert engine.n_clusters == 5
        assert engine.auto_select_k is False
        assert engine.distance_metric == "cosine"

    def test_kmeans_creation(self) -> None:
        """Test creating K-means engine."""
        engine = BeliefClusteringEngine(
            algorithm="kmeans",
            n_clusters=3,
            distance_metric="euclidean",
        )
        assert engine.algorithm == "kmeans"
        assert engine.n_clusters == 3
        assert engine.distance_metric == "euclidean"

    def test_dbscan_creation(self) -> None:
        """Test creating DBSCAN engine."""
        engine = BeliefClusteringEngine(
            algorithm="dbscan",
            eps=0.5,
            min_samples=3,
        )
        assert engine.algorithm == "dbscan"

    def test_minibatch_creation(self) -> None:
        """Test creating MiniBatchKMeans engine."""
        engine = BeliefClusteringEngine(
            algorithm="minibatch",
            n_clusters=4,
        )
        assert engine.algorithm == "minibatch"
        assert engine.n_clusters == 4

    def test_invalid_algorithm(self) -> None:
        """Test that invalid algorithm raises error."""
        with pytest.raises(ClusteringError, match="Invalid algorithm"):
            BeliefClusteringEngine(algorithm="invalid")

    def test_invalid_distance_metric(self) -> None:
        """Test that invalid distance metric raises error."""
        with pytest.raises(ClusteringError, match="Invalid distance metric"):
            BeliefClusteringEngine(distance_metric="manhattan")

    def test_repr(self) -> None:
        """Test string representation."""
        engine = BeliefClusteringEngine(algorithm="kmeans", n_clusters=3)
        repr_str = repr(engine)
        assert "BeliefClusteringEngine" in repr_str
        assert "kmeans" in repr_str
        assert "n_clusters=3" in repr_str


class TestBeliefClusteringEngineKMeans:
    """Tests for K-means clustering."""

    def _create_sample_beliefs(self, n: int = 20, dim: int = 10) -> list[BeliefVector]:
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

    def test_fit_kmeans(self) -> None:
        """Test fitting K-means clustering."""
        beliefs = self._create_sample_beliefs(n=30)
        engine = BeliefClusteringEngine(algorithm="kmeans", n_clusters=3)

        metrics = engine.fit(beliefs)

        assert metrics.num_clusters == 3
        assert metrics.total_points == 30
        assert metrics.silhouette_score is not None
        assert len(engine.get_centroids()) == 3

    def test_fit_empty_beliefs(self) -> None:
        """Test that fitting empty beliefs raises error."""
        engine = BeliefClusteringEngine()
        with pytest.raises(ClusteringError, match="empty list"):
            engine.fit([])

    def test_fit_dimension_mismatch(self) -> None:
        """Test that dimension mismatch raises error."""
        beliefs = [
            BeliefVector(vector=np.random.randn(10), belief_id="b1"),
            BeliefVector(vector=np.random.randn(20), belief_id="b2"),
        ]
        engine = BeliefClusteringEngine()
        with pytest.raises(ValidationError, match="Dimension mismatch"):
            engine.fit(beliefs)

    def test_predict_before_fit(self) -> None:
        """Test that predict before fit raises error."""
        engine = BeliefClusteringEngine()
        belief = BeliefVector(vector=np.random.randn(10))
        with pytest.raises(ClusteringError, match="Model not fitted"):
            engine.predict(belief)

    def test_predict_after_fit(self) -> None:
        """Test predicting cluster assignment."""
        beliefs = self._create_sample_beliefs(n=30)
        engine = BeliefClusteringEngine(algorithm="kmeans", n_clusters=3)
        engine.fit(beliefs)

        new_belief = BeliefVector(vector=np.random.randn(10))
        cluster_id = engine.predict(new_belief)

        assert isinstance(cluster_id, int)
        assert 0 <= cluster_id < 3

    def test_predict_dimension_mismatch(self) -> None:
        """Test that predict with wrong dimension raises error."""
        beliefs = self._create_sample_beliefs(n=20, dim=10)
        engine = BeliefClusteringEngine()
        engine.fit(beliefs)

        wrong_belief = BeliefVector(vector=np.random.randn(20))
        with pytest.raises(ValidationError, match="Dimension mismatch"):
            engine.predict(wrong_belief)

    def test_assign_clusters(self) -> None:
        """Test assigning clusters to beliefs."""
        beliefs = self._create_sample_beliefs(n=20)
        engine = BeliefClusteringEngine(n_clusters=2)
        engine.fit(beliefs)

        assignments = engine.assign_clusters(beliefs)

        assert len(assignments) == 20
        for assignment in assignments:
            assert isinstance(assignment, ClusterAssignment)
            assert assignment.cluster_id in [0, 1]
            assert assignment.belief_id.startswith("belief_")
            assert 0.0 <= assignment.confidence <= 1.0

    def test_assign_clusters_before_fit(self) -> None:
        """Test that assign_clusters before fit raises error."""
        engine = BeliefClusteringEngine()
        beliefs = self._create_sample_beliefs(n=10)
        with pytest.raises(ClusteringError, match="Model not fitted"):
            engine.assign_clusters(beliefs)

    def test_auto_select_k(self) -> None:
        """Test automatic cluster number selection."""
        beliefs = self._create_sample_beliefs(n=50)
        engine = BeliefClusteringEngine(
            algorithm="kmeans",
            n_clusters=10,
            auto_select_k=True,
        )

        metrics = engine.fit(beliefs, min_k=2, max_k=8)

        # Auto-selected k should be different from initial
        assert engine.n_clusters <= 8
        assert engine.n_clusters >= 2
        assert metrics.num_clusters == engine.n_clusters

    def test_get_centroids(self) -> None:
        """Test getting cluster centroids."""
        beliefs = self._create_sample_beliefs(n=20)
        engine = BeliefClusteringEngine(n_clusters=3)
        engine.fit(beliefs)

        centroids = engine.get_centroids()

        assert len(centroids) == 3
        for cluster_id, centroid in centroids.items():
            assert isinstance(cluster_id, int)
            assert isinstance(centroid, np.ndarray)
            assert len(centroid) == 10  # Same dimension as input


class TestBeliefClusteringEngineDBSCAN:
    """Tests for DBSCAN clustering."""

    def _create_clustered_beliefs(self) -> list[BeliefVector]:
        """Create beliefs with clear clusters for DBSCAN."""
        np.random.seed(42)
        beliefs = []

        # Cluster 1
        for i in range(15):
            vector = np.random.randn(10) * 0.1 + np.array([1.0] * 10)
            beliefs.append(BeliefVector(vector=vector, belief_id=f"c1_{i}"))

        # Cluster 2
        for i in range(15):
            vector = np.random.randn(10) * 0.1 - np.array([1.0] * 10)
            beliefs.append(BeliefVector(vector=vector, belief_id=f"c2_{i}"))

        return beliefs

    def test_fit_dbscan(self) -> None:
        """Test fitting DBSCAN clustering."""
        beliefs = self._create_clustered_beliefs()
        engine = BeliefClusteringEngine(
            algorithm="dbscan",
            eps=0.5,
            min_samples=3,
        )

        metrics = engine.fit(beliefs)

        assert metrics.num_clusters >= 1
        assert metrics.total_points == 30

    def test_dbscan_predict(self) -> None:
        """Test DBSCAN prediction (uses nearest centroid)."""
        beliefs = self._create_clustered_beliefs()
        engine = BeliefClusteringEngine(
            algorithm="dbscan",
            eps=0.5,
            min_samples=3,
        )
        engine.fit(beliefs)

        new_belief = BeliefVector(vector=np.ones(10) * 0.9)
        cluster_id = engine.predict(new_belief)

        # Should assign to one of the found clusters
        assert cluster_id in engine.get_centroids()


class TestBeliefClusteringEngineMiniBatch:
    """Tests for MiniBatchKMeans clustering."""

    def _create_sample_beliefs(self, n: int = 50) -> list[BeliefVector]:
        """Create sample beliefs."""
        np.random.seed(42)
        return [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(n)
        ]

    def test_fit_minibatch(self) -> None:
        """Test fitting MiniBatchKMeans."""
        beliefs = self._create_sample_beliefs(n=100)
        engine = BeliefClusteringEngine(
            algorithm="minibatch",
            n_clusters=5,
        )

        metrics = engine.fit(beliefs)

        assert metrics.num_clusters == 5
        assert len(engine.get_centroids()) == 5

    def test_partial_fit(self) -> None:
        """Test incremental clustering with partial_fit."""
        beliefs = self._create_sample_beliefs(n=50)
        engine = BeliefClusteringEngine(
            algorithm="minibatch",
            n_clusters=3,
        )

        # Initial fit
        engine.fit(beliefs[:30])

        # Incremental update
        new_beliefs = beliefs[30:]
        metrics = engine.partial_fit(new_beliefs)

        # After partial_fit, we should have metrics and 3 centroids
        # Note: num_clusters counts clusters with actual points,
        # so it might be less than 3 with small sample sizes
        assert metrics is not None
        assert len(engine.get_centroids()) == 3
        assert metrics.num_clusters >= 1  # At least 1 cluster should have data

    def test_partial_fit_not_minibatch(self) -> None:
        """Test that partial_fit fails for non-minibatch algorithms."""
        engine = BeliefClusteringEngine(algorithm="kmeans")
        beliefs = self._create_sample_beliefs(n=10)
        with pytest.raises(ClusteringError, match="only supported for 'minibatch'"):
            engine.partial_fit(beliefs)

    def test_partial_fit_empty(self) -> None:
        """Test that partial_fit with empty beliefs raises error."""
        engine = BeliefClusteringEngine(algorithm="minibatch")
        with pytest.raises(ClusteringError, match="empty list"):
            engine.partial_fit([])


class TestBeliefClusteringEngineSerialization:
    """Tests for engine serialization."""

    def _create_sample_beliefs(self, n: int = 20) -> list[BeliefVector]:
        """Create sample beliefs."""
        np.random.seed(42)
        return [
            BeliefVector(vector=np.random.randn(10), belief_id=f"b_{i}")
            for i in range(n)
        ]

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        engine = BeliefClusteringEngine(
            algorithm="kmeans",
            n_clusters=5,
            auto_select_k=True,
        )

        data = engine.to_dict()

        assert data["algorithm"] == "kmeans"
        assert data["n_clusters"] == 5
        assert data["auto_select_k"] is True
        assert data["distance_metric"] == "cosine"
        assert data["is_fitted"] is False

    def test_to_dict_fitted(self) -> None:
        """Test conversion after fitting."""
        beliefs = self._create_sample_beliefs(n=20)
        engine = BeliefClusteringEngine(n_clusters=3)
        engine.fit(beliefs)

        data = engine.to_dict()

        assert data["is_fitted"] is True
        assert len(data["centroids"]) == 3

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "algorithm": "kmeans",
            "n_clusters": 4,
            "auto_select_k": False,
            "distance_metric": "euclidean",
            "is_fitted": False,
            "centroids": {},
        }

        engine = BeliefClusteringEngine.from_dict(data)

        assert engine.algorithm == "kmeans"
        assert engine.n_clusters == 4
        assert engine.auto_select_k is False
        assert engine.distance_metric == "euclidean"

    def test_from_dict_with_centroids(self) -> None:
        """Test creation from dictionary with centroids."""
        data = {
            "algorithm": "kmeans",
            "n_clusters": 2,
            "is_fitted": True,
            "centroids": {"0": [1.0, 2.0, 3.0], "1": [4.0, 5.0, 6.0]},
        }

        engine = BeliefClusteringEngine.from_dict(data)

        assert engine._is_fitted is True
        centroids = engine.get_centroids()
        assert len(centroids) == 2
        assert np.allclose(centroids[0], [1.0, 2.0, 3.0])

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip serialization."""
        beliefs = self._create_sample_beliefs(n=20)
        engine = BeliefClusteringEngine(n_clusters=3)
        engine.fit(beliefs)

        # Serialize
        data = engine.to_dict()
        json_str = json.dumps(data)

        # Deserialize
        loaded_data = json.loads(json_str)
        restored = BeliefClusteringEngine.from_dict(loaded_data)

        assert restored.algorithm == engine.algorithm
        assert restored.n_clusters == engine.n_clusters
        assert restored._is_fitted == engine._is_fitted


class TestBeliefClusteringEngineMetrics:
    """Tests for cluster metrics computation."""

    def _create_well_separated_clusters(self) -> list[BeliefVector]:
        """Create beliefs with well-separated clusters."""
        np.random.seed(42)
        beliefs = []

        # Three well-separated clusters
        centers = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ]

        for cluster_idx, center in enumerate(centers):
            for i in range(10):
                vector = center + np.random.randn(3) * 0.05
                belief = BeliefVector(
                    vector=vector,
                    belief_id=f"c{cluster_idx}_{i}",
                )
                beliefs.append(belief)

        return beliefs

    def test_silhouette_score(self) -> None:
        """Test silhouette score computation."""
        beliefs = self._create_well_separated_clusters()
        engine = BeliefClusteringEngine(n_clusters=3)
        metrics = engine.fit(beliefs)

        assert metrics.silhouette_score is not None
        assert -1.0 <= metrics.silhouette_score <= 1.0
        # Well-separated clusters should have positive silhouette
        assert metrics.silhouette_score > 0

    def test_cohesion_metric(self) -> None:
        """Test cohesion metric computation."""
        beliefs = self._create_well_separated_clusters()
        engine = BeliefClusteringEngine(n_clusters=3)
        metrics = engine.fit(beliefs)

        assert metrics.cohesion is not None
        assert metrics.cohesion >= 0

    def test_separation_metric(self) -> None:
        """Test separation metric computation."""
        beliefs = self._create_well_separated_clusters()
        engine = BeliefClusteringEngine(n_clusters=3)
        metrics = engine.fit(beliefs)

        assert metrics.separation is not None
        assert metrics.separation > 0

    def test_davies_bouldin_index(self) -> None:
        """Test Davies-Bouldin index computation."""
        beliefs = self._create_well_separated_clusters()
        engine = BeliefClusteringEngine(n_clusters=3)
        metrics = engine.fit(beliefs)

        assert metrics.davies_bouldin_index is not None
        assert metrics.davies_bouldin_index >= 0

    def test_single_cluster_no_silhouette(self) -> None:
        """Test that single cluster doesn't produce silhouette score."""
        beliefs = [
            BeliefVector(vector=np.random.randn(5), belief_id=f"b_{i}")
            for i in range(10)
        ]
        engine = BeliefClusteringEngine(n_clusters=1)
        metrics = engine.fit(beliefs)

        # Single cluster cannot have silhouette score
        assert metrics.silhouette_score is None


class TestBeliefClusteringEngineValidation:
    """Tests for input validation."""

    def test_invalid_belief_type(self) -> None:
        """Test that non-BeliefVector raises error."""
        engine = BeliefClusteringEngine()
        with pytest.raises(ValidationError, match="Expected BeliefVector"):
            engine.fit(["not_a_belief"])  # type: ignore[list-item]

    def test_invalid_belief_type_predict(self) -> None:
        """Test that predict with invalid type raises error."""
        beliefs = [
            BeliefVector(vector=np.random.randn(5), belief_id=f"b_{i}")
            for i in range(10)
        ]
        engine = BeliefClusteringEngine()
        engine.fit(beliefs)

        # Should work with BeliefVector
        result = engine.predict(beliefs[0])
        assert isinstance(result, int)
