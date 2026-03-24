#!/usr/bin/env python3
"""
CLI wrapper for Tempmemory Ingestion Runner.

Provides command-line interface for cron-safe ingestion of tempmemory files.

Usage:
    python scripts/ops/tempmemory_ingestion_runner.py --dry-run
    python scripts/ops/tempmemory_ingestion_runner.py --single-file docs/tempmemories/test.md
    python scripts/ops/tempmemory_ingestion_runner.py --filter-type decision

Exit codes:
    0 = Success
    1 = Failure
    2 = Already running (lock held)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    import redis
except ImportError:
    print("ERROR: redis package not installed. Install with: pip install redis")
    sys.exit(1)

from governance.tempmemory.ingestion_runner import (
    VALID_INGESTION_TYPES,
    IngestionStatus,
    TempmemoryIngestionRunner,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_redis_client(redis_url: str | None = None) -> redis.Redis | None:
    """
    Get Redis client with Docker-safe defaults.

    Priority:
    1. Explicit redis_url parameter
    2. REDIS_URL environment variable
    3. REDIS_HOST/REDIS_PORT environment variables
    4. Default: chiseai-redis:6380 (in-container) with host.docker.internal fallback

    Args:
        redis_url: Optional Redis URL.

    Returns:
        Redis client or None if not available.
    """
    import os

    # Priority 1: Explicit URL parameter
    if redis_url:
        try:
            client = redis.from_url(redis_url, decode_responses=False)
            client.ping()
            logger.info(f"Connected to Redis: {redis_url}")
            return client
        except Exception as e:
            logger.warning(f"Failed to connect to explicit Redis URL: {e}")

    # Priority 2: REDIS_URL environment variable
    env_url = os.getenv("REDIS_URL")
    if env_url:
        try:
            client = redis.from_url(env_url, decode_responses=False)
            client.ping()
            logger.info(f"Connected to Redis via REDIS_URL: {env_url}")
            return client
        except Exception as e:
            logger.warning(f"Failed to connect to REDIS_URL: {e}")

    # Priority 3: REDIS_HOST/REDIS_PORT
    redis_host = os.getenv("REDIS_HOST")
    redis_port = os.getenv("REDIS_PORT", "6380")
    if redis_host:
        try:
            client = redis.Redis(
                host=redis_host,
                port=int(redis_port),
                decode_responses=False,
            )
            client.ping()
            logger.info(f"Connected to Redis: {redis_host}:{redis_port}")
            return client
        except Exception as e:
            logger.warning(f"Failed to connect to REDIS_HOST: {e}")

    # Priority 4: Try chiseai-redis (in-container) then host.docker.internal
    hosts_to_try = [
        ("chiseai-redis", 6380, "in-container service"),
        ("host.docker.internal", 6380, "host fallback"),
    ]

    for host, port, description in hosts_to_try:
        try:
            client = redis.Redis(
                host=host,
                port=port,
                decode_responses=False,
                socket_connect_timeout=2,
            )
            client.ping()
            logger.info(f"Connected to Redis ({description}): {host}:{port}")
            return client
        except Exception as e:
            logger.debug(f"Failed to connect to {host}:{port}: {e}")

    logger.warning(
        "Could not connect to Redis - tempmemory ingestion will run without persistence"
    )
    return None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tempmemory Ingestion Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - show what would be ingested
  %(prog)s --dry-run

  # Ingest specific file
  %(prog)s --single-file docs/tempmemories/test.md

  # Force re-ingestion
  %(prog)s --force

  # Filter by type
  %(prog)s --filter-type decision --filter-type pattern

  # Check status
  %(prog)s --status
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be ingested without making changes",
    )

    parser.add_argument(
        "--single-file",
        type=str,
        metavar="PATH",
        help="Ingest specific file",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if already processed",
    )

    parser.add_argument(
        "--filter-type",
        type=str,
        action="append",
        choices=list(VALID_INGESTION_TYPES),
        metavar="TYPE",
        help="Only ingest files with specific frontmatter type (can be specified multiple times)",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show ingestion status and exit",
    )

    parser.add_argument(
        "--redis-url",
        type=str,
        metavar="URL",
        help="Redis connection URL (default: from REDIS_URL env var)",
    )

    parser.add_argument(
        "--tempmemory-path",
        type=str,
        metavar="PATH",
        default="docs/tempmemories",
        help="Path to tempmemory directory (default: docs/tempmemories)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get Redis client
    redis_client = get_redis_client(args.redis_url)

    # Create runner
    runner = TempmemoryIngestionRunner(
        redis_client=redis_client,
        tempmemory_path=args.tempmemory_path,
        dry_run=args.dry_run,
        force=args.force,
        filter_types=args.filter_type,
    )

    # Handle status request
    if args.status:
        status = runner.get_ingestion_status()
        if args.json:
            print(json.dumps(status.to_dict(), indent=2))
        else:
            print("Ingestion Status:")
            print(f"  Last Run: {status.last_run or 'Never'}")
            print(f"  Last Success: {status.last_success}")
            print(f"  Total Processed: {status.total_files_processed}")
            print(f"  Total Ingested: {status.total_files_ingested}")
            print(f"  Total Failed: {status.total_files_failed}")
            if status.last_error:
                print(f"  Last Error: {status.last_error}")
        return 0

    try:
        # Run ingestion
        if args.single_file:
            logger.info(f"Ingesting single file: {args.single_file}")
            result = runner.ingest_single_file(args.single_file)

            if args.json:
                output = {
                    "file_path": result.file_path,
                    "status": result.status.value,
                    "already_processed": result.already_processed,
                    "filtered": result.filtered,
                    "filter_reason": result.filter_reason,
                    "error_message": result.error_message,
                    "timestamp": result.timestamp,
                }
                print(json.dumps(output, indent=2))
            else:
                print(f"\nFile: {result.file_path}")
                print(f"Status: {result.status.value}")
                if result.already_processed:
                    print("  (Already processed)")
                if result.filtered:
                    print(f"  Filtered: {result.filter_reason}")
                if result.error_message:
                    print(f"  Error: {result.error_message}")

            return 0 if result.status.value == "completed" else 1

        else:
            # Run full scan with lock
            logger.info("Starting ingestion scan with lock")
            report = runner.run_with_lock()

            if args.json:
                print(report.to_json())
            else:
                print("\n" + "=" * 60)
                print("TEMPMEMORY INGESTION REPORT")
                print("=" * 60)
                print(f"Dry Run: {report.dry_run}")
                print(f"Total Files: {report.total_files}")
                print(f"Scanned: {report.scanned_files}")
                print(f"Migrated: {report.migrated_files}")
                print(f"Failed: {report.failed_files}")
                print(f"Skipped: {report.skipped_files}")
                print(f"Duration: {report.duration_seconds:.2f}s")
                print("=" * 60)

                if report.failed_files > 0:
                    print("\nFailed Files:")
                    for result in report.results:
                        if result.status.value == "failed":
                            print(f"  - {result.file_path}: {result.error_message}")

            return 0 if report.failed_files == 0 else 1

    except RuntimeError as e:
        # Lock already held
        logger.error(str(e))
        if args.json:
            print(json.dumps({"error": str(e), "exit_code": 2}))
        else:
            print(f"\nERROR: {e}")
        return 2

    except Exception as e:
        logger.exception("Ingestion failed")
        if args.json:
            print(json.dumps({"error": str(e), "exit_code": 1}))
        else:
            print(f"\nERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
