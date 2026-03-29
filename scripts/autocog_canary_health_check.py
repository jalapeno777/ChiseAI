#!/usr/bin/env python3
"""
CANARY Mode Health Check Script.

Performs an on-demand health check of the CANARY mode validation status.
Exit codes: 0=healthy, 1=warnings, 2=critical

Usage:
    python3 scripts/autocog_canary_health_check.py [--dry-run] [--verbose]

This script checks:
    - Current mode (should be "canary")
    - Divergence score (last N cycles)
    - Consecutive non-regression count
    - Position fraction used
    - Trade count today
    - Error count
    - Notification suppression status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Try to import redis, but handle gracefully if not available
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Constants from runtime_integration.py
DIVERGENCE_THRESHOLD_LOW = 0.15
DIVERGENCE_THRESHOLD_HIGH = 0.35
DIVERGENCE_THRESHOLD_CRITICAL = 0.45
DRIFT_THRESHOLD_FOR_DEMOTION = 0.40
CANARY_MAX_POSITION_FRACTION = 0.01
REQUIRED_CONSECUTIVE_CHECKS = 5
AUTOCOG_CYCLE_DIR = "_bmad-output/autocog/cycles"
REDIS_KEY_PREFIX = "bmad:chiseai:autocog"


def get_repo_root() -> Path:
    """Get the repository root directory."""
    env_root = Path(__file__).parent.parent.resolve()
    marker = env_root / "pyproject.toml"
    if marker.exists():
        return env_root
    # Fallback to current working directory
    return Path.cwd()


def load_latest_cycle_artifact() -> dict[str, Any] | None:
    """Load the most recent CANARY cycle artifact from _bmad-output/autocog/cycles/."""
    repo_root = get_repo_root()
    cycles_dir = repo_root / AUTOCOG_CYCLE_DIR

    if not cycles_dir.exists():
        return None

    # Find all cycle artifacts, sorted by modification time
    cycle_files = sorted(
        cycles_dir.glob("autocog-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )

    if not cycle_files:
        return None

    try:
        with open(cycle_files[0], encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def check_redis_health() -> dict[str, Any]:
    """Check Redis for CANARY state and return relevant metrics."""
    if not REDIS_AVAILABLE:
        return {
            "available": False,
            "error": "redis package not available",
            "current_mode": "unknown",
            "divergence_score": None,
            "consecutive_non_regression_count": 0,
            "position_fraction": None,
            "trade_count_today": 0,
            "error_count": 0,
            "notification_suppressed": None,
        }

    try:
        # Try to connect using common Redis connection methods
        redis_client = redis.Redis.from_url(
            "redis://host.docker.internal:6380/1", socket_connect_timeout=2
        )
        redis_client.ping()

        # Check current mode
        current_mode = redis_client.hget(f"{REDIS_KEY_PREFIX}:state", "current_mode")
        current_mode = current_mode.decode("utf-8") if current_mode else "unknown"

        # Get divergence score
        divergence_score = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "divergence_score"
        )
        divergence_score = (
            float(divergence_score.decode("utf-8")) if divergence_score else None
        )

        # Get consecutive non-regression count
        consecutive_count = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:state", "consecutive_non_regression_count"
        )
        consecutive_count = (
            int(consecutive_count.decode("utf-8")) if consecutive_count else 0
        )

        # Get position fraction
        position_fraction = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "position_fraction"
        )
        position_fraction = (
            float(position_fraction.decode("utf-8")) if position_fraction else None
        )

        # Get trade count today
        trade_count = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:metrics", "trade_count_today"
        )
        trade_count = int(trade_count.decode("utf-8")) if trade_count else 0

        # Get error count
        error_count = redis_client.hget(f"{REDIS_KEY_PREFIX}:metrics", "error_count")
        error_count = int(error_count.decode("utf-8")) if error_count else 0

        # Get notification suppression status
        notification_suppressed = redis_client.hget(
            f"{REDIS_KEY_PREFIX}:state", "notification_suppressed"
        )
        notification_suppressed = (
            notification_suppressed.decode("utf-8") == "true"
            if notification_suppressed
            else None
        )

        return {
            "available": True,
            "current_mode": current_mode,
            "divergence_score": divergence_score,
            "consecutive_non_regression_count": consecutive_count,
            "position_fraction": position_fraction,
            "trade_count_today": trade_count,
            "error_count": error_count,
            "notification_suppressed": notification_suppressed,
        }

    except redis.RedisError as e:
        return {
            "available": False,
            "error": str(e),
            "current_mode": "unknown",
            "divergence_score": None,
            "consecutive_non_regression_count": 0,
            "position_fraction": None,
            "trade_count_today": 0,
            "error_count": 0,
            "notification_suppressed": None,
        }


def check_experiment_limits(cycle_data: dict[str, Any] | None) -> dict[str, Any]:
    """Verify experiments are running within limits (max 1 per cycle)."""
    if cycle_data is None:
        return {"ok": None, "message": "No cycle data available"}

    experiments_run = cycle_data.get("experiments_run", 0)

    if experiments_run > 1:
        return {
            "ok": False,
            "message": f"Too many experiments in cycle: {experiments_run} (max: 1)",
            "experiments_run": experiments_run,
        }

    return {
        "ok": True,
        "message": "Experiments within limits",
        "experiments_run": experiments_run,
    }


def evaluate_health_status(
    redis_data: dict[str, Any], cycle_data: dict[str, Any] | None
) -> tuple[int, list[str], list[str]]:
    """
    Evaluate the overall health status based on collected data.

    Returns:
        Tuple of (exit_code, info_messages, error_messages)
        exit_code: 0=healthy, 1=warnings, 2=critical
    """
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    # Check mode
    current_mode = redis_data.get("current_mode", "unknown")
    if current_mode != "canary":
        if current_mode == "unknown":
            warnings.append("Current mode is unknown (Redis may not be populated yet)")
        else:
            warnings.append(f"Current mode is '{current_mode}', expected 'canary'")

    # Check divergence
    divergence = redis_data.get("divergence_score")
    if divergence is not None:
        if divergence >= DRIFT_THRESHOLD_FOR_DEMOTION:
            errors.append(
                f"CRITICAL: Divergence {divergence:.3f} exceeds demotion threshold {DRIFT_THRESHOLD_FOR_DEMOTION}"
            )
        elif divergence >= DIVERGENCE_THRESHOLD_HIGH:
            warnings.append(
                f"WARNING: Divergence {divergence:.3f} is elevated (threshold: {DIVERGENCE_THRESHOLD_HIGH})"
            )
        elif divergence >= DIVERGENCE_THRESHOLD_LOW:
            warnings.append(
                f"CAUTION: Divergence {divergence:.3f} is borderline (threshold: {DIVERGENCE_THRESHOLD_LOW})"
            )
        else:
            info.append(f"Divergence {divergence:.3f} is within acceptable range")
    else:
        info.append("No divergence data available yet")

    # Check consecutive non-regression count
    consecutive = redis_data.get("consecutive_non_regression_count", 0)
    if consecutive >= REQUIRED_CONSECUTIVE_CHECKS:
        info.append(
            f"Consecutive non-regression count ({consecutive}) meets promotion threshold"
        )
    else:
        info.append(
            f"Consecutive non-regression checks: {consecutive}/{REQUIRED_CONSECUTIVE_CHECKS}"
        )

    # Check position fraction
    position_frac = redis_data.get("position_fraction")
    if position_frac is not None:
        if position_frac > CANARY_MAX_POSITION_FRACTION:
            errors.append(
                f"CRITICAL: Position fraction {position_frac:.4f} exceeds CANARY limit {CANARY_MAX_POSITION_FRACTION}"
            )
        else:
            info.append(f"Position fraction {position_frac:.4f} is within CANARY limit")
    else:
        info.append("No position fraction data available")

    # Check trade count
    trade_count = redis_data.get("trade_count_today", 0)
    info.append(f"Trades today: {trade_count}")

    # Check error count
    error_count = redis_data.get("error_count", 0)
    if error_count > 10:
        warnings.append(f"Error count is elevated: {error_count}")
    elif error_count > 0:
        info.append(f"Errors: {error_count}")
    else:
        info.append("No errors recorded")

    # Check notification suppression
    notification_suppressed = redis_data.get("notification_suppressed")
    if notification_suppressed is not None:
        if notification_suppressed:
            info.append("Notification suppression is active (expected in CANARY)")
        else:
            warnings.append("Notification suppression is NOT active (may cause spam)")
    else:
        info.append("Notification suppression status unknown")

    # Check experiment limits
    exp_check = check_experiment_limits(cycle_data)
    if exp_check["ok"] is False:
        errors.append(exp_check["message"])
    elif exp_check["ok"] is True:
        info.append(exp_check["message"])

    # Determine exit code
    if errors:
        return 2, info, errors
    elif warnings:
        return 1, info, errors
    else:
        return 0, info, errors


def print_report(
    redis_data: dict[str, Any], cycle_data: dict[str, Any] | None, verbose: bool = False
) -> None:
    """Print a human-readable health report."""
    print("\n" + "=" * 60)
    print("CANARY Mode Health Check Report")
    print(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    print("\n--- Redis Connectivity ---")
    if redis_data["available"]:
        print("  Status: AVAILABLE")
    else:
        print(f"  Status: UNAVAILABLE ({redis_data.get('error', 'unknown error')})")

    print("\n--- Current Mode ---")
    print(f"  Mode: {redis_data.get('current_mode', 'unknown')}")

    print("\n--- Key Metrics ---")
    div = redis_data.get("divergence_score")
    print(
        f"  Divergence Score: {div:.3f}"
        if div is not None
        else "  Divergence Score: N/A"
    )
    print(
        f"  Consecutive Non-Regression: {redis_data.get('consecutive_non_regression_count', 0)}/{REQUIRED_CONSECUTIVE_CHECKS}"
    )
    pos = redis_data.get("position_fraction")
    print(
        f"  Position Fraction: {pos:.4f}"
        if pos is not None
        else "  Position Fraction: N/A"
    )
    print(f"  Trade Count Today: {redis_data.get('trade_count_today', 0)}")
    print(f"  Error Count: {redis_data.get('error_count', 0)}")

    print("\n--- Notification Status ---")
    ns = redis_data.get("notification_suppressed")
    if ns is not None:
        print(f"  Suppressed: {ns}")
    else:
        print("  Status: Unknown")

    if cycle_data:
        print("\n--- Latest Cycle Artifact ---")
        print(f"  Run ID: {cycle_data.get('run_id', 'N/A')}")
        print(f"  Status: {cycle_data.get('status', 'N/A')}")
        print(f"  Experiments Run: {cycle_data.get('experiments_run', 0)}")
        print(f"  Promotions: {cycle_data.get('promotions', 0)}")
        print(f"  Rejections: {cycle_data.get('rejections', 0)}")

    exit_code, info_messages, error_messages = evaluate_health_status(
        redis_data, cycle_data
    )

    print("\n--- Status Evaluation ---")
    for msg in info_messages:
        print(f"  [INFO] {msg}")
    for msg in error_messages:
        print(f"  [ERROR] {msg}")

    if verbose:
        print("\n--- Thresholds Reference ---")
        print(f"  DIVERGENCE_THRESHOLD_LOW: {DIVERGENCE_THRESHOLD_LOW}")
        print(f"  DIVERGENCE_THRESHOLD_HIGH: {DIVERGENCE_THRESHOLD_HIGH}")
        print(f"  DRIFT_THRESHOLD_FOR_DEMOTION: {DRIFT_THRESHOLD_FOR_DEMOTION}")
        print(f"  CANARY_MAX_POSITION_FRACTION: {CANARY_MAX_POSITION_FRACTION}")
        print(f"  REQUIRED_CONSECUTIVE_CHECKS: {REQUIRED_CONSECUTIVE_CHECKS}")

    print("\n" + "=" * 60)
    status_map = {0: "HEALTHY", 1: "WARNINGS", 2: "CRITICAL"}
    print(f"Overall Status: {status_map[exit_code]} (exit code: {exit_code})")
    print("=" * 60 + "\n")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CANARY Mode Health Check Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 - HEALTHY: All metrics within acceptable ranges
  1 - WARNINGS: Some metrics are elevated but not critical
  2 - CRITICAL: One or more metrics exceed critical thresholds

Examples:
  python3 scripts/autocog_canary_health_check.py
  python3 scripts/autocog_canary_health_check.py --dry-run
  python3 scripts/autocog_canary_health_check.py --verbose
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Perform dry run (don't check Redis)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output including threshold reference",
    )

    args = parser.parse_args()

    # Load latest cycle artifact
    cycle_data = load_latest_cycle_artifact()

    # Check Redis health
    if args.dry_run:
        redis_data = {
            "available": False,
            "error": "dry-run mode",
            "current_mode": "canary",
            "divergence_score": 0.08,
            "consecutive_non_regression_count": 3,
            "position_fraction": 0.005,
            "trade_count_today": 5,
            "error_count": 0,
            "notification_suppressed": True,
        }
        print("[DRY RUN] Using simulated CANARY health data")
    else:
        redis_data = check_redis_health()

    # Print report
    print_report(redis_data, cycle_data, verbose=args.verbose)

    # Determine exit code
    exit_code, _, _ = evaluate_health_status(redis_data, cycle_data)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
