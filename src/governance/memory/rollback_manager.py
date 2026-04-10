"""
Rollback Manager for Memory Audit Framework.

Implements per-metric 3-consecutive-day breach detection with R1 invariant
preservation: NO staleness recomputation at query time.

All staleness values are READ ONLY from precomputed Redis/Qdrant state.
"""

from __future__ import annotations


class ObserverFabricationError(Exception):
    """Kill criterion: FP rate > 15%"""

    pass


class ObserverInsufficientCompression(Exception):
    """Kill criterion: Compression ratio < 2x after 2 tuning rounds"""

    pass


class ObserverInformationLoss(Exception):
    """Kill criterion: Information retention < 60%"""

    pass


class ObserverNoImprovement(Exception):
    """Kill criterion: A/B test Observer loses 8/10+"""

    pass


# Kill criteria thresholds (from memory-audit-framework-20260409.md Section 5)
KILL_CRITERIA = {
    "fp_rate": {
        "threshold": 0.05,
        "kill_threshold": 0.15,
        "consecutive_days": 3,
    },
    "compression_ratio": {
        "threshold": 0.4,
        "kill_threshold": 0.2,
        "consecutive_days": 3,
    },
    "information_retention": {
        "threshold": 0.80,
        "kill_threshold": 0.60,
        "consecutive_days": 3,
    },
    "recall_accuracy": {
        "threshold": None,  # No kill threshold specified
        "kill_threshold": None,
        "consecutive_days": 3,
    },
}

# Redis keys for metric storage
REDIS_METRIC_PREFIX = "bmad:chiseai:memory:metrics"
REDIS_METRIC_BREACH_COUNT_KEY = f"{REDIS_METRIC_PREFIX}:{{metric_name}}:breach_days"


def check_rollback_conditions() -> tuple[bool, list[str]]:
    """
    Check if rollback conditions are met.

    READ ONLY - does NOT trigger staleness recomputation.
    All staleness values must already be precomputed in Redis/Qdrant.

    Per-metric rule: A metric triggers rollback ONLY when that specific
    metric breaches its threshold on ALL 3 consecutive daily checks.

    Returns: (should_rollback, breached_metrics)
    """

    breached_metrics: list[str] = []

    for metric_name, criteria in KILL_CRITERIA.items():
        consecutive_days = criteria["consecutive_days"]
        kill_threshold = criteria["kill_threshold"]

        # Skip if no kill threshold defined
        if kill_threshold is None:
            continue

        status = get_metric_status(metric_name)

        # If staleness is unknown (None/missing), record does NOT trigger rollback
        # This is safe fallback per R1 invariant
        if status["value"] is None:
            continue

        if status["breaching"]:
            # Check consecutive days from Redis counter
            breach_count = _get_breach_count(metric_name)

            if breach_count >= consecutive_days:
                breached_metrics.append(
                    f"{metric_name} (breach_count={breach_count}, "
                    f"current_value={status['value']}, "
                    f"kill_threshold={kill_threshold})"
                )

    should_rollback = len(breached_metrics) > 0

    # If rollback triggered, disable hybrid memory
    if should_rollback:
        _set_memory_hybrid_disabled()

    return should_rollback, breached_metrics


def get_metric_status(metric_name: str) -> dict:
    """
    Get current status of a metric.

    Returns: {'value': float, 'breaching': bool, 'consecutive_days': int}
    """
    # R1 HARDENING: Read precomputed values only from Redis
    # NEVER compute staleness here

    value = _get_metric_value(metric_name)
    consecutive_days = KILL_CRITERIA.get(metric_name, {}).get("consecutive_days", 3)
    kill_threshold = KILL_CRITERIA.get(metric_name, {}).get("kill_threshold")

    breaching = False
    if value is not None and kill_threshold is not None:
        # Per-metric breach detection
        breaching = _is_breaching(metric_name, value, kill_threshold)

    return {
        "value": value,
        "breaching": breaching,
        "consecutive_days": consecutive_days,
    }


