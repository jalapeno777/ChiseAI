"""Expansion engine for generating new beliefs from existing ones.

This module provides the core expansion logic that generates new beliefs
through various expansion strategies like derivation, generalization,
specialization, analogy, and inference.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from ..belief_expansion import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TIME_LIMIT_SECONDS,
    BELIEF_EXPANSION_COLLECTION,
    ExpansionConfig,
    ExpansionProgress,
    ExpansionResult,
    ExpansionType,
    ExpandedBelief,
)

logger = logging.getLogger(__name__)


class BeliefExpander:
    """Generates new beliefs from existing ones through expansion strategies."""

    def __init__(
        self,
        config: ExpansionConfig | None = None,
        qdrant_client: Any | None = None,
    ):
        """Initialize the belief expander.

        Args:
            config: Expansion configuration (uses defaults if None)
            qdrant_client: Optional Qdrant client for storage
        """
        self.config = config or ExpansionConfig()
        self._qdrant_client = qdrant_client
        self._qdrant_initialized = False

    def _get_qdrant_client(self) -> Any | None:
        """Get or create Qdrant client with lazy initialization."""
        if self._qdrant_client is not None:
            return self._qdrant_client

        try:
            import os

            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams

            host = os.environ.get("QDRANT_HOST", "host.docker.internal")
            port = int(os.environ.get("QDRANT_PORT", "6333"))

            self._qdrant_client = QdrantClient(host=host, port=port, timeout=5)
            self._ensure_collection()
            return self._qdrant_client
        except Exception as e:
            logger.warning("Failed to connect to Qdrant: %s", e)
            return None

    def _ensure_collection(self) -> bool:
        """Ensure the expansion collection exists in Qdrant."""
        if self._qdrant_initialized or self._qdrant_client is None:
            return self._qdrant_initialized

        try:
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.config.qdrant_collection not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name=self.config.qdrant_collection,
                    vectors_config=VectorParams(
                        size=384,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    "Created Qdrant collection: %s",
                    self.config.qdrant_collection,
                )

            self._qdrant_initialized = True
            return True
        except Exception as e:
            logger.warning("Failed to ensure Qdrant collection: %s", e)
            return False

    def expand_belief(
        self,
        belief_id: str,
        statement: str,
        domain: str,
        confidence: float,
    ) -> list[ExpandedBelief]:
        """Generate expanded beliefs from a source belief.

        Args:
            belief_id: Source belief ID
            statement: Source belief statement
            domain: Belief domain
            confidence: Source belief confidence

        Returns:
            List of expanded beliefs
        """
        expansions: list[ExpandedBelief] = []

        # Check confidence threshold
        if confidence < self.config.min_confidence:
            logger.debug(
                "Belief %s confidence %f below threshold, skipping",
                belief_id,
                confidence,
            )
            return expansions

        # Generate expansions using different strategies
        for expansion_type in ExpansionType:
            if len(expansions) >= self.config.max_expansions_per_belief:
                break

            expanded = self._generate_expansion(
                belief_id, statement, domain, confidence, expansion_type
            )
            if expanded:
                # Apply relevance filtering
                if expanded.relevance_score >= self.config.min_relevance_score:
                    expansions.append(expanded)
                else:
                    logger.debug(
                        "Expansion %s relevance %f below threshold",
                        expanded.belief_id,
                        expanded.relevance_score,
                    )

        return expansions

    def _generate_expansion(
        self,
        belief_id: str,
        statement: str,
        domain: str,
        confidence: float,
        expansion_type: ExpansionType,
    ) -> ExpandedBelief | None:
        """Generate a single expansion of the given type.

        Args:
            belief_id: Source belief ID
            statement: Source belief statement
            domain: Belief domain
            confidence: Source belief confidence
            expansion_type: Type of expansion to generate

        Returns:
            ExpandedBelief or None if generation fails
        """
        # Generate derived statement based on expansion type
        derived_statement = self._derive_statement(statement, expansion_type)
        if not derived_statement:
            return None

        # Calculate relevance score based on semantic relationship
        relevance_score = self._calculate_relevance(statement, derived_statement)

        # Confidence is derived from source confidence with decay
        derived_confidence = confidence * 0.85

        return ExpandedBelief(
            belief_id=f"exp_{uuid.uuid4().hex[:12]}",
            statement=derived_statement,
            domain=domain,
            confidence=derived_confidence,
            source_belief_id=belief_id,
            expansion_type=expansion_type,
            relevance_score=relevance_score,
            metadata={
                "original_statement": statement,
                "generation_method": "rule_based_expansion",
            },
        )

    def _derive_statement(
        self, statement: str, expansion_type: ExpansionType
    ) -> str | None:
        """Derive a new statement based on the expansion type.

        Args:
            statement: Original belief statement
            expansion_type: Type of derivation

        Returns:
            Derived statement or None
        """
        # Simple rule-based derivation
        # In production, this would use LLM or more sophisticated methods

        if expansion_type == ExpansionType.DERIVATION:
            # Extract implications
            if m := re.search(
                r"(.*?)(therefore|thus|hence|implies|consequently)(.*)",
                statement,
                re.IGNORECASE,
            ):
                return f"Because {m.group(1).strip().rstrip('.')}, {m.group(3).strip().lstrip('.')}".strip()

        elif expansion_type == ExpansionType.GENERALIZATION:
            # Make statement more general
            replacements = [
                (r"\bsome\b", "many"),
                (r"\boften\b", "frequently"),
                (r"\bsometimes\b", "often"),
            ]
            result = statement
            for pattern, replacement in replacements:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            if result != statement:
                return result

        elif expansion_type == ExpansionType.SPECIALIZATION:
            # Make statement more specific
            replacements = [
                (r"\bmany\b", "some"),
                (r"\bfrequently\b", "often"),
                (r"\boften\b", "sometimes"),
            ]
            result = statement
            for pattern, replacement in replacements:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            if result != statement:
                return result

        elif expansion_type == ExpansionType.ANALOGY:
            # Create analogical statement
            if re.search(r"\b(is|are|was|were)\b", statement):
                return re.sub(
                    r"(.*?\b(is|are|was|were)\b\s*)(.*)", r"\1Similarly, \3", statement
                )

        elif expansion_type == ExpansionType.INFERENCE:
            # Create logical inference
            if " and " in statement.lower():
                parts = statement.split(" and ", 1)
                if len(parts) == 2:
                    return f"Either {parts[0].strip().rstrip('.')} or {parts[1].strip().lstrip('.')}"

        return None

    def _calculate_relevance(self, original: str, derived: str) -> float:
        """Calculate relevance score between original and derived statements.

        Args:
            original: Original statement
            derived: Derived statement

        Returns:
            Relevance score between 0 and 1
        """
        # Simple word overlap-based relevance
        original_words = set(re.findall(r"\w+", original.lower()))
        derived_words = set(re.findall(r"\w+", derived.lower()))

        if not original_words or not derived_words:
            return 0.0

        # Calculate Jaccard similarity
        intersection = original_words & derived_words
        union = original_words | derived_words

        return len(intersection) / len(union) if union else 0.0

    def store_expansion(self, expansion: ExpandedBelief) -> bool:
        """Store an expanded belief in Qdrant.

        Args:
            expansion: The expanded belief to store

        Returns:
            True if storage succeeded
        """
        qdrant_client = self._get_qdrant_client()
        if qdrant_client is None:
            logger.warning("Qdrant unavailable, skipping storage")
            return False

        try:
            import hashlib

            point_id = hashlib.sha256(expansion.belief_id.encode("utf-8")).hexdigest()[
                :32
            ]

            qdrant_client.upsert(
                collection_name=self.config.qdrant_collection,
                points=[
                    {
                        "id": point_id,
                        "vector": self._generate_embedding(expansion.statement),
                        "payload": expansion.to_dict(),
                    }
                ],
            )
            logger.debug(
                "Stored expansion %s in Qdrant",
                expansion.belief_id,
            )
            return True
        except Exception as e:
            logger.warning("Failed to store expansion in Qdrant: %s", e)
            return False

    def _generate_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding vector from text.

        Args:
            text: Input text to embed

        Returns:
            List of float values representing the embedding
        """
        import hashlib

        dimensions = 384
        if not text:
            return [0.0] * dimensions

        values: list[float] = []
        data = text.encode("utf-8")
        for i in range(dimensions):
            digest = hashlib.sha256(data + i.to_bytes(4, "little")).digest()
            raw = int.from_bytes(digest[:4], "little")
            values.append((raw % 20000) / 10000 - 1.0)
        return values


