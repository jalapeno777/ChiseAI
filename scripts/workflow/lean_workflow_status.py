#!/usr/bin/env python3
"""
Lean Workflow Status

Removes archived details from the main workflow status file,
keeping only essential fields for lean reference.

Usage:
    python lean_workflow_status.py --manifest PATH [--backup] [--validate]

Safety:
    - Creates backup before modification
    - Preserves required fields
    - Validates YAML after modification
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("lean_workflow")


WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")

# Fields to preserve in lean format
LEAN_FIELDS = [
    "id",
    "status",
    "pr_number",
    "merge_commit",
    "completed_date",
    "merged_date",
    "title",
    "epic_id",
]

# Fields that can be removed
REMOVABLE_FIELDS = [
    "acceptance_criteria",
    "description",
    "notes",
    "implementation_notes",
    "test_results",
    "validation_summary",
    "rollback_plan",
    "live_validation_gates",
    "scope_globs",
    "files_changed",
    "branches",
    "commit_shas",
    "depends_on",
]


def load_yaml(path: Path) -> dict:
    """Load YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict, path: Path):
    """Save data to YAML file."""
    with open(path, "w") as f:
        yaml.dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )


def calculate_hash(data: Any) -> str:
    """Calculate hash of data for comparison."""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def is_story_lean(story: dict) -> bool:
    """Check if story is already in lean format."""
    field_count = len(story.keys())
    # Lean stories typically have 5-10 fields
    return field_count <= 10


def lean_story(story: dict) -> dict:
    """Convert story to lean format."""
    lean = {}

    for field in LEAN_FIELDS:
        if field in story:
            lean[field] = story[field]

    # Preserve any other fields that might be important
    # but aren't in the standard lean list
    for key, value in story.items():
        if key not in LEAN_FIELDS and key not in REMOVABLE_FIELDS:
            lean[key] = value

    return lean


def lean_workflow(
    workflow_data: dict, story_ids: list[str] = None
) -> tuple[dict, dict]:
    """
    Lean the workflow status.

    Args:
        workflow_data: The workflow data to lean
        story_ids: Optional list of specific story IDs to lean

    Returns:
        Tuple of (leaned_data, statistics)
    """
    stats = {
        "stories_learned": 0,
        "stories_skipped": 0,
        "fields_removed": 0,
        "original_size": 0,
        "leaned_size": 0,
    }

    # Calculate original size
    stats["original_size"] = len(json.dumps(workflow_data))

    # Process each story section
    for section in ["completed", "backlog", "launch_stories"]:
        if section not in workflow_data:
            continue

        stories = workflow_data[section]
        for i, story in enumerate(stories):
            if not isinstance(story, dict):
                continue

            story_id = story.get("id", "UNKNOWN")

            # Skip if specific IDs requested and this isn't one
            if story_ids and story_id not in story_ids:
                continue

            # Skip if already lean
            if is_story_lean(story):
                stats["stories_skipped"] += 1
                continue

            # Count fields before
            fields_before = len(story.keys())

            # Lean the story
            leaned_story = lean_story(story)
            stories[i] = leaned_story

            # Update stats
            fields_after = len(leaned_story.keys())
            stats["fields_removed"] += fields_before - fields_after
            stats["stories_learned"] += 1

            logger.info(f"Leaned {story_id}: {fields_before} -> {fields_after} fields")

    # Calculate leaned size
    stats["leaned_size"] = len(json.dumps(workflow_data))

    return workflow_data, stats


def validate_workflow(workflow_data: dict) -> tuple[bool, list[str]]:
    """Validate the leaned workflow data."""
    errors = []

    # Check YAML can be serialized
    try:
        yaml.dump(workflow_data, default_flow_style=False)
    except Exception as e:
        errors.append(f"YAML serialization failed: {e}")
        return False, errors

    # Check all stories have required fields
    for section in ["completed", "backlog", "launch_stories"]:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id", "UNKNOWN")

            for field in ["id", "status", "title"]:
                if field not in story:
                    errors.append(
                        f"{section}.{story_id}: Missing required field '{field}'"
                    )

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(
        description="Lean workflow status by removing archived details"
    )
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Path to migration manifest"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup before modification",
    )
    parser.add_argument(
        "--no-backup", dest="backup", action="store_false", help="Skip backup creation"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate after modification",
    )
    parser.add_argument(
        "--no-validate", dest="validate", action="store_false", help="Skip validation"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without saving"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Workflow Status Leaning Tool")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print("=" * 70)

    # Load manifest
    if not args.manifest.exists():
        logger.error(f"Manifest not found: {args.manifest}")
        sys.exit(1)

    manifest = load_yaml(args.manifest)
    story_ids = [s.get("story_id") for s in manifest.get("stories", [])]

    logger.info(f"Loaded manifest with {len(story_ids)} stories to lean")

    # Load workflow data
    workflow_data = load_yaml(WORKFLOW_FILE)

    # Create backup
    if args.backup and not args.dry_run:
        backup_path = (
            WORKFLOW_FILE.parent
            / f"{WORKFLOW_FILE.name}.backup.lean.{datetime.now():%Y%m%d_%H%M%S}"
        )
        shutil.copy2(WORKFLOW_FILE, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Lean workflow
    leaned_data, stats = lean_workflow(workflow_data, story_ids)

    # Validate
    if args.validate:
        valid, errors = validate_workflow(leaned_data)
        if not valid:
            logger.error("Validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            sys.exit(1)
        logger.info("Validation passed")

    # Save if not dry run
    if not args.dry_run:
        save_yaml(leaned_data, WORKFLOW_FILE)
        logger.info(f"Saved leaned workflow to {WORKFLOW_FILE}")

    # Summary
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Stories leaned: {stats['stories_learned']}")
    print(f"  Stories skipped: {stats['stories_skipped']}")
    print(f"  Fields removed: {stats['fields_removed']}")
    print(f"  Original size: {stats['original_size']:,} bytes")
    print(f"  Leaned size: {stats['leaned_size']:,} bytes")
    if stats["original_size"] > 0:
        reduction = (1 - stats["leaned_size"] / stats["original_size"]) * 100
        print(f"  Size reduction: {reduction:.1f}%")
    print("=" * 70)

    print("\n✓ Leaning complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
