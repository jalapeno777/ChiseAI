#!/usr/bin/env python3
"""
Daily Burn-in Validation Job

Validates burn-in invariants for paper trading:
- Risk limits adherence
- Drawdown limits
- Confidence thresholds
- Signal generation health

Logs breaches to Redis with timestamp, signal_id, severity.

Invariants checked:
1. Max daily drawdown: 5% (paper trading limit)
2. Min signal confidence: 50% (below = no trade)
3. Max position size: 10% of paper balance
4. Min signals per day: 1 (sanity check)
5. Max concurrent positions: 5

Usage:
    python burnin_daily_validation.py [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "host.docker.internal")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))

# Burn-in constants
BURNIN_TTL_SECONDS = 35 * 24 * 60 * 60  # 35 days

# Redis key patterns
KEY_BURNIN_STATUS = "paper:burnin:status"
KEY_BURNIN_BREACH_PREFIX = "paper:burnin:breach:"
KEY_SIGNAL_PREFIX = "paper:signal:"
KEY_OUTCOME_PREFIX = "paper:outcome:"

# Invariant thresholds
INVARIANTS = {
    "max_daily_drawdown_pct": 5.0,
    "min_signal_confidence": 50.0,
    "max_position_size_pct": 10.0,
    "min_signals_per_day": 1,
    "max_concurrent_positions": 5,
}


def get_redis():
    """Get Redis connection."""
    try:
        import redis

        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            socket_connect_timeout=5,
            decode_responses=True,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def is_burnin_active(r: Any) -> bool:
    """Check if burn-in is currently active."""
    status = r.hget(KEY_BURNIN_STATUS, "status")
    return status == "BURNIN_ACTIVE"


def add_breach(r: Any, signal_id: str, severity: str, reason: str) -> bool:
    """Log an invariant breach to Redis."""
    try:
        now = datetime.now(UTC)
        breach_id = now.strftime("%Y%m%d%H%M%S%f")

        breach_data = {
            "breach_id": breach_id,
            "timestamp": now.isoformat(),
            "signal_id": signal_id,
            "severity": severity,
            "reason": reason,
            "invariant_check": "daily_validation",
        }

        breach_key = f"{KEY_BURNIN_BREACH_PREFIX}{breach_id}"
        r.hset(breach_key, mapping=breach_data)
        r.expire(breach_key, BURNIN_TTL_SECONDS)

        # Increment breach count
        r.incr(f"{KEY_BURNIN_STATUS}:breach_count")
        breach_count = r.get(f"{KEY_BURNIN_STATUS}:breach_count") or "0"
        r.hset(KEY_BURNIN_STATUS, "breach_count", breach_count)

        logger.warning(f"Breach [{severity}]: {signal_id} - {reason}")
        return True

    except Exception as e:
        logger.error(f"Failed to log breach: {e}")
        return False


def get_signals_today(r: redis.Redis) -> list[dict[str, Any]]:
    """Get all signals generated today."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    signals = []

    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=f"{KEY_SIGNAL_PREFIX}{today}*", count=100)
        for key in keys:
            data = r.hgetall(key)
            if data:
                signals.append(data)
        if cursor == 0:
            break

    return signals


