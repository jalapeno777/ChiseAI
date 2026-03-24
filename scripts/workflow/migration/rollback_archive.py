#!/usr/bin/env python3
"""
Workflow Status Archive Rollback Script
Story: ST-WORKFLOW-ARCHIVAL-001

Restores archived stories back to workflow-status.yaml.
This is a safety mechanism for the archival migration.

Usage:
    python scripts/workflow/migration/rollback_archive.py --archive-ref ARCH-20260309-...
    python scripts/workflow/migration/rollback_archive.py --story-id ST-LAUNCH-001
    python scripts/workflow/migration/rollback_archive.py --dry-run --archive-ref ARCH-...
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

import yaml

ARCHIVE_ENTRIES_DIR = Path("docs/archives/workflow-status/entries")
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")


def load_archive_entry(archive_ref: str) -> dict | None:
    """Load archive entry by reference."""
    filepath = ARCHIVE_ENTRIES_DIR / f"{archive_ref}.yaml"
    if not filepath.exists():
        return None

    with open(filepath) as f:
        return yaml.safe_load(f)


def load_workflow_status() -> dict:
    """Load workflow-status.yaml."""
    with open(WORKFLOW_STATUS_PATH) as f:
        return yaml.safe_load(f)


def save_workflow_status(data: dict, dry_run: bool = False):
    """Save workflow-status.yaml."""
    if not dry_run:
        with open(WORKFLOW_STATUS_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def find_archive_by_story_id(story_id: str) -> dict | None:
    """Find archive entry by story ID."""
    if not ARCHIVE_ENTRIES_DIR.exists():
        return None

    for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
        with open(archive_file) as f:
            archive_entry = yaml.safe_load(f)

        if archive_entry.get("original_story_id") == story_id:
            return archive_entry

    return None


def reconstruct_original_story(archive_entry: dict) -> dict:
    """Reconstruct original story from archive entry."""
    # Start with lean status
    story = dict(archive_entry.get("lean_status", {}))

    # Remove archive_ref and restore original status
    if "archive_ref" in story:
        del story["archive_ref"]

    # Restore original status (default to completed if not known)
    story["status"] = "completed"

    # Add archived fields back
    archived_fields = archive_entry.get("archived_fields", {})
    story.update(archived_fields)

    # Add completion evidence
    completion_evidence = archive_entry.get("completion_evidence", {})
    if completion_evidence:
        story.update(completion_evidence)

    # Add archival metadata for audit
    story["restored_from_archive"] = {
        "archive_ref": archive_entry.get("archive_ref"),
        "archived_at": archive_entry.get("archived_at"),
        "restored_at": "2026-03-09T00:00:00Z",  # Will be updated
    }

    return story


def rollback_story(
    workflow_data: dict, archive_entry: dict, dry_run: bool = False
) -> bool:
    """Rollback a story from archive to workflow status."""
    story_id = archive_entry.get("original_story_id")

    # Reconstruct original story
    original_story = reconstruct_original_story(archive_entry)

    # Find where to insert (completed section)
    if "completed" not in workflow_data:
        workflow_data["completed"] = []

    # Check if story already exists
    existing_idx = None
    for i, story in enumerate(workflow_data["completed"]):
        if story.get("id") == story_id:
            existing_idx = i
            break

    if existing_idx is not None:
        # Replace existing lean entry
        if not dry_run:
            workflow_data["completed"][existing_idx] = original_story
        print(f"  Replaced existing entry at index {existing_idx}")
    else:
        # Add new entry
        if not dry_run:
            workflow_data["completed"].append(original_story)
        print("  Added new entry to completed section")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Rollback archived story to workflow-status.yaml"
    )
    parser.add_argument(
        "--archive-ref",
        type=str,
        help="Rollback specific archive by reference",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        help="Rollback archive for specific story ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be rolled back without making changes",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the rollback (disables dry-run)",
    )

    args = parser.parse_args()

    # Determine if we're in dry-run mode
    dry_run = not args.execute if args.execute else args.dry_run

    print("=" * 80)
    print("WORKFLOW STATUS ARCHIVE ROLLBACK")
    print("=" * 80)
    print(
        f"Mode: {'DRY-RUN (no changes)' if dry_run else 'EXECUTE (will make changes)'}"
    )
    print("=" * 80)
    print()

    # Load archive entry
    archive_entry = None

    if args.archive_ref:
        archive_entry = load_archive_entry(args.archive_ref)
        if not archive_entry:
            print(f"ERROR: Archive {args.archive_ref} not found")
            return 1
    elif args.story_id:
        archive_entry = find_archive_by_story_id(args.story_id)
        if not archive_entry:
            print(f"ERROR: No archive found for story {args.story_id}")
            return 1
    else:
        parser.print_help()
        return 1

    # Display archive info
    archive_ref = archive_entry.get("archive_ref")
    story_id = archive_entry.get("original_story_id")
    story_title = archive_entry.get("lean_status", {}).get("title", "N/A")

    print(f"Archive: {archive_ref}")
    print(f"Story ID: {story_id}")
    print(f"Title: {story_title}")
    print(f"Archived at: {archive_entry.get('archived_at')}")
    print(f"Archive reason: {archive_entry.get('archive_reason')}")
    print()

    # Load workflow status
    print("Loading workflow status...")
    workflow_data = load_workflow_status()

    # Perform rollback
    print(f"Rolling back story {story_id}...")
    success = rollback_story(workflow_data, archive_entry, dry_run)

    if success:
        print()
        print(f"Rollback {'WOULD SUCCEED' if dry_run else 'SUCCEEDED'}")

        # Save workflow status
        if not dry_run:
            print("Saving updated workflow status...")
            save_workflow_status(workflow_data, dry_run)
            print("Done.")

        return 0
    else:
        print()
        print("Rollback FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
