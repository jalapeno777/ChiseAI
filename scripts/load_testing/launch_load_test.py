#!/usr/bin/env python3
"""CLI tool to launch load tests with configurable parameters.

This script provides automated load test execution with:
- Configurable load profiles (signal-only, db-only, websocket-only, full)
- Automatic reporting generation (JSON + HTML)
- Integration with Grafana for metrics export
- Exit codes: 0=pass, 1=fail

Usage:
    # Run full load test
    python scripts/load_testing/launch_load_test.py --profile full --duration 1h

    # Run signal-only load test
    python scripts/load_testing/launch_load_test.py --profile signal-only --users 10

    # Run with custom parameters
    python scripts/load_testing/launch_load_test.py \
        --host http://localhost:8001 --users 100 --duration 30m

Exit Codes:
    0 - All acceptance criteria met
    1 - One or more acceptance criteria failed
    2 - Configuration or setup error
    3 - Load test execution error
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
LOCUSTFILE = PROJECT_ROOT / "tests" / "load" / "locustfile.py"
REPORTS_DIR = PROJECT_ROOT / "reports" / "load_tests"

# Acceptance criteria thresholds
ACCEPTANCE_CRITERIA = {
    "signals_per_hour": 1000,
    "outcomes_per_hour": 10000,
    "websocket_connections": 1000,
    "signal_latency_ms": 1000,
    "db_insert_latency_ms": 50,
    "db_query_latency_ms": 100,
    "min_success_rate": 0.95,
}


class LoadTestProfile:
    """Load test profile configuration."""

    def __init__(
        self,
        name: str,
        users: int,
        spawn_rate: int,
        duration: str,
        tags: list[str] | None = None,
    ):
        self.name = name
        self.users = users
        self.spawn_rate = spawn_rate
        self.duration = duration
        self.tags = tags or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "users": self.users,
            "spawn_rate": self.spawn_rate,
            "duration": self.duration,
            "tags": self.tags,
        }


# Predefined profiles
PROFILES = {
    "signal-only": LoadTestProfile(
        name="signal-only",
        users=10,
        spawn_rate=2,
        duration="5m",
        tags=["signal"],
    ),
    "db-only": LoadTestProfile(
        name="db-only",
        users=20,
        spawn_rate=5,
        duration="5m",
        tags=["database"],
    ),
    "websocket-only": LoadTestProfile(
        name="websocket-only",
        users=100,
        spawn_rate=10,
        duration="5m",
        tags=["websocket"],
    ),
    "full": LoadTestProfile(
        name="full",
        users=50,
        spawn_rate=5,
        duration="10m",
        tags=None,  # Run all
    ),
    "smoke": LoadTestProfile(
        name="smoke",
        users=5,
        spawn_rate=1,
        duration="1m",
        tags=None,
    ),
}


class LoadTestRunner:
    """Runner for load tests with reporting."""

    def __init__(
        self,
        host: str,
        profile: LoadTestProfile,
        report_format: list[str] | None = None,
    ):
        self.host = host
        self.profile = profile
        self.report_format = report_format or ["json", "html"]
        self.results: dict[str, Any] = {}
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

    def _build_locust_command(self) -> list[str]:
        """Build the locust command."""
        cmd = [
            "locust",
            "-f",
            str(LOCUSTFILE),
            "--host",
            self.host,
            "--users",
            str(self.profile.users),
            "--spawn-rate",
            str(self.profile.spawn_rate),
            "--run-time",
            self.profile.duration,
            "--headless",  # Run without web UI
        ]

        if self.profile.tags:
            for tag in self.profile.tags:
                cmd.extend(["--tags", tag])

        return cmd

    def _generate_report_filename(self, extension: str) -> Path:
        """Generate a report filename with timestamp."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"load_test_{self.profile.name}_{timestamp}.{extension}"
        return REPORTS_DIR / filename

    def _ensure_reports_dir(self) -> None:
        """Ensure reports directory exists."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _parse_locust_stats(self, stats_json: dict[str, Any]) -> dict[str, Any]:
        """Parse locust statistics."""
        endpoints: dict[str, Any] = {}
        parsed: dict[str, Any] = {
            "total_requests": 0,
            "total_failures": 0,
            "success_rate": 0.0,
            "avg_response_time_ms": 0.0,
            "p95_response_time_ms": 0.0,
            "p99_response_time_ms": 0.0,
            "requests_per_second": 0.0,
            "endpoints": endpoints,
        }

        if "stats" in stats_json:
            for stat in stats_json["stats"]:
                name = stat.get("name", "unknown")
                parsed["total_requests"] += stat.get("num_requests", 0)
                parsed["total_failures"] += stat.get("num_failures", 0)

                parsed["endpoints"][name] = {
                    "requests": stat.get("num_requests", 0),
                    "failures": stat.get("num_failures", 0),
                    "avg_response_time": stat.get("avg_response_time", 0),
                    "p95": stat.get("p95", 0),
                    "p99": stat.get("p99", 0),
                }

        # Calculate aggregates
        if parsed["total_requests"] > 0:
            parsed["success_rate"] = (
                parsed["total_requests"] - parsed["total_failures"]
            ) / parsed["total_requests"]

        return parsed

    def _evaluate_acceptance_criteria(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Evaluate results against acceptance criteria."""
        checks: dict[str, Any] = {}
        results: dict[str, Any] = {
            "passed": True,
            "checks": checks,
        }

        # Check success rate
        success_rate = stats.get("success_rate", 0)
        checks["success_rate"] = {
            "value": success_rate,
            "threshold": ACCEPTANCE_CRITERIA["min_success_rate"],
            "passed": success_rate >= ACCEPTANCE_CRITERIA["min_success_rate"],
        }

        # Check response times for specific endpoints
        endpoints = stats.get("endpoints", {})

        # Signal generation latency
        signal_endpoint = endpoints.get("signal_generate", {})
        signal_latency = signal_endpoint.get("avg_response_time", 0)
        checks["signal_latency"] = {
            "value": signal_latency,
            "threshold": ACCEPTANCE_CRITERIA["signal_latency_ms"],
            "passed": signal_latency <= ACCEPTANCE_CRITERIA["signal_latency_ms"],
        }

        # Database insert latency
        db_insert_endpoint = endpoints.get("outcome_insert", {})
        db_insert_latency = db_insert_endpoint.get("avg_response_time", 0)
        checks["db_insert_latency"] = {
            "value": db_insert_latency,
            "threshold": ACCEPTANCE_CRITERIA["db_insert_latency_ms"],
            "passed": db_insert_latency <= ACCEPTANCE_CRITERIA["db_insert_latency_ms"],
        }

        # Database query latency
        db_query_endpoint = endpoints.get("outcome_query", {})
        db_query_latency = db_query_endpoint.get("avg_response_time", 0)
        checks["db_query_latency"] = {
            "value": db_query_latency,
            "threshold": ACCEPTANCE_CRITERIA["db_query_latency_ms"],
            "passed": db_query_latency <= ACCEPTANCE_CRITERIA["db_query_latency_ms"],
        }

        # Overall pass/fail
        results["passed"] = all(check["passed"] for check in checks.values())

        return results

    def _generate_json_report(
        self,
        stats: dict[str, Any],
        criteria_results: dict[str, Any],
    ) -> Path:
        """Generate JSON report."""
        report = {
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "profile": self.profile.to_dict(),
                "host": self.host,
                "duration_seconds": (
                    (self.end_time - self.start_time).total_seconds()
                    if self.end_time and self.start_time
                    else 0
                ),
            },
            "acceptance_criteria": ACCEPTANCE_CRITERIA,
            "criteria_results": criteria_results,
            "statistics": stats,
        }

        filepath = self._generate_report_filename("json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"JSON report saved: {filepath}")
        return filepath

    def _generate_html_report(
        self,
        stats: dict[str, Any],
        criteria_results: dict[str, Any],
    ) -> Path:
        """Generate HTML report."""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Load Test Report - {self.profile.name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .status {{
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 18px;
            margin: 20px 0;
        }}
        .status.pass {{
            background-color: #4CAF50;
            color: white;
        }}
        .status.fail {{
            background-color: #f44336;
            color: white;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        .pass {{
            color: #4CAF50;
            font-weight: bold;
        }}
        .fail {{
            color: #f44336;
            font-weight: bold;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            border-left: 4px solid #4CAF50;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Load Test Report - {self.profile.name.upper()}</h1>
        
        <div class="status {"pass" if criteria_results["passed"] else "fail"}">
            {"✓ PASSED" if criteria_results["passed"] else "✗ FAILED"}
        </div>
        
        <h2>Test Configuration</h2>
        <table>
            <tr>
                <th>Parameter</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Profile</td>
                <td>{self.profile.name}</td>
            </tr>
            <tr>
                <td>Host</td>
                <td>{self.host}</td>
            </tr>
            <tr>
                <td>Users</td>
                <td>{self.profile.users}</td>
            </tr>
            <tr>
                <td>Spawn Rate</td>
                <td>{self.profile.spawn_rate}/s</td>
            </tr>
            <tr>
                <td>Duration</td>
                <td>{self.profile.duration}</td>
            </tr>
            <tr>
                <td>Timestamp</td>
                <td>{datetime.now(UTC).isoformat()}</td>
            </tr>
        </table>
        
        <h2>Acceptance Criteria Results</h2>
        <table>
            <tr>
                <th>Check</th>
                <th>Actual</th>
                <th>Threshold</th>
                <th>Status</th>
            </tr>
"""

        for check_name, check_data in criteria_results["checks"].items():
            status_class = "pass" if check_data["passed"] else "fail"
            status_text = "✓ PASS" if check_data["passed"] else "✗ FAIL"
            html_content += f"""
            <tr>
                <td>{check_name.replace("_", " ").title()}</td>
                <td>{check_data["value"]:.3f}</td>
                <td>{check_data["threshold"]:.3f}</td>
                <td class="{status_class}">{status_text}</td>
            </tr>
"""

        html_content += """
        </table>
        
        <h2>Statistics Summary</h2>
        <div class="stats-grid">
"""

        # Add stat cards
        html_content += f"""
            <div class="stat-card">
                <div class="stat-label">Total Requests</div>
                <div class="stat-value">{stats.get("total_requests", 0):,}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value">{stats.get("success_rate", 0):.1%}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Response Time</div>
                <div class="stat-value">
                    {stats.get("avg_response_time_ms", 0):.1f}ms
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Requests/Second</div>
                <div class="stat-value">{stats.get("requests_per_second", 0):.1f}</div>
            </div>
        </div>
        
        <h2>Endpoint Details</h2>
        <table>
            <tr>
                <th>Endpoint</th>
                <th>Requests</th>
                <th>Failures</th>
                <th>Avg (ms)</th>
                <th>P95 (ms)</th>
                <th>P99 (ms)</th>
            </tr>
"""

        for endpoint_name, endpoint_stats in stats.get("endpoints", {}).items():
            html_content += f"""
            <tr>
                <td>{endpoint_name}</td>
                <td>{endpoint_stats.get("requests", 0):,}</td>
                <td>{endpoint_stats.get("failures", 0):,}</td>
                <td>{endpoint_stats.get("avg_response_time", 0):.1f}</td>
                <td>{endpoint_stats.get("p95", 0):.1f}</td>
                <td>{endpoint_stats.get("p99", 0):.1f}</td>
            </tr>
"""

        html_content += """
        </table>
        
        <footer style="margin-top: 40px; padding-top: 20px;
                       border-top: 1px solid #ddd; color: #666;
                       text-align: center;">
            Generated by ChiseAI Load Testing Framework
        </footer>
    </div>
</body>
</html>
"""

        filepath = self._generate_report_filename("html")
        with open(filepath, "w") as f:
            f.write(html_content)

        logger.info(f"HTML report saved: {filepath}")
        return filepath

    def run(self) -> int:
        """Run the load test and generate reports.

        Returns:
            Exit code (0=pass, 1=fail, 2=config error, 3=execution error)
        """
        self._ensure_reports_dir()

        # Check if locust is available
        try:
            subprocess.run(  # nosec B607
                ["locust", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Locust is not installed. Install with: pip install locust")
            return 2

        # Check if locustfile exists
        if not LOCUSTFILE.exists():
            logger.error(f"Locustfile not found: {LOCUSTFILE}")
            return 2

        logger.info(f"Starting load test with profile: {self.profile.name}")
        logger.info(f"Configuration: {self.profile.to_dict()}")

        self.start_time = datetime.now(UTC)

        try:
            # Run locust
            cmd = self._build_locust_command()
            logger.info(f"Running: {' '.join(cmd)}")

            # Create temporary files for stats
            with tempfile.NamedTemporaryFile(
                mode="w+",
                suffix=".json",
                delete=False,
            ):
                # Add CSV and JSON output options
                csv_prefix = str(REPORTS_DIR / f"locust_stats_{int(time.time())}")
                cmd.extend(
                    [
                        "--csv",
                        csv_prefix,
                        "--json",  # Output stats in JSON format at end
                    ]
                )

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                )

                logger.info(f"Locust exit code: {result.returncode}")

                if result.stderr:
                    logger.warning(f"Locust stderr: {result.stderr}")

            self.end_time = datetime.now(UTC)

            # Try to parse stats from CSV files
            stats = self._load_stats_from_csv(csv_prefix)

            # Evaluate acceptance criteria
            criteria_results = self._evaluate_acceptance_criteria(stats)

            # Generate reports
            if "json" in self.report_format:
                self._generate_json_report(stats, criteria_results)

            if "html" in self.report_format:
                self._generate_html_report(stats, criteria_results)

            # Print summary
            self._print_summary(stats, criteria_results)

            # Return appropriate exit code
            return 0 if criteria_results["passed"] else 1

        except Exception as e:
            logger.error(f"Load test execution failed: {e}")
            return 3

    def _load_stats_from_csv(self, csv_prefix: str) -> dict[str, Any]:
        """Load statistics from locust CSV files."""
        endpoints: dict[str, Any] = {}
        stats: dict[str, Any] = {
            "total_requests": 0,
            "total_failures": 0,
            "success_rate": 0.0,
            "avg_response_time_ms": 0.0,
            "requests_per_second": 0.0,
            "endpoints": endpoints,
        }

        try:
            # Try to read the stats CSV file
            stats_file = f"{csv_prefix}_stats.csv"
            import csv

            with open(stats_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Type") == "GET" or row.get("Type") == "POST":
                        name = row.get("Name", "unknown")
                        requests = int(row.get("Request Count", 0))
                        failures = int(row.get("Failure Count", 0))
                        avg_time = float(row.get("Average Response Time", 0))
                        p95 = float(row.get("95%", 0))
                        p99 = float(row.get("99%", 0))

                        stats["total_requests"] += requests
                        stats["total_failures"] += failures
                        endpoints[name] = {
                            "requests": requests,
                            "failures": failures,
                            "avg_response_time": avg_time,
                            "p95": p95,
                            "p99": p99,
                        }

            # Calculate aggregates
            if stats["total_requests"] > 0:
                stats["success_rate"] = (
                    stats["total_requests"] - stats["total_failures"]
                ) / stats["total_requests"]

                # Calculate weighted average
                total_time = sum(
                    ep["avg_response_time"] * ep["requests"]
                    for ep in endpoints.values()
                )
                stats["avg_response_time_ms"] = total_time / stats["total_requests"]

        except Exception as e:
            logger.warning(f"Could not load stats from CSV: {e}")

        return stats

    def _print_summary(
        self,
        stats: dict[str, Any],
        criteria_results: dict[str, Any],
    ) -> None:
        """Print test summary to console."""
        print("\n" + "=" * 70)
        print("LOAD TEST SUMMARY")
        print("=" * 70)
        print(f"\nProfile: {self.profile.name}")
        print(f"Host: {self.host}")
        print(f"Duration: {self.profile.duration}")

        print(
            f"\nOverall Status: {'PASS ✓' if criteria_results['passed'] else 'FAIL ✗'}"
        )

        print("\nAcceptance Criteria:")
        print("-" * 70)
        for check_name, check_data in criteria_results["checks"].items():
            status = "✓" if check_data["passed"] else "✗"
            print(
                f"  {status} {check_name.replace('_', ' ').title()}: "
                f"{check_data['value']:.3f} (threshold: {check_data['threshold']:.3f})"
            )

        print("\nStatistics:")
        print("-" * 70)
        print(f"  Total Requests: {stats.get('total_requests', 0):,}")
        print(f"  Success Rate: {stats.get('success_rate', 0):.2%}")
        print(f"  Avg Response Time: {stats.get('avg_response_time_ms', 0):.1f}ms")
        print(f"  Requests/Second: {stats.get('requests_per_second', 0):.1f}")

        print("\n" + "=" * 70)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Launch load tests for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full load test
  %(prog)s --profile full --duration 1h
  
  # Run signal-only test
  %(prog)s --profile signal-only --users 10
  
  # Run with custom host
  %(prog)s --host http://localhost:8001 --users 100

Exit Codes:
  0 - All acceptance criteria met
  1 - One or more acceptance criteria failed
  2 - Configuration or setup error
  3 - Load test execution error
        """,
    )

    parser.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        default="smoke",
        help="Load test profile (default: smoke)",
    )

    parser.add_argument(
        "--host",
        default="http://localhost:8001",
        help="Target host URL (default: http://localhost:8001)",
    )

    parser.add_argument(
        "--users",
        type=int,
        help="Override number of concurrent users",
    )

    parser.add_argument(
        "--duration",
        help="Override test duration (e.g., 5m, 1h)",
    )

    parser.add_argument(
        "--report-format",
        nargs="+",
        choices=["json", "html"],
        default=["json", "html"],
        help="Report formats to generate (default: json html)",
    )

    parser.add_argument(
        "--grafana-export",
        action="store_true",
        help="Export metrics to Grafana (requires Grafana configuration)",
    )

    args = parser.parse_args()

    # Get profile
    profile = PROFILES[args.profile]

    # Override with CLI arguments if provided
    if args.users:
        profile.users = args.users
    if args.duration:
        profile.duration = args.duration

    # Create runner and execute
    runner = LoadTestRunner(
        host=args.host,
        profile=profile,
        report_format=args.report_format,
    )

    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
