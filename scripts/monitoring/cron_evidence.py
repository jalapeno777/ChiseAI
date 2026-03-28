#!/usr/bin/env python3
"""Cron evidence tracking utilities for monitoring scripts.

Provides functions to track cron job execution and cadence verification.
Used by all monitoring scripts to write evidence keys to Redis.
"""

import logging
import os
import time
import uuid
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
    "bybit-truth-collector": {
        "interval": 1800,  # 30 minutes
        "description": "Bybit truth data collector for G12 freshness",
    },
}

# Redis key prefixes
KEY_PREFIX = "chise:cron"

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5


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


def _calculate_missed_count(
    r: Any, job_name: str, now: datetime, timestamp: str
) -> int:
    """Calculate the number of missed runs based on time since last run.

    Args:
        r: Redis connection
        job_name: Name of the cron job
        now: Current datetime
        timestamp: Current run timestamp string

    Returns:
        Number of missed runs (0 if none or error)
    """
    job_config = CRON_JOBS[job_name]
    last_run_key = f"{KEY_PREFIX}:{job_name}:last_run"

    try:
        prev_run = r.get(last_run_key)
        if prev_run and prev_run != timestamp:
            try:
                prev_dt = datetime.fromisoformat(prev_run)
                elapsed = (now - prev_dt).total_seconds()
                expected = int(cast(Any, job_config["interval"]))

                # Calculate how many expected runs were missed
                # Allow 20% grace period
                grace_period = expected * 0.2
                if elapsed > expected + grace_period:
                    missed = int((elapsed - expected) / expected)
                    return missed
            except Exception as e:
                logger.warning(f"Error calculating missed runs: {e}")
    except Exception as e:
        logger.warning(f"Error reading previous run timestamp: {e}")

    return 0


def _write_evidence_with_pipeline(
    r: Any,
    job_name: str,
    status: str,
    timestamp: str,
    invocation_id: str,
    write_mode: str,
    error_message: str | None,
) -> bool:
    """Write evidence using Redis pipeline for atomicity.

    Args:
        r: Redis connection
        job_name: Name of the cron job
        status: "success" or "error"
        timestamp: ISO format timestamp string
        invocation_id: Unique invocation ID for traceability
        write_mode: "wrapper" or "direct"
        error_message: Optional error message if status is "error"

    Returns:
        True if evidence was written successfully, False otherwise
    """
    job_config = CRON_JOBS[job_name]
    now = datetime.fromisoformat(timestamp)

    # Calculate or reset missed count
    # On success: reset to 0 (job ran successfully, no missed runs)
    # On error: calculate based on elapsed time since last run
    if status == "success":
        missed_count = 0
    else:
        missed_count = _calculate_missed_count(r, job_name, now, timestamp)

    # Use pipeline for atomic write
    pipe = r.pipeline()

    # Write all evidence keys atomically
    pipe.set(f"{KEY_PREFIX}:{job_name}:last_run", timestamp)
    pipe.set(f"{KEY_PREFIX}:{job_name}:expected_interval", str(job_config["interval"]))
    pipe.set(f"{KEY_PREFIX}:{job_name}:status", status)
    pipe.set(f"{KEY_PREFIX}:{job_name}:invocation_id", invocation_id)
    pipe.set(f"{KEY_PREFIX}:{job_name}:write_mode", write_mode)
    pipe.set(f"{KEY_PREFIX}:{job_name}:missed_count", str(missed_count))

    # Handle error message
    if error_message:
        pipe.set(f"{KEY_PREFIX}:{job_name}:last_error", error_message)
    else:
        pipe.delete(f"{KEY_PREFIX}:{job_name}:last_error")

    # Execute pipeline
    results = pipe.execute()

    # Verify write succeeded - check that no command returned None (error)
    # Note: delete() returns 0 or 1 (int), which is acceptable
    if any(r is None for r in results):
        logger.warning(f"Pipeline write returned None for some commands: {results}")
        return False

    return True


