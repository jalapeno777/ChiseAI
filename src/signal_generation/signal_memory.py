"""Signal memory persistence to Qdrant with vector embeddings.

Provides the SignalMemory class for persisting generated trading signals
to Qdrant with vector embeddings for similarity search. Supports signal
outcome tracking (predicted vs actual price movement) and TTL-based cleanup.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    DatetimeRange,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    Range,
    VectorParams,
)

from signal_generation.models import Signal

logger = logging.getLogger(__name__)

# --- Constants ---
COLLECTION_NAME = "signal_memory"
VECTOR_DIMENSIONS = 384
DEFAULT_QDRANT_HOST = "host.docker.internal"
DEFAULT_QDRANT_PORT = 6334
DEFAULT_TIMEOUT = 10
DEFAULT_TTL_DAYS = 90
DEFAULT_BATCH_SIZE = 100


class SignalOutcome(Enum):
    """Outcome of a signal relative to predicted direction."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    NEUTRAL = "neutral"
    PENDING = "pending"


def _deterministic_embedding(
    text: str, dimensions: int = VECTOR_DIMENSIONS
) -> list[float]:
    """Generate deterministic embedding using SHA-256 hash.

    Produces consistent vectors for the same input without requiring
    ML dependencies. Values are in the range [-1.0, 1.0].

    Args:
        text: Input text to embed.
        dimensions: Number of dimensions for the vector.

    Returns:
        List of float values representing the embedding.
    """
    if not text:
        return [0.0] * dimensions

    values: list[float] = []
    data = text.encode("utf-8")
    for i in range(dimensions):
        digest = hashlib.sha256(data + i.to_bytes(4, "little")).digest()
        raw = int.from_bytes(digest[:4], "little")
        values.append((raw % 20000) / 10000 - 1.0)
    return values


