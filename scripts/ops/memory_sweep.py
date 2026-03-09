#!/usr/bin/env python3
"""
Memory Sweep CLI Script for ChiseAI.

Runs memory stewardship operations including:
- Deduplication of memory entries
- Promotion from Redis to Qdrant
- Contradiction detection
- TTL management

Usage:
    python3 scripts/ops/memory_sweep.py --dry-run
    python3 scripts/ops/memory_sweep.py --promote
    python3 scripts/ops/memory_sweep.py --check-contradictions
    python3 scripts/ops/memory_sweep.py --full-sweep

Cron Setup:
    0 2 * * * cd /path/to/chiseai && python3 scripts/ops/memory_sweep.py --full-sweep >> /var/log/chiseai/memory_sweep.log 2>&1
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from governance.memory.contradiction import ContradictionConfig, ContradictionDetector
from governance.memory.deduplication import (
    DeduplicationConfig,
    MemoryDeduplicationEngine,
)
from governance.memory.promotion import MemoryPromotionEngine, PromotionConfig
from governance.memory.sweep import MemorySweepEngine, SweepConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_redis_client() -> Any | None:
    """Create Redis client if available."""
    try:
        import redis

        port = int(
            os.getenv("REDIS_PORT")
            or os.getenv("CHISE_REDIS_PORT")
            or os.getenv("ACP_REDIS_PORT")
            or "6380"
        )
        db = int(os.getenv("REDIS_DB", "0"))
        hosts = [
            os.getenv("REDIS_HOST"),
            os.getenv("CHISE_REDIS_HOST"),
            os.getenv("ACP_REDIS_HOST"),
            "chiseai-redis",
            "host.docker.internal",
            "localhost",
        ]
        hosts = [h for i, h in enumerate(hosts) if h and h not in hosts[:i]]
        for host in hosts:
            try:
                client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=True,
                )
                client.ping()
                logger.info(f"Redis client connected: {host}:{port}/{db}")
                return client
            except Exception:
                continue
        return None
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def create_qdrant_client() -> Any | None:
    """Create Qdrant client if available."""
    try:
        from qdrant_client import QdrantClient

        port = int(os.getenv("QDRANT_PORT", "6334"))
        hosts = [
            os.getenv("QDRANT_HOST"),
            os.getenv("CHISE_QDRANT_HOST"),
            "chiseai-qdrant",
            "host.docker.internal",
            "localhost",
        ]
        hosts = [h for i, h in enumerate(hosts) if h and h not in hosts[:i]]
        for host in hosts:
            try:
                client = QdrantClient(
                    host=host,
                    port=port,
                )
                client.get_collections()
                logger.info(f"Qdrant client connected: {host}:{port}")
                return client
            except Exception:
                continue
        return None
    except Exception as e:
        logger.warning(f"Qdrant not available: {e}")
        return None


def print_stats(stats: Any, title: str = "Statistics") -> None:
    """Print statistics in a readable format."""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")

    if hasattr(stats, "__dict__"):
        for key, value in vars(stats).items():
            if not key.startswith("_"):
                print(f"  {key}: {value}")
    else:
        print(f"  {stats}")

    print(f"{'=' * 60}\n")


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Run sweep in dry-run mode."""
    logger.info("Starting dry-run sweep")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    config = SweepConfig(dry_run=True)
    engine = MemorySweepEngine(
        config=config,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    stats = engine.run_sweep(dry_run=True)
    print_stats(stats, "Dry-Run Sweep Results")

    return 0 if not stats.error else 1


def cmd_promote(args: argparse.Namespace) -> int:
    """Run promotion only."""
    logger.info("Starting memory promotion")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    if not redis_client:
        logger.error("Redis is required for promotion")
        return 1

    config = PromotionConfig(dry_run=args.dry_run)
    engine = MemoryPromotionEngine(
        config=config,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    # Enable if requested
    if args.enable:
        engine.enable()

    if not engine.is_enabled() and not args.dry_run:
        logger.error("Promotion engine is disabled. Use --enable or --dry-run")
        return 1

    stats = engine.run_promotion(dry_run=args.dry_run)
    print_stats(stats, "Promotion Results")

    return 0 if not stats.error else 1


def cmd_deduplicate(args: argparse.Namespace) -> int:
    """Run deduplication only."""
    logger.info("Starting deduplication")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    config = DeduplicationConfig(dry_run=args.dry_run)
    engine = MemoryDeduplicationEngine(
        config=config,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    # Enable if requested
    if args.enable:
        engine.enable()

    if not engine.is_enabled() and not args.dry_run:
        logger.error("Deduplication engine is disabled. Use --enable or --dry-run")
        return 1

    stats = engine.deduplicate(dry_run=args.dry_run)
    print_stats(stats, "Deduplication Results")

    return 0 if not stats.error else 1


def cmd_check_contradictions(args: argparse.Namespace) -> int:
    """Check for contradictions."""
    logger.info("Starting contradiction detection")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    config = ContradictionConfig()
    detector = ContradictionDetector(
        config=config,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    contradictions = detector.scan_for_contradictions()

    print(f"\n{'=' * 60}")
    print("Contradiction Detection Results")
    print(f"{'=' * 60}")
    print(f"Total contradictions found: {len(contradictions)}")

    for i, c in enumerate(contradictions, 1):
        print(f"\n{i}. {c.severity.upper()} Severity")
        print(f"   Memory 1: {c.memory_id_1}")
        print(f"   Memory 2: {c.memory_id_2}")
        print(f"   Similarity: {c.similarity:.2f}")
        print(f"   Reason: {c.reason}")

    print(f"{'=' * 60}\n")

    return 0


def cmd_full_sweep(args: argparse.Namespace) -> int:
    """Run full sweep with all components."""
    logger.info("Starting full memory sweep")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    config = SweepConfig(dry_run=args.dry_run)
    engine = MemorySweepEngine(
        config=config,
        redis_client=redis_client,
        qdrant_client=qdrant_client,
    )

    # Enable if requested
    if args.enable:
        engine.enable()

    if not engine.is_enabled() and not args.dry_run:
        logger.error("Sweep engine is disabled. Use --enable or --dry-run")
        return 1

    stats = engine.run_sweep(dry_run=args.dry_run)
    print_stats(stats, "Full Sweep Results")

    # Also print component stats
    if stats.dedup_stats:
        print("\nDeduplication:")
        for key, value in stats.dedup_stats.items():
            print(f"  {key}: {value}")

    if stats.promotion_stats:
        print("\nPromotion:")
        for key, value in stats.promotion_stats.items():
            print(f"  {key}: {value}")

    if stats.contradiction_stats:
        print("\nContradiction Detection:")
        for key, value in stats.contradiction_stats.items():
            print(f"  {key}: {value}")

    return 0 if not stats.error else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Check status of memory systems."""
    logger.info("Checking memory system status")

    redis_client = create_redis_client()
    qdrant_client = create_qdrant_client()

    print(f"\n{'=' * 60}")
    print("Memory System Status")
    print(f"{'=' * 60}")

    # Check Redis
    if redis_client:
        print("\nRedis:")
        print("  Status: Connected")

        # Check feature flags
        flags = [
            "chise:feature_flags:governance:memory_sweep_enabled",
            "chise:feature_flags:governance:memory_promotion_enabled",
            "chise:feature_flags:governance:memory_dedup_enabled",
            "chise:feature_flags:governance:contradiction_detection_enabled",
        ]

        for flag in flags:
            value = redis_client.get(flag)
            status = value if value else "not set (default: disabled)"
            print(f"  {flag.split(':')[-1]}: {status}")

        # Count iterlog entries
        iterlog_count = 0
        try:
            for key in redis_client.scan_iter(
                match="bmad:chiseai:iterlog:story:*", count=100
            ):
                iterlog_count += 1
        except Exception:
            pass
        print(f"  Iterlog entries: ~{iterlog_count}")
    else:
        print("\nRedis: Not connected")

    # Check Qdrant
    if qdrant_client:
        print("\nQdrant:")
        print("  Status: Connected")
        try:
            collection_info = qdrant_client.get_collection("ChiseAI")
            print(f"  Collection 'ChiseAI': {collection_info.points_count} points")
        except Exception as e:
            print(f"  Collection 'ChiseAI': Error - {e}")
    else:
        print("\nQdrant: Not connected")

    print(f"{'=' * 60}\n")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Memory Sweep CLI for ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - see what would happen without making changes
  python3 scripts/ops/memory_sweep.py --dry-run
  
  # Run full sweep (requires engines to be enabled)
  python3 scripts/ops/memory_sweep.py --full-sweep --enable
  
  # Check for contradictions only
  python3 scripts/ops/memory_sweep.py --check-contradictions
  
  # Check system status
  python3 scripts/ops/memory_sweep.py --status
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making actual changes",
    )

    parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable the engine before running",
    )

    parser.add_argument(
        "--promote",
        action="store_true",
        help="Run promotion only",
    )

    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Run deduplication only",
    )

    parser.add_argument(
        "--check-contradictions",
        action="store_true",
        help="Check for contradictions only",
    )

    parser.add_argument(
        "--full-sweep",
        action="store_true",
        help="Run full sweep with all components",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Check memory system status",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Default to dry-run if no command specified
    if not any(
        [
            args.promote,
            args.deduplicate,
            args.check_contradictions,
            args.full_sweep,
            args.status,
        ]
    ):
        args.dry_run = True

    # Route to appropriate command
    if args.status:
        return cmd_status(args)
    elif args.check_contradictions:
        return cmd_check_contradictions(args)
    elif args.promote:
        return cmd_promote(args)
    elif args.deduplicate:
        return cmd_deduplicate(args)
    elif args.full_sweep:
        return cmd_full_sweep(args)
    else:
        return cmd_dry_run(args)


if __name__ == "__main__":
    sys.exit(main())
