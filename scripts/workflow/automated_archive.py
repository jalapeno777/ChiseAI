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
    python scripts/workflow/automated_archive.py --live --i-understand-live-mode
    WORKFLOW_ARCHIVE_LIVE=1 python scripts/workflow/automated_archive.py --i-understand-live-mode

Exit Codes:
    0 - Archival completed successfully
    1 - Preflight checks failed
    2 - Archival execution failed
    3 - Post-archival verification failed
    4 - Safety check failed (live mode without confirmation)
    5 - Lock acquisition failed
    6 - Backup failed
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Configuration
PREFLIGHT_SCRIPT = Path("scripts/workflow/preflight_archive.py")
ARCHIVE_SCRIPT = Path("scripts/workflow/migration/archive_stories.py")
VERIFY_SCRIPT = Path("scripts/workflow/migration/verify_archive.py")
NOTIFIER_SCRIPT = Path("scripts/notifications/discord_workflow_notifier.py")
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")
BACKUP_DIR = Path(".backup")

AUTOMATION_VERSION = "2.0.0"
DEFAULT_BATCH_SIZE = 10

# Redis configuration
REDIS_LOCK_KEY = "bmad:chiseai:workflow:archival:lock"
REDIS_LOCK_TTL_SECONDS = 3600  # 1 hour


class ExecutionReport:
    """Report of automated archival execution."""

    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        self.version = AUTOMATION_VERSION
        self.live_mode = False
        self.dry_run_mode = True
        self.preflight_passed = False
        self.preflight_exit_code = 0
        self.lock_acquired = False
        self.backup_created = False
        self.backup_path: Optional[str] = None
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
            "live_mode": self.live_mode,
            "dry_run_mode": self.dry_run_mode,
            "preflight_passed": self.preflight_passed,
            "preflight_exit_code": self.preflight_exit_code,
            "lock_acquired": self.lock_acquired,
            "backup_created": self.backup_created,
            "backup_path": self.backup_path,
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

        # Mode indicator
        if self.live_mode:
            print("🚨 MODE: LIVE EXECUTION - CHANGES WILL BE MADE")
        else:
            print("🛡️  MODE: DRY-RUN - NO CHANGES WILL BE MADE")
        print()

        print("SAFETY CHECKS:")
        if self.lock_acquired:
            print("  ✓ Redis lock acquired")
        else:
            print("  ⚠ Redis lock not acquired (may be unavailable)")
        if self.backup_created:
            print(f"  ✓ Backup created: {self.backup_path}")
        else:
            print("  ⚠ No backup created")
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
            if self.live_mode:
                print("RESULT: ✓ SUCCESS - Archival completed and verified (LIVE MODE)")
            else:
                print("RESULT: ✓ SUCCESS - Dry-run completed successfully")
        elif not self.preflight_passed:
            print("RESULT: ✗ BLOCKED - Preflight checks failed")
        elif not self.archival_executed:
            print("RESULT: ✗ FAILED - Archival execution failed")
        else:
            print("RESULT: ✗ FAILED - Post-archival verification failed")
        print("=" * 80)


