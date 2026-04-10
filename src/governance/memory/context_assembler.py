"""
Context Assembly Session-Start Builder for Phase 4 Hybrid Memory Architecture.

Builds session context at session start using L0-L3 tiered recall.
Key constraints from memory-systems-evaluation-20260409.md Section 5:

1. NO query-time staleness recomputation in context assembly read path
2. If staleness_score absent in payload, mark as legacy_missing
   and do NOT compute surrogate at query time
3. Token budget capped at 25K total assembled context

HARDENING (Aria decision AD-PHASE4-20260409T000000Z-ctx001):
- Strategic challenge invariant hard-gate enforced via invariants.py
- All payloads checked for staleness_score presence
- Legacy missing records tracked, not computed
- MEMORY_HYBRID_ENABLED=false triggers direct retrieval fallback
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from .domain_context import DomainContext
from .invariants import (
    StalenessComputeError,
    assert_no_runtime_staleness_compute,
)
from .tiered_recall import (
    RecallEngine,
    TieredRecallResponse,
)

logger = logging.getLogger(__name__)

# Token budget cap for total assembled context
TOKEN_BUDGET_CAP = 25_000

# Alias for the external import
FreshnessSummary = "FreshnessSummary"  # Will be resolved at runtime


@dataclass
class MemoryContext:
    """
    Assembled memory context for a session.

    Attributes:
        hot_context: L0 tier - last iteration observations (from Redis).
        warm_context: L1 tier - last 7 days (from Qdrant).
        cold_context: L2 tier - 8-30 days (from Qdrant).
        archived_hints: L3 tier - 30+ day search hints (from Qdrant).
        token_budget_used: Total tokens assembled across all tiers.
        legacy_missing: List of record IDs missing staleness_score.
        domain: Optional domain context for scoping (from DomainContext).
    """

    hot_context: dict  # L0: last iteration observations
    warm_context: dict  # L1: last 7 days
    cold_context: dict  # L2: 8-30 days
    archived_hints: dict  # L3: 30+ day search hints
    token_budget_used: int
    legacy_missing: list[str] = field(default_factory=list)
    domain: dict | None = field(default=None)  # DomainContext metadata


def build_session_context(
    session_id: str,
    redis_client: Any = None,
    qdrant_client: Any = None,
    max_tokens: int = TOKEN_BUDGET_CAP,
) -> MemoryContext:
    """
    Assemble context for a session using tiered recall.

    HARDENING (Aria decision AD-PHASE4-20260409T000000Z-ctx001):
    - MEMORY_HYBRID_ENABLED=false → direct Qdrant retrieval (FALLBACK)
    - MEMORY_HYBRID_ENABLED=true → full Context Assembly pipeline
    - If staleness_score absent in payload, mark as legacy_missing
      and do NOT compute surrogate at query time
    - Token budget capped at 25K total

    Args:
        session_id: The session ID to assemble context for.
        redis_client: Optional Redis client for L0 access.
        qdrant_client: Optional Qdrant client for L1-L3 access.
        max_tokens: Token budget cap (default 25K).

    Returns:
        MemoryContext with all tier levels assembled.

    Raises:
        StalenessComputeError: If any payload has staleness_score
            that appears to be computed at query time (callable).
    """
    # HARDENING: Check feature flag to determine retrieval path
    from src.config.feature_flags import FeatureFlags

    ff = FeatureFlags()
    if not ff.is_memory_hybrid_enabled_for_session(session_id):
        # FALLBACK: Direct Qdrant retrieval (safe when flag is off)
        return _direct_retrieval_fallback(
            session_id=session_id,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
        )

    # FULL PIPELINE: Hybrid context assembly with DomainContext
    return _assemble_hybrid_context(
        session_id=session_id,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
        max_tokens=max_tokens,
    )


def _direct_retrieval_fallback(
    session_id: str,
    redis_client: Any = None,
    qdrant_client: Any = None,
) -> MemoryContext:
    """
    Fallback path: Direct Qdrant retrieval when MEMORY_HYBRID_ENABLED=false.

    This is the safe fallback path that bypasses the full Context Assembly
    pipeline. It provides basic retrieval without DomainContext overlay.

    Args:
        session_id: The session ID to retrieve context for.
        redis_client: Optional Redis client for L0 access.
        qdrant_client: Optional Qdrant client for L1-L3 access.

    Returns:
        MemoryContext with basic tier retrieval (no DomainContext).
    """
    logger.info(
        f"Using direct retrieval fallback for session={session_id} "
        "(MEMORY_HYBRID_ENABLED=false)"
    )

    # Use RecallEngine for basic L0-L3 retrieval
    recall = RecallEngine(
        session_id=session_id,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    # Get all tiers with default token budget
    response: TieredRecallResponse = recall.get_all_tiers(
        max_tokens=TOKEN_BUDGET_CAP,
    )

    # Collect legacy_missing from all tiers
    all_legacy_missing: list[str] = []

    # Validate and extract L0 (hot_context)
    hot_context = _extract_tier_context(response.tiers.get("L0"), all_legacy_missing)

    # Validate and extract L1 (warm_context)
    warm_context = _extract_tier_context(response.tiers.get("L1"), all_legacy_missing)

    # Validate and extract L2 (cold_context)
    cold_context = _extract_tier_context(response.tiers.get("L2"), all_legacy_missing)

    # Validate and extract L3 (archived_hints)
    archived_hints = _extract_tier_context(response.tiers.get("L3"), all_legacy_missing)

    # Compute total token budget used
    total_tokens = response.context_tokens

    return MemoryContext(
        hot_context=hot_context,
        warm_context=warm_context,
        cold_context=cold_context,
        archived_hints=archived_hints,
        token_budget_used=total_tokens,
        legacy_missing=all_legacy_missing,
        domain=None,  # No DomainContext in fallback mode
    )


def _assemble_hybrid_context(
    session_id: str,
    redis_client: Any = None,
    qdrant_client: Any = None,
    max_tokens: int = TOKEN_BUDGET_CAP,
) -> MemoryContext:
    """
    Full Context Assembly pipeline when MEMORY_HYBRID_ENABLED=true.

    Uses the RecallEngine to gather L0-L3 tier context, then validates
    all payloads against the staleness invariants. Includes DomainContext.

    Args:
        session_id: The session ID to assemble context for.
        redis_client: Optional Redis client for L0 access.
        qdrant_client: Optional Qdrant client for L1-L3 access.
        max_tokens: Token budget cap (default 25K).

    Returns:
        MemoryContext with all tier levels assembled including DomainContext.

    Raises:
        StalenessComputeError: If any payload has staleness_score
            that appears to be computed at query time (callable).
    """
    logger.info(
        f"Using full hybrid context assembly for session={session_id} "
        "(MEMORY_HYBRID_ENABLED=true)"
    )

    # Cap token budget at maximum
    effective_max_tokens = min(max_tokens, TOKEN_BUDGET_CAP)

    # Use RecallEngine to get all tiers
    recall = RecallEngine(
        session_id=session_id,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    # Get all tiers with token budget
    response: TieredRecallResponse = recall.get_all_tiers(
        max_tokens=effective_max_tokens,
    )

    # Collect legacy_missing from all tiers
    all_legacy_missing: list[str] = []

    # Validate and extract L0 (hot_context)
    hot_context = _extract_tier_context(response.tiers.get("L0"), all_legacy_missing)

    # Validate and extract L1 (warm_context)
    warm_context = _extract_tier_context(response.tiers.get("L1"), all_legacy_missing)

    # Validate and extract L2 (cold_context)
    cold_context = _extract_tier_context(response.tiers.get("L2"), all_legacy_missing)

    # Validate and extract L3 (archived_hints)
    archived_hints = _extract_tier_context(response.tiers.get("L3"), all_legacy_missing)

    # Compute total token budget used
    total_tokens = response.context_tokens

    # Build DomainContext from session metadata (if available)
    # This is a placeholder - actual DomainContext would come from
    # session metadata or memory record payloads
    domain = None
    try:
        # Try to extract DomainContext from hot_context results if present
        if hot_context.get("results"):
            first_result = hot_context["results"][0]
            if isinstance(first_result, dict) and "payload" in first_result:
                payload = first_result["payload"]
                if "domain_context" in payload:
                    dc = DomainContext.from_payload(payload)
                    domain = dc.to_payload()
    except Exception as e:
        logger.warning(f"Could not extract DomainContext: {e}")

    return MemoryContext(
        hot_context=hot_context,
        warm_context=warm_context,
        cold_context=cold_context,
        archived_hints=archived_hints,
        token_budget_used=total_tokens,
        legacy_missing=all_legacy_missing,
        domain=domain,
    )


def _extract_tier_context(tier_ctx: Any, legacy_missing: list[str]) -> dict:
    """
    Extract context dict from a TierContext, validating staleness invariants.

    Args:
        tier_ctx: TierContext from RecallEngine (or None).
        legacy_missing: List to append legacy_missing record IDs to.

    Returns:
        Dict with tier data formatted for MemoryContext.

    Raises:
        StalenessComputeError: If any payload has callable staleness_score.
    """
    if tier_ctx is None:
        return {
            "tier": None,
            "results": [],
            "freshness": None,
            "complete": False,
            "token_count": 0,
        }

    # Validate each payload in results
    results = tier_ctx.results or []
    validated_results = []

    for item in results:
        # Get payload - item is a Qdrant point with 'payload' key
        if isinstance(item, dict) and "payload" in item:
            payload = item["payload"]
        else:
            payload = item

        # Validate staleness invariant
        try:
            assert_no_runtime_staleness_compute(payload)
        except StalenessComputeError:
            raise

        # Check if staleness_score is missing (legacy)
        if payload.get("staleness_score") is None:
            record_id = payload.get("id", "unknown")
            if record_id not in legacy_missing:
                legacy_missing.append(f"legacy_missing:{record_id}")

        validated_results.append(item)

    # Build context dict
    freshness_dict = None
    if tier_ctx.freshness:
        freshness_dict = {
            "age_hours": tier_ctx.freshness.age_hours,
            "staleness_score": tier_ctx.freshness.staleness_score,
            "confidence_hint": tier_ctx.freshness.confidence_hint,
            "oldest_record": tier_ctx.freshness.oldest_record,
            "newest_record": tier_ctx.freshness.newest_record,
        }

    return {
        "tier": tier_ctx.tier,
        "results": validated_results,
        "freshness": freshness_dict,
        "complete": tier_ctx.complete,
        "token_count": tier_ctx.token_count,
    }


def assert_no_runtime_staleness_compute_in_context(
    context: MemoryContext,
) -> None:
    """
    Fail-fast assertion: raises StalenessComputeError if any payload
    in the assembled context has staleness_score computed at query time.

    This should be called after build_session_context() to verify
    the entire assembled context conforms to the staleness invariant.

    Args:
        context: MemoryContext assembled by build_session_context().

    Raises:
        StalenessComputeError: If any tier payload has callable staleness_score.
    """
    for tier_name, tier_data in [
        ("hot_context", context.hot_context),
        ("warm_context", context.warm_context),
        ("cold_context", context.cold_context),
        ("archived_hints", context.archived_hints),
    ]:
        results = tier_data.get("results", [])
        for item in results:
            # Get payload
            if isinstance(item, dict) and "payload" in item:
                payload = item["payload"]
            else:
                payload = item

            try:
                assert_no_runtime_staleness_compute(payload)
            except StalenessComputeError as e:
                logger.error(f"StalenessComputeError in {tier_name}: {e}")
                raise
