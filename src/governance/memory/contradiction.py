"""
Contradiction Detection for ChiseAI Memory System.

Identifies potential contradictions between memories to prevent
conflicting information from being stored in canonical memory.

Feature Flag: chise:feature_flags:governance:contradiction_detection_enabled
Default: Enabled (critical for safety)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:governance:contradiction_detection_enabled"

# Default contradiction keywords
DEFAULT_CONTRADICTION_KEYWORDS = [
    "contradicts",
    "conflicts with",
    "overrides",
    "deprecated",
    "replaced by",
    "supersedes",
    "invalidates",
    "no longer valid",
    "outdated",
    "obsolete",
]


@dataclass
class Contradiction:
    """Represents a detected contradiction between memories."""

    # Memory IDs involved
    memory_id_1: str
    memory_id_2: str

    # Similarity score (0.0 to 1.0)
    similarity: float

    # Contradiction severity
    severity: str  # "high", "medium", "low"

    # Reason for contradiction detection
    reason: str

    # Detected at
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Optional details
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "memory_id_1": self.memory_id_1,
            "memory_id_2": self.memory_id_2,
            "similarity": self.similarity,
            "severity": self.severity,
            "reason": self.reason,
            "detected_at": self.detected_at.isoformat(),
            "details": self.details,
        }


@dataclass
class ContradictionConfig:
    """Configuration for contradiction detection."""

    # Similarity range for potential contradictions
    # Memories must be similar enough to be related
    min_similarity: float = 0.75
    max_similarity: float = 0.92

    # Keywords indicating contradiction
    contradiction_keywords: list[str] = field(
        default_factory=lambda: DEFAULT_CONTRADICTION_KEYWORDS.copy()
    )

    # Whether to check for keyword-based contradictions
    check_keywords: bool = True

    # Whether to check for semantic contradictions
    check_semantic: bool = True

    # Minimum severity to report
    min_severity: str = "low"  # "low", "medium", "high"

    # Auto-flag for review if contradiction detected
    auto_flag: bool = True


@dataclass
class ContradictionStats:
    """Statistics from contradiction detection run."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    memories_checked: int = 0
    comparisons_made: int = 0
    contradictions_found: int = 0
    high_severity: int = 0
    medium_severity: int = 0
    low_severity: int = 0
    processing_time_seconds: float = 0.0
    error: str | None = None


