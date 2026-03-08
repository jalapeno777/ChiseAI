#!/usr/bin/env python3
"""
Validate that completed/merged stories have PR/merge evidence.

This script validates that any story with status="completed" or status="merged"
has at least one of the required evidence fields:
  - pr_number (must exist and be non-empty)
  - merge_commit or commit_sha (must exist and be non-empty)

This prevents status falsification as described in GOV-BATCH-003-STATUS-FALSIFICATION,
where 90 stories were marked as "completed" without any merge evidence.

Exit codes:
    0 - All validations passed
    1 - Evidence validation errors found
    2 - YAML parsing or file errors
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Configuration
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")

# Statuses that require evidence
REQUIRES_EVIDENCE = {"completed", "merged"}

# Evidence field combinations that satisfy the requirement
VALID_EVIDENCE_COMBINATIONS = [
    # Has PR number
    lambda story: bool(
        story.get("pr_number") and str(story.get("pr_number", "")).strip()
    ),
    # Has merge_commit (or merge_commits list)
    lambda story: bool(
        (story.get("merge_commit") and str(story.get("merge_commit", "")).strip())
        or (story.get("merge_commits") and isinstance(story.get("merge_commits"), list))
    ),
    # Has commit_sha
    lambda story: bool(
        story.get("commit_sha") and str(story.get("commit_sha", "")).strip()
    ),
]


@dataclass
class ValidationResult:
    """Container for validation results."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stories_checked: int = 0
    stories_missing_evidence: int = 0

    def add_error(self, message: str) -> None:
        """Add an error to the result."""
        self.errors.append(f"ERROR: {message}")
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(f"WARNING: {message}")

    def print(self, verbose: bool = False) -> None:
        """Print all messages."""
        for msg in self.errors:
            print(msg, file=sys.stderr)

        for msg in self.warnings:
            print(msg)

        if verbose:
            print(
                f"\nSummary: {self.stories_checked} stories checked, {self.stories_missing_evidence} missing evidence"
            )


def load_yaml_file(filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load and parse a YAML file.

    Returns:
        Tuple of (parsed_data, error_message)
    """
    if not filepath.exists():
        return None, f"File not found: {filepath}"

    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
        return data, None
    except yaml.YAMLError as e:
        return None, f"YAML parsing error in {filepath}: {e}"
    except OSError as e:
        return None, f"IO error reading {filepath}: {e}"


def extract_stories_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract all stories from workflow status data.

    Stories can be in multiple locations:
    - 'completed' section (top-level list)
    - 'stories' section
    - 'launch_stories' section
    - Within 'epics' -> 'story_ids' references

    Returns:
        List of story dictionaries
    """
    stories: list[dict[str, Any]] = []

    # Extract from completed section (top-level list)
    if "completed" in data:
        completed_items = data["completed"]
        if isinstance(completed_items, list):
            stories.extend([item for item in completed_items if isinstance(item, dict)])

    # Extract from stories section
    if "stories" in data:
        stories_items = data["stories"]
        if isinstance(stories_items, list):
            stories.extend([item for item in stories_items if isinstance(item, dict)])

    # Extract from launch_stories section
    if "launch_stories" in data:
        launch_items = data["launch_stories"]
        if isinstance(launch_items, list):
            stories.extend([item for item in launch_items if isinstance(item, dict)])

    return stories


def has_valid_evidence(story: dict[str, Any]) -> bool:
    """
    Check if a story has valid evidence fields.

    A story has valid evidence if it matches at least one of the
    VALID_EVIDENCE_COMBINATIONS.

    Args:
        story: Story dictionary

    Returns:
        True if story has valid evidence, False otherwise
    """
    return any(check(story) for check in VALID_EVIDENCE_COMBINATIONS)


def validate_story_evidence(story: dict[str, Any], result: ValidationResult) -> None:
    """
    Validate that a story with completed/merged status has evidence.

    Args:
        story: Story dictionary
        result: ValidationResult to populate
    """
    story_id = story.get("id", "unknown")
    status = story.get("status")

    # Skip if status doesn't require evidence
    if status not in REQUIRES_EVIDENCE:
        return

    result.stories_checked += 1

    # Check if story has any evidence
    if not has_valid_evidence(story):
        result.stories_missing_evidence += 1

        # Detail which evidence fields are missing
        missing_fields = []
        if not story.get("pr_number") or not str(story.get("pr_number", "")).strip():
            missing_fields.append("pr_number")
        if not (
            (story.get("merge_commit") and str(story.get("merge_commit", "")).strip())
            or (
                story.get("merge_commits")
                and isinstance(story.get("merge_commits"), list)
            )
        ):
            missing_fields.append("merge_commit or merge_commits")
        if not story.get("commit_sha") or not str(story.get("commit_sha", "")).strip():
            missing_fields.append("commit_sha")

        result.add_error(
            f"Story '{story_id}' has status='{status}' but lacks merge evidence. "
            f"Missing: {', '.join(missing_fields)}. "
            f"At least one evidence field is required for completed/merged status."
        )


def validate_status_evidence(data: dict[str, Any], result: ValidationResult) -> None:
    """
    Validate that all completed/merged stories have evidence.

    Args:
        data: Workflow status YAML data
        result: ValidationResult to populate
    """
    # Extract all stories from various locations
    stories = extract_stories_from_data(data)

    # Validate each story
    for story in stories:
        if not isinstance(story, dict):
            continue
        validate_story_evidence(story, result)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate that completed/merged stories have PR/merge evidence"
    )
    parser.add_argument(
        "--file",
        "-f",
        default=str(WORKFLOW_STATUS_FILE),
        help=f"Path to workflow status file (default: {WORKFLOW_STATUS_FILE})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    result = ValidationResult()

    # Load workflow status file
    data, error = load_yaml_file(Path(args.file))
    if error:
        result.add_error(error)
        result.print(verbose=args.verbose)
        return 2
    elif data is None:
        result.add_error(f"Empty YAML file: {args.file}")
        result.print(verbose=args.verbose)
        return 2

    # Validate evidence
    validate_status_evidence(data, result)

    # Print results
    result.print(verbose=args.verbose)

    # Determine exit code
    if result.errors:
        print(
            f"\n❌ Status evidence validation FAILED: {result.stories_missing_evidence} "
            f"out of {result.stories_checked} completed/merged stories lack evidence",
            file=sys.stderr,
        )
        return 1
    else:
        if result.stories_checked > 0:
            print(
                f"✅ All {result.stories_checked} completed/merged stories have evidence"
            )
        else:
            print("✅ No completed/merged stories requiring evidence found")
        return 0


if __name__ == "__main__":
    sys.exit(main())
