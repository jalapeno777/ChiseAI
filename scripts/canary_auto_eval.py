#!/usr/bin/env python3
"""Canary auto-evaluation CLI tool.

Provides commands to run canary gate evaluations, schedule automatic
evaluations, and check status of active canaries.

Usage:
    python -m scripts.canary_auto_eval run [--canary-id ID]
    python -m scripts.canary_auto_eval schedule [--interval MINUTES]
    python -m scripts.canary_auto_eval status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.bootstrap import bootstrap
from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import (
    CanaryDeployment,
    CanaryStatus,
)
from execution.canary.monitor import CanaryMonitor


def get_default_reports_dir() -> Path:
    """Get default reports directory."""
    return Path("reports/canary")


def load_canary_if_exists(canary_id: str) -> CanaryDeployment | None:
    """Load canary from disk if it exists."""
    canary_path = Path(f"data/canary/{canary_id}.json")
    if canary_path.exists():
        data = json.loads(canary_path.read_text())
        return CanaryDeployment.from_dict(data)
    return None


def save_canary(canary: CanaryDeployment) -> None:
    """Save canary to disk."""
    canary_path = Path(f"data/canary/{canary.canary_id}.json")
    canary_path.parent.mkdir(parents=True, exist_ok=True)
    canary_path.write_text(json.dumps(canary.to_dict(), indent=2))


def format_canary_status(canary: CanaryDeployment) -> str:
    """Format canary status for display."""
    status_emoji = {
        CanaryStatus.PENDING: "⏳",
        CanaryStatus.RUNNING: "🔄",
        CanaryStatus.PASSED: "✅",
        CanaryStatus.FAILED: "❌",
        CanaryStatus.ROLLED_BACK: "⏪",
        CanaryStatus.PROMOTED: "🚀",
    }
    emoji = status_emoji.get(canary.status, "❓")
    return f"{emoji} {canary.status.value.upper()}"


async def cmd_run(args: argparse.Namespace) -> int:
    """Run single evaluation command.

    Returns:
        Exit code: 0=all pass, 1=any fail, 2=no active
    """
    reports_dir = get_default_reports_dir()
    evaluator = GateEvaluator()

    # Load or create canary
    if args.canary_id:
        canary = load_canary_if_exists(args.canary_id)
        if canary is None:
            print(f"❌ Canary not found: {args.canary_id}")
            return 1
        canaries = [canary]
    else:
        # Find all canaries
        canary_dir = Path("data/canary")
        canaries = []
        if canary_dir.exists():
            for f in canary_dir.glob("*.json"):
                data = json.loads(f.read_text())
                canary = CanaryDeployment.from_dict(data)
                if canary.status in (CanaryStatus.RUNNING, CanaryStatus.PENDING):
                    canaries.append(canary)

    if not canaries:
        print("ℹ️  No active canaries found")
        return 2

    print(f"🔍 Evaluating {len(canaries)} active canary(s)...\n")

    all_passed = True
    any_failed = False

    for canary in canaries:
        # Generate artifacts
        artifacts = evaluator.generate_evaluation_artifact(
            canary,
            output_dir=reports_dir / canary.canary_id / "evaluations",
        )

        # Get summary for display
        summary = evaluator.generate_pass_fail_summary(canary)

        print(f"📊 {canary.canary_id} ({canary.strategy_id})")
        print(f"   Status: {summary['status']}")
        print(
            f"   Gates: {summary['gate_summary']['pass']} pass, "
            f"{summary['gate_summary']['fail']} fail, "
            f"{summary['gate_summary']['pending']} pending"
        )

        if summary["reasons"]:
            for reason in summary["reasons"][:3]:  # Show first 3
                print(f"   ⚠️  {reason}")

        print(f"   📁 Artifacts: {artifacts['json']}")
        print()

        if summary["status"] == "FAIL":
            any_failed = True
            all_passed = False
        elif summary["status"] != "PASS":
            all_passed = False

    if any_failed:
        print("❌ Some canaries failed evaluation")
        return 1
    elif all_passed:
        print("✅ All canaries passed evaluation")
        return 0
    else:
        print("⏳ Some canaries still pending")
        return 0


async def cmd_schedule(args: argparse.Namespace) -> int:
    """Schedule automatic evaluations command.

    Returns:
        Exit code: 0=success, 1=error
    """
    interval = args.interval or 15
    reports_dir = get_default_reports_dir()

    print(f"📅 Scheduling auto-evaluation every {interval} minutes")
    print(f"📁 Reports directory: {reports_dir}")
    print("\n⚠️  Note: This would start a background scheduler.")
    print("   In production, use a proper cron job or task scheduler.")
    print()

    # Create monitor with schedule config
    monitor = CanaryMonitor(check_interval_minutes=interval)

    # Schedule the auto-evaluation
    config = monitor.schedule_auto_evaluation(
        cron_interval_minutes=interval,
        storage_path=reports_dir,
    )

    print("✅ Schedule configuration created:")
    print(f"   Interval: {config['interval_minutes']} minutes")
    print(f"   Next evaluation: {datetime.fromtimestamp(config['next_evaluation_at'])}")
    print()
    print("To run evaluations manually, use: canary_auto_eval run")

    # Save schedule config
    schedule_path = reports_dir / "schedule_config.json"
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    schedule_path.write_text(json.dumps(config, indent=2))
    print(f"   Config saved: {schedule_path}")

    return 0


async def cmd_status(args: argparse.Namespace) -> int:
    """Show status of active canaries.

    Returns:
        Exit code: 0=has active, 1=none active
    """
    canary_dir = Path("data/canary")

    if not canary_dir.exists():
        print("ℹ️  No canary data directory found")
        return 1

    active_canaries = []
    all_canaries = []

    for f in canary_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            canary = CanaryDeployment.from_dict(data)
            all_canaries.append(canary)
            if canary.status in (CanaryStatus.RUNNING, CanaryStatus.PENDING):
                active_canaries.append(canary)
        except Exception as e:
            print(f"⚠️  Error loading {f}: {e}")

    if not all_canaries:
        print("ℹ️  No canaries found")
        return 1

    print(f"\n📋 Canary Status Summary")
    print(f"   Total: {len(all_canaries)} | Active: {len(active_canaries)}")
    print()

    # Show active first
    if active_canaries:
        print("🔄 Active Canaries:")
        for canary in active_canaries:
            duration_days = (datetime.now().timestamp() - canary.start_time) / 86400
            print(f"   • {canary.canary_id}")
            print(f"     Strategy: {canary.strategy_id}")
            print(f"     Status: {format_canary_status(canary)}")
            print(f"     Duration: {duration_days:.1f} days")
            print(f"     Trades: {canary.metrics.total_trades}")
            print(f"     Win Rate: {canary.metrics.win_rate_pct:.2f}%")
            print(f"     Drawdown: {canary.metrics.max_drawdown_pct:.2f}%")
            print()

    # Show completed
    completed = [c for c in all_canaries if c not in active_canaries]
    if completed:
        print("✅ Completed Canaries:")
        for canary in completed[:5]:  # Show last 5
            print(f"   • {canary.canary_id}: {format_canary_status(canary)}")
        if len(completed) > 5:
            print(f"   ... and {len(completed) - 5} more")
        print()

    return 0 if active_canaries else 1


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="canary_auto_eval",
        description="Canary gate auto-evaluation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run                    # Evaluate all active canaries
  %(prog)s run --canary-id canary-001  # Evaluate specific canary
  %(prog)s schedule --interval 15  # Schedule evaluations every 15 min
  %(prog)s status                 # Show active canaries

Exit Codes:
  0 - All canaries passed / Success
  1 - Any canary failed / Error
  2 - No active canaries found
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run single evaluation on active canaries",
    )
    run_parser.add_argument(
        "--canary-id",
        help="Specific canary ID to evaluate (default: all active)",
    )

    # schedule command
    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Schedule automatic evaluations",
    )
    schedule_parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Evaluation interval in minutes (default: 15)",
    )

    # status command
    subparsers.add_parser(
        "status",
        help="Show status of active canaries",
    )

    return parser


async def main_async() -> int:
    """Async main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "run":
        return await cmd_run(args)
    elif args.command == "schedule":
        return await cmd_schedule(args)
    elif args.command == "status":
        return await cmd_status(args)
    else:
        parser.print_help()
        return 1


def main() -> int:
    """Main entry point."""
    # Bootstrap environment first
    bootstrap(load_env=True)

    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
