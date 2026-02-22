#!/usr/bin/env python3
"""Emergency stop script for auto-approval.

Usage:
    python emergency_stop_auto_approval.py [--reason REASON] [--dry-run]

This script sets the emergency stop flag to disable all auto-approvals.
The flag is stored in Redis at: bmad:chiseai:auto_approval:disabled
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Redis key for emergency stop
EMERGENCY_STOP_KEY = "bmad:chiseai:auto_approval:disabled"
EMERGENCY_STOP_REASON_KEY = "bmad:chiseai:auto_approval:stop_reason"
EMERGENCY_STOP_TIME_KEY = "bmad:chiseai:auto_approval:stop_time"


async def set_emergency_stop(reason: str, dry_run: bool = False) -> bool:
    """Set the emergency stop flag.

    Args:
        reason: Reason for stopping
        dry_run: If True, don't actually set the flag

    Returns:
        True if successful
    """
    timestamp = datetime.now(UTC).isoformat()

    if dry_run:
        logger.info("[DRY RUN] Would set emergency stop flag")
        logger.info(f"[DRY RUN] Reason: {reason}")
        logger.info(f"[DRY RUN] Timestamp: {timestamp}")
        return True

    try:
        # Try to use Redis
        import redis.asyncio as redis

        r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

        # Set the stop flag
        await r.set(EMERGENCY_STOP_KEY, "true")
        await r.set(EMERGENCY_STOP_REASON_KEY, reason)
        await r.set(EMERGENCY_STOP_TIME_KEY, timestamp)

        # Set TTL of 30 days (emergency stops should be resolved by then)
        await r.expire(EMERGENCY_STOP_KEY, 30 * 24 * 3600)
        await r.expire(EMERGENCY_STOP_REASON_KEY, 30 * 24 * 3600)
        await r.expire(EMERGENCY_STOP_TIME_KEY, 30 * 24 * 3600)

        await r.close()

        logger.info("✅ Emergency stop flag SET successfully")
        logger.info(f"   Reason: {reason}")
        logger.info(f"   Timestamp: {timestamp}")
        logger.info(f"   Redis key: {EMERGENCY_STOP_KEY}")

        return True

    except ImportError:
        logger.error("❌ redis package not installed")
        logger.info("Install with: pip install redis")
        return False

    except Exception as e:
        logger.error(f"❌ Failed to set emergency stop: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Emergency stop for auto-approval system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python emergency_stop_auto_approval.py --reason "Critical bug detected"
    python emergency_stop_auto_approval.py --reason "Security incident" --dry-run
        """,
    )

    parser.add_argument(
        "--reason",
        type=str,
        required=True,
        help="Reason for emergency stop (required)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    # Run the async function
    success = asyncio.run(set_emergency_stop(args.reason, args.dry_run))

    if success:
        logger.info("\n⚠️  Auto-approval is now DISABLED")
        logger.info("   To resume: python resume_auto_approval.py")
        sys.exit(0)
    else:
        logger.error("\n❌ Failed to set emergency stop")
        sys.exit(1)


if __name__ == "__main__":
    main()
