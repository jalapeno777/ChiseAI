#!/usr/bin/env python3
"""
Paper Trading Daily Health Report
Story: ST-PAPER-REPORT-001

Generates daily health metrics for paper trading system.
Returns JSON with health metrics for monitoring and alerting.

Usage:
    python scripts/workflow/daily_paper_health_report.py
    python scripts/workflow/daily_paper_health_report.py --verbose
    python scripts/workflow/daily_paper_health_report.py --json

Exit Codes:
    0 - Health check passed (system healthy)
    1 - Health check found issues (degraded)
    2 - Health check found critical issues
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any

# Add src to path for imports
sys.path.insert(0, "src")

from reporting.daily_generator import DailyReportGenerator
from reporting.models import PaperHealthReport

HEALTH_REPORT_VERSION = "1.0.0"


class PaperHealthReportOutput:
    """Wrapper for paper health report with output formatting."""

    def __init__(self, report: PaperHealthReport):
        self.report = report
        self.timestamp = datetime.now(UTC).isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON output."""
        report_dict = self.report.to_dict()
        return {
            "version": HEALTH_REPORT_VERSION,
            "timestamp": self.timestamp,
            "date": report_dict["date"],
            "health_status": report_dict["health_status"],
            "all_checks_pass": report_dict["all_checks_pass"],
            "health_metrics": report_dict["health_metrics"],
            "portfolio": report_dict["portfolio"],
            "active_strategies": report_dict["active_strategies"],
            "warnings": report_dict["warnings"],
            "generated_at": report_dict["generated_at"],
        }

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def print_report(self, verbose: bool = False):
        """Print human-readable health report."""
        health_status = self.report.health_metrics.overall_health
        all_pass = self.report.health_metrics.all_pass

        print("=" * 80)
        print("PAPER TRADING DAILY HEALTH REPORT")
        print("=" * 80)
        print(f"Version: {HEALTH_REPORT_VERSION}")
        print(f"Timestamp: {self.timestamp}")
        print(f"Date: {self.report.date.strftime('%Y-%m-%d')}")
        print()

        print("SUMMARY:")
        print(f"  Overall Status: {health_status}")
        print(f"  All Checks Pass: {'YES' if all_pass else 'NO'}")
        print(f"  Portfolio Value: ${self.report.portfolio_value:,.2f}")
        print(f"  Total PnL: ${self.report.total_pnl:,.2f}")
        print(f"  Open Positions: {self.report.open_positions}")
        print(f"  Active Strategies: {self.report.active_strategies}")
        print()

        print("HEALTH CHECKS:")
        hm = self.report.health_metrics
        checks = [
            ("Redis Sync", hm.redis_sync_pass, hm.redis_sync_status),
            (
                "Validation",
                hm.validation_pass,
                f"{hm.validation_failure_rate_pct:.1f}% failure rate",
            ),
            ("Circuit Breaker", hm.circuit_breaker_pass, hm.circuit_breaker_state),
            (
                "Kill Switch",
                hm.kill_switch_pass,
                "ARMED" if hm.kill_switch_armed else "disarmed",
            ),
            (
                "Data Freshness",
                hm.data_freshness_pass,
                f"{hm.data_freshness_seconds:.0f}s ago",
            ),
        ]

        for check_name, passed, detail in checks:
            status_icon = "✓" if passed else "✗"
            print(f"  {status_icon} {check_name}: {detail}")
        print()

        if self.report.warnings:
            print("WARNINGS:")
            for warning in self.report.warnings:
                print(f"  ⚠ {warning}")
            print()

        if verbose and self.report.health_metrics.last_data_update:
            print("DETAILED METRICS:")
            print(f"  Redis Error Rate: {hm.redis_error_rate_pct:.2f}%")
            print(f"  Validation Failure Rate: {hm.validation_failure_rate_pct:.2f}%")
            print(f"  Data Freshness: {hm.data_freshness_seconds:.0f} seconds")
            print(
                f"  Last Data Update: {hm.last_data_update.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            print()

        print("=" * 80)
        if health_status == "HEALTHY":
            print("STATUS: ✓ HEALTHY - All systems operational")
        elif health_status == "DEGRADED":
            print("STATUS: ⚠ DEGRADED - Some issues detected, monitoring required")
        else:
            print("STATUS: ✗ CRITICAL - Critical issues require immediate attention")
        print("=" * 80)


async def generate_health_report() -> PaperHealthReportOutput:
    """Generate paper trading health report."""
    generator = DailyReportGenerator()
    report = await generator.generate_paper_health_report()
    return PaperHealthReportOutput(report)


def main():
    parser = argparse.ArgumentParser(
        description="Daily health report for paper trading system"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )

    args = parser.parse_args()

    # Generate health report
    report_output = asyncio.run(generate_health_report())

    # Output report
    if args.json:
        print(report_output.to_json())
    else:
        report_output.print_report(verbose=args.verbose)

    # Determine exit code based on health status
    health_status = report_output.report.health_metrics.overall_health
    if health_status == "CRITICAL":
        return 2
    elif health_status == "DEGRADED":
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
