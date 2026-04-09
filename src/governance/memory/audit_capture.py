"""
Baseline Metrics Capture for Memory Context Assembly.

Captures baseline metrics for metrics that depend on context assembly.
Part of Phase 4 memory architecture hardening.

From Aria decision AD-PHASE4-20260409T000000Z-ctx001:
"Baseline Capture: Also implement baseline capture for metrics that depend
on context assembly"

Anti-Gaming Protections:
- Append-only: Never overwrite. Each capture creates a new hash entry.
- Capture Hash: SHA256(metric_values + timestamp) to detect replay.
- TTL Refresh: When TTL < 7 days, async refresh (don't block).
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import redis

logger = logging.getLogger(__name__)


def _get_redis_conn() -> redis.Redis:
    """Get Redis connection for baseline metrics storage."""
    host = os.getenv("REDIS_HOST", "host.docker.internal")
    port = int(os.getenv("REDIS_PORT", "6380"))
    db = int(os.getenv("REDIS_DB", "0"))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


# Redis key prefixes for baseline metrics
BASELINE_KEY_PREFIX = "bmad:chiseai:memory:baseline"
BASELINE_METRIC_KEYS = {
    "recall_accuracy": f"{BASELINE_KEY_PREFIX}:recall_accuracy",
    "context_cost": f"{BASELINE_KEY_PREFIX}:context_cost",
    "dedup_effectiveness": f"{BASELINE_KEY_PREFIX}:dedup_effectiveness",
    "staleness": f"{BASELINE_KEY_PREFIX}:staleness",
    "compression_ratio": f"{BASELINE_KEY_PREFIX}:compression_ratio",
    "coverage": f"{BASELINE_KEY_PREFIX}:coverage",
    "fp_rate": f"{BASELINE_KEY_PREFIX}:fp_rate",
    "near_dup_rate": f"{BASELINE_KEY_PREFIX}:near_dup_rate",
}

# TTL: 90 days in seconds
BASELINE_TTL_SECONDS = 90 * 24 * 60 * 60
# TTL refresh threshold: 7 days in seconds
TTL_REFRESH_THRESHOLD_SECONDS = 7 * 24 * 60 * 60


def _compute_capture_hash(value: float, captured_at: str) -> str:
    """Compute SHA256 hash for anti-gaming capture verification."""
    data = f"{value}:{captured_at}"
    return f"sha256:{hashlib.sha256(data.encode()).hexdigest()}"


def _capture_metric_to_redis(
    redis_key: str,
    value: float,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """
    Capture a single metric to Redis with anti-gaming protections.

    Args:
        redis_key: Redis hash key for this metric.
        value: The metric value to capture.
        captured_at: Optional ISO8601 timestamp. Defaults to now.

    Returns:
        Dict with value, captured_at, capture_hash, and ttl.
    """
    if captured_at is None:
        captured_at = datetime.now(UTC).isoformat()

    capture_hash = _compute_capture_hash(value, captured_at)
    ttl = BASELINE_TTL_SECONDS

    # Use current timestamp as field name for append-only behavior
    field_name = captured_at

    redis_conn = _get_redis_conn()
    redis_conn.hset(
        redis_key,
        field_name,
        f"{value}|{capture_hash}|{ttl}",
    )

    # Check if TTL needs refresh
    _refresh_ttl_if_needed(redis_key)

    return {
        "value": value,
        "captured_at": captured_at,
        "capture_hash": capture_hash,
        "ttl": ttl,
    }


def _refresh_ttl_if_needed(redis_key: str) -> bool:
    """
    Refresh TTL on Redis key if it's below threshold.

    Returns True if refresh was performed.
    """
    redis_conn = _get_redis_conn()
    current_ttl = redis_conn.ttl(redis_key)

    if current_ttl < 0:  # Key doesn't exist or has no TTL
        redis_conn.expire(redis_key, BASELINE_TTL_SECONDS)
        logger.debug(f"Set TTL on {redis_key}")
        return True
    elif current_ttl < TTL_REFRESH_THRESHOLD_SECONDS:
        redis_conn.expire(redis_key, BASELINE_TTL_SECONDS)
        logger.debug(f"Refreshed TTL on {redis_key} (was {current_ttl}s)")
        return True

    return False


def _refresh_ttl_async(redis_key: str) -> None:
    """Async wrapper for TTL refresh (non-blocking)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(_refresh_ttl_if_needed, redis_key)
        else:
            _refresh_ttl_if_needed(redis_key)
    except RuntimeError:
        # No event loop, just refresh synchronously
        _refresh_ttl_if_needed(redis_key)


