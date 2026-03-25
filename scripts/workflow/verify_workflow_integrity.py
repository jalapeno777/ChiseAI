#!/usr/bin/env python3
"""
Verify Workflow Integrity

Ensures the main workflow status file remains valid after archival operations.

Usage:
    python verify_workflow_integrity.py [--file PATH]

Checks:
    - YAML syntax valid
    - All required fields present
    - Epic-story relationships intact
    - No orphaned references
    - Status values are valid

Exit Codes:
    0 - Workflow integrity verified
    1 - Integrity violations found
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify_workflow")


WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
STORY_SECTIONS = ["stories", "completed", "backlog", "launch_stories"]
VALID_STATUSES = [
    "archived",
    "deprecated",
    "planned",
    "in_progress",
    "completed",
    "merged",
    "blocked",
    "cancelled",
    "deferred",
    "validated",
]
REQUIRED_LEAN_FIELDS = ["id", "status", "title"]
LEGACY_VIEW_SECTIONS = {"completed", "backlog", "launch_stories"}


def load_workflow(path: Path) -> dict:
    """Load and parse workflow YAML."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def check_yaml_syntax(path: Path) -> tuple[bool, str]:
    """Verify YAML syntax is valid."""
    try:
        with open(path) as f:
            yaml.safe_load(f)
        return True, "YAML syntax valid"
    except yaml.YAMLError as e:
        return False, f"YAML syntax error: {e}"


def check_required_fields(workflow_data: dict) -> tuple[bool, list[str]]:
    """Verify all stories have required fields."""
    errors = []

    for section in STORY_SECTIONS:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id", "UNKNOWN")

            for field in REQUIRED_LEAN_FIELDS:
                if field not in story:
                    errors.append(
                        f"{section}.{story_id}: Missing required field '{field}'"
                    )

    return len(errors) == 0, errors


def check_epic_integrity(workflow_data: dict) -> tuple[bool, list[str]]:
    """Verify epic-story relationships are intact."""
    errors = []

    epics = workflow_data.get("epics", [])
    epic_ids = {e.get("id") for e in epics if isinstance(e, dict)}

    # Check all stories reference valid epics
    for section in STORY_SECTIONS:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id", "UNKNOWN")
            epic_id = story.get("epic_id")

            if epic_id and epic_id not in epic_ids:
                errors.append(
                    f"{section}.{story_id}: References unknown epic '{epic_id}'"
                )

    # Check all epic story_ids exist
    for epic in epics:
        if not isinstance(epic, dict):
            continue

        epic_id = epic.get("id", "UNKNOWN")
        story_ids = epic.get("story_ids", [])

        # Collect all story IDs
        all_story_ids = set()
        for section in STORY_SECTIONS:
            for story in workflow_data.get(section, []):
                if isinstance(story, dict) and story.get("id"):
                    all_story_ids.add(story["id"])

        for story_id in story_ids:
            if story_id not in all_story_ids:
                errors.append(f"epic.{epic_id}: References unknown story '{story_id}'")

    return len(errors) == 0, errors


def check_status_values(workflow_data: dict) -> tuple[bool, list[str]]:
    """Verify all status values are valid."""
    errors = []

    for section in STORY_SECTIONS:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id", "UNKNOWN")
            status = story.get("status", "").lower()

            if status and status not in VALID_STATUSES:
                errors.append(f"{section}.{story_id}: Invalid status '{status}'")

    return len(errors) == 0, errors


def check_no_duplicates(workflow_data: dict) -> tuple[bool, list[str]]:
    """Verify no duplicate story IDs."""
    errors = []
    story_ids = {}

    for section in STORY_SECTIONS:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id")
            if story_id:
                if story_id in story_ids:
                    prior_section = story_ids[story_id]
                    mirrored_sections = {section, prior_section}
                    if mirrored_sections == {"stories", "completed"}:
                        continue
                    if mirrored_sections == {"stories", "backlog"}:
                        continue
                    if mirrored_sections == {"stories", "launch_stories"}:
                        continue
                    if mirrored_sections <= LEGACY_VIEW_SECTIONS:
                        continue
                    errors.append(
                        f"Duplicate story ID '{story_id}' in {section} and {prior_section}"
                    )
                else:
                    story_ids[story_id] = section

    return len(errors) == 0, errors


def verify_workflow(file_path: Path) -> dict:
    """Run all workflow integrity checks."""
    results = {"checks_passed": 0, "checks_failed": 0, "total_errors": 0, "details": {}}

    # Check YAML syntax
    passed, message = check_yaml_syntax(file_path)
    results["details"]["yaml_syntax"] = {"passed": passed, "message": message}
    if passed:
        results["checks_passed"] += 1
    else:
        results["checks_failed"] += 1
        results["total_errors"] += 1
        return results  # Can't proceed if YAML is invalid

    # Load workflow data
    workflow_data = load_workflow(file_path)

    # Run all checks
    checks = [
        ("required_fields", check_required_fields),
        ("epic_integrity", check_epic_integrity),
        ("status_values", check_status_values),
        ("no_duplicates", check_no_duplicates),
    ]

    for check_name, check_func in checks:
        passed, errors = check_func(workflow_data)
        results["details"][check_name] = {"passed": passed, "errors": errors}

        if passed:
            results["checks_passed"] += 1
        else:
            results["checks_failed"] += 1
            results["total_errors"] += len(errors)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Verify workflow status file integrity"
    )
    parser.add_argument(
        "--file", type=Path, default=WORKFLOW_FILE, help="Path to workflow status file"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Workflow Integrity Verification")
    print("=" * 70)
    print(f"File: {args.file}")
    print("=" * 70)

    if not args.file.exists():
        logger.error(f"File not found: {args.file}")
        sys.exit(1)

    results = verify_workflow(args.file)

    print("\nCheck Results:")
    for check_name, check_result in results["details"].items():
        status = "✓" if check_result["passed"] else "✗"
        print(f"  {status} {check_name}")

        if not check_result["passed"]:
            if isinstance(check_result.get("errors"), list):
                for error in check_result["errors"][:5]:  # Show first 5
                    print(f"      - {error}")
                if len(check_result["errors"]) > 5:
                    print(f"      ... and {len(check_result['errors']) - 5} more")
            else:
                print(f"      - {check_result.get('message', 'Unknown error')}")

    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Checks passed: {results['checks_passed']}")
    print(f"  Checks failed: {results['checks_failed']}")
    print(f"  Total errors: {results['total_errors']}")
    print("=" * 70)

    if results["checks_failed"] > 0:
        print("\n✗ Workflow integrity check failed")
        sys.exit(1)

    print("\n✓ Workflow integrity verified")
    sys.exit(0)


if __name__ == "__main__":
    main()
