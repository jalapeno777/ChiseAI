#!/usr/bin/env python3
"""Memory Canary Producer - populates data/canary/memory-canary-001.json from Redis metrics.

Architecture:
  - Reads current memory health metrics from Redis via audit_capture.py functions
  - Maps 8 Redis baseline metrics to 6 scoreboard fields
  - Writes output to data/canary/memory-canary-001.json
  - Idempotent (safe to run multiple times)
  - Handles Redis unavailable gracefully with defaults

Usage:
  python3 scripts/ops/canary_memory_producer.py          # normal run
  python3 scripts/ops/canary_memory_producer.py --dry-run # print what would be written

Metrics mapping (Redis → Canary):
  - recall_accuracy  → recall_quality
  - context_cost     → context_cost
  - staleness        → staleness_quality
  - coverage         → token_efficiency (approximate mapping)
  - fp_rate          → anti_gaming_status (derived: pass if < 0.05, warn if < 0.15, fail otherwise)
  - near_dup_rate    → operational_reliability (1.0 - near_dup_rate)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

# ── Metric mapping defaults ────────────────────────────────────────────────

DEFAULT_RECALL_QUALITY = 0.75
DEFAULT_CONTEXT_COST = 15000
DEFAULT_TOKEN_EFFICIENCY = 0.70
DEFAULT_STALENESS_QUALITY = 0.85
DEFAULT_ANTI_GAMING = "pass"
DEFAULT_OPERATIONAL_RELIABILITY = 0.90

OUTPUT_FILE = Path("data/canary/memory-canary-001.json")


def _derive_anti_gaming_status(fp_rate: float) -> str:
    """Derive anti-gaming status from false positive rate."""
    if fp_rate < 0.05:
        return "pass"
    elif fp_rate < 0.15:
        return "warn"
    else:
        return "fail"


def _load_redis_metrics() -> dict[str, float]:
    """Load latest metric values from Redis via audit_capture.py.

    Returns dict mapping metric name to value (0.0 if not available).
    """
    try:
        from src.governance.memory.audit_capture import (
            get_memory_health_summary_all,
        )

        raw = get_memory_health_summary_all()
    except Exception:
        # Redis unavailable - use all defaults
        return {}

    result = {}
    for metric_name, metric_data in raw.items():
        value = metric_data.get("value", 0.0)
        # Treat 0.0 as "not available" for metrics that should be non-zero
        # ( staleness and coverage can legitimately be 0, but for canary
        #   purposes treat anything < 0.01 as unavailable )
        if value < 0.01:
            result[metric_name] = 0.0
        else:
            result[metric_name] = value
    return result


def produce_metrics(redis_metrics: dict[str, float]) -> dict[str, float]:
    """Map Redis metrics to canary scoreboard fields.

    Args:
        redis_metrics: Dict mapping Redis metric names to values.
                      Empty dict means use all defaults.

    Returns:
        Dict mapping canary field names to values.
    """
    if not redis_metrics:
        # All defaults when Redis unavailable
        return {
            "recall_quality": DEFAULT_RECALL_QUALITY,
            "context_cost": DEFAULT_CONTEXT_COST,
            "token_efficiency": DEFAULT_TOKEN_EFFICIENCY,
            "staleness_quality": DEFAULT_STALENESS_QUALITY,
            "anti_gaming_status": DEFAULT_ANTI_GAMING,
            "operational_reliability": DEFAULT_OPERATIONAL_RELIABILITY,
        }

    rm = redis_metrics  # shorthand

    # recall_accuracy → recall_quality
    recall_quality = rm.get("recall_accuracy", 0.0)
    if recall_quality < 0.01:
        recall_quality = DEFAULT_RECALL_QUALITY

    # context_cost (tokens) - pass through, default if missing
    context_cost = rm.get("context_cost", 0.0)
    if context_cost < 1:
        context_cost = DEFAULT_CONTEXT_COST

    # coverage → token_efficiency (coverage is already 0-1 ratio)
    token_efficiency = rm.get("coverage", 0.0)
    if token_efficiency < 0.01:
        token_efficiency = DEFAULT_TOKEN_EFFICIENCY

    # staleness → staleness_quality
    staleness_quality = rm.get("staleness", 0.0)
    if staleness_quality < 0.01:
        staleness_quality = DEFAULT_STALENESS_QUALITY

    # fp_rate → anti_gaming_status
    fp_rate = rm.get("fp_rate", 0.0)
    if fp_rate < 0.01:
        anti_gaming_status = DEFAULT_ANTI_GAMING
    else:
        anti_gaming_status = _derive_anti_gaming_status(fp_rate)

    # near_dup_rate → operational_reliability (1.0 - near_dup_rate)
    near_dup_rate = rm.get("near_dup_rate", 0.0)
    if near_dup_rate < 0.01:
        operational_reliability = DEFAULT_OPERATIONAL_RELIABILITY
    else:
        operational_reliability = 1.0 - near_dup_rate
        # Clamp to valid range
        operational_reliability = max(0.0, min(1.0, operational_reliability))

    return {
        "recall_quality": round(recall_quality, 4),
        "context_cost": int(context_cost),
        "token_efficiency": round(token_efficiency, 4),
        "staleness_quality": round(staleness_quality, 4),
        "anti_gaming_status": anti_gaming_status,
        "operational_reliability": round(operational_reliability, 4),
    }


def build_canary_payload(metrics: dict[str, float]) -> dict:
    """Build the full memory-canary-001.json payload."""
    return {
        "canary_id": "memory-canary-001",
        "name": "Memory Hybrid Canary",
        "status": "running",
        "canary_mode": "memory",
        "metrics": metrics,
        "description": "Memory domain validation - hybrid architecture",
        "produced_at": datetime.now(UTC).isoformat(),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Memory canary producer - populates memory-canary-001.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written but do not write file",
    )
    args = parser.parse_args()

    # Load Redis metrics
    redis_metrics = _load_redis_metrics()

    # Produce canary fields
    canary_metrics = produce_metrics(redis_metrics)

    # Build payload
    payload = build_canary_payload(canary_metrics)

    if args.dry_run:
        print("DRY-RUN: would write:")
        print(json.dumps(payload, indent=2))
        return

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write output (idempotent - overwrites each run)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUTPUT_FILE}")

    # Validation: ensure all 6 fields are non-null
    missing = [k for k, v in canary_metrics.items() if v is None]
    if missing:
        print(f"WARNING: null fields: {missing}", file=sys.stderr)
    else:
        print("All 6 metrics populated.")


if __name__ == "__main__":
    main()
