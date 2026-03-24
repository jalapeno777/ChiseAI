#!/usr/bin/env python3
"""
Workflow Status Archive Preflight Guard Script
Story: ST-WORKFLOW-ARCHIVAL-001

Performs pre-execution safety checks before archival automation runs.
Fail-closed design: returns non-zero exit code on any failure.

Usage:
    python scripts/workflow/preflight_archive.py
    python scripts/workflow/preflight_archive.py --verbose
    python scripts/workflow/preflight_archive.py --json

Exit Codes:
    0 - All checks passed, archival can proceed
    1 - One or more checks failed
    2 - Critical failure (data loss risk detected)
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

# Configuration
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_ENTRIES_DIR = Path("docs/archives/workflow-status/entries")
ARCHIVE_SCHEMA_PATH = Path(
    "docs/archives/workflow-status/schema/archive-entry-schema.yaml"
)
ROLLBACK_SCRIPT = Path("scripts/workflow/migration/rollback_archive.py")
VERIFY_SCRIPT = Path("scripts/workflow/migration/verify_archive.py")
ARCHIVE_SCRIPT = Path("scripts/workflow/migration/archive_stories.py")

PREFLIGHT_VERSION = "1.0.0"


class PreflightCheck:
    """Represents a single preflight check with result."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.passed = False
        self.details: dict[str, Any] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "passed": self.passed,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PreflightReport:
    """Aggregates all preflight check results."""

    def __init__(self):
        self.checks: list[PreflightCheck] = []
        self.timestamp = datetime.now(UTC).isoformat() + "Z"
        self.version = PREFLIGHT_VERSION

    def add_check(self, check: PreflightCheck):
        self.checks.append(check)

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def has_critical_failures(self) -> bool:
        """Check if any failures indicate data loss risk."""
        critical_checks = ["no_data_loss", "rollback_readiness", "integrity_validation"]
        for check in self.checks:
            if check.name in critical_checks and not check.passed:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "all_passed": self.all_passed,
            "has_critical_failures": self.has_critical_failures,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def print_report(self, verbose: bool = False):
        """Print human-readable report."""
        print("=" * 80)
        print("WORKFLOW STATUS ARCHIVE PREFLIGHT CHECKS")
        print("=" * 80)
        print(f"Version: {self.version}")
        print(f"Timestamp: {self.timestamp}")
        print()

        for check in self.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.description}")

            if verbose or not check.passed:
                if check.details:
                    for key, value in check.details.items():
                        print(f"    {key}: {value}")

                if check.warnings:
                    for warning in check.warnings:
                        print(f"    ⚠ WARNING: {warning}")

                if check.errors:
                    for error in check.errors:
                        print(f"    ✗ ERROR: {error}")

            print()

        print("=" * 80)
        if self.all_passed:
            print("RESULT: ✓ ALL CHECKS PASSED - Archival can proceed")
        elif self.has_critical_failures:
            print("RESULT: ✗ CRITICAL FAILURES - Archival BLOCKED (data loss risk)")
        else:
            print("RESULT: ✗ CHECKS FAILED - Archival blocked (non-critical)")
        print("=" * 80)