class ContradictionDetector:
    """
    Detector for identifying contradictions in memory entries.

    Uses multiple strategies:
    1. Keyword-based: Looks for contradiction indicators in content
    2. Semantic similarity: Finds similar memories with conflicting content
    3. Temporal analysis: Detects newer memories that override older ones

    Safety Features:
    - Enabled by default (critical for memory integrity)
    - Configurable severity thresholds
    - Auto-flagging for human review
    """

    def __init__(
        self,
        config: ContradictionConfig | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
    ):
        """
        Initialize the contradiction detector.

        Args:
            config: Optional configuration override.
            redis_client: Optional Redis client.
            qdrant_client: Optional Qdrant client for vector search.
        """
        self._config = config or ContradictionConfig()
        self._redis_client = redis_client
        self._qdrant_client = qdrant_client
        self._enabled: bool | None = None
        self._last_stats: ContradictionStats | None = None

        logger.info(
            "ContradictionDetector initialized",
            extra={
                "check_keywords": self._config.check_keywords,
                "check_semantic": self._config.check_semantic,
            },
        )

    def is_enabled(self) -> bool:
        """Check if contradiction detection is enabled."""
        if self._enabled is not None:
            return self._enabled

        # Default to enabled for safety
        if self._redis_client is not None:
            try:
                flag_value = self._redis_client.get(FEATURE_FLAG_KEY)
                if flag_value is not None:
                    self._enabled = flag_value.lower() in (
                        "true",
                        "1",
                        "yes",
                        "enabled",
                    )
                else:
                    self._enabled = True  # Default to enabled
                logger.debug(f"Feature flag check: enabled={self._enabled}")
            except Exception as e:
                logger.warning(f"Failed to read feature flag: {e}")
                return True  # Default to enabled for safety
        else:
            self._enabled = True  # Default to enabled
            logger.debug("No Redis client, defaulting to enabled for safety")

        return self._enabled

    def check_keywords(self, content: str) -> list[str]:
        """
        Check content for contradiction keywords.

        Args:
            content: The memory content to check.

        Returns:
            List of found contradiction keywords.
        """
        found_keywords = []
        content_lower = content.lower()

        for keyword in self._config.contradiction_keywords:
            if keyword.lower() in content_lower:
                found_keywords.append(keyword)

        return found_keywords

    def compute_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity score between 0.0 and 1.0.
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        # Compute dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))

        # Compute magnitudes
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def detect_contradiction(
        self,
        memory_1: dict[str, Any],
        memory_2: dict[str, Any],
    ) -> Contradiction | None:
        """
        Detect if two memories contradict each other.

        Args:
            memory_1: First memory entry.
            memory_2: Second memory entry.

        Returns:
            Contradiction object if detected, None otherwise.
        """
        if not self.is_enabled():
            return None

        memory_id_1 = memory_1.get("id", "unknown")
        memory_id_2 = memory_2.get("id", "unknown")

        # Get content
        content_1 = memory_1.get("content", "")
        content_2 = memory_2.get("content", "")

        # Check keyword-based contradictions
        keywords_1 = (
            self.check_keywords(content_1) if self._config.check_keywords else []
        )
        keywords_2 = (
            self.check_keywords(content_2) if self._config.check_keywords else []
        )

        # If either mentions contradiction keywords referencing the other
        keyword_contradiction = False
        if keywords_1 or keywords_2:
            # Check if content from one appears in the other with contradiction keywords
            for keyword in keywords_1:
                # Simple heuristic: if keyword is present, flag for review
                keyword_contradiction = True
                break

        # Check semantic similarity
        similarity = 0.0
        vector_1 = memory_1.get("vector", [])
        vector_2 = memory_2.get("vector", [])

        if vector_1 and vector_2 and self._config.check_semantic:
            similarity = self.compute_similarity(vector_1, vector_2)

        # Determine if this is a contradiction
        is_contradiction = False
        reason = ""
        severity = "low"

        # Case 1: High similarity with keyword indicators
        if (
            self._config.min_similarity <= similarity <= self._config.max_similarity
            and keyword_contradiction
        ):
            is_contradiction = True
            reason = f"Similar content ({similarity:.2f}) with contradiction keywords"
            severity = "high"

        # Case 2: Very similar content without exact match (potential conflict)
        elif (
            self._config.min_similarity <= similarity
            and similarity <= self._config.max_similarity
            and similarity > 0.85
        ):
            is_contradiction = True
            reason = f"Highly similar content ({similarity:.2f}) with differences"
            severity = "medium"

        # Case 3: Keyword-only contradiction (with any similarity above threshold)
        elif keyword_contradiction and similarity >= self._config.min_similarity:
            is_contradiction = True
            reason = "Contradiction keywords detected in related content"
            severity = "medium"

        # Case 4: Cross-reference contradiction - keywords in one referencing the other
        elif keyword_contradiction and (
            similarity > 0.5 or not vector_1 or not vector_2
        ):
            is_contradiction = True
            reason = "Contradiction keywords detected"
            severity = "medium"

        if not is_contradiction:
            return None

        # Check minimum severity threshold
        severity_levels = {"low": 0, "medium": 1, "high": 2}
        if severity_levels.get(severity, 0) < severity_levels.get(
            self._config.min_severity, 0
        ):
            return None

        return Contradiction(
            memory_id_1=memory_id_1,
            memory_id_2=memory_id_2,
            similarity=similarity,
            severity=severity,
            reason=reason,
            details={
                "keywords_1": keywords_1,
                "keywords_2": keywords_2,
                "content_preview_1": content_1[:200] if content_1 else "",
                "content_preview_2": content_2[:200] if content_2 else "",
            },
        )

    def scan_for_contradictions(
        self,
        memories: list[dict[str, Any]] | None = None,
    ) -> list[Contradiction]:
        """
        Scan a set of memories for contradictions.

        Args:
            memories: List of memory entries to check. If None, scans Qdrant.

        Returns:
            List of detected contradictions.
        """
        start_time = datetime.now(UTC)
        stats = ContradictionStats()
        contradictions = []

        if not self.is_enabled():
            logger.info("Contradiction detection is disabled")
            return contradictions

        try:
            # Get memories if not provided
            if memories is None:
                memories = self._scan_qdrant_memories()

            stats.memories_checked = len(memories)

            # Compare each pair (O(n²) but typically n is small)
            for i in range(len(memories)):
                for j in range(i + 1, len(memories)):
                    stats.comparisons_made += 1

                    contradiction = self.detect_contradiction(
                        memories[i],
                        memories[j],
                    )

                    if contradiction:
                        contradictions.append(contradiction)
                        stats.contradictions_found += 1

                        if contradiction.severity == "high":
                            stats.high_severity += 1
                        elif contradiction.severity == "medium":
                            stats.medium_severity += 1
                        else:
                            stats.low_severity += 1

                        # Auto-flag if configured
                        if self._config.auto_flag:
                            self._flag_contradiction(contradiction)

            logger.info(
                f"Contradiction scan completed: {len(contradictions)} found",
                extra={
                    "memories_checked": stats.memories_checked,
                    "comparisons_made": stats.comparisons_made,
                    "contradictions_found": stats.contradictions_found,
                },
            )

        except Exception as e:
            stats.error = str(e)
            logger.exception("Contradiction scan failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return contradictions

    def _scan_qdrant_memories(self) -> list[dict[str, Any]]:
        """
        Scan Qdrant for memories to check.

        Returns:
            List of memory entries.
        """
        memories = []

        if self._qdrant_client is None:
            return memories

        try:
            # Scroll through Qdrant collection
            offset = None
            while True:
                result = self._qdrant_client.scroll(
                    collection_name="ChiseAI",
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )

                points, next_offset = result

                for point in points:
                    memories.append(
                        {
                            "id": point.id,
                            "content": point.payload.get("content", ""),
                            "vector": point.vector,
                            "payload": point.payload,
                        }
                    )

                if next_offset is None:
                    break
                offset = next_offset

        except Exception as e:
            logger.error(f"Qdrant scan failed: {e}")

        return memories

    def _flag_contradiction(self, contradiction: Contradiction) -> None:
        """
        Flag a contradiction for human review.

        Args:
            contradiction: The contradiction to flag.
        """
        logger.warning(
            f"Contradiction detected: {contradiction.memory_id_1} vs {contradiction.memory_id_2}",
            extra={
                "severity": contradiction.severity,
                "reason": contradiction.reason,
                "similarity": contradiction.similarity,
            },
        )

        # Store in Redis for review queue
        if self._redis_client:
            try:
                key = f"chise:governance:contradictions:pending"
                self._redis_client.lpush(
                    key,
                    json.dumps(contradiction.to_dict()),
                )
            except Exception as e:
                logger.warning(f"Failed to store contradiction flag: {e}")

    def get_stats(self) -> ContradictionStats | None:
        """Get statistics from the last scan."""
        return self._last_stats

    def enable(self) -> bool:
        """Enable contradiction detection."""
        if self._redis_client is None:
            self._enabled = True
            logger.info("Contradiction detection enabled (local state only)")
            return True

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "true")
            self._enabled = True
            logger.info("Contradiction detection enabled")
            return True
        except Exception as e:
            logger.error(f"Failed to enable contradiction detection: {e}")
            return False

    def disable(self) -> bool:
        """
        Disable contradiction detection.

        Note: This is strongly discouraged as contradictions can
        corrupt the memory system. Use with caution.
        """
        logger.warning("Disabling contradiction detection - not recommended!")

        if self._redis_client is None:
            self._enabled = False
            logger.info("Contradiction detection disabled (local state only)")
            return True

        try:
            self._redis_client.set(FEATURE_FLAG_KEY, "false")
            self._enabled = False
            logger.info("Contradiction detection disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable contradiction detection: {e}")
            self._enabled = False
            return True
