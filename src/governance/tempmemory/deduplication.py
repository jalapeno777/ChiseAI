"""
Tempmemory Deduplication Module for ChiseAI.

Provides embedding-based deduplication for memories before Qdrant storage.
Uses sentence-transformers for generating embeddings and cosine similarity
for duplicate detection.

This module is part of Phase 2 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Default similarity threshold for duplicate detection
DEFAULT_SIMILARITY_THRESHOLD = 0.92


class DeduplicationAction(Enum):
    """Actions to take when a duplicate is detected."""

    SKIP = "skip"  # Skip storing the duplicate
    MERGE = "merge"  # Merge with existing memory
    FLAG = "flag"  # Store but flag as duplicate
    REPLACE = "replace"  # Replace existing with new


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match.

    Attributes:
        memory_id: ID of the matched memory
        similarity: Similarity score (0.0 to 1.0)
        content: Content of the matched memory
        metadata: Metadata of the matched memory
    """

    memory_id: str
    similarity: float
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "similarity": self.similarity,
            "content": self.content[:500] if self.content else "",  # Truncate
            "metadata": self.metadata,
        }


@dataclass
class DeduplicationResult:
    """Result of a deduplication check.

    Attributes:
        is_duplicate: Whether the content is a duplicate
        action: Action to take
        matches: List of matching memories
        selected_match: The best matching memory (if any)
        message: Human-readable message
    """

    is_duplicate: bool
    action: DeduplicationAction
    matches: list[DuplicateMatch] = field(default_factory=list)
    selected_match: DuplicateMatch | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_duplicate": self.is_duplicate,
            "action": self.action.value,
            "matches": [m.to_dict() for m in self.matches],
            "selected_match": (
                self.selected_match.to_dict() if self.selected_match else None
            ),
            "message": self.message,
        }


