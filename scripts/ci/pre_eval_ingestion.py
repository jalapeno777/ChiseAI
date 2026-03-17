#!/usr/bin/env python3
"""
Pre-Evaluation Tempmemory Ingestion Script for CI.

This script runs tempmemory ingestion before BrainEval in the CI pipeline.
It integrates with the CI system to ensure tempmemory files are ingested
before brain evaluation runs.

Usage:
    python pre_eval_ingestion.py [--dry-run] [--force] [--strict]

Exit Codes:
    0: Ingestion completed successfully (or skipped if disabled)
    1: Ingestion failed critically
    2: Error during ingestion execution

Feature Flag:
    Set CI_TEMPMEMORY_INGESTION_ENABLED=true to enable ingestion.
    Default is disabled for backward compatibility.

Environment Variables:
    CI_TEMPMEMORY_INGESTION_ENABLED: Feature flag (default: false)
    CI_PIPELINE_NUMBER: Pipeline ID for caching
    CI_COMMIT_SHA: Git commit SHA for tracking
    REDIS_HOST: Redis host (default: host.docker.internal)
    REDIS_PORT: Redis port (default: 6380)
    QDRANT_HOST: Qdrant host (default: host.docker.internal)
    QDRANT_PORT: Qdrant port (default: 6334)
    CI_TEMPMEMORY_INGESTION_STRICT: If set, fail on any error (default: false)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add src and scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from governance.tempmemory.ci_integration import (
    FEATURE_FLAG_ENV,
    format_report_for_logs,
    is_ingestion_enabled,
    run_pre_eval_ingestion,
    should_fail_ci,
    validate_ingestion_success,
)

# Configure logging for CI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Pre-evaluation tempmemory ingestion for CI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run ingestion (if feature flag enabled)
    python pre_eval_ingestion.py

    # Dry run mode (don't actually ingest)
    python pre_eval_ingestion.py --dry-run

    # Force re-ingestion of already processed files
    python pre_eval_ingestion.py --force

    # Strict mode - fail on any error
    python pre_eval_ingestion.py --strict

    # Custom tempmemory path
    python pre_eval_ingestion.py --tempmemory-path /path/to/tempmemories

    # Output report to file
    python pre_eval_ingestion.py --output /tmp/ingestion-report.json
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (don't actually ingest)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion of already processed files",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any error (strict mode)",
    )

    parser.add_argument(
        "--tempmemory-path",
        type=str,
        default=None,
        help="Path to tempmemory directory (default: docs/tempmemories/)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path for JSON report",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress non-error output",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for pre-evaluation ingestion.

    Returns:
        Exit code (0 for success, 1 for failure, 2 for error)
    """
    args = parse_args()

    # Adjust logging level if quiet mode
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # Log startup info
    logger.info("=" * 60)
    logger.info("PRE-EVALUATION TEMPMEMORY INGESTION")
    logger.info("=" * 60)
    logger.info(
        f"Feature flag: {FEATURE_FLAG_ENV}={os.getenv(FEATURE_FLAG_ENV, 'false')}"
    )
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Force: {args.force}")
    logger.info(f"Strict mode: {args.strict}")

    # Check if ingestion is enabled
    if not is_ingestion_enabled():
        logger.info("=" * 60)
        logger.info("INGESTION DISABLED")
        logger.info("=" * 60)
        logger.info(f"{FEATURE_FLAG_ENV} is not set to 'true'")
        logger.info(
            "Skipping ingestion - BrainEval will run without tempmemory updates"
        )
        logger.info(
            "To enable, set environment variable: CI_TEMPMEMORY_INGESTION_ENABLED=true"
        )

        # Write empty report if output requested
        if args.output:
            skip_report = {
                "success": True,
                "skipped": True,
                "reason": "Feature flag disabled",
                "timestamp": None,
                "files_processed": 0,
                "files_ingested": 0,
                "files_failed": 0,
                "files_skipped": 0,
                "duration_seconds": 0,
                "errors": [],
                "ingested_memory_ids": [],
            }
            with open(args.output, "w") as f:
                json.dump(skip_report, f, indent=2)
            logger.info(f"Skip report written to: {args.output}")

        return 0  # Success - just skipped

    # Run ingestion
    logger.info("=" * 60)
    logger.info("RUNNING INGESTION")
    logger.info("=" * 60)

    try:
        report = run_pre_eval_ingestion(
            dry_run=args.dry_run,
            force=args.force,
            tempmemory_path=args.tempmemory_path,
        )
    except Exception as e:
        logger.exception("Fatal error during ingestion")
        print(f"\n❌ FATAL ERROR: {e}", file=sys.stderr)
        return 2

    # Format and print report
    if not args.quiet:
        print("\n" + format_report_for_logs(report))

    # Write report to file if requested
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(report.to_json())
            logger.info(f"Report written to: {args.output}")
        except Exception as e:
            logger.error(f"Failed to write report: {e}")

    # Determine if CI should fail
    strict_mode = (
        args.strict
        or os.getenv("CI_TEMPMEMORY_INGESTION_STRICT", "false").lower() == "true"
    )
    should_fail = should_fail_ci(report, strict=strict_mode)

    # Validate ingestion
    is_valid = validate_ingestion_success(report)

    # Print summary
    logger.info("=" * 60)
    if report.success and is_valid and not should_fail:
        logger.info("✅ INGESTION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info(f"Files ingested: {report.files_ingested}")
        logger.info("BrainEval can now proceed with updated tempmemory")
        return 0
    elif should_fail:
        logger.error("❌ INGESTION FAILED - CI WILL FAIL")
        logger.info("=" * 60)
        logger.error(f"Files failed: {report.files_failed}")
        logger.error(f"Errors: {len(report.errors)}")
        if report.errors:
            for error in report.errors[:5]:
                logger.error(f"  - {error}")
        return 1
    else:
        logger.warning("⚠️ INGESTION COMPLETED WITH WARNINGS")
        logger.info("=" * 60)
        logger.warning(f"Files failed: {report.files_failed}")
        logger.warning(f"Files ingested: {report.files_ingested}")
        logger.warning("Continuing - BrainEval will proceed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
