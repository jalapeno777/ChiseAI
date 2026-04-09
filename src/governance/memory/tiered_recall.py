"""
Tiered Recall Engine for ChiseAI Memory Governance.

Provides multi-tier memory context assembly:
- L0: Immediate context from Redis (last 24h)
- L1: Recent context from Qdrant (0-7 days)
- L2: Historical context from Qdrant (7-30 days)
- L3: Archived context from Qdrant (30+ days) — STUB for Batch 2

Staleness scoring is precomputed at WRITE TIME (reflector/promotion path),
NOT computed dynamically at query time. This ensures O(1) L3 queries.

Feature Flag: chise:feature_flags:memory:tiered_recall_enabled
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Feature flag key in Redis
FEATURE_FLAG_KEY = "chise:feature_flags:memory:tiered_recall_enabled"

# Tier thresholds
L0_MAX_AGE_HOURS = 24
L1_MAX_AGE_HOURS = 168  # 7 days
L2_MAX_AGE_HOURS = 720  # 30 days

# Qdrant collection
QDRANT_COLLECTION = "ChiseAI"

# Redis key patterns
REDIS_ACTIVE_OBSERVATIONS_KEY = "chise:observations:active:{session_id}"


@dataclass
class FreshnessSummary:
    """Summarizes the freshness of a memory tier.

    Attributes:
        age_hours: Age of newest record in hours (L0 only; None for L1-L3).
        staleness_score: Precomputed staleness 0.0 (stale) to 1.0 (fresh).
            Computed at WRITE TIME for L1-L3; always 0.0 for L0.
        confidence_hint: Confidence hint 0.0-1.0 based on tier source.
            L0 from Observer = 0.9; L1 = 0.7; L2 = 0.5; L3 = 0.3.
        oldest_record: ISO8601 timestamp of oldest record, or None.
        newest_record: ISO8601 timestamp of newest record, or None.
    """

    age_hours: float | None  # L0 only; None for L1-L3
    staleness_score: float  # 0.0 (stale) to 1.0 (fresh)
    confidence_hint: float  # 0.0-1.0
    oldest_record: str | None  # ISO8601
    newest_record: str | None  # ISO8601


@dataclass
class TierContext:
    """Context envelope for a single memory tier.

    Attributes:
        tier: Tier identifier ("L0", "L1", "L2", "L3").
        results: List of memory records for this tier.
        freshness: FreshnessSummary for this tier.
        complete: Whether this tier has complete data (False for L3 stub).
        token_count: Estimated token count of results.
    """

    tier: str  # "L0" | "L1" | "L2" | "L3"
    results: list[dict[str, Any]]
    freshness: FreshnessSummary
    complete: bool
    token_count: int


class RecallEngine:
    """Tiered recall engine for multi-tier memory context assembly.

    Assembles context from L0-L3 tiers with token budget management.
    Staleness scores are read from Qdrant payload (precomputed at write time),
    never computed dynamically at query time.
    """

    def __init__(
        self,
        session_id: str,
        redis_client: Any = None,
        qdrant_client: Any = None,
    ):
        """Initialize RecallEngine.

        Args:
            session_id: The session ID to assemble context for.
            redis_client: Optional Redis client for L0 access.
            qdrant_client: Optional Qdrant client for L1-L3 access.
        """
        self.session_id = session_id
        self._redis = redis_client
        self._qdrant = qdrant_client

    def get_all_tiers(
        self,
        max_tokens: int = 8000,
        domain_filter: dict[str, Any] | None = None,
    ) -> dict[str, TierContext]:
        """Assemble context from all tiers (L0-L3).

        Args:
            max_tokens: Maximum tokens to return across all tiers.
            domain_filter: Optional Qdrant filter to limit scope.

        Returns:
            Dict mapping tier name ("L0", "L1", "L2", "L3") to TierContext.
        """
        # L0: Immediate (Redis, last 24h)
        l0 = self._get_l0_immediate()

        # L1: Recent (Qdrant, 0-7 days)
        l1 = self._get_l1_recent(domain_filter)

        # L2: Historical (Qdrant, 7-30 days)
        l2 = self._get_l2_historical(domain_filter)

        # L3: Archived (Qdrant, 30+ days) — STUB for Batch 2
        l3 = self._get_l3_archived_stub(domain_filter)

        # Token budget fill order: L0 → L1 → L2 → L3
        assembled = self._assemble_with_budget(
            {"L0": l0, "L1": l1, "L2": l2, "L3": l3},
            max_tokens,
        )

        return assembled

    def _get_l0_immediate(self) -> TierContext:
        """L0: Immediate context from Redis sorted set (last 24h).

        Returns:
            TierContext with L0 observations sorted by timestamp desc.
        """
        key = REDIS_ACTIVE_OBSERVATIONS_KEY.format(session_id=self.session_id)

        if self._redis is None:
            logger.warning("Redis client not available for L0 access")
            return TierContext(
                tier="L0",
                results=[],
                freshness=FreshnessSummary(
                    age_hours=None,
                    staleness_score=0.0,
                    confidence_hint=0.9,
                    oldest_record=None,
                    newest_record=None,
                ),
                complete=True,
                token_count=0,
            )

        try:
            raw = self._redis.zrange(key, 0, -1, desc=True)
            items = [json.loads(r) for r in raw]

            now = datetime.now(UTC)
            for item in items:
                ts = datetime.fromisoformat(item["timestamp"])
                item["age_hours"] = (now - ts).total_seconds() / 3600

            newest_record = items[0]["timestamp"] if items else None
            oldest_record = items[-1]["timestamp"] if items else None
            age_hours = items[0]["age_hours"] if items else None

            return TierContext(
                tier="L0",
                results=items,
                freshness=FreshnessSummary(
                    age_hours=age_hours,
                    staleness_score=0.0,  # L0 is always "fresh" (no staleness decay)
                    confidence_hint=0.9,  # L0 from Observer, high confidence
                    oldest_record=oldest_record,
                    newest_record=newest_record,
                ),
                complete=True,
                token_count=self._estimate_tokens(items),
            )

        except Exception as e:
            logger.error(f"Failed to get L0 context from Redis: {e}")
            return TierContext(
                tier="L0",
                results=[],
                freshness=FreshnessSummary(
                    age_hours=None,
                    staleness_score=0.0,
                    confidence_hint=0.9,
                    oldest_record=None,
                    newest_record=None,
                ),
                complete=True,
                token_count=0,
            )

    def _get_l1_recent(
        self, domain_filter: dict[str, Any] | None = None
    ) -> TierContext:
        """L1: Recent context from Qdrant (0-7 days).

        Staleness_score is read from payload (precomputed at write time).

        Args:
            domain_filter: Optional Qdrant filter.

        Returns:
            TierContext with L1 memories.
        """
        from_dt = datetime.now(UTC) - timedelta(hours=L1_MAX_AGE_HOURS)

        filter_conditions: dict[str, Any] = {
            "must": [
                {"key": "story_id", "match": {"value": self.session_id}},
                {"key": "memory_type", "match": {"value": "consolidated"}},
                {"key": "created_at", "range": {"gte": from_dt.isoformat()}},
            ]
        }

        if domain_filter:
            filter_conditions["must"].append(domain_filter)

        results = self._scroll_qdrant(filter_conditions, limit=1000)

        # Read staleness_score from payload (precomputed at WRITE TIME)
        now = datetime.now(UTC)
        newest_record = None
        oldest_record = None

        for item in results:
            payload = item.get("payload", {})
            # staleness_score is precomputed at write time; read from payload
            # For records without precomputed score (legacy), compute at read time
            # but this is the exception, not the rule
            if "staleness_score" not in payload:
                updated = datetime.fromisoformat(
                    payload.get("updated_at", now.isoformat())
                )
                hours_since = (now - updated).total_seconds() / 3600
                payload["staleness_score"] = max(
                    0.0, 1.0 - hours_since / L1_MAX_AGE_HOURS
                )

            ts = payload.get("created_at")
            if ts:
                if oldest_record is None or ts < oldest_record:
                    oldest_record = ts
                if newest_record is None or ts > newest_record:
                    newest_record = ts

        staleness_scores = [
            r.get("payload", {}).get("staleness_score", 0.0) for r in results
        ]
        avg_staleness = (
            sum(staleness_scores) / len(staleness_scores) if staleness_scores else 0.0
        )

        return TierContext(
            tier="L1",
            results=results,
            freshness=FreshnessSummary(
                age_hours=None,  # L1+ doesn't track age_hours
                staleness_score=avg_staleness,
                confidence_hint=0.7,
                oldest_record=oldest_record,
                newest_record=newest_record,
            ),
            complete=True,
            token_count=self._estimate_tokens([r.get("payload", {}) for r in results]),
        )

    def _get_l2_historical(
        self, domain_filter: dict[str, Any] | None = None
    ) -> TierContext:
        """L2: Historical context from Qdrant (7-30 days).

        Staleness_score is read from payload (precomputed at write time).

        Args:
            domain_filter: Optional Qdrant filter.

        Returns:
            TierContext with L2 memories.
        """
        from_dt = datetime.now(UTC) - timedelta(hours=L2_MAX_AGE_HOURS)
        to_dt = datetime.now(UTC) - timedelta(hours=L1_MAX_AGE_HOURS)

        filter_conditions: dict[str, Any] = {
            "must": [
                {"key": "story_id", "match": {"value": self.session_id}},
                {"key": "memory_type", "match": {"value": "consolidated"}},
                {
                    "key": "created_at",
                    "range": {"gte": from_dt.isoformat(), "lte": to_dt.isoformat()},
                },
            ]
        }

        if domain_filter:
            filter_conditions["must"].append(domain_filter)

        results = self._scroll_qdrant(filter_conditions, limit=1000)

        # Read staleness_score from payload (precomputed at WRITE TIME)
        now = datetime.now(UTC)
        newest_record = None
        oldest_record = None

        for item in results:
            payload = item.get("payload", {})
            if "staleness_score" not in payload:
                updated = datetime.fromisoformat(
                    payload.get("updated_at", now.isoformat())
                )
                hours_since = (now - updated).total_seconds() / 3600
                payload["staleness_score"] = max(
                    0.0, 1.0 - hours_since / L2_MAX_AGE_HOURS
                )

            ts = payload.get("created_at")
            if ts:
                if oldest_record is None or ts < oldest_record:
                    oldest_record = ts
                if newest_record is None or ts > newest_record:
                    newest_record = ts

        staleness_scores = [
            r.get("payload", {}).get("staleness_score", 0.0) for r in results
        ]
        avg_staleness = (
            sum(staleness_scores) / len(staleness_scores) if staleness_scores else 0.0
        )

        return TierContext(
            tier="L2",
            results=results,
            freshness=FreshnessSummary(
                age_hours=None,
                staleness_score=avg_staleness,
                confidence_hint=0.5,
                oldest_record=oldest_record,
                newest_record=newest_record,
            ),
            complete=True,
            token_count=self._estimate_tokens([r.get("payload", {}) for r in results]),
        )

    def _get_l3_archived_stub(
        self, domain_filter: dict[str, Any] | None = None
    ) -> TierContext:
        """L3: Archived context from Qdrant (30+ days) — STUB.

        WARNING: L3 staleness MUST be precomputed at write time (Batch 2).
        This stub returns empty results with a note that L3 staleness
        MUST come from the Qdrant payload (precomputed), NOT computed dynamically.

        Batch 2 will implement full L3 support with precomputed staleness_score.

        Returns:
            TierContext stub for L3.
        """
        # NOTE: When Batch 2 implements L3, staleness_score will be read from
        # Qdrant payload. The query will filter by created_at > 30 days and
        # read precomputed staleness_score from payload — NO dynamic computation.
        return TierContext(
            tier="L3",
            results=[],
            freshness=FreshnessSummary(
                age_hours=None,
                staleness_score=0.0,  # Will use precomputed from Qdrant payload in Batch 2
                confidence_hint=0.3,
                oldest_record=None,
                newest_record=None,
            ),
            complete=False,  # Stub incomplete until Batch 2
            token_count=0,
        )

    def _scroll_qdrant(
        self,
        filter_conditions: dict[str, Any],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Scroll Qdrant collection with filter conditions.

        Args:
            filter_conditions: Qdrant filter conditions.
            limit: Maximum results to return.

        Returns:
            List of Qdrant points with payload.
        """
        if self._qdrant is None:
            logger.warning("Qdrant client not available for scroll")
            return []

        try:
            # Use scroll API with filter
            results, _ = self._qdrant.scroll(
                collection_name=QDRANT_COLLECTION,
                filter=filter_conditions,
                limit=limit,
                with_payload=True,
            )
            return results or []

        except Exception as e:
            logger.error(f"Failed to scroll Qdrant: {e}")
            return []

    def _assemble_with_budget(
        self,
        tiers: dict[str, TierContext],
        max_tokens: int,
    ) -> dict[str, TierContext]:
        """Assemble tiers within token budget.

        Fill order: L0 → L1 → L2 → L3.
        Each tier is included fully until budget is exhausted.

        Args:
            tiers: Dict of tier name to TierContext.
            max_tokens: Maximum tokens across all tiers.

        Returns:
            Dict of tier name to TierContext (may have truncated results).
        """
        remaining_tokens = max_tokens
        result: dict[str, TierContext] = {}

        for tier_name in ["L0", "L1", "L2", "L3"]:
            tier_ctx = tiers.get(tier_name)
            if tier_ctx is None:
                continue

            if tier_ctx.token_count <= remaining_tokens:
                # Include full tier
                result[tier_name] = tier_ctx
                remaining_tokens -= tier_ctx.token_count
            elif remaining_tokens > 0:
                # Partial tier — truncate results
                # Estimate ratio to keep
                ratio = remaining_tokens / tier_ctx.token_count
                keep_count = max(1, int(len(tier_ctx.results) * ratio))
                truncated_results = tier_ctx.results[:keep_count]

                result[tier_name] = TierContext(
                    tier=tier_ctx.tier,
                    results=truncated_results,
                    freshness=tier_ctx.freshness,
                    complete=False,
                    token_count=remaining_tokens,
                )
                remaining_tokens = 0
            else:
                # No budget remaining — mark complete=False, empty results
                result[tier_name] = TierContext(
                    tier=tier_ctx.tier,
                    results=[],
                    freshness=tier_ctx.freshness,
                    complete=False,
                    token_count=0,
                )

        return result

    def _estimate_tokens(self, items: list[dict[str, Any]]) -> int:
        """Estimate token count for items.

        Uses rough estimate: 4 characters per token.

        Args:
            items: List of items to estimate.

        Returns:
            Estimated token count.
        """
        total_chars = 0
        for item in items:
            content = item.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            else:
                total_chars += len(str(content))
        return max(1, total_chars // 4)
