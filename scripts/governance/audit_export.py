#!/usr/bin/env python3
"""
Audit Trail Export Script.

ST-GOV-009: Decision Audit Trail Export

Provides command-line interface for exporting audit trail data.

Usage:
    python scripts/governance/audit_export.py --mode daily
    python scripts/governance/audit_export.py --mode full --output /tmp/exports
    python scripts/governance/audit_export.py --mode file --start 2024-01-01 --end 2024-01-31
    python scripts/governance/audit_export.py --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.governance.audit_trail import (
    AuditTrail,
    AuditTrailExporter,
    AuditTrailQuery,
    ExportConfig,
    S3Config,
)
from src.governance.audit_trail.query import QueryFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_redis_client():
    """Create Redis client from environment."""
    import os

    redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
    redis_port = int(os.getenv("REDIS_PORT", "6380"))

    try:
        import redis

        return redis.Redis(host=redis_host, port=redis_port, decode_responses=False)
    except ImportError:
        logger.warning("Redis package not installed, using in-memory mode")
        return None
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}, using in-memory mode")
        return None


def export_daily(args: argparse.Namespace) -> int:
    """Perform daily export."""
    logger.info("Starting daily audit trail export...")

    redis_client = create_redis_client()
    trail = AuditTrail(redis_client=redis_client)
    query = AuditTrailQuery(redis_client=redis_client)

    # Get chain state for verification
    chain_state = trail.get_chain_state()
    chain_valid, chain_msg = trail.verify_chain()

    s3_config = S3Config.from_env() if args.s3_bucket else None
    if args.s3_bucket and s3_config:
        s3_config.bucket = args.s3_bucket

    exporter = AuditTrailExporter(
        query_interface=query,
        config=ExportConfig(
            compress=not args.no_compress,
            include_chain_verification=True,
        ),
        s3_config=s3_config,
        output_dir=args.output,
    )

    result = exporter.export_daily()

    # Add chain verification to result
    chain_data = {
        "valid": chain_valid,
        "message": chain_msg,
        "chain_length": chain_state.chain_length,
        "last_hash": chain_state.last_hash,
    }

    print(
        json.dumps(
            {
                "status": result.status.value,
                "entry_count": result.entry_count,
                "file_path": result.file_path,
                "s3_key": result.s3_key,
                "file_size_bytes": result.file_size_bytes,
                "chain_verification": chain_data,
                "checksum": result.checksum,
                "error": result.error_message,
            },
            indent=2,
        )
    )

    return 0 if result.status.value == "completed" else 1


def export_full(args: argparse.Namespace) -> int:
    """Perform full export."""
    logger.info("Starting full audit trail export...")

    redis_client = create_redis_client()
    trail = AuditTrail(redis_client=redis_client)
    query = AuditTrailQuery(redis_client=redis_client)

    chain_state = trail.get_chain_state()
    chain_valid, chain_msg = trail.verify_chain()

    s3_config = S3Config.from_env() if args.s3_bucket else None
    if args.s3_bucket and s3_config:
        s3_config.bucket = args.s3_bucket

    exporter = AuditTrailExporter(
        query_interface=query,
        config=ExportConfig(
            compress=not args.no_compress,
            include_chain_verification=True,
        ),
        s3_config=s3_config,
        output_dir=args.output,
    )

    result = exporter.export_full()

    chain_data = {
        "valid": chain_valid,
        "message": chain_msg,
        "chain_length": chain_state.chain_length,
        "last_hash": chain_state.last_hash,
    }

    print(
        json.dumps(
            {
                "status": result.status.value,
                "entry_count": result.entry_count,
                "file_path": result.file_path,
                "s3_key": result.s3_key,
                "file_size_bytes": result.file_size_bytes,
                "chain_verification": chain_data,
                "checksum": result.checksum,
                "error": result.error_message,
            },
            indent=2,
        )
    )

    return 0 if result.status.value == "completed" else 1


def export_file(args: argparse.Namespace) -> int:
    """Export to local file with optional time range."""
    logger.info(f"Starting file export to {args.output}...")

    redis_client = create_redis_client()
    trail = AuditTrail(redis_client=redis_client)
    query = AuditTrailQuery(redis_client=redis_client)

    # Build filter from arguments
    filter_criteria = None
    if args.start or args.end:
        filter_criteria = QueryFilter(
            start_time=datetime.fromisoformat(args.start) if args.start else None,
            end_time=datetime.fromisoformat(args.end) if args.end else None,
        )

    chain_state = trail.get_chain_state()
    chain_valid, chain_msg = trail.verify_chain()

    chain_data = {
        "valid": chain_valid,
        "message": chain_msg,
        "chain_length": chain_state.chain_length,
        "last_hash": chain_state.last_hash,
    }

    exporter = AuditTrailExporter(
        query_interface=query,
        config=ExportConfig(
            compress=not args.no_compress,
            include_chain_verification=True,
        ),
        output_dir=args.output,
    )

    result = exporter.export_to_file(
        filter_criteria=filter_criteria,
        chain_state=chain_data,
    )

    print(
        json.dumps(
            {
                "status": result.status.value,
                "entry_count": result.entry_count,
                "file_path": result.file_path,
                "file_size_bytes": result.file_size_bytes,
                "chain_verification": chain_data,
                "checksum": result.checksum,
                "error": result.error_message,
            },
            indent=2,
        )
    )

    return 0 if result.status.value == "completed" else 1


def verify_chain(args: argparse.Namespace) -> int:
    """Verify the integrity of the audit trail hash chain."""
    logger.info("Verifying audit trail hash chain integrity...")

    redis_client = create_redis_client()
    trail = AuditTrail(redis_client=redis_client)

    chain_state = trail.get_chain_state()
    is_valid, message = trail.verify_chain()

    result = {
        "valid": is_valid,
        "message": message,
        "chain_length": chain_state.chain_length,
        "last_hash": chain_state.last_hash,
        "genesis_hash": chain_state.genesis_hash,
        "last_timestamp": chain_state.last_timestamp.isoformat(),
    }

    print(json.dumps(result, indent=2))

    return 0 if is_valid else 1


def query_entries(args: argparse.Namespace) -> int:
    """Query and display audit trail entries."""
    logger.info(f"Querying audit trail (agent={args.agent}, type={args.type})...")

    redis_client = create_redis_client()
    query = AuditTrailQuery(redis_client=redis_client)

    # Build filter
    filter_criteria = None
    if args.agent or args.type or args.start or args.end:
        from src.governance.audit_trail.decision import DecisionType

        types = None
        if args.type:
            types = [DecisionType(t) for t in args.type.split(",")]

        filter_criteria = QueryFilter(
            agent_id=args.agent,
            decision_types=types,
            start_time=datetime.fromisoformat(args.start) if args.start else None,
            end_time=datetime.fromisoformat(args.end) if args.end else None,
        )

    result = query.query(
        filter_criteria=filter_criteria,
        page=args.page,
        page_size=args.limit,
    )

    output = {
        "total_count": result.total_count,
        "page": result.page,
        "page_size": result.page_size,
        "has_more": result.has_more,
        "query_time_ms": result.query_time_ms,
        "entries": [e.to_dict() for e in result.entries],
    }

    print(json.dumps(output, indent=2))

    return 0


def cleanup_exports(args: argparse.Namespace) -> int:
    """Clean up old export files."""
    logger.info(f"Cleaning up exports older than {args.retention_days} days...")

    redis_client = create_redis_client()
    query = AuditTrailQuery(redis_client=redis_client)

    exporter = AuditTrailExporter(
        query_interface=query,
        config=ExportConfig(retention_years=args.retention_days // 365),
        output_dir=args.output,
    )

    deleted_count = exporter.cleanup_old_exports(retention_days=args.retention_days)

    print(
        json.dumps(
            {
                "deleted_count": deleted_count,
                "retention_days": args.retention_days,
                "output_dir": args.output,
            },
            indent=2,
        )
    )

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Audit Trail Export Tool (ST-GOV-009)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Daily export to S3
  python scripts/governance/audit_export.py --mode daily --s3-bucket my-bucket

  # Full export to local directory
  python scripts/governance/audit_export.py --mode full --output /tmp/exports

  # Export specific time range
  python scripts/governance/audit_export.py --mode file --start 2024-01-01 --end 2024-01-31

  # Verify chain integrity
  python scripts/governance/audit_export.py --verify

  # Query entries
  python scripts/governance/audit_export.py --query --agent jarvis-001 --limit 10
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["daily", "full", "file"],
        help="Export mode",
    )
    parser.add_argument(
        "--output",
        default="/tmp/audit_exports",
        help="Output directory for exports",
    )
    parser.add_argument(
        "--s3-bucket",
        help="S3 bucket for cloud exports",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable gzip compression",
    )
    parser.add_argument(
        "--start",
        help="Start time for time range (ISO format)",
    )
    parser.add_argument(
        "--end",
        help="End time for time range (ISO format)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify hash chain integrity",
    )
    parser.add_argument(
        "--query",
        action="store_true",
        help="Query audit trail entries",
    )
    parser.add_argument(
        "--agent",
        help="Filter by agent ID",
    )
    parser.add_argument(
        "--type",
        help="Filter by decision type(s), comma-separated",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum entries to return",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number for pagination",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up old exports",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=2557,  # 7 years
        help="Retention period in days for cleanup",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Route to appropriate handler
    if args.verify:
        return verify_chain(args)
    elif args.query:
        return query_entries(args)
    elif args.cleanup:
        return cleanup_exports(args)
    elif args.mode == "daily":
        return export_daily(args)
    elif args.mode == "full":
        return export_full(args)
    elif args.mode == "file":
        return export_file(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
