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

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

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

    # Check required top-level keys - support both 'epics' and legacy 'sprints'
    has_epics = "epics" in data
    has_sprints = "sprints" in data

    if not has_epics and not has_sprints:
        result.add_error(
            "Missing required key: either 'epics' or 'sprints' must be present in workflow status"
        )

    if "stories" not in data:
        result.add_warning("Missing key: 'stories' (may be empty for planned projects)")

    # Validate epics (current canonical structure)
    if has_epics:
        _validate_epics(data.get("epics", []), result)

    # Validate sprints (legacy structure - backwards compatibility)
    if has_sprints:
        _validate_sprints(data.get("sprints", []), result)

    # Validate stories if present
    if "stories" in data:
        _validate_stories(data.get("stories", []), data.get("epics", []), result)


def _validate_epics(epics: list[Any], result: ValidationResult) -> set[str]:
    """Validate epics structure and return set of valid epic IDs."""
    epic_ids: set[str] = set()

    for idx, epic in enumerate(epics):
        if not isinstance(epic, dict):
            result.add_error(f"Epic {idx} is not a dictionary")
            continue

        epic_id = epic.get("id", f"index_{idx}")
        if epic_id:
            epic_ids.add(epic_id)

        # Validate required epic fields
        if "name" not in epic:
            result.add_error(f"Epic '{epic_id}' is missing required field: 'name'")

        # Validate status
        status = epic.get("status")
        if status and status not in WORKFLOW_STATUSES:
            result.add_error(
                f"Epic '{epic_id}' has invalid status '{status}'. "
                f"Must be one of: {', '.join(sorted(WORKFLOW_STATUSES))}"
            )

        # Validate story_ids if present
        story_ids = epic.get("story_ids", [])
        if story_ids and not isinstance(story_ids, list):
            result.add_error(
                f"Epic '{epic_id}' has invalid 'story_ids' - must be a list"
            )

    return epic_ids


def _validate_sprints(sprints: list[Any], result: ValidationResult) -> None:
    """Validate sprints structure (legacy support)."""
    for idx, sprint in enumerate(sprints):
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


