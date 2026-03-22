#!/usr/bin/env python3
"""
Truth Gate Runner - CI wrapper for truth gate validation.

This script runs truth gate validation in CI environment:
1. Auto-detects story ID from CI environment
2. Gets commit SHA from CI
3. Runs truth_gate_check.py with all three checks
4. Writes status file for ci-gate.py

Usage:
    truth_gate_runner.py [--story-id <id>] [--output <file>]

Environment:
    CI_STATUS_DIR: Directory for status files
    CI_COMMIT_SHA: Current commit SHA
    CI_COMMIT_BRANCH: Current branch name
    CI_COMMIT_MESSAGE: Commit message (for story ID extraction)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def get_story_id_from_env() -> str | None:
    """Extract story ID from CI environment variables."""
    # Try to use the extract_story_id_from_pr.py script
    extract_script = Path("scripts/validation/extract_story_id_from_pr.py")
    if extract_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(extract_script), "--from-env"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    # Fallback: manual extraction
    import re

    story_patterns = [
        r"(GOV-\d+[A-Z]?)",
        r"(STRONG-\d+[A-Z]?)",
        r"(TG-\d+[A-Z]?)",
        r"(ST-\d+[A-Z]?)",
        r"(CH-\d+[A-Z]?)",
        r"(FT-\d+[A-Z]?)",
    ]

    # Check commit message
    commit_msg = os.environ.get("CI_COMMIT_MESSAGE", "")
    for pattern in story_patterns:
        match = re.search(pattern, commit_msg, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    # Check branch name
    branch = os.environ.get("CI_COMMIT_BRANCH", "")
    for pattern in story_patterns:
        match = re.search(pattern, branch, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def is_strong_system_story(story_id: str) -> bool:
    """Check if story ID is a strong-system story requiring truth gate."""
    import re

    strong_patterns = [
        r"^STRONG-",
        r"^TG-",
        r"^ST-",
        r"^GOV-",
    ]

    for pattern in strong_patterns:
        if re.search(pattern, story_id, re.IGNORECASE):
            return True
    return False


def run_truth_gate_check(
    story_id: str, output_file: Path | None = None
) -> dict[str, Any]:
    """Run truth gate check for the story."""
    truth_gate_script = Path("scripts/validation/truth_gate.py")

    if not truth_gate_script.exists():
        return {
            "passed": False,
            "error": f"truth_gate.py not found at {truth_gate_script}",
            "checks": [],
        }

    cmd = [
        sys.executable,
        str(truth_gate_script),
        "--check",
        "all",
        "--story-id",
        story_id,
        "--output",
        "json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse JSON output
        try:
            check_result = json.loads(result.stdout)
        except json.JSONDecodeError:
            check_result = {
                "passed": False,
                "error": f"Failed to parse truth gate output: {result.stdout}",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        return check_result

    except Exception as e:
        return {
            "passed": False,
            "error": f"Failed to run truth gate: {e}",
        }


def format_error_message(result: dict[str, Any]) -> str:
    """Format error message with remediation steps."""
    lines = []
    lines.append("=" * 70)
    lines.append("TRUTH GATE VALIDATION FAILED")
    lines.append("=" * 70)
    lines.append("")

    if "error" in result:
        lines.append(f"Error: {result['error']}")
        lines.append("")

    if "checks" in result:
        for check in result["checks"]:
            if not check.get("passed", True):
                lines.append(
                    f"✗ {check.get('check_type', 'unknown')}: {check.get('message', 'Failed')}"
                )

                if "details" in check and check["details"]:
                    for detail in check["details"]:
                        if not detail.get("passed", True):
                            lines.append(f"    - {detail.get('message', '')}")

    lines.append("")
    lines.append("-" * 70)
    lines.append("REMEDIATION STEPS:")
    lines.append("-" * 70)
    lines.append("")
    lines.append("1. Verify workflow status file entry:")
    lines.append("   - Check docs/bmm-workflow-status.yaml has correct story entry")
    lines.append("   - Ensure files_changed matches actual changed files")
    lines.append("")
    lines.append("2. Verify test counts:")
    lines.append("   - Run: pytest --collect-only tests/")
    lines.append("   - Update tests_added in workflow status file")
    lines.append("")
    lines.append("3. Verify merge truth:")
    lines.append("   - Ensure commits are on both local main and origin/main")
    lines.append("   - Run: git branch --contains <commit>")
    lines.append("")
    lines.append("4. For detailed output, run locally:")
    lines.append(
        " python scripts/validation/truth_gate.py --check all --story-id <story-id>"
    )
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def write_status_file(ci_status_dir: Path, status: int, result: dict[str, Any]) -> None:
    """Write status file for ci-gate.py."""
    status_file = ci_status_dir / "truth-gate.status"
    status_file.write_text(str(status))

    # Also write detailed JSON result
    json_file = ci_status_dir / "truth-gate.json"
    json_file.write_text(json.dumps(result, indent=2))


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Truth Gate Runner - CI wrapper for truth gate validation",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        help="Story ID to validate (auto-detected if not provided)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for JSON results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Get CI status directory
    ci_status_dir = Path(os.environ.get("CI_STATUS_DIR", "_bmad-output/ci"))
    ci_status_dir.mkdir(parents=True, exist_ok=True)

    # Get story ID
    story_id = args.story_id or get_story_id_from_env()

    if not story_id:
        result = {
            "passed": True,
            "skipped": True,
            "reason": "No story ID found in CI environment",
            "checks": [],
        }
        print("truth-gate-runner: No story ID found, skipping validation")
        write_status_file(ci_status_dir, 0, result)

        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2))

        return 0

    print(f"truth-gate-runner: Validating story {story_id}")

    # Check if this is a strong-system story
    if not is_strong_system_story(story_id):
        result = {
            "passed": True,
            "skipped": True,
            "reason": f"Story {story_id} is not a strong-system story",
            "story_id": story_id,
            "checks": [],
        }
        print(f"truth-gate-runner: {story_id} is not a strong-system story, skipping")
        write_status_file(ci_status_dir, 0, result)

        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2))

        return 0

    # Run truth gate validation
    print(f"truth-gate-runner: Running truth gate validation for {story_id}")
    result = run_truth_gate_check(story_id)

    # Determine exit status
    passed = result.get("passed", False)
    status = 0 if passed else 1

    # Write status files
    write_status_file(ci_status_dir, status, result)

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))

    # Output results
    if passed:
        print(f"truth-gate-runner: Validation PASSED for {story_id}")
        if args.verbose:
            print(json.dumps(result, indent=2))
        return 0
    else:
        print(f"truth-gate-runner: Validation FAILED for {story_id}")
        print(format_error_message(result))
        return 1


if __name__ == "__main__":
    sys.exit(main())
