#!/usr/bin/env python3
"""
Validate per-story evidence file conventions.

This script validates that each story in workflow-status.yaml has at least one
evidence file in docs/evidence/ following the naming convention:
  docs/evidence/{STORY-ID}-*.{json,md}

Exit codes:
    0 - All stories have evidence files (or no stories to check)
    1 - One or more stories lack evidence files
    2 - YAML parsing, file system, or configuration errors

Usage:
    python3 validate_story_evidence.py --story-id ST-XXX
    python3 validate_story_evidence.py --all
    python3 validate_story_evidence.py --all --verbose
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
EVIDENCE_DIR = Path("docs/evidence")

# Valid evidence file extensions
EVIDENCE_EXTENSIONS = {".json", ".md"}


@dataclass
class ValidationResult:
    """Container for validation results."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stories_checked: int = 0
    stories_with_evidence: int = 0
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
                f"\nSummary: {self.stories_checked} stories checked, "
                f"{self.stories_with_evidence} with evidence, "
                f"{self.stories_missing_evidence} missing evidence"
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


def extract_story_ids_from_data(data: dict[str, Any]) -> set[str]:
    """
    Extract all story IDs from workflow status data.

    Stories can be in multiple locations:
    - 'completed' section (top-level list)
    - 'in_progress' section
    - 'stories' section
    - 'launch_stories' section
    - Within 'epics' -> 'story_ids' references

    Returns:
        Set of story IDs (uppercase for consistent comparison)
    """
    story_ids: set[str] = set()

    def extract_id(item: Any) -> str | None:
        """Extract story ID from an item, handling both string and dict formats."""
        if isinstance(item, str):
            return item.upper()
        elif isinstance(item, dict):
            story_id = item.get("id") or item.get("story_id")
            if story_id:
                return str(story_id).upper()
        return None

    # Extract from completed section (top-level list)
    if "completed" in data:
        completed_items = data["completed"]
        if isinstance(completed_items, list):
            for item in completed_items:
                story_id = extract_id(item)
                if story_id:
                    story_ids.add(story_id)

    # Extract from in_progress section
    if "in_progress" in data:
        in_progress_items = data["in_progress"]
        if isinstance(in_progress_items, list):
            for item in in_progress_items:
                story_id = extract_id(item)
                if story_id:
                    story_ids.add(story_id)

    # Extract from stories section
    if "stories" in data:
        stories_items = data["stories"]
        if isinstance(stories_items, list):
            for item in stories_items:
                story_id = extract_id(item)
                if story_id:
                    story_ids.add(story_id)

    # Extract from launch_stories section
    if "launch_stories" in data:
        launch_items = data["launch_stories"]
        if isinstance(launch_items, list):
            for item in launch_items:
                story_id = extract_id(item)
                if story_id:
                    story_ids.add(story_id)

    # Extract from epics section
    if "epics" in data:
        epics = data["epics"]
        if isinstance(epics, list):
            for epic in epics:
                if isinstance(epic, dict):
                    # Epic may have story_ids list
                    epic_story_ids = epic.get("story_ids", [])
                    if isinstance(epic_story_ids, list):
                        for story_id in epic_story_ids:
                            if isinstance(story_id, str):
                                story_ids.add(story_id.upper())
                            elif isinstance(story_id, dict):
                                sid = extract_id(story_id)
                                if sid:
                                    story_ids.add(sid)

    return story_ids


def find_evidence_files(story_id: str, evidence_dir: Path) -> list[Path]:
    """
    Find evidence files for a story in the evidence directory.

    Evidence files follow the pattern: {STORY-ID}-*.{json,md}
    The story ID is case-insensitive for matching.

    Args:
        story_id: The story ID to search for
        evidence_dir: Path to the evidence directory

    Returns:
        List of matching evidence file paths
    """
    if not evidence_dir.exists():
        return []

    matching_files: list[Path] = []
    story_id_upper = story_id.upper()

    try:
        for file_path in evidence_dir.iterdir():
            if not file_path.is_file():
                continue

            # Check extension
            if file_path.suffix.lower() not in EVIDENCE_EXTENSIONS:
                continue

            # Check if filename starts with the story ID (case-insensitive)
            file_stem_upper = file_path.stem.upper()
            if (
                file_stem_upper.startswith(story_id_upper + "-")
                or file_stem_upper == story_id_upper
            ):
                matching_files.append(file_path)
    except OSError:
        pass

    return matching_files


