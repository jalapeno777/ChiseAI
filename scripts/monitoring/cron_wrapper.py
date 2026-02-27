#!/usr/bin/env python3
"""Cron wrapper for ChiseAI monitoring scripts.

Sets up the environment for cron jobs:
- Loads .env file properly
- Sets up logging
- Changes to correct working directory
- Runs the specified script with proper error handling

P0 HARDENING ENHANCEMENTS:
- Execution timestamp recording to Redis
- Retry logic for failed scripts (3 attempts)
- Circuit breaker for consistently failing scripts
- Notification on repeated failures

Usage in crontab:
    0 * * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/hourly_health_check.py
    0 0 * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/daily_executive_summary.py
    0 */6 * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/checkpoint_gate_audit.py
"""

import os
import sys
import subprocess
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# P0 HARDENING: Redis imports
import redis

# P0 HARDENING: Redis configuration
REDIS_HOST = os.getenv(
    "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
)
REDIS_PORT = int(os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380")))

# P0 HARDENING: Redis keys for execution tracking
EXECUTION_PREFIX = "bmad:chiseai:monitoring:cron_wrapper"
SCRIPT_EXECUTION_KEY = f"{EXECUTION_PREFIX}:script:{{script_name}}"
CIRCUIT_BREAKER_KEY = f"{EXECUTION_PREFIX}:circuit_breaker"
FAILURE_LOG_KEY = f"{EXECUTION_PREFIX}:failure_log"

# P0 HARDENING: Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
CIRCUIT_BREAKER_THRESHOLD = 5  # Open circuit after 5 consecutive failures
CIRCUIT_BREAKER_WINDOW_MINUTES = 30  # Reset counter after 30 minutes
FAILURE_LOG_ENTRIES = 50


def get_redis() -> Optional[redis.Redis]:
    """P0 HARDENING: Get Redis connection."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        r.ping()
        return r
    except Exception as e:
        # Can't use logger here as it may not be initialized yet
        print(f"Redis connection failed: {e}", file=sys.stderr)
        return None


def record_script_execution(
    r: redis.Redis,
    script_name: str,
    status: str,
    exit_code: int = 0,
    attempts: int = 1,
    error_message: str = "",
) -> None:
    """P0 HARDENING: Record script execution details to Redis."""
    try:
        now = datetime.now(timezone.utc)
        key = SCRIPT_EXECUTION_KEY.format(script_name=script_name.replace("/", ":"))

        # Update execution tracking hash
        r.hset(
            key,
            mapping={
                "last_run": now.isoformat(),
                "status": status,
                "exit_code": str(exit_code),
                "attempts": str(attempts),
                "error": error_message[:500],  # Limit error message length
            },
        )

        # Add to execution history list (keep last 20)
        history_key = f"{key}:history"
        history_entry = f"{now.isoformat()}|{status}|{exit_code}|{attempts}"
        r.lpush(history_key, history_entry)
        r.ltrim(history_key, 0, 19)

        logger.debug(f"Recorded execution for {script_name}: {status}")
    except Exception as e:
        logger.error(f"Failed to record execution: {e}")


def check_circuit_breaker(r: redis.Redis, script_name: str) -> tuple[bool, str]:
    """P0 HARDENING: Check if circuit breaker is open for this script.

    Returns:
        (is_open, reason): Tuple indicating if circuit is open
    """
    try:
        key = CIRCUIT_BREAKER_KEY
        script_key = script_name.replace("/", ":")

        # Get current failure count
        failures = r.hget(key, f"{script_key}:failures")
        last_failure = r.hget(key, f"{script_key}:last_failure")

        if not failures:
            return False, ""

        failures = int(failures)

        # Check if we should reset the counter (window expired)
        if last_failure:
            last_dt = datetime.fromisoformat(last_failure)
            now = datetime.now(timezone.utc)
            elapsed_minutes = (now - last_dt).total_seconds() / 60

            if elapsed_minutes > CIRCUIT_BREAKER_WINDOW_MINUTES:
                # Reset counter - window expired
                r.hdel(key, f"{script_key}:failures")
                r.hdel(key, f"{script_key}:last_failure")
                logger.info(
                    f"Circuit breaker window expired for {script_name}, resetting counter"
                )
                return False, ""

        # Check if threshold exceeded
        if failures >= CIRCUIT_BREAKER_THRESHOLD:
            reason = f"Circuit breaker OPEN: {failures} failures in {CIRCUIT_BREAKER_WINDOW_MINUTES}min window"
            logger.error(f"{reason} for {script_name}")
            return True, reason

        return False, ""

    except Exception as e:
        logger.error(f"Error checking circuit breaker: {e}")
        return False, ""


def update_circuit_breaker(r: redis.Redis, script_name: str, success: bool) -> None:
    """P0 HARDENING: Update circuit breaker state based on execution result."""
    try:
        key = CIRCUIT_BREAKER_KEY
        script_key = script_name.replace("/", ":")
        now = datetime.now(timezone.utc)

        if success:
            # Reset on success
            r.hdel(key, f"{script_key}:failures")
            r.hdel(key, f"{script_key}:last_failure")
            logger.debug(f"Circuit breaker reset for {script_name} (success)")
        else:
            # Increment failure count
            new_count = r.hincrby(key, f"{script_key}:failures", 1)
            r.hset(key, f"{script_key}:last_failure", now.isoformat())

            logger.warning(
                f"Circuit breaker: {script_name} failure count = {new_count}"
            )

            # Log to failure log if threshold approaching
            if new_count >= CIRCUIT_BREAKER_THRESHOLD - 2:
                failure_entry = {
                    "timestamp": now.isoformat(),
                    "script": script_name,
                    "failure_count": new_count,
                    "threshold": CIRCUIT_BREAKER_THRESHOLD,
                }
                r.lpush(FAILURE_LOG_KEY, str(failure_entry))
                r.ltrim(FAILURE_LOG_KEY, 0, FAILURE_LOG_ENTRIES - 1)

    except Exception as e:
        logger.error(f"Error updating circuit breaker: {e}")


def notify_repeated_failures(script_name: str, attempts: int, final_error: str) -> None:
    """P0 HARDENING: Notify on repeated failures via Discord webhook."""
    try:
        import urllib.request
        import urllib.error
        import json

        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        if not webhook_url:
            logger.warning("No Discord webhook configured for failure notifications")
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        message = (
            f"🚨 **Cron Script Failure Alert**\n"
            f"Script: `{script_name}`\n"
            f"Time: {timestamp}\n"
            f"Attempts: {attempts}/{MAX_RETRIES}\n"
            f"Error: {final_error[:200]}"
        )

        data = json.dumps({"content": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                logger.info("Failure notification sent to Discord")
            else:
                logger.warning(f"Failed to send notification: {resp.status}")

    except Exception as e:
        logger.error(f"Error sending failure notification: {e}")


def setup_logging(log_dir: str = None) -> logging.Logger:
    """Setup logging for cron execution."""
    if log_dir is None:
        # Default to logs/cron/ relative to this script
        script_dir = Path(__file__).parent.absolute()
        log_dir = script_dir.parent.parent / "logs" / "cron"

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"cron-{timestamp}.log")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )

    return logging.getLogger(__name__)


def load_env_file(project_root: Path) -> None:
    """Load .env file from project root."""
    env_path = project_root / ".env"

    if env_path.exists():
        logger.info(f"Loading .env from {env_path}")
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Only set if not already set (don't override existing)
                    if key not in os.environ:
                        os.environ[key] = value
                        logger.debug(f"Set env var: {key}")
    else:
        logger.warning(f"No .env file found at {env_path}")


def find_project_root() -> Path:
    """Find the project root directory."""
    # Start from this script's location
    script_path = Path(__file__).absolute()

    # Go up to find the project root (look for .env or pyproject.toml or .git)
    current = script_path.parent
    while current != current.parent:
        if (
            (current / ".env").exists()
            or (current / ".git").exists()
            or (current / "pyproject.toml").exists()
        ):
            return current
        current = current.parent

    # Fallback: assume we're in scripts/monitoring/
    return script_path.parent.parent.parent


def run_script_with_retry(
    script_path: str, project_root: Path, r: Optional[redis.Redis], script_name: str
) -> tuple[int, int, str]:
    """P0 HARDENING: Run script with retry logic and circuit breaker.

    Returns:
        (exit_code, attempts, error_message)
    """
    # Check circuit breaker first
    if r:
        is_open, reason = check_circuit_breaker(r, script_name)
        if is_open:
            logger.error(f"Circuit breaker is OPEN for {script_name}: {reason}")
            return 1, 0, f"Circuit breaker open: {reason}"

    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Running {script_name} - Attempt {attempt}/{MAX_RETRIES}")

        exit_code, error = run_script_once(script_path, project_root)

        if exit_code == 0:
            # Success - reset circuit breaker
            if r:
                update_circuit_breaker(r, script_name, success=True)
                record_script_execution(r, script_name, "success", 0, attempt)
            logger.info(f"Script succeeded on attempt {attempt}")
            return 0, attempt, ""

        # Failure - record and retry
        last_error = error
        logger.warning(f"Script failed on attempt {attempt}: {error}")

        if attempt < MAX_RETRIES:
            logger.info(f"Waiting {RETRY_DELAY_SECONDS}s before retry...")
            import time

            time.sleep(RETRY_DELAY_SECONDS)

    # All retries exhausted
    logger.error(f"Script failed after {MAX_RETRIES} attempts")

    if r:
        update_circuit_breaker(r, script_name, success=False)
        record_script_execution(r, script_name, "failed", 1, MAX_RETRIES, last_error)

    # Notify on repeated failures
    notify_repeated_failures(script_name, MAX_RETRIES, last_error)

    return 1, MAX_RETRIES, last_error


def run_script_once(script_path: str, project_root: Path) -> tuple[int, str]:
    """P0 HARDENING: Run script once and return result."""
    # Resolve script path
    if os.path.isabs(script_path):
        full_script_path = Path(script_path)
    else:
        full_script_path = project_root / script_path

    if not full_script_path.exists():
        error = f"Script not found: {full_script_path}"
        logger.error(error)
        return 1, error

    # Ensure script is executable
    if not os.access(full_script_path, os.X_OK):
        logger.debug(f"Making script executable: {full_script_path}")
        os.chmod(full_script_path, 0o755)

    # Run the script
    logger.info(f"Running script: {full_script_path}")

    try:
        result = subprocess.run(
            [sys.executable, str(full_script_path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Log output
        if result.stdout:
            logger.info(f"Script stdout:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Script stderr:\n{result.stderr}")

        if result.returncode == 0:
            logger.info(
                f"Script completed successfully (exit code: {result.returncode})"
            )
            return 0, ""
        else:
            error = f"Script failed (exit code: {result.returncode})"
            if result.stderr:
                error += f" - {result.stderr[:200]}"
            logger.error(error)
            return result.returncode, error

    except subprocess.TimeoutExpired:
        error = "Script timed out after 5 minutes"
        logger.error(error)
        return 1, error
    except Exception as e:
        error = f"Error running script: {str(e)}"
        logger.exception(error)
        return 1, error


def main() -> int:
    """Main entry point with P0 HARDENING."""
    parser = argparse.ArgumentParser(
        description="Cron wrapper for ChiseAI monitoring scripts (P0 HARDENED)"
    )
    parser.add_argument(
        "script",
        help="Path to the script to run (relative to project root or absolute)",
    )
    parser.add_argument("--log-dir", help="Directory for log files", default=None)
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument("--no-retry", action="store_true", help="Disable retry logic")

    args = parser.parse_args()

    global logger
    logger = setup_logging(args.log_dir)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Cron wrapper started (P0 HARDENED)")
    logger.info(f"Script to run: {args.script}")

    # Find project root
    project_root = find_project_root()
    logger.info(f"Project root: {project_root}")

    # Change to project root
    original_cwd = os.getcwd()
    os.chdir(project_root)
    logger.info(f"Changed working directory to: {project_root}")

    # Load .env
    load_env_file(project_root)

    # P0 HARDENING: Connect to Redis
    r = get_redis()
    if r:
        logger.info("Redis connection established for execution tracking")
    else:
        logger.warning("Redis unavailable - execution tracking disabled")

    # Run the script with retry logic
    if args.no_retry:
        logger.info("Retry logic disabled via --no-retry")
        exit_code, _, error = run_script_once(args.script, project_root)
        if r:
            record_script_execution(
                r,
                args.script,
                "success" if exit_code == 0 else "failed",
                exit_code,
                1,
                error,
            )
    else:
        exit_code, attempts, error = run_script_with_retry(
            args.script, project_root, r, args.script
        )
        logger.info(
            f"Script completed with exit code {exit_code} after {attempts} attempt(s)"
        )

    # Restore original directory
    os.chdir(original_cwd)

    logger.info(f"Cron wrapper finished with exit code: {exit_code}")
    logger.info("=" * 60)

    return exit_code


if __name__ == "__main__":
    # Initialize logger (will be replaced in main())
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    sys.exit(main())