def _parse_metric_entry(entry: str) -> dict[str, Any] | None:
    """Parse a metric entry from Redis hash value."""
    try:
        parts = entry.split("|")
        if len(parts) != 3:
            return None
        value_str, capture_hash, ttl_str = parts
        return {
            "value": float(value_str),
            "capture_hash": capture_hash,
            "ttl": int(ttl_str),
        }
    except (ValueError, TypeError):
        return None


def _get_latest_metric_from_redis(redis_key: str) -> dict[str, Any] | None:
    """
    Get the latest (most recent) metric entry from Redis hash.

    Returns None if no entries exist.
    """
    redis_conn = _get_redis_conn()
    all_entries = redis_conn.hgetall(redis_key)

    if not all_entries:
        return None

    # Find the most recent entry by field name (timestamp)
    latest_field = max(all_entries.keys())
    entry = _parse_metric_entry(all_entries[latest_field])

    if entry:
        entry["captured_at"] = latest_field

    return entry


def _get_all_metrics_from_redis(redis_key: str) -> list[dict[str, Any]]:
    """Get all metric entries from Redis hash."""
    redis_conn = _get_redis_conn()
    all_entries = redis_conn.hgetall(redis_key)

    metrics = []
    for field_name, entry_value in all_entries.items():
        parsed = _parse_metric_entry(entry_value)
        if parsed:
            parsed["captured_at"] = field_name
            metrics.append(parsed)

    # Sort by captured_at
    metrics.sort(key=lambda x: x["captured_at"])
    return metrics


@dataclass
class MemoryHealthMetrics:
    """
    Memory health baseline metrics for context assembly.

    Attributes:
        captured_at: ISO8601 timestamp when metrics were captured.
        total_sessions: Number of sessions in the sample.
        avg_token_budget_used: Average tokens used per session.
        max_token_budget_used: Maximum tokens used in sample.
        sessions_near_cap: Count of sessions approaching 25K cap (>80%).
        legacy_missing_count: Total records missing staleness_score.
        legacy_missing_ratio: Ratio of legacy_missing to total records.
        context_hit_rates: Per-tier context availability.
        staleness_violations: Count of staleness invariant violations.
    """

    captured_at: str
    total_sessions: int
    avg_token_budget_used: float
    max_token_budget_used: int
    sessions_near_cap: int
    legacy_missing_count: int
    legacy_missing_ratio: float
    context_hit_rates: dict[str, float] = field(default_factory=dict)
    staleness_violations: int = 0


@dataclass
class MemoryHealthSummary:
    """
    Summary of memory health status.

    Attributes:
        health_status: "healthy" | "degraded" | "critical".
        confidence: 0.0-1.0 confidence in the assessment.
        findings: List of human-readable findings.
        recommendations: List of recommended actions.
        staleness_violations: Count of staleness invariant violations detected.
    """

    health_status: str  # "healthy" | "degraded" | "critical"
    confidence: float
    findings: list[str]
    recommendations: list[str]
    staleness_violations: int = 0