def _verify_evidence_write(
    r: Any, job_name: str, timestamp: str, invocation_id: str
) -> bool:
    """Verify that evidence was written correctly.

    Args:
        r: Redis connection
        job_name: Name of the cron job
        timestamp: Expected timestamp
        invocation_id: Expected invocation ID

    Returns:
        True if evidence matches expected values
    """
    try:
        stored_timestamp = r.get(f"{KEY_PREFIX}:{job_name}:last_run")
        stored_invocation_id = r.get(f"{KEY_PREFIX}:{job_name}:invocation_id")

        if stored_timestamp != timestamp:
            logger.warning(
                f"Timestamp mismatch: expected {timestamp}, got {stored_timestamp}"
            )
            return False

        if stored_invocation_id != invocation_id:
            logger.warning(
                f"Invocation ID mismatch: expected {invocation_id}, got {stored_invocation_id}"
            )
            return False

        return True
    except Exception as e:
        logger.error(f"Error verifying evidence write: {e}")
        return False


def write_cron_evidence(
    job_name: str,
    status: str = "success",
    error_message: str | None = None,
    invocation_id: str | None = None,
    write_mode: str = "direct",
) -> tuple[bool, str | None]:
    """Write cron execution evidence to Redis.

    Args:
        job_name: Name of the cron job (must be in CRON_JOBS)
        status: "success" or "error"
        error_message: Optional error message if status is "error"
        invocation_id: Optional unique invocation ID for traceability.
                      If not provided, a new UUID will be generated.
        write_mode: "wrapper" if called from cron_wrapper, "direct" otherwise

    Returns:
        Tuple of (success: bool, invocation_id: str | None)
        - success: True if evidence was written successfully
        - invocation_id: The invocation ID used (or None if failed before generation)
    """
    if job_name not in CRON_JOBS:
        logger.error(f"Unknown cron job: {job_name}")
        return False, None

    # Generate invocation ID if not provided
    if invocation_id is None:
        invocation_id = str(uuid.uuid4())

    r = get_redis_connection()
    if not r:
        logger.error("Cannot connect to Redis for cron evidence")
        return False, invocation_id

    now = datetime.now(UTC)
    timestamp = now.isoformat()

    # Retry loop for resilience
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            # Write evidence atomically with pipeline
            write_success = _write_evidence_with_pipeline(
                r, job_name, status, timestamp, invocation_id, write_mode, error_message
            )

            if not write_success:
                logger.warning(f"Pipeline write returned False on attempt {attempt}")
                last_error = "Pipeline write failed"
                if attempt < MAX_RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)  # Exponential backoff
                continue

            # Verify the write
            if _verify_evidence_write(r, job_name, timestamp, invocation_id):
                logger.info(
                    f"Cron evidence written for {job_name}: {status} at {timestamp} "
                    f"(invocation_id={invocation_id}, mode={write_mode})"
                )
                return True, invocation_id
            else:
                logger.warning(f"Evidence verification failed on attempt {attempt}")
                last_error = "Verification failed"
                if attempt < MAX_RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue

        except Exception as e:
            last_error = str(e)
            logger.error(
                f"Error writing cron evidence for {job_name} on attempt {attempt}: {e}"
            )
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            continue

    # All retries exhausted
    logger.error(
        f"Failed to write cron evidence for {job_name} after {MAX_RETRY_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )
    return False, invocation_id


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
                    "invocation_id": "...",
                    "write_mode": "...",
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
            "invocation_id": None,
            "write_mode": None,
            "detail": "No data available",
        }

        try:
            # Get evidence keys
            last_run = r.get(f"{KEY_PREFIX}:{job_name}:last_run")
            missed_count = r.get(f"{KEY_PREFIX}:{job_name}:missed_count")
            invocation_id = r.get(f"{KEY_PREFIX}:{job_name}:invocation_id")
            write_mode = r.get(f"{KEY_PREFIX}:{job_name}:write_mode")
            r.get(f"{KEY_PREFIX}:{job_name}:status")

            # Store invocation_id and write_mode for traceability
            if invocation_id:
                job_result["invocation_id"] = invocation_id
            if write_mode:
                job_result["write_mode"] = write_mode

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
    success, invocation_id = write_cron_evidence("pager", status="success")
    print(f"Write result: success={success}, invocation_id={invocation_id}")

    # Test checking cadence
    print("\nTesting cron cadence check...")
    results = check_cron_cadence()
    print(format_cron_status(results))
