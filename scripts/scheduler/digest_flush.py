#!/usr/bin/env python3
"""
Daily Digest Flush Script.

Runs as a daemon by default, waiting until 20:00 America/Toronto before
flushing the digest queue. Can also run in one-shot mode for testing
or manual invocation via the --run-once flag.

Usage:
    python digest_flush.py           # Daemon mode (default)
    python digest_flush.py --run-once  # One-shot mode, flush and exit
    python digest_flush.py --flush-now # Alias for --run-once
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.governance.notifications.discord_notifier import DiscordNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
TORONTO_TZ = ZoneInfo("America/Toronto")
DIGEST_HOUR = 20
DIGEST_MINUTE = 0


def sleep_until_20_et() -> None:
    """Sleep until 20:00 ET today (or tomorrow if already past)."""
    now_et = datetime.now(TORONTO_TZ)
    target_today = now_et.replace(
        hour=DIGEST_HOUR, minute=DIGEST_MINUTE, second=0, microsecond=0
    )

    if now_et >= target_today:
        # Already past 20:00 ET today, sleep until tomorrow
        target = target_today.replace(day=target_today.day + 1)
    else:
        target = target_today

    seconds_until = (target - now_et).total_seconds()
    logger.info(
        "Digest flush daemon sleeping until %s ET (%d seconds)", target, seconds_until
    )

    # Use a simple sleep with wake-up check every minute to handle signal interrupts
    import time

    while True:
        time.sleep(60)  # Sleep in 1-minute increments
        now = datetime.now(TORONTO_TZ)
        if now >= target:
            break


async def flush_digest() -> bool:
    """Flush the digest queue and send to Discord.

    Returns:
        True if digest was sent, False if queue was empty or send failed.
    """
    logger.info("Starting digest flush")

    notifier = DiscordNotifier()

    try:
        success = await notifier.send_digest()
        if success:
            logger.info("Digest sent successfully")
        else:
            logger.info("Digest flush: nothing to send or send failed")
        return success
    except Exception as e:
        logger.error("Digest flush failed: %s", e)
        return False


def run_daemon() -> None:
    """Run in daemon mode: loop forever, flush at 20:00 ET daily."""
    logger.info("Digest flush daemon starting (PID=%d)", sys.pid)

    # Set up signal handlers for graceful shutdown
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down gracefully...", sig_name)
        shutdown_requested = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while not shutdown_requested:
        sleep_until_20_et()

        if shutdown_requested:
            break

        # Flush digest
        try:
            success = asyncio.run(flush_digest())
            if not success:
                logger.info("No digest to send, will retry tomorrow")
        except Exception as e:
            logger.error("Error during digest flush: %s", e)

        # Sleep a bit to avoid tight loop if flush fails immediately
        if not shutdown_requested:
            import time

            time.sleep(60)

    logger.info("Digest flush daemon stopped")


def run_once() -> int:
    """Run in one-shot mode: flush once and exit.

    Returns:
        0 if digest was sent, 1 if nothing to send or error.
    """
    logger.info("Digest flush running in one-shot mode")
    success = asyncio.run(flush_digest())
    return 0 if success else 1


def main() -> int:
    """Main entry point.

    Returns:
        0 for success (daemon stays running, or one-shot sent digest),
        1 for no content or error.
    """
    parser = argparse.ArgumentParser(
        description="Daily digest flush script for governance notifications."
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run once and exit (skip the daemon loop). "
        "Useful for testing or manual invocation.",
    )
    parser.add_argument(
        "--flush-now",
        action="store_true",
        help="Alias for --run-once. Flush now and exit.",
    )

    args = parser.parse_args()

    if args.run_once or args.flush_now:
        return run_once()
    else:
        run_daemon()
        return 0  # Never reached in daemon mode


if __name__ == "__main__":
    sys.exit(main())
