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
import time
from dataclasses import dataclass, field
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

# L3 pagination constants
MAX_L3_PAGE_SIZE = 100
L3_QUERY_TIMEOUT_SECONDS = 10


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


@dataclass
class SaturationAlert:
    """Alert when context saturation is outside nominal range.

    Attributes:
        ratio: Actual tokens / max_tokens ratio.
        tier_breakdown: Per-tier token ratios.
        alert_type: "sparse" (< 0.3) | "saturated" (> 0.85) | "nominal".
        recommendation: Actionable recommendation string or None.
    """

    ratio: float
    tier_breakdown: dict[str, float]
    alert_type: str  # "sparse" | "saturated" | "nominal"
    recommendation: str | None


@dataclass
class TieredRecallResponse:
    """Full response from tiered recall with saturation metrics.

    Attributes:
        tiers: Mapping of tier name to TierContext.
        context_tokens: Total tokens assembled.
        max_tokens: Token budget limit.
        saturation_ratio: context_tokens / max_tokens.
        complete: True if all tiers returned full results.
        status: "ok" | "partial" | "feature_disabled".
        incomplete_tiers: List of tier names that returned partial results.
        next_cursors: Cursor for next page of incomplete tiers.
        timeout_ms: Elapsed ms for slowest tier query.
        saturation_alert: SaturationAlert if outside nominal range.
    """

    tiers: dict[str, TierContext]
    context_tokens: int
    max_tokens: int
    saturation_ratio: float
    complete: bool
    status: str  # "ok" | "partial" | "feature_disabled"
    incomplete_tiers: list[str] = field(default_factory=list)
    next_cursors: dict[str, str | None] = field(default_factory=dict)
    timeout_ms: int | None = None
    saturation_alert: SaturationAlert | None = None