def _validate_stories(
    stories: list[Any], epics: list[Any], result: ValidationResult
) -> None:
    """Validate stories structure and cross-references with epics."""
    # Build set of valid epic IDs for cross-reference validation
    epic_ids: set[str] = set()
    for epic in epics:
        if isinstance(epic, dict):
            epic_id = epic.get("id")
            if isinstance(epic_id, str):
                epic_ids.add(epic_id)

    story_ids_in_epics: set[str] = set()

    # Collect all story_ids referenced in epics
    for epic in epics:
        if isinstance(epic, dict):
            for story_id in epic.get("story_ids", []):
                if isinstance(story_id, str):
                    story_ids_in_epics.add(story_id)

    for idx, story in enumerate(stories):
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

        # Validate epic_id cross-reference
        epic_id = story.get("epic_id")
        if epic_id is not None:
            if epic_id not in epic_ids:
                epic_list = sorted(epic_ids) if epic_ids else []
                result.add_error(
                    f"Story '{story_id}' references unknown epic_id '{epic_id}'. "
                    f"Must be one of: {', '.join(epic_list) if epic_list else 'N/A - no epics defined'}"
                )

    # Validate that all story_ids in epics reference valid stories
    story_ids_in_stories = {
        story.get("id")
        for story in stories
        if isinstance(story, dict) and story.get("id")
    }

    for story_id in story_ids_in_epics:
        if story_id not in story_ids_in_stories:
            result.add_warning(
                f"Epic references story_id '{story_id}' that is not defined in stories list"
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

    # Support both 'epics' (current) and 'sprints' (legacy) for story extraction
    if "epics" in data:
        for epic in data.get("epics", []):
            if isinstance(epic, dict) and "story_ids" in epic:
                for story_id in epic.get("story_ids", []):
                    if isinstance(story_id, str):
                        story_ids.add(story_id)

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
                # Check for story_id field.
                # Skip null/None values for cross-cutting gates.
                story_id = validation.get("story_id")
                if story_id is not None and story_id != "None":
                    refs.add(story_id)
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


def validate_epic_status_consistency(
    workflow_data: dict[str, Any], result: ValidationResult
) -> None:
    """
    Validate that epic status is consistent with child story statuses.
    An epic's status should reflect the aggregate status of its stories.
    """
    epics = workflow_data.get("epics", [])
    stories = workflow_data.get("stories", [])

    if not isinstance(epics, list) or not isinstance(stories, list):
        return

    # Build story lookup by ID
    story_by_id: dict[str, dict[str, Any]] = {}
    for story in stories:
        if isinstance(story, dict) and "id" in story:
            story_by_id[story["id"]] = story

    for epic in epics:
        if not isinstance(epic, dict):
            continue

        epic_id = epic.get("id", "unknown")
        epic_status = epic.get("status")
        story_ids = epic.get("story_ids", [])

        if not isinstance(story_ids, list):
            continue

        # Collect child story statuses
        child_statuses: list[str] = []
        for story_id in story_ids:
            if isinstance(story_id, str) and story_id in story_by_id:
                story_status = story_by_id[story_id].get("status")
                if story_status:
                    child_statuses.append(story_status)

        if not child_statuses:
            continue

        # Derive expected epic status from child stories
        # Priority: in_progress > blocked > completed > planned
        if "in_progress" in child_statuses:
            expected_status = "in_progress"
        elif "blocked" in child_statuses:
            expected_status = "blocked"
        elif all(s == "completed" for s in child_statuses):
            expected_status = "completed"
        elif any(s == "completed" for s in child_statuses):
            expected_status = "in_progress"
        else:
            expected_status = "planned"

        # Check if epic status matches expected
        if epic_status and epic_status != expected_status:
            # Allow some flexibility - completed epics may have deprecated stories
            if epic_status == "completed" and expected_status == "in_progress":
                # Check if only deprecated stories are incomplete
                non_deprecated_incomplete = [
                    sid
                    for sid in story_ids
                    if isinstance(sid, str)
                    and sid in story_by_id
                    and story_by_id[sid].get("status") != "completed"
                    and story_by_id[sid].get("status") != "deprecated"
                ]
                if not non_deprecated_incomplete:
                    continue

            result.add_warning(
                f"Epic '{epic_id}' has status '{epic_status}' but derived status "
                f"from child stories is '{expected_status}' "
                f"(child statuses: {', '.join(child_statuses)})"
            )


def validate_validation_registry_completeness(
    workflow_data: dict[str, Any],
    validation_data: dict[str, Any],
    result: ValidationResult,
) -> None:
    """
    Validate that every story has a corresponding validation entry
    and that completed stories have validated status.
    """
    stories = workflow_data.get("stories", [])
    validations = validation_data.get("validations", [])

    if not isinstance(stories, list) or not isinstance(validations, list):
        return

    # Build validation lookup by story_id
    validation_by_story: dict[str, dict[str, Any]] = {}
    for validation in validations:
        if isinstance(validation, dict):
            story_id = validation.get("story_id")
            if isinstance(story_id, str):
                validation_by_story[story_id] = validation

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = story.get("id", "unknown")
        story_status = story.get("status")
        validation_status = story.get("validation_status")

        # Skip deprecated stories
        if story_status == "deprecated":
            continue

        # Check if story has validation entry
        if story_id not in validation_by_story:
            result.add_warning(
                f"Story '{story_id}' has no validation entry in validation registry"
            )
            continue

        # Check if completed stories have validated status
        if story_status == "completed":
            validation_entry = validation_by_story[story_id]
            registry_status = validation_entry.get("status")

            if validation_status != "validated":
                result.add_warning(
                    f"Story '{story_id}' is completed but has validation_status='{validation_status}' "
                    f"(should be 'validated')"
                )

            if registry_status != "validated":
                result.add_warning(
                    f"Story '{story_id}' is completed but validation registry status is '{registry_status}' "
                    f"(should be 'validated')"
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
        validate_validation_registry_completeness(
            workflow_data, validation_data, result
        )

    # Epic status consistency check (always run)
    if workflow_data:
        validate_epic_status_consistency(workflow_data, result)

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