def _get_metric_value(metric_name: str) -> float | None:
    """
    Get precomputed metric value from Redis.

    R1 HARDENING: This only reads precomputed values.
    It NEVER computes staleness or calls any staleness compute function.
    """
    try:
        import os

        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )

        # Read precomputed metric value from Redis
        key = f"{REDIS_METRIC_PREFIX}:{metric_name}:current"
        value = client.get(key)

        if value is not None:
            return float(value)
        return None

    except (redis.RedisError, ValueError, TypeError):
        # Safe fallback: if Redis is unavailable or value is invalid,
        # do NOT trigger rollback (conservative safe behavior)
        return None


def _is_breaching(metric_name: str, value: float, kill_threshold: float) -> bool:
    """
    Check if metric value breaches kill threshold.

    For fp_rate and compression_ratio: value > threshold means breaching
    For information_retention: value < threshold means breaching
    """
    if metric_name in ("fp_rate", "compression_ratio"):
        # Higher is worse for these metrics
        return value > kill_threshold
    elif metric_name == "information_retention" or metric_name == "recall_accuracy":
        # Lower is worse
        return value < kill_threshold
    else:
        # Default: treat as "higher is worse"
        return value > kill_threshold


def _get_breach_count(metric_name: str) -> int:
    """
    Get the number of consecutive days this metric has breached.

    Returns integer count of consecutive breach days from Redis.
    """
    try:
        import os

        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )

        key = REDIS_METRIC_BREACH_COUNT_KEY.format(metric_name=metric_name)
        value = client.get(key)

        if value is not None:
            return int(value)
        return 0

    except (redis.RedisError, ValueError, TypeError):
        return 0


def _set_memory_hybrid_disabled() -> None:
    """
    Disable MEMORY_HYBRID_ENABLED feature flag.

    When disabled, guaranteed direct retrieval fallback is active.
    """
    from src.config.feature_flags import FeatureFlags

    ff = FeatureFlags()
    ff.set_memory_hybrid_enabled(False)


def set_memory_hybrid_enabled(enabled: bool) -> None:
    """
    Set MEMORY_HYBRID_ENABLED feature flag.
    When enabled=False, guaranteed direct retrieval fallback is active.
    """
    from src.config.feature_flags import FeatureFlags

    ff = FeatureFlags()
    ff.set_memory_hybrid_enabled(enabled)


def increment_breach_count(metric_name: str) -> int:
    """
    Increment the breach count for a metric.

    Called by daily cron job after metric evaluation.
    Returns the new breach count.
    """
    try:
        import os

        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )

        key = REDIS_METRIC_BREACH_COUNT_KEY.format(metric_name=metric_name)
        new_count = client.incr(key)

        # Set TTL to 10 days to auto-expire stale counters
        client.expire(key, 864000)

        return new_count

    except redis.RedisError:
        return 0


def reset_breach_count(metric_name: str) -> None:
    """
    Reset the breach count for a metric.

    Called when a metric is no longer breaching.
    """
    try:
        import os

        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )

        key = REDIS_METRIC_BREACH_COUNT_KEY.format(metric_name=metric_name)
        client.delete(key)

    except redis.RedisError:
        pass


def set_metric_value(metric_name: str, value: float) -> None:
    """
    Set the precomputed metric value in Redis.

    This is called by the Observer/metrics system at write time,
    NOT by the rollback manager at query time.
    """
    try:
        import os

        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )

        key = f"{REDIS_METRIC_PREFIX}:{metric_name}:current"
        client.set(key, str(value))

        # Also set timestamp for freshness tracking
        import time

        ts_key = f"{REDIS_METRIC_PREFIX}:{metric_name}:updated_at"
        client.set(ts_key, str(int(time.time())))

    except redis.RedisError:
        pass
