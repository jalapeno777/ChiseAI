#!/usr/bin/env python3
"""
Truth Gate Check - Core validation logic for ChiseAI merge truth enforcement.

Validates:
1. Commit exists in repository
2. Commit is on specified branch (git branch --contains)
3. Story ID format is valid (ST-*, CH-*, FT-*, REWARD-*, REPO-*, SAFETY-*, BRANCH-*, PAPER-*, RECON-*, TG-*, GOV-*)
4. PR title contains story ID (when --pr provided)

Usage:
    truth_gate_check.py --commit <sha> --story-id <id>
    truth_gate_check.py --commit <sha> --story-id <id> --branch main
    truth_gate_check.py --commit <sha> --story-id <id> --pr "feat: Add feature (ST-001)"
    truth_gate_check.py --commit <sha> --story-id <id> --branch main --verbose

Exit Codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Invalid arguments or git error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

# Story ID patterns (must include a digit)
# Based on AGENTS.md PR title requirements
STORY_ID_PATTERNS = [
    r"(ST-\d+)",  # ST-* (Story)
    r"(CH-\d+)",  # CH-* (Chore)
    r"(FT-\d+)",  # FT-* (Feature)
    r"(REWARD-\d+)",  # REWARD-* (Reward system)
    r"(REPO-\d+)",  # REPO-* (Repository work)
    r"(SAFETY-\d+)",  # SAFETY-* (Safety-critical)
    r"(BRANCH-\d+)",  # BRANCH-* (Branch management)
    r"(PAPER-\d+)",  # PAPER-* (Paper trading)
    r"(RECON-\d+)",  # RECON-* (Reconnaissance)
    r"(TG-\d+)",  # TG-* (Truth gate)
    r"(GOV-\d+)",  # GOV-* (Governance)
    r"(STRONG-\d+)",  # STRONG-* (Strong system)
]

# Compile combined regex for story ID search (non-anchored, for finding in text)
STORY_ID_REGEX = re.compile(
    "|".join(STORY_ID_PATTERNS),
    re.IGNORECASE,
)

# Compile anchored regex for strict validation (story ID must be at start)
# Keep the capturing groups so we can extract the matched ID
STORY_ID_ANCHORED_REGEX = re.compile(
    "^(?:" + "|".join(STORY_ID_PATTERNS) + ")",
    re.IGNORECASE,
)


def validate_story_id(story_id: str) -> dict[str, Any]:
    """
    Validate story ID format.

    Args:
        story_id: Story ID to validate

    Returns:
        Dictionary with validation result
    """
    if not story_id:
        return {
            "passed": False,
            "check": "story-id-format",
            "message": "Story ID is empty",
            "story_id": story_id,
        }

    # For story ID validation, use anchored regex (story ID must be at start)
    match = STORY_ID_ANCHORED_REGEX.match(story_id)
    if match:
        # Find the first non-None group (the matched story ID)
        matched_id = None
        for group in match.groups():
            if group is not None:
                matched_id = group
                break

        if matched_id:
            return {
                "passed": True,
                "check": "story-id-format",
                "message": f"Story ID '{story_id}' matches valid pattern",
                "story_id": matched_id.upper(),
                "pattern": matched_id.split("-")[0],
            }

    # If we get here, no valid story ID was found (either no match or no group)
    return {
        "passed": False,
        "check": "story-id-format",
        "message": (
            f"Story ID '{story_id}' does not match valid pattern. "
            f"Valid patterns: ST-*, CH-*, FT-*, REWARD-*, REPO-*, "
            f"SAFETY-*, BRANCH-*, PAPER-*, RECON-*, TG-*, GOV-*, STRONG-*"
        ),
        "story_id": story_id,
    }


def verify_commit_exists(commit: str, repo_root: Path | None = None) -> dict[str, Any]:
    """
    Verify a commit exists in the repository.

    Args:
        commit: Commit SHA to verify
        repo_root: Root of the git repository

    Returns:
        Dictionary with verification result
    """
    if repo_root is None:
        repo_root = Path.cwd()

    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", commit],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )

        if result.returncode == 0 and result.stdout.strip() == "commit":
            return {
                "passed": True,
                "check": "commit-exists",
                "message": f"Commit {commit[:8]} exists in repository",
                "commit": commit,
            }
        else:
            return {
                "passed": False,
                "check": "commit-exists",
                "message": f"Commit {commit[:8]} does not exist in repository",
                "commit": commit,
                "error": (
                    result.stderr.strip() if result.stderr else "Not a valid commit"
                ),
            }

    except Exception as e:
        return {
            "passed": False,
            "check": "commit-exists",
            "message": f"Error verifying commit {commit[:8]}: {e}",
            "commit": commit,
            "error": str(e),
        }


def verify_commit_on_branch(
    commit: str,
    branch: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Verify a commit is on a specific branch using git branch --contains.

    Args:
        commit: Commit SHA to verify
        branch: Branch name to check
        repo_root: Root of the git repository

    Returns:
        Dictionary with verification result
    """
    if repo_root is None:
        repo_root = Path.cwd()

    try:
        # Run git branch --contains <commit>
        result = subprocess.run(
            ["git", "branch", "--contains", commit],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )

        if result.returncode != 0:
            return {
                "passed": False,
                "check": "commit-on-branch",
                "message": f"Failed to check branches containing {commit[:8]}",
                "commit": commit,
                "branch": branch,
                "error": result.stderr.strip() if result.stderr else "Unknown error",
            }

        # Parse branch list
        branches = [
            b.strip().strip("* ")  # Remove leading * and spaces (current branch marker)
            for b in result.stdout.strip().split("\n")
            if b.strip()
        ]

        # Check if target branch is in the list
        if branch in branches:
            return {
                "passed": True,
                "check": "commit-on-branch",
                "message": f"Commit {commit[:8]} is on branch '{branch}'",
                "commit": commit,
                "branch": branch,
                "branches_found": branches,
            }
        else:
            return {
                "passed": False,
                "check": "commit-on-branch",
                "message": f"Commit {commit[:8]} is NOT on branch '{branch}'",
                "commit": commit,
                "branch": branch,
                "branches_found": branches,
            }

    except Exception as e:
        return {
            "passed": False,
            "check": "commit-on-branch",
            "message": f"Error checking commit {commit[:8]} on branch '{branch}': {e}",
            "commit": commit,
            "branch": branch,
            "error": str(e),
        }