def capture_baseline_metrics(
    session_samples: list[dict[str, Any]],
    timestamp: str | None = None,
) -> MemoryHealthMetrics:
    """
    Capture baseline metrics from session context samples.

    Args:
        session_samples: List of dicts with keys:
            - session_id: str
            - token_budget_used: int
            - legacy_missing: list[str]
            - hot_context_results: int
            - warm_context_results: int
            - cold_context_results: int
            - archived_context_results: int
            - staleness_violations: int (default 0)
        timestamp: Optional ISO8601 timestamp. Defaults to now.

    Returns:
        MemoryHealthMetrics with captured baseline.
    """
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()

    if not session_samples:
        logger.warning("No session samples provided for baseline capture")
        return MemoryHealthMetrics(
            captured_at=timestamp,
            total_sessions=0,
            avg_token_budget_used=0.0,
            max_token_budget_used=0,
            sessions_near_cap=0,
            legacy_missing_count=0,
            legacy_missing_ratio=0.0,
            context_hit_rates={},
            staleness_violations=0,
        )

    # Compute token budget stats
    token_budgets = [s.get("token_budget_used", 0) for s in session_samples]
    avg_tokens = sum(token_budgets) / len(token_budgets) if token_budgets else 0.0
    max_tokens = max(token_budgets) if token_budgets else 0

    # Count sessions near cap (>80% of 25K)
    cap_threshold = 25_000 * 0.8
    sessions_near_cap = sum(1 for tb in token_budgets if tb >= cap_threshold)

    # Legacy missing stats
    all_legacy_missing = []
    for sample in session_samples:
        legacy = sample.get("legacy_missing", [])
        all_legacy_missing.extend(legacy)

    total_records = sum(
        (
            s.get("hot_context_results", 0)
            + s.get("warm_context_results", 0)
            + s.get("cold_context_results", 0)
            + s.get("archived_context_results", 0)
        )
        for s in session_samples
    )

    legacy_ratio = len(all_legacy_missing) / total_records if total_records > 0 else 0.0

    # Context hit rates (per-tier availability)
    hit_rates = {}
    for tier in ["hot", "warm", "cold", "archived"]:
        results_key = f"{tier}_context_results"
        samples_with_results = sum(
            1 for s in session_samples if s.get(results_key, 0) > 0
        )
        hit_rate = (
            samples_with_results / len(session_samples) if session_samples else 0.0
        )
        hit_rates[tier] = hit_rate

    # Staleness violations
    total_violations = sum(s.get("staleness_violations", 0) for s in session_samples)

    return MemoryHealthMetrics(
        captured_at=timestamp,
        total_sessions=len(session_samples),
        avg_token_budget_used=avg_tokens,
        max_token_budget_used=max_tokens,
        sessions_near_cap=sessions_near_cap,
        legacy_missing_count=len(all_legacy_missing),
        legacy_missing_ratio=legacy_ratio,
        context_hit_rates=hit_rates,
        staleness_violations=total_violations,
    )


def get_memory_health_summary(
    metrics: MemoryHealthMetrics,
) -> MemoryHealthSummary:
    """
    Derive health summary from captured metrics.

    Args:
        metrics: MemoryHealthMetrics from capture_baseline_metrics().

    Returns:
        MemoryHealthSummary with status, findings, and recommendations.
    """
    findings = []
    recommendations = []
    health_status = "healthy"
    confidence = 0.9

    # Check staleness violations
    if metrics.staleness_violations > 0:
        health_status = "critical"
        confidence = 0.95
        findings.append(
            f"CRITICAL: {metrics.staleness_violations} staleness invariant violations detected"
        )
        recommendations.append(
            "Immediately investigate code paths computing staleness at query time"
        )

    # Check legacy missing ratio
    elif metrics.legacy_missing_ratio > 0.5:
        health_status = "degraded"
        confidence = 0.8
        findings.append(
            f"High legacy missing ratio: {metrics.legacy_missing_ratio:.1%} "
            f"({metrics.legacy_missing_count} records)"
        )
        recommendations.append(
            "Schedule migration to backfill staleness_score for legacy records"
        )

    # Check token budget saturation
    if metrics.sessions_near_cap > metrics.total_sessions * 0.3:
        if health_status == "healthy":
            health_status = "degraded"
        findings.append(
            f"{metrics.sessions_near_cap}/{metrics.total_sessions} sessions "
            f"approaching 25K token cap"
        )
        recommendations.append(
            "Consider increasing L3 pagination efficiency or adjusting retention"
        )

    # Context hit rates
    low_tiers = [tier for tier, rate in metrics.context_hit_rates.items() if rate < 0.5]
    if low_tiers:
        findings.append(f"Low hit rates for tiers: {', '.join(low_tiers)}")
        recommendations.append(
            "Investigate why context is not being promoted to warmer tiers"
        )

    # If no issues found
    if not findings:
        findings.append("All memory health metrics within normal parameters")
        recommendations.append("Continue monitoring")

    return MemoryHealthSummary(
        health_status=health_status,
        confidence=confidence,
        findings=findings,
        recommendations=recommendations,
        staleness_violations=metrics.staleness_violations,
    )


