#!/usr/bin/env python3
"""Run mini brain evaluation and persist KPI snapshots.

This script runs a 6-hour mini brain evaluation, collects KPIs, and persists
the results to both Redis and file artifacts.

Usage:
    # Run evaluation and persist results
    python3 scripts/evaluation/run_mini_eval.py

    # Dry run (no persistence)
    python3 scripts/evaluation/run_mini_eval.py --dry-run

    # Custom output directory
    python3 scripts/evaluation/run_mini_eval.py --output-dir /path/to/output

Exit Codes:
    0 - Success
    1 - Failure

Examples:
    >>> # Standard run
    >>> python3 scripts/evaluation/run_mini_eval.py
    INFO:__main__:Starting mini brain evaluation
    INFO:__main__:Evaluation completed successfully
    INFO:__main__:KPI snapshot persisted: mini_eval-20260302-143022

    >>> # Dry run
    >>> python3 scripts/evaluation/run_mini_eval.py --dry-run
    INFO:__main__:Starting mini brain evaluation (DRY RUN)
    INFO:__main__:Evaluation completed successfully
    INFO:__main__:Dry run completed - no persistence
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluation.kpi_persistence import KPIPersistence, KPIPersistenceError
from evaluation.mini_brain_eval import MiniBrainEval, MiniBrainEvalError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp.

    Returns:
        Run ID in format: mini_eval-YYYYMMDD-HHMMSS
    """
    timestamp = datetime.now(UTC)
    return f"mini_eval-{timestamp.strftime('%Y%m%d-%H%M%S')}"


def create_redis_client():
    """Create Redis client with graceful failure handling.

    Returns:
        Redis client if connection successful, None otherwise
    """
    try:
        import redis

        # Use environment variables with fallback for container environments
        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))

        # Try to connect to Redis
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Test connection
        client.ping()
        logger.info("Connected to Redis successfully")
        return client

    except ImportError:
        logger.warning("Redis library not installed, running without Redis persistence")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        logger.warning("Continuing without Redis persistence")
        return None


def run_mini_eval(
    dry_run: bool = False,
    output_dir: str = "_bmad-output/brain-eval/kpi-snapshots/",
) -> int:
    """Run mini brain evaluation and persist KPI snapshot.

    Args:
        dry_run: If True, don't persist results
        output_dir: Directory for file artifact output

    Returns:
        Exit code: 0 for success, 1 for failure
    """
    run_id = generate_run_id()
    logger.info(f"Starting mini brain evaluation (run_id: {run_id})")

    if dry_run:
        logger.info("DRY RUN MODE - No persistence will occur")

    try:
        # Create Redis client (graceful failure)
        redis_client = create_redis_client()

        # Initialize MiniBrainEval
        evaluator = MiniBrainEval(
            redis_client=redis_client,
            influxdb_client=None,  # Not required for mini eval
            brain_evaluator=None,  # Not required for mini eval
            qdrant_client=None,  # Not required for mini eval
        )

        # Run 6h evaluation
        logger.info("Running 6-hour mini evaluation...")
        result = evaluator.run_6h_eval()

        # Log results
        logger.info(f"Evaluation completed with {len(result.issues)} issues")
        if result.issues:
            for issue in result.issues:
                logger.warning(
                    f"Issue detected: [{issue.severity}] {issue.category} - "
                    f"{issue.description}"
                )

        # Log KPIs
        if result.kpis:
            logger.info("KPIs collected:")
            for key, value in result.kpis.items():
                logger.info(f"  {key}: {value}")

        # Log data freshness
        if result.data_freshness:
            logger.info("Data freshness status:")
            for source, status in result.data_freshness.items():
                logger.info(f"  {source}: {status}")

        # Persist results (unless dry run)
        if not dry_run:
            # Initialize KPI persistence
            persistence = KPIPersistence(
                redis_client=redis_client,
                output_dir=output_dir,
            )

            # Prepare KPI data from evaluation result
            kpi_data = {
                "kpis": result.kpis,
                "issues_count": len(result.issues),
                "issues": [
                    {
                        "issue_id": issue.issue_id,
                        "category": issue.category,
                        "severity": issue.severity,
                        "description": issue.description,
                    }
                    for issue in result.issues
                ],
                "mitigations_count": len(result.mitigations),
                "data_freshness": result.data_freshness,
                "eval_id": result.eval_id,
                "cadence": result.cadence,
            }

            # Add proxy metrics if available
            if result.proxies:
                kpi_data["proxies"] = result.proxies

            # Persist snapshot
            logger.info("Persisting KPI snapshot...")
            snapshot = persistence.persist_kpi_snapshot(
                kpi_data=kpi_data,
                source="mini_eval",
                run_id=run_id,
                measured_vs_proxy="measured",
                metadata={
                    "eval_id": result.eval_id,
                    "cadence": result.cadence,
                    "timestamp": result.timestamp,
                },
            )

            logger.info(f"KPI snapshot persisted successfully")
            logger.info(f"  Run ID: {run_id}")
            logger.info(f"  Bucket: {snapshot.bucket_type} / {snapshot.bucket_key}")
            logger.info(f"  Timestamp: {snapshot.timestamp}")

            # Log artifact location
            artifact_path = (
                Path(output_dir)
                / snapshot.bucket_type
                / snapshot.source
                / datetime.now(UTC).strftime("%Y")
                / datetime.now(UTC).strftime("%m")
                / datetime.now(UTC).strftime("%d")
                / f"{run_id}.json"
            )
            logger.info(f"  Artifact: {artifact_path}")
        else:
            logger.info("Dry run completed - no persistence")

        # Determine exit code based on critical issues
        if result.has_critical_issues():
            logger.error("Critical issues detected during evaluation")
            return 1

        logger.info("Mini brain evaluation completed successfully")
        return 0

    except MiniBrainEvalError as e:
        logger.error(f"Mini brain evaluation failed: {e}")
        return 1
    except KPIPersistenceError as e:
        logger.error(f"KPI persistence failed: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Evaluation interrupted by user")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error during evaluation: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run mini brain evaluation and persist KPI snapshots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run evaluation and persist results
  python3 scripts/evaluation/run_mini_eval.py
  
  # Dry run (no persistence)
  python3 scripts/evaluation/run_mini_eval.py --dry-run
  
  # Custom output directory
  python3 scripts/evaluation/run_mini_eval.py --output-dir /path/to/output
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run evaluation without persisting results",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="_bmad-output/brain-eval/kpi-snapshots/",
        help="Output directory for KPI snapshots (default: _bmad-output/brain-eval/kpi-snapshots/)",
    )

    args = parser.parse_args()

    # Run evaluation
    exit_code = run_mini_eval(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