class EmbeddingGenerator:
    """Generates embeddings for text content.

    Uses sentence-transformers (all-MiniLM-L6-v2) for generating embeddings.
    Falls back to simple hash-based embeddings if the library is not available.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384  # Dimensionality of all-MiniLM-L6-v2

    def __init__(self) -> None:
        """Initialize the embedding generator."""
        self._model: Any | None = None
        self._model_available = False

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
            self._model_available = True
            logger.info(f"Loaded embedding model: {self.MODEL_NAME}")
        except ImportError:
            logger.warning(
                "sentence-transformers not available, using fallback embeddings"
            )
        except Exception as e:
            logger.warning(f"Failed to load embedding model: {e}")

    def generate(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: The text to embed.

        Returns:
            List of float values representing the embedding.
        """
        if not text:
            return [0.0] * self.EMBEDDING_DIM

        if self._model_available and self._model is not None:
            try:
                embedding = self._model.encode(text, convert_to_numpy=True)
                return embedding.tolist()
            except Exception as e:
                logger.warning(f"Model encoding failed, using fallback: {e}")

        # Fallback: Use simple hash-based embedding
        return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str) -> list[float]:
        """Generate a simple hash-based embedding as fallback.

        This is not as good as proper embeddings but provides a consistent
        vector representation for similarity comparison.

        Args:
            text: The text to embed.

        Returns:
            List of float values.
        """
        import hashlib

        # Create multiple hash values from the text
        hash_input = text.encode("utf-8")
        hash_values = []

        # Generate multiple hash segments
        for i in range(self.EMBEDDING_DIM // 8):
            hash_obj = hashlib.md5(
                hash_input + i.to_bytes(4, "little"), usedforsecurity=False
            )
            hash_int = int(hash_obj.hexdigest(), 16)
            # Normalize to [-1, 1] range
            normalized = (hash_int % 20000) / 10000 - 1
            hash_values.append(normalized)

        # Pad to full dimension
        while len(hash_values) < self.EMBEDDING_DIM:
            hash_values.extend(hash_values[: self.EMBEDDING_DIM - len(hash_values)])

        return hash_values[: self.EMBEDDING_DIM]

    def compute_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Cosine similarity score (0.0 to 1.0).
        """
        if len(embedding1) != len(embedding2):
            logger.warning(
                f"Embedding dimension mismatch: {len(embedding1)} vs {len(embedding2)}"
            )
            return 0.0

        # Compute dot product
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2, strict=False))

        # Compute magnitudes
        magnitude1 = sum(a * a for a in embedding1) ** 0.5
        magnitude2 = sum(b * b for b in embedding2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        # Cosine similarity
        similarity = dot_product / (magnitude1 * magnitude2)

        # Clamp to [0, 1] range
        return max(0.0, min(1.0, similarity))


class DeduplicationEngine:
    """Engine for detecting and handling duplicate memories.

    Uses embedding-based similarity to detect near-duplicate memories.
    Stores embeddings in Redis for fast lookup.

    Redis Key Structure:
    - bmad:chiseai:tempmemory:embeddings:{memory_id} - Hash with embedding vector
    - bmad:chiseai:tempmemory:dedup:index - Set of all indexed memory IDs
    """

    REDIS_EMBEDDING_PREFIX = "bmad:chiseai:tempmemory:embeddings"
    REDIS_DEDUP_INDEX = "bmad:chiseai:tempmemory:dedup:index"
    REDIS_DEDUP_TTL = 90 * 24 * 3600  # 90 days

    def __init__(
        self,
        redis_client: Any | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        default_action: DeduplicationAction = DeduplicationAction.FLAG,
        dry_run: bool = False,
    ):
        """Initialize the deduplication engine.

        Args:
            redis_client: Optional Redis client for storing embeddings.
            similarity_threshold: Threshold for duplicate detection (0.0-1.0).
            default_action: Default action when duplicate is detected.
            dry_run: If True, don't make actual changes.
        """
        self._redis_client = redis_client
        self._similarity_threshold = similarity_threshold
        self._default_action = default_action
        self._dry_run = dry_run
        self._embedding_generator = EmbeddingGenerator()

        logger.info(
            "DeduplicationEngine initialized",
            extra={
                "similarity_threshold": similarity_threshold,
                "default_action": default_action.value,
                "has_redis": redis_client is not None,
                "dry_run": dry_run,
            },
        )

    def check_duplicate(
        self,
        content: str,
        memory_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeduplicationResult:
        """Check if content is a duplicate of existing memories.

        Args:
            content: The content to check.
            memory_id: Optional memory ID (for new memories).
            metadata: Optional metadata for the content.

        Returns:
            DeduplicationResult with detection results.
        """
        if not content:
            return DeduplicationResult(
                is_duplicate=False,
                action=DeduplicationAction.SKIP,
                message="Empty content, cannot check for duplicates",
            )

        # Generate embedding for the new content
        embedding = self._embedding_generator.generate(content)

        # Search for similar embeddings
        matches = self._find_similar_embeddings(embedding, exclude_id=memory_id)

        # Filter matches by threshold
        above_threshold = [
            m for m in matches if m.similarity >= self._similarity_threshold
        ]

        if not above_threshold:
            return DeduplicationResult(
                is_duplicate=False,
                action=DeduplicationAction.SKIP,  # No action needed
                matches=matches[:5],  # Return top 5 for reference
                message=f"No duplicates found (threshold: {self._similarity_threshold})",
            )

        # Sort by similarity (highest first)
        above_threshold.sort(key=lambda m: m.similarity, reverse=True)
        best_match = above_threshold[0]

        return DeduplicationResult(
            is_duplicate=True,
            action=self._default_action,
            matches=above_threshold,
            selected_match=best_match,
            message=(
                f"Duplicate detected with similarity {best_match.similarity:.4f} "
                f"(threshold: {self._similarity_threshold})"
            ),
        )

    def index_memory(
        self,
        memory_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Index a memory for future deduplication checks.

        Args:
            memory_id: Unique identifier for the memory.
            content: The content to index.
            metadata: Optional metadata.

        Returns:
            True if successful, False otherwise.
        """
        if self._dry_run:
            logger.debug(f"[DRY RUN] Would index memory: {memory_id}")
            return True

        if self._redis_client is None:
            logger.debug(f"No Redis client, skipping indexing for {memory_id}")
            return False

        try:
            # Generate embedding
            embedding = self._embedding_generator.generate(content)

            # Store embedding in Redis
            redis_key = f"{self.REDIS_EMBEDDING_PREFIX}:{memory_id}"
            self._redis_client.hset(
                redis_key,
                mapping={
                    "embedding": json.dumps(embedding),
                    "content_preview": content[:200],
                    "metadata": json.dumps(metadata or {}),
                    "indexed_at": datetime.now(UTC).isoformat(),
                },
            )
            self._redis_client.expire(redis_key, self.REDIS_DEDUP_TTL)

            # Add to index
            self._redis_client.sadd(self.REDIS_DEDUP_INDEX, memory_id)
            self._redis_client.expire(self.REDIS_DEDUP_INDEX, self.REDIS_DEDUP_TTL)

            logger.debug(f"Indexed memory: {memory_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to index memory {memory_id}: {e}")
            return False

    def remove_from_index(self, memory_id: str) -> bool:
        """Remove a memory from the deduplication index.

        Args:
            memory_id: The memory ID to remove.

        Returns:
            True if successful, False otherwise.
        """
        if self._dry_run:
            logger.debug(f"[DRY RUN] Would remove from index: {memory_id}")
            return True

        if self._redis_client is None:
            return False

        try:
            redis_key = f"{self.REDIS_EMBEDDING_PREFIX}:{memory_id}"
            self._redis_client.delete(redis_key)
            self._redis_client.srem(self.REDIS_DEDUP_INDEX, memory_id)
            logger.debug(f"Removed from index: {memory_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove {memory_id} from index: {e}")
            return False

    def _find_similar_embeddings(
        self,
        query_embedding: list[float],
        exclude_id: str | None = None,
    ) -> list[DuplicateMatch]:
        """Find similar embeddings in the index.

        Args:
            query_embedding: The embedding to search for.
            exclude_id: Optional memory ID to exclude from results.

        Returns:
            List of DuplicateMatch objects sorted by similarity.
        """
        matches: list[DuplicateMatch] = []

        if self._redis_client is None:
            return matches

        try:
            # Get all indexed memory IDs
            memory_ids = self._redis_client.smembers(self.REDIS_DEDUP_INDEX)

            for memory_id_bytes in memory_ids:
                memory_id = (
                    memory_id_bytes.decode()
                    if isinstance(memory_id_bytes, bytes)
                    else memory_id_bytes
                )

                if memory_id == exclude_id:
                    continue

                # Get the stored embedding
                redis_key = f"{self.REDIS_EMBEDDING_PREFIX}:{memory_id}"
                data = self._redis_client.hgetall(redis_key)

                if not data:
                    continue

                # Parse embedding
                embedding_json = data.get(b"embedding") or data.get("embedding")
                if not embedding_json:
                    continue

                try:
                    stored_embedding = json.loads(
                        embedding_json.decode()
                        if isinstance(embedding_json, bytes)
                        else embedding_json
                    )
                except json.JSONDecodeError:
                    continue

                # Compute similarity
                similarity = self._embedding_generator.compute_similarity(
                    query_embedding, stored_embedding
                )

                # Get content preview and metadata
                content_preview = data.get(b"content_preview") or data.get(
                    "content_preview", ""
                )
                metadata_json = data.get(b"metadata") or data.get("metadata", "{}")

                try:
                    metadata = json.loads(
                        metadata_json.decode()
                        if isinstance(metadata_json, bytes)
                        else metadata_json
                    )
                except json.JSONDecodeError:
                    metadata = {}

                matches.append(
                    DuplicateMatch(
                        memory_id=memory_id,
                        similarity=similarity,
                        content=(
                            content_preview.decode()
                            if isinstance(content_preview, bytes)
                            else content_preview
                        ),
                        metadata=metadata,
                    )
                )

            # Sort by similarity (highest first)
            matches.sort(key=lambda m: m.similarity, reverse=True)

        except Exception as e:
            logger.warning(f"Failed to find similar embeddings: {e}")

        return matches

    def get_index_stats(self) -> dict[str, Any]:
        """Get statistics about the deduplication index.

        Returns:
            Dictionary with index statistics.
        """
        stats = {
            "total_indexed": 0,
            "index_key": self.REDIS_DEDUP_INDEX,
            "similarity_threshold": self._similarity_threshold,
            "default_action": self._default_action.value,
        }

        if self._redis_client is None:
            stats["status"] = "no_redis_client"
            return stats

        try:
            stats["total_indexed"] = self._redis_client.scard(self.REDIS_DEDUP_INDEX)
            stats["status"] = "active"
        except Exception as e:
            stats["status"] = f"error: {e}"

        return stats

    def clear_index(self) -> bool:
        """Clear all indexed embeddings.

        Returns:
            True if successful, False otherwise.
        """
        if self._dry_run:
            logger.debug("[DRY RUN] Would clear deduplication index")
            return True

        if self._redis_client is None:
            return False

        try:
            # Get all indexed IDs
            memory_ids = self._redis_client.smembers(self.REDIS_DEDUP_INDEX)

            # Delete each embedding key
            for memory_id_bytes in memory_ids:
                memory_id = (
                    memory_id_bytes.decode()
                    if isinstance(memory_id_bytes, bytes)
                    else memory_id_bytes
                )
                redis_key = f"{self.REDIS_EMBEDDING_PREFIX}:{memory_id}"
                self._redis_client.delete(redis_key)

            # Delete the index
            self._redis_client.delete(self.REDIS_DEDUP_INDEX)

            logger.info("Cleared deduplication index")
            return True
        except Exception as e:
            logger.warning(f"Failed to clear index: {e}")
            return False
