#!/usr/bin/env python3
"""
BrainEval Ingestion CLI for ChiseAI.

CLI tool to ingest tempmemory migration results into BrainEval.
Supports dry-run mode, generates ingestion reports, and integrates
with MiniBrainEval for KPI updates.

Usage:
    python3 scripts/ops/brain_eval_ingestion.py --dry-run
    python3 scripts/ops/brain_eval_ingestion.py --source=iterlog --story-id=ST-XXX
    python3 scripts/ops/brain_eval_ingestion.py --full-ingestion

This script is part of Phase 2 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.tempmemory.brain_integration import (
    BrainEvalIntegration,
    IngestionSource,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_redis_client() -> Any | None:
    """Create a Redis client if available."""
    try:
        import redis

        # Try to connect to Redis
        client = redis.Redis(
            host="host.docker.internal",
            port=6380,
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def create_qdrant_client() -> Any | None:
    """Create a Qdrant client if available."""
    try:
        # Qdrant client would be imported here
        # For now, we return None as Qdrant is optional
        return None
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return None


def run_dry_run() -> int:
    """Run ingestion in dry-run mode.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger.info("Running BrainEval ingestion in DRY-RUN mode")

    redis_client = create_redis_client()
    create_qdrant_client()

    integration = BrainEvalIntegration(
        redis_client=redis_client,
        dry_run=True,
    )

    # Run migration
    report = integration._migration_engine.run_migration()

    print("\n" + "=" * 60)
    print("DRY RUN - Migration Report")
    print("=" * 60)
    print(f"Total files scanned: {report.total_files}")
    print(f"Files migrated: {report.migrated_files}")
    print(f"Files failed: {report.failed_files}")
    print(f"Files skipped: {report.skipped_files}")
    print(f"Duration: {report.duration_seconds:.2f}s")
    print("=" * 60)
    print("\nNo actual changes were made (dry-run mode)")

    return 0


def run_source_ingestion(source: str, story_id: str | None = None) -> int:
    """Run ingestion from a specific source.

    Args:
        source: The source to ingest from.
        story_id: Optional story ID filter.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger.info(f"Running ingestion from source: {source}")

    redis_client = create_redis_client()

    integration = BrainEvalIntegration(
        redis_client=redis_client,
        dry_run=False,
    )

    try:
        if source == IngestionSource.MIGRATION_REPORT.value:
            report = integration._migration_engine.run_migration()
            metrics = integration.ingest_from_migration_report(report)
        elif source == IngestionSource.ITERLOG_DECISIONS.value:
            metrics = integration.ingest_from_iterlog(story_id=story_id)
        elif source == IngestionSource.TEMPMEMORY_FILES.value:
            metrics = integration.ingest_from_tempmemory_files()
        else:
            logger.error(f"Unknown source: {source}")
            return 1

        print("\n" + "=" * 60)
        print(f"Ingestion from {source} completed")
        print("=" * 60)
        print(f"Items processed: {metrics.items_processed}")
        print(f"Items ingested: {metrics.items_ingested}")
        print(f"Items failed: {metrics.items_failed}")
        print(f"Items deduplicated: {metrics.items_deduplicated}")
        print(f"KPI updates: {metrics.kpi_updates}")
        print(f"Duration: {metrics.duration_seconds:.2f}s")
        print("=" * 60)

        return 0

    except Exception as e:
        logger.exception(f"Ingestion failed: {e}")
        return 1


def run_full_ingestion(story_id: str | None = None) -> int:
    """Run full multi-source ingestion.

    Args:
        story_id: Optional story ID filter.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger.info("Running full multi-source ingestion")

    redis_client = create_redis_client()

    integration = BrainEvalIntegration(
        redis_client=redis_client,
        dry_run=False,
    )

    try:
        result = integration.run_full_ingestion(story_id=story_id)

        print("\n" + "=" * 60)
        print("Full Ingestion Completed")
        print("=" * 60)
        print(f"Ingestion ID: {result.ingestion_id}")
        print(f"Timestamp: {result.timestamp}")
        print(f"Overall success: {result.overall_success}")
        print(f"BrainEval updated: {result.brain_eval_updated}")
        print(f"MiniBrainEval updated: {result.mini_eval_updated}")

        if result.error_message:
            print(f"Error: {result.error_message}")

        print("\nSource Metrics:")
        for metrics in result.metrics:
            print(f"\n  Source: {metrics.source}")
            print(f"    Processed: {metrics.items_processed}")
            print(f"    Ingested: {metrics.items_ingested}")
            print(f"    Failed: {metrics.items_failed}")
            print(f"    Duration: {metrics.duration_seconds:.2f}s")

        print("=" * 60)

        # Save report to file
        report_path = Path(tempfile.gettempdir()) / "brain_eval_ingestion_report.json"
        with open(report_path, "w") as f:
            f.write(result.to_json())
        print(f"\nReport saved to: {report_path}")

        return 0 if result.overall_success else 1

    except Exception as e:
        logger.exception(f"Full ingestion failed: {e}")
        return 1


def show_ingestion_history(limit: int = 10) -> int:
    """Show recent ingestion history.

    Args:
        limit: Maximum number of entries to show.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger.info(f"Showing ingestion history (limit={limit})")

    redis_client = create_redis_client()

    integration = BrainEvalIntegration(
        redis_client=redis_client,
        dry_run=True,
    )

    history = integration.get_ingestion_history(limit=limit)

    print("\n" + "=" * 60)
    print("Ingestion History")
    print("=" * 60)

    if not history:
        print("No ingestion history found")
    else:
        for i, result in enumerate(history, 1):
            print(f"\n{i}. Ingestion ID: {result.ingestion_id}")
            print(f"   Timestamp: {result.timestamp}")
            print(f"   Success: {result.overall_success}")
            print(f"   BrainEval: {result.brain_eval_updated}")
            print(f"   MiniBrainEval: {result.mini_eval_updated}")

    print("=" * 60)

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BrainEval Ingestion CLI for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - show what would be ingested
  python3 scripts/ops/brain_eval_ingestion.py --dry-run

  # Ingest from specific source
  python3 scripts/ops/brain_eval_ingestion.py --source=iterlog --story-id=ST-XXX

  # Full multi-source ingestion
  python3 scripts/ops/brain_eval_ingestion.py --full-ingestion

  # Show ingestion history
  python3 scripts/ops/brain_eval_ingestion.py --history --limit=20
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual changes)",
    )

    parser.add_argument(
        "--source",
        type=str,
        choices=[s.value for s in IngestionSource],
        help="Source to ingest from",
    )

    parser.add_argument(
        "--story-id",
        type=str,
        help="Story ID filter (optional)",
    )

    parser.add_argument(
        "--full-ingestion",
        action="store_true",
        help="Run full multi-source ingestion",
    )

    parser.add_argument(
        "--history",
        action="store_true",
        help="Show ingestion history",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit for history (default: 10)",
    )

    args = parser.parse_args()

    if args.dry_run:
        return run_dry_run()
    elif args.source:
        return run_source_ingestion(args.source, args.story_id)
    elif args.full_ingestion:
        return run_full_ingestion(args.story_id)
    elif args.history:
        return show_ingestion_history(args.limit)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