def verify_pr_title_contains_story_id(pr_title: str, story_id: str) -> dict[str, Any]:
    """
    Verify PR title contains the story ID.

    Args:
        pr_title: PR title to check
        story_id: Expected story ID

    Returns:
        Dictionary with verification result
    """
    if not pr_title:
        return {
            "passed": False,
            "check": "pr-title",
            "message": "PR title is empty",
            "pr_title": pr_title,
            "story_id": story_id,
        }

    # Search for story ID pattern in PR title
    match = STORY_ID_REGEX.search(pr_title)

    if match:
        # Find the first non-None group (the matched story ID)
        found_id = None
        for group in match.groups():
            if group is not None:
                found_id = group.upper()
                break

        if found_id:
            expected_id = story_id.upper()

            if found_id == expected_id:
                return {
                    "passed": True,
                    "check": "pr-title",
                    "message": f"PR title contains story ID '{story_id}'",
                    "pr_title": pr_title,
                    "story_id": story_id,
                    "found_id": found_id,
                }
            else:
                return {
                    "passed": False,
                    "check": "pr-title",
                    "message": f"PR title contains different story ID '{found_id}' (expected '{story_id}')",
                    "pr_title": pr_title,
                    "story_id": story_id,
                    "found_id": found_id,
                }

    # If we get here, no valid story ID was found in the PR title
    return {
        "passed": False,
        "check": "pr-title",
        "message": f"PR title does not contain a valid story ID (expected '{story_id}')",
        "pr_title": pr_title,
        "story_id": story_id,
    }