def validate_story_evidence(
    story_id: str,
    evidence_dir: Path,
    result: ValidationResult,
    verbose: bool = False,
) -> bool:
    """
    Validate that a story has at least one evidence file.

    Args:
        story_id: The story ID to validate
        evidence_dir: Path to the evidence directory
        result: ValidationResult to populate
        verbose: Whether to print detailed output

    Returns:
        True if story has evidence, False otherwise
    """
    result.stories_checked += 1

    evidence_files = find_evidence_files(story_id, evidence_dir)

    if evidence_files:
        result.stories_with_evidence += 1
        if verbose:
            print(f"  ✅ {story_id}: {len(evidence_files)} evidence file(s)")
            for f in evidence_files:
                print(f"     - {f.name}")
        return True
    else:
        result.stories_missing_evidence += 1
        result.add_error(
            f"Story '{story_id}' has no evidence files. "
            f"Expected: docs/evidence/{story_id}-*{{.json,.md}}"
        )
        if verbose:
            print(f"  ❌ {story_id}: NO evidence files found")
        return False


def validate_all_stories(
    data: dict[str, Any],
    evidence_dir: Path,
    result: ValidationResult,
    verbose: bool = False,
) -> None:
    """
    Validate evidence for all stories in workflow status.

    Args:
        data: Workflow status YAML data
        evidence_dir: Path to the evidence directory
        result: ValidationResult to populate
        verbose: Whether to print detailed output
    """
    story_ids = extract_story_ids_from_data(data)

    if not story_ids:
        if verbose:
            print("No stories found in workflow status file")
        return

    if verbose:
        print(f"Found {len(story_ids)} story(ies) to validate:\n")

    for story_id in sorted(story_ids):
        validate_story_evidence(story_id, evidence_dir, result, verbose)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate per-story evidence file conventions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 %(prog)s --story-id ST-CONTROL-001
  python3 %(prog)s --all
  python3 %(prog)s --all --verbose
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
        help="Validate evidence for all stories in workflow status",
    )
    parser.add_argument(
        "--file",
        "-f",
        default=str(WORKFLOW_STATUS_FILE),
        help=f"Path to workflow status file (default: {WORKFLOW_STATUS_FILE})",
    )
    parser.add_argument(
        "--evidence-dir",
        "-e",
        default=str(EVIDENCE_DIR),
        help=f"Path to evidence directory (default: {EVIDENCE_DIR})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    if not args.story_id and not args.all:
        parser.error("Must specify either --story-id or --all")

    result = ValidationResult()

    # Validate paths
    workflow_file = Path(args.file)
    evidence_dir = Path(args.evidence_dir)

    # Load workflow status file
    data, error = load_yaml_file(workflow_file)
    if error:
        result.add_error(error)
        result.print(verbose=args.verbose)
        return 2
    elif data is None:
        result.add_error(f"Empty YAML file: {args.file}")
        result.print(verbose=args.verbose)
        return 2

    # Validate evidence directory exists
    if not evidence_dir.exists():
        result.add_error(f"Evidence directory not found: {evidence_dir}")
        result.print(verbose=args.verbose)
        return 2

    # Perform validation
    if args.story_id:
        # Validate single story
        story_id = args.story_id.upper()
        if args.verbose:
            print(f"Validating evidence for story: {story_id}\n")
        validate_story_evidence(story_id, evidence_dir, result, args.verbose)
    else:
        # Validate all stories
        if args.verbose:
            print(f"Validating evidence for all stories\n")
        validate_all_stories(data, evidence_dir, result, args.verbose)

    # Print results
    result.print(verbose=args.verbose)

    # Determine exit code
    if result.errors:
        if args.all:
            print(
                f"\n❌ Story evidence validation FAILED: {result.stories_missing_evidence} "
                f"out of {result.stories_checked} stories lack evidence files",
                file=sys.stderr,
            )
        else:
            print(
                f"\n❌ Story evidence validation FAILED for {args.story_id}",
                file=sys.stderr,
            )
        return 1
    else:
        if args.all:
            if result.stories_checked > 0:
                print(f"✅ All {result.stories_checked} stories have evidence files")
            else:
                print("✅ No stories found requiring evidence validation")
        else:
            print(f"✅ Story '{args.story_id}' has evidence files")
        return 0


if __name__ == "__main__":
    sys.exit(main())
