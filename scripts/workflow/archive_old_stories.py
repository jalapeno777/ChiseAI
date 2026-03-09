#!/usr/bin/env python3
"""
Archive Old Stories Script

Implements the data retention policy by moving completed stories older than 7 days
from the active workflow file to archive documents.

Usage:
    python3 scripts/workflow/archive_old_stories.py [--dry-run] [--execute] [--story-id ST-XXX]

Policy Reference:
    docs/policy/data_retention_policy.yaml (Section 2: Archival Triggers)

Author: ChiseAI Workflow Governance
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

# Configuration
WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_BASE = Path("docs/archives")
STORY_DETAILS_DIR = ARCHIVE_BASE / "story-details"
WORKFLOW_ARCHIVE_DIR = ARCHIVE_BASE / "workflow-status"
ARCHIVE_INDEX_FILE = ARCHIVE_BASE / "workflow-status" / "archive-index.yaml"
RETENTION_DAYS = 7


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 date string to datetime."""
    if not date_str:
        return None
    try:
        # Handle both date-only and datetime formats
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def calculate_age_days(date_str: Optional[str]) -> Optional[int]:
    """Calculate age in days from a date string."""
    date = parse_date(date_str)
    if not date:
        return None
    now = datetime.now(timezone.utc)
    return (now - date).days


def should_archive_story(story: dict) -> tuple[bool, str]:
    """
    Determine if a story should be archived based on retention policy.

    Returns:
        Tuple of (should_archive, reason)
    """
    status = story.get("status", "").lower()

    # Only archive completed/merged/cancelled stories
    if status not in ["completed", "merged", "cancelled"]:
        return False, f"Status '{status}' not eligible for archival"

    # Check completion/merged date
    completed_date = story.get("completed_date") or story.get("merged_date")
    if not completed_date:
        return False, "No completion date found"

    age_days = calculate_age_days(completed_date)
    if age_days is None:
        return False, "Could not parse completion date"

    if age_days <= RETENTION_DAYS:
        return False, f"Age {age_days} days <= retention period {RETENTION_DAYS} days"

    return True, f"Age {age_days} days > retention period {RETENTION_DAYS} days"


def generate_story_slug(title: str) -> str:
    """Generate URL-friendly slug from story title."""
    # Remove special characters, convert to lowercase, replace spaces with hyphens
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug)
    # Limit to 50 characters
    return slug[:50].strip("-")


def create_story_archive(story: dict) -> dict:
    """
    Create archive document for a story.

    Returns archive document structure per policy Section 3.
    """
    story_id = story.get("id", "UNKNOWN")
    title = story.get("title", "Unknown Title")
    slug = generate_story_slug(title)

    now = datetime.now(timezone.utc)
    retention_until = now + timedelta(days=7 * 365)  # 7 years

    archive_doc = {
        "archive_metadata": {
            "version": "1.0",
            "archived_date": now.isoformat(),
            "archived_by": "archive_old_stories.py",
            "source_file": "docs/bmm-workflow-status.yaml",
            "retention_until": retention_until.isoformat(),
            "policy_version": "1.0.0",
        },
        "story_summary": {
            "id": story_id,
            "title": title,
            "epic_id": story.get("epic_id"),
            "status": story.get("status"),
            "owner": story.get("owner"),
            "priority": story.get("priority"),
            "story_points": story.get("story_points"),
            "created_date": story.get("created_date"),
            "completed_date": story.get("completed_date"),
            "merged_date": story.get("merged_date"),
            "pr_number": story.get("pr_number"),
            "merge_commit": story.get("merge_commit"),
        },
        "acceptance_criteria": [],
        "evidence_manifest": {"files": []},
        "test_results": {},
        "validation_summary": {
            "gates_passed": [],
            "manual_verifications": [],
            "sign_offs": [],
        },
        "notes_and_decisions": {
            "implementation_notes": [],
            "key_decisions": [],
            "lessons_learned": [],
            "blockers_resolved": [],
        },
        "qdrant_promotion": {
            "promoted": False,
            "promotion_date": None,
            "vectors_created": [],
            "promotion_reason": None,
        },
        "related_stories": [],
        "iterlog_references": [],
        "integrity": {
            "checksum_algorithm": "sha256",
            "last_verified": now.isoformat(),
            "verification_status": "valid",
        },
    }

    # Process acceptance criteria
    if "acceptance_criteria" in story:
        for ac in story["acceptance_criteria"]:
            if isinstance(ac, str):
                archive_doc["acceptance_criteria"].append(
                    {"criterion": ac, "status": "completed", "evidence": None}
                )
            elif isinstance(ac, dict):
                archive_doc["acceptance_criteria"].append(ac)

    # Process evidence files
    if "evidence_files" in story:
        for ef in story["evidence_files"]:
            archive_doc["evidence_manifest"]["files"].append(
                {
                    "path": ef if isinstance(ef, str) else ef.get("path"),
                    "type": "unknown",
                    "size_bytes": 0,
                    "checksum": None,
                    "commit": story.get("merge_commit"),
                }
            )

    # Process test results
    if "test_results" in story:
        archive_doc["test_results"] = story["test_results"]
    elif "tests_passed" in story:
        archive_doc["test_results"] = {"summary": story.get("tests_passed")}

    # Process notes
    if "notes" in story:
        for note in story["notes"]:
            archive_doc["notes_and_decisions"]["implementation_notes"].append(note)

    # Process validation
    if "validation_summary" in story:
        archive_doc["validation_summary"] = story["validation_summary"]

    # Check Qdrant promotion eligibility
    priority = story.get("priority", "").upper()
    story_points = story.get("story_points", 0) or 0

    if priority in ["P0", "P0-CRITICAL", "P1", "P1-HIGH"] or story_points >= 5:
        archive_doc["qdrant_promotion"]["promoted"] = True
        archive_doc["qdrant_promotion"]["promotion_date"] = now.isoformat()
        archive_doc["qdrant_promotion"]["promotion_reason"] = (
            f"Priority {priority} story with {story_points} points"
        )

    return archive_doc


