"""Vector Search Module for Belief Embeddings.

Provides the BeliefSearchIndex class for managing vector search operations
with Qdrant integration and persistence support.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, PointStruct, VectorParams

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

from .vector import BeliefMetadata, BeliefVector, ValidationError


class SearchResult:
    """Result of a vector search operation.

    Attributes:
        belief_id: Unique identifier of the matched belief
        score: Similarity score (higher is more similar for cosine similarity)
        vector: The matched vector (optional)
        metadata: Associated metadata (optional)
    """

    def __init__(
        self,
        belief_id: str,
        score: float,
        vector: np.ndarray | None = None,
        metadata: BeliefMetadata | None = None,
    ):
        self.belief_id = belief_id
        self.score = score
        self.vector = vector
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        """Convert search result to dictionary."""
        result = {
            "belief_id": self.belief_id,
            "score": self.score,
        }
        if self.vector is not None:
            result["vector"] = self.vector.tolist()
        if self.metadata is not None:
            result["metadata"] = self.metadata.to_dict()
        return result

    def __repr__(self) -> str:
        return f"SearchResult(belief_id={self.belief_id!r}, score={self.score:.4f})"


class VectorIndexBackend(Protocol):
    """Protocol for vector index backend implementations."""

    def add_belief(self, belief: BeliefVector) -> None:
        """Add a belief to the index."""
        ...

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search for k nearest neighbors."""
        ...

    def delete_belief(self, belief_id: str) -> bool:
        """Delete a belief from the index."""
        ...

    def get_belief(self, belief_id: str) -> BeliefVector | None:
        """Get a belief by ID."""
        ...