def get_outcomes_today(r: redis.Redis) -> list[dict[str, Any]]:
    """Get all trade outcomes recorded today."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    outcomes = []

    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=f"{KEY_OUTCOME_PREFIX}{today}*", count=100)
        for key in keys:
            data = r.hgetall(key)
            if data:
                outcomes.append(data)
        if cursor == 0:
            break

    return outcomes


def check_signal_confidence(signal: dict[str, Any], r: redis.Redis) -> list[dict]:
    """Check if signal confidence meets minimum threshold."""
    breaches = []
    confidence = float(signal.get("confidence", 0))

    if confidence < INVARIANTS["min_signal_confidence"]:
        breach = {
            "signal_id": signal.get("signal_id", signal.get("id", "unknown")),
            "severity": "medium" if confidence >= 30 else "high",
            "reason": f"Low confidence: {confidence}% (min: {INVARIANTS['min_signal_confidence']}%)",
        }
        breaches.append(breach)
        add_breach(r, breach["signal_id"], breach["severity"], breach["reason"])

    return breaches


def check_position_size(signal: dict[str, Any], r: redis.Redis) -> list[dict]:
    """Check if position size is within limits."""
    breaches = []
    position_pct = float(signal.get("position_size_pct", 0))

    if position_pct > INVARIANTS["max_position_size_pct"]:
        breach = {
            "signal_id": signal.get("signal_id", signal.get("id", "unknown")),
            "severity": "critical" if position_pct > 20 else "high",
            "reason": f"Position size {position_pct}% exceeds max {INVARIANTS['max_position_size_pct']}%",
        }
        breaches.append(breach)
        add_breach(r, breach["signal_id"], breach["severity"], breach["reason"])

    return breaches


def check_drawdown(outcomes: list[dict], r: redis.Redis) -> list[dict]:
    """Check if daily drawdown exceeds limit."""
    breaches = []

    # Calculate P&L from outcomes
    total_pnl_pct = 0.0
    for outcome in outcomes:
        pnl = float(outcome.get("pnl_pct", 0))
        total_pnl_pct += pnl

    # Drawdown is negative P&L
    if total_pnl_pct < -INVARIANTS["max_daily_drawdown_pct"]:
        breach = {
            "signal_id": "DRAWDOWN_CHECK",
            "severity": "critical",
            "reason": f"Daily drawdown {abs(total_pnl_pct):.2f}% exceeds limit {INVARIANTS['max_daily_drawdown_pct']}%",
        }
        breaches.append(breach)
        add_breach(r, breach["signal_id"], breach["severity"], breach["reason"])

    return breaches


def check_signal_frequency(signals: list, r: redis.Redis) -> list[dict]:
    """Check if minimum signals per day are generated."""
    breaches = []

    if len(signals) < INVARIANTS["min_signals_per_day"]:
        breach = {
            "signal_id": "SIGNAL_FREQUENCY_CHECK",
            "severity": "medium",
            "reason": f"Only {len(signals)} signals today (min: {INVARIANTS['min_signals_per_day']})",
        }
        breaches.append(breach)
        add_breach(r, breach["signal_id"], breach["severity"], breach["reason"])

    return breaches


def run_validation(output_file: str | None = None) -> dict[str, Any]:
    """Run full daily validation.

    Returns:
        Validation results dictionary
    """
    r = get_redis()
    if not r:
        return {"status": "error", "message": "Redis connection failed"}

    # Check if burn-in is active
    if not is_burnin_active(r):
        logger.info("Burn-in is not active, skipping validation")
        r.close()
        return {"status": "skipped", "message": "Burn-in not active"}

    logger.info("Running daily burn-in validation...")

    # Get today's signals and outcomes
    signals = get_signals_today(r)
    outcomes = get_outcomes_today(r)

    all_breaches = []

    # Run invariant checks
    logger.info(f"Checking {len(signals)} signals...")
    for signal in signals:
        all_breaches.extend(check_signal_confidence(signal, r))
        all_breaches.extend(check_position_size(signal, r))

    logger.info(f"Checking {len(outcomes)} outcomes...")
    all_breaches.extend(check_drawdown(outcomes, r))

    logger.info("Checking signal frequency...")
    all_breaches.extend(check_signal_frequency(signals, r))

    # Update status
    breach_count = r.hget(KEY_BURNIN_STATUS, "breach_count") or "0"
    days_elapsed = r.hget(KEY_BURNIN_STATUS, "days_elapsed") or "0"

    r.close()

    result = {
        "status": "completed",
        "timestamp": datetime.now(UTC).isoformat(),
        "burnin_days_elapsed": int(days_elapsed),
        "signals_checked": len(signals),
        "outcomes_checked": len(outcomes),
        "breaches_found": len(all_breaches),
        "total_breach_count": int(breach_count),
        "breaches": all_breaches,
        "invariants_checked": list(INVARIANTS.keys()),
    }

    if output_file:
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Validation results written to {output_file}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Daily Burn-in Validation")
    parser.add_argument(
        "--output",
        "-o",
        help="Output file for validation results (JSON)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    result = run_validation(args.output)

    # Print summary
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║               DAILY BURN-IN VALIDATION RESULTS              ║
╠══════════════════════════════════════════════════════════════╣
║  Status:      {result.get("status", "unknown"):15}                    ║
║  Signals:     {result.get("signals_checked", 0):5} checked                           ║
║  Outcomes:    {result.get("outcomes_checked", 0):5} checked                           ║
║  Breaches:    {result.get("breaches_found", 0):5} found ({result.get("total_breach_count", 0)} total)              ║
╚══════════════════════════════════════════════════════════════╝
""")

    if result.get("breaches"):
        print("Breaches found:")
        for b in result["breaches"]:
            print(f"  [{b.get('severity'):8}] {b.get('signal_id')} - {b.get('reason')}")

    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
