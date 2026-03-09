#!/usr/bin/env python3
"""
Workflow Status Automated Archive Script
Story: ST-WORKFLOW-ARCHIVAL-001

Main automation wrapper for workflow status archival.
Calls preflight checks first (fail-closed), then executes archival if safe.

Usage:
    python scripts/workflow/automated_archive.py
    python scripts/workflow/automated_archive.py --batch-size 20
    python scripts/workflow/automated_archive.py --verbose
    python scripts/workflow/automated_archive.py --notify

Exit Codes:
    0 - Archival completed successfully
    1 - Preflight checks failed
    2 - Archival execution failed
    3 - Post-archival verification failed
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Configuration
PREFLIGHT_SCRIPT = Path("scripts/workflow/preflight_archive.py")
ARCHIVE_SCRIPT = Path("scripts/workflow/migration/archive_stories.py")
VERIFY_SCRIPT = Path("scripts/workflow/migration/verify_archive.py")
NOTIFIER_SCRIPT = Path("scripts/notifications/discord_workflow_notifier.py")

AUTOMATION_VERSION = "1.0.0"
DEFAULT_BATCH_SIZE = 10


class ExecutionReport:
    """Report of automated archival execution."""

    def __init__(self):
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.version = AUTOMATION_VERSION
        self.preflight_passed = False
        self.preflight_exit_code = 0
        self.archival_executed = False
        self.archival_exit_code = 0
        self.archival_output = ""
        self.post_verification_passed = False
        self.post_verification_exit_code = 0
        self.stories_archived = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.duration_seconds = 0.0

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "preflight_passed": self.preflight_passed,
            "preflight_exit_code": self.preflight_exit_code,
            "archival_executed": self.archival_executed,
            "archival_exit_code": self.archival_exit_code,
            "post_verification_passed": self.post_verification_passed,
            "post_verification_exit_code": self.post_verification_exit_code,
            "stories_archived": self.stories_archived,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": self.duration_seconds,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def print_report(self):
        """Print human-readable execution report."""
        print("=" * 80)
        print("WORKFLOW STATUS AUTOMATED ARCHIVE EXECUTION REPORT")
        print("=" * 80)
        print(f"Version: {self.version}")
        print(f"Timestamp: {self.timestamp}")
        print(f"Duration: {self.duration_seconds:.2f} seconds")
        print()

        print("PREFLIGHT CHECKS:")
        if self.preflight_passed:
            print("  ✓ All preflight checks passed")
        else:
            print(
                f"  ✗ Preflight checks failed (exit code: {self.preflight_exit_code})"
            )
        print()

        print("ARCHIVAL EXECUTION:")
        if self.archival_executed:
            print(f"  ✓ Archival executed (exit code: {self.archival_exit_code})")
            print(f"  Stories archived: {self.stories_archived}")
        else:
            print("  ✗ Archival was not executed")
        print()

        print("POST-ARCHIVAL VERIFICATION:")
        if self.post_verification_passed:
            print("  ✓ All archives verified successfully")
        else:
            print(
                f"  ✗ Verification failed (exit code: {self.post_verification_exit_code})"
            )
        print()

        if self.warnings:
            print("WARNINGS:")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")
            print()

        if self.errors:
            print("ERRORS:")
            for error in self.errors:
                print(f"  ✗ {error}")
            print()

        print("=" * 80)
        if (
            self.preflight_passed
            and self.archival_executed
            and self.post_verification_passed
        ):
            print("RESULT: ✓ SUCCESS - Archival completed and verified")
        elif not self.preflight_passed:
            print("RESULT: ✗ BLOCKED - Preflight checks failed")
        elif not self.archival_executed:
            print("RESULT: ✗ FAILED - Archival execution failed")
        else:
            print("RESULT: ✗ FAILED - Post-archival verification failed")
        print("=" * 80)


def run_preflight_checks(verbose: bool = False) -> tuple[bool, int, str]:
    """
    Run preflight checks.

    Returns:
        (passed, exit_code, output)
    """
    cmd = ["python3", str(PREFLIGHT_SCRIPT)]
    if verbose:
        cmd.append("--verbose")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Preflight returns 0 if all passed, 1 if non-critical failures, 2 if critical
        passed = result.returncode == 0
        return passed, result.returncode, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        return False, -1, "Preflight checks timed out after 120 seconds"
    except Exception as e:
        return False, -2, f"Failed to run preflight checks: {e}"


def run_archival(batch_size: int, verbose: bool = False) -> tuple[bool, int, str, int]:
    """
    Execute archival.

    Returns:
        (success, exit_code, output, stories_archived)
    """
    cmd = [
        "python3",
        str(ARCHIVE_SCRIPT),
        "--execute",
        "--batch-size",
        str(batch_size),
        "--migrated-by",
        "automated-archive",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout + result.stderr

        # Parse stories archived from output
        stories_archived = 0
        import re

        match = re.search(r"Successfully archived:\s*(\d+)", output)
        if match:
            stories_archived = int(match.group(1))

        success = result.returncode == 0 and stories_archived > 0
        return success, result.returncode, output, stories_archived

    except subprocess.TimeoutExpired:
        return False, -1, "Archival timed out after 300 seconds", 0
    except Exception as e:
        return False, -2, f"Failed to run archival: {e}", 0


def run_post_verification(verbose: bool = False) -> tuple[bool, int, str]:
    """
    Run post-archival verification.

    Returns:
        (passed, exit_code, output)
    """
    cmd = ["python3", str(VERIFY_SCRIPT), "--all"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        passed = result.returncode == 0
        return passed, result.returncode, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        return False, -1, "Verification timed out after 120 seconds"
    except Exception as e:
        return False, -2, f"Failed to run verification: {e}"


def send_notification(
    report: ExecutionReport, webhook_url: Optional[str] = None
) -> bool:
    """
    Send notification about archival results.

    Returns:
        True if notification was sent successfully, False otherwise
    """
    if not NOTIFIER_SCRIPT.exists():
        return False

    # Determine notification level
    if not report.preflight_passed:
        level = "ERROR"
    elif not report.archival_executed:
        level = "ERROR"
    elif not report.post_verification_passed:
        level = "CRITICAL"
    elif report.stories_archived == 0:
        level = "INFO"
    else:
        level = "INFO"

    # Build message
    if (
        report.preflight_passed
        and report.archival_executed
        and report.post_verification_passed
    ):
        title = "✓ Workflow Archival Complete"
        message = f"Successfully archived {report.stories_archived} stories. All verifications passed."
    elif not report.preflight_passed:
        title = "✗ Workflow Archival Blocked"
        message = f"Preflight checks failed with exit code {report.preflight_exit_code}. Archival was not executed."
    elif not report.archival_executed:
        title = "✗ Workflow Archival Failed"
        message = (
            f"Archival execution failed with exit code {report.archival_exit_code}."
        )
    else:
        title = "✗ Workflow Archival Verification Failed"
        message = f"Post-archival verification failed with exit code {report.post_verification_exit_code}."

    cmd = [
        "python3",
        str(NOTIFIER_SCRIPT),
        "--level",
        level,
        "--title",
        title,
        "--message",
        message,
    ]

    if webhook_url:
        cmd.extend(["--webhook-url", webhook_url])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Automated workflow status archival with preflight checks"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Maximum number of stories to archive (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output execution report as JSON",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Discord notification after execution",
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=os.environ.get("DISCORD_WEBHOOK_URL"),
        help="Discord webhook URL (or set DISCORD_WEBHOOK_URL env var)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks (USE WITH CAUTION)",
    )

    args = parser.parse_args()

    start_time = datetime.utcnow()
    report = ExecutionReport()

    print("=" * 80)
    print("WORKFLOW STATUS AUTOMATED ARCHIVE")
    print("=" * 80)
    print(f"Version: {AUTOMATION_VERSION}")
    print(f"Started: {start_time.isoformat()}Z")
    print(f"Batch Size: {args.batch_size}")
    print("=" * 80)
    print()

    # Step 1: Preflight Checks
    if args.skip_preflight:
        print("⚠ WARNING: Preflight checks skipped (--skip-preflight)")
        report.preflight_passed = True
        report.warnings.append("Preflight checks were skipped")
    else:
        print("Step 1/3: Running preflight checks...")
        report.preflight_passed, report.preflight_exit_code, preflight_output = (
            run_preflight_checks(verbose=args.verbose)
        )

        if args.verbose:
            print(preflight_output)

        if not report.preflight_passed:
            report.errors.append(
                f"Preflight checks failed with exit code {report.preflight_exit_code}"
            )
            print("✗ Preflight checks FAILED - Archival blocked (fail-closed)")
        else:
            print("✓ Preflight checks passed")

    print()

    # Step 2: Archival Execution (only if preflight passed)
    if report.preflight_passed:
        print("Step 2/3: Executing archival...")
        (
            report.archival_executed,
            report.archival_exit_code,
            archival_output,
            report.stories_archived,
        ) = run_archival(
            batch_size=args.batch_size,
            verbose=args.verbose,
        )

        if args.verbose:
            print(archival_output)

        if report.archival_executed:
            print(f"✓ Archival executed: {report.stories_archived} stories archived")
        else:
            report.errors.append(
                f"Archival failed with exit code {report.archival_exit_code}"
            )
            print("✗ Archival execution FAILED")
    else:
        print("Step 2/3: SKIPPED (preflight failed)")

    print()

    # Step 3: Post-Archival Verification (only if archival executed)
    if report.archival_executed:
        print("Step 3/3: Running post-archival verification...")
        (
            report.post_verification_passed,
            report.post_verification_exit_code,
            verify_output,
        ) = run_post_verification(verbose=args.verbose)

        if args.verbose:
            print(verify_output)

        if report.post_verification_passed:
            print("✓ Post-archival verification passed")
        else:
            report.errors.append(
                f"Post-archival verification failed with exit code {report.post_verification_exit_code}"
            )
            print("✗ Post-archival verification FAILED")
    else:
        print("Step 3/3: SKIPPED (archival not executed)")

    print()

    # Calculate duration
    end_time = datetime.utcnow()
    report.duration_seconds = (end_time - start_time).total_seconds()

    # Send notification if requested
    if args.notify:
        print("Sending notification...")
        notification_sent = send_notification(report, args.webhook_url)
        if notification_sent:
            print("✓ Notification sent")
        else:
            print("⚠ Notification failed (non-blocking)")
            report.warnings.append("Failed to send notification")
        print()

    # Output report
    if args.json:
        print(report.to_json())
    else:
        report.print_report()

    # Exit with appropriate code
    if not report.preflight_passed:
        return 1
    elif not report.archival_executed:
        return 2
    elif not report.post_verification_passed:
        return 3
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