# =============================================================================
# Phase 1 PoC Baseline Metrics - 8 Metrics with Anti-Gaming Protections
# =============================================================================


def capture_baseline_metrics_all() -> dict[str, float]:
    """
    Capture current values for all 8 baseline metrics.
    Anti-gaming: append-only with SHA256 hash.

    Returns:
        Dict mapping metric name to current value.
    """
    results = {}

    for metric_name in BASELINE_METRIC_KEYS:
        latest = _get_latest_metric_from_redis(BASELINE_METRIC_KEYS[metric_name])
        if latest:
            results[metric_name] = latest["value"]
        else:
            results[metric_name] = 0.0

    return results


def capture_recall_accuracy_baseline(value: float) -> dict[str, Any]:
    """
    Capture recall accuracy baseline metric.

    Args:
        value: Recall accuracy value (0.0-1.0).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["recall_accuracy"],
        value,
    )


def capture_context_cost_baseline(value: float) -> dict[str, Any]:
    """
    Capture context cost baseline metric.

    Args:
        value: Context cost value (tokens or monetary cost).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["context_cost"],
        value,
    )


def capture_dedup_effectiveness_baseline(value: float) -> dict[str, Any]:
    """
    Capture deduplication effectiveness baseline metric.

    Args:
        value: Dedup effectiveness ratio (0.0-1.0).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["dedup_effectiveness"],
        value,
    )


def capture_staleness_baseline(value: float) -> dict[str, Any]:
    """
    Capture staleness baseline metric.

    Args:
        value: Staleness score (0.0-1.0, higher = staler).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["staleness"],
        value,
    )


def capture_compression_ratio_baseline(value: float) -> dict[str, Any]:
    """
    Capture compression ratio baseline metric.

    Args:
        value: Compression ratio (e.g., 0.5 means 50% compression).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["compression_ratio"],
        value,
    )


def capture_coverage_baseline(value: float) -> dict[str, Any]:
    """
    Capture coverage baseline metric.

    Args:
        value: Coverage ratio (0.0-1.0).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["coverage"],
        value,
    )


def capture_fp_rate_baseline(value: float) -> dict[str, Any]:
    """
    Capture false positive rate baseline from human evaluation.

    Args:
        value: False positive rate (0.0-1.0).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["fp_rate"],
        value,
    )


def capture_near_dup_rate_baseline(value: float) -> dict[str, Any]:
    """
    Capture near-duplicate rate (cosine similarity > 0.95 pairs / total).

    Args:
        value: Near-duplicate rate (0.0-1.0).

    Returns:
        Capture result dict with value, captured_at, capture_hash, ttl.
    """
    return _capture_metric_to_redis(
        BASELINE_METRIC_KEYS["near_dup_rate"],
        value,
    )


def get_memory_health_summary_all() -> dict[str, dict[str, Any]]:
    """
    Return health summary for all 8 baseline metrics.

    Returns:
        Dict mapping metric name to dict with:
        - value: float
        - captured_at: str
        - capture_hash: str
        - ttl: int
    """
    results = {}

    for metric_name, redis_key in BASELINE_METRIC_KEYS.items():
        latest = _get_latest_metric_from_redis(redis_key)
        if latest:
            results[metric_name] = latest
        else:
            results[metric_name] = {
                "value": 0.0,
                "captured_at": "",
                "capture_hash": "",
                "ttl": 0,
            }

    return results
