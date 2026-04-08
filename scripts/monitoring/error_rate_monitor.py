#!/usr/bin/env python3
"""Error rate monitoring script.

Calculates error rates from Redis data and triggers alerts when thresholds
are exceeded. Outputs JSON for evidence collection.

Usage:
    python3 error_rate_monitor.py [--dry-run] [--category CATEGORY] [--output OUTPUT]

For ST-PARTY-E2E-REMEDIATION-001: Error Rate Monitor & Alert Integration
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.execution.alerts.error_rate_integration import (
    AlertSeverity,
    ErrorCategory,
    ErrorRateAlertIntegration,
    ErrorRateThresholds,
    ErrorRateTracker,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Monitor error rates and trigger alerts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                           # Run full check
    %(prog)s --dry-run                 # Check without sending alerts
    %(prog)s --category api            # Check only API errors
    %(prog)s --output results.json     # Save results to file
    %(prog)s --threshold-warning 3.0   # Set warning threshold to 3%
    %(prog)s --threshold-critical 8.0  # Set critical threshold to 8%
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending Discord alerts",
    )

    parser.add_argument(
        "--category",
        type=str,
        choices=[c.value for c in ErrorCategory],
        help="Check specific error category only",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON results",
    )

    parser.add_argument(
        "--threshold-warning",
        type=float,
        default=5.0,
        help="Warning threshold percentage (default: 5.0)",
    )

    parser.add_argument(
        "--threshold-critical",
        type=float,
        default=10.0,
        help="Critical threshold percentage (default: 10.0)",
    )

    parser.add_argument(
        "--min-operations",
        type=int,
        default=10,
        help="Minimum operations before calculating rate (default: 10)",
    )

    parser.add_argument(
        "--webhook-url",
        type=str,
        help="Discord webhook URL (overrides environment variable)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


def get_discord_webhook_url(args: argparse.Namespace) -> str | None:
    """Get Discord webhook URL from args or environment."""
    if args.webhook_url:
        return args.webhook_url

    import os

    # Try common environment variable names
    for env_var in [
        "DISCORD_ALERT_WEBHOOK_URL",
        "DISCORD_WEBHOOK_URL",
        "DISCORD_TRADING_WEBHOOK_URL",
    ]:
        url = os.getenv(env_var)
        if url:
            logger.debug(f"Using webhook URL from {env_var}")
            return url

    return None


async def run_monitor(args: argparse.Namespace) -> dict[str, Any]:
    """Run error rate monitoring.

    Args:
        args: Parsed command line arguments

    Returns:
        Monitoring results dictionary
    """
    start_time = datetime.now(UTC)

    # Configure thresholds
    thresholds = ErrorRateThresholds(
        warning=args.threshold_warning,
        critical=args.threshold_critical,
        min_operations=args.min_operations,
    )

    # Initialize tracker and alert integration
    tracker = ErrorRateTracker(thresholds=thresholds)
    webhook_url = get_discord_webhook_url(args)

    alert_integration = ErrorRateAlertIntegration(
        tracker=tracker,
        discord_webhook_url=webhook_url,
        enabled=not args.dry_run,
    )

    # Determine which categories to check
    if args.category:
        category = ErrorCategory(args.category)
        categories = [category]
    else:
        categories = list(ErrorCategory)

    logger.info(f"Checking error rates for {len(categories)} categories")
    logger.info(
        f"Thresholds: warning={thresholds.warning}%, "
        f"critical={thresholds.critical}%, min_ops={thresholds.min_operations}"
    )

    # Get current metrics for all categories
    all_metrics = tracker.get_all_error_rates()

    # Check each category and collect results
    category_results = []
    alerts_triggered = []
    alerts_suppressed = []

    for category in categories:
        snapshot = all_metrics[category]

        result = {
            "category": category.value,
            "total_operations": snapshot.total_operations,
            "error_count": snapshot.error_count,
            "error_rate": round(snapshot.error_rate, 4),
            "threshold_warning": snapshot.threshold_warning,
            "threshold_critical": snapshot.threshold_critical,
            "is_warning": snapshot.is_warning,
            "is_critical": snapshot.is_critical,
            "severity": snapshot.severity.value,
        }

        # Check if we should trigger alert
        if snapshot.total_operations >= thresholds.min_operations:
            # Safety gate: verify producer has written recently before alerting
            redis_client = tracker._get_redis()
            if redis_client:
                try:
                    key = tracker._get_key(category, "stats")
                    last_updated_str = redis_client.hget(key, "last_updated")
                    if last_updated_str:
                        last_updated = datetime.fromisoformat(last_updated_str)
                        age_seconds = (datetime.now(UTC) - last_updated).total_seconds()
                        if age_seconds > 3600:
                            logger.warning(
                                f"Skipping alert for {category.value}: producer data is stale "
                                f"(last_updated {age_seconds / 3600:.1f}h ago)"
                            )
                            alerts_suppressed.append(
                                {
                                    "category": category.value,
                                    "severity": snapshot.severity.value,
                                    "error_rate": snapshot.error_rate,
                                    "reason": "stale_producer_data",
                                    "last_updated": last_updated_str,
                                }
                            )
                            continue
                    else:
                        logger.warning(
                            f"Skipping alert for {category.value}: no producer data "
                            f"(last_updated field missing)"
                        )
                        alerts_suppressed.append(
                            {
                                "category": category.value,
                                "severity": snapshot.severity.value,
                                "error_rate": snapshot.error_rate,
                                "reason": "no_producer_data",
                            }
                        )
                        continue
                except Exception as e:
                    logger.error(
                        f"Error checking producer freshness for {category.value}: {e}"
                    )

            if snapshot.is_critical or snapshot.is_warning:
                if not args.dry_run:
                    alert_result = await alert_integration.check_and_alert(category)
                    if alert_result.get("alerts_sent"):
                        alerts_triggered.extend(alert_result["alerts_sent"])
                    if alert_result.get("alerts_suppressed"):
                        alerts_suppressed.extend(alert_result["alerts_suppressed"])
                else:
                    alerts_suppressed.append(
                        {
                            "category": category.value,
                            "severity": snapshot.severity.value,
                            "error_rate": snapshot.error_rate,
                            "reason": "dry_run",
                        }
                    )

        category_results.append(result)

    end_time = datetime.now(UTC)
    duration_ms = (end_time - start_time).total_seconds() * 1000

    # Build final result
    result = {
        "timestamp": start_time.isoformat(),
        "duration_ms": round(duration_ms, 2),
        "dry_run": args.dry_run,
        "thresholds": thresholds.to_dict(),
        "categories_checked": len(categories),
        "category_results": category_results,
        "alerts_triggered": alerts_triggered,
        "alerts_suppressed": alerts_suppressed,
        "summary": {
            "total_categories": len(categories),
            "categories_with_errors": sum(
                1 for r in category_results if r["error_count"] > 0
            ),
            "warning_count": sum(1 for r in category_results if r["is_warning"]),
            "critical_count": sum(1 for r in category_results if r["is_critical"]),
            "alerts_sent": len(alerts_triggered),
            "alerts_suppressed": len(alerts_suppressed),
        },
    }

    return result


def print_results(results: dict[str, Any], verbose: bool = False) -> None:
    """Print monitoring results to console.

    Args:
        results: Monitoring results dictionary
        verbose: Whether to print verbose output
    """
    print("\n" + "=" * 60)
    print("ERROR RATE MONITOR RESULTS")
    print("=" * 60)

    print(f"\nTimestamp: {results['timestamp']}")
    print(f"Duration: {results['duration_ms']:.2f}ms")
    print(f"Dry Run: {results['dry_run']}")

    print("\n" + "-" * 60)
    print("THRESHOLDS")
    print("-" * 60)
    thresholds = results["thresholds"]
    print(f"  Warning:    {thresholds['warning']:.2f}%")
    print(f"  Critical:   {thresholds['critical']:.2f}%")
    print(f"  Min Ops:    {thresholds['min_operations']}")

    print("\n" + "-" * 60)
    print("CATEGORY RESULTS")
    print("-" * 60)

    for cat_result in results["category_results"]:
        cat = cat_result["category"].upper()
        ops = cat_result["total_operations"]
        errors = cat_result["error_count"]
        rate = cat_result["error_rate"]

        if cat_result["is_critical"]:
            status = "🚨 CRITICAL"
        elif cat_result["is_warning"]:
            status = "⚠️  WARNING"
        else:
            status = "✅ OK"

        print(f"\n  {cat}:")
        print(f"    Status:     {status}")
        print(f"    Operations: {ops}")
        print(f"    Errors:     {errors}")
        print(f"    Error Rate: {rate:.4f}%")

    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    summary = results["summary"]
    print(f"  Categories Checked:     {summary['total_categories']}")
    print(f"  Categories with Errors: {summary['categories_with_errors']}")
    print(f"  Warnings:               {summary['warning_count']}")
    print(f"  Critical:               {summary['critical_count']}")
    print(f"  Alerts Sent:            {summary['alerts_sent']}")
    print(f"  Alerts Suppressed:      {summary['alerts_suppressed']}")

    if results["alerts_triggered"]:
        print("\n" + "-" * 60)
        print("ALERTS TRIGGERED")
        print("-" * 60)
        for alert in results["alerts_triggered"]:
            print(
                f"  - {alert['category']}: {alert['severity']} ({alert['error_rate']:.2f}%)"
            )

    if results["alerts_suppressed"]:
        print("\n" + "-" * 60)
        print("ALERTS SUPPRESSED")
        print("-" * 60)
        for alert in results["alerts_suppressed"]:
            print(
                f"  - {alert['category']}: {alert.get('severity', 'N/A')} "
                f"(reason: {alert.get('reason', 'unknown')})"
            )

    print("\n" + "=" * 60)

    if verbose:
        print("\nFULL JSON OUTPUT:")
        print(json.dumps(results, indent=2))


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        results = asyncio.run(run_monitor(args))

        # Print results
        print_results(results, verbose=args.verbose)

        # Save to file if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to {output_path}")

        # Exit with error code if critical errors found
        if results["summary"]["critical_count"] > 0:
            logger.error("Critical error rates detected!")
            return 2

        if results["summary"]["warning_count"] > 0:
            logger.warning("Warning-level error rates detected")
            return 1

        logger.info("All error rates within acceptable thresholds")
        return 0

    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Monitor failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
