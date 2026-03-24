#!/usr/bin/env python3
"""
Restore From Archive

Emergency restoration of archived story details back to workflow status.

Usage:
    python restore_from_archive.py --story-id ST-XXX [--dry-run]
    python restore_from_archive.py --all [--dry-run]

This script is part of the rollback plan for the archival system.
"""

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("restore_archive")


WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_DIR = Path("docs/archives/workflow-status")
STORY_DETAILS_DIR = ARCHIVE_DIR / "story-details"


def load_yaml(path: Path) -> dict:
    """Load YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict, path: Path):
    """Save data to YAML file."""
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def find_archive_file(story_id: str) -> Path:
    """Find archive file for story."""
    pattern = f"{story_id}-*-details.yaml"
    matches = list(STORY_DETAILS_DIR.glob(pattern))

    if not matches:
        return None

    # Return most recent if multiple versions exist
    return sorted(matches)[-1]


def restore_story(
    story_id: str, workflow_data: dict, dry_run: bool = False
) -> tuple[bool, str]:
    """Restore a single story from archive."""
    # Find archive file
    archive_path = find_archive_file(story_id)
    if not archive_path:
        return False, f"Archive file not found for {story_id}"

    # Load archive
    archive_data = load_yaml(archive_path)
    archived_story = archive_data.get("archived_story", {})
    full_details = archived_story.get("full_details", {})

    if not full_details:
        return False, f"No full_details found in archive for {story_id}"

    # Find story in workflow
    found = False
    for section in ["completed", "backlog", "launch_stories"]:
        stories = workflow_data.get(section, [])
        for i, story in enumerate(stories):
            if story.get("id") == story_id:
                found = True

                if dry_run:
                    return True, f"Would restore {story_id} in section '{section}'"

                # Replace with full details
                workflow_data[section][i] = full_details
                logger.info(f"Restored {story_id} in section '{section}'")
                break
        if found:
            break

    if not found:
        # Story not in workflow, add to completed
        if dry_run:
            return True, f"Would add {story_id} to completed section"

        if "completed" not in workflow_data:
            workflow_data["completed"] = []
        workflow_data["completed"].append(full_details)
        logger.info(f"Added {story_id} to completed section")

    return True, f"Restored {story_id}"


def restore_all(workflow_data: dict, dry_run: bool = False) -> dict:
    """Restore all archived stories."""
    results = {"restored": 0, "failed": 0, "errors": []}

    # Find all archive files
    archive_files = list(STORY_DETAILS_DIR.glob("*-*-details.yaml"))

    logger.info(f"Found {len(archive_files)} archive files")

    for archive_path in archive_files:
        # Extract story ID from filename
        story_id = archive_path.name.split("-")[0]

        success, message = restore_story(story_id, workflow_data, dry_run)

        if success:
            results["restored"] += 1
        else:
            results["failed"] += 1
            results["errors"].append({"story_id": story_id, "error": message})

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Restore archived stories to workflow status"
    )
    parser.add_argument("--story-id", type=str, help="Story ID to restore")
    parser.add_argument(
        "--all", action="store_true", help="Restore all archived stories"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview restoration without changes"
    )

    args = parser.parse_args()

    if not args.story_id and not args.all:
        parser.error("Must specify --story-id or --all")

    print("=" * 70)
    print("Archive Restoration Tool")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print("=" * 70)

    # Load workflow data
    workflow_data = load_yaml(WORKFLOW_FILE)

    # Create backup
    if not args.dry_run:
        backup_path = (
            WORKFLOW_FILE.parent
            / f"{WORKFLOW_FILE.name}.backup.pre-restore.{datetime.now():%Y%m%d_%H%M%S}"
        )
        shutil.copy2(WORKFLOW_FILE, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Perform restoration
    if args.story_id:
        success, message = restore_story(args.story_id, workflow_data, args.dry_run)
        results = {
            "restored": 1 if success else 0,
            "failed": 0 if success else 1,
            "errors": (
                [] if success else [{"story_id": args.story_id, "error": message}]
            ),
        }
        print(message)
    else:
        results = restore_all(workflow_data, args.dry_run)

    # Save workflow if not dry run
    if not args.dry_run and results["restored"] > 0:
        save_yaml(workflow_data, WORKFLOW_FILE)
        logger.info("Saved workflow status")

    # Summary
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Restored: {results['restored']}")
    print(f"  Failed: {results['failed']}")

    if results["errors"]:
        print("\nErrors:")
        for error in results["errors"]:
            print(f"  {error['story_id']}: {error['error']}")

    print("=" * 70)

    if results["failed"] > 0:
        sys.exit(1)

    print("\n✓ Restoration complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
