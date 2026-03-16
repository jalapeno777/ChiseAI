#!/usr/bin/env python3
"""Qdrant Health Check CLI Script for ChiseAI.

Performs health checks on Qdrant and reports status with proper exit codes.
Designed for cron execution and monitoring system integration.

Usage:
    # Basic health check
    python scripts/monitoring/qdrant_health_check.py

    # JSON output for monitoring systems
    python scripts/monitoring/qdrant_health_check.py --json

    # Detailed metrics
    python scripts/monitoring/qdrant_health_check.py --verbose

    # Specific health checks
    python scripts/monitoring/qdrant_health_check.py --connectivity-only
    python scripts/monitoring/qdrant_health_check.py --latency-only

Exit Codes:
    0 - Healthy
    1 - Degraded
    2 - Unhealthy

Environment Variables:
    QDRANT_HOST - Qdrant host (default: host.docker.internal)
    QDRANT_PORT - Qdrant port (default: 6334)
    REDIS_HOST - Redis host for fallback queue (default: host.docker.internal)
    REDIS_PORT - Redis port (default: 6380)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

# Add project root to path
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)

from src.governance.memory.qdrant_health import (
    DEFAULT_QDRANT_HOST,
    DEFAULT_QDRANT_PORT,
    QdrantHealthMonitor,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Exit codes
EXIT_HEALTHY = 0
EXIT_DEGRADED = 1
EXIT_UNHEALTHY = 2


def load_env_file() -> None:
    """Load .env file from project root."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)


load_env_file()


def format_health_status(status: str) -> str:
    """Format health status with emoji."""
    status_emojis = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌",
        "unknown": "❓",
    }
    return f"{status_emojis.get(status, '❓')} {status.upper()}"


