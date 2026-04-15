"""Learning Store Module for Autonomous Cognition.

Provides real Qdrant vector storage for iteration learnings with graceful
degradation to Redis fallback when Qdrant is unavailable.

This module replaces simulated "would store" behavior with actual
qdrant_client.upsert() calls for persistent vector storage.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default collection name for autocog learnings
LEARNING_COLLECTION = "autocog_learnings"

# Redis key prefix for fallback
REDIS_LEARNING_PREFIX = "bmad:chiseai:learning:qdrant_fallback"


@dataclass
class LearningRecord:
    """A learning record to be stored in Qdrant."""

    record_id: str
    record_type: str  # "prediction" or "outcome"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_payload(self) -> dict[str, Any]:
        """Convert to Qdrant payload."""
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class LearningStore:
    """Handles real Qdrant writes for autonomous cognition learnings.

    Provides vector storage with graceful degradation to Redis if Qdrant
    is unavailable. All production paths perform real vector upserts.

    Attributes:
        qdrant_collection: The Qdrant collection name for learnings
        vector_size: Dimensionality of embedding vectors
    """

    def __init__(
        self,
        qdrant_client: Any | None = None,
        redis_client: Any | None = None,
        collection_name: str = LEARNING_COLLECTION,
        vector_size: int = 384,
    ) -> None:
        """Initialize the LearningStore.

        Args:
            qdrant_client: Optional Qdrant client instance
            redis_client: Optional Redis client for fallback
            collection_name: Qdrant collection name (default: autocog_learnings)
            vector_size: Embedding vector dimensionality (default: 384)
        """
        self._qdrant_client = qdrant_client
        self._redis_client = redis_client
        self.qdrant_collection = collection_name
        self.vector_size = vector_size
        self._qdrant_initialized = False

    def _get_qdrant_client(self) -> Any | None:
        """Get or create Qdrant client with lazy initialization.

        Returns:
            QdrantClient instance or None if unavailable
        """
        if self._qdrant_client is not None:
            return self._qdrant_client

        if not QDRANT_AVAILABLE:
            logger.warning("Qdrant client library not available")
            return None

        try:
            # Use host.docker.internal for container access to Qdrant
            # falls back to localhost for local development
            import os

            host = os.environ.get("QDRANT_HOST", "host.docker.internal")
            port = int(os.environ.get("QDRANT_PORT", "6334"))

            self._qdrant_client = QdrantClient(host=host, port=port)
            self._ensure_collection()
            return self._qdrant_client
        except Exception as e:
            logger.warning("Failed to connect to Qdrant: %s", e)
            return None

    def _ensure_collection(self) -> bool:
        """Ensure the learning collection exists in Qdrant.

        Returns:
            True if collection exists or was created
        """
        if self._qdrant_initialized or self._qdrant_client is None:
            return self._qdrant_initialized

        try:
            # Check if collection exists
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.qdrant_collection not in collection_names:
                # Create the collection
                self._qdrant_client.create_collection(
                    collection_name=self.qdrant_collection,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection: %s", self.qdrant_collection)

            self._qdrant_initialized = True
            return True
        except Exception as e:
            logger.warning("Failed to ensure Qdrant collection: %s", e)
            return False

    @staticmethod
    def generate_embedding(text: str, dimensions: int = 384) -> list[float]:
        """Generate a deterministic embedding vector from text.

        Uses SHA256-based hashing to create reproducible vectors without
        requiring ML model dependencies.

        Args:
            text: Input text to embed
            dimensions: Vector dimensionality (default: 384)

        Returns:
            List of float values representing the embedding
        """
        if not text:
            return [0.0] * dimensions

        values: list[float] = []
        data = text.encode("utf-8")
        for i in range(dimensions):
            digest = hashlib.sha256(data + i.to_bytes(4, "little")).digest()
            raw = int.from_bytes(digest[:4], "little")
            # Normalize to [-1, 1] range
            values.append((raw % 20000) / 10000 - 1.0)
        return values

    def store_learning(
        self,
        record: LearningRecord,
        vector: list[float] | None = None,
    ) -> bool:
        """Store a learning record in Qdrant with real vector upsert.

        This method performs actual Qdrant upsert operations. No simulated
        or "would store" behavior occurs in production paths.

        Args:
            record: The LearningRecord to store
            vector: Optional pre-computed embedding (generated from content if None)

        Returns:
            True if storage succeeded (Qdrant or Redis fallback)
        """
        # Generate embedding from content if not provided
        if vector is None:
            vector = self.generate_embedding(record.content, self.vector_size)

        payload = record.to_payload()

        # Attempt real Qdrant upsert
        qdrant_client = self._get_qdrant_client()
        if qdrant_client is not None:
            try:
                point_id = hashlib.sha256(record.record_id.encode("utf-8")).hexdigest()[
                    :32
                ]

                qdrant_client.upsert(
                    collection_name=self.qdrant_collection,
                    points=[
                        {
                            "id": point_id,
                            "vector": vector,
                            "payload": payload,
                        }
                    ],
                )
                logger.debug(
                    "Stored learning in Qdrant: %s (%s)",
                    record.record_id,
                    record.record_type,
                )
                return True
            except Exception as e:
                logger.warning(
                    "Qdrant upsert failed for %s, falling back to Redis: %s",
                    record.record_id,
                    e,
                )

        # Graceful degradation to Redis fallback
        return self._redis_fallback(record, payload)

    def _redis_fallback(self, record: LearningRecord, payload: dict[str, Any]) -> bool:
        """Store learning in Redis when Qdrant is unavailable.

        Args:
            record: The learning record
            payload: Pre-serialized payload

        Returns:
            True if Redis storage succeeded
        """
        if self._redis_client is None:
            logger.error(
                "Both Qdrant and Redis unavailable for learning storage: %s",
                record.record_id,
            )
            return False

        try:
            key = f"{REDIS_LEARNING_PREFIX}:{record.record_type}:{record.record_id}"
            self._redis_client.set(
                key,
                json.dumps(payload),
                ex=86400 * 7,  # 7 day TTL for fallback
            )
            logger.debug(
                "Stored learning in Redis fallback: %s (%s)",
                record.record_id,
                record.record_type,
            )
            return True
        except Exception as e:
            logger.error(
                "Redis fallback also failed for %s: %s",
                record.record_id,
                e,
            )
            return False

    def store_prediction(
        self,
        prediction_id: str,
        prediction_type: str,
        confidence: float,
        context: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> bool:
        """Store a prediction learning record.

        Args:
            prediction_id: Unique identifier for the prediction
            prediction_type: Type/category of prediction
            confidence: Confidence level (0.0 to 1.0)
            context: Additional prediction context
            timestamp: When the prediction was made

        Returns:
            True if storage succeeded
        """
        record = LearningRecord(
            record_id=prediction_id,
            record_type="prediction",
            content=f"Prediction: {prediction_id} | Type: {prediction_type} | Confidence: {confidence}",
            metadata={
                "prediction_type": prediction_type,
                "confidence": confidence,
                "context": context,
            },
            created_at=timestamp or datetime.now(UTC),
        )
        return self.store_learning(record)

    def store_outcome(
        self,
        outcome_id: str,
        prediction_id: str,
        actual_value: Any,
        metadata: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> bool:
        """Store an outcome learning record.

        Args:
            outcome_id: Unique identifier for the outcome
            prediction_id: ID of the associated prediction
            actual_value: The actual observed value
            metadata: Additional outcome metadata
            timestamp: When the outcome was recorded

        Returns:
            True if storage succeeded
        """
        record = LearningRecord(
            record_id=outcome_id,
            record_type="outcome",
            content=f"Outcome: {outcome_id} | Prediction: {prediction_id} | Actual: {actual_value}",
            metadata={
                "prediction_id": prediction_id,
                "actual_value": str(actual_value),
                **metadata,
            },
            created_at=timestamp or datetime.now(UTC),
        )
        return self.store_learning(record)

    def delete_learning(self, learning_id: str) -> bool:
        """Delete a learning record from both Qdrant and Redis fallback.

        Attempts to remove the learning from Qdrant first. If Qdrant is
        unavailable, attempts Redis cleanup. Returns True if deletion
        succeeded from any backend.

        Args:
            learning_id: The record_id of the learning to delete

        Returns:
            True if deletion succeeded from at least one backend
        """
        qdrant_deleted = self._delete_from_qdrant(learning_id)
        redis_deleted = self._delete_from_redis(learning_id)

        if qdrant_deleted or redis_deleted:
            logger.debug(
                "Deleted learning %s (qdrant=%s, redis=%s)",
                learning_id,
                qdrant_deleted,
                redis_deleted,
            )
            return True

        logger.warning(
            "Failed to delete learning %s from all backends",
            learning_id,
        )
        return False

    def _delete_from_qdrant(self, learning_id: str) -> bool:
        """Delete a learning point from Qdrant.

        Args:
            learning_id: The record_id used to derive the Qdrant point ID

        Returns:
            True if Qdrant deletion succeeded
        """
        qdrant_client = self._get_qdrant_client()
        if qdrant_client is None:
            return False

        try:
            point_id = hashlib.sha256(learning_id.encode("utf-8")).hexdigest()[:32]
            qdrant_client.delete(
                collection_name=self.qdrant_collection,
                points_selector={"points": [point_id]},
            )
            logger.debug("Deleted learning from Qdrant: %s", learning_id)
            return True
        except Exception as e:
            logger.warning(
                "Qdrant delete failed for %s: %s",
                learning_id,
                e,
            )
            return False

    def _delete_from_redis(self, learning_id: str) -> bool:
        """Delete learning records from Redis fallback.

        Since we don't know the record_type at delete time, this method
        attempts to delete both prediction and outcome keys.

        Args:
            learning_id: The record_id of the learning

        Returns:
            True if any Redis key was deleted
        """
        if self._redis_client is None:
            return False

        try:
            deleted_any = False
            for record_type in ("prediction", "outcome"):
                key = f"{REDIS_LEARNING_PREFIX}:{record_type}:{learning_id}"
                result = self._redis_client.delete(key)
                if result:
                    deleted_any = True
            return deleted_any
        except Exception as e:
            logger.warning(
                "Redis delete failed for %s: %s",
                learning_id,
                e,
            )
            return False

    def get_learning(self, learning_id: str) -> LearningRecord | None:
        """Retrieve a learning record from Qdrant by its record_id.

        This method enables write-back verification to confirm that data
        was actually persisted to Qdrant.

        Args:
            learning_id: The record_id of the learning to retrieve

        Returns:
            LearningRecord if found, None otherwise
        """
        qdrant_client = self._get_qdrant_client()
        if qdrant_client is None:
            logger.debug("Qdrant unavailable for get_learning: %s", learning_id)
            return None

        try:
            point_id = hashlib.sha256(learning_id.encode("utf-8")).hexdigest()[:32]

            result = qdrant_client.retrieve(
                collection_name=self.qdrant_collection,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )

            if not result:
                logger.debug("Learning not found in Qdrant: %s", learning_id)
                return None

            point = result[0]
            payload = point.payload

            if payload is None:
                return None

            # Reconstruct LearningRecord from payload
            record = LearningRecord(
                record_id=payload.get("record_id", learning_id),
                record_type=payload.get("record_type", "unknown"),
                content=payload.get("content", ""),
                metadata=payload.get("metadata", {}),
                created_at=(
                    datetime.fromisoformat(payload["created_at"])
                    if "created_at" in payload
                    else datetime.now(UTC)
                ),
            )

            logger.debug(
                "Retrieved learning from Qdrant: %s (%s)",
                record.record_id,
                record.record_type,
            )
            return record

        except Exception as e:
            logger.warning(
                "Failed to retrieve learning %s from Qdrant: %s",
                learning_id,
                e,
            )
            return None


# Module-level convenience instance for simple usage
_default_store: LearningStore | None = None


def get_learning_store() -> LearningStore:
    """Get or create the default LearningStore instance.

    Returns:
        A singleton LearningStore instance
    """
    global _default_store
    if _default_store is None:
        _default_store = LearningStore()
    return _default_store
