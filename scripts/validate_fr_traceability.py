#!/usr/bin/env python3
"""
Validate Functional Requirement (FR) traceability from PRD to stories.

This script verifies:
1. All PRD FRs are covered by at least one story
2. Stories reference valid FRs
3. No orphaned FRs exist

Exit codes:
    0 - All FRs covered
    1 - Orphaned FRs found or validation errors
    2 - Warnings only (e.g., suggestions available)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

# Configuration
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")
PRD_FILE = Path("docs/prd.md")
VALIDATION_REGISTRY_FILE = Path("docs/validation/validation-registry.yaml")

# FR pattern supports legacy numeric IDs (FR-001) and namespaced IDs
# like FR-EVO-002 or FR-DEV-005.
FR_PATTERN = re.compile(r"\bFR-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.IGNORECASE)


def normalize_fr_id(fr_id: str) -> str:
    return fr_id.strip().upper()


class ValidationResult:
    """Container for validation results."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.suggestions: dict[str, list[str]] = {}
        self.stats: dict[str, Any] = {
            "total_frs": 0,
            "covered_frs": 0,
            "orphaned_frs": 0,
            "total_stories": 0,
            "stories_with_fr_coverage": 0,
        }

    def add_error(self, message: str) -> None:
        self.errors.append(f"ERROR: {message}")

    def add_warning(self, message: str) -> None:
        self.warnings.append(f"WARNING: {message}")

    def add_suggestion(self, fr_id: str, story_id: str) -> None:
        if fr_id not in self.suggestions:
            self.suggestions[fr_id] = []
        self.suggestions[fr_id].append(story_id)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def print(self, verbose: bool = False, json_output: bool = False) -> None:
        """Print all messages."""
        if json_output:
            output = {
                "valid": self.is_valid,
                "stats": self.stats,
                "errors": self.errors,
                "warnings": self.warnings,
                "suggestions": self.suggestions,
            }
            print(json.dumps(output, indent=2))
            return

        for msg in self.errors:
            print(msg, file=sys.stderr)

        for msg in self.warnings:
            print(msg)

        if self.suggestions:
            print("\n📋 Story Suggestions for Orphaned FRs:")
            for fr_id, stories in self.suggestions.items():
                print(f"  {fr_id}: Consider stories {', '.join(stories)}")

        if verbose:
            print("\n📊 Summary Statistics:")
            for key, value in self.stats.items():
                print(f"  {key}: {value}")

            if not self.is_valid:
                print(
                    f"\n❌ Validation failed: {len(self.errors)} errors, {len(self.warnings)} warnings"
                )
            elif self.warnings:
                print(f"\n⚠️  Validation passed with {len(self.warnings)} warnings")
            else:
                print("\n✅ All validations passed")


def load_yaml_file(filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse a YAML file."""
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


def load_prd_file(filepath: Path) -> tuple[str | None, str | None]:
    """Load PRD markdown file."""
    if not filepath.exists():
        return None, f"File not found: {filepath}"

    try:
        with open(filepath) as f:
            return f.read(), None
    except OSError as e:
        return None, f"IO error reading {filepath}: {e}"


def extract_frs_from_prd(content: str) -> set[str]:
    """Extract all FR references from PRD content."""
    return {normalize_fr_id(fr_id) for fr_id in FR_PATTERN.findall(content)}


def extract_fr_coverage_from_stories(
    stories: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Extract FR coverage mapping from stories.

    Returns: dict mapping FR ID to list of story IDs that cover it
    """
    coverage: dict[str, list[str]] = {}

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = story.get("id", "unknown")
        fr_coverage = story.get("fr_coverage", [])

        if isinstance(fr_coverage, str):
            fr_coverage = [fr_coverage]

        for fr_id in fr_coverage:
            if isinstance(fr_id, str):
                normalized = normalize_fr_id(fr_id)
                if normalized not in coverage:
                    coverage[normalized] = []
                coverage[normalized].append(story_id)

    return coverage


def find_story_suggestions(
    orphaned_fr: str,
    stories: list[dict[str, Any]],
    prd_content: str,
) -> list[str]:
    """Find story suggestions for an orphaned FR based on keywords/title matching."""
    suggestions = []

    # Extract FR description from PRD (simple heuristic: look for FR line)
    fr_description = ""
    for line in prd_content.split("\n"):
        if orphaned_fr in line:
            fr_description = line.lower()
            break

    # Keywords to match
    keywords = set()
    if fr_description:
        # Extract meaningful words (longer than 3 chars)
        words = re.findall(r"\b[a-z]{4,}\b", fr_description)
        keywords = set(words)

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = story.get("id", "")
        story_title = story.get("title", "").lower()
        story_desc = story.get("description", "").lower()
        story_text = f"{story_title} {story_desc}"

        # Calculate keyword match score
        matches = sum(1 for kw in keywords if kw in story_text)
        if matches > 0:
            suggestions.append((story_id, matches))

    # Sort by match score and return top 3
    suggestions.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in suggestions[:3]]


