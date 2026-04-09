"""
Baseline Metrics Capture for Memory Context Assembly.

Captures baseline metrics for metrics that depend on context assembly.
Part of Phase 4 memory architecture hardening.

From Aria decision AD-PHASE4-20260409T000000Z-ctx001:
"Baseline Capture: Also implement baseline capture for metrics that depend
on context assembly"
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    timestamp: Optional[str] = None,
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
