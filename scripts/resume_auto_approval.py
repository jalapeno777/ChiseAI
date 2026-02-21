#!/usr/bin/env python3
"""Resume script for auto-approval.

Usage:
    python resume_auto_approval.py [--confirm] [--dry-run]

This script clears the emergency stop flag to re-enable auto-approvals.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Redis keys
EMERGENCY_STOP_KEY = "bmad:chiseai:auto_approval:disabled"
EMERGENCY_STOP_REASON_KEY = "bmad:chiseai:auto_approval:stop_reason"
EMERGENCY_STOP_TIME_KEY = "bmad:chiseai:auto_approval:stop_time"
RESUME_TIME_KEY = "bmad:chiseai:auto_approval:resume_time"


async def clear_emergency_stop(dry_run: bool = False) -> bool:
    """Clear the emergency stop flag.

    Args:
        dry_run: If True, don't actually clear the flag

    Returns:
        True if successful
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if dry_run:
        logger.info("[DRY RUN] Would clear emergency stop flag")
        return True

    try:
        # Try to use Redis
        import redis.asyncio as redis

        r = redis.Redis(host="host.docker.internal", port=6380, decode_responses=True)

        # Check current status
        current = await r.get(EMERGENCY_STOP_KEY)
        reason = await r.get(EMERGENCY_STOP_REASON_KEY)
        stop_time = await r.get(EMERGENCY_STOP_TIME_KEY)

        if current and current.lower() in ("true", "1", "yes"):
            logger.info("Current status: STOPPED")
            if reason:
                logger.info(f"Stop reason: {reason}")
            if stop_time:
                logger.info(f"Stopped at: {stop_time}")
        else:
            logger.info("Current status: NOT STOPPED (flag not set)")

        # Clear the stop flag
        await r.delete(EMERGENCY_STOP_KEY)
        await r.delete(EMERGENCY_STOP_REASON_KEY)
        await r.delete(EMERGENCY_STOP_TIME_KEY)

        # Record resume time
        await r.set(RESUME_TIME_KEY, timestamp)
        await r.expire(RESUME_TIME_KEY, 30 * 24 * 3600)

        await r.close()

        logger.info("✅ Emergency stop flag CLEARED successfully")
        logger.info(f"   Resumed at: {timestamp}")

        return True

    except ImportError:
        logger.error("❌ redis package not installed")
        logger.info("Install with: pip install redis")
        return False

    except Exception as e:
        logger.error(f"❌ Failed to clear emergency stop: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Resume auto-approval system after emergency stop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python resume_auto_approval.py --confirm
    python resume_auto_approval.py --dry-run
        """,
    )

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that you want to resume auto-approval (required)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    if not args.confirm and not args.dry_run:
        logger.error("❌ Must specify --confirm to resume auto-approval")
        logger.info("   Use --dry-run to see current status without changes")
        sys.exit(1)

    # Run the async function
    success = asyncio.run(clear_emergency_stop(args.dry_run))

    if success:
        if args.dry_run:
            logger.info("\n[DRY RUN] No changes made")
        else:
            logger.info("\n✅ Auto-approval is now ENABLED")
        sys.exit(0)
    else:
        logger.error("\n❌ Failed to resume auto-approval")
        sys.exit(1)


if __name__ == "__main__":
    main()
