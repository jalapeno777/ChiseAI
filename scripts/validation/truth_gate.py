#!/usr/bin/env python3
"""
Truth Gate - Command-backed validation tool for ChiseAI workflow.

Validates:
1. Workflow status file entries match actual commit file paths
2. Recorded test counts match command outputs (pytest --collect-only)
3. Merge truth confirms commits on local main + origin/main

Usage:
    truth_gate.py --check workflow-status [--story-id STRONG-001-A-S3]
    truth_gate.py --check test-counts [--path tests/...]
    truth_gate.py --check merge-truth --commits <sha1> [<sha2> ...]
    truth_gate.py --check all --story-id <id>
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from truth_gate_checks.workflow_status import check_workflow_status
from truth_gate_checks.test_counts import check_test_counts
from truth_gate_checks.merge_truth import check_merge_truth


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Truth Gate - Command-backed validation for ChiseAI workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --check workflow-status --story-id STRONG-001-A-S3
  %(prog)s --check test-counts --path tests/unit/
  %(prog)s --check merge-truth --commits abc123 def456
  %(prog)s --check all --story-id STRONG-001-A-S3 --output json
        """,
    )

    parser.add_argument(
        "--check",
        choices=["workflow-status", "test-counts", "merge-truth", "all"],
        required=True,
        help="Type of check to perform",
    )

    parser.add_argument(
        "--story-id",
        type=str,
        help="Story ID to filter checks (e.g., STRONG-001-A-S3)",
    )

    parser.add_argument(
        "--path",
        type=str,
        help="Path for test-counts check (e.g., tests/unit/)",
    )

    parser.add_argument(
        "--commits",
        nargs="+",
        help="Commit SHAs for merge-truth check",
    )

    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--workflow-file",
        type=str,
        default="docs/bmm-workflow-status.yaml",
        help="Path to workflow status file (default: docs/bmm-workflow-status.yaml)",
    )

    return parser


def format_output(result: dict[str, Any], output_format: str) -> str:
    """Format result for output."""
    if output_format == "json":
        return json.dumps(result, indent=2)

    # Text format
    lines = []
    lines.append("=" * 60)
    lines.append(f"TRUTH GATE RESULT: {'PASS' if result['passed'] else 'FAIL'}")
    lines.append("=" * 60)
    lines.append(f"Check Type: {result['check_type']}")
    lines.append(f"Timestamp: {result['timestamp']}")

    if "story_id" in result and result["story_id"]:
        lines.append(f"Story ID: {result['story_id']}")

    lines.append("-" * 60)

    # Add details based on check type
    if "checks" in result:
        for check in result["checks"]:
            status = "✓" if check.get("passed", False) else "✗"
            lines.append(f"{status} {check['name']}: {check.get('message', '')}")

            if "details" in check and check["details"]:
                for detail in check["details"]:
                    detail_status = "✓" if detail.get("passed", False) else "✗"
                    lines.append(f"    {detail_status} {detail.get('message', '')}")

    # Summary
    lines.append("-" * 60)
    lines.append(f"Total Checks: {result.get('total_checks', 0)}")
    lines.append(f"Passed: {result.get('passed_checks', 0)}")
    lines.append(f"Failed: {result.get('failed_checks', 0)}")

    if "errors" in result and result["errors"]:
        lines.append("\nERRORS:")
        for error in result["errors"]:
            lines.append(f"  - {error}")

    lines.append("=" * 60)

    return "\n".join(lines)


def run_all_checks(
    story_id: str | None,
    workflow_file: str,
    output_format: str,
) -> dict[str, Any]:
    """Run all checks and combine results."""
    from datetime import datetime

    all_results = []
    errors = []

    # Run workflow-status check
    try:
        workflow_result = check_workflow_status(story_id, workflow_file)
        all_results.append(workflow_result)
    except Exception as e:
        errors.append(f"workflow-status check failed: {e}")
        all_results.append(
            {
                "check_type": "workflow-status",
                "passed": False,
                "errors": [str(e)],
            }
        )

    # Run test-counts check (if story_id provided)
    if story_id:
        try:
            test_result = check_test_counts(story_id, None, workflow_file)
            all_results.append(test_result)
        except Exception as e:
            errors.append(f"test-counts check failed: {e}")
            all_results.append(
                {
                    "check_type": "test-counts",
                    "passed": False,
                    "errors": [str(e)],
                }
            )

    # Combine results
    combined = {
        "check_type": "all",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "story_id": story_id,
        "passed": all(r.get("passed", False) for r in all_results),
        "checks": all_results,
        "total_checks": len(all_results),
        "passed_checks": sum(1 for r in all_results if r.get("passed", False)),
        "failed_checks": sum(1 for r in all_results if not r.get("passed", False)),
        "errors": errors,
    }

    return combined


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    result: dict[str, Any]

    try:
        if args.check == "workflow-status":
            result = check_workflow_status(args.story_id, args.workflow_file)

        elif args.check == "test-counts":
            result = check_test_counts(args.story_id, args.path, args.workflow_file)

        elif args.check == "merge-truth":
            if not args.commits:
                print(
                    "Error: --commits required for merge-truth check", file=sys.stderr
                )
                return 1
            result = check_merge_truth(args.commits)

        elif args.check == "all":
            result = run_all_checks(args.story_id, args.workflow_file, args.output)

        else:
            print(f"Error: Unknown check type: {args.check}", file=sys.stderr)
            return 1

    except Exception as e:
        result = {
            "check_type": args.check,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "story_id": args.story_id,
            "passed": False,
            "errors": [str(e)],
        }

    # Output result
    print(format_output(result, args.output))

    # Return exit code
    return 0 if result.get("passed", False) else 1


if __name__ == "__main__":
    sys.exit(main())
