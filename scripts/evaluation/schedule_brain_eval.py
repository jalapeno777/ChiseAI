#!/usr/bin/env python3
"""BrainEval scheduling script.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Schedules and runs MiniBrainEval at specified cadences (6h, daily, weekly).
Saves results to timestamped JSON files in the output directory.

Usage:
    python schedule_brain_eval.py --cadence 6h --output-dir _bmad-output/brain-eval
    python schedule_brain_eval.py --cadence daily --output-dir _bmad-output/brain-eval
    python schedule_brain_eval.py --cadence weekly --output-dir _bmad-output/brain-eval
    python schedule_brain_eval.py --cadence 6h --dry-run  # For testing

Exit codes:
    0: Success
    1: Failure
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

try:
    from src.evaluation.mini_brain_eval import MiniBrainEval
except ImportError as e:
    print(f"ERROR: Failed to import MiniBrainEval: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import redis
except ImportError:
    redis = None  # type: ignore


# Configure logging
def setup_logging(log_dir: Path) -> logging.Logger:
    """Set up logging to file and console.

    Args:
        log_dir: Directory for log files

    Returns:
        Configured logger
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger("schedule_brain_eval")
    logger.setLevel(logging.INFO)

    # File handler
    log_file = log_dir / f"schedule_{datetime.now(UTC).strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_output_filename(cadence: str) -> str:
    """Generate output filename based on cadence.

    Args:
        cadence: Evaluation cadence (6h, daily, weekly)

    Returns:
        Filename string with timestamp

    Examples:
        6h: 2026-03-01T06-00-00.json
        daily: 2026-03-01.json
        weekly: 2026-W09.json
    """
    now = datetime.now(UTC)

    if cadence == "6h":
        # Include hour for 6-hour cadence
        return now.strftime("%Y-%m-%dT%H-00-00.json")
    elif cadence == "daily":
        # Date only for daily
        return now.strftime("%Y-%m-%d.json")
    elif cadence == "weekly":
        # ISO week format for weekly
        iso_calendar = now.isocalendar()
        return f"{iso_calendar[0]}-W{iso_calendar[1]:02d}.json"
    else:
        raise ValueError(f"Invalid cadence: {cadence}")


def save_result(result: dict[str, Any], output_path: Path) -> None:
    """Save evaluation result to JSON file.

    Args:
        result: Evaluation result dictionary
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)


def run_evaluation(
    cadence: str,
    output_dir: Path,
    dry_run: bool = False,
    redis_client: Any = None,
) -> int:
    """Run evaluation at specified cadence.

    Args:
        cadence: Evaluation cadence (6h, daily, weekly)
        output_dir: Base output directory
        dry_run: If True, don't actually run evaluation
        redis_client: Optional Redis client

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    log_dir = output_dir / "logs"
    logger = setup_logging(log_dir)

    logger.info(f"Starting {cadence} evaluation")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Dry run: {dry_run}")

    if dry_run:
        logger.info("DRY RUN: Skipping actual evaluation")

        # Create mock result for dry run
        mock_result = {
            "eval_id": "dry-run-test",
            "timestamp": datetime.now(UTC).isoformat(),
            "cadence": cadence,
            "kpis": {"status": "dry_run"},
            "proxies": {},
            "data_freshness": {},
            "issues": [],
            "mitigations": [],
        }

        # Determine output path
        cadence_dir = output_dir / cadence
        output_file = get_output_filename(cadence)
        output_path = cadence_dir / output_file

        logger.info(f"DRY RUN: Would save result to {output_path}")
        save_result(mock_result, output_path)
        logger.info(f"DRY RUN: Saved mock result to {output_path}")

        return 0

    try:
        # Initialize MiniBrainEval
        evaluator = MiniBrainEval(
            redis_client=redis_client,
            influxdb_client=None,  # Placeholder for future InfluxDB integration
            brain_evaluator=None,  # Placeholder for future BrainEvaluator integration
        )

        # Run evaluation based on cadence
        logger.info(f"Running {cadence} evaluation...")
        start_time = datetime.now(UTC)

        if cadence == "6h":
            result = evaluator.run_6h_eval()
        elif cadence == "daily":
            result = evaluator.run_daily_eval()
        elif cadence == "weekly":
            result = evaluator.run_weekly_eval()
        else:
            logger.error(f"Invalid cadence: {cadence}")
            return 1

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        logger.info(f"Evaluation completed in {duration:.2f} seconds")
        logger.info(f"Issues detected: {len(result.issues)}")
        logger.info(f"Mitigations applied: {len(result.mitigations)}")

        # Save result to file
        cadence_dir = output_dir / cadence
        output_file = get_output_filename(cadence)
        output_path = cadence_dir / output_file

        save_result(result.to_dict(), output_path)
        logger.info(f"Result saved to {output_path}")

        # Check for critical issues
        if result.has_critical_issues():
            logger.error("Critical issues detected!")
            critical = result.get_issues_by_severity("P0")
            for issue in critical:
                logger.error(f"  - {issue.description}")
            return 1

        logger.info(f"{cadence} evaluation completed successfully")
        return 0

    except Exception as e:
        logger.exception(f"Evaluation failed: {e}")
        return 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Schedule and run BrainEval at specified cadences"
    )
    parser.add_argument(
        "--cadence",
        choices=["6h", "daily", "weekly"],
        required=True,
        help="Evaluation cadence",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("_bmad-output/brain-eval"),
        help="Output directory for results (default: _bmad-output/brain-eval)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual evaluation)",
    )
    parser.add_argument(
        "--no-redis",
        action="store_true",
        help="Disable Redis client (for testing without Redis)",
    )

    args = parser.parse_args()

    # Initialize Redis client if not disabled
    redis_client = None
    if not args.no_redis:
        try:
            # Try to connect to Redis (default: host.docker.internal:6380 for chiseai)
            import os

            redis_client = redis.Redis(
                host=os.environ.get("REDIS_HOST", "host.docker.internal"),
                port=6380,
                db=0,
                socket_timeout=2,
                decode_responses=True,
            )
            # Test connection
            redis_client.ping()
        except Exception as e:
            print(f"WARNING: Failed to connect to Redis: {e}", file=sys.stderr)
            print("Continuing without Redis client", file=sys.stderr)
            redis_client = None

    # Run evaluation
    exit_code = run_evaluation(
        cadence=args.cadence,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        redis_client=redis_client,
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
