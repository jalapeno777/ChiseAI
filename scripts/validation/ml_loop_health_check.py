#!/usr/bin/env python3
"""ML Loop Health Check Script.

This script checks the health status of all ML feedback loop components
and reports their status as ACTIVE, SHADOW, or DISABLED.

Usage:
    python3 scripts/validation/ml_loop_health_check.py [--format {table,json,simple}]
    python3 scripts/validation/ml_loop_health_check.py --component {orchestrator,matcher,analyzer,updater}

Exit Codes:
    0: All components healthy
    1: One or more components unhealthy
    2: Error running health check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ComponentStatus(Enum):
    """Status of an ML loop component."""

    ACTIVE = "ACTIVE"
    SHADOW = "SHADOW"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: ComponentStatus
    is_healthy: bool
    reason: str
    details: dict[str, Any]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Check ML feedback loop component health"
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "simple"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--component",
        choices=["orchestrator", "matcher", "analyzer", "updater", "all"],
        default="all",
        help="Check specific component only (default: all)",
    )
    parser.add_argument(
        "--redis-host",
        default="host.docker.internal",
        help="Redis host for health data (default: host.docker.internal)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=6380,
        help="Redis port (default: 6380)",
    )
    return parser.parse_args()


def check_orchestrator_health() -> ComponentHealth:
    """Check FeedbackOrchestrator health.

    Returns:
        ComponentHealth with status and details
    """
    try:
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        sys.path.insert(0, os.path.join(repo_root, "src"))
        from ml.feedback.orchestrator import FeedbackOrchestrator

        orchestrator = FeedbackOrchestrator()
        health = orchestrator.get_health_status()

        # Determine component status
        if health["is_healthy"]:
            status = ComponentStatus.ACTIVE
        elif health["total_iterations"] == 0:
            status = ComponentStatus.DISABLED
        else:
            status = ComponentStatus.SHADOW

        return ComponentHealth(
            name="FeedbackOrchestrator",
            status=status,
            is_healthy=health["is_healthy"],
            reason=health["reason"],
            details={
                "loop_status": health["loop_status"],
                "last_iteration_time": health["last_iteration_time"],
                "total_iterations": health["total_iterations"],
                "error_count": health["error_count"],
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="FeedbackOrchestrator",
            status=ComponentStatus.UNKNOWN,
            is_healthy=False,
            reason=f"Error checking health: {e}",
            details={},
        )


def check_matcher_health() -> ComponentHealth:
    """Check PredictionOutcomeMatcher health.

    Returns:
        ComponentHealth with status and details
    """
    try:
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        sys.path.insert(0, os.path.join(repo_root, "src"))
        from ml.feedback.matcher import PredictionOutcomeMatcher

        matcher = PredictionOutcomeMatcher()
        health = matcher.get_health_status()

        # Determine component status
        if health["is_healthy"]:
            status = ComponentStatus.ACTIVE
        elif health["total_matches"] == 0:
            status = ComponentStatus.DISABLED
        else:
            status = ComponentStatus.SHADOW

        return ComponentHealth(
            name="PredictionOutcomeMatcher",
            status=status,
            is_healthy=health["is_healthy"],
            reason=health["reason"],
            details={
                "is_active": health["is_active"],
                "last_match_time": health["last_match_time"],
                "total_matches": health["total_matches"],
                "match_rate": health["match_rate"],
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="PredictionOutcomeMatcher",
            status=ComponentStatus.UNKNOWN,
            is_healthy=False,
            reason=f"Error checking health: {e}",
            details={},
        )


def check_analyzer_health() -> ComponentHealth:
    """Check FeedbackAnalyzer health.

    Returns:
        ComponentHealth with status and details
    """
    try:
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        sys.path.insert(0, os.path.join(repo_root, "src"))
        from ml.feedback.analyzer import FeedbackAnalyzer

        analyzer = FeedbackAnalyzer()
        health = analyzer.get_health_status()

        # Determine component status
        if health["is_healthy"]:
            status = ComponentStatus.ACTIVE
        elif health["total_analyses"] == 0:
            status = ComponentStatus.DISABLED
        else:
            status = ComponentStatus.SHADOW

        return ComponentHealth(
            name="FeedbackAnalyzer",
            status=status,
            is_healthy=health["is_healthy"],
            reason=health["reason"],
            details={
                "is_active": health["is_active"],
                "last_analysis_time": health["last_analysis_time"],
                "total_analyses": health["total_analyses"],
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="FeedbackAnalyzer",
            status=ComponentStatus.UNKNOWN,
            is_healthy=False,
            reason=f"Error checking health: {e}",
            details={},
        )


def check_updater_health() -> ComponentHealth:
    """Check ModelUpdater health.

    Returns:
        ComponentHealth with status and details
    """
    try:
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        sys.path.insert(0, os.path.join(repo_root, "src"))
        from ml.feedback.updater import ModelUpdater

        updater = ModelUpdater()
        health = updater.get_health_status()

        # Determine component status
        if health["is_healthy"]:
            status = ComponentStatus.ACTIVE
        elif health["total_updates"] == 0:
            status = ComponentStatus.DISABLED
        else:
            status = ComponentStatus.SHADOW

        return ComponentHealth(
            name="ModelUpdater",
            status=status,
            is_healthy=health["is_healthy"],
            reason=health["reason"],
            details={
                "is_active": health["is_active"],
                "last_update_time": health["last_update_time"],
                "total_updates": health["total_updates"],
                "successful_updates": health["successful_updates"],
                "failed_updates": health["failed_updates"],
                "success_rate": health["success_rate"],
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="ModelUpdater",
            status=ComponentStatus.UNKNOWN,
            is_healthy=False,
            reason=f"Error checking health: {e}",
            details={},
        )


def check_redis_health(redis_host: str, redis_port: int) -> ComponentHealth | None:
    """Check Redis connectivity for health data.

    Args:
        redis_host: Redis host
        redis_port: Redis port

    Returns:
        ComponentHealth for Redis or None if not available
    """
    try:
        # Try to import and connect to Redis
        import os

        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        sys.path.insert(0, os.path.join(repo_root, "src"))
        from redis_state import redis_state_info

        info = redis_state_info()
        if info and "error" not in str(info).lower():
            return ComponentHealth(
                name="RedisHealthStore",
                status=ComponentStatus.ACTIVE,
                is_healthy=True,
                reason="Redis connection active",
                details={"host": redis_host, "port": redis_port},
            )
    except Exception as e:
        pass

    return ComponentHealth(
        name="RedisHealthStore",
        status=ComponentStatus.DISABLED,
        is_healthy=True,  # Not critical if Redis is not available
        reason="Redis not available - using in-memory health tracking",
        details={},
    )


def format_table(results: list[ComponentHealth]) -> str:
    """Format results as a table.

    Args:
        results: List of component health results

    Returns:
        Formatted table string
    """
    lines = []
    lines.append("=" * 100)
    lines.append("ML Feedback Loop Component Health Check")
    lines.append(f"Timestamp: {datetime.now(UTC).isoformat()}")
    lines.append("=" * 100)
    lines.append("")

    # Header
    lines.append(f"{'Component':<30} {'Status':<10} {'Healthy':<8} {'Reason':<50}")
    lines.append("-" * 100)

    # Rows
    for result in results:
        status_str = result.status.value
        healthy_str = "YES" if result.is_healthy else "NO"
        reason = (
            result.reason[:47] + "..." if len(result.reason) > 50 else result.reason
        )
        lines.append(
            f"{result.name:<30} {status_str:<10} {healthy_str:<8} {reason:<50}"
        )

    lines.append("-" * 100)

    # Summary
    healthy_count = sum(1 for r in results if r.is_healthy)
    total_count = len(results)
    lines.append(f"\nSummary: {healthy_count}/{total_count} components healthy")

    return "\n".join(lines)


def format_json(results: list[ComponentHealth]) -> str:
    """Format results as JSON.

    Args:
        results: List of component health results

    Returns:
        JSON string
    """
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "components": [],
        "summary": {
            "total": len(results),
            "healthy": sum(1 for r in results if r.is_healthy),
            "unhealthy": sum(1 for r in results if not r.is_healthy),
        },
    }

    for result in results:
        data["components"].append(
            {
                "name": result.name,
                "status": result.status.value,
                "is_healthy": result.is_healthy,
                "reason": result.reason,
                "details": result.details,
            }
        )

    return json.dumps(data, indent=2)


def format_simple(results: list[ComponentHealth]) -> str:
    """Format results as simple status line.

    Args:
        results: List of component health results

    Returns:
        Simple status string
    """
    healthy_count = sum(1 for r in results if r.is_healthy)
    total_count = len(results)

    if healthy_count == total_count:
        return f"OK: All {total_count} components healthy"
    else:
        unhealthy = [r.name for r in results if not r.is_healthy]
        return f"WARNING: {healthy_count}/{total_count} healthy. Unhealthy: {', '.join(unhealthy)}"


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0=healthy, 1=unhealthy, 2=error)
    """
    args = parse_args()

    try:
        results: list[ComponentHealth] = []

        # Check requested components
        if args.component in ("orchestrator", "all"):
            results.append(check_orchestrator_health())

        if args.component in ("matcher", "all"):
            results.append(check_matcher_health())

        if args.component in ("analyzer", "all"):
            results.append(check_analyzer_health())

        if args.component in ("updater", "all"):
            results.append(check_updater_health())

        # Check Redis (informational only)
        if args.component == "all":
            redis_health = check_redis_health(args.redis_host, args.redis_port)
            if redis_health:
                results.append(redis_health)

        # Format output
        if args.format == "table":
            print(format_table(results))
        elif args.format == "json":
            print(format_json(results))
        else:  # simple
            print(format_simple(results))

        # Determine exit code
        # Filter out RedisHealthStore for health determination
        component_results = [r for r in results if r.name != "RedisHealthStore"]
        if all(r.is_healthy for r in component_results):
            return 0
        else:
            return 1

    except Exception as e:
        print(f"ERROR: Failed to run health check: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