def validate_validation_registry(
    validation_data: dict[str, Any],
    workflow_data: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate validation registry coverage for stories."""
    validations = validation_data.get("validations", [])
    stories = workflow_data.get("stories", [])

    # Build set of story IDs with validations
    validated_story_ids: set[str] = set()
    for validation in validations:
        if isinstance(validation, dict):
            story_id = validation.get("story_id")
            if story_id:
                validated_story_ids.add(story_id)

    # Build set of all story IDs
    all_story_ids: set[str] = set()
    for story in stories:
        if isinstance(story, dict):
            story_id = story.get("id")
            if story_id:
                all_story_ids.add(story_id)

    # Check for stories without validation entries
    stories_without_validation = all_story_ids - validated_story_ids
    if stories_without_validation:
        for story_id in sorted(stories_without_validation):
            result.add_warning(
                f"Story '{story_id}' has no validation entry in validation-registry.yaml"
            )

    # Check for validation entries referencing non-existent stories
    invalid_validations = validated_story_ids - all_story_ids
    if invalid_validations:
        for story_id in sorted(invalid_validations):
            result.add_error(f"Validation references non-existent story '{story_id}'")

    # Check for status inconsistencies
    for validation in validations:
        if not isinstance(validation, dict):
            continue

        story_id = validation.get("story_id")
        validation_status = validation.get("status")

        if not story_id:
            continue

        # Find corresponding story
        story = next(
            (s for s in stories if isinstance(s, dict) and s.get("id") == story_id),
            None,
        )

        if story:
            story_status = story.get("status")

            # Flag if story is completed but validation is not validated
            if story_status == "completed" and validation_status != "validated":
                result.add_warning(
                    f"Story '{story_id}' is completed but validation status is '{validation_status}'"
                )

            # Flag if validation is validated but story is not completed
            if validation_status == "validated" and story_status != "completed":
                result.add_warning(
                    f"Validation for '{story_id}' is validated but story status is '{story_status}'"
                )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate FR traceability from PRD to stories"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--check-validation",
        action="store_true",
        help="Also verify validation registry coverage",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Suggest stories for orphaned FRs",
    )
    args = parser.parse_args()

    result = ValidationResult()

    # Load PRD file
    prd_content, error = load_prd_file(PRD_FILE)
    if error:
        result.add_error(error)
        result.print(verbose=args.verbose, json_output=args.json)
        return 1

    # Load workflow status file
    workflow_data, error = load_yaml_file(WORKFLOW_STATUS_FILE)
    if error:
        result.add_error(error)
        result.print(verbose=args.verbose, json_output=args.json)
        return 1

    # Extract FRs from PRD
    prd_frs = extract_frs_from_prd(prd_content)
    result.stats["total_frs"] = len(prd_frs)

    # Extract FR coverage from stories
    stories = workflow_data.get("stories", [])
    result.stats["total_stories"] = len(stories)

    fr_coverage = extract_fr_coverage_from_stories(stories)
    covered_frs = set(fr_coverage.keys())
    result.stats["covered_frs"] = len(covered_frs)

    # Count stories with FR coverage
    stories_with_coverage = sum(
        1 for s in stories if isinstance(s, dict) and s.get("fr_coverage")
    )
    result.stats["stories_with_fr_coverage"] = stories_with_coverage

    # Find orphaned FRs (in PRD but not covered by any story)
    orphaned_frs = prd_frs - covered_frs
    result.stats["orphaned_frs"] = len(orphaned_frs)

    for fr_id in sorted(orphaned_frs):
        result.add_error(f"FR '{fr_id}' is orphaned - not covered by any story")

        if args.suggest:
            suggestions = find_story_suggestions(fr_id, stories, prd_content)
            for story_id in suggestions:
                result.add_suggestion(fr_id, story_id)

    # Find FRs covered by stories but not in PRD
    extra_frs = covered_frs - prd_frs
    for fr_id in sorted(extra_frs):
        result.add_warning(f"FR '{fr_id}' is covered by stories but not found in PRD")

    # Check validation registry if requested
    if args.check_validation:
        validation_data, error = load_yaml_file(VALIDATION_REGISTRY_FILE)
        if error:
            result.add_error(error)
        elif validation_data:
            validate_validation_registry(validation_data, workflow_data, result)

    # Print results
    result.print(verbose=args.verbose, json_output=args.json)

    # Determine exit code
    if result.errors:
        return 1
    elif result.warnings:
        return 2
    else:
        if not args.json:
            print("✅ All FR traceability checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
