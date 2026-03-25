#!/usr/bin/env python3
"""
Completion Evidence Validation Guardrail

Prevents stories from being marked as "completed" or "merged" without proper
PR/merge evidence. This guardrail was created in response to incident
GOV-BATCH-003-STATUS-FALSIFICATION.

Required evidence fields for completion:
  - pr_number: The GitHub PR number that was merged
  - merge_commit: The SHA of the merge commit
  - Verification via `git branch --contains` that commit is on main

Usage:
    python scripts/validate_completion_evidence.py
    python scripts/validate_completion_evidence.py --status-file docs/bmm-workflow-status.yaml
    python scripts/validate_completion_evidence.py --story-id ST-EXAMPLE-001
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class EvidenceValidationError(Exception):
    """Raised when completion evidence validation fails."""

    pass


def get_story_completion_age(story: dict[str, Any]) -> int | None:
    """
    Calculate the age of a story in days since completion.

    Looks for completion date in these fields (in order of preference):
    - completion_date (YYYY-MM-DD format)
    - completed_date (YYYY-MM-DD format)
    - merged_date (YYYY-MM-DD format)

    Args:
        story: Story dictionary

    Returns:
        Number of days since completion, or None if no completion date found
    """
    today = datetime.now().date()

    for date_field in ["completion_date", "completed_date", "merged_date"]:
        date_str = story.get(date_field)
        if date_str:
            try:
                completion_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
                return (today - completion_date).days
            except ValueError:
                continue
    return None


def run_git_command(args: list[str], cwd: Path = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args, capture_output=True, text=True, cwd=cwd or Path.cwd()
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def validate_completion_evidence(
    story: dict[str, Any], story_id: str = None, grace_period_days: int = 7
) -> tuple[bool, str, bool]:
    """
    Validate that a story marked as completed/merged has proper evidence.

    Args:
        story: Story dictionary from bmm-workflow-status.yaml
        story_id: Story ID (for error messages)
        grace_period_days: Stories older than this are warned but not blocked

    Returns:
        Tuple of (is_valid, error_message, is_legacy_warning)
        - is_valid: True if evidence is valid
        - error_message: Description of validation result
        - is_legacy_warning: True if this is a legacy story that only warrants warning
    """
    story_id = story_id or story.get("id", "UNKNOWN")
    status = story.get("status", "")

    # Only validate stories marked as completed or merged
    if status not in ["completed", "merged"]:
        return True, "Valid (not marked as completed/merged)", False

    # Check if story is legacy (outside grace period)
    story_age = get_story_completion_age(story)
    is_legacy = story_age is not None and story_age > grace_period_days

    errors = []

    # Must have PR number
    pr_number = story.get("pr_number")
    if not pr_number:
        errors.append("Missing required field: pr_number")

    # Must have merge commit
    merge_commit = story.get("merge_commit")
    if not merge_commit:
        errors.append("Missing required field: merge_commit")

    # If we have merge commit, verify it's on main branch
    if merge_commit:
        returncode, stdout, stderr = run_git_command(
            ["branch", "--contains", merge_commit]
        )

        if returncode != 0:
            errors.append(f"Failed to verify merge_commit {merge_commit}: {stderr}")
        elif "main" not in stdout and "master" not in stdout:
            errors.append(
                f"Commit {merge_commit} not found on main/master branch. "
                f"Branches containing commit: {stdout.strip() or '(none)'}"
            )

    # Check for merge_commits list (alternative field)
    if not merge_commit and "merge_commits" in story:
        merge_commits = story.get("merge_commits", [])
        if merge_commits:
            # Verify at least one merge commit is on main
            found_on_main = False
            for commit in merge_commits:
                returncode, stdout, stderr = run_git_command(
                    ["branch", "--contains", commit]
                )
                if returncode == 0 and ("main" in stdout or "master" in stdout):
                    found_on_main = True
                    break

            if not found_on_main:
                errors.append(
                    f"None of the merge_commits {merge_commits} found on main/master branch"
                )

    # Check for remediation_pr_numbers (alternative field for multi-PR stories)
    if not pr_number and "remediation_pr_numbers" in story:
        remediation_prs = story.get("remediation_pr_numbers", [])
        if not remediation_prs:
            errors.append("Has remediation_pr_numbers field but list is empty")

    if errors:
        return False, "; ".join(errors), is_legacy

    return True, "Valid completion evidence", False


def validate_status_file(
    status_file: Path, grace_period_days: int = 7
) -> dict[str, Any]:
    """
    Validate all stories in the workflow status file.

    Args:
        status_file: Path to bmm-workflow-status.yaml
        grace_period_days: Stories older than this are warned but not blocked

    Returns:
        Dictionary with validation results
    """
    if not status_file.exists():
        raise EvidenceValidationError(f"Status file not found: {status_file}")

    with open(status_file) as f:
        data = yaml.safe_load(f)

    results = {
        "valid": [],
        "invalid": [],
        "warnings": [],  # Legacy stories missing evidence (outside grace period)
        "skipped": [],
        "total_stories": 0,
        "completed_merged_stories": 0,
    }

    # Sections to check
    sections = ["completed", "backlog", "launch_stories"]

    for section in sections:
        if section not in data:
            continue

        stories = data[section]
        if not isinstance(stories, list):
            continue

        for story in stories:
            if not isinstance(story, dict):
                continue

            results["total_stories"] += 1
            story_id = story.get("id", "UNKNOWN")
            status = story.get("status", "")

            # Only validate completed/merged stories
            if status not in ["completed", "merged"]:
                results["skipped"].append(
                    {
                        "id": story_id,
                        "status": status,
                        "reason": f"Status '{status}' does not require completion evidence",
                    }
                )
                continue

            results["completed_merged_stories"] += 1

            is_valid, message, is_legacy_warning = validate_completion_evidence(
                story, story_id, grace_period_days
            )

            if is_valid:
                results["valid"].append(
                    {"id": story_id, "status": status, "message": message}
                )
            elif is_legacy_warning:
                # Legacy story - add to warnings, not blocking errors
                results["warnings"].append(
                    {"id": story_id, "status": status, "warning": message}
                )
            else:
                # Within grace period - blocking error
                results["invalid"].append(
                    {"id": story_id, "status": status, "error": message}
                )

    return results


def print_validation_report(results: dict[str, Any], verbose: bool = False):
    """Print a formatted validation report."""
    print("\n" + "=" * 80)
    print("COMPLETION EVIDENCE VALIDATION REPORT")
    print("=" * 80)
    print(f"\nTotal stories analyzed: {results['total_stories']}")
    print(f"Stories marked completed/merged: {results['completed_merged_stories']}")
    print(f"Valid completion evidence: {len(results['valid'])}")
    print(f"Invalid completion evidence: {len(results['invalid'])}")
    print(f"Legacy warnings (outside grace period): {len(results['warnings'])}")
    print(f"Skipped (not completed/merged): {len(results['skipped'])}")

    if results["invalid"]:
        print("\n" + "-" * 80)
        print("❌ INVALID COMPLETIONS (BLOCKING)")
        print("-" * 80)
        for invalid in results["invalid"]:
            print(f"\n  Story ID: {invalid['id']}")
            print(f"  Status: {invalid['status']}")
            print(f"  Error: {invalid['error']}")

    if results["warnings"]:
        print("\n" + "-" * 80)
        print("⚠️  LEGACY WARNINGS (non-blocking - outside grace period)")
        print("-" * 80)
        for warning in results["warnings"]:
            print(f"\n  Story ID: {warning['id']}")
            print(f"  Status: {warning['status']}")
            print(f"  Warning: {warning['warning']}")

    if verbose and results["valid"]:
        print("\n" + "-" * 80)
        print("✅ VALID COMPLETIONS")
        print("-" * 80)
        for valid in results["valid"]:
            print(f"  {valid['id']}: {valid['message']}")

    print("\n" + "=" * 80)
    if results["invalid"]:
        print(
            "❌ VALIDATION FAILED: Stories marked as completed without proper evidence"
        )
        print("=" * 80)
        return False
    else:
        if results["warnings"]:
            print("✅ VALIDATION PASSED (with legacy warnings)")
        else:
            print("✅ VALIDATION PASSED: All completed stories have proper evidence")
        print("=" * 80)
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Validate completion evidence for stories in workflow status"
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=Path("docs/bmm-workflow-status.yaml"),
        help="Path to bmm-workflow-status.yaml",
    )
    parser.add_argument(
        "--story-id", type=str, help="Validate a specific story ID only"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show valid completions as well as invalid",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--legacy-grace-period-days",
        type=int,
        default=7,
        help="Stories older than this many days are warned but not blocked (default: 7)",
    )

    args = parser.parse_args()

    try:
        # Validate specific story if requested
        if args.story_id:
            with open(args.status_file) as f:
                data = yaml.safe_load(f)

            story = None
            for section in ["completed", "backlog", "launch_stories"]:
                if section in data:
                    for s in data[section]:
                        if s.get("id") == args.story_id:
                            story = s
                            break
                if story:
                    break

            if not story:
                print(f"Error: Story {args.story_id} not found", file=sys.stderr)
                sys.exit(1)

            is_valid, message, is_legacy = validate_completion_evidence(
                story, args.story_id, args.legacy_grace_period_days
            )

            if args.json:
                import json

                print(
                    json.dumps(
                        {
                            "story_id": args.story_id,
                            "valid": is_valid,
                            "message": message,
                            "is_legacy_warning": is_legacy,
                        },
                        indent=2,
                    )
                )
            else:
                if is_valid:
                    print(f"✅ {args.story_id}: {message}")
                elif is_legacy:
                    print(f"⚠️ {args.story_id}: {message} (legacy, non-blocking)")
                else:
                    print(f"❌ {args.story_id}: {message}", file=sys.stderr)

            # Exit 0 for valid, 0 for legacy warnings, 1 for blocking errors
            sys.exit(0 if (is_valid or is_legacy) else 1)

        # Validate entire status file
        results = validate_status_file(args.status_file, args.legacy_grace_period_days)

        if args.json:
            import json

            print(json.dumps(results, indent=2))
            success = len(results["invalid"]) == 0
        else:
            success = print_validation_report(results, verbose=args.verbose)

        sys.exit(0 if success else 1)

    except EvidenceValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