def check_dry_run_candidates() -> PreflightCheck:
    """Perform dry-run candidate scan."""
    check = PreflightCheck(
        name="dry_run_candidates",
        description="Scan for stories that would be archived",
    )

    try:
        # Run archive_stories.py in dry-run mode
        result = subprocess.run(
            ["python3", str(ARCHIVE_SCRIPT), "--dry-run", "--batch-size", "100"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse output to find candidate count
        output = result.stdout + result.stderr

        # Look for "Found X stories eligible for archival"
        import re

        match = re.search(r"Found (\d+) stories eligible for archival", output)
        if match:
            candidate_count = int(match.group(1))
            check.details["candidate_count"] = candidate_count
        else:
            check.details["candidate_count"] = 0

        # Look for any errors in output
        if "ERROR" in output:
            errors = [line for line in output.split("\n") if "ERROR" in line]
            check.errors.extend(errors[:5])  # First 5 errors

        check.passed = result.returncode == 0

    except subprocess.TimeoutExpired:
        check.errors.append("Dry-run scan timed out after 60 seconds")
        check.passed = False
    except Exception as e:
        check.errors.append(f"Failed to run dry-run scan: {e}")
        check.passed = False

    return check


def check_no_data_loss() -> PreflightCheck:
    """Verify no data loss by comparing checksums."""
    check = PreflightCheck(
        name="no_data_loss",
        description="Verify no data loss risk (checksum comparison)",
    )

    try:
        if not ARCHIVE_ENTRIES_DIR.exists():
            check.details["archive_count"] = 0
            check.passed = True
            return check

        # Check each existing archive entry
        archives_checked = 0
        checksum_mismatches = 0

        for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
            with open(archive_file) as f:
                archive_entry = yaml.safe_load(f)

            archives_checked += 1

            # Verify checksum integrity
            integrity = archive_entry.get("integrity", {})
            archived_checksum = integrity.get("archived_checksum")

            if archived_checksum:
                # Recompute checksum
                verification_entry = {
                    k: v for k, v in archive_entry.items() if k != "integrity"
                }
                if "integrity" in archive_entry:
                    verification_entry["integrity"] = {
                        k: v
                        for k, v in archive_entry["integrity"].items()
                        if k != "archived_checksum"
                    }

                content = json.dumps(verification_entry, sort_keys=True, default=str)
                computed_checksum = hashlib.sha256(content.encode()).hexdigest()

                if archived_checksum != computed_checksum:
                    checksum_mismatches += 1
                    check.errors.append(
                        f"Checksum mismatch in {archive_file.name}: "
                        f"stored={archived_checksum[:16]}..., computed={computed_checksum[:16]}..."
                    )

        check.details["archives_checked"] = archives_checked
        check.details["checksum_mismatches"] = checksum_mismatches

        if checksum_mismatches > 0:
            check.passed = False
        else:
            check.passed = True

    except Exception as e:
        check.errors.append(f"Failed to verify data integrity: {e}")
        check.passed = False

    return check


def check_rollback_readiness() -> PreflightCheck:
    """Verify rollback script works correctly."""
    check = PreflightCheck(
        name="rollback_readiness",
        description="Verify rollback capability is functional",
    )

    try:
        # Check rollback script exists
        if not ROLLBACK_SCRIPT.exists():
            check.errors.append(f"Rollback script not found: {ROLLBACK_SCRIPT}")
            check.passed = False
            return check

        # Test rollback script --help
        result = subprocess.run(
            ["python3", str(ROLLBACK_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            check.errors.append("Rollback script --help failed")
            check.passed = False
            return check

        # If archives exist, test dry-run rollback on first one
        if ARCHIVE_ENTRIES_DIR.exists():
            archive_files = list(ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"))
            check.details["available_archives"] = len(archive_files)

            if archive_files:
                # Extract archive ref from filename
                archive_ref = archive_files[0].stem

                # Test dry-run rollback
                result = subprocess.run(
                    [
                        "python3",
                        str(ROLLBACK_SCRIPT),
                        "--archive-ref",
                        archive_ref,
                        "--dry-run",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    check.details["rollback_test"] = (
                        f"Dry-run rollback succeeded for {archive_ref}"
                    )
                    check.passed = True
                else:
                    check.errors.append(f"Dry-run rollback failed for {archive_ref}")
                    check.passed = False
            else:
                check.warnings.append("No archives available for rollback test")
                check.passed = True
        else:
            check.details["available_archives"] = 0
            check.warnings.append("No archive directory found")
            check.passed = True

    except subprocess.TimeoutExpired:
        check.errors.append("Rollback test timed out")
        check.passed = False
    except Exception as e:
        check.errors.append(f"Rollback readiness check failed: {e}")
        check.passed = False

    return check


def check_integrity_validation() -> PreflightCheck:
    """Verify archive integrity using verify_archive.py."""
    check = PreflightCheck(
        name="integrity_validation",
        description="Validate archive integrity with verify_archive.py",
    )

    try:
        # Check verify script exists
        if not VERIFY_SCRIPT.exists():
            check.errors.append(f"Verify script not found: {VERIFY_SCRIPT}")
            check.passed = False
            return check

        # Run verify --all
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT), "--all"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse results
        output = result.stdout + result.stderr

        # Look for "Failed: X" in output
        import re

        failed_match = re.search(r"Failed:\s*(\d+)", output)
        passed_match = re.search(r"Passed:\s*(\d+)", output)
        total_match = re.search(r"Total Archives:\s*(\d+)", output)

        if total_match:
            check.details["total_archives"] = int(total_match.group(1))
        if passed_match:
            check.details["passed"] = int(passed_match.group(1))
        if failed_match:
            check.details["failed"] = int(failed_match.group(1))

        if result.returncode == 0:
            check.passed = True
        else:
            check.errors.append(
                f"Integrity validation failed with exit code {result.returncode}"
            )
            check.passed = False

    except subprocess.TimeoutExpired:
        check.errors.append("Integrity validation timed out after 60 seconds")
        check.passed = False
    except Exception as e:
        check.errors.append(f"Integrity validation failed: {e}")
        check.passed = False

    return check


def check_dependencies() -> PreflightCheck:
    """Check that required dependencies are available."""
    check = PreflightCheck(
        name="dependencies",
        description="Verify required scripts and files exist",
    )

    required_files = [
        (WORKFLOW_STATUS_PATH, "Workflow status file"),
        (ARCHIVE_SCRIPT, "Archive script"),
        (VERIFY_SCRIPT, "Verify script"),
        (ROLLBACK_SCRIPT, "Rollback script"),
        (ARCHIVE_SCHEMA_PATH, "Archive schema"),
    ]

    missing_files = []
    for filepath, description in required_files:
        if not filepath.exists():
            missing_files.append(f"{description}: {filepath}")

    check.details["required_files"] = len(required_files)
    check.details["missing_files"] = len(missing_files)

    if missing_files:
        check.errors.extend(missing_files)
        check.passed = False
    else:
        check.passed = True

    return check


def check_disk_space() -> PreflightCheck:
    """Check available disk space for archival."""
    check = PreflightCheck(
        name="disk_space",
        description="Verify sufficient disk space for archival",
    )

    try:
        # Get disk usage for archive directory (or parent if doesn't exist)
        check_path = (
            ARCHIVE_ENTRIES_DIR
            if ARCHIVE_ENTRIES_DIR.exists()
            else ARCHIVE_ENTRIES_DIR.parent
        )

        stat = os.statvfs(check_path)
        free_bytes = stat.f_bavail * stat.f_frsize
        free_mb = free_bytes / (1024 * 1024)

        check.details["free_space_mb"] = round(free_mb, 2)
        check.details["free_space_gb"] = round(free_mb / 1024, 2)

        # Require at least 100MB free
        min_required_mb = 100
        check.details["required_mb"] = min_required_mb

        if free_mb < min_required_mb:
            check.errors.append(
                f"Insufficient disk space: {free_mb:.1f}MB free, {min_required_mb}MB required"
            )
            check.passed = False
        else:
            check.passed = True

    except Exception as e:
        check.errors.append(f"Failed to check disk space: {e}")
        check.passed = False

    return check


def check_git_status() -> PreflightCheck:
    """Check git status for uncommitted changes."""
    check = PreflightCheck(
        name="git_status",
        description="Verify git working tree is clean",
    )

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            check.errors.append("Failed to check git status")
            check.passed = False
            return check

        uncommitted = result.stdout.strip()
        if uncommitted:
            lines = uncommitted.split("\n")
            check.details["uncommitted_files"] = len(lines)
            check.warnings.append(f"{len(lines)} uncommitted changes in working tree")
            # This is a warning, not a failure - archival can still proceed
            check.passed = True
        else:
            check.details["uncommitted_files"] = 0
            check.passed = True

    except Exception as e:
        check.errors.append(f"Failed to check git status: {e}")
        check.passed = False

    return check


def main():
    parser = argparse.ArgumentParser(
        description="Preflight checks for workflow status archival"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output for all checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--skip",
        type=str,
        default="",
        help="Comma-separated list of checks to skip",
    )

    args = parser.parse_args()

    # Parse skip list
    skip_checks = set(args.skip.split(",")) if args.skip else set()

    # Create report
    report = PreflightReport()

    # Define all checks
    checks_to_run = [
        ("dependencies", check_dependencies),
        ("disk_space", check_disk_space),
        ("git_status", check_git_status),
        ("dry_run_candidates", check_dry_run_candidates),
        ("no_data_loss", check_no_data_loss),
        ("rollback_readiness", check_rollback_readiness),
        ("integrity_validation", check_integrity_validation),
    ]

    # Run checks
    for check_name, check_func in checks_to_run:
        if check_name in skip_checks:
            skipped_check = PreflightCheck(
                name=check_name,
                description="Skipped per --skip flag",
            )
            skipped_check.passed = True
            skipped_check.details["skipped"] = True
            report.add_check(skipped_check)
        else:
            check = check_func()
            report.add_check(check)

    # Output results
    if args.json:
        print(report.to_json())
    else:
        report.print_report(verbose=args.verbose)

    # Exit with appropriate code
    if report.has_critical_failures:
        return 2  # Critical failure
    elif not report.all_passed:
        return 1  # Non-critical failure
    else:
        return 0  # All passed


if __name__ == "__main__":
    sys.exit(main())
