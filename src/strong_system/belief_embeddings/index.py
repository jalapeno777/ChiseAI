"""Belief Index Module for Strong AI System.

Provides the BeliefIndex class for efficient cluster-based retrieval
with hierarchical index structure and fast cluster lookup by belief ID.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .clustering import BeliefClusteringEngine, ClusterAssignment, ClusterMetrics
from .search import BeliefSearchIndex, SearchResult
from .vector import BeliefVector, ValidationError


class IndexError(ValueError):
    """Raised when index operation fails."""


@dataclass
class ClusterInfo:
    """Information about a cluster.

    Attributes:
        cluster_id: Unique cluster identifier
        size: Number of beliefs in the cluster
        centroid: Cluster centroid vector
        belief_ids: List of belief IDs in the cluster
        parent_cluster: Parent cluster ID for hierarchical structure
        metadata: Additional cluster metadata
    """

    cluster_id: int
    size: int = 0
    centroid: np.ndarray | None = None
    belief_ids: list[str] = field(default_factory=list)
    parent_cluster: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert cluster info to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "size": self.size,
            "centroid": self.centroid.tolist() if self.centroid is not None else None,
            "belief_ids": self.belief_ids,
            "parent_cluster": self.parent_cluster,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterInfo:
        """Create cluster info from dictionary."""
        centroid_data = data.get("centroid")
        centroid = (
            np.array(centroid_data, dtype=np.float64)
            if centroid_data is not None
            else None
        )

        return cls(
            cluster_id=data.get("cluster_id", -1),
            size=data.get("size", 0),
            centroid=centroid,
            belief_ids=list(data.get("belief_ids", [])),
            parent_cluster=data.get("parent_cluster"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class HierarchicalLevel:
    """Represents a level in the hierarchical index.

    Attributes:
        level: Level number (0 = leaf, higher = more abstract)
        engine: Clustering engine for this level
        clusters: Dictionary of cluster info
    """

    level: int
    engine: BeliefClusteringEngine
    clusters: dict[int, ClusterInfo] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert level to dictionary."""
        return {
            "level": self.level,
            "engine": self.engine.to_dict(),
            "clusters": {k: v.to_dict() for k, v in self.clusters.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HierarchicalLevel:
        """Create level from dictionary."""
        engine = BeliefClusteringEngine.from_dict(data.get("engine", {}))
        clusters = {
            int(k): ClusterInfo.from_dict(v)
            for k, v in data.get("clusters", {}).items()
        }

        return cls(
            level=data.get("level", 0),
            engine=engine,
            clusters=clusters,
        )


class BeliefIndex:
    """Hierarchical index for cluster-based belief retrieval.

    Provides efficient cluster-based retrieval with support for:
    - Hierarchical clustering structure
    - Fast cluster lookup by belief ID
    - Cluster-based search refinement
    - Cluster statistics and analytics

    Attributes:
        clustering_engine: Primary clustering engine
        search_index: BeliefSearchIndex for similarity search
        enable_hierarchy: Whether to build hierarchical structure
    """

    def __init__(
        self,
        clustering_engine: BeliefClusteringEngine | None = None,
        search_index: BeliefSearchIndex | None = None,
        enable_hierarchy: bool = False,
        hierarchy_depth: int = 2,
    ):
        """Initialize the belief index.

        Args:
            clustering_engine: Clustering engine (creates default if None)
            search_index: Search index for similarity search (creates default if None)
            enable_hierarchy: Whether to enable hierarchical clustering
            hierarchy_depth: Maximum depth of hierarchy
        """
        self.clustering_engine = (
            clustering_engine
            if clustering_engine is not None
            else BeliefClusteringEngine()
        )
        self.search_index = (
            search_index
            if search_index is not None
            else BeliefSearchIndex.create_with_fallback()
        )
        self.enable_hierarchy = enable_hierarchy
        self.hierarchy_depth = hierarchy_depth

        self._clusters: dict[int, ClusterInfo] = {}
        self._belief_to_cluster: dict[str, int] = {}
        self._levels: list[HierarchicalLevel] = []
        self._metrics: ClusterMetrics | None = None
        self._is_built = False
        self._vector_dim: int | None = None

    def build(
        self,
        beliefs: list[BeliefVector],
        min_k: int = 2,
        max_k: int = 10,
    ) -> ClusterMetrics:
        """Build the index from beliefs.

        Args:
            beliefs: List of beliefs to index
            min_k: Minimum clusters for auto-selection
            max_k: Maximum clusters for auto-selection

        Returns:
            ClusterMetrics with cluster quality metrics

        Raises:
            IndexError: If index build fails
            ValidationError: If beliefs are invalid
        """
        if not beliefs:
            raise IndexError("Cannot build index from empty beliefs")

        # Validate dimension consistency
        dimensions = {b.dimension for b in beliefs}
        if len(dimensions) > 1:
            raise ValidationError(
                f"All beliefs must have same dimension, found: {dimensions}"
            )
        self._vector_dim = dimensions.pop()

        # Add beliefs to search index
        for belief in beliefs:
            self.search_index.add_belief(belief)

        # Cluster beliefs
        self._metrics = self.clustering_engine.fit(beliefs, min_k=min_k, max_k=max_k)

        # Assign clusters and build mappings
        assignments = self.clustering_engine.assign_clusters(beliefs)
        self._build_cluster_mappings(assignments, beliefs)

        # Build hierarchical structure if enabled
        if self.enable_hierarchy and self.hierarchy_depth > 1:
            self._build_hierarchy(beliefs)

        self._is_built = True
        return self._metrics

    def _build_cluster_mappings(
        self,
        assignments: list[ClusterAssignment],
        beliefs: list[BeliefVector],
    ) -> None:
        """Build cluster to belief mappings.

        Args:
            assignments: Cluster assignments
            beliefs: Original beliefs
        """
        # Initialize clusters from metrics
        self._clusters = {}
        centroids = self.clustering_engine.get_centroids()

        for cluster_id, size in self._metrics.cluster_sizes.items():
            cluster_info = ClusterInfo(
                cluster_id=cluster_id,
                size=size,
                centroid=centroids.get(cluster_id),
            )
            self._clusters[cluster_id] = cluster_info

        # Assign beliefs to clusters
        {b.belief_id: b for b in beliefs}

        for assignment in assignments:
            cluster_id = assignment.cluster_id
            belief_id = assignment.belief_id

            self._belief_to_cluster[belief_id] = cluster_id

            if cluster_id in self._clusters:
                self._clusters[cluster_id].belief_ids.append(belief_id)

    def _build_hierarchy(self, beliefs: list[BeliefVector]) -> None:
        """Build hierarchical clustering structure.

        Args:
            beliefs: Original beliefs
        """
        self._levels = []

        # Level 0 is the base clustering
        base_level = HierarchicalLevel(level=0, engine=self.clustering_engine)
        base_level.clusters = self._clusters.copy()
        self._levels.append(base_level)

        # Build higher levels
        for level in range(1, self.hierarchy_depth):
            # Cluster the centroids from previous level
            centroids = self._levels[-1].engine.get_centroids()
            if len(centroids) <= 2:
                break

            # Create belief vectors from centroids
            centroid_beliefs = [
                BeliefVector(vector=centroid, belief_id=f"centroid_{label}")
                for label, centroid in centroids.items()
            ]

            # Cluster centroids with fewer clusters
            n_clusters = max(2, len(centroids) // 2)
            engine = BeliefClusteringEngine(
                algorithm="kmeans",
                n_clusters=n_clusters,
                auto_select_k=False,
            )

            try:
                engine.fit(centroid_beliefs)
                level_obj = HierarchicalLevel(level=level, engine=engine)

                # Map parent relationships
                assignments = engine.assign_clusters(centroid_beliefs)
                for i, assignment in enumerate(assignments):
                    cluster_id = list(centroids.keys())[i]
                    parent_id = assignment.cluster_id

                    if parent_id not in level_obj.clusters:
                        level_obj.clusters[parent_id] = ClusterInfo(
                            cluster_id=parent_id,
                        )

                    # Link child to parent
                    if cluster_id in self._clusters:
                        self._clusters[cluster_id].parent_cluster = parent_id

                self._levels.append(level_obj)
            except Exception:
                # Stop hierarchy building if clustering fails
                break

    def search_in_cluster(
        self,
        query_vector: np.ndarray,
        cluster_id: int,
        k: int = 5,
    ) -> list[SearchResult]:
        """Search within a specific cluster.

        Args:
            query_vector: Query vector
            cluster_id: Cluster to search in
            k: Number of results

        Returns:
            List of search results from the cluster

        Raises:
            IndexError: If cluster doesn't exist
        """
        if cluster_id not in self._clusters:
            raise IndexError(f"Cluster {cluster_id} not found")

        cluster = self._clusters[cluster_id]

        if not cluster.belief_ids:
            return []

        # Search in the full index then filter to cluster
        results = self.search_index.search(query_vector, k=k * 2)
        cluster_results = [r for r in results if r.belief_id in cluster.belief_ids]

        return cluster_results[:k]

    def search_with_cluster_refinement(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        n_clusters: int = 3,
    ) -> list[SearchResult]:
        """Search with cluster-based refinement.

        First finds the most relevant clusters, then searches within them.

        Args:
            query_vector: Query vector
            k: Total number of results
            n_clusters: Number of clusters to search in

        Returns:
            List of search results
        """
        if not self._is_built or not self._clusters:
            # Fall back to regular search
            return self.search_index.search(query_vector, k=k)

        # Find nearest clusters
        nearest_clusters = self._find_nearest_clusters(query_vector, n_clusters)

        # Search in each cluster
        all_results: list[SearchResult] = []
        results_per_cluster = max(1, k // len(nearest_clusters))

        for cluster_id in nearest_clusters:
            try:
                results = self.search_in_cluster(
                    query_vector, cluster_id, k=results_per_cluster * 2
                )
                all_results.extend(results)
            except IndexError:
                continue

        # Sort by score and return top k
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:k]

    def _find_nearest_clusters(self, query_vector: np.ndarray, n: int) -> list[int]:
        """Find n nearest clusters to query vector.

        Args:
            query_vector: Query vector
            n: Number of clusters to find

        Returns:
            List of cluster IDs
        """
        distances = []
        query_norm = np.linalg.norm(query_vector)

        for cluster_id, cluster in self._clusters.items():
            if cluster.centroid is None:
                continue

            # Compute cosine distance to centroid
            centroid = cluster.centroid
            dot_product = np.dot(query_vector, centroid)
            centroid_norm = np.linalg.norm(centroid)

            if centroid_norm == 0 or query_norm == 0:
                distance = 1.0
            else:
                similarity = dot_product / (query_norm * centroid_norm)
                distance = 1.0 - similarity

            distances.append((cluster_id, distance))

        # Sort by distance and return top n
        distances.sort(key=lambda x: x[1])
        return [c[0] for c in distances[:n]]

    def get_cluster(self, cluster_id: int) -> ClusterInfo | None:
        """Get cluster information.

        Args:
            cluster_id: Cluster identifier

        Returns:
            ClusterInfo if found, None otherwise
        """
        return self._clusters.get(cluster_id)

    def get_belief_cluster(self, belief_id: str) -> int | None:
        """Get the cluster ID for a belief.

        Args:
            belief_id: Belief identifier

        Returns:
            Cluster ID if found, None otherwise
        """
        return self._belief_to_cluster.get(belief_id)

    def get_cluster_beliefs(self, cluster_id: int) -> list[str]:
        """Get all belief IDs in a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            List of belief IDs
        """
        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return []
        return cluster.belief_ids.copy()

    def get_cluster_statistics(self, cluster_id: int) -> dict[str, Any]:
        """Get statistics for a cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            Dictionary with cluster statistics
        """
        cluster = self._clusters.get(cluster_id)
        if cluster is None:
            return {"error": f"Cluster {cluster_id} not found"}

        stats = {
            "cluster_id": cluster_id,
            "size": cluster.size,
            "belief_count": len(cluster.belief_ids),
            "has_centroid": cluster.centroid is not None,
            "parent_cluster": cluster.parent_cluster,
            "metadata": cluster.metadata,
        }

        # Add centroid statistics if available
        if cluster.centroid is not None:
            stats["centroid_norm"] = float(np.linalg.norm(cluster.centroid))
            stats["centroid_dimension"] = len(cluster.centroid)

        return stats

    def get_all_clusters(self) -> list[int]:
        """Get list of all cluster IDs.

        Returns:
            List of cluster IDs
        """
        return list(self._clusters.keys())

    def get_cluster_count(self) -> int:
        """Get total number of clusters.

        Returns:
            Number of clusters
        """
        return len(self._clusters)

    def get_belief_count(self) -> int:
        """Get total number of indexed beliefs.

        Returns:
            Number of beliefs
        """
        return len(self._belief_to_cluster)

    def get_metrics(self) -> ClusterMetrics | None:
        """Get cluster quality metrics.

        Returns:
            ClusterMetrics if index is built, None otherwise
        """
        return self._metrics

    def get_hierarchy_levels(self) -> list[int]:
        """Get list of hierarchy levels.

        Returns:
            List of level numbers
        """
        return [level.level for level in self._levels]

    def get_level_info(self, level: int) -> HierarchicalLevel | None:
        """Get information about a hierarchy level.

        Args:
            level: Level number

        Returns:
            HierarchicalLevel if exists, None otherwise
        """
        for lvl in self._levels:
            if lvl.level == level:
                return lvl
        return None

    def add_belief(self, belief: BeliefVector) -> int:
        """Add a new belief to the index.

        Args:
            belief: Belief to add

        Returns:
            Assigned cluster ID

        Raises:
            IndexError: If index not built
            ValidationError: If belief dimension doesn't match
        """
        if not self._is_built:
            raise IndexError("Index not built. Call build() first.")

        if self._vector_dim is not None:
            if belief.dimension != self._vector_dim:
                raise ValidationError(
                    f"Dimension mismatch: {belief.dimension} vs {self._vector_dim}"
                )

        # Add to search index
        self.search_index.add_belief(belief)

        # Assign to cluster
        cluster_id = self.clustering_engine.predict(belief)

        # Update mappings
        self._belief_to_cluster[belief.belief_id] = cluster_id

        if cluster_id in self._clusters:
            self._clusters[cluster_id].belief_ids.append(belief.belief_id)
            self._clusters[cluster_id].size += 1

        return cluster_id

    def remove_belief(self, belief_id: str) -> bool:
        """Remove a belief from the index.

        Args:
            belief_id: Belief to remove

        Returns:
            True if removed, False if not found
        """
        if belief_id not in self._belief_to_cluster:
            return False

        cluster_id = self._belief_to_cluster[belief_id]

        # Remove from cluster
        if cluster_id in self._clusters:
            cluster = self._clusters[cluster_id]
            if belief_id in cluster.belief_ids:
                cluster.belief_ids.remove(belief_id)
                cluster.size -= 1

        # Remove from mapping
        del self._belief_to_cluster[belief_id]

        # Remove from search index
        self.search_index.delete_belief(belief_id)

        return True

    def save(self, filepath: str) -> None:
        """Save the index to a file.

        Args:
            filepath: Path to save index

        Raises:
            IOError: If file cannot be written
        """
        data = {
            "version": "1.0.0",
            "is_built": self._is_built,
            "vector_dim": self._vector_dim,
            "enable_hierarchy": self.enable_hierarchy,
            "hierarchy_depth": self.hierarchy_depth,
            "clustering_engine": self.clustering_engine.to_dict(),
            "clusters": {k: v.to_dict() for k, v in self._clusters.items()},
            "belief_to_cluster": self._belief_to_cluster,
            "levels": [level.to_dict() for level in self._levels],
            "metrics": self._metrics.to_dict() if self._metrics else None,
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(
        cls,
        filepath: str,
        search_index: BeliefSearchIndex | None = None,
    ) -> BeliefIndex:
        """Load an index from a file.

        Args:
            filepath: Path to load index from
            search_index: Search index to use (creates default if None)

        Returns:
            Loaded BeliefIndex

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        # Reconstruct clustering engine
        engine_data = data.get("clustering_engine", {})
        clustering_engine = BeliefClusteringEngine.from_dict(engine_data)

        # Create index
        index = cls(
            clustering_engine=clustering_engine,
            search_index=search_index or BeliefSearchIndex.create_with_fallback(),
            enable_hierarchy=data.get("enable_hierarchy", False),
            hierarchy_depth=data.get("hierarchy_depth", 2),
        )

        # Restore state
        index._is_built = data.get("is_built", False)
        index._vector_dim = data.get("vector_dim")
        index._belief_to_cluster = dict(data.get("belief_to_cluster", {}))

        # Restore clusters
        clusters_data = data.get("clusters", {})
        index._clusters = {
            int(k): ClusterInfo.from_dict(v) for k, v in clusters_data.items()
        }

        # Restore levels
        levels_data = data.get("levels", [])
        index._levels = [
            HierarchicalLevel.from_dict(level_data) for level_data in levels_data
        ]

        # Restore metrics
        metrics_data = data.get("metrics")
        if metrics_data:
            index._metrics = ClusterMetrics.from_dict(metrics_data)

        return index

    def to_dict(self) -> dict[str, Any]:
        """Convert index to dictionary (without search index)."""
        return {
            "is_built": self._is_built,
            "vector_dim": self._vector_dim,
            "enable_hierarchy": self.enable_hierarchy,
            "hierarchy_depth": self.hierarchy_depth,
            "cluster_count": len(self._clusters),
            "belief_count": len(self._belief_to_cluster),
            "clusters": {k: v.to_dict() for k, v in self._clusters.items()},
            "metrics": self._metrics.to_dict() if self._metrics else None,
        }

    def __repr__(self) -> str:
        return (
            f"BeliefIndex("
            f"clusters={len(self._clusters)}, "
            f"beliefs={len(self._belief_to_cluster)}, "
            f"built={self._is_built})"
        )

    def __len__(self) -> int:
        """Return number of indexed beliefs."""
        return len(self._belief_to_cluster)
