#!/usr/bin/env python3
"""
Evidence Gate Runner for CI Pipeline.

This script runs evidence validation in CI context, supporting PR-scoped
checking to ensure stories have required evidence files before merge.

It integrates with the Woodpecker CI environment to:
1. Extract story ID from PR title or branch name
2. Check if the story requires evidence validation
3. Run validation against docs/evidence/ directory

Exit codes:
    0 - All stories have evidence (or no stories to check)
    1 - One or more stories lack evidence files
    2 - Configuration or execution errors

Usage:
    # Run in CI environment (auto-detects story from PR/branch)
    python3 evidence_gate_runner.py

    # Validate specific story
    python3 evidence_gate_runner.py --story-id ST-XXX

    # Validate all stories (full gate mode)
    python3 evidence_gate_runner.py --all
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Configuration
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")
EVIDENCE_DIR = Path("docs/evidence")
VALIDATION_SCRIPT = Path("scripts/validation/validate_story_evidence.py")


def run_command(cmd: list[str], capture_output: bool = True) -> tuple[int, str, str]:
    """
    Run a command and return exit code, stdout, stderr.

    Args:
        cmd: Command and arguments as list
        capture_output: Whether to capture stdout/stderr

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=False,
        )
        stdout = result.stdout if result.stdout else ""
        stderr = result.stderr if result.stderr else ""
        return result.returncode, stdout, stderr
    except FileNotFoundError as e:
        return 127, "", f"Command not found: {e}"
    except Exception as e:
        return 1, "", f"Error executing command: {e}"


def extract_story_id_from_ci() -> str | None:
    """
    Extract story ID from CI environment variables.

    Uses the extract_story_id_from_pr.py script for consistent extraction.

    Returns:
        Story ID if found, None otherwise
    """
    result = run_command(
        [
            "python3",
            str(VALIDATION_SCRIPT.parent / "extract_story_id_from_pr.py"),
            "--from-env",
        ]
    )
    if result[0] == 0 and result[1].strip():
        return result[1].strip()
    return None


def check_validation_script_exists() -> bool:
    """Check if the validation script exists."""
    return VALIDATION_SCRIPT.exists()


def run_evidence_validation(
    story_id: str | None = None,
    all_stories: bool = False,
    verbose: bool = False,
) -> int:
    """
    Run evidence validation using the validate_story_evidence.py script.

    Args:
        story_id: Specific story ID to validate, or None to auto-detect
        all_stories: Whether to validate all stories
        verbose: Whether to show detailed output

    Returns:
        Exit code from validation (0 = success, 1 = validation failed, 2 = error)
    """
    if not check_validation_script_exists():
        print(
            f"ERROR: Validation script not found: {VALIDATION_SCRIPT}", file=sys.stderr
        )
        return 2

    # Build command
    cmd = ["python3", str(VALIDATION_SCRIPT)]

    if all_stories:
        cmd.append("--all")
    elif story_id:
        cmd.extend(["--story-id", story_id])
    else:
        # Auto-detect from CI environment
        detected_story = extract_story_id_from_ci()
        if detected_story:
            cmd.extend(["--story-id", detected_story])
            print(
                f"Evidence gate: Detected story ID '{detected_story}' from CI environment"
            )
        else:
            print("Evidence gate: No story ID detected from CI environment")
            print("Evidence gate: Skipping evidence validation (not a story PR)")
            return 0

    if verbose:
        cmd.append("--verbose")

    # Run validation
    print(f"Evidence gate: Running validation...")
    print(f"Evidence gate: Command: {' '.join(cmd)}")

    exit_code, stdout, stderr = run_command(cmd, capture_output=False)

    return exit_code


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Evidence Gate Runner for CI Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in CI environment (auto-detects story from PR/branch)
  python3 %(prog)s
  
  # Validate specific story
  python3 %(prog)s --story-id ST-XXX
  
  # Validate all stories (full gate mode)
  python3 %(prog)s --all
        """,
    )

    parser.add_argument(
        "--story-id",
        type=str,
        help="Validate evidence for a specific story ID",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate evidence for all stories (full gate mode)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        default=True,
        help="Require evidence files (exit with error if missing)",
    )

    args = parser.parse_args()

    # Check if we're in CI environment
    ci_env_vars = [
        "CI",
        "CI_COMMIT_BRANCH",
        "WOODPECKER",
        "WOODPECKER_COMMIT_BRANCH",
        "GITHUB_ACTIONS",
    ]
    in_ci = any(os.environ.get(var) for var in ci_env_vars)

    if in_ci and args.verbose:
        print("Evidence gate: Running in CI environment")

    # Validate paths exist
    if not WORKFLOW_STATUS_FILE.exists():
        print(
            f"ERROR: Workflow status file not found: {WORKFLOW_STATUS_FILE}",
            file=sys.stderr,
        )
        return 2

    # Create evidence directory if it doesn't exist
    if not EVIDENCE_DIR.exists():
        print(f"WARNING: Evidence directory not found: {EVIDENCE_DIR}", file=sys.stderr)
        print("WARNING: Creating evidence directory...", file=sys.stderr)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    # Run validation
    exit_code = run_evidence_validation(
        story_id=args.story_id,
        all_stories=args.all,
        verbose=args.verbose,
    )

    if exit_code == 0:
        print("\n✅ Evidence gate: PASSED")
    elif exit_code == 1:
        print("\n❌ Evidence gate: FAILED - Missing evidence files", file=sys.stderr)
        print("\nExpected evidence file pattern:", file=sys.stderr)
        print("  docs/evidence/{STORY-ID}-*.{json,md}", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print("  docs/evidence/TECH-002-B-evidence-ci.json", file=sys.stderr)
    else:
        print(f"\n❌ Evidence gate: ERROR (exit code {exit_code})", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
