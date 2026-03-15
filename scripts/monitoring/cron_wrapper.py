#!/usr/bin/env python3
"""Cron wrapper for ChiseAI monitoring scripts.

Sets up the environment for cron jobs:
- Loads .env file properly
- Sets up logging
- Changes to correct working directory
- Runs the specified script with proper error handling

Usage in crontab:
    0 * * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/hourly_health_check.py
    0 0 * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/daily_executive_summary.py
    0 */6 * * * /usr/bin/python3 /path/to/scripts/monitoring/cron_wrapper.py scripts/monitoring/checkpoint_gate_audit.py
"""

import argparse
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Retry configuration for evidence writes
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5


def setup_logging(log_dir: str | Path | None = None) -> logging.Logger:
    """Setup logging for cron execution."""
    if log_dir is None:
        # Default to logs/cron/ relative to this script
        script_dir = Path(__file__).parent.absolute()
        log_dir = script_dir.parent.parent / "logs" / "cron"

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d")
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
        with open(env_path) as f:
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


def get_job_name_from_path(script_path: str | Path) -> str | None:
    """Extract job name from script path for cron evidence tracking."""
    job_mapping = {
        "pager_alerts.py": "pager",
        "signal_growth_detector.py": "signal-growth",
        "hourly_health_check.py": "hourly-health",
        "checkpoint_gate_audit.py": "checkpoint-audit",
        "bybit_truth_collector.py": "bybit-truth-collector",
    }
    basename = os.path.basename(script_path)
    return job_mapping.get(basename)


def write_cron_evidence_with_retry(
    job_name: str, status: str, error_msg: str | None = None
) -> tuple[bool, str | None]:
    """Write cron execution evidence to Redis with retry logic.

    Args:
        job_name: Name of the cron job
        status: "success" or "error"
        error_msg: Optional error message if status is "error"

    Returns:
        Tuple of (success: bool, invocation_id: str | None)
    """
    invocation_id = str(uuid.uuid4())
    last_error = None

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from cron_evidence import write_cron_evidence as write_evidence

            success, returned_id = write_evidence(
                job_name,
                status=status,
                error_message=error_msg,
                invocation_id=invocation_id,
                write_mode="wrapper",
            )

            if success:
                logger.info(
                    f"Cron evidence written for {job_name}: {status} "
                    f"(invocation_id={returned_id}, attempt={attempt})"
                )
                return True, returned_id
            else:
                logger.warning(
                    f"Cron evidence write returned False for {job_name} on attempt {attempt}"
                )
                last_error = "Write returned False"

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"Failed to write cron evidence for {job_name} on attempt {attempt}: {e}"
            )

        # Retry with backoff if not the last attempt
        if attempt < MAX_RETRY_ATTEMPTS:
            sleep_time = RETRY_DELAY_SECONDS * attempt
            logger.info(f"Retrying evidence write in {sleep_time}s...")
            time.sleep(sleep_time)

    # All retries exhausted
    logger.error(
        f"Failed to write cron evidence for {job_name} after {MAX_RETRY_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )
    return False, invocation_id


def run_script(script_path: str, project_root: Path) -> int:
    """Run the specified monitoring script."""
    # Resolve script path
    if os.path.isabs(script_path):
        full_script_path = Path(script_path)
    else:
        full_script_path = project_root / script_path

    if not full_script_path.exists():
        logger.error(f"Script not found: {full_script_path}")
        return 1

    # Ensure script is executable
    if not os.access(full_script_path, os.X_OK):
        logger.debug(f"Making script executable: {full_script_path}")
        os.chmod(full_script_path, 0o700)

    # Determine job name for cron evidence
    job_name = get_job_name_from_path(str(full_script_path))
    if job_name:
        logger.info(f"Job name for cron evidence: {job_name}")

    # Generate invocation ID for this execution
    execution_invocation_id = str(uuid.uuid4())
    logger.info(f"Execution invocation ID: {execution_invocation_id}")

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
            # Write success evidence with retry
            if job_name:
                success, evidence_id = write_cron_evidence_with_retry(
                    job_name, status="success"
                )
                if not success:
                    logger.error(
                        f"Failed to write success evidence for {job_name} "
                        f"despite script succeeding"
                    )
        else:
            logger.error(f"Script failed (exit code: {result.returncode})")
            # Write error evidence with retry
            if job_name:
                error_msg = result.stderr[:500] if result.stderr else "Script failed"
                success, evidence_id = write_cron_evidence_with_retry(
                    job_name, status="error", error_msg=error_msg
                )
                if not success:
                    logger.error(
                        f"Failed to write error evidence for {job_name} "
                        f"after script failure - this is a critical gap"
                    )

        return result.returncode

    except subprocess.TimeoutExpired:
        logger.error("Script timed out after 5 minutes")
        if job_name:
            success, evidence_id = write_cron_evidence_with_retry(
                job_name, status="error", error_msg="Timeout after 5 minutes"
            )
            if not success:
                logger.error(
                    f"Failed to write timeout evidence for {job_name} - "
                    f"this is a critical gap"
                )
        return 1
    except Exception as e:
        logger.exception(f"Error running script: {e}")
        if job_name:
            success, evidence_id = write_cron_evidence_with_retry(
                job_name, status="error", error_msg=str(e)[:500]
            )
            if not success:
                logger.error(
                    f"Failed to write error evidence for {job_name} - "
                    f"this is a critical gap"
                )
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cron wrapper for ChiseAI monitoring scripts"
    )
    parser.add_argument(
        "script",
        help="Path to the script to run (relative to project root or absolute)",
    )
    parser.add_argument("--log-dir", help="Directory for log files", default=None)
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    global logger
    logger = setup_logging(args.log_dir)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Cron wrapper started")
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

    # Run the script
    exit_code = run_script(args.script, project_root)

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
