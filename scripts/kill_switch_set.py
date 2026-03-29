#!/usr/bin/env python3
"""Set the paper trading kill switch.

Usage:
    python scripts/kill_switch_set.py --reason "manual stop" --ttl 3600

For PAPER-009: Emergency kill switch for paper trading
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.paper.paper_kill_switch import (
    DEFAULT_TTL_SECONDS,
    activate_sync,
    get_status_sync,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Activate the paper trading kill switch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Activate with default TTL (1 hour)
  python scripts/kill_switch_set.py --reason "manual stop"

  # Activate with custom TTL (5 minutes)
  python scripts/kill_switch_set.py --reason "testing" --ttl 300

  # Activate with longer TTL (4 hours)
  python scripts/kill_switch_set.py --reason "weekend pause" --ttl 14400
        """,
    )
    parser.add_argument(
        "--reason",
        type=str,
        required=True,
        help="Reason for activating the kill switch",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=DEFAULT_TTL_SECONDS,
        help=f"TTL in seconds (default: {DEFAULT_TTL_SECONDS} = 1 hour)",
    )
    parser.add_argument(
        "--activated-by",
        type=str,
        default="manual",
        help="Who/what is activating the kill switch (default: manual)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Activate even if kill switch is already active",
    )

    args = parser.parse_args()

    # Check if already active
    if not args.force:
        status = get_status_sync()
        if status.active:
            logger.error(
                f"Kill switch is already active: reason='{status.reason}' "
                f"activated_by='{status.activated_by}' ttl_remaining={status.ttl_remaining}s"
            )
            logger.error("Use --force to override")
            sys.exit(1)

    # Activate kill switch
    logger.info(f"Activating paper kill switch: reason='{args.reason}' ttl={args.ttl}s")
    success = activate_sync(
        reason=args.reason,
        activated_by=args.activated_by,
        ttl=args.ttl,
    )

    if success:
        logger.info("Paper kill switch activated successfully")
        # Show updated status
        status = get_status_sync()
        print(f"\nCurrent status:\n{status}")
        sys.exit(0)
    else:
        logger.error("Failed to activate kill switch")
        sys.exit(1)


if __name__ == "__main__":
    main()