def expand_beliefs(
    beliefs: list[dict[str, Any]],
    config: ExpansionConfig | None = None,
    qdrant_client: Any | None = None,
    progress_callback: Callable[[ExpansionProgress], None] | None = None,
) -> ExpansionResult:
    """Expand a list of beliefs with timeboxing and progress tracking.

    Args:
        beliefs: List of belief dictionaries with keys: belief_id, statement, domain, confidence
        config: Expansion configuration
        qdrant_client: Optional Qdrant client for storage
        progress_callback: Optional callback for progress updates

    Returns:
        ExpansionResult with generated beliefs and progress information
    """
    expander = BeliefExpander(config=config, qdrant_client=qdrant_client)
    config = config or ExpansionConfig()

    progress = ExpansionProgress(total_beliefs=len(beliefs))
    expanded_beliefs: list[ExpandedBelief] = []
    start_time = time.time()

    try:
        for belief in beliefs:
            # Check time limit
            if not progress.is_within_time_limit(config):
                progress.timed_out = True
                logger.info(
                    "Belief expansion timed out after %f seconds",
                    progress.elapsed_seconds(),
                )
                break

            # Process belief
            expansions = expander.expand_belief(
                belief_id=belief["belief_id"],
                statement=belief["statement"],
                domain=belief["domain"],
                confidence=belief["confidence"],
            )

            progress.processed_beliefs += 1
            progress.expansions_generated += len(expansions)

            for expansion in expansions:
                # Store in Qdrant
                if expander.store_expansion(expansion):
                    progress.expansions_stored += 1
                    expanded_beliefs.append(expansion)
                else:
                    progress.expansions_filtered += 1

            # Report progress
            if progress_callback:
                progress_callback(progress)

    except Exception as e:
        progress.error_message = str(e)
        logger.exception("Error during belief expansion")

    progress.end_time = time.time()

    return ExpansionResult(
        success=progress.error_message is None
        and (progress.expansions_stored > 0 or not progress.timed_out),
        progress=progress,
        expanded_beliefs=expanded_beliefs,
        error=progress.error_message,
    )
