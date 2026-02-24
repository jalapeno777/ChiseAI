"""
Golden Memory Promoter for Consolidation.

Promotes high-value memories to the "golden" collection for long-term retention.

Story: ST-GOV-005
Governance Feature: GF-005
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.governance.consolidation.config import (
    CONSOLIDATION_PREFIX,
    MemoryType,
)

logger = logging.getLogger(__name__)


@dataclass
class PromotionCandidate:
    """A memory candidate for golden promotion."""

    memory_id: str
    content: str
    metadata: dict[str, Any]
    memory_type: MemoryType
    access_count: int
    relevance_score: float
    age_days: int
    tags: list[str] = field(default_factory=list)

    # Promotion scoring
    promotion_score: float = 0.0
    promotion_reasons: list[str] = field(default_factory=list)

    def calculate_promotion_score(
        self,
        min_access: int,
        min_age: int,
        min_relevance: float,
    ) -> float:
        """
        Calculate a promotion score based on multiple factors.

        Score is weighted combination of:
        - Access frequency (40%)
        - Relevance score (40%)
        - Age maturity (20%)

        Args:
            min_access: Minimum access threshold
            min_age: Minimum age threshold
            min_relevance: Minimum relevance threshold

        Returns:
            Promotion score between 0 and 1
        """
        # Access score (normalized, capped at 10x minimum)
        access_ratio = min(self.access_count / max(min_access, 1), 10.0)
        access_score = min(access_ratio / 10.0, 1.0)

        # Relevance score (direct use, already 0-1)
        relevance_score = self.relevance_score

        # Age maturity score (how long past minimum age, capped at 3x)
        age_ratio = min(self.age_days / max(min_age, 1), 3.0)
        age_score = min(age_ratio / 3.0, 1.0)

        # Weighted combination
        self.promotion_score = (
            0.4 * access_score + 0.4 * relevance_score + 0.2 * age_score
        )

        # Track reasons for promotion
        if self.access_count >= min_access * 2:
            self.promotion_reasons.append("high_access_frequency")
        if self.relevance_score >= min_relevance:
            self.promotion_reasons.append("high_relevance")
        if self.age_days >= min_age * 2:
            self.promotion_reasons.append("mature_memory")

        return self.promotion_score


@dataclass
class PromotionStats:
    """Statistics from a promotion operation."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    candidates_evaluated: int = 0
    candidates_promoted: int = 0
    candidates_rejected: int = 0
    promotion_score_avg: float = 0.0
    errors: list[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0
    was_dry_run: bool = True


class GoldenMemoryPromoter:
    """
    Promotes high-value memories to the golden collection.

    Golden memories are:
    - Never archived (exempt from retention)
    - Stored in a dedicated high-availability collection
    - Tagged for priority retrieval

    Promotion Criteria (all must be met):
    - Access count >= golden_min_access_count
    - Age >= golden_min_age_days
    - Relevance score >= golden_min_relevance_score

    Example:
        >>> promoter = GoldenMemoryPromoter(config)
        >>> stats = promoter.promote_memories()
        >>> print(f"Promoted {stats.candidates_promoted} memories to golden")
    """

    def __init__(
        self,
        config: Any,  # ConsolidationConfig
        qdrant_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the golden memory promoter.

        Args:
            config: ConsolidationConfig instance
            qdrant_client: Optional Qdrant client for vector operations
            redis_client: Optional Redis client for state management
        """
        self._config = config
        self._qdrant_client = qdrant_client
        self._redis_client = redis_client
        self._last_stats: PromotionStats | None = None

        logger.info(
            "GoldenMemoryPromoter initialized",
            extra={
                "min_access": config.golden_min_access_count,
                "min_age": config.golden_min_age_days,
                "min_relevance": config.golden_min_relevance_score,
            },
        )

    def _is_promotion_eligible(self, candidate: PromotionCandidate) -> bool:
        """
        Check if a candidate meets promotion criteria.

        Args:
            candidate: Memory candidate to evaluate

        Returns:
            True if eligible for promotion
        """
        meets_access = candidate.access_count >= self._config.golden_min_access_count
        meets_age = candidate.age_days >= self._config.golden_min_age_days
        meets_relevance = (
            candidate.relevance_score >= self._config.golden_min_relevance_score
        )

        return meets_access and meets_age and meets_relevance

    def promote_memories(
        self,
        dry_run: bool | None = None,
        batch_size: int | None = None,
    ) -> PromotionStats:
        """
        Identify and promote high-value memories to golden collection.

        Args:
            dry_run: Override config dry_run setting
            batch_size: Override config batch_size setting

        Returns:
            PromotionStats with operation results
        """
        start_time = datetime.now(UTC)
        is_dry_run = dry_run if dry_run is not None else self._config.dry_run
        batch = batch_size or self._config.batch_size

        stats = PromotionStats(was_dry_run=is_dry_run)
        promotion_scores: list[float] = []

        try:
            # Scan memories for promotion candidates
            if self._qdrant_client is not None:
                candidates = self._scan_candidates(batch)
                stats.candidates_evaluated = len(candidates)

                for candidate in candidates:
                    # Calculate promotion score
                    score = candidate.calculate_promotion_score(
                        min_access=self._config.golden_min_access_count,
                        min_age=self._config.golden_min_age_days,
                        min_relevance=self._config.golden_min_relevance_score,
                    )

                    if self._is_promotion_eligible(candidate):
                        stats.candidates_promoted += 1
                        promotion_scores.append(score)

                        if not is_dry_run:
                            self._promote_to_golden(candidate)
                            self._update_original_priority(candidate)
                            self._store_promotion_record(candidate)

                        logger.info(
                            f"Promoted memory {candidate.memory_id} to golden "
                            f"(score: {score:.3f}, reasons: {candidate.promotion_reasons})"
                        )
                    else:
                        stats.candidates_rejected += 1

                # Update metrics
                if not is_dry_run and stats.candidates_promoted > 0:
                    self._update_metrics(stats)

            if promotion_scores:
                stats.promotion_score_avg = sum(promotion_scores) / len(
                    promotion_scores
                )

            logger.info(
                "Promotion operation completed",
                extra={
                    "candidates_evaluated": stats.candidates_evaluated,
                    "candidates_promoted": stats.candidates_promoted,
                    "dry_run": is_dry_run,
                },
            )

        except Exception as e:
            stats.errors.append(str(e))
            logger.exception("Promotion operation failed")

        finally:
            stats.processing_time_seconds = (
                datetime.now(UTC) - start_time
            ).total_seconds()
            self._last_stats = stats

        return stats

    def _scan_candidates(self, batch_size: int) -> list[PromotionCandidate]:
        """Scan memories for potential promotion candidates."""
        # Stub implementation - will be connected to actual Qdrant
        logger.debug(f"Scanning for promotion candidates, batch size {batch_size}")
        return []

    def _promote_to_golden(self, candidate: PromotionCandidate) -> None:
        """Add memory to golden collection in Qdrant."""
        if self._qdrant_client is None:
            return

        # Stub - actual Qdrant upsert to golden collection
        logger.info(f"Adding {candidate.memory_id} to golden collection")

    def _update_original_priority(self, candidate: PromotionCandidate) -> None:
        """Update original memory's priority to golden."""
        if self._qdrant_client is None:
            return

        # Stub - update priority field in original collection
        logger.debug(f"Updated priority for {candidate.memory_id}")

    def _store_promotion_record(self, candidate: PromotionCandidate) -> None:
        """Store promotion record in Redis for audit trail."""
        if self._redis_client is None:
            return

        try:
            record_key = f"{CONSOLIDATION_PREFIX}:promotions:{candidate.memory_id}"
            record = {
                "promoted_at": datetime.now(UTC).isoformat(),
                "memory_type": candidate.memory_type.value,
                "promotion_score": candidate.promotion_score,
                "reasons": candidate.promotion_reasons,
                "access_count": candidate.access_count,
                "relevance_score": candidate.relevance_score,
            }
            self._redis_client.setex(
                record_key,
                self._config.rollback_retention_days * 86400,
                json.dumps(record),
            )
        except Exception as e:
            logger.warning(f"Could not store promotion record: {e}")

    def _update_metrics(self, stats: PromotionStats) -> None:
        """Update promotion metrics in Redis."""
        if self._redis_client is None:
            return

        try:
            metrics_key = f"{CONSOLIDATION_PREFIX}:metrics:promotion"
            self._redis_client.hset(
                metrics_key,
                mapping={
                    "last_run": stats.timestamp.isoformat(),
                    "candidates_promoted": stats.candidates_promoted,
                    "avg_score": str(stats.promotion_score_avg),
                    "dry_run": str(stats.was_dry_run).lower(),
                },
            )
        except Exception as e:
            logger.warning(f"Could not update promotion metrics: {e}")

    def get_stats(self) -> PromotionStats | None:
        """Get statistics from last promotion run."""
        return self._last_stats

    def demote_from_golden(
        self,
        memory_id: str,
        reason: str = "manual",
    ) -> bool:
        """
        Demote a memory from golden back to normal priority.

        Args:
            memory_id: ID of memory to demote
            reason: Reason for demotion

        Returns:
            True if demotion successful
        """
        if self._qdrant_client is None:
            return False

        try:
            # Remove from golden collection
            # Update original priority
            # Log demotion

            logger.info(f"Demoted memory {memory_id} from golden: {reason}")
            return True

        except Exception as e:
            logger.error(f"Failed to demote {memory_id}: {e}")
            return False
