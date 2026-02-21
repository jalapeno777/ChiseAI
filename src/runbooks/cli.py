"""
CLI interface for the runbook executor.

Usage:
    python -m runbooks list
    python -m runbooks execute <runbook-name> [--dry-run]
    python -m runbooks show <runbook-name>
    python -m runbooks history [<runbook-name>] [--limit N]
"""

import argparse
import json
import sys

from .executor import RunbookExecutor
from .parser import RunbookParser


def cmd_list(args: argparse.Namespace) -> int:
    """List all available runbooks."""
    parser = RunbookParser()
    runbooks = parser.list_runbooks()

    if not runbooks:
        print("No runbooks found in docs/runbooks/")
        return 1

    print(f"Available runbooks ({len(runbooks)}):")
    print("-" * 50)

    for name in runbooks:
        try:
            runbook = parser.parse(name)
            executable = "✓" if runbook.is_executable else " "
            category = runbook.metadata.category or "uncategorized"
            severity = runbook.metadata.severity or "unknown"
            print(f"  [{executable}] {name:30} ({category}, {severity})")
        except Exception as e:
            print(f"  [?] {name:30} (error: {e})")

    print("\nLegend: [✓] = executable, [ ] = documentation only")
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    """Execute a runbook."""
    executor = RunbookExecutor(dry_run=args.dry_run)

    result = executor.execute(args.runbook_name, dry_run=args.dry_run)

    if args.json:
        print(result.to_json())

    return 0 if result.success else 1


def cmd_show(args: argparse.Namespace) -> int:
    """Show runbook details."""
    parser = RunbookParser()

    try:
        runbook = parser.parse(args.runbook_name)
    except FileNotFoundError:
        print(f"Error: Runbook '{args.runbook_name}' not found", file=sys.stderr)
        return 1

    print(f"Runbook: {runbook.name}")
    print(f"Path: {runbook.path}")
    print("-" * 50)

    print(f"Title: {runbook.metadata.title or 'N/A'}")
    print(f"Category: {runbook.metadata.category or 'N/A'}")
    print(f"Severity: {runbook.metadata.severity or 'N/A'}")
    print(f"Executable: {'Yes' if runbook.is_executable else 'No'}")
    print(f"Story ID: {runbook.metadata.story_id or 'N/A'}")
    print(f"Maintainers: {', '.join(runbook.metadata.maintainers) or 'N/A'}")
    print(f"Estimated Time: {runbook.metadata.estimated_time or 'N/A'}")

    if runbook.steps:
        print(f"\nExecutable Steps ({len(runbook.steps)}):")
        for i, step in enumerate(runbook.steps, 1):
            print(f"  {i}. {step.name}")
            if step.command:
                print(f"     Command: {step.command[:60]}...")
            if step.script:
                print(f"     Script: {step.script}")
            if step.description:
                print(f"     Description: {step.description}")
    else:
        print("\nNo executable steps defined.")

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show execution history."""
    executor = RunbookExecutor()
    logs = executor.get_execution_history(args.runbook_name, limit=args.limit)

    if not logs:
        if args.runbook_name:
            print(f"No execution history for runbook: {args.runbook_name}")
        else:
            print("No execution history found.")
        return 0

    print(f"Execution History ({len(logs)} entries):")
    print("-" * 70)
    print(f"{'Timestamp':20} {'Runbook':25} {'Result':10} {'Duration':10}")
    print("-" * 70)

    for log_file in logs:
        try:
            data = json.loads(log_file.read_text())
            execution = data.get("execution", {})

            timestamp = execution.get("start_time", "unknown")[:19].replace("T", " ")
            runbook = execution.get("runbook_name", "unknown")
            success = "SUCCESS" if execution.get("success") else "FAILED"
            duration = f"{execution.get('execution_time_seconds', 0):.1f}s"

            print(f"{timestamp:20} {runbook:25} {success:10} {duration:10}")
        except Exception as e:
            print(f"{log_file.name:20} Error reading log: {e}")

    print(f"\nLog directory: {executor.log_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="runbooks",
        description="Execute runbooks linking documentation to automation",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List all available runbooks")
    list_parser.set_defaults(func=cmd_list)

    # execute command
    execute_parser = subparsers.add_parser("execute", help="Execute a runbook")
    execute_parser.add_argument("runbook_name", help="Name of the runbook to execute")
    execute_parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be executed without running",
    )
    execute_parser.add_argument(
        "--json", "-j", action="store_true", help="Output results as JSON"
    )
    execute_parser.set_defaults(func=cmd_execute)

    # show command
    show_parser = subparsers.add_parser("show", help="Show runbook details")
    show_parser.add_argument("runbook_name", help="Name of the runbook to show")
    show_parser.set_defaults(func=cmd_show)

    # history command
    history_parser = subparsers.add_parser("history", help="Show execution history")
    history_parser.add_argument(
        "runbook_name", nargs="?", help="Filter by runbook name (optional)"
    )
    history_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=10,
        help="Maximum number of entries to show (default: 10)",
    )
    history_parser.set_defaults(func=cmd_history)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