def _create_embedding(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    """Create embedding vector, preferring sentence-transformers if available.

    Falls back to deterministic hash-based embedding when ML dependencies
    are not available.

    Args:
        text: Input text to embed.
        dimensions: Number of dimensions for the vector.

    Returns:
        List of float values representing the embedding.
    """
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401

        model = SentenceTransformer("all-MiniLM-L6-v2")
        vector = model.encode(text, convert_to_numpy=True).tolist()
        if len(vector) == dimensions:
            return [float(v) for v in vector]
    except Exception:
        pass

    return _deterministic_embedding(text, dimensions=dimensions)


def _signal_to_text(signal: Signal) -> str:
    """Convert signal to text representation for embedding.

    Creates a canonical text representation that captures the key
    features of a signal for vector similarity search.

    Args:
        signal: The Signal instance to convert.

    Returns:
        Canonical text representation of the signal.
    """
    factors_str = ", ".join(
        f.get("name", "unknown") for f in signal.contributing_factors[:10]
    )
    breakdown_str = json.dumps(signal.signal_breakdown, sort_keys=True, default=str)
    return (
        f"{signal.token} {signal.direction.value} "
        f"confidence={signal.confidence:.4f} "
        f"score={signal.base_score:.2f} "
        f"timeframe={signal.timeframe} "
        f"status={signal.status.value} "
        f"factors=[{factors_str}] "
        f"breakdown={breakdown_str}"
    )


def _build_payload(signal: Signal, ttl_days: int) -> dict[str, Any]:
    """Build Qdrant payload from a Signal instance.

    Args:
        signal: The Signal to convert.
        ttl_days: TTL in days for expiry calculation.

    Returns:
        Dictionary suitable for Qdrant point payload.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=ttl_days)

    return {
        "token": signal.token,
        "direction": signal.direction.value,
        "confidence": signal.confidence,
        "base_score": signal.base_score,
        "timestamp": signal.timestamp.isoformat(),
        "status": signal.status.value,
        "timeframe": signal.timeframe,
        "signal_id": signal.signal_id,
        "outcome": SignalOutcome.PENDING.value,
        "actual_direction": None,
        "actual_price_change_pct": None,
        "stored_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "contributing_factors": signal.contributing_factors,
        "signal_breakdown": signal.signal_breakdown,
        "generation_latency_ms": signal.generation_latency_ms,
        "stop_loss": signal.stop_loss,
        "risk_reward_ratio": signal.risk_reward_ratio,
    }


class SignalMemory:
    """Persistent signal memory backed by Qdrant.

    Stores generated signals as vector-embedded points in Qdrant,
    enabling similarity search across historical signals. Tracks
    signal outcomes (predicted vs actual price movement) and
    supports TTL-based cleanup of old signals.

    Args:
        qdrant_host: Qdrant server hostname.
        qdrant_port: Qdrant server port.
        timeout: Connection timeout in seconds.
        ttl_days: Default TTL for stored signals in days.
        vector_dimensions: Dimensionality of embedding vectors.
    """

    def __init__(
        self,
        qdrant_host: str = DEFAULT_QDRANT_HOST,
        qdrant_port: int = DEFAULT_QDRANT_PORT,
        timeout: int = DEFAULT_TIMEOUT,
        ttl_days: int = DEFAULT_TTL_DAYS,
        vector_dimensions: int = VECTOR_DIMENSIONS,
    ) -> None:
        self._qdrant_host = qdrant_host
        self._qdrant_port = qdrant_port
        self._timeout = timeout
        self._ttl_days = ttl_days
        self._vector_dimensions = vector_dimensions
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize and return the Qdrant client.

        Returns:
            Connected QdrantClient instance.
        """
        if self._client is None:
            self._client = QdrantClient(
                host=self._qdrant_host,
                port=self._qdrant_port,
                timeout=self._timeout,
            )
        return self._client

    def ensure_collection(self) -> bool:
        """Ensure the signal_memory collection exists in Qdrant.

        Creates the collection with appropriate vector configuration
        and payload indexes if it does not already exist.

        Returns:
            True if collection is ready, False on failure.
        """
        try:
            collections = self.client.get_collections()
            existing = [c.name for c in collections.collections]

            if COLLECTION_NAME not in existing:
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self._vector_dimensions,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created collection '%s'", COLLECTION_NAME)

                # Create payload indexes for filtering
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="token",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="direction",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="status",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="outcome",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="timestamp",
                    field_schema=PayloadSchemaType.DATETIME,
                )
                self.client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="expires_at",
                    field_schema=PayloadSchemaType.DATETIME,
                )
                logger.info("Created payload indexes for '%s'", COLLECTION_NAME)

            return True
        except Exception:
            logger.exception("Failed to ensure collection '%s'", COLLECTION_NAME)
            return False

    def store_signal(self, signal: Signal) -> str:
        """Persist a signal to Qdrant with vector embedding.

        Args:
            signal: The Signal instance to store.

        Returns:
            The point ID (signal_id) if stored successfully.

        Raises:
            ValueError: If signal has no signal_id.
            RuntimeError: If storage fails.
        """
        if not signal.signal_id:
            raise ValueError("Signal must have a signal_id to be stored")

        self.ensure_collection()

        text = _signal_to_text(signal)
        vector = _create_embedding(text, dimensions=self._vector_dimensions)
        payload = _build_payload(signal, self._ttl_days)

        point = PointStruct(
            id=signal.signal_id,
            vector=vector,
            payload=payload,
        )

        try:
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=[point],
            )
            logger.info(
                "Stored signal %s for %s (%s)",
                signal.signal_id,
                signal.token,
                signal.direction.value,
            )
            return signal.signal_id
        except Exception:
            logger.exception("Failed to store signal %s", signal.signal_id)
            raise RuntimeError(f"Failed to store signal {signal.signal_id}") from None

    def store_signals(self, signals: list[Signal]) -> list[str]:
        """Batch persist multiple signals to Qdrant.

        Args:
            signals: List of Signal instances to store.

        Returns:
            List of stored signal IDs.

        Raises:
            ValueError: If any signal has no signal_id.
            RuntimeError: If batch storage fails.
        """
        if not signals:
            return []

        self.ensure_collection()

        points: list[PointStruct] = []
        for signal in signals:
            if not signal.signal_id:
                raise ValueError("All signals must have a signal_id to be stored")

            text = _signal_to_text(signal)
            vector = _create_embedding(text, dimensions=self._vector_dimensions)
            payload = _build_payload(signal, self._ttl_days)

            points.append(
                PointStruct(
                    id=signal.signal_id,
                    vector=vector,
                    payload=payload,
                )
            )

        # Upsert in batches
        stored_ids: list[str] = []
        for i in range(0, len(points), DEFAULT_BATCH_SIZE):
            batch = points[i : i + DEFAULT_BATCH_SIZE]
            try:
                self.client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=batch,
                )
                for p in batch:
                    stored_ids.append(str(p.id))
            except Exception:
                logger.exception("Failed to store batch starting at index %d", i)
                raise RuntimeError(
                    f"Failed to store signal batch starting at index {i}"
                ) from None

        logger.info("Stored %d signals in batch", len(stored_ids))
        return stored_ids

    def record_outcome(
        self,
        signal_id: str,
        actual_price_change_pct: float,
    ) -> dict[str, Any] | None:
        """Record the actual outcome for a stored signal.

        Compares the predicted direction against the actual price
        movement and updates the signal's outcome status.

        Args:
            signal_id: The signal ID to update.
            actual_price_change_pct: Actual price change percentage
                (positive = up, negative = down).

        Returns:
            Updated payload dict if found, None otherwise.
        """
        try:
            points = self.client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[signal_id],
                with_payload=True,
            )
        except Exception:
            logger.exception("Failed to retrieve signal %s", signal_id)
            return None

        if not points:
            logger.warning("Signal %s not found for outcome recording", signal_id)
            return None

        payload = points[0].payload
        if payload is None:
            return None

        predicted_direction = payload.get("direction", "neutral")

        # Determine outcome based on predicted direction vs actual movement
        if actual_price_change_pct > 0.1:
            actual_direction = "long"
        elif actual_price_change_pct < -0.1:
            actual_direction = "short"
        else:
            actual_direction = "neutral"

        if predicted_direction == actual_direction:
            outcome = SignalOutcome.CORRECT.value
        elif actual_direction == "neutral":
            outcome = SignalOutcome.NEUTRAL.value
        else:
            outcome = SignalOutcome.INCORRECT.value

        now_iso = datetime.now(UTC).isoformat()
        update_payload: dict[str, Any] = {
            "outcome": outcome,
            "actual_direction": actual_direction,
            "actual_price_change_pct": actual_price_change_pct,
            "outcome_recorded_at": now_iso,
        }

        try:
            self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update_payload,
                points=[signal_id],
            )
            logger.info(
                "Recorded outcome %s for signal %s (predicted=%s, actual=%s, change=%.2f%%)",
                outcome,
                signal_id,
                predicted_direction,
                actual_direction,
                actual_price_change_pct,
            )

            # Return merged payload
            merged: dict[str, Any] = dict(payload)
            merged.update(update_payload)
            return merged
        except Exception:
            logger.exception("Failed to update outcome for signal %s", signal_id)
            return None

    def find_similar_signals(
        self,
        signal: Signal,
        limit: int = 10,
        score_threshold: float = 0.7,
        token_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find similar historical signals using vector similarity search.

        Args:
            signal: Query signal to find similar matches for.
            limit: Maximum number of results.
            score_threshold: Minimum similarity score (0.0-1.0).
            token_filter: Optional token to filter results by.

        Returns:
            List of matching signal payloads with similarity scores.
        """
        self.ensure_collection()

        text = _signal_to_text(signal)
        vector = _create_embedding(text, dimensions=self._vector_dimensions)

        conditions: list[FieldCondition] = []

        if token_filter:
            conditions.append(
                FieldCondition(key="token", match=MatchValue(value=token_filter))
            )

        # Exclude expired signals using DatetimeRange
        now = datetime.now(UTC)
        conditions.append(
            FieldCondition(
                key="expires_at",
                range=DatetimeRange(gte=now),
            )
        )

        query_filter: Filter | None = Filter(must=conditions) if conditions else None

        try:
            response = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
            )

            similar: list[dict[str, Any]] = []
            for scored_point in response.points:
                entry: dict[str, Any] = {
                    "signal_id": str(scored_point.id),
                    "score": scored_point.score,
                    "payload": scored_point.payload if scored_point.payload else {},
                }
                similar.append(entry)

            logger.info(
                "Found %d similar signals for %s (threshold=%.2f)",
                len(similar),
                signal.signal_id,
                score_threshold,
            )
            return similar

        except UnexpectedResponse:
            logger.warning(
                "Collection '%s' not found during similarity search",
                COLLECTION_NAME,
            )
            return []
        except Exception:
            logger.exception("Similarity search failed for signal %s", signal.signal_id)
            return []

    def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        """Retrieve a specific signal by ID.

        Args:
            signal_id: The signal ID to retrieve.

        Returns:
            Signal payload dict if found, None otherwise.
        """
        try:
            points = self.client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[signal_id],
                with_payload=True,
                with_vectors=False,
            )
            if points and points[0].payload:
                return dict(points[0].payload)
            return None
        except Exception:
            logger.exception("Failed to retrieve signal %s", signal_id)
            return None

    def search_signals(
        self,
        token: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        outcome: str | None = None,
        min_confidence: float | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search signals with metadata filters.

        Provides flexible retrieval of historical signals based on
        multiple filter criteria.

        Args:
            token: Filter by token (e.g., "BTC/USDT").
            direction: Filter by direction ("long", "short", "neutral").
            status: Filter by status ("actionable", "logged_only", etc.).
            outcome: Filter by outcome ("correct", "incorrect", etc.).
            min_confidence: Minimum confidence threshold.
            since: Only include signals after this timestamp.
            until: Only include signals before this timestamp.
            limit: Maximum number of results.

        Returns:
            List of matching signal payloads.
        """
        self.ensure_collection()

        conditions: list[FieldCondition] = []

        if token:
            conditions.append(
                FieldCondition(key="token", match=MatchValue(value=token))
            )
        if direction:
            conditions.append(
                FieldCondition(key="direction", match=MatchValue(value=direction))
            )
        if status:
            conditions.append(
                FieldCondition(key="status", match=MatchValue(value=status))
            )
        if outcome:
            conditions.append(
                FieldCondition(key="outcome", match=MatchValue(value=outcome))
            )
        if min_confidence is not None:
            conditions.append(
                FieldCondition(
                    key="confidence",
                    range=Range(gte=min_confidence),
                )
            )
        if since is not None:
            conditions.append(
                FieldCondition(
                    key="timestamp",
                    range=DatetimeRange(gte=since),
                )
            )
        if until is not None:
            conditions.append(
                FieldCondition(
                    key="timestamp",
                    range=DatetimeRange(lte=until),
                )
            )

        # Exclude expired signals
        now = datetime.now(UTC)
        conditions.append(
            FieldCondition(
                key="expires_at",
                range=DatetimeRange(gte=now),
            )
        )

        query_filter = Filter(must=conditions) if conditions else None

        try:
            # Use scroll for large result sets
            offset = None
            all_results: list[dict[str, Any]] = []
            collected = 0

            while collected < limit:
                batch_size = min(DEFAULT_BATCH_SIZE, limit - collected)
                results, offset = self.client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=query_filter,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in results:
                    if point.payload:
                        all_results.append(dict(point.payload))
                    collected += 1

                if not offset or collected >= limit:
                    break

            return all_results[:limit]

        except UnexpectedResponse:
            logger.warning(
                "Collection '%s' not found during signal search", COLLECTION_NAME
            )
            return []
        except Exception:
            logger.exception("Signal search failed")
            return []

    def cleanup_expired(self, dry_run: bool = False) -> int:
        """Remove expired signals from the collection.

        Scans for signals whose expiry time has passed and removes them.

        Args:
            dry_run: If True, count expired signals without deleting.

        Returns:
            Number of signals removed (or that would be removed if dry_run).
        """
        self.ensure_collection()

        now = datetime.now(UTC)

        try:
            # Find expired points using scroll with DatetimeRange
            conditions = [
                FieldCondition(
                    key="expires_at",
                    range=DatetimeRange(lt=now),
                )
            ]
            query_filter = Filter(must=conditions)

            offset = None
            expired_ids: list[str] = []

            while True:
                results, offset = self.client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=query_filter,
                    limit=DEFAULT_BATCH_SIZE,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )

                for point in results:
                    expired_ids.append(str(point.id))

                if not offset:
                    break

            count = len(expired_ids)

            if dry_run:
                logger.info(
                    "Dry run: would delete %d expired signals from '%s'",
                    count,
                    COLLECTION_NAME,
                )
                return count

            if expired_ids:
                # Delete in batches
                for i in range(0, len(expired_ids), DEFAULT_BATCH_SIZE):
                    batch = expired_ids[i : i + DEFAULT_BATCH_SIZE]
                    self.client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=PointIdsList(points=batch),
                    )

                logger.info(
                    "Deleted %d expired signals from '%s'",
                    count,
                    COLLECTION_NAME,
                )

            return count

        except UnexpectedResponse:
            logger.warning("Collection '%s' not found during cleanup", COLLECTION_NAME)
            return 0
        except Exception:
            logger.exception("Cleanup of expired signals failed")
            return 0

    def get_signal_stats(
        self,
        token: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Get aggregate statistics for stored signals.

        Computes accuracy metrics, direction distribution, and
        other summary statistics.

        Args:
            token: Optional token filter.
            since: Optional start time filter.

        Returns:
            Dict with statistics including accuracy, counts, distributions.
        """
        signals = self.search_signals(
            token=token,
            since=since,
            limit=10000,
        )

        if not signals:
            return {
                "total": 0,
                "correct": 0,
                "incorrect": 0,
                "neutral": 0,
                "pending": 0,
                "accuracy": 0.0,
                "avg_confidence": 0.0,
                "direction_distribution": {},
                "outcome_distribution": {},
            }

        total = len(signals)
        correct = sum(1 for s in signals if s.get("outcome") == "correct")
        incorrect = sum(1 for s in signals if s.get("outcome") == "incorrect")
        neutral_outcome = sum(1 for s in signals if s.get("outcome") == "neutral")
        pending = sum(1 for s in signals if s.get("outcome") == "pending")

        judged = correct + incorrect
        accuracy = correct / judged if judged > 0 else 0.0

        confidences = [s.get("confidence", 0.0) for s in signals]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Direction distribution
        direction_counts: dict[str, int] = {}
        for s in signals:
            d = s.get("direction", "unknown")
            direction_counts[d] = direction_counts.get(d, 0) + 1

        # Outcome distribution
        outcome_counts: dict[str, int] = {}
        for s in signals:
            o = s.get("outcome", "unknown")
            outcome_counts[o] = outcome_counts.get(o, 0) + 1

        return {
            "total": total,
            "correct": correct,
            "incorrect": incorrect,
            "neutral": neutral_outcome,
            "pending": pending,
            "accuracy": round(accuracy, 4),
            "avg_confidence": round(avg_confidence, 4),
            "direction_distribution": direction_counts,
            "outcome_distribution": outcome_counts,
        }