def check_connectivity(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Check Qdrant connectivity.

    Returns:
        Dictionary with check results
    """
    connected = monitor.check_connectivity()
    metrics = monitor.get_metrics()

    return {
        "check": "connectivity",
        "status": "healthy" if connected else "unhealthy",
        "connected": connected,
        "last_check": metrics["connectivity"]["last_check_at"],
    }


def check_latency(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Check Qdrant write latency.

    Returns:
        Dictionary with check results
    """
    latency_ms = monitor.get_write_latency()
    metrics = monitor.get_metrics()

    status = "healthy"
    if latency_ms > 1000:  # > 1 second
        status = "degraded"
    if latency_ms > 5000:  # > 5 seconds
        status = "unhealthy"

    return {
        "check": "latency",
        "status": status,
        "latency_ms": round(latency_ms, 2),
        "avg_latency_ms": metrics["latency"]["avg_ms"],
        "p95_latency_ms": metrics["latency"]["p95_ms"],
        "threshold_ms": 1000,
    }


def check_success_rate(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Check Qdrant write success rate.

    Returns:
        Dictionary with check results
    """
    success_rate = monitor.get_success_rate()
    metrics = monitor.get_metrics()

    status = "healthy"
    if success_rate < 0.95:  # < 95%
        status = "degraded"
    if success_rate < 0.90:  # < 90%
        status = "unhealthy"

    return {
        "check": "success_rate",
        "status": status,
        "success_rate": round(success_rate, 4),
        "success_rate_pct": f"{success_rate:.2%}",
        "attempts_total": metrics["success_rate"]["attempts_total"],
        "attempts_success": metrics["success_rate"]["attempts_success"],
        "attempts_failed": metrics["success_rate"]["attempts_failed"],
        "threshold": 0.95,
    }


def check_fallback_queue(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Check Redis fallback queue status.

    Returns:
        Dictionary with check results
    """
    metrics = monitor.get_metrics()
    queue_info = metrics["fallback_queue"]

    if not queue_info.get("available"):
        return {
            "check": "fallback_queue",
            "status": "unknown",
            "available": False,
            "error": queue_info.get("error", "Unknown error"),
        }

    queue_length = queue_info.get("queue_length", 0)
    utilization = queue_info.get("utilization", 0)

    status = "healthy"
    if utilization > 0.5:  # > 50% full
        status = "degraded"
    if utilization > 0.8:  # > 80% full
        status = "unhealthy"

    return {
        "check": "fallback_queue",
        "status": status,
        "available": True,
        "queue_length": queue_length,
        "max_size": queue_info.get("max_size", 10000),
        "utilization": round(utilization, 4),
        "utilization_pct": f"{utilization:.2%}",
    }


def check_errors(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Check error counts and types.

    Returns:
        Dictionary with check results
    """
    error_types = monitor.get_error_types()
    metrics = monitor.get_metrics()

    total_errors = sum(error_types.values())
    consecutive_failures = metrics["errors"]["consecutive_failures"]

    status = "healthy"
    if consecutive_failures >= 2:
        status = "degraded"
    if consecutive_failures >= 3:
        status = "unhealthy"

    return {
        "check": "errors",
        "status": status,
        "total_errors": total_errors,
        "error_types": error_types,
        "consecutive_failures": consecutive_failures,
        "last_error_at": metrics["errors"]["last_error_at"],
        "last_error_type": metrics["errors"]["last_error_type"],
        "last_error_message": metrics["errors"]["last_error_message"],
    }


def run_all_checks(monitor: QdrantHealthMonitor) -> dict[str, Any]:
    """Run all health checks.

    Returns:
        Dictionary with all check results
    """
    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {},
    }

    # Run each check
    results["checks"]["connectivity"] = check_connectivity(monitor)
    results["checks"]["latency"] = check_latency(monitor)
    results["checks"]["success_rate"] = check_success_rate(monitor)
    results["checks"]["fallback_queue"] = check_fallback_queue(monitor)
    results["checks"]["errors"] = check_errors(monitor)

    # Determine overall status
    statuses = [check["status"] for check in results["checks"].values()]

    if "unhealthy" in statuses:
        results["overall_status"] = "unhealthy"
    elif "degraded" in statuses:
        results["overall_status"] = "degraded"
    else:
        results["overall_status"] = "healthy"

    # Add full metrics if verbose
    results["full_metrics"] = monitor.get_metrics()

    return results


def format_output(results: dict[str, Any], verbose: bool = False) -> str:
    """Format check results for human-readable output.

    Args:
        results: Check results dictionary
        verbose: Include detailed metrics

    Returns:
        Formatted output string
    """
    lines = [
        f"Qdrant Health Check | {results['timestamp']}",
        "=" * 50,
        f"Overall Status: {format_health_status(results['overall_status'])}",
        "",
    ]

    # Connectivity
    conn = results["checks"]["connectivity"]
    lines.append(f"Connectivity: {format_health_status(conn['status'])}")
    lines.append(f"  Connected: {conn['connected']}")
    if conn.get("last_check"):
        lines.append(f"  Last Check: {conn['last_check']}")
    lines.append("")

    # Latency
    lat = results["checks"]["latency"]
    lines.append(f"Latency: {format_health_status(lat['status'])}")
    lines.append(f"  Current: {lat['latency_ms']}ms")
    lines.append(f"  Average: {lat['avg_latency_ms']}ms")
    lines.append(f"  P95: {lat['p95_latency_ms']}ms")
    lines.append("")

    # Success Rate
    sr = results["checks"]["success_rate"]
    lines.append(f"Success Rate: {format_health_status(sr['status'])}")
    lines.append(f"  Rate: {sr['success_rate_pct']}")
    lines.append(f"  Attempts: {sr['attempts_success']}/{sr['attempts_total']}")
    if sr["attempts_failed"] > 0:
        lines.append(f"  Failed: {sr['attempts_failed']}")
    lines.append("")

    # Fallback Queue
    fq = results["checks"]["fallback_queue"]
    lines.append(f"Fallback Queue: {format_health_status(fq['status'])}")
    lines.append(f"  Available: {fq.get('available', False)}")
    if fq.get("available"):
        lines.append(f"  Queue Length: {fq['queue_length']}")
        lines.append(f"  Utilization: {fq['utilization_pct']}")
    elif fq.get("error"):
        lines.append(f"  Error: {fq['error']}")
    lines.append("")

    # Errors
    err = results["checks"]["errors"]
    lines.append(f"Errors: {format_health_status(err['status'])}")
    lines.append(f"  Total Errors: {err['total_errors']}")
    lines.append(f"  Consecutive Failures: {err['consecutive_failures']}")
    if err.get("last_error_type"):
        lines.append(f"  Last Error: {err['last_error_type']}")
        if verbose and err.get("last_error_message"):
            lines.append(f"  Error Message: {err['last_error_message'][:100]}")
    lines.append("")

    # Verbose metrics
    if verbose and "full_metrics" in results:
        lines.append("=" * 50)
        lines.append("Detailed Metrics:")
        lines.append("=" * 50)
        metrics = results["full_metrics"]

        lines.append(f"Host: {metrics['config']['host']}")
        lines.append(f"Port: {metrics['config']['port']}")
        lines.append(f"Collection: {metrics['config']['collection']}")
        lines.append("")

        lines.append("Latency Samples:")
        lines.append(f"  Count: {metrics['latency']['samples']}")
        lines.append(f"  Max: {metrics['latency']['max_ms']}ms")
        lines.append("")

        lines.append("Error Breakdown:")
        for error_type, count in metrics["errors"]["counts"].items():
            lines.append(f"  {error_type}: {count}")
        lines.append("")

    return "\n".join(lines)


def get_exit_code(status: str) -> int:
    """Get exit code for a health status.

    Args:
        status: Health status string

    Returns:
        Exit code
    """
    if status == "healthy":
        return EXIT_HEALTHY
    elif status == "degraded":
        return EXIT_DEGRADED
    else:
        return EXIT_UNHEALTHY


def main() -> int:
    """Main entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Qdrant Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit Codes:
    0 - Healthy
    1 - Degraded
    2 - Unhealthy

Examples:
    %(prog)s                    # Basic health check
    %(prog)s --json            # JSON output
    %(prog)s --verbose         # Detailed output
    %(prog)s --connectivity-only  # Check connectivity only
        """,
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format for monitoring systems",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include detailed metrics in output",
    )
    parser.add_argument(
        "--connectivity-only",
        action="store_true",
        help="Only check connectivity",
    )
    parser.add_argument(
        "--latency-only",
        action="store_true",
        help="Only check latency",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("QDRANT_HOST", DEFAULT_QDRANT_HOST),
        help="Qdrant host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("QDRANT_PORT", DEFAULT_QDRANT_PORT)),
        help="Qdrant port",
    )
    parser.add_argument(
        "--collection",
        default="ChiseAI",
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--alert-threshold",
        type=int,
        default=3,
        help="Consecutive failures threshold for alerting",
    )

    args = parser.parse_args()

    # Create monitor
    monitor = QdrantHealthMonitor(
        host=args.host,
        port=args.port,
        collection=args.collection,
        alert_threshold_consecutive_failures=args.alert_threshold,
    )

    try:
        # Run checks
        if args.connectivity_only:
            result = check_connectivity(monitor)
            status = result["status"]

            if args.json:
                output = json.dumps(result, indent=2)
            else:
                output = f"Connectivity: {format_health_status(status)}"
                output += f"\nConnected: {result['connected']}"

            print(output)
            return get_exit_code(status)

        elif args.latency_only:
            result = check_latency(monitor)
            status = result["status"]

            if args.json:
                output = json.dumps(result, indent=2)
            else:
                output = f"Latency: {format_health_status(status)}"
                output += f"\nCurrent: {result['latency_ms']}ms"
                output += f"\nAverage: {result['avg_latency_ms']}ms"

            print(output)
            return get_exit_code(status)

        else:
            # Full health check
            results = run_all_checks(monitor)
            status = results["overall_status"]

            if args.json:
                output = json.dumps(results, indent=2, default=str)
            else:
                output = format_output(results, verbose=args.verbose)

            print(output)
            return get_exit_code(status)

    except Exception as e:
        error_result = {
            "error": str(e),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "unhealthy",
        }

        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ ERROR: {e}")

        return EXIT_UNHEALTHY


if __name__ == "__main__":
    sys.exit(main())
