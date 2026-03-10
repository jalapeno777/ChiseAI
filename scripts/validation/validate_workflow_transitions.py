#!/usr/bin/env python3
"""
Workflow State Machine Validator for ChiseAI.

This script validates workflow status transitions and epic-story consistency
in the bmm-workflow-status.yaml file. It ensures that:

1. Status transitions follow the valid state machine rules
2. Epic status is consistent with its child stories
3. No invalid status combinations exist

Valid Status Transitions:
    planned → in_progress
    in_progress → completed
    in_progress → cancelled
    completed → archived
    completed → merged
    backlog → planned
    Any status → deprecated (admin override)

Exit Codes:
    0 - All validations passed (or only warnings in non-strict mode)
    1 - Validation errors found (strict mode or critical violations)
    2 - YAML parsing error or file not found

Usage:
    python3 scripts/validation/validate_workflow_transitions.py
    python3 scripts/validation/validate_workflow_transitions.py --strict
    python3 scripts/validation/validate_workflow_transitions.py --verbose --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")

# Valid status values
VALID_STATUSES = {
    "backlog",
    "planned",
    "in_progress",
    "completed",
    "merged",
    "archived",
    "cancelled",
    "deprecated",
}

# Terminal statuses (cannot transition out of these)
TERMINAL_STATUSES = {"archived", "cancelled", "deprecated"}

# Status transition rules: {from_status: [allowed_to_statuses]}
# Special case: "*" in allowed_to_statuses means any status can transition there
VALID_TRANSITIONS: dict[str, list[str]] = {
    "backlog": ["planned"],
    "planned": ["in_progress"],
    "in_progress": ["completed", "cancelled"],
    "completed": ["archived", "merged"],
    # Terminal statuses - no outgoing transitions allowed
    "merged": [],
    "archived": [],
    "cancelled": [],
    # Any status can transition to deprecated (admin override)
    # This is handled separately in the validation logic
}

# Epic status compatibility rules
# Maps epic status to the set of compatible child story statuses
EPIC_STORY_COMPATIBILITY: dict[str, set[str]] = {
    "planned": {"planned", "backlog"},
    "in_progress": {
        "planned",
        "in_progress",
        "completed",
        "merged",
        "archived",
        "cancelled",
    },
    "completed": {"completed", "merged", "archived", "cancelled"},
    "merged": {"completed", "merged", "archived", "cancelled"},
    "archived": {"archived", "cancelled"},
    "cancelled": {"cancelled"},
    "deprecated": set(),  # Deprecated epics should have no active stories
}

# Status precedence for calculating epic status from stories (higher = more advanced)
STATUS_PRECEDENCE: dict[str, int] = {
    "deprecated": -1,  # Special handling
    "backlog": 0,
    "planned": 1,
    "in_progress": 2,
    "completed": 3,
    "merged": 4,
    "archived": 5,
    "cancelled": 5,
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""

    severity: str  # 'error' or 'warning'
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
        }


@dataclass
class ValidationResult:
    """Container for validation results."""

    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    transition_count: int = 0
    epic_count: int = 0
    story_count: int = 0

    def add_issue(
        self, severity: str, message: str, context: dict[str, Any] | None = None
    ) -> None:
        """Add a validation issue."""
        issue = ValidationIssue(
            severity=severity, message=message, context=context or {}
        )
        self.issues.append(issue)
        if severity == "error":
            self.valid = False

    def add_error(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Add an error issue."""
        self.add_issue("error", message, context)

    def add_warning(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Add a warning issue."""
        self.add_issue("warning", message, context)

    def get_errors(self) -> list[ValidationIssue]:
        """Get all error issues."""
        return [i for i in self.issues if i.severity == "error"]

    def get_warnings(self) -> list[ValidationIssue]:
        """Get all warning issues."""
        return [i for i in self.issues if i.severity == "warning"]

    def print_text(self, verbose: bool = False) -> None:
        """Print results in text format."""
        errors = self.get_errors()
        warnings = self.get_warnings()

        if errors:
            print("\n❌ ERRORS:", file=sys.stderr)
            for issue in errors:
                print(f"  • {issue.message}", file=sys.stderr)
                if verbose and issue.context:
                    for key, value in issue.context.items():
                        print(f"    {key}: {value}", file=sys.stderr)

        if warnings:
            print("\n⚠️  WARNINGS:")
            for issue in warnings:
                print(f"  • {issue.message}")
                if verbose and issue.context:
                    for key, value in issue.context.items():
                        print(f"    {key}: {value}")

        if verbose:
            print(f"\n📊 Summary:")
            print(f"  Transitions checked: {self.transition_count}")
            print(f"  Epics checked: {self.epic_count}")
            print(f"  Stories checked: {self.story_count}")
            print(f"  Errors: {len(errors)}")
            print(f"  Warnings: {len(warnings)}")

    def print_json(self) -> None:
        """Print results in JSON format."""
        output = {
            "valid": self.valid,
            "summary": {
                "transitions_checked": self.transition_count,
                "epics_checked": self.epic_count,
                "stories_checked": self.story_count,
                "error_count": len(self.get_errors()),
                "warning_count": len(self.get_warnings()),
            },
            "issues": [issue.to_dict() for issue in self.issues],
        }
        print(json.dumps(output, indent=2))


@dataclass
class Story:
    """Represents a workflow story."""

    id: str
    status: str
    title: str
    epic_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Story | None:
        """Create a Story from a dictionary."""
        story_id = data.get("id")
        if not story_id:
            return None

        status = data.get("status", "")
        title = data.get("title", "Unknown")
        epic_id = data.get("epic_id")

        return cls(
            id=str(story_id),
            status=str(status).lower() if status else "",
            title=str(title),
            epic_id=str(epic_id) if epic_id else None,
            data=data,
        )


@dataclass
class Epic:
    """Represents an epic containing stories."""

    id: str
    status: str
    name: str
    story_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Epic | None:
        """Create an Epic from a dictionary."""
        epic_id = data.get("id")
        if not epic_id:
            return None

        status = data.get("status", "")
        name = data.get("name", "Unknown")
        story_ids = data.get("story_ids", [])

        return cls(
            id=str(epic_id),
            status=str(status).lower() if status else "",
            name=str(name),
            story_ids=[str(sid) for sid in story_ids] if story_ids else [],
            data=data,
        )


# =============================================================================
# Core Functions
# =============================================================================


def load_yaml_file(filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load and parse a YAML file.

    Args:
        filepath: Path to the YAML file

    Returns:
        Tuple of (parsed_data, error_message). If successful, error_message is None.
        If unsuccessful, parsed_data is None and error_message contains the error.
    """
    if not filepath.exists():
        return None, f"File not found: {filepath}"

    try:
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data, None
    except yaml.YAMLError as e:
        return None, f"YAML parsing error in {filepath}: {e}"
    except OSError as e:
        return None, f"IO error reading {filepath}: {e}"


def extract_stories(data: dict[str, Any]) -> list[Story]:
    """
    Extract all stories from workflow status data.

    Stories can be located in:
    - 'completed' section (top-level list)
    - 'backlog' section
    - 'launch_stories' section
    - 'epics' -> 'stories' (if nested)

    Args:
        data: Workflow status YAML data

    Returns:
        List of Story objects
    """
    stories: list[Story] = []
    story_ids_seen: set[str] = set()

    # Helper function to process a list of story dicts
    def process_story_list(
        story_list: list[Any], default_epic_id: str | None = None
    ) -> None:
        for item in story_list:
            if not isinstance(item, dict):
                continue
            story = Story.from_dict(item)
            if story and story.id not in story_ids_seen:
                # Set epic_id from context if not already set
                if default_epic_id and not story.epic_id:
                    story.epic_id = default_epic_id
                stories.append(story)
                story_ids_seen.add(story.id)

    # Extract from 'completed' section
    if "completed" in data and isinstance(data["completed"], list):
        process_story_list(data["completed"])

    # Extract from 'backlog' section
    if "backlog" in data and isinstance(data["backlog"], list):
        process_story_list(data["backlog"])

    # Extract from 'launch_stories' section
    if "launch_stories" in data and isinstance(data["launch_stories"], list):
        process_story_list(data["launch_stories"])

    # Extract from 'stories' section (if exists)
    if "stories" in data and isinstance(data["stories"], list):
        process_story_list(data["stories"])

    return stories


def extract_epics(data: dict[str, Any]) -> list[Epic]:
    """
    Extract all epics from workflow status data.

    Epics are located in the 'epics' section.

    Args:
        data: Workflow status YAML data

    Returns:
        List of Epic objects
    """
    epics: list[Epic] = []

    if "epics" in data and isinstance(data["epics"], list):
        for item in data["epics"]:
            if not isinstance(item, dict):
                continue
            epic = Epic.from_dict(item)
            if epic:
                epics.append(epic)

    return epics


def is_valid_status(status: str) -> bool:
    """Check if a status value is valid."""
    return status.lower() in VALID_STATUSES


def is_valid_transition(from_status: str, to_status: str) -> tuple[bool, str]:
    """
    Check if a status transition is valid.

    Args:
        from_status: The current status
        to_status: The target status

    Returns:
        Tuple of (is_valid, reason_message)
    """
    from_lower = from_status.lower()
    to_lower = to_status.lower()

    # Same status is always valid (no transition)
    if from_lower == to_lower:
        return True, ""

    # Check if from_status is valid
    if not is_valid_status(from_lower):
        return False, f"Invalid source status: '{from_status}'"

    # Check if to_status is valid
    if not is_valid_status(to_lower):
        return False, f"Invalid target status: '{to_status}'"

    # Any status can transition to deprecated (admin override)
    if to_lower == "deprecated":
        return True, ""

    # Check terminal statuses - cannot transition out
    if from_lower in TERMINAL_STATUSES:
        return False, f"Cannot transition out of terminal status '{from_status}'"

    # Check valid transitions
    allowed = VALID_TRANSITIONS.get(from_lower, [])
    if to_lower in allowed:
        return True, ""

    # Invalid transition
    return (
        False,
        f"Invalid transition: '{from_status}' → '{to_status}'. "
        f"Allowed from '{from_status}': {allowed if allowed else 'none (terminal status)'}",
    )


def get_story_status_history(story: Story) -> list[tuple[str, str]]:
    """
    Extract status change history for a story if available.

    Some stories may have status_history or similar fields tracking changes.

    Args:
        story: Story object

    Returns:
        List of (old_status, new_status) tuples
    """
    history: list[tuple[str, str]] = []

    # Check for status_history field
    if "status_history" in story.data and isinstance(
        story.data["status_history"], list
    ):
        for entry in story.data["status_history"]:
            if isinstance(entry, dict):
                old_status = entry.get("from", "")
                new_status = entry.get("to", "")
                if old_status and new_status:
                    history.append((old_status, new_status))

    # Check for status_correction field (indicates a status change happened)
    if "status_correction" in story.data:
        correction = story.data["status_correction"]
        if isinstance(correction, dict):
            prev_status = correction.get("previous_status", "")
            if prev_status and story.status:
                history.append((prev_status, story.status))

    return history


def validate_story_transitions(story: Story, result: ValidationResult) -> None:
    """
    Validate status transitions for a single story.

    Args:
        story: Story to validate
        result: ValidationResult to populate with issues
    """
    result.story_count += 1

    # Validate current status is valid
    if story.status and not is_valid_status(story.status):
        result.add_error(
            f"Story '{story.id}' has invalid status: '{story.status}'",
            {"story_id": story.id, "invalid_status": story.status},
        )
        return

    # Validate status history transitions
    history = get_story_status_history(story)
    for old_status, new_status in history:
        result.transition_count += 1
        is_valid, reason = is_valid_transition(old_status, new_status)
        if not is_valid:
            result.add_warning(
                f"Story '{story.id}' has invalid transition: {reason}",
                {
                    "story_id": story.id,
                    "from_status": old_status,
                    "to_status": new_status,
                    "reason": reason,
                },
            )


def calculate_expected_epic_status(stories: list[Story]) -> str | None:
    """
    Calculate the expected epic status based on child stories.

    The expected status is determined by the highest precedence status
    among all non-cancelled/non-deprecated stories.

    Args:
        stories: List of child stories

    Returns:
        Expected epic status or None if no valid stories
    """
    if not stories:
        return None

    # Filter out deprecated stories
    active_stories = [s for s in stories if s.status != "deprecated"]

    if not active_stories:
        return "deprecated"

    # Get the highest precedence status
    max_precedence = -1
    expected_status = "backlog"

    for story in active_stories:
        precedence = STATUS_PRECEDENCE.get(story.status, 0)
        if precedence > max_precedence:
            max_precedence = precedence
            expected_status = story.status

    # Special case: if all stories are completed/merged/archived/cancelled
    completed_count = sum(
        1
        for s in active_stories
        if s.status in {"completed", "merged", "archived", "cancelled"}
    )

    if completed_count == len(active_stories):
        # If any story is merged, epic should be merged
        if any(s.status == "merged" for s in active_stories):
            return "merged"
        # If any story is completed, epic should be completed
        if any(s.status == "completed" for s in active_stories):
            return "completed"
        # Otherwise archived or cancelled
        if any(s.status == "archived" for s in active_stories):
            return "archived"
        return "cancelled"

    # If any story is in_progress, epic should be in_progress
    if any(s.status == "in_progress" for s in active_stories):
        return "in_progress"

    return expected_status


def validate_epic_consistency(
    epic: Epic, stories: list[Story], result: ValidationResult
) -> None:
    """
    Validate that an epic's status is consistent with its child stories.

    Args:
        epic: Epic to validate
        stories: List of all stories (to find child stories)
        result: ValidationResult to populate with issues
    """
    result.epic_count += 1

    # Validate epic status is valid
    if epic.status and not is_valid_status(epic.status):
        result.add_error(
            f"Epic '{epic.id}' has invalid status: '{epic.status}'",
            {"epic_id": epic.id, "invalid_status": epic.status},
        )
        return

    # Find child stories for this epic
    child_stories = [
        s for s in stories if s.epic_id == epic.id or s.id in epic.story_ids
    ]

    if not child_stories:
        # No child stories found - this might be OK for some epics
        return

    # Check each child story's status compatibility
    epic_compatible = EPIC_STORY_COMPATIBILITY.get(epic.status, set())

    for story in child_stories:
        if story.status not in epic_compatible and story.status != "deprecated":
            result.add_warning(
                f"Story '{story.id}' status '{story.status}' may be incompatible "
                f"with epic '{epic.id}' status '{epic.status}'",
                {
                    "epic_id": epic.id,
                    "epic_status": epic.status,
                    "story_id": story.id,
                    "story_status": story.status,
                    "compatible_statuses": list(epic_compatible),
                },
            )

    # Check if epic status matches calculated expected status
    expected_status = calculate_expected_epic_status(child_stories)
    if expected_status and expected_status != epic.status:
        # Only flag as warning - epic status might be intentionally different
        result.add_warning(
            f"Epic '{epic.id}' status '{epic.status}' differs from expected '{expected_status}' "
            f"based on {len(child_stories)} child stories",
            {
                "epic_id": epic.id,
                "current_status": epic.status,
                "expected_status": expected_status,
                "child_stories": [s.id for s in child_stories],
                "child_statuses": [s.status for s in child_stories],
            },
        )


def validate_all_transitions(data: dict[str, Any], result: ValidationResult) -> None:
    """
    Validate all status transitions in the workflow data.

    Args:
        data: Workflow status YAML data
        result: ValidationResult to populate
    """
    # Extract stories and epics
    stories = extract_stories(data)
    epics = extract_epics(data)

    # Create a lookup for stories by ID
    story_lookup = {s.id: s for s in stories}

    # Validate story transitions
    for story in stories:
        validate_story_transitions(story, result)

    # Validate epic consistency
    for epic in epics:
        validate_epic_consistency(epic, stories, result)

    # Additional validation: Check for orphaned stories (referenced by epic but not found)
    for epic in epics:
        for story_id in epic.story_ids:
            if story_id not in story_lookup:
                result.add_warning(
                    f"Epic '{epic.id}' references story '{story_id}' which was not found",
                    {"epic_id": epic.id, "missing_story_id": story_id},
                )


def main() -> int:
    """
    Main entry point for the workflow transition validator.

    Returns:
        Exit code (0 for success, 1 for validation errors, 2 for file/YAML errors)
    """
    parser = argparse.ArgumentParser(
        description="Validate workflow status transitions and epic-story consistency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default validation (warn on issues)
  python3 %(prog)s

  # Strict validation (fail on any issue)
  python3 %(prog)s --strict

  # Verbose output with JSON format
  python3 %(prog)s --verbose --json

  # Validate custom file
  python3 %(prog)s --file path/to/workflow-status.yaml
        """,
    )

    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=DEFAULT_WORKFLOW_FILE,
        help=f"Path to workflow status file (default: {DEFAULT_WORKFLOW_FILE})",
    )

    parser.add_argument(
        "--strict",
        "-s",
        action="store_true",
        help="Fail on any invalid transition (default: warn only)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )

    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output results in JSON format",
    )

    args = parser.parse_args()

    # Initialize result
    result = ValidationResult()

    # Load workflow file
    data, error = load_yaml_file(args.file)
    if error:
        if args.json:
            print(json.dumps({"valid": False, "error": error}, indent=2))
        else:
            print(f"❌ Error: {error}", file=sys.stderr)
        return 2

    if data is None:
        error_msg = f"Empty or invalid YAML file: {args.file}"
        if args.json:
            print(json.dumps({"valid": False, "error": error_msg}, indent=2))
        else:
            print(f"❌ Error: {error_msg}", file=sys.stderr)
        return 2

    # Perform validation
    validate_all_transitions(data, result)

    # Output results
    if args.json:
        result.print_json()
    else:
        result.print_text(verbose=args.verbose)

    # Determine exit code
    if result.get_errors():
        # Errors always cause exit code 1
        if not args.json:
            print(
                f"\n❌ Validation FAILED with {len(result.get_errors())} error(s)",
                file=sys.stderr,
            )
        return 1

    if result.get_warnings():
        if args.strict:
            # In strict mode, warnings become errors
            if not args.json:
                print(
                    f"\n❌ Validation FAILED (strict mode): {len(result.get_warnings())} warning(s) treated as errors",
                    file=sys.stderr,
                )
            return 1
        else:
            # Non-strict mode: warnings don't fail
            if not args.json:
                print(
                    f"\n⚠️  Validation completed with {len(result.get_warnings())} warning(s)"
                )
                print("✅ Pass (warnings only - use --strict to fail on warnings)")
            return 0

    # No issues
    if not args.json:
        print("\n✅ All validations passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
