#!/usr/bin/env python3
"""
CI runner wrapper for deprecation validation gate.

This script is designed to be called from the CI pipeline to validate
deprecation warnings. It wraps the validate_deprecations.py script with
CI-specific configuration and output formatting.

Exit codes:
    0 - No new deprecation warnings
    1 - New deprecation warnings found (blocking)
    2 - Configuration or execution error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Default paths
DEFAULT_BASELINE_PATH = "docs/baselines/deprecation-baseline.json"
VALIDATION_SCRIPT = Path("scripts/validation/validate_deprecations.py")


def run_deprecation_check(
    baseline_path: str | None = None,
    changed_files_only: bool = False,
    verbose: bool = False,
) -> int:
    """
    Run the deprecation validation check.

    Args:
        baseline_path: Path to the baseline file
        changed_files_only: Only check changed files
        verbose: Enable verbose output

    Returns:
        Exit code (0=pass, 1=fail, 2=error)
    """
    # Determine baseline path
    if baseline_path is None:
        baseline_path = os.environ.get(
            "DEPRECATION_BASELINE_PATH",
            os.environ.get("BASELINE_PATH", DEFAULT_BASELINE_PATH),
        )

    # Check if validation script exists
    if not VALIDATION_SCRIPT.exists():
        print(
            f"ERROR: Validation script not found: {VALIDATION_SCRIPT}",
            file=sys.stderr,
        )
        return 2

    # Build command
    cmd = [
        sys.executable,
        str(VALIDATION_SCRIPT),
        "--check",
        "--baseline-path",
        baseline_path,
    ]

    if changed_files_only:
        cmd.append("--changed-files-only")

    if verbose:
        cmd.append("--verbose")

    # Run validation
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except subprocess.SubprocessError as e:
        print(f"ERROR: Failed to run deprecation check: {e}", file=sys.stderr)
        return 2


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CI runner for deprecation validation gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  DEPRECATION_BASELINE_PATH  Path to deprecation baseline file
  BASELINE_PATH              Fallback path to baseline file
  CI                         Set to 'true' when running in CI environment

Examples:
  # Run full check
  python scripts/ci/deprecation_gate_runner.py

  # Run check on changed files only
  python scripts/ci/deprecation_gate_runner.py --changed-files-only

  # Run with specific baseline
  python scripts/ci/deprecation_gate_runner.py --baseline-path path/to/baseline.json
""",
    )

    parser.add_argument(
        "--baseline-path",
        type=str,
        default=None,
        help=f"Path to baseline file (default: {DEFAULT_BASELINE_PATH})",
    )
    parser.add_argument(
        "--changed-files-only",
        action="store_true",
        help="Only check files changed in this PR/commit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if not args.changed_files_only and os.environ.get("CI", "").lower() == "true":
        # Keep CI runtime bounded by default. The validator now resolves changed
        # files defensively, so changed-files mode is safe in Woodpecker.
        args.changed_files_only = True

    # Run the check
    exit_code = run_deprecation_check(
        baseline_path=args.baseline_path,
        changed_files_only=args.changed_files_only,
        verbose=args.verbose,
    )

    # Print summary for CI
    if exit_code == 0:
        print("\n✓ Deprecation gate: PASSED - No new deprecation warnings")
    elif exit_code == 1:
        print("\n✗ Deprecation gate: FAILED - New deprecation warnings detected")
        print("  To update the baseline, run:")
        print(f"  python {VALIDATION_SCRIPT} --update-baseline")
    else:
        print("\n✗ Deprecation gate: ERROR - Check execution failed")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
