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
from pathlib import Path
from typing import Any

import yaml


class EvidenceValidationError(Exception):
    """Raised when completion evidence validation fails."""

    pass


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
    story: dict[str, Any], story_id: str = None
) -> tuple[bool, str]:
    """
    Validate that a story marked as completed/merged has proper evidence.

    Args:
        story: Story dictionary from bmm-workflow-status.yaml
        story_id: Story ID (for error messages)

    Returns:
        Tuple of (is_valid, error_message)
    """
    story_id = story_id or story.get("id", "UNKNOWN")
    status = story.get("status", "")

    # Only validate stories marked as completed or merged
    if status not in ["completed", "merged"]:
        return True, "Valid (not marked as completed/merged)"

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
        return False, "; ".join(errors)

    return True, "Valid completion evidence"


def validate_status_file(status_file: Path) -> dict[str, Any]:
    """
    Validate all stories in the workflow status file.

    Args:
        status_file: Path to bmm-workflow-status.yaml

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

            is_valid, message = validate_completion_evidence(story, story_id)

            if is_valid:
                results["valid"].append(
                    {"id": story_id, "status": status, "message": message}
                )
            else:
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
    print(f"Skipped (not completed/merged): {len(results['skipped'])}")

    if results["invalid"]:
        print("\n" + "-" * 80)
        print("❌ INVALID COMPLETIONS (BLOCKING)")
        print("-" * 80)
        for invalid in results["invalid"]:
            print(f"\n  Story ID: {invalid['id']}")
            print(f"  Status: {invalid['status']}")
            print(f"  Error: {invalid['error']}")

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

            is_valid, message = validate_completion_evidence(story, args.story_id)

            if args.json:
                import json

                print(
                    json.dumps(
                        {
                            "story_id": args.story_id,
                            "valid": is_valid,
                            "message": message,
                        },
                        indent=2,
                    )
                )
            else:
                if is_valid:
                    print(f"✅ {args.story_id}: {message}")
                else:
                    print(f"❌ {args.story_id}: {message}", file=sys.stderr)

            sys.exit(0 if is_valid else 1)

        # Validate entire status file
        results = validate_status_file(args.status_file)

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
