#!/usr/bin/env python3
"""Scheduled Digest Flush.

Wakes at 8:00 PM America/Toronto (DST-safe) and triggers DiscordNotifier.send_digest()
to flush buffered low/medium severity events from Redis digest queue.

Usage:
    python scripts/scheduler/digest_flush.py
    python scripts/scheduler/digest_flush.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load .env file for environment variables
env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key patterns (same as digest_store.py)
REDIS_QUEUE_KEY = "chise:governance:notifications:digest_queue"
DIGEST_SCHEDULER_HEARTBEAT_KEY = "bmad:chiseai:scheduler:digest_flush:heartbeat"
DIGEST_SCHEDULER_LAST_RUN_KEY = "bmad:chiseai:scheduler:digest_flush:last_run"

# Feature flag key (same as digest_store.py)
FEATURE_FLAG_KEY = "chise:feature_flags:governance:durable_digest_enabled"
FEATURE_FLAG_FIELD = "durable_digest_enabled"

# Timezone
TORONTO_TZ = ZoneInfo("America/Toronto")


def get_next_flush_time() -> datetime:
    """Get next configured flush time in policy timezone (DST-safe).

    Reads timezone and delivery_time_local from notification-policy.yaml.
    Falls back to America/Toronto / 20:00 if policy is missing.

    Returns:
        datetime in the policy timezone, next flush time.
    """
    policy_path = project_root / "config" / "aria" / "notification-policy.yaml"
    policy = {}
    if policy_path.exists():
        with open(policy_path) as f:
            policy = yaml.safe_load(f) or {}

    # Get timezone from policy, default to America/Toronto
    tz_name = policy.get("timezone", "America/Toronto")
    tz = ZoneInfo(tz_name)

    # Get delivery time from policy, default to 20:00
    delivery_time = policy.get("digest", {}).get("delivery_time_local", "20:00")
    hour, minute = map(int, delivery_time.split(":"))

    now = datetime.now(tz)
    next_flush = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If past target time today, schedule for tomorrow
    if now >= next_flush:
        next_flush += timedelta(days=1)

    return next_flush


def is_feature_enabled() -> bool:
    """Check if durable digest feature flag is enabled.

    Returns:
        True if the feature flag is enabled or not set (default-on).
    """
    try:
        from tools.redis_state import redis_state_hget

        flag = redis_state_hget(FEATURE_FLAG_KEY, FEATURE_FLAG_FIELD)
        if flag is None:
            return True  # Default enabled
        return flag.lower() not in ("false", "0", "no", "off")
    except Exception as e:
        logger.warning(f"Failed to read feature flag: {e}")
        return True  # Fail-open


async def flush_digest() -> bool:
    """Invoke DiscordNotifier.send_digest() to flush buffered events.

    Idempotent: safe to call when queue is empty (no-op).

    Returns:
        True if digest was sent, False if skipped or no events.
    """
    if not is_feature_enabled():
        logger.info("Digest flush skipped: durable_digest_enabled=false")
        return False

    from governance.notifications.discord_notifier import DiscordNotifier

    notifier = DiscordNotifier()
    result = await notifier.send_digest()

    # Update last-run timestamp (non-critical)
    try:
        from datetime import UTC

        from tools.redis_state import redis_state_expire, redis_state_set

        redis_state_set(DIGEST_SCHEDULER_LAST_RUN_KEY, datetime.now(UTC).isoformat())
        redis_state_expire(DIGEST_SCHEDULER_LAST_RUN_KEY, 86400 * 2)
    except Exception:
        pass  # Non-critical

    return result


def sleep_until(target_time: datetime) -> None:
    """Sleep until target datetime (blocking).

    Args:
        target_time: The datetime to sleep until.
    """
    now = datetime.now(target_time.tzinfo)
    wait_seconds = (target_time - now).total_seconds()
    if wait_seconds > 0:
        logger.info(f"Sleeping {wait_seconds:.0f}s until {target_time.isoformat()}")
        time.sleep(wait_seconds)


def main() -> None:
    """Main scheduler loop: sleep until configured flush time, flush, repeat."""
    parser = argparse.ArgumentParser(description="Digest Flush Scheduler")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run once without sleeping (log what would happen)",
    )
    args = parser.parse_args()

    logger.info("Digest Flush Scheduler starting")

    while True:
        next_time = get_next_flush_time()
        logger.info(
            f"Next flush scheduled for {next_time.isoformat()} ({next_time.tzinfo})"
        )

        if args.dry_run:
            logger.info("[DRY-RUN] Would flush digest now")
            return

        sleep_until(next_time)

        logger.info("Triggering scheduled digest flush")
        try:
            result = asyncio.run(flush_digest())
            if result:
                logger.info("Digest sent successfully")
            else:
                logger.info("Digest flush completed (no events to send)")
        except Exception as e:
            logger.error(f"Digest flush failed: {e}", exc_info=True)

        # Loop continues to next day


if __name__ == "__main__":
    main()
