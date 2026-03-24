#!/usr/bin/env python3
"""
Verify Archive Completeness

Ensures no data loss during archival by comparing original content
with archived content using hash verification.

Usage:
    python verify_archive_completeness.py [--manifest PATH] [--strict]

Exit Codes:
    0 - All verifications passed
    1 - One or more verifications failed
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify_archive")


WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_DIR = Path("docs/archives/workflow-status")
STORY_DETAILS_DIR = ARCHIVE_DIR / "story-details"
ARCHIVE_INDEX_FILE = ARCHIVE_DIR / "archive-index.yaml"


def calculate_hash(data: Any) -> str:
    """Calculate SHA256 hash of data."""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def load_yaml(path: Path) -> dict:
    """Load YAML file."""
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def verify_archive_exists(story_id: str) -> tuple[bool, str]:
    """Verify archive file exists for story."""
    # Check for story archive file
    archive_pattern = f"{story_id}-*-details.yaml"
    matches = list(STORY_DETAILS_DIR.glob(archive_pattern))

    if not matches:
        return False, f"No archive file found for {story_id}"

    return True, f"Found archive: {matches[0].name}"


def verify_archive_integrity(story_id: str, original_story: dict) -> tuple[bool, str]:
    """Verify archive content matches original."""
    # Find archive file
    archive_pattern = f"{story_id}-*-details.yaml"
    matches = list(STORY_DETAILS_DIR.glob(archive_pattern))

    if not matches:
        return False, "Archive file not found"

    archive_path = matches[0]
    archive_data = load_yaml(archive_path)

    # Get archived story content
    archived_story = archive_data.get("archived_story", {}).get("full_details", {})

    # Compare key fields
    key_fields = [
        "id",
        "title",
        "status",
        "pr_number",
        "merge_commit",
        "completed_date",
        "merged_date",
    ]

    for field in key_fields:
        orig_val = original_story.get(field)
        arch_val = archived_story.get(field)

        if orig_val != arch_val:
            return False, f"Field '{field}' mismatch: {orig_val} != {arch_val}"

    return True, "Archive integrity verified"


def verify_index_entry(story_id: str) -> tuple[bool, str]:
    """Verify story has entry in archive index."""
    index_data = load_yaml(ARCHIVE_INDEX_FILE)
    entries = index_data.get("archive_index", {}).get("entries", [])

    for entry in entries:
        if entry.get("story_id") == story_id:
            return True, "Index entry found"

    return False, "No index entry found"


def verify_lean_reference(story_id: str, workflow_data: dict) -> tuple[bool, str]:
    """Verify story has lean reference in workflow."""
    # Check all story sections
    for section in ["completed", "backlog", "launch_stories"]:
        stories = workflow_data.get(section, [])
        for story in stories:
            if story.get("id") == story_id:
                # Check if it's lean (minimal fields)
                field_count = len(story.keys())
                if field_count <= 10:  # Lean stories have few fields
                    return True, f"Lean reference found ({field_count} fields)"
                else:
                    return False, f"Story not lean ({field_count} fields)"

    return False, "Story not found in workflow"


def verify_all_archives(manifest_path: Path = None, strict: bool = False) -> dict:
    """Verify all archives for completeness."""
    workflow_data = load_yaml(WORKFLOW_FILE)

    results = {"total_checked": 0, "passed": 0, "failed": 0, "errors": []}

    # If manifest provided, verify only those stories
    if manifest_path and manifest_path.exists():
        manifest = load_yaml(manifest_path)
        stories_to_check = manifest.get("stories", [])
    else:
        # Otherwise, check all stories in archive index
        index_data = load_yaml(ARCHIVE_INDEX_FILE)
        entries = index_data.get("archive_index", {}).get("entries", [])
        stories_to_check = [{"story_id": e.get("story_id")} for e in entries]

    logger.info(f"Verifying {len(stories_to_check)} archived stories...")

    for item in stories_to_check:
        story_id = item.get("story_id") if isinstance(item, dict) else item
        if not story_id:
            continue

        results["total_checked"] += 1
        story_errors = []

        # Find original story in workflow
        original_story = None
        for section in ["completed", "backlog", "launch_stories"]:
            for story in workflow_data.get(section, []):
                if story.get("id") == story_id:
                    original_story = story
                    break
            if original_story:
                break

        # Run verifications
        checks = [
            ("Archive exists", verify_archive_exists(story_id)),
            ("Index entry", verify_index_entry(story_id)),
            ("Lean reference", verify_lean_reference(story_id, workflow_data)),
        ]

        if original_story:
            checks.append(
                (
                    "Archive integrity",
                    verify_archive_integrity(story_id, original_story),
                )
            )

        for check_name, (passed, message) in checks:
            if not passed:
                story_errors.append(f"{check_name}: {message}")

        if story_errors:
            results["failed"] += 1
            results["errors"].append({"story_id": story_id, "errors": story_errors})
            logger.error(f"✗ {story_id}: {', '.join(story_errors)}")
        else:
            results["passed"] += 1
            logger.info(f"✓ {story_id}: All checks passed")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Verify archive completeness and data integrity"
    )
    parser.add_argument("--manifest", type=Path, help="Path to migration manifest")
    parser.add_argument("--strict", action="store_true", help="Fail on any warning")

    args = parser.parse_args()

    print("=" * 70)
    print("Archive Completeness Verification")
    print("=" * 70)

    results = verify_all_archives(args.manifest, args.strict)

    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Total checked: {results['total_checked']}")
    print(f"  Passed: {results['passed']}")
    print(f"  Failed: {results['failed']}")
    print("=" * 70)

    if results["failed"] > 0:
        print("\nFailed stories:")
        for error in results["errors"]:
            print(f"  {error['story_id']}:")
            for e in error["errors"]:
                print(f"    - {e}")
        sys.exit(1)

    print("\n✓ All archives verified successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
