#!/usr/bin/env python3
"""Cron evidence tracking utilities for monitoring scripts.

Provides functions to track cron job execution and cadence verification.
Used by all monitoring scripts to write evidence keys to Redis.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any, cast

import redis

logger = logging.getLogger(__name__)

# Job configurations with expected intervals in seconds
CRON_JOBS = {
    "pager": {
        "interval": 300,  # 5 minutes
        "description": "Pager alerts for critical conditions",
    },
    "signal-growth": {
        "interval": 1800,  # 30 minutes
        "description": "Signal growth detector",
    },
    "hourly-health": {
        "interval": 3600,  # 60 minutes
        "description": "Hourly health check",
    },
    "checkpoint-audit": {
        "interval": 21600,  # 6 hours
        "description": "6-hour checkpoint gate audit",
    },
}

# Redis key prefixes
KEY_PREFIX = "chise:cron"


def get_redis_connection() -> Any | None:
    """Get Redis connection for cron evidence tracking."""
    try:
        redis_host = os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        redis_port = int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )
        return redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def write_cron_evidence(
    job_name: str, status: str = "success", error_message: str | None = None
) -> bool:
    """Write cron execution evidence to Redis.

    Args:
        job_name: Name of the cron job (must be in CRON_JOBS)
        status: "success" or "error"
        error_message: Optional error message if status is "error"

    Returns:
        True if evidence was written successfully, False otherwise
    """
    if job_name not in CRON_JOBS:
        logger.error(f"Unknown cron job: {job_name}")
        return False

    r = get_redis_connection()
    if not r:
        logger.error("Cannot connect to Redis for cron evidence")
        return False

    try:
        now = datetime.now(UTC)
        timestamp = now.isoformat()
        job_config = CRON_JOBS[job_name]

        # Write evidence keys
        r.set(f"{KEY_PREFIX}:{job_name}:last_run", timestamp)
        r.set(f"{KEY_PREFIX}:{job_name}:expected_interval", str(job_config["interval"]))
        r.set(f"{KEY_PREFIX}:{job_name}:status", status)

        # Update missed count based on time since last run
        last_run_key = f"{KEY_PREFIX}:{job_name}:last_run"
        prev_run = r.get(last_run_key)
        missed_count_key = f"{KEY_PREFIX}:{job_name}:missed_count"

        if prev_run and prev_run != timestamp:
            # We have a previous run, calculate if we missed any
            try:
                prev_dt = datetime.fromisoformat(prev_run)
                elapsed = (now - prev_dt).total_seconds()
                expected = int(cast(Any, job_config["interval"]))

                # Calculate how many expected runs were missed
                # Allow 20% grace period
                grace_period = expected * 0.2
                if elapsed > expected + grace_period:
                    missed = int((elapsed - expected) / expected)
                    current_missed = int(r.get(missed_count_key) or "0")
                    r.set(missed_count_key, str(current_missed + missed))
                else:
                    # Reset missed count on successful run within window
                    r.set(missed_count_key, "0")
            except Exception as e:
                logger.warning(f"Error calculating missed runs: {e}")
                r.set(missed_count_key, "0")
        else:
            # First run or no previous data
            r.set(missed_count_key, "0")

        # Write error message if provided
        if error_message:
            r.set(f"{KEY_PREFIX}:{job_name}:last_error", error_message)
        else:
            # Clear any previous error
            r.delete(f"{KEY_PREFIX}:{job_name}:last_error")

        logger.info(f"Cron evidence written for {job_name}: {status} at {timestamp}")
        return True

    except Exception as e:
        logger.error(f"Error writing cron evidence for {job_name}: {e}")
        return False


def check_cron_cadence(r: Any | None = None) -> dict[str, Any]:
    """Check if all cron jobs are running on their expected cadence.

    Args:
        r: Optional Redis connection (will create one if not provided)

    Returns:
        Dictionary with overall status and per-job details:
        {
            "overall_status": "PASS" | "CHECK" | "FAIL",
            "jobs": {
                "pager": {
                    "status": "PASS" | "CHECK" | "FAIL",
                    "last_run": "...",
                    "elapsed_seconds": 123,
                    "expected_interval": 300,
                    "missed_count": 0,
                    "detail": "..."
                },
                ...
            }
        }
    """
    if r is None:
        r = get_redis_connection()

    if not r:
        return {
            "overall_status": "FAIL",
            "error": "Cannot connect to Redis",
            "jobs": {},
        }

    now = datetime.now(UTC)
    results: dict[str, Any] = {"overall_status": "PASS", "jobs": {}}

    for job_name, config in CRON_JOBS.items():
        job_result = {
            "status": "CHECK",
            "last_run": None,
            "elapsed_seconds": None,
            "expected_interval": config["interval"],
            "missed_count": None,
            "detail": "No data available",
        }

        try:
            # Get evidence keys
            last_run = r.get(f"{KEY_PREFIX}:{job_name}:last_run")
            missed_count = r.get(f"{KEY_PREFIX}:{job_name}:missed_count")
            r.get(f"{KEY_PREFIX}:{job_name}:status")

            if last_run:
                try:
                    last_dt = datetime.fromisoformat(last_run)
                    elapsed = (now - last_dt).total_seconds()
                    job_result["last_run"] = last_run
                    job_result["elapsed_seconds"] = int(elapsed)

                    expected = int(cast(Any, config["interval"]))
                    grace = expected * 0.2  # 20% grace period

                    if missed_count:
                        job_result["missed_count"] = int(missed_count)

                        # Determine status based on missed count and elapsed time
                        if int(missed_count) > 2:
                            job_result["status"] = "FAIL"
                            job_result["detail"] = (
                                f"Missed {missed_count} consecutive runs"
                            )
                        elif elapsed > expected + grace:
                            job_result["status"] = "CHECK"
                            job_result["detail"] = (
                                f"Last run {elapsed:.0f}s ago (expected every {expected}s)"
                            )
                        else:
                            job_result["status"] = "PASS"
                            job_result["detail"] = (
                                f"Running on schedule ({elapsed:.0f}s ago)"
                            )
                    else:
                        # No missed count data, check elapsed time only
                        if elapsed > expected + grace:
                            job_result["status"] = "CHECK"
                            job_result["detail"] = (
                                f"Last run {elapsed:.0f}s ago (expected every {expected}s)"
                            )
                        else:
                            job_result["status"] = "PASS"
                            job_result["detail"] = (
                                f"Running on schedule ({elapsed:.0f}s ago)"
                            )

                except Exception as e:
                    job_result["detail"] = f"Error parsing timestamp: {e}"
            else:
                job_result["detail"] = "No last_run data found"

        except Exception as e:
            job_result["detail"] = f"Error checking job: {e}"

        results["jobs"][job_name] = job_result

        # Update overall status
        if job_result["status"] == "FAIL":
            results["overall_status"] = "FAIL"
        elif job_result["status"] == "CHECK" and results["overall_status"] == "PASS":
            results["overall_status"] = "CHECK"

    return results


def format_cron_status(results: dict) -> str:
    """Format cron cadence results for display.

    Args:
        results: Results from check_cron_cadence()

    Returns:
        Formatted string suitable for logging or Discord messages
    """
    lines = []

    if "error" in results:
        return f"❌ Cron Cadence Check Failed: {results['error']}"

    status_emoji = {"PASS": "✅", "CHECK": "⚠️", "FAIL": "❌"}
    overall = results.get("overall_status", "UNKNOWN")
    emoji = status_emoji.get(overall, "❓")

    lines.append(f"{emoji} **Cron Cadence Status: {overall}**")
    lines.append("")

    for job_name, job_data in results.get("jobs", {}).items():
        status = job_data.get("status", "UNKNOWN")
        emoji = status_emoji.get(status, "❓")
        detail = job_data.get("detail", "No details")

        # Format elapsed time nicely
        elapsed = job_data.get("elapsed_seconds")
        if elapsed is not None:
            if elapsed < 60:
                elapsed_str = f"{elapsed}s ago"
            elif elapsed < 3600:
                elapsed_str = f"{elapsed // 60}m ago"
            else:
                elapsed_str = f"{elapsed // 3600}h ago"
            detail = f"{elapsed_str} - {detail}"

        lines.append(f"  {emoji} **{job_name}**: {detail}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)

    # Test writing evidence
    print("Testing cron evidence write...")
    success = write_cron_evidence("pager", status="success")
    print(f"Write result: {success}")

    # Test checking cadence
    print("\nTesting cron cadence check...")
    results = check_cron_cadence()
    print(format_cron_status(results))
