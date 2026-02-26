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

import os
import sys
import subprocess
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path


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
        else:
            logger.error(f"Script failed (exit code: {result.returncode})")

        return result.returncode

    except subprocess.TimeoutExpired:
        logger.error(f"Script timed out after 5 minutes")
        return 1
    except Exception as e:
        logger.exception(f"Error running script: {e}")
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
