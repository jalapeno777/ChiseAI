#!/usr/bin/env python3
"""
Validate synchronization between BMAD workflow status files.

This script validates:
1. YAML parsing correctness for docs/bmm-workflow-status.yaml
2. YAML parsing correctness for docs/validation/validation-registry.yaml
3. Story ID consistency between files
4. Status vocabulary compliance

Exit codes:
    0 - All validations passed
    1 - Errors (parsing failures, invalid status)
    2 - Warnings (missing references, consistency issues)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

# Configuration
WORKFLOW_STATUS_FILE = Path("docs/bmm-workflow-status.yaml")
VALIDATION_REGISTRY_FILE = Path("docs/validation/validation-registry.yaml")

# Allowed status vocabularies
WORKFLOW_STATUSES = {"planned", "in_progress", "completed", "blocked", "deprecated"}
VALIDATION_STATUSES = {"planned", "in_progress", "validated", "blocked", "deprecated"}


class ValidationResult:
    """Container for validation results."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(f"ERROR: {message}")

    def add_warning(self, message: str) -> None:
        self.warnings.append(f"WARNING: {message}")

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def print(self, verbose: bool = False) -> None:
        """Print all messages."""
        for msg in self.errors:
            print(msg, file=sys.stderr)

        for msg in self.warnings:
            print(msg)

        if verbose and not self.is_valid:
            print(
                f"\nSummary: {len(self.errors)} errors, {len(self.warnings)} warnings"
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


def validate_workflow_status(data: dict[str, Any], result: ValidationResult) -> None:
    """Validate workflow status file structure and status values."""

    # Check required top-level keys
    if "sprints" not in data:
        result.add_error("Missing required key: 'sprints' in workflow status")

    if "stories" not in data:
        result.add_warning("Missing key: 'stories' (may be empty for planned projects)")

    # Validate sprints
    if "sprints" in data:
        for idx, sprint in enumerate(data.get("sprints", [])):
            if not isinstance(sprint, dict):
                result.add_error(f"Sprint {idx} is not a dictionary")
                continue

            sprint_id = sprint.get("id", f"index_{idx}")

            # Validate status
            status = sprint.get("status")
            if status and status not in WORKFLOW_STATUSES:
                result.add_error(
                    f"Sprint '{sprint_id}' has invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(WORKFLOW_STATUSES))}"
                )

    # Validate stories if present
    if "stories" in data:
        for idx, story in enumerate(data.get("stories", [])):
            if not isinstance(story, dict):
                result.add_error(f"Story {idx} is not a dictionary")
                continue

            story_id = story.get("id", f"index_{idx}")

            # Validate status
            status = story.get("status")
            if status and status not in WORKFLOW_STATUSES:
                result.add_error(
                    f"Story '{story_id}' has invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(WORKFLOW_STATUSES))}"
                )


def validate_validation_registry(
    data: dict[str, Any], result: ValidationResult
) -> None:
    """Validate validation registry file structure and status values."""

    # Check for validations array
    if "validations" not in data:
        result.add_warning("Missing key: 'validations' (may be empty for new projects)")

    # Validate individual validations
    if "validations" in data:
        for idx, validation in enumerate(data.get("validations", [])):
            if not isinstance(validation, dict):
                result.add_error(f"Validation {idx} is not a dictionary")
                continue

            validation_id = validation.get("id", f"index_{idx}")

            # Validate status
            status = validation.get("status")
            if status and status not in VALIDATION_STATUSES:
                result.add_error(
                    f"Validation '{validation_id}' has invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(VALIDATION_STATUSES))}"
                )


def extract_story_ids(data: dict[str, Any]) -> set[str]:
    """Extract all story IDs from workflow status data."""
    story_ids: set[str] = set()

    if "stories" in data:
        for story in data.get("stories", []):
            if isinstance(story, dict) and "id" in story:
                story_ids.add(story["id"])

    if "sprints" in data:
        # Check for story_ids within sprints
        for sprint in data.get("sprints", []):
            if isinstance(sprint, dict) and "stories" in sprint:
                for story_id in sprint.get("stories", []):
                    if isinstance(story_id, str):
                        story_ids.add(story_id)
                    elif isinstance(story_id, dict) and "id" in story_id:
                        story_ids.add(story_id["id"])

    return story_ids


def extract_validation_story_refs(data: dict[str, Any]) -> set[str]:
    """Extract story references from validation registry."""
    refs: set[str] = set()

    if "validations" in data:
        for validation in data.get("validations", []):
            if isinstance(validation, dict):
                # Check for story_id field
                if "story_id" in validation:
                    refs.add(validation["story_id"])
                # Check for any field that looks like a story reference
                for _key, value in validation.items():
                    if isinstance(value, str) and value.startswith("ST-"):
                        refs.add(value)

    return refs


def validate_story_id_consistency(
    workflow_data: dict[str, Any],
    validation_data: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate that story IDs referenced in validation exist in workflow status."""

    workflow_story_ids = extract_story_ids(workflow_data)
    validation_story_refs = extract_validation_story_refs(validation_data)

    # Check for validation refs that don't exist in workflow
    missing_refs = validation_story_refs - workflow_story_ids
    for ref in missing_refs:
        result.add_warning(
            f"Story ID '{ref}' referenced in validation registry "
            f"but not found in workflow status"
        )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate BMAD workflow status synchronization"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full audit including all checks (default: quick validation)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    args = parser.parse_args()

    result = ValidationResult()

    # Load workflow status file
    workflow_data, error = load_yaml_file(WORKFLOW_STATUS_FILE)
    if error:
        result.add_error(error)
    elif workflow_data is None:
        result.add_error(f"Empty YAML file: {WORKFLOW_STATUS_FILE}")
    else:
        validate_workflow_status(workflow_data, result)

    # Load validation registry file
    validation_data, error = load_yaml_file(VALIDATION_REGISTRY_FILE)
    if error:
        result.add_error(error)
    elif validation_data is None:
        result.add_error(f"Empty YAML file: {VALIDATION_REGISTRY_FILE}")
    else:
        validate_validation_registry(validation_data, result)

    # Cross-reference validation (only in full mode)
    if args.full and workflow_data and validation_data:
        validate_story_id_consistency(workflow_data, validation_data, result)

    # Print results
    result.print(verbose=args.verbose)

    # Determine exit code
    if result.errors:
        return 1
    elif result.warnings:
        return 2
    else:
        print("✅ All validations passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
