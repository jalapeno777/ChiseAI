#!/usr/bin/env python3
"""
Validate FR traceability from PRD to stories.

This script validates:
1. Extract all FR-XXX IDs from docs/prd.md
2. Extract all fr_coverage references from docs/bmm-workflow-status.yaml
3. Verify every PRD FR is covered by at least one story's fr_coverage
4. Report any orphaned FRs (FRs in PRD but not covered by any story)

Exit codes:
    0 - All FRs are covered by stories
    1 - One or more FRs are orphaned (not covered by any story)
    2 - Validation could not complete (file errors, parsing issues)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Configuration
PRD_FILE = Path("docs/prd.md")
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")

# FR pattern: FR-XXX or FR-XXXa (e.g., FR-001, FR-004a, FR-DEV-001)
FR_PATTERN = re.compile(r"FR-[A-Z]*-?\d+[a-z]?")


class ValidationResult:
    """Container for validation results."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(f"ERROR: {message}")

    def add_warning(self, message: str) -> None:
        self.warnings.append(f"WARNING: {message}")

    def add_info(self, message: str) -> None:
        self.info.append(f"INFO: {message}")

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def print(self, verbose: bool = False) -> None:
        """Print all messages."""
        for msg in self.info:
            print(msg)

        for msg in self.errors:
            print(msg, file=sys.stderr)

        for msg in self.warnings:
            print(msg)

        if verbose:
            print(
                f"\nSummary: {len(self.errors)} errors, {len(self.warnings)} warnings"
            )


def extract_frs_from_prd(filepath: Path) -> set[str]:
    """
    Extract all FR-XXX IDs from the PRD markdown file.

    Returns:
        Set of FR IDs found in the PRD
    """
    frs: set[str] = set()

    if not filepath.exists():
        return frs

    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        # Find all FR-XXX patterns
        matches = FR_PATTERN.findall(content)
        frs.update(matches)

    except OSError:
        pass

    return frs


def extract_fr_coverage_from_workflow(filepath: Path) -> dict[str, list[str]]:
    """
    Extract fr_coverage mappings from workflow status YAML.

    Returns:
        Dict mapping FR ID to list of story IDs that cover it
    """
    coverage: dict[str, list[str]] = {}

    if not filepath.exists():
        return coverage

    try:
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return coverage

    if not isinstance(data, dict):
        return coverage

    stories = data.get("stories", [])
    if not isinstance(stories, list):
        return coverage

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = story.get("id", "unknown")
        fr_coverage = story.get("fr_coverage", [])

        if not isinstance(fr_coverage, list):
            continue

        for fr in fr_coverage:
            if isinstance(fr, str):
                if fr not in coverage:
                    coverage[fr] = []
                coverage[fr].append(story_id)

    return coverage


def validate_fr_traceability(
    prd_frs: set[str], fr_coverage: dict[str, list[str]], result: ValidationResult
) -> None:
    """
    Validate that all PRD FRs are covered by stories.

    Args:
        prd_frs: Set of FR IDs found in PRD
        fr_coverage: Dict mapping FR ID to list of covering story IDs
        result: ValidationResult to populate
    """
    if not prd_frs:
        result.add_error("No FRs found in PRD file")
        return

    result.add_info(f"Found {len(prd_frs)} FRs in PRD")

    # Find orphaned FRs (in PRD but not covered by any story)
    covered_frs = set(fr_coverage.keys())
    orphaned_frs = prd_frs - covered_frs

    # Find FRs covered but not in PRD (potential drift)
    extra_coverage = covered_frs - prd_frs

    # Report coverage statistics
    coverage_count = len(prd_frs - orphaned_frs)
    result.add_info(f"FRs covered by stories: {coverage_count}/{len(prd_frs)}")

    # Report orphaned FRs as errors
    if orphaned_frs:
        result.add_error(
            f"Orphaned FRs (not covered by any story): {', '.join(sorted(orphaned_frs))}"
        )
        for fr in sorted(orphaned_frs):
            result.add_error(f"  - {fr}: No story has this FR in fr_coverage")

    # Report extra coverage as warnings
    if extra_coverage:
        result.add_warning(
            f"FRs covered by stories but not found in PRD: {', '.join(sorted(extra_coverage))}"
        )

    # Report detailed coverage for verbose mode
    for fr in sorted(prd_frs - orphaned_frs):
        stories = fr_coverage.get(fr, [])
        result.add_info(
            f"  {fr} -> covered by {len(stories)} story(s): {', '.join(stories)}"
        )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate FR traceability from PRD to stories"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    args = parser.parse_args()

    result = ValidationResult()

    # Check if required files exist
    if not PRD_FILE.exists():
        result.add_error(f"PRD file not found: {PRD_FILE}")
        result.print(verbose=args.verbose)
        return 2

    if not WORKFLOW_STATUS_FILE.exists():
        result.add_error(f"Workflow status file not found: {WORKFLOW_STATUS_FILE}")
        result.print(verbose=args.verbose)
        return 2

    # Extract FRs from PRD
    prd_frs = extract_frs_from_prd(PRD_FILE)

    # Extract fr_coverage from workflow status
    fr_coverage = extract_fr_coverage_from_workflow(WORKFLOW_STATUS_FILE)

    # Validate traceability
    validate_fr_traceability(prd_frs, fr_coverage, result)

    # Print results
    result.print(verbose=args.verbose)

    # Determine exit code
    if not result.is_valid:
        return 1
    else:
        print("✅ All FRs are covered by stories")
        return 0


if __name__ == "__main__":
    sys.exit(main())
