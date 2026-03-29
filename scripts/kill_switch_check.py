#!/usr/bin/env python3
"""Check the paper trading kill switch status.

Usage:
    python scripts/kill_switch_check.py

For PAPER-009: Emergency kill switch for paper trading
"""

import argparse
import json
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.paper.paper_kill_switch import (
    deactivate_sync,
    get_status_sync,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Check paper trading kill switch status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check status
  python scripts/kill_switch_check.py

  # Deactivate kill switch
  python scripts/kill_switch_check.py --deactivate

  # Deactivate with confirmation
  python scripts/kill_switch_check.py --deactivate --force
        """,
    )
    parser.add_argument(
        "--deactivate",
        action="store_true",
        help="Deactivate the kill switch if active",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt when deactivating",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output status as JSON",
    )

    args = parser.parse_args()

    # Get status
    status = get_status_sync()

    if args.json:
        import json

        print(json.dumps(status.to_dict(), indent=2))
        sys.exit(0)

    # Print status
    print("\nPaper Trading Kill Switch Status")
    print("=" * 40)
    print(f"Active: {status.active}")
    if status.active:
        print(f"Reason: {status.reason}")
        print(f"Activated by: {status.activated_by}")
        print(f"Activated at: {status.activated_at}")
        print(f"TTL remaining: {status.ttl_remaining}s")
    print()

    # Deactivate if requested
    if args.deactivate:
        if not status.active:
            logger.info("Kill switch is not active, nothing to deactivate")
            sys.exit(0)

        if not args.force:
            confirm = input("Deactivate kill switch? [y/N] ").strip().lower()
            if confirm != "y":
                logger.info("Aborted")
                sys.exit(0)

        logger.info("Deactivating kill switch...")
        success = deactivate_sync()
        if success:
            logger.info("Kill switch deactivated successfully")
            sys.exit(0)
        else:
            logger.error("Failed to deactivate kill switch")
            sys.exit(1)


if __name__ == "__main__":
    main()