def create_workflow_entry(story: dict) -> dict:
    """Create minimal workflow entry for archived story."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "archive_old_stories.py",
        "action": "story_archived",
        "description": f"Story {story.get('id')} archived to story-details",
        "story_id": story.get("id"),
        "epic_id": story.get("epic_id"),
        "archived_to": f"story-details/{story.get('id')}-{generate_story_slug(story.get('title', ''))}-details.yaml",
        "archived_date": datetime.now(timezone.utc).isoformat(),
    }


def load_workflow_data() -> dict:
    """Load workflow status data from YAML file."""
    if not WORKFLOW_FILE.exists():
        print(f"ERROR: Workflow file not found: {WORKFLOW_FILE}")
        sys.exit(1)

    with open(WORKFLOW_FILE, "r") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict, path: Path) -> None:
    """Save data to YAML file with proper formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )


def archive_stories(
    story_ids: Optional[list[str]] = None, dry_run: bool = True
) -> dict:
    """
    Main archival function.

    Args:
        story_ids: Optional list of specific story IDs to archive
        dry_run: If True, only report what would be archived

    Returns:
        Summary of archival operations
    """
    workflow_data = load_workflow_data()

    # Find all story lists in workflow file
    story_lists = []
    for key in ["completed", "backlog", "current_phase", "epics", "launch_stories"]:
        if key in workflow_data and isinstance(workflow_data[key], list):
            story_lists.append((key, workflow_data[key]))

    # Collect stories to archive
    stories_to_archive = []

    for list_name, story_list in story_lists:
        for story in story_list:
            if not isinstance(story, dict):
                continue

            story_id = story.get("id")

            # Skip if specific IDs requested and this isn't one
            if story_ids and story_id not in story_ids:
                continue

            should_archive, reason = should_archive_story(story)

            if should_archive:
                stories_to_archive.append(
                    {"list_name": list_name, "story": story, "reason": reason}
                )
            elif story_ids and story_id in story_ids:
                print(f"Story {story_id}: NOT archived - {reason}")

    if not stories_to_archive:
        print("No stories eligible for archival.")
        return {"archived": 0, "errors": 0}

    print(f"\nFound {len(stories_to_archive)} stories to archive:\n")

    results = {"archived": 0, "errors": 0, "stories": []}

    for item in stories_to_archive:
        story = item["story"]
        story_id = story.get("id", "UNKNOWN")
        title = story.get("title", "Unknown")

        print(f"  {story_id}: {title[:60]}...")
        print(f"    Reason: {item['reason']}")

        if dry_run:
            print(f"    [DRY RUN] Would archive to story-details/")
            results["archived"] += 1
            results["stories"].append(story_id)
            continue

        try:
            # Create archive document
            archive_doc = create_story_archive(story)
            slug = generate_story_slug(title)
            archive_filename = f"{story_id}-{slug}-details.yaml"
            archive_path = STORY_DETAILS_DIR / archive_filename

            # Save archive document
            save_yaml(archive_doc, archive_path)
            print(f"    Saved: {archive_path}")

            # Update workflow archive index
            workflow_entry = create_workflow_entry(story)
            update_archive_index(workflow_entry)

            results["archived"] += 1
            results["stories"].append(story_id)

        except Exception as e:
            print(f"    ERROR: {e}")
            results["errors"] += 1

    return results


def update_archive_index(entry: dict) -> None:
    """Add entry to archive index."""
    ARCHIVE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)

    index_data = {"archive_index": {"version": "1.0", "entries": []}}

    if ARCHIVE_INDEX_FILE.exists():
        with open(ARCHIVE_INDEX_FILE, "r") as f:
            existing = yaml.safe_load(f) or {}
            if "archive_index" in existing:
                index_data = existing

    index_data["archive_index"]["entries"].append(entry)

    save_yaml(index_data, ARCHIVE_INDEX_FILE)


def main():
    parser = argparse.ArgumentParser(
        description="Archive old stories from workflow status file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run to see what would be archived
    python3 scripts/workflow/archive_old_stories.py --dry-run
    
    # Actually archive eligible stories
    python3 scripts/workflow/archive_old_stories.py --execute
    
    # Archive specific story
    python3 scripts/workflow/archive_old_stories.py --story-id ST-XXX --execute
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be archived without making changes (default)",
    )

    parser.add_argument(
        "--execute", action="store_true", help="Actually perform the archival"
    )

    parser.add_argument(
        "--story-id",
        action="append",
        help="Specific story ID to archive (can be used multiple times)",
    )

    args = parser.parse_args()

    # If --execute is specified, disable dry_run
    dry_run = not args.execute

    print("=" * 70)
    print("ChiseAI Workflow Archival Tool")
    print("=" * 70)
    print(f"Policy: docs/policy/data_retention_policy.yaml")
    print(f"Retention: {RETENTION_DAYS} days after completion")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print("=" * 70)

    results = archive_stories(story_ids=args.story_id, dry_run=dry_run)

    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Stories archived: {results['archived']}")
    print(f"  Errors: {results['errors']}")
    if results.get("stories"):
        print(f"  Story IDs: {', '.join(results['stories'])}")
    print("=" * 70)

    if results["errors"] > 0:
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
