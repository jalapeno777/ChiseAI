"""Belief Clustering Module for Strong AI System.

Provides the BeliefClusteringEngine class for grouping belief vectors into clusters
using various clustering algorithms, with support for automatic cluster number
selection and incremental clustering for streaming beliefs.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN, KMeans, MiniBatchKMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.metrics.pairwise import cosine_distances, euclidean_distances

from .vector import BeliefVector, ValidationError


class ClusteringError(ValueError):
    """Raised when clustering operation fails."""


@dataclass
class ClusterMetrics:
    """Metrics for evaluating cluster quality.

    Attributes:
        silhouette_score: Silhouette coefficient (-1 to 1, higher is better)
        davies_bouldin_index: Davies-Bouldin index (lower is better)
        cohesion: Average intra-cluster similarity (higher is better)
        separation: Average inter-cluster distance (higher is better)
        cluster_sizes: Dictionary mapping cluster labels to sizes
        cluster_centroids: Dictionary mapping cluster labels to centroids
    """

    silhouette_score: float | None = None
    davies_bouldin_index: float | None = None
    cohesion: float | None = None
    separation: float | None = None
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    cluster_centroids: dict[int, np.ndarray] = field(default_factory=dict)

    @property
    def num_clusters(self) -> int:
        """Return the number of clusters."""
        return len(self.cluster_sizes)

    @property
    def total_points(self) -> int:
        """Return the total number of points in all clusters."""
        return sum(self.cluster_sizes.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        # Convert cluster_centroids keys to strings for JSON serialization
        centroids_dict = {str(k): v.tolist() for k, v in self.cluster_centroids.items()}
        return {
            "silhouette_score": self.silhouette_score,
            "davies_bouldin_index": self.davies_bouldin_index,
            "cohesion": self.cohesion,
            "separation": self.separation,
            "cluster_sizes": self.cluster_sizes,
            "cluster_centroids": centroids_dict,
            "num_clusters": self.num_clusters,
            "total_points": self.total_points,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterMetrics:
        """Create metrics from dictionary."""
        centroids = {}
        for k, v in data.get("cluster_centroids", {}).items():
            centroids[int(k)] = np.array(v, dtype=np.float64)

        return cls(
            silhouette_score=data.get("silhouette_score"),
            davies_bouldin_index=data.get("davies_bouldin_index"),
            cohesion=data.get("cohesion"),
            separation=data.get("separation"),
            cluster_sizes={int(k): v for k, v in data.get("cluster_sizes", {}).items()},
            cluster_centroids=centroids,
        )


@dataclass
class ClusterAssignment:
    """Represents a belief-to-cluster assignment.

    Attributes:
        belief_id: Unique identifier of the belief
        cluster_id: Assigned cluster label
        distance_to_centroid: Distance from belief to cluster centroid
        confidence: Assignment confidence score
    """

    belief_id: str
    cluster_id: int
    distance_to_centroid: float
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert assignment to dictionary."""
        return {
            "belief_id": self.belief_id,
            "cluster_id": self.cluster_id,
            "distance_to_centroid": self.distance_to_centroid,
            "confidence": self.confidence,
        }


