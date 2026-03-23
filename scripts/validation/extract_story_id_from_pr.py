#!/usr/bin/env python3
"""
Extract Story ID from PR metadata.

Extracts story ID from PR title, branch name, or other CI environment variables.
Supports strong-system story patterns: STRONG-*, TG-*, ST-*

Usage:
    extract_story_id_from_pr.py --from-title "feat: Add new feature (STRONG-001)"
    extract_story_id_from_pr.py --from-branch "feature/STRONG-001-new-feature"
    extract_story_id_from_pr.py --from-env

Returns:
    - Story ID (e.g., "STRONG-001") on success (exit code 0)
    - Empty string if no story ID found (exit code 0)
    - Error message on error (exit code 1)
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# Strong-system story patterns
# These patterns match the BASE story ID only (without trailing descriptive suffixes)
STRONG_SYSTEM_PATTERNS = [
    r"(STRONG-\d+)",  # STRONG-001 (base only, -A, -A-S3 are validation suffixes)
    r"(TG-\d+)",  # TG-003
    r"(ST-(?!CI-)\d+)",  # ST-042 (exclude CI remediation branches like ST-CI-001)
]

# Extended patterns for matching IDs with validation suffixes (for --check-strong-system)
EXTENDED_PATTERNS = [
    r"(STRONG-\d+(?:-[A-Z]\d?(?:-S\d+)?)?)",  # STRONG-001, STRONG-001-A, STRONG-001-A-S3
    r"(TG-\d+)",  # TG-003
    r"(ST-(?!CI-)\d+(?:-[A-Z]+)?)",  # ST-001, ST-001-CI (exclude ST-CI-001)
]

# Compile regex patterns
STORY_ID_REGEX = re.compile(
    "(?:" + "|".join(STRONG_SYSTEM_PATTERNS) + ")",
    re.IGNORECASE,
)

# Extended regex for validation checks
EXTENDED_ID_REGEX = re.compile(
    "(?:" + "|".join(EXTENDED_PATTERNS) + ")",
    re.IGNORECASE,
)

# Pattern to check if a story is a strong-system story
STRONG_SYSTEM_REGEX = re.compile(
    r"^(STRONG-|TG-|ST-)",
    re.IGNORECASE,
)


def extract_from_text(text: str) -> str | None:
    """
    Extract story ID from arbitrary text.

    Args:
        text: Text to search for story ID

    Returns:
        Story ID if found, None otherwise
    """
    if not text:
        return None

    match = STORY_ID_REGEX.search(text)
    if match:
        # Return the first matching group that is not None
        for group in match.groups():
            if group:
                return group.upper()
    return None


def extract_from_pr_title(title: str) -> str | None:
    """
    Extract story ID from PR title.

    Args:
        title: PR title

    Returns:
        Story ID if found, None otherwise
    """
    return extract_from_text(title)


def extract_from_branch_name(branch: str) -> str | None:
    """
    Extract story ID from branch name.

    Args:
        branch: Branch name (e.g., "feature/STRONG-001-new-feature")

    Returns:
        Story ID if found, None otherwise
    """
    return extract_from_text(branch)


def is_strong_system_story(story_id: str | None) -> bool:
    """
    Check if a story ID is a strong-system story.

    Strong-system stories use patterns:
    - STRONG-*
    - TG-*
    - ST-*

    Args:
        story_id: Story ID to check

    Returns:
        True if strong-system story, False otherwise
    """
    if not story_id:
        return False
    return bool(STRONG_SYSTEM_REGEX.match(story_id))


def extract_from_ci_environment() -> str | None:
    """
    Extract story ID from CI environment variables.

    Checks common CI environment variables for PR/branch information.

    Returns:
        Story ID if found, None otherwise
    """
    # Check PR title from various CI systems
    pr_title_vars = [
        "CI_COMMIT_MESSAGE",  # Woodpecker/Gitea
        "WOODPECKER_COMMIT_MESSAGE",
        "CI_PR_TITLE",  # Generic
        "PR_TITLE",
        "GITHUB_EVENT_PULL_REQUEST_TITLE",  # GitHub
        "CI_MERGE_REQUEST_TITLE",  # GitLab
    ]

    for var in pr_title_vars:
        value = os.environ.get(var)
        if value:
            story_id = extract_from_pr_title(value)
            if story_id:
                return story_id

    # Check branch name from various CI systems
    branch_vars = [
        "CI_COMMIT_BRANCH",  # Woodpecker/Gitea
        "WOODPECKER_COMMIT_BRANCH",
        "CI_BRANCH",  # Generic
        "GITHUB_HEAD_REF",  # GitHub
        "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME",  # GitLab
        "CIRCLE_BRANCH",  # CircleCI
        "TRAVIS_BRANCH",  # Travis CI
    ]

    for var in branch_vars:
        value = os.environ.get(var)
        if value:
            story_id = extract_from_branch_name(value)
            if story_id:
                return story_id

    # Check PR body for story ID references
    pr_body_vars = [
        "CI_PR_BODY",
        "PR_BODY",
        "GITHUB_EVENT_PULL_REQUEST_BODY",
    ]

    for var in pr_body_vars:
        value = os.environ.get(var)
        if value:
            story_id = extract_from_text(value)
            if story_id:
                return story_id

    return None


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract story ID from PR metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --from-title "feat: Add feature (STRONG-001)"
  %(prog)s --from-branch "feature/TG-003-ci-gate"
  %(prog)s --from-env
  %(prog)s --check-strong-system "STRONG-001" && echo "Is strong-system"
        """,
    )

    parser.add_argument(
        "--from-title",
        type=str,
        metavar="TITLE",
        help="Extract story ID from PR title",
    )

    parser.add_argument(
        "--from-branch",
        type=str,
        metavar="BRANCH",
        help="Extract story ID from branch name",
    )

    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Extract story ID from CI environment variables",
    )

    parser.add_argument(
        "--check-strong-system",
        type=str,
        metavar="STORY_ID",
        help="Check if story ID is a strong-system story (exit 0 if yes, 1 if no)",
    )

    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle --check-strong-system
    if args.check_strong_system:
        if is_strong_system_story(args.check_strong_system):
            if args.output == "json":
                print(
                    f'{{"story_id": "{args.check_strong_system}", "is_strong_system": true}}'
                )
            else:
                print(args.check_strong_system)
            return 0
        else:
            if args.output == "json":
                print(
                    f'{{"story_id": "{args.check_strong_system}", "is_strong_system": false}}'
                )
            else:
                print("")
            return 1

    # Extract story ID based on source
    story_id: str | None = None

    if args.from_title:
        story_id = extract_from_pr_title(args.from_title)
    elif args.from_branch:
        story_id = extract_from_branch_name(args.from_branch)
    elif args.from_env:
        story_id = extract_from_ci_environment()
    else:
        # Default to environment extraction
        story_id = extract_from_ci_environment()

    # Output result
    if args.output == "json":
        import json

        result = {
            "story_id": story_id,
            "is_strong_system": is_strong_system_story(story_id),
        }
        print(json.dumps(result))
    else:
        # Text output: just the story ID or empty string
        print(story_id if story_id else "")

    return 0


if __name__ == "__main__":
    sys.exit(main())