def _get_redis_client():
    """Get Redis client for lock management."""
    try:
        import redis

        redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
        redis_port = int(os.getenv("REDIS_PORT", "6380"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Test connection
        client.ping()
        return client
    except Exception as e:
        print(f"⚠ Warning: Redis connection failed: {e}")
        return None


def acquire_lock() -> tuple[bool, str]:
    """
    Acquire Redis lock for archival operation.

    Returns:
        (acquired, message) - Whether lock was acquired and status message
    """
    client = _get_redis_client()
    if client is None:
        return False, "Redis unavailable - cannot acquire lock"

    try:
        # Use SET NX (set if not exists) with expiration
        lock_value = f"archival-{datetime.now(timezone.utc).isoformat()}"
        acquired = client.set(
            REDIS_LOCK_KEY,
            lock_value,
            nx=True,  # Only set if key doesn't exist
            ex=REDIS_LOCK_TTL_SECONDS,
        )

        if acquired:
            return True, f"Lock acquired (TTL: {REDIS_LOCK_TTL_SECONDS}s)"
        else:
            # Check existing lock info
            existing = client.get(REDIS_LOCK_KEY)
            ttl = client.ttl(REDIS_LOCK_KEY)
            return (
                False,
                f"Lock already held by another process (value: {existing}, TTL: {ttl}s)",
            )
    except Exception as e:
        return False, f"Failed to acquire lock: {e}"


def release_lock() -> bool:
    """Release Redis lock."""
    client = _get_redis_client()
    if client is None:
        return False

    try:
        client.delete(REDIS_LOCK_KEY)
        return True
    except Exception as e:
        print(f"⚠ Warning: Failed to release lock: {e}")
        return False


def create_backup() -> tuple[bool, Optional[Path]]:
    """
    Create timestamped backup of workflow-status.yaml.

    Returns:
        (success, backup_path) - Whether backup was created and its path
    """
    if not WORKFLOW_STATUS_PATH.exists():
        return False, None

    try:
        # Create backup directory if it doesn't exist
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Generate timestamped backup filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_filename = f"workflow-status-{timestamp}.yaml"
        backup_path = BACKUP_DIR / backup_filename

        # Copy file with metadata
        shutil.copy2(WORKFLOW_STATUS_PATH, backup_path)

        # Verify backup
        if backup_path.exists():
            # Compute checksums for verification
            original_hash = hashlib.sha256(
                WORKFLOW_STATUS_PATH.read_bytes()
            ).hexdigest()
            backup_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()

            if original_hash == backup_hash:
                return True, backup_path
            else:
                backup_path.unlink()  # Remove corrupted backup
                return False, None

        return False, None
    except Exception as e:
        print(f"⚠ Warning: Backup creation failed: {e}")
        return False, None


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


def run_archival(
    batch_size: int, verbose: bool = False, live_mode: bool = False
) -> tuple[bool, int, str, int]:
    """
    Execute archival.

    Args:
        batch_size: Maximum number of stories to archive
        verbose: Show detailed output
        live_mode: If True, pass --execute; otherwise pass --dry-run

    Returns:
        (success, exit_code, output, stories_archived)
    """
    cmd = [
        "python3",
        str(ARCHIVE_SCRIPT),
        "--batch-size",
        str(batch_size),
        "--migrated-by",
        "automated-archive",
    ]

    # Add execution mode flag
    if live_mode:
        cmd.append("--execute")
    else:
        cmd.append("--dry-run")

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

        success = result.returncode == 0
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


def send_notification(report: ExecutionReport, webhook_url: str | None = None) -> bool:
    """
    Send notification about archival results.

    Returns:
        True if notification was sent successfully, False otherwise
    """
    if not NOTIFIER_SCRIPT.exists():
        return False

    # Determine notification level based on mode and results
    if report.live_mode:
        if not report.preflight_passed or not report.archival_executed:
            level = "CRITICAL"
        elif not report.post_verification_passed:
            level = "CRITICAL"
        else:
            level = "SUCCESS"
    else:
        if not report.preflight_passed or not report.archival_executed:
            level = "WARNING"
        elif not report.post_verification_passed:
            level = "ERROR"
        else:
            level = "INFO"

    # Build message with mode indicator
    mode_indicator = "🚨 LIVE MODE" if report.live_mode else "🛡️ DRY-RUN"

    if (
        report.preflight_passed
        and report.archival_executed
        and report.post_verification_passed
    ):
        if report.live_mode:
            title = f"✓ Workflow Archival Complete - {mode_indicator}"
            message = (
                f"Successfully archived {report.stories_archived} stories in LIVE MODE. "
                f"Backup: {report.backup_path or 'N/A'}. All verifications passed."
            )
        else:
            title = f"✓ Workflow Archival Dry-Run Complete"
            message = f"Dry-run completed. {report.stories_archived} stories would be archived. No changes made."
    elif not report.preflight_passed:
        title = f"✗ Workflow Archival Blocked - {mode_indicator}"
        message = f"Preflight checks failed with exit code {report.preflight_exit_code}. Archival was not executed."
    elif not report.archival_executed:
        title = f"✗ Workflow Archival Failed - {mode_indicator}"
        message = (
            f"Archival execution failed with exit code {report.archival_exit_code}."
        )
    else:
        title = f"✗ Workflow Archival Verification Failed - {mode_indicator}"
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
        description="Automated workflow status archival with preflight checks and safety controls"
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

    # Live mode controls
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Enable live mode (actual changes will be made). Default is dry-run.",
    )
    parser.add_argument(
        "--i-understand-live-mode",
        action="store_true",
        default=False,
        help="Required confirmation flag for live mode execution",
    )

    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    report = ExecutionReport()

    # Determine live mode from args or environment
    env_live_mode = os.environ.get("WORKFLOW_ARCHIVE_LIVE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    report.live_mode = args.live or env_live_mode
    report.dry_run_mode = not report.live_mode

    # Print header with mode indication
    print("=" * 80)
    print("WORKFLOW STATUS AUTOMATED ARCHIVE")
    print("=" * 80)
    print(f"Version: {AUTOMATION_VERSION}")
    print(f"Started: {start_time.isoformat()}Z")
    print(f"Batch Size: {args.batch_size}")

    if report.live_mode:
        print("🚨 RUNNING IN LIVE MODE - CHANGES WILL BE MADE")
    else:
        print("🛡️  RUNNING IN DRY-RUN MODE - NO CHANGES WILL BE MADE")

    print("=" * 80)
    print()

    # Safety check for live mode
    if report.live_mode:
        env_confirmed = os.environ.get("WORKFLOW_ARCHIVE_LIVE_CONFIRM", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        flag_confirmed = args.i_understand_live_mode

        if not (env_confirmed or flag_confirmed):
            print("🚫 SAFETY CHECK FAILED")
            print()
            print("Live mode requires explicit confirmation. Use one of:")
            print("  1. --i-understand-live-mode flag")
            print("  2. WORKFLOW_ARCHIVE_LIVE_CONFIRM=1 environment variable")
            print()
            print("This safety measure prevents accidental live execution.")
            print()
            print("Example:")
            print(
                "  python scripts/workflow/automated_archive.py --live --i-understand-live-mode"
            )
            print(
                "  WORKFLOW_ARCHIVE_LIVE=1 WORKFLOW_ARCHIVE_LIVE_CONFIRM=1 python scripts/workflow/automated_archive.py"
            )
            return 4

        print("✓ Live mode safety check passed")
        print()

    # Step 0: Acquire lock and create backup (for live mode)
    if report.live_mode:
        print("Step 0/4: Acquiring lock and creating backup...")

        # Acquire Redis lock
        lock_acquired, lock_message = acquire_lock()
        report.lock_acquired = lock_acquired

        if lock_acquired:
            print(f"  ✓ {lock_message}")
        else:
            print(f"  ⚠ {lock_message}")
            report.warnings.append(f"Lock: {lock_message}")
            # Continue anyway - lock is advisory

        # Create backup
        backup_success, backup_path = create_backup()
        report.backup_created = backup_success
        report.backup_path = str(backup_path) if backup_path else None

        if backup_success:
            print(f"  ✓ Backup created: {backup_path}")
        else:
            print("  ✗ Backup creation FAILED")
            report.errors.append("Failed to create backup before live archival")
            # Release lock if we acquired it
            if lock_acquired:
                release_lock()
            return 6

        print()
    else:
        print("Step 0/4: SKIPPED (dry-run mode)")
        print()

    # Step 1: Preflight Checks
    if args.skip_preflight:
        print("⚠ WARNING: Preflight checks skipped (--skip-preflight)")
        report.preflight_passed = True
        report.warnings.append("Preflight checks were skipped")
    else:
        print("Step 1/4: Running preflight checks...")
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
        print("Step 2/4: Executing archival...")
        if report.live_mode:
            print("  🚨 LIVE MODE: Changes will be made to workflow-status.yaml")
        else:
            print("  🛡️  DRY-RUN: No changes will be made")
        print()

        (
            report.archival_executed,
            report.archival_exit_code,
            archival_output,
            report.stories_archived,
        ) = run_archival(
            batch_size=args.batch_size,
            verbose=args.verbose,
            live_mode=report.live_mode,
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
        print("Step 2/4: SKIPPED (preflight failed)")

    print()

    # Step 3: Post-Archival Verification (only if archival executed)
    if report.archival_executed:
        print("Step 3/4: Running post-archival verification...")
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
        print("Step 3/4: SKIPPED (archival not executed)")

    print()

    # Step 4: Cleanup (release lock in live mode)
    if report.live_mode:
        print("Step 4/4: Cleaning up...")
        if release_lock():
            print("  ✓ Lock released")
        else:
            print("  ⚠ Lock release failed (will expire naturally)")
        print()
    else:
        print("Step 4/4: SKIPPED (dry-run mode)")
        print()

    # Calculate duration
    end_time = datetime.now(timezone.utc)
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