class BeliefClusteringEngine:
    """Engine for clustering belief vectors.

    Supports multiple clustering algorithms including K-means and DBSCAN,
    with automatic cluster number selection and incremental clustering
    for streaming beliefs.

    Attributes:
        algorithm: Clustering algorithm ("kmeans", "dbscan", or "minibatch")
        n_clusters: Number of clusters (for K-means variants)
        auto_select_k: Whether to automatically select optimal k
        distance_metric: Distance metric ("cosine" or "euclidean")
    """

    def __init__(
        self,
        algorithm: str = "kmeans",
        n_clusters: int = 5,
        auto_select_k: bool = False,
        distance_metric: str = "cosine",
        **kwargs: Any,
    ):
        """Initialize the clustering engine.

        Args:
            algorithm: Clustering algorithm ("kmeans", "dbscan", "minibatch")
            n_clusters: Number of clusters for K-means variants
            auto_select_k: Whether to automatically select optimal k
            distance_metric: Distance metric ("cosine" or "euclidean")
            **kwargs: Additional parameters for clustering algorithms

        Raises:
            ClusteringError: If algorithm or metric is invalid
        """
        valid_algorithms = ["kmeans", "dbscan", "minibatch"]
        if algorithm not in valid_algorithms:
            raise ClusteringError(
                f"Invalid algorithm '{algorithm}'. Must be one of: {valid_algorithms}"
            )

        valid_metrics = ["cosine", "euclidean"]
        if distance_metric not in valid_metrics:
            raise ClusteringError(
                f"Invalid distance metric '{distance_metric}'. "
                f"Must be one of: {valid_metrics}"
            )

        self.algorithm = algorithm
        self.n_clusters = n_clusters
        self.auto_select_k = auto_select_k
        self.distance_metric = distance_metric
        self._clustering_params = kwargs

        self._model: KMeans | DBSCAN | MiniBatchKMeans | None = None
        self._centroids: dict[int, np.ndarray] = {}
        self._is_fitted = False
        self._vector_dim: int | None = None
        self._belief_ids: list[str] = []

    def _get_distance_matrix(self, vectors: np.ndarray) -> np.ndarray:
        """Compute distance matrix based on configured metric.

        Args:
            vectors: Array of vectors

        Returns:
            Distance matrix
        """
        if self.distance_metric == "cosine":
            return cosine_distances(vectors)
        return euclidean_distances(vectors)

    def _compute_elbow_scores(
        self, vectors: np.ndarray, k_range: range
    ) -> dict[int, float]:
        """Compute inertia scores for elbow method.

        Args:
            vectors: Array of belief vectors
            k_range: Range of k values to test

        Returns:
            Dictionary mapping k to inertia score
        """
        scores = {}
        for k in k_range:
            if k < 2:
                continue
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(vectors)
            scores[k] = kmeans.inertia_
        return scores

    def _find_elbow_point(self, scores: dict[int, float]) -> int:
        """Find the elbow point in the inertia curve.

        Args:
            scores: Dictionary mapping k to inertia score

        Returns:
            Optimal k value
        """
        if not scores:
            return 2

        sorted_ks = sorted(scores.keys())
        inertias = [scores[k] for k in sorted_ks]

        if len(inertias) < 3:
            return sorted_ks[0] if sorted_ks else 2

        # Compute second derivative to find elbow
        # Normalize to [0, 1] for fair comparison
        max_inertia = max(inertias)
        min_inertia = min(inertias)
        if max_inertia == min_inertia:
            return sorted_ks[len(sorted_ks) // 2]

        normalized = [(i - min_inertia) / (max_inertia - min_inertia) for i in inertias]

        # Find point with maximum second derivative (elbow)
        max_curvature = -1
        elbow_k = sorted_ks[0]

        for i in range(1, len(sorted_ks) - 1):
            # Second derivative approximation
            second_deriv = normalized[i - 1] - 2 * normalized[i] + normalized[i + 1]
            if second_deriv > max_curvature:
                max_curvature = second_deriv
                elbow_k = sorted_ks[i]

        return elbow_k

    def _select_optimal_k(self, vectors: np.ndarray, max_k: int = 10) -> int:
        """Select optimal number of clusters using elbow method.

        Args:
            vectors: Array of belief vectors
            max_k: Maximum number of clusters to consider

        Returns:
            Optimal k value
        """
        n_samples = len(vectors)
        if n_samples < 3:
            return min(2, n_samples)

        # Limit max_k based on sample size
        max_k = min(max_k, n_samples - 1)
        k_range = range(2, max_k + 1)

        scores = self._compute_elbow_scores(vectors, k_range)
        return self._find_elbow_point(scores)

    def fit(
        self,
        beliefs: list[BeliefVector],
        min_k: int = 2,
        max_k: int = 10,
    ) -> ClusterMetrics:
        """Fit clustering model to belief vectors.

        Args:
            beliefs: List of BeliefVector objects to cluster
            min_k: Minimum number of clusters for auto-selection
            max_k: Maximum number of clusters for auto-selection

        Returns:
            ClusterMetrics with cluster quality metrics

        Raises:
            ClusteringError: If clustering fails
            ValidationError: If beliefs are invalid
        """
        if not beliefs:
            raise ClusteringError("Cannot cluster empty list of beliefs")

        # Validate and extract vectors
        vectors = []
        self._belief_ids = []
        expected_dim = None

        for belief in beliefs:
            if not isinstance(belief, BeliefVector):
                raise ValidationError(f"Expected BeliefVector, got {type(belief)}")

            if expected_dim is None:
                expected_dim = belief.dimension
            elif belief.dimension != expected_dim:
                raise ValidationError(
                    f"Dimension mismatch: {belief.dimension} vs {expected_dim}"
                )

            vectors.append(belief.vector)
            self._belief_ids.append(belief.belief_id)

        self._vector_dim = expected_dim
        vectors_array = np.array(vectors)

        # Auto-select k if enabled
        if self.auto_select_k and self.algorithm in ("kmeans", "minibatch"):
            self.n_clusters = self._select_optimal_k(vectors_array, max_k)
            # Ensure at least min_k
            self.n_clusters = max(self.n_clusters, min_k)
            # Cap at number of samples
            self.n_clusters = min(self.n_clusters, len(beliefs))

        # Fit clustering model
        try:
            if self.algorithm == "kmeans":
                self._model = KMeans(
                    n_clusters=self.n_clusters,
                    random_state=42,
                    n_init=10,
                    **self._clustering_params,
                )
                labels = self._model.fit_predict(vectors_array)

            elif self.algorithm == "minibatch":
                self._model = MiniBatchKMeans(
                    n_clusters=self.n_clusters,
                    random_state=42,
                    n_init=3,
                    **self._clustering_params,
                )
                labels = self._model.fit_predict(vectors_array)

            elif self.algorithm == "dbscan":
                eps = self._clustering_params.get("eps", 0.5)
                min_samples = self._clustering_params.get("min_samples", 5)
                self._model = DBSCAN(
                    eps=eps,
                    min_samples=min_samples,
                    metric=self.distance_metric,
                )
                labels = self._model.fit_predict(vectors_array)

            else:
                raise ClusteringError(f"Unknown algorithm: {self.algorithm}")

        except Exception as e:
            raise ClusteringError(f"Clustering failed: {e}") from e

        self._is_fitted = True

        # Compute centroids
        self._centroids = self._compute_centroids(vectors_array, labels)

        # Compute metrics
        return self._compute_metrics(vectors_array, labels)

    def _compute_centroids(
        self, vectors: np.ndarray, labels: np.ndarray
    ) -> dict[int, np.ndarray]:
        """Compute cluster centroids.

        Args:
            vectors: Array of vectors
            labels: Cluster labels

        Returns:
            Dictionary mapping cluster labels to centroids
        """
        centroids = {}
        unique_labels = set(labels)

        # Remove noise cluster label (-1) for DBSCAN
        unique_labels.discard(-1)

        for label in unique_labels:
            mask = labels == label
            cluster_vectors = vectors[mask]
            centroid = np.mean(cluster_vectors, axis=0)
            centroids[int(label)] = centroid

        return centroids

    def _compute_metrics(
        self, vectors: np.ndarray, labels: np.ndarray
    ) -> ClusterMetrics:
        """Compute cluster quality metrics.

        Args:
            vectors: Array of vectors
            labels: Cluster labels

        Returns:
            ClusterMetrics with quality metrics
        """
        metrics = ClusterMetrics()

        # Filter out noise points for DBSCAN
        valid_mask = labels != -1
        if valid_mask.sum() == 0:
            # All points are noise
            metrics.cluster_sizes = {-1: len(labels)}
            return metrics

        valid_vectors = vectors[valid_mask]
        valid_labels = labels[valid_mask]

        # Cluster sizes
        unique_labels = set(valid_labels)
        for label in unique_labels:
            metrics.cluster_sizes[int(label)] = int((valid_labels == label).sum())

        # Add noise cluster count if present
        noise_count = (labels == -1).sum()
        if noise_count > 0:
            metrics.cluster_sizes[-1] = int(noise_count)

        metrics.cluster_centroids = self._centroids

        # Need at least 2 clusters for these metrics
        if len(unique_labels) < 2:
            return metrics

        # Need more samples than clusters for silhouette score
        if len(valid_vectors) > len(unique_labels):
            try:
                metrics.silhouette_score = silhouette_score(
                    valid_vectors, valid_labels, metric=self.distance_metric
                )
            except Exception:
                pass

        # Davies-Bouldin index
        try:
            metrics.davies_bouldin_index = davies_bouldin_score(
                valid_vectors, valid_labels
            )
        except Exception:
            pass

        # Cohesion (average intra-cluster distance to centroid)
        total_cohesion = 0.0
        total_points = 0
        for label in unique_labels:
            mask = valid_labels == label
            cluster_vectors = valid_vectors[mask]
            centroid = self._centroids.get(int(label))
            if centroid is not None:
                distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
                total_cohesion += distances.sum()
                total_points += len(distances)

        if total_points > 0:
            metrics.cohesion = total_cohesion / total_points

        # Separation (average inter-cluster centroid distance)
        if len(unique_labels) > 1:
            centroid_list = list(self._centroids.values())
            if len(centroid_list) > 1:
                centroid_array = np.array(centroid_list)
                if self.distance_metric == "cosine":
                    distances = cosine_distances(centroid_array)
                else:
                    distances = euclidean_distances(centroid_array)
                # Average of upper triangle (unique pairs)
                n = len(centroid_list)
                metrics.separation = distances.sum() / (n * (n - 1))

        return metrics

    def predict(self, belief: BeliefVector) -> int:
        """Predict cluster assignment for a single belief.

        Args:
            belief: BeliefVector to assign

        Returns:
            Cluster label

        Raises:
            ClusteringError: If model not fitted
            ValidationError: If belief dimension doesn't match
        """
        if not self._is_fitted:
            raise ClusteringError("Model not fitted. Call fit() first.")

        if self._vector_dim is not None:
            if belief.dimension != self._vector_dim:
                raise ValidationError(
                    f"Dimension mismatch: {belief.dimension} vs {self._vector_dim}"
                )

        if self.algorithm == "dbscan":
            # DBSCAN doesn't support predict - use nearest centroid
            return self._find_nearest_centroid(belief.vector)

        if self._model is None:
            raise ClusteringError("Model not initialized")

        label = self._model.predict(belief.vector.reshape(1, -1))[0]
        return int(label)

    def _find_nearest_centroid(self, vector: np.ndarray) -> int:
        """Find the nearest centroid for a vector.

        Args:
            vector: Vector to assign

        Returns:
            Nearest cluster label
        """
        if not self._centroids:
            raise ClusteringError("No centroids available")

        min_distance = float("inf")
        nearest_label = -1

        for label, centroid in self._centroids.items():
            if self.distance_metric == "cosine":
                # Cosine distance = 1 - cosine similarity
                distance = cosine_distances([vector], [centroid])[0, 0]
            else:
                distance = np.linalg.norm(vector - centroid)

            if distance < min_distance:
                min_distance = distance
                nearest_label = label

        return nearest_label

    def assign_clusters(self, beliefs: list[BeliefVector]) -> list[ClusterAssignment]:
        """Assign clusters to beliefs and return detailed assignments.

        Args:
            beliefs: List of BeliefVector objects

        Returns:
            List of ClusterAssignment objects

        Raises:
            ClusteringError: If model not fitted
        """
        if not self._is_fitted:
            raise ClusteringError("Model not fitted. Call fit() first.")

        assignments = []
        for belief in beliefs:
            cluster_id = self.predict(belief)
            centroid = self._centroids.get(cluster_id)

            if centroid is not None:
                if self.distance_metric == "cosine":
                    distance = float(
                        cosine_distances([belief.vector], [centroid])[0, 0]
                    )
                else:
                    distance = float(np.linalg.norm(belief.vector - centroid))
            else:
                distance = float("inf")

            # Confidence based on distance (closer = higher confidence)
            # Normalize: assume max distance of 2 for cosine, reasonable for euclidean
            max_dist = 2.0 if self.distance_metric == "cosine" else 10.0
            confidence = max(0.0, 1.0 - (distance / max_dist))

            assignment = ClusterAssignment(
                belief_id=belief.belief_id,
                cluster_id=cluster_id,
                distance_to_centroid=distance,
                confidence=confidence,
            )
            assignments.append(assignment)

        return assignments

    def partial_fit(self, beliefs: list[BeliefVector]) -> ClusterMetrics:
        """Incrementally fit on new beliefs (for streaming data).

        Only supported for MiniBatchKMeans algorithm.

        Args:
            beliefs: List of new BeliefVector objects

        Returns:
            ClusterMetrics with updated cluster quality

        Raises:
            ClusteringError: If not using MiniBatchKMeans
        """
        if self.algorithm != "minibatch":
            raise ClusteringError(
                "Incremental clustering only supported for 'minibatch' algorithm"
            )

        if not beliefs:
            raise ClusteringError("Cannot fit on empty list of beliefs")

        # Validate and extract vectors
        vectors = []
        for belief in beliefs:
            if not isinstance(belief, BeliefVector):
                raise ValidationError(f"Expected BeliefVector, got {type(belief)}")
            vectors.append(belief.vector)
            if belief.belief_id not in self._belief_ids:
                self._belief_ids.append(belief.belief_id)

        vectors_array = np.array(vectors)

        # First fit if not yet fitted
        if not self._is_fitted:
            return self.fit(beliefs)

        # Partial fit on new data
        if self._model is None:
            raise ClusteringError("Model not initialized")

        self._model.partial_fit(vectors_array)
        self._is_fitted = True

        # Recompute centroids from the model
        for i, centroid in enumerate(self._model.cluster_centers_):
            self._centroids[i] = centroid

        # Predict all labels to compute metrics using new beliefs
        # In a full implementation, we'd track all beliefs for accurate metrics
        labels = self._model.predict(vectors_array)
        return self._compute_metrics(vectors_array, labels)

    def _get_all_belief_vectors(self) -> list[BeliefVector]:
        """Get all belief vectors (for incremental updates).

        Returns:
            List of stored belief vectors
        """
        # In a real implementation, this would retrieve from storage
        # For now, return empty list
        return []

    def get_cluster_beliefs(self, cluster_id: int) -> list[str]:
        """Get belief IDs belonging to a cluster.

        Args:
            cluster_id: Cluster label

        Returns:
            List of belief IDs in the cluster
        """
        if not self._is_fitted or not self._model:
            return []

        # This would need the original vectors to return accurate results
        # For now, return empty list as placeholder
        return []

    def get_centroids(self) -> dict[int, np.ndarray]:
        """Get cluster centroids.

        Returns:
            Dictionary mapping cluster labels to centroids
        """
        return self._centroids.copy()

    def to_dict(self) -> dict[str, Any]:
        """Convert engine state to dictionary."""
        # Convert centroids keys to strings for JSON serialization
        centroids_dict = {str(k): v.tolist() for k, v in self._centroids.items()}
        return {
            "algorithm": self.algorithm,
            "n_clusters": self.n_clusters,
            "auto_select_k": self.auto_select_k,
            "distance_metric": self.distance_metric,
            "is_fitted": self._is_fitted,
            "centroids": centroids_dict,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeliefClusteringEngine:
        """Create engine from dictionary (without fitted state)."""
        engine = cls(
            algorithm=data.get("algorithm", "kmeans"),
            n_clusters=data.get("n_clusters", 5),
            auto_select_k=data.get("auto_select_k", False),
            distance_metric=data.get("distance_metric", "cosine"),
        )

        # Restore centroids if available
        centroids_data = data.get("centroids", {})
        for k, v in centroids_data.items():
            engine._centroids[int(k)] = np.array(v, dtype=np.float64)

        engine._is_fitted = data.get("is_fitted", False)
        return engine

    def __repr__(self) -> str:
        return (
            f"BeliefClusteringEngine("
            f"algorithm={self.algorithm!r}, "
            f"n_clusters={self.n_clusters}, "
            f"fitted={self._is_fitted})"
        )
