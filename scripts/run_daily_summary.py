#!/usr/bin/env python3
"""CLI entry point for daily summary generation.

Supports manual trigger with test and dry-run flags.
Cron-friendly (exit 0 on success).

Usage:
    python scripts/run_daily_summary.py [--test] [--dry-run] [--date YYYY-MM-DD]

For PAPER-LIVE-001: Daily Summary Scheduler
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.reporting.daily_scheduler import DailySummaryScheduler  # noqa: E402

from config.bootstrap import bootstrap  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Generate and send daily trading summary reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate and send daily summary (normal operation)
    python scripts/run_daily_summary.py

    # Send to test channel immediately
    python scripts/run_daily_summary.py --test

    # Generate report without sending (dry run)
    python scripts/run_daily_summary.py --dry-run

    # Generate report for specific date
    python scripts/run_daily_summary.py --date 2024-01-15

    # Health check
    python scripts/run_daily_summary.py --health-check

Exit codes:
    0 - Success
    1 - Error (check logs)
    2 - Configuration error
        """,
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Send to #test channel instead of #summaries",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate report without sending to Discord",
    )

    parser.add_argument(
        "--date",
        type=str,
        metavar="YYYY-MM-DD",
        help="Generate report for specific date (default: yesterday)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/scheduler.yaml",
        help="Path to scheduler configuration file",
    )

    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run health check and exit",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Datetime object

    Raises:
        ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Use YYYY-MM-DD format."
        ) from e


async def run_health_check(scheduler: DailySummaryScheduler, json_output: bool) -> int:
    """Run health check.

    Args:
        scheduler: Scheduler instance
        json_output: Output as JSON

    Returns:
        Exit code (0 if healthy, 1 otherwise)
    """
    health = await scheduler.health_check()

    if json_output:
        print(json.dumps(health, indent=2))
    else:
        print("Daily Summary Scheduler Health Check")
        print("=" * 50)
        print(f"Status: {'✓ Healthy' if health['healthy'] else '✗ Unhealthy'}")
        print(f"Running: {'Yes' if health['running'] else 'No'}")
        print()
        print("Schedule:")
        print(f"  Time: {health['schedule']['time']}")
        print(f"  Timezone: {health['schedule']['timezone']}")
        print()
        print("Discord:")
        summaries_configured = health["discord"]["summaries_webhook_configured"]
        test_configured = health["discord"]["test_webhook_configured"]
        summaries_status = (
            "✓ Configured" if summaries_configured else "✗ Not configured"
        )
        test_status = "✓ Configured" if test_configured else "✗ Not configured"
        print(f"  Summaries webhook: {summaries_status}")
        print(f"  Test webhook: {test_status}")
        print(f"  Connection: {'✓ OK' if health['discord']['healthy'] else '✗ Failed'}")
        if health["discord"].get("error"):
            print(f"  Error: {health['discord']['error']}")
        print()
        print("InfluxDB:")
        print(f"  Bucket: {health['influxdb']['bucket']}")
        print(f"  Org: {health['influxdb']['org']}")

    return 0 if health["healthy"] else 1


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 on success, 1 on error, 2 on config error)
    """
    bootstrap(load_env=True)

    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Configuration file not found: {args.config}")
        return 2

    try:
        # Initialize scheduler
        scheduler = DailySummaryScheduler(config_path=str(config_path))

        # Health check mode
        if args.health_check:
            return await run_health_check(scheduler, args.json)

        # Parse date if provided
        target_date = None
        if args.date:
            try:
                target_date = parse_date(args.date)
            except ValueError as e:
                logger.error(str(e))
                return 2

        # Log operation mode
        if args.test:
            logger.info("Running in TEST mode - will send to #test channel")
        elif args.dry_run:
            logger.info("Running in DRY RUN mode - report will not be sent")
        else:
            logger.info("Running in PRODUCTION mode - will send to #summaries channel")

        # Generate and send report
        result = await scheduler.generate_and_send(
            test_mode=args.test,
            dry_run=args.dry_run,
            date=target_date,
        )

        # Output result
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result["success"]:
                print("✓ Daily summary generated successfully")
                if result.get("dry_run"):
                    print("  (Dry run - not sent)")
                elif result.get("message_ids"):
                    print(f"  Message IDs: {', '.join(result['message_ids'])}")

                # Print summary
                report = result.get("report", {})
                print()
                print("Summary:")
                print(f"  Date: {report.get('date', 'N/A')}")
                print(f"  Total PnL: ${report.get('total_pnl', 0):,.2f}")
                print(f"  Trades: {report.get('total_trades', 0)}")
                print(f"  Win Rate: {report.get('win_rate', 0):.1f}%")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")

        return 0 if result["success"] else 1

    except Exception as e:
        logger.exception("Unexpected error")
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(f"✗ Error: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