@dataclass
class PartialL3Result:
    """Result of a single L3 page query with timeout tracking.

    Attributes:
        results: List of Qdrant points for this page.
        complete: True if no more pages remain.
        next_cursor: Cursor for next page, or None if complete.
        timeout_ms: Elapsed milliseconds for this query.
        fallback_tier: Tier to use as fallback on error, or None.
    """

    results: list[dict[str, Any]]
    complete: bool
    next_cursor: str | None
    timeout_ms: int
    fallback_tier: str | None = None

    @property
    def tier_context(self) -> TierContext:
        """Convert to TierContext for assembly.

        Returns:
            TierContext with results and metadata.
        """
        # Read staleness_score from payload (precomputed at write time)
        newest_record = None
        oldest_record = None

        for item in self.results:
            payload = item.get("payload", {})
            if "staleness_score" not in payload:
                # Legacy record: mark as legacy_missing, do NOT compute surrogate
                payload["legacy_missing"] = True
                payload["staleness_score"] = None  # Explicit None, not computed

            ts = payload.get("created_at")
            if ts:
                if oldest_record is None or ts < oldest_record:
                    oldest_record = ts
                if newest_record is None or ts > newest_record:
                    newest_record = ts

        staleness_scores = [
            r.get("payload", {}).get("staleness_score") or 0.0 for r in self.results
        ]
        avg_staleness = (
            sum(staleness_scores) / len(staleness_scores) if staleness_scores else 0.0
        )

        return TierContext(
            tier="L3",
            results=self.results,
            freshness=FreshnessSummary(
                age_hours=None,
                staleness_score=avg_staleness,
                confidence_hint=0.3,
                oldest_record=oldest_record,
                newest_record=newest_record,
            ),
            complete=self.complete,
            token_count=self._compute_token_count(),
        )

    def _compute_token_count(self) -> int:
        """Estimate token count for results.

        Uses rough estimate: 4 characters per token.

        Returns:
            Estimated token count.
        """
        total_chars = 0
        for item in self.results:
            payload = item.get("payload", {})
            content = payload.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            else:
                total_chars += len(str(content))
        return max(1, total_chars // 4)


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

    def _is_feature_enabled(self) -> bool:
        """Check if tiered recall feature flag is enabled.

        Returns:
            True if feature flag is set to a truthy value, False otherwise.
        """
        if self._redis is None:
            return False
        try:
            flag = self._redis.get(FEATURE_FLAG_KEY)
            if flag is None:
                return False
            return str(flag).lower() in ("true", "1", "yes")
        except Exception:
            return False

    def get_all_tiers(
        self,
        max_tokens: int = 8000,
        domain_filter: dict[str, Any] | None = None,
    ) -> TieredRecallResponse:
        """Assemble context from all tiers (L0-L3).

        Args:
            max_tokens: Maximum tokens to return across all tiers.
            domain_filter: Optional Qdrant filter to limit scope.

        Returns:
            TieredRecallResponse with full saturation metrics.
        """
        # H1: Feature flag gating — return empty response if disabled
        if not self._is_feature_enabled():
            return TieredRecallResponse(
                tiers={},
                context_tokens=0,
                max_tokens=max_tokens,
                saturation_ratio=0.0,
                complete=False,
                status="feature_disabled",
                incomplete_tiers=[],
                next_cursors={},
                timeout_ms=None,
                saturation_alert=None,
            )

        # L0: Immediate (Redis, last 24h)
        l0 = self._get_l0_immediate()

        # L1: Recent (Qdrant, 0-7 days)
        l1 = self._get_l1_recent(domain_filter)

        # L2: Historical (Qdrant, 7-30 days)
        l2 = self._get_l2_historical(domain_filter)

        # L3: Archived (Qdrant, 30+ days) with pagination + timeout
        l3_result = self._get_l3_archived(domain_filter)
        l3 = l3_result.tier_context

        # Track incomplete tiers and cursors
        incomplete_tiers = []
        next_cursors = {}
        timeout_ms = l3_result.timeout_ms
        status = "ok"

        if not l3_result.complete:
            incomplete_tiers.append("L3")
            next_cursors["L3"] = l3_result.next_cursor
            if l3_result.fallback_tier:
                status = "partial"

        if (
            l3_result.timeout_ms
            and l3_result.timeout_ms > L3_QUERY_TIMEOUT_SECONDS * 1000
        ):
            incomplete_tiers.append("L3")
            status = "partial"

        # Token budget fill order: L0 → L1 → L2 → L3
        assembled_tiers = self._assemble_with_budget(
            {"L0": l0, "L1": l1, "L2": l2, "L3": l3},
            max_tokens,
        )

        # Compute saturation metrics
        total_tokens = sum(ctx.token_count for ctx in assembled_tiers.values())
        saturation_ratio = total_tokens / max_tokens if max_tokens > 0 else 0.0

        # Compute per-tier breakdown
        tier_breakdown = {
            tier: ctx.token_count / max_tokens if max_tokens > 0 else 0.0
            for tier, ctx in assembled_tiers.items()
        }

        # Determine alert type and recommendation
        if saturation_ratio < 0.3:
            alert_type = "sparse"
            recommendation = "Consider expanding L2 or L3 search"
        elif saturation_ratio > 0.85:
            alert_type = "saturated"
            recommendation = "Approaching token limit; consider reducing L3 page size"
        else:
            alert_type = "nominal"
            recommendation = None

        saturation_alert = SaturationAlert(
            ratio=saturation_ratio,
            tier_breakdown=tier_breakdown,
            alert_type=alert_type,
            recommendation=recommendation,
        )

        # Determine if all tiers are complete
        all_complete = all(ctx.complete for ctx in assembled_tiers.values())

        return TieredRecallResponse(
            tiers=assembled_tiers,
            context_tokens=total_tokens,
            max_tokens=max_tokens,
            saturation_ratio=saturation_ratio,
            complete=all_complete,
            status=status,
            incomplete_tiers=incomplete_tiers,
            next_cursors=next_cursors,
            timeout_ms=timeout_ms,
            saturation_alert=saturation_alert,
        )

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
        newest_record = None
        oldest_record = None

        for item in results:
            payload = item.get("payload", {})
            # staleness_score is precomputed at write time; read from payload
            # For records without precomputed score (legacy), mark as legacy_missing
            # Do NOT compute surrogate staleness at query time
            if "staleness_score" not in payload:
                payload["legacy_missing"] = True
                payload["staleness_score"] = None  # Explicit None, not computed

            ts = payload.get("created_at")
            if ts:
                if oldest_record is None or ts < oldest_record:
                    oldest_record = ts
                if newest_record is None or ts > newest_record:
                    newest_record = ts

        staleness_scores = [
            r.get("payload", {}).get("staleness_score") or 0.0 for r in results
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
        newest_record = None
        oldest_record = None

        for item in results:
            payload = item.get("payload", {})
            if "staleness_score" not in payload:
                # Legacy record: mark as legacy_missing, do NOT compute surrogate
                payload["legacy_missing"] = True
                payload["staleness_score"] = None  # Explicit None, not computed

            ts = payload.get("created_at")
            if ts:
                if oldest_record is None or ts < oldest_record:
                    oldest_record = ts
                if newest_record is None or ts > newest_record:
                    newest_record = ts

        staleness_scores = [
            r.get("payload", {}).get("staleness_score") or 0.0 for r in results
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

    def _get_l3_archived(
        self, domain_filter: dict[str, Any] | None = None, cursor: str | None = None
    ) -> PartialL3Result:
        """L3: Archived context from Qdrant (30+ days) with pagination + timeout.

        Args:
            domain_filter: Optional Qdrant filter.
            cursor: Pagination cursor from previous page, or None for first page.

        Returns:
            PartialL3Result with results, completion status, next cursor, and timing.
        """
        start_time = time.time()
        filter_conditions = self._build_l3_filter(domain_filter)

        try:
            # Use Qdrant scroll with pagination cursor
            results, next_offset = self._qdrant.scroll(
                collection_name=QDRANT_COLLECTION,
                filter=filter_conditions,
                limit=MAX_L3_PAGE_SIZE,
                offset=cursor,
                with_payload=True,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            if elapsed_ms > L3_QUERY_TIMEOUT_SECONDS * 1000:
                # Timeout exceeded — return partial results with cursor
                return PartialL3Result(
                    results=results or [],
                    complete=False,
                    next_cursor=str(next_offset) if next_offset else None,
                    timeout_ms=elapsed_ms,
                    fallback_tier=None,
                )

            return PartialL3Result(
                results=results or [],
                complete=next_offset is None,
                next_cursor=str(next_offset) if next_offset else None,
                timeout_ms=elapsed_ms,
                fallback_tier=None,
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Failed to get L3 archived context: {e}")
            return PartialL3Result(
                results=[],
                complete=False,
                next_cursor=None,
                timeout_ms=elapsed_ms,
                fallback_tier="L3",
            )

    def _build_l3_filter(
        self, domain_filter: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build L3 Qdrant filter: created_at < L2_MAX_AGE_HOURS (older than L2 window).

        Args:
            domain_filter: Optional domain filter to append.

        Returns:
            Qdrant filter conditions for L3 archived tier.
        """
        from_dt = datetime.now(UTC) - timedelta(hours=L2_MAX_AGE_HOURS)

        filter_conditions: dict[str, Any] = {
            "must": [
                {"key": "created_at", "range": {"lt": from_dt.isoformat()}},
                {"key": "memory_type", "match": {"value": "consolidated"}},
            ]
        }

        if domain_filter:
            filter_conditions["must"].append(domain_filter)

        return filter_conditions

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