def run_truth_gate_checks(
    commit: str | None,
    story_id: str | None,
    branch: str | None,
    pr_title: str | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Run all truth gate checks.

    Args:
        commit: Commit SHA to verify
        story_id: Story ID to validate
        branch: Branch to check commit is on
        pr_title: PR title to verify contains story ID
        repo_root: Root of the git repository

    Returns:
        Dictionary with all check results
    """
    if repo_root is None:
        repo_root = Path.cwd()

    result: dict[str, Any] = {
        "passed": True,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checks": [],
        "total_checks": 0,
        "passed_checks": 0,
        "failed_checks": 0,
    }

    if commit:
        result["commit"] = commit
    if story_id:
        result["story_id"] = story_id
    if branch:
        result["branch"] = branch
    if pr_title:
        result["pr_title"] = pr_title

    # Check 1: Story ID format validation
    if story_id:
        story_result = validate_story_id(story_id)
        result["checks"].append(story_result)
        if not story_result["passed"]:
            result["passed"] = False

    # Check 2: Commit exists
    if commit:
        exists_result = verify_commit_exists(commit, repo_root)
        result["checks"].append(exists_result)
        if not exists_result["passed"]:
            result["passed"] = False

    # Check 3: Commit is on branch
    if commit and branch:
        branch_result = verify_commit_on_branch(commit, branch, repo_root)
        result["checks"].append(branch_result)
        if not branch_result["passed"]:
            result["passed"] = False

    # Check 4: PR title contains story ID
    if pr_title and story_id:
        pr_result = verify_pr_title_contains_story_id(pr_title, story_id)
        result["checks"].append(pr_result)
        if not pr_result["passed"]:
            result["passed"] = False

    # Calculate summary
    result["total_checks"] = len(result["checks"])
    result["passed_checks"] = sum(1 for c in result["checks"] if c.get("passed", False))
    result["failed_checks"] = result["total_checks"] - result["passed_checks"]

    return result


def format_output(result: dict[str, Any], verbose: bool = False) -> str:
    """
    Format check results for output.

    Args:
        result: Check results dictionary
        verbose: Whether to include verbose output

    Returns:
        Formatted output string
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"TRUTH GATE CHECK: {'PASS' if result['passed'] else 'FAIL'}")
    lines.append("=" * 60)

    if "commit" in result:
        lines.append(f"Commit: {result['commit'][:8] if result['commit'] else 'N/A'}")
    if "story_id" in result:
        lines.append(f"Story ID: {result['story_id']}")
    if "branch" in result:
        lines.append(f"Branch: {result['branch']}")
    if "pr_title" in result:
        lines.append(f"PR Title: {result['pr_title']}")

    lines.append("-" * 60)

    # Individual check results
    for check in result.get("checks", []):
        status = "✓" if check.get("passed", False) else "✗"
        check_name = check.get("check", "unknown")
        message = check.get("message", "")
        lines.append(f"{status} {check_name}: {message}")

        # Verbose output for failed checks
        if verbose and not check.get("passed", False):
            if "error" in check:
                lines.append(f"    Error: {check['error']}")
            if "branches_found" in check:
                lines.append(
                    f"    Branches found: {', '.join(check['branches_found'])}"
                )
            if "found_id" in check:
                lines.append(f"    Found ID: {check['found_id']}")

    lines.append("-" * 60)
    lines.append(
        f"Total: {result['total_checks']} | Passed: {result['passed_checks']} | Failed: {result['failed_checks']}"
    )
    lines.append("=" * 60)

    return "\n".join(lines)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Truth Gate Check - Core validation logic for ChiseAI merge truth enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --commit 5737a8ee --story-id TG-003
  %(prog)s --commit 5737a8ee --story-id TG-003 --branch main
  %(prog)s --commit 5737a8ee --story-id TG-003 --pr "feat: Add feature (TG-003)"
  %(prog)s --commit 5737a8ee --story-id TG-003 --branch main --verbose

Exit Codes:
  0 - All checks passed
  1 - One or more checks failed
  2 - Invalid arguments or git error
        """,
    )

    parser.add_argument(
        "--commit",
        type=str,
        help="Commit SHA to verify",
    )

    parser.add_argument(
        "--story-id",
        type=str,
        help="Story ID to validate (e.g., ST-001, TG-003, GOV-001-A)",
    )

    parser.add_argument(
        "--branch",
        type=str,
        help="Branch to verify commit is on (e.g., main, feature/ST-001)",
    )

    parser.add_argument(
        "--pr",
        type=str,
        metavar="PR_TITLE",
        help="PR title to verify contains story ID",
    )

    parser.add_argument(
        "--repo-root",
        type=str,
        default=".",
        help="Root of the git repository (default: current directory)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Validate arguments
    if not args.commit and not args.story_id:
        print(
            "Error: At least one of --commit or --story-id must be provided",
            file=sys.stderr,
        )
        return 2

    # Resolve repo root
    repo_root = Path(args.repo_root).resolve()

    # Check if we're in a git repository
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        # Try to find git root
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
            if result.returncode != 0:
                print(f"Error: Not a git repository: {repo_root}", file=sys.stderr)
                return 2
        except Exception as e:
            print(f"Error: Cannot access git repository: {e}", file=sys.stderr)
            return 2

    # Run checks
    result = run_truth_gate_checks(
        commit=args.commit,
        story_id=args.story_id,
        branch=args.branch,
        pr_title=args.pr,
        repo_root=repo_root,
    )

    # Output results
    if args.json:
        import json

        print(json.dumps(result, indent=2))
    else:
        print(format_output(result, verbose=args.verbose))

    # Return exit code
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