@dataclass
class InMemoryBackend:
    """In-memory vector index backend using brute-force search.

    Used as a fallback when Qdrant is unavailable or for testing.
    """

    _beliefs: dict[str, BeliefVector] = field(default_factory=dict)

    def add_belief(self, belief: BeliefVector) -> None:
        """Add a belief to the in-memory index."""
        self._beliefs[belief.belief_id] = belief

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search for k nearest neighbors using cosine similarity."""
        if not self._beliefs:
            return []

        results = []
        query_norm = np.linalg.norm(query_vector)

        for belief in self._beliefs.values():
            if belief.dimension != len(query_vector):
                continue

            # Compute cosine similarity
            dot_product = np.dot(query_vector, belief.vector)
            magnitude_product = query_norm * belief.magnitude

            if magnitude_product == 0:
                continue

            similarity = dot_product / magnitude_product

            results.append(
                SearchResult(
                    belief_id=belief.belief_id,
                    score=float(similarity),
                    vector=belief.vector.copy(),
                    metadata=belief.metadata,
                )
            )

        # Sort by similarity (descending)
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:k]

    def delete_belief(self, belief_id: str) -> bool:
        """Delete a belief from the index."""
        if belief_id in self._beliefs:
            del self._beliefs[belief_id]
            return True
        return False

    def get_belief(self, belief_id: str) -> BeliefVector | None:
        """Get a belief by ID."""
        return self._beliefs.get(belief_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert the index to a dictionary for serialization."""
        return {
            "beliefs": [belief.to_dict() for belief in self._beliefs.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InMemoryBackend:
        """Create an index from a dictionary."""
        backend = cls()
        for belief_data in data.get("beliefs", []):
            belief = BeliefVector.from_dict(belief_data)
            backend.add_belief(belief)
        return backend


class QdrantBackend:
    """Qdrant-based vector index backend.

    Provides persistent, scalable vector search using Qdrant.
    """

    DEFAULT_COLLECTION = "ChiseAI"
    DEFAULT_DIMENSION = 384
    DEFAULT_HOST = "host.docker.internal"
    DEFAULT_PORT = 6334

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        dimension: int | None = None,
    ):
        """Initialize Qdrant backend.

        Args:
            host: Qdrant server host (default: host.docker.internal)
            port: Qdrant server port (default: 6334)
            collection_name: Name of the collection (default: "ChiseAI")
            dimension: Vector dimension (default: 384)
        """
        if not QDRANT_AVAILABLE:
            raise ImportError(
                "qdrant-client is required for QdrantBackend. "
                "Install with: pip install qdrant-client"
            )

        self.host = host or os.getenv("QDRANT_HOST", self.DEFAULT_HOST)
        self.port = port or int(os.getenv("QDRANT_PORT", self.DEFAULT_PORT))
        self.collection_name = collection_name or self.DEFAULT_COLLECTION
        self.dimension = dimension or self.DEFAULT_DIMENSION

        self._client: QdrantClient | None = None
        self._initialized = False

    def _get_client(self) -> QdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    def _ensure_collection(self) -> None:
        """Ensure the collection exists."""
        if self._initialized:
            return

        client = self._get_client()

        try:
            # Check if collection exists
            collections = client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                # Create collection with cosine distance
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE,
                    ),
                )
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Qdrant collection: {e}") from e

        self._initialized = True

    def add_belief(self, belief: BeliefVector) -> None:
        """Add a belief to the Qdrant index."""
        self._ensure_collection()
        client = self._get_client()

        # Convert vector to list for Qdrant
        vector_list = belief.vector.tolist()

        # Validate dimension
        if len(vector_list) != self.dimension:
            raise ValidationError(
                f"Vector dimension {len(vector_list)} does not match "
                f"collection dimension {self.dimension}"
            )

        # Prepare payload with metadata
        payload = {
            "belief_id": belief.belief_id,
            "metadata": belief.metadata.to_dict(),
        }

        try:
            client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=belief.belief_id,
                        vector=vector_list,
                        payload=payload,
                    )
                ],
            )
        except Exception as e:
            raise ConnectionError(f"Failed to add belief to Qdrant: {e}") from e

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search for k nearest neighbors in Qdrant."""
        self._ensure_collection()
        client = self._get_client()

        vector_list = query_vector.tolist()

        if len(vector_list) != self.dimension:
            raise ValidationError(
                f"Query vector dimension {len(vector_list)} does not match "
                f"collection dimension {self.dimension}"
            )

        try:
            search_result = client.search(
                collection_name=self.collection_name,
                query_vector=vector_list,
                limit=k,
                with_payload=True,
            )
        except Exception as e:
            raise ConnectionError(f"Failed to search Qdrant: {e}") from e

        results = []
        for scored_point in search_result:
            payload = scored_point.payload or {}
            metadata_dict = payload.get("metadata", {})
            metadata = BeliefMetadata.from_dict(metadata_dict)

            results.append(
                SearchResult(
                    belief_id=str(scored_point.id),
                    score=float(scored_point.score),
                    metadata=metadata,
                )
            )

        return results

    def delete_belief(self, belief_id: str) -> bool:
        """Delete a belief from the Qdrant index."""
        self._ensure_collection()
        client = self._get_client()

        try:
            result = client.delete(
                collection_name=self.collection_name,
                points_selector=[belief_id],
            )
            return result.status == "completed"
        except Exception:
            # Belief may not exist
            return False

    def get_belief(self, belief_id: str) -> BeliefVector | None:
        """Get a belief by ID from Qdrant."""
        self._ensure_collection()
        client = self._get_client()

        try:
            points = client.retrieve(
                collection_name=self.collection_name,
                ids=[belief_id],
                with_vectors=True,
                with_payload=True,
            )

            if not points:
                return None

            point = points[0]
            payload = point.payload or {}
            vector = np.array(point.vector, dtype=np.float64)
            metadata_dict = payload.get("metadata", {})
            metadata = BeliefMetadata.from_dict(metadata_dict)

            return BeliefVector(
                vector=vector,
                metadata=metadata,
                belief_id=belief_id,
            )
        except Exception:
            return None


@dataclass
class BeliefSearchIndex:
    """Main interface for belief vector search operations.

    Provides a unified API for adding, searching, and managing beliefs
    in a vector index. Supports both Qdrant (for production) and
    in-memory backends.

    Attributes:
        backend: The underlying vector index backend
        auto_persist: Whether to auto-save on modifications
        persist_path: Path for persistence (if auto_persist is True)
    """

    backend: VectorIndexBackend = field(default_factory=InMemoryBackend)
    auto_persist: bool = False
    persist_path: str | None = None

    @classmethod
    def create_with_qdrant(
        cls,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        dimension: int | None = None,
    ) -> BeliefSearchIndex:
        """Create a search index backed by Qdrant.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Name of the collection
            dimension: Vector dimension

        Returns:
            BeliefSearchIndex configured with Qdrant backend

        Raises:
            ImportError: If qdrant-client is not installed
            ConnectionError: If Qdrant is not available
        """
        backend = QdrantBackend(
            host=host,
            port=port,
            collection_name=collection_name,
            dimension=dimension,
        )
        return cls(backend=backend)

    @classmethod
    def create_with_fallback(
        cls,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        dimension: int | None = None,
    ) -> BeliefSearchIndex:
        """Create a search index with automatic fallback to in-memory.

        Attempts to connect to Qdrant, falls back to in-memory if unavailable.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Name of the collection
            dimension: Vector dimension

        Returns:
            BeliefSearchIndex with either Qdrant or in-memory backend
        """
        if not QDRANT_AVAILABLE:
            return cls(backend=InMemoryBackend())

        try:
            backend = QdrantBackend(
                host=host,
                port=port,
                collection_name=collection_name,
                dimension=dimension,
            )
            # Test connection
            backend._get_client()
            backend._ensure_collection()
            return cls(backend=backend)
        except Exception:
            # Fall back to in-memory
            return cls(backend=InMemoryBackend())

    def add_belief(
        self,
        belief: BeliefVector,
    ) -> None:
        """Add a belief to the search index.

        Args:
            belief: The BeliefVector to add

        Raises:
            ValidationError: If the belief is invalid
            ConnectionError: If the backend operation fails
        """
        self.backend.add_belief(belief)

        if self.auto_persist and self.persist_path:
            self.save(self.persist_path)

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Search for k beliefs most similar to the query vector.

        Args:
            query_vector: The query vector (numpy array)
            k: Number of results to return (default: 5)

        Returns:
            List of SearchResult objects, sorted by similarity (descending)

        Raises:
            ValidationError: If query vector is invalid
            ConnectionError: If the backend operation fails
        """
        if not isinstance(query_vector, np.ndarray):
            raise ValidationError(
                f"Query vector must be numpy.ndarray, got {type(query_vector)}"
            )

        if query_vector.ndim != 1:
            raise ValidationError(
                f"Query vector must be 1-dimensional, got {query_vector.ndim} dimensions"
            )

        if len(query_vector) == 0:
            raise ValidationError("Query vector cannot be empty")

        return self.backend.search(query_vector, k)

    def search_by_similarity(
        self,
        belief: BeliefVector,
        k: int = 5,
    ) -> list[SearchResult]:
        """Search for beliefs similar to an existing belief.

        Args:
            belief: The BeliefVector to search by
            k: Number of results to return (default: 5)

        Returns:
            List of SearchResult objects, sorted by similarity (descending)

        Raises:
            ValidationError: If the belief is invalid
            ConnectionError: If the backend operation fails
        """
        # Search for k+1 to potentially exclude the belief itself
        results = self.backend.search(belief.vector, k=k + 1)

        # Filter out the belief itself if it's in the results
        results = [r for r in results if r.belief_id != belief.belief_id]

        return results[:k]

    def delete_belief(self, belief_id: str) -> bool:
        """Delete a belief from the index.

        Args:
            belief_id: The unique identifier of the belief to delete

        Returns:
            True if the belief was deleted, False if it didn't exist
        """
        result = self.backend.delete_belief(belief_id)

        if result and self.auto_persist and self.persist_path:
            self.save(self.persist_path)

        return result

    def get_belief(self, belief_id: str) -> BeliefVector | None:
        """Get a belief by its ID.

        Args:
            belief_id: The unique identifier of the belief

        Returns:
            The BeliefVector if found, None otherwise
        """
        return self.backend.get_belief(belief_id)

    def save(self, filepath: str) -> None:
        """Save the index to a file.

        Only supported for InMemoryBackend. Qdrant backend
        is already persistent.

        Args:
            filepath: Path to save the index

        Raises:
            TypeError: If backend doesn't support serialization
            IOError: If file cannot be written
        """
        if isinstance(self.backend, InMemoryBackend):
            data = {
                "type": "InMemoryBackend",
                "created_at": datetime.now(UTC).isoformat(),
                "data": self.backend.to_dict(),
            }
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            raise TypeError(
                "Save is only supported for InMemoryBackend. "
                "Qdrant backend is already persistent."
            )

    @classmethod
    def load(cls, filepath: str) -> BeliefSearchIndex:
        """Load an index from a file.

        Args:
            filepath: Path to the saved index

        Returns:
            BeliefSearchIndex with loaded data

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        if data.get("type") != "InMemoryBackend":
            raise ValueError(f"Unknown backend type: {data.get('type')}")

        backend = InMemoryBackend.from_dict(data["data"])
        return cls(backend=backend)

    def __len__(self) -> int:
        """Return the number of beliefs in the index."""
        if isinstance(self.backend, InMemoryBackend):
            return len(self.backend._beliefs)
        # For Qdrant, we can't easily get count without an API call
        return -1

    def __repr__(self) -> str:
        backend_name = type(self.backend).__name__
        return f"BeliefSearchIndex(backend={backend_name})"
