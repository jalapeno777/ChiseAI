#!/usr/bin/env python3
"""
Paper Trading Burn-in Tracker

Manages the 30-day burn-in period for paper trading with:
- Redis-based burn-in status tracking
- TTL of 35 days (buffer beyond 30-day burn-in)
- Daily validation job scheduling support

Key Redis Pattern: paper:burnin:status
Fields:
    - start_timestamp: ISO8601 timestamp when burn-in started
    - days_elapsed: Number of days since burn-in started
    - breach_count: Number of invariant breaches detected
    - status: BURNIN_ACTIVE | BURNIN_PASS | BURNIN_FAIL

Usage:
    python burnin_tracker.py start [--duration DAYS]
    python burnin_tracker.py status
    python burnin_tracker.py breach add --signal-id ID --severity LEVEL --reason TEXT
    python burnin_tracker.py breach list
    python burnin_tracker.py breach clear
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
BURNIN_DURATION_DAYS = 30
BURNIN_TTL_SECONDS = 35 * 24 * 60 * 60  # 35 days in seconds

# Redis key patterns
KEY_BURNIN_STATUS = "paper:burnin:status"
KEY_BURNIN_BREACH_PREFIX = "paper:burnin:breach:"
KEY_BURNIN_BREACH_COUNT = "paper:burnin:breach:count"

# Status values
STATUS_ACTIVE = "BURNIN_ACTIVE"
STATUS_PASS = "BURNIN_PASS"
STATUS_FAIL = "BURNIN_FAIL"


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


def start_burnin(duration_days: int = BURNIN_DURATION_DAYS) -> bool:
    """Start the burn-in period.

    Args:
        duration_days: Number of days for burn-in (default 30)

    Returns:
        True if burn-in started successfully
    """
    r = get_redis()
    if not r:
        return False

    try:
        now = datetime.now(UTC)
        end_date = now + timedelta(days=duration_days)

        status_data = {
            "start_timestamp": now.isoformat(),
            "start_date": now.strftime("%Y-%m-%d"),
            "duration_days": str(duration_days),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "days_elapsed": "0",
            "breach_count": "0",
            "status": STATUS_ACTIVE,
        }

        # Use HSET to store all fields at once
        r.hset(KEY_BURNIN_STATUS, mapping=status_data)

        # Set TTL on the hash
        r.expire(KEY_BURNIN_STATUS, BURNIN_TTL_SECONDS)

        # Initialize breach count key with TTL
        r.set(
            f"{KEY_BURNIN_STATUS}:initialized", now.isoformat(), ex=BURNIN_TTL_SECONDS
        )

        logger.info(f"✓ Burn-in started: {now.isoformat()}")
        logger.info(f"  Duration: {duration_days} days")
        logger.info(f"  End date: {end_date.strftime('%Y-%m-%d')}")
        logger.info(
            f"  TTL: {BURNIN_TTL_SECONDS} seconds ({BURNIN_TTL_SECONDS // 86400} days)"
        )

        r.close()
        return True

    except Exception as e:
        logger.error(f"Failed to start burn-in: {e}")
        return False


def get_status() -> dict[str, Any] | None:
    """Get current burn-in status.

    Returns:
        Dictionary with burn-in status or None if not started
    """
    r = get_redis()
    if not r:
        return None

    try:
        data = r.hgetall(KEY_BURNIN_STATUS)
        r.close()

        if not data:
            return None

        # Calculate days elapsed
        if "start_timestamp" in data:
            start = datetime.fromisoformat(
                data["start_timestamp"].replace("Z", "+00:00")
            )
            now = datetime.now(UTC)
            days_elapsed = (now - start).days
            data["days_elapsed"] = str(days_elapsed)

            # Update status based on days elapsed
            duration = int(data.get("duration_days", BURNIN_DURATION_DAYS))
            if days_elapsed >= duration:
                data["status"] = STATUS_PASS
            else:
                data["status"] = STATUS_ACTIVE

        return data

    except Exception as e:
        logger.error(f"Failed to get burn-in status: {e}")
        return None


def add_breach(signal_id: str, severity: str, reason: str) -> bool:
    """Log an invariant breach during burn-in.

    Args:
        signal_id: The signal ID that triggered the breach
        severity: Breach severity (low, medium, high, critical)
        reason: Description of the breach

    Returns:
        True if breach logged successfully
    """
    r = get_redis()
    if not r:
        return False

    try:
        now = datetime.now(UTC)
        breach_id = now.strftime("%Y%m%d%H%M%S%f")

        breach_data = {
            "breach_id": breach_id,
            "timestamp": now.isoformat(),
            "signal_id": signal_id,
            "severity": severity,
            "reason": reason,
        }

        # Store breach with unique ID
        breach_key = f"{KEY_BURNIN_BREACH_PREFIX}{breach_id}"
        r.hset(breach_key, mapping=breach_data)
        r.expire(breach_key, BURNIN_TTL_SECONDS)

        # Increment breach count
        r.incr(KEY_BURNIN_BREACH_COUNT)

        # Update breach count in status
        breach_count = r.get(KEY_BURNIN_BREACH_COUNT) or "0"
        r.hset(KEY_BURNIN_STATUS, "breach_count", breach_count)

        # Update status if high/critical breach
        if severity in ("high", "critical"):
            r.hset(KEY_BURNIN_STATUS, "status", STATUS_FAIL)

        logger.warning(f"Breach logged: [{severity}] {signal_id} - {reason}")

        r.close()
        return True

    except Exception as e:
        logger.error(f"Failed to log breach: {e}")
        return False


def list_breaches(limit: int = 50) -> list[dict[str, Any]]:
    """List recent burn-in breaches.

    Args:
        limit: Maximum number of breaches to return

    Returns:
        List of breach dictionaries
    """
    r = get_redis()
    if not r:
        return []

    try:
        # Scan for breach keys
        breach_keys = []
        cursor = 0
        while True:
            cursor, keys = r.scan(
                cursor, match=f"{KEY_BURNIN_BREACH_PREFIX}*", count=100
            )
            breach_keys.extend(keys)
            if cursor == 0:
                break

        # Sort by timestamp (most recent first) and limit
        breaches = []
        for key in breach_keys[:limit]:
            data = r.hgetall(key)
            if data:
                breaches.append(data)

        breaches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        r.close()
        return breaches

    except Exception as e:
        logger.error(f"Failed to list breaches: {e}")
        return []


def clear_breaches() -> bool:
    """Clear all burn-in breaches.

    Returns:
        True if cleared successfully
    """
    r = get_redis()
    if not r:
        return False

    try:
        # Delete all breach keys
        cursor = 0
        while True:
            cursor, keys = r.scan(
                cursor, match=f"{KEY_BURNIN_BREACH_PREFIX}*", count=100
            )
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break

        # Reset breach count
        r.set(KEY_BURNIN_BREACH_COUNT, "0")
        r.hset(KEY_BURNIN_STATUS, "breach_count", "0")

        # Reset status to active
        r.hset(KEY_BURNIN_STATUS, "status", STATUS_ACTIVE)

        logger.info("All breaches cleared")
        r.close()
        return True

    except Exception as e:
        logger.error(f"Failed to clear breaches: {e}")
        return False


def print_status(status: dict[str, Any]) -> None:
    """Print formatted burn-in status."""
    if not status:
        print("Burn-in not started")
        return

    days_elapsed = int(status.get("days_elapsed", 0))
    duration = int(status.get("duration_days", BURNIN_DURATION_DAYS))
    breach_count = int(status.get("breach_count", 0))
    st = status.get("status", "UNKNOWN")

    # Status emoji
    emoji = {"BURNIN_ACTIVE": "🔄", "BURNIN_PASS": "✅", "BURNIN_FAIL": "❌"}.get(
        st, "❓"
    )

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  PAPER TRADING BURN-IN STATUS                ║
╠══════════════════════════════════════════════════════════════╣
║  Status:    {emoji} {st:15}                          ║
║  Started:   {status.get("start_date", "N/A"):15}                          ║
║  Ends:      {status.get("end_date", "N/A"):15}                          ║
║  Progress:  {days_elapsed:3}/{duration:3} days ({100 * days_elapsed / max(duration, 1):5.1f}%)                ║
║  Breaches:  {breach_count:3}                                             ║
╚══════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(description="Paper Trading Burn-in Tracker")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start burn-in period")
    start_parser.add_argument(
        "--duration",
        type=int,
        default=BURNIN_DURATION_DAYS,
        help=f"Duration in days (default: {BURNIN_DURATION_DAYS})",
    )

    # Status command
    subparsers.add_parser("status", help="Get burn-in status")

    # Breach subcommands
    breach_parser = subparsers.add_parser("breach", help="Manage breaches")
    breach_subparsers = breach_parser.add_subparsers(dest="breach_command")

    breach_add = breach_subparsers.add_parser("add", help="Add a breach")
    breach_add.add_argument("--signal-id", required=True, help="Signal ID")
    breach_add.add_argument(
        "--severity",
        required=True,
        choices=["low", "medium", "high", "critical"],
        help="Breach severity",
    )
    breach_add.add_argument("--reason", required=True, help="Breach reason")

    breach_list = breach_subparsers.add_parser("list", help="List breaches")
    breach_list.add_argument(
        "--limit", type=int, default=50, help="Max breaches to show"
    )

    _breach_clear = breach_subparsers.add_parser("clear", help="Clear all breaches")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "start":
        success = start_burnin(args.duration)
        return 0 if success else 1

    elif args.command == "status":
        status = get_status()
        print_status(status)
        return 0 if status else 1

    elif args.command == "breach":
        if args.breach_command == "add":
            success = add_breach(args.signal_id, args.severity, args.reason)
            return 0 if success else 1
        elif args.breach_command == "list":
            breaches = list_breaches(args.limit)
            if not breaches:
                print("No breaches recorded")
                return 0
            for b in breaches:
                print(
                    f"[{b.get('timestamp')}] {b.get('severity'):8} | {b.get('signal_id')} | {b.get('reason')}"
                )
            return 0
        elif args.breach_command == "clear":
            success = clear_breaches()
            return 0 if success else 1
        else:
            breach_parser.print_help()
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
