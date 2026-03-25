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
from datetime import datetime
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
    legacy_warnings: list[str] = field(
        default_factory=list
    )  # Legacy stories (outside grace period)
    stories_checked: int = 0
    stories_missing_evidence: int = 0

    def add_error(self, message: str) -> None:
        """Add an error to the result (blocking)."""
        self.errors.append(f"ERROR: {message}")
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning to the result (non-blocking)."""
        self.warnings.append(f"WARNING: {message}")

    def add_legacy_warning(self, message: str) -> None:
        """Add a legacy warning to the result (non-blocking, outside grace period)."""
        self.legacy_warnings.append(f"WARNING (legacy): {message}")

    def has_blocking_errors(self) -> bool:
        """Check if there are any blocking errors."""
        return len(self.errors) > 0

    def print(self, verbose: bool = False) -> None:
        """Print all messages."""
        for msg in self.errors:
            print(msg, file=sys.stderr)

        for msg in self.warnings:
            print(msg)

        for msg in self.legacy_warnings:
            print(msg)

        if verbose:
            print(
                f"\nSummary: {self.stories_checked} stories checked, "
                f"{self.stories_missing_evidence} missing evidence, "
                f"{len(self.legacy_warnings)} legacy warnings"
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


def validate_story_evidence(
    story: dict[str, Any], result: ValidationResult, grace_period_days: int = 7
) -> None:
    """
    Validate that a story with completed/merged status has evidence.

    Args:
        story: Story dictionary
        result: ValidationResult to populate
        grace_period_days: Stories older than this are warned but not blocked
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

        error_msg = (
            f"Story '{story_id}' has status='{status}' but lacks merge evidence. "
            f"Missing: {', '.join(missing_fields)}. "
            f"At least one evidence field is required for completed/merged status."
        )

        # Check if story is legacy (outside grace period)
        story_age = get_story_completion_age(story)
        is_legacy = story_age is not None and story_age > grace_period_days

        if is_legacy:
            # Legacy story - add as legacy warning, not blocking error
            result.add_legacy_warning(
                f"{error_msg} (story is {story_age} days old, grace period: {grace_period_days} days)"
            )
        else:
            # Within grace period - blocking error
            result.add_error(error_msg)


def validate_status_evidence(
    data: dict[str, Any], result: ValidationResult, grace_period_days: int = 7
) -> None:
    """
    Validate that all completed/merged stories have evidence.

    Args:
        data: Workflow status YAML data
        result: ValidationResult to populate
        grace_period_days: Stories older than this are warned but not blocked
    """
    # Extract all stories from various locations
    stories = extract_stories_from_data(data)

    # Validate each story
    for story in stories:
        if not isinstance(story, dict):
            continue
        validate_story_evidence(story, result, grace_period_days)


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
    parser.add_argument(
        "--legacy-grace-period-days",
        type=int,
        default=7,
        help="Stories older than this many days are warned but not blocked (default: 7)",
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
    validate_status_evidence(data, result, args.legacy_grace_period_days)

    # Print results
    result.print(verbose=args.verbose)

    # Determine exit code
    if result.has_blocking_errors():
        print(
            f"\n❌ Status evidence validation FAILED: {result.stories_missing_evidence} "
            f"out of {result.stories_checked} completed/merged stories lack evidence",
            file=sys.stderr,
        )
        return 1
    else:
        if result.stories_checked > 0:
            if result.legacy_warnings:
                print(
                    f"✅ Validation passed with {len(result.legacy_warnings)} legacy warnings "
                    f"(stories older than {args.legacy_grace_period_days} days)"
                )
            else:
                print(
                    f"✅ All {result.stories_checked} completed/merged stories have evidence"
                )
        else:
            print("✅ No completed/merged stories requiring evidence found")
        return 0


if __name__ == "__main__":
    sys.exit(main())
