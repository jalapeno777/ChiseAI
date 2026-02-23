#!/usr/bin/env python3
"""
Memory Consolidation Scheduler CLI.

Provides command-line interface for running and managing memory consolidation.

Usage:
    python scripts/governance/consolidation_scheduler.py run [--dry-run]
    python scripts/governance/consolidation_scheduler.py rollback <memory_id>
    python scripts/governance/consolidation_scheduler.py status
    python scripts/governance/consolidation_scheduler.py validate
    python scripts/governance/consolidation_scheduler.py start-daemon

Story: ST-GOV-005
Governance Feature: GF-005
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.governance.consolidation import (
    ConsolidationConfig,
    MemoryConsolidationScheduler,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_scheduler(dry_run: bool = True) -> MemoryConsolidationScheduler:
    """Create and configure the scheduler."""
    config = ConsolidationConfig(dry_run=dry_run)
    return MemoryConsolidationScheduler(config)


def cmd_run(args: argparse.Namespace) -> int:
    """Run consolidation once."""
    scheduler = create_scheduler(dry_run=args.dry_run)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Running consolidation...")
    print("-" * 50)

    result = scheduler.run_now(
        dry_run=args.dry_run,
        archive=not args.skip_archive,
        promote=not args.skip_promote,
    )

    # Print results
    print(f"\nTimestamp: {result.timestamp.isoformat()}")
    print(f"Success: {result.success}")
    print(f"Total time: {result.total_processing_time_seconds:.2f}s")

    if result.archive_stats:
        print("\nArchive Stats:")
        print(f"  Memories scanned: {result.archive_stats.memories_scanned}")
        print(f"  Memories archived: {result.archive_stats.memories_archived}")
        print(f"  Bytes archived: {result.archive_stats.bytes_archived}")

    if result.promotion_stats:
        print("\nPromotion Stats:")
        print(f"  Candidates evaluated: {result.promotion_stats.candidates_evaluated}")
        print(f"  Candidates promoted: {result.promotion_stats.candidates_promoted}")
        print(
            f"  Avg promotion score: {result.promotion_stats.promotion_score_avg:.3f}"
        )

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.success else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    """Roll back a memory."""
    scheduler = create_scheduler()

    memory_id = args.memory_id

    print(f"\nChecking rollback eligibility for {memory_id}...")

    if not scheduler.can_rollback(memory_id):
        print(f"ERROR: Memory {memory_id} cannot be rolled back")
        print("  - May not exist in rollback data")
        print("  - May be outside 7-day rollback window")
        return 1

    print(f"Memory {memory_id} is eligible for rollback")

    if args.dry_run:
        print("\n[DRY RUN] Would roll back this memory")
        return 0

    confirm = input("\nProceed with rollback? [y/N]: ")
    if confirm.lower() != "y":
        print("Aborted")
        return 0

    print(f"\nRolling back {memory_id}...")
    stats = scheduler.rollback_memory(memory_id)

    print(f"Rollback time: {stats.rollback_time_seconds:.2f}s")
    print(f"Success: {stats.operations_succeeded > 0}")

    if stats.errors:
        print("Errors:")
        for error in stats.errors:
            print(f"  - {error}")

    return 0 if stats.operations_succeeded > 0 else 1


def cmd_rollback_batch(args: argparse.Namespace) -> int:
    """Roll back multiple memories."""
    scheduler = create_scheduler()

    memory_ids = args.memory_ids
    print(f"\nRolling back {len(memory_ids)} memories...")

    stats = scheduler.rollback_batch(memory_ids, dry_run=args.dry_run)

    print(f"\nResults:")
    print(f"  Requested: {stats.operations_requested}")
    print(f"  Succeeded: {stats.operations_succeeded}")
    print(f"  Failed: {stats.operations_failed}")
    print(f"  Time: {stats.rollback_time_seconds:.2f}s")

    return 0 if stats.operations_failed == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show consolidation status."""
    scheduler = create_scheduler()

    print("\n" + "=" * 50)
    print("Memory Consolidation Status")
    print("=" * 50)

    # Config
    config = scheduler.get_config()
    print(f"\nConfiguration:")
    print(f"  Schedule: Daily at {config.schedule_time.isoformat()} UTC")
    print(f"  Enabled: {scheduler.is_enabled()}")
    print(f"  Dry run: {config.dry_run}")
    print(f"  Rollback window: {config.rollback_retention_days} days")

    # Last run
    result = scheduler.get_last_result()
    if result:
        print(f"\nLast Run:")
        print(f"  Timestamp: {result.timestamp.isoformat()}")
        print(f"  Success: {result.success}")
        print(f"  Duration: {result.total_processing_time_seconds:.2f}s")
        if result.archive_stats:
            print(f"  Archived: {result.archive_stats.memories_archived} memories")
        if result.promotion_stats:
            print(f"  Promoted: {result.promotion_stats.candidates_promoted} memories")
    else:
        print("\nLast Run: None")

    # Rollback window
    window = scheduler.get_rollback_window()
    print(f"\nRollback Window:")
    print(f"  Start: {window.start_date.isoformat()}")
    print(f"  End: {window.end_date.isoformat()}")
    print(f"  Available memories: {window.available_memories}")

    # Live gates
    validation = scheduler.validate_live_gates()
    print(f"\nLive Validation Gates:")
    if "reason" in validation:
        print(f"  Status: {validation['reason']}")
    else:
        for gate_name, gate_info in validation.get("gates", {}).items():
            status = "✓ PASS" if gate_info["pass"] else "✗ FAIL"
            print(f"  {gate_name}: {status} (value={gate_info['value']})")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate live gates."""
    scheduler = create_scheduler()

    print("\nValidating Live Gates...")
    print("-" * 50)

    # First run a consolidation if requested
    if args.run_first:
        print("Running consolidation first...")
        scheduler.run_now(dry_run=args.dry_run)

    validation = scheduler.validate_live_gates()

    if "reason" in validation:
        print(f"Status: {validation['reason']}")
        return 1

    all_pass = True
    for gate_name, gate_info in validation.get("gates", {}).items():
        status = "✓ PASS" if gate_info["pass"] else "✗ FAIL"
        print(f"{gate_name}:")
        print(f"  Value: {gate_info['value']}")
        print(f"  Expected: {gate_info['expected']}")
        print(f"  Status: {status}")

        if not gate_info["pass"]:
            all_pass = False

    print("-" * 50)
    print(f"Overall: {'✓ ALL GATES PASS' if all_pass else '✗ SOME GATES FAILED'}")

    return 0 if all_pass else 1


def cmd_start_daemon(args: argparse.Namespace) -> int:
    """Start the scheduler daemon."""
    scheduler = create_scheduler(dry_run=args.dry_run)

    print(f"\nStarting consolidation scheduler daemon...")
    print(f"Schedule: Daily at {scheduler.get_config().schedule_time.isoformat()} UTC")
    print(f"Dry run: {args.dry_run}")
    print("\nPress Ctrl+C to stop\n")

    if not scheduler.start():
        print("ERROR: Failed to start scheduler")
        return 1

    try:
        # Keep running until interrupted
        import time

        while scheduler.is_scheduler_running():
            time.sleep(60)
            # Log heartbeat
            logger.debug("Scheduler heartbeat")
    except KeyboardInterrupt:
        print("\nShutting down...")
        scheduler.stop()

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Show or export configuration."""
    config = ConsolidationConfig()

    print("\nConsolidation Configuration:")
    print("-" * 50)

    if args.json:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        for key, value in config.to_dict().items():
            print(f"  {key}: {value}")

        print("\nRetention Policies:")
        for memory_type, policy in config.retention_policies.items():
            print(f"  {memory_type.value}:")
            print(f"    Retention: {policy.retention_days} days")
            print(f"    Archive to cold: {policy.archive_to_cold}")
            print(f"    Min access count: {policy.min_access_count}")
            if policy.preserve_if_tagged:
                print(f"    Preserve tags: {policy.preserve_if_tagged}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Memory Consolidation Scheduler CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run consolidation once")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode (no actual changes)",
    )
    run_parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Run with actual changes",
    )
    run_parser.add_argument(
        "--skip-archive",
        action="store_true",
        help="Skip archival phase",
    )
    run_parser.add_argument(
        "--skip-promote",
        action="store_true",
        help="Skip promotion phase",
    )
    run_parser.set_defaults(func=cmd_run)

    # rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Roll back a memory")
    rollback_parser.add_argument("memory_id", help="Memory ID to roll back")
    rollback_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rollback",
    )
    rollback_parser.set_defaults(func=cmd_rollback)

    # rollback-batch command
    rollback_batch_parser = subparsers.add_parser(
        "rollback-batch", help="Roll back multiple memories"
    )
    rollback_batch_parser.add_argument(
        "memory_ids", nargs="+", help="Memory IDs to roll back"
    )
    rollback_batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rollback",
    )
    rollback_batch_parser.set_defaults(func=cmd_rollback_batch)

    # status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.set_defaults(func=cmd_status)

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate live gates")
    validate_parser.add_argument(
        "--run-first",
        action="store_true",
        help="Run consolidation before validating",
    )
    validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run mode for consolidation",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # start-daemon command
    daemon_parser = subparsers.add_parser("start-daemon", help="Start scheduler daemon")
    daemon_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode",
    )
    daemon_parser.set_defaults(func=cmd_start_daemon)

    # config command
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    config_parser.set_defaults(func=cmd_config)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Handle --no-dry-run for run command
    if hasattr(args, "no_dry_run") and args.no_dry_run:
        args.dry_run = False

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
