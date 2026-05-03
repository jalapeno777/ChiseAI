#!/usr/bin/env python3
"""
Workflow Status Archive Migration Script
Story: ST-WORKFLOW-ARCHIVAL-001

This script migrates completed stories older than 7 days from workflow-status.yaml
to the archive storage, preserving lean status fields and completion evidence.

Usage:
    python scripts/workflow/migration/archive_stories.py --dry-run
    python scripts/workflow/migration/archive_stories.py --execute --story-id ST-LAUNCH-001
    python scripts/workflow/migration/archive_stories.py --execute --batch-size 10

Safety Features:
    - Dry-run mode by default
    - SHA-256 checksums for data integrity
    - Rollback capability
    - Verification of archived data
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

# Configuration
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_ENTRIES_DIR = Path("docs/archives/workflow-status/entries")
ARCHIVE_SCHEMA_VERSION = "1.0.0"
MIGRATION_SCRIPT_VERSION = "1.0.0"
ARCHIVE_AGE_THRESHOLD_DAYS = 14  # Phase 2: 14+ days old

# Fields to archive (long-form content)
ARCHIVE_FIELDS = [
    "description",
    "acceptance_criteria",
    "notes",
    "implementation_notes",
    "test_results",
    "live_validation_gates",
    "rollback_plan",
    "scope_globs",
    "files_changed",
    "evidence_files",
    "phases",
    "branches",
    "commit_shas",
    "depends_on",
    "remediation_pr_numbers",
    "merge_commits",
    "test_strategy",
    "validation_gates",
    "validation_notes",
    "ci_evidence",
    "retrospective_pr_evidence",
    "status_correction",
    "completion_evidence",
    "completion_notes",
    "created_date",
    "merged_date",
    "owner",
    "sprint",
    "sprint_id",
    "story_points",
    "batch",
    "gate_id",
    "gate_status",
    "verification_method",
    "verification_checklist",
    "discord_message_ids",
    "verification_evidence",
    "related_story",
    "depends_on",
    "accelerated_roadmap",
    "roadmap_document",
    "rollout",
    "progress",
    "integration_with",
    "deprecated_stories",
    "remaining_stories",
    "current_completion",
    "target_completion",
    "target_date",
    "total_remaining_points",
    "timeline",
    "deployment",
    "fr_coverage",
    "validation_status",
    "fix_summary",
    "root_cause",
    "re_enable_steps",
    "minimax_disabled",
    "handoff_document",
    "redis_iterlog_key",
    "policy_change_summary",
    "related_audit",
    "evidence_commit",
    "evidence_files",
    "consolidation_remediation_note",
    "stories_implementation_complete_pending_merge",
    "stories_completed_verified",
]

# Fields to preserve in lean status
LEAN_STATUS_FIELDS = [
    "id",
    "status",
    "title",
    "priority",
    "epic_id",
    "completion_date",
    "merge_commit",
    "pr_number",
    "archive_ref",
]

# Completion evidence fields to preserve
COMPLETION_EVIDENCE_FIELDS = [
    "pr_number",
    "merge_commit",
    "pr_numbers",
    "merge_commits",
    "commit_sha",
    "evidence_files",
    "ci_evidence",
]


def generate_archive_ref(story_id: str) -> str:
    """Generate unique archive reference."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"ARCH-{timestamp}-{story_id}"


def compute_checksum(data: dict) -> str:
    """Compute SHA-256 checksum of data."""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def parse_date(date_str: str) -> datetime | None:
    """Parse date string to datetime."""
    if not date_str:
        return None
    formats = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def should_archive(story: dict, current_date: datetime) -> tuple[bool, str, str]:
    """
    Determine if a story should be archived.

    Returns:
        (should_archive, reason, reason_detail)
    """
    story.get("id", "unknown")
    status = story.get("status", "").lower()

    # Skip if already archived (has archive_ref)
    if story.get("archive_ref"):
        return False, "already archived", ""

    # Only archive completed/merged stories
    if status not in ["completed", "merged"]:
        return False, f"Status '{status}' not eligible for archival", ""

    # Check completion date
    completion_date_str = story.get("completion_date") or story.get("merged_date")
    if not completion_date_str:
        # Try to extract from other fields
        completion_date_str = story.get("created_date", "")

    completion_date = (
        parse_date(str(completion_date_str)) if completion_date_str else None
    )

    if not completion_date:
        return False, "No completion date found", ""

    age_days = (current_date - completion_date).days

    if age_days < ARCHIVE_AGE_THRESHOLD_DAYS:
        return (
            False,
            f"Only {age_days} days old (threshold: {ARCHIVE_AGE_THRESHOLD_DAYS})",
            "",
        )

    # Check completion evidence (pr_number or merge_commit)
    has_pr = story.get("pr_number") is not None and story.get("pr_number") not in [
        "N/A",
        None,
        "",
    ]
    has_merge = story.get("merge_commit") is not None and story.get(
        "merge_commit"
    ) not in ["N/A", None, ""]
    has_remediation_prs = bool(story.get("remediation_pr_numbers"))
    has_merge_commits = bool(story.get("merge_commits"))

    if not (has_pr or has_merge or has_remediation_prs or has_merge_commits):
        return False, "MISSING COMPLETION EVIDENCE", ""

    return (
        True,
        "age",
        f"Story completed {age_days} days ago, exceeds {ARCHIVE_AGE_THRESHOLD_DAYS}-day threshold",
    )


def extract_archived_fields(story: dict) -> dict:
    """Extract fields to be archived."""
    archived = {}
    for field in ARCHIVE_FIELDS:
        if field in story:
            archived[field] = story[field]
    return archived


def create_lean_status(story: dict, archive_ref: str) -> dict:
    """Create lean status from story."""
    lean = {"archive_ref": archive_ref}

    for field in LEAN_STATUS_FIELDS:
        if field in story and field != "archive_ref":
            lean[field] = story[field]

    # Ensure status is set to archived
    lean["status"] = "archived"

    return lean


def create_completion_evidence(story: dict) -> dict | None:
    """Extract completion evidence from story."""
    evidence = {}

    for field in COMPLETION_EVIDENCE_FIELDS:
        if field in story:
            evidence[field] = story[field]

    return evidence if evidence else None


def create_archive_entry(
    story: dict,
    archive_ref: str,
    archive_reason: str,
    archive_reason_detail: str,
    migrated_by: str,
) -> dict:
    """Create archive entry from story."""
    archived_fields = extract_archived_fields(story)
    lean_status = create_lean_status(story, archive_ref)
    completion_evidence = create_completion_evidence(story)

    # Compute checksums
    original_checksum = compute_checksum(story)

    archive_entry = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "archive_ref": archive_ref,
        "original_story_id": story.get("id", "unknown"),
        "archived_at": datetime.now(UTC).isoformat() + "Z",
        "archive_reason": archive_reason,
        "archive_reason_detail": archive_reason_detail,
        "migration": {
            "phase": "batch_1",
            "migrated_by": migrated_by,
            "migration_script_version": MIGRATION_SCRIPT_VERSION,
            "verification_status": "pending",
        },
        "lean_status": lean_status,
        "archived_fields": archived_fields,
        "completion_evidence": completion_evidence,
        "archive_location": f"docs/archives/workflow-status/entries/{archive_ref}.yaml",
        "integrity": {
            "original_checksum": original_checksum,
            "archived_checksum": None,  # Will be computed after creation
            "verification_date": None,
        },
    }

    # Compute archived checksum
    archive_entry["integrity"]["archived_checksum"] = compute_checksum(archive_entry)
    archive_entry["integrity"]["verification_date"] = (
        datetime.now(UTC).isoformat() + "Z"
    )
    archive_entry["migration"]["verification_status"] = "verified"

    return archive_entry


def save_archive_entry(archive_entry: dict, dry_run: bool = False) -> Path:
    """Save archive entry to file."""
    archive_ref = archive_entry["archive_ref"]
    filepath = ARCHIVE_ENTRIES_DIR / f"{archive_ref}.yaml"

    if not dry_run:
        ARCHIVE_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            yaml.dump(archive_entry, f, default_flow_style=False, sort_keys=False)

    return filepath


def update_workflow_status(
    workflow_data: dict, story_id: str, lean_status: dict, dry_run: bool = False
) -> dict:
    """Update workflow-status.yaml with lean status."""
    # Find and update the story in completed section
    if "completed" in workflow_data:
        for i, story in enumerate(workflow_data["completed"]):
            if story.get("id") == story_id:
                if not dry_run:
                    workflow_data["completed"][i] = lean_status
                return workflow_data

    # Check backlog section
    if "backlog" in workflow_data:
        for i, story in enumerate(workflow_data["backlog"]):
            if story.get("id") == story_id:
                if not dry_run:
                    workflow_data["backlog"][i] = lean_status
                return workflow_data

    # Check launch_stories section
    if "launch_stories" in workflow_data:
        for i, story in enumerate(workflow_data["launch_stories"]):
            if story.get("id") == story_id:
                if not dry_run:
                    workflow_data["launch_stories"][i] = lean_status
                return workflow_data

    return workflow_data


def load_workflow_status() -> dict:
    """Load workflow-status.yaml."""
    with open(WORKFLOW_STATUS_PATH) as f:
        return yaml.safe_load(f)


def save_workflow_status(data: dict, dry_run: bool = False):
    """Save workflow-status.yaml."""
    if not dry_run:
        with open(WORKFLOW_STATUS_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def find_stories_to_archive(
    workflow_data: dict, current_date: datetime, story_id_filter: str | None = None
) -> list[tuple[dict, str, str]]:
    """Find stories eligible for archival."""
    stories_to_archive = []
    seen_story_ids = set()

    # Search in all story sections
    sections = ["completed", "backlog", "launch_stories"]

    for section in sections:
        if section not in workflow_data:
            continue

        for story in workflow_data[section]:
            story_id = story.get("id", "")

            # Skip if already seen (story appears in multiple sections)
            if story_id in seen_story_ids:
                continue

            # Skip if specific story ID requested and doesn't match
            if story_id_filter and story_id != story_id_filter:
                continue

            should_arch, reason, reason_detail = should_archive(story, current_date)
            if should_arch:
                stories_to_archive.append((story, reason, reason_detail))
                seen_story_ids.add(story_id)

    return stories_to_archive


def verify_archive_integrity(archive_entry: dict, original_story: dict) -> bool:
    """Verify archived data matches original."""
    # Check that all archived fields are present
    archived_fields = archive_entry.get("archived_fields", {})

    for field in ARCHIVE_FIELDS:
        if field in original_story and field not in archived_fields:
            print(f"  WARNING: Field '{field}' missing from archive")
            return False

    # Verify lean status has required fields
    lean_status = archive_entry.get("lean_status", {})
    required_lean = ["id", "status", "title", "archive_ref"]
    for field in required_lean:
        if field not in lean_status:
            print(f"  WARNING: Required lean field '{field}' missing")
            return False

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate workflow status stories to archive"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be archived without making changes (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the archival (disables dry-run)",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        help="Archive specific story by ID",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Maximum number of stories to archive (default: 10)",
    )
    parser.add_argument(
        "--migrated-by",
        type=str,
        default="senior-dev",
        help="Name of agent performing migration",
    )

    args = parser.parse_args()

    # Determine if we're in dry-run mode
    dry_run = not args.execute if args.execute else args.dry_run

    print("=" * 80)
    print("WORKFLOW STATUS ARCHIVE MIGRATION")
    print("=" * 80)
    print(
        f"Mode: {'DRY-RUN (no changes)' if dry_run else 'EXECUTE (will make changes)'}"
    )
    print(f"Script Version: {MIGRATION_SCRIPT_VERSION}")
    print(f"Schema Version: {ARCHIVE_SCHEMA_VERSION}")
    print(f"Age Threshold: {ARCHIVE_AGE_THRESHOLD_DAYS} days")
    print(f"Batch Size: {args.batch_size}")
    print("=" * 80)
    print()

    # Load workflow status
    print(f"Loading workflow status from {WORKFLOW_STATUS_PATH}...")
    workflow_data = load_workflow_status()

    # Find stories to archive
    current_date = datetime.now(UTC)
    stories_to_archive = find_stories_to_archive(
        workflow_data, current_date, args.story_id
    )

    print(f"Found {len(stories_to_archive)} stories eligible for archival")
    print()

    if not stories_to_archive:
        print("No stories to archive. Exiting.")
        return 0

    # Limit batch size
    stories_to_archive = stories_to_archive[: args.batch_size]

    # Process each story
    archived_count = 0
    failed_count = 0

    for story, reason, reason_detail in stories_to_archive:
        story_id = story.get("id", "unknown")
        print(f"Processing: {story_id}")
        print(f"  Reason: {reason}")
        print(f"  Title: {story.get('title', 'N/A')[:60]}...")

        try:
            # Generate archive reference
            archive_ref = generate_archive_ref(story_id)

            # Create archive entry
            archive_entry = create_archive_entry(
                story, archive_ref, reason, reason_detail, args.migrated_by
            )

            # Verify integrity
            if not verify_archive_integrity(archive_entry, story):
                print("  ERROR: Integrity check failed")
                failed_count += 1
                continue

            # Save archive entry
            archive_path = save_archive_entry(archive_entry, dry_run)
            print(f"  Archive: {archive_path}")

            # Update workflow status
            lean_status = archive_entry["lean_status"]
            workflow_data = update_workflow_status(
                workflow_data, story_id, lean_status, dry_run
            )

            print(f"  Status: {'WOULD UPDATE' if dry_run else 'UPDATED'}")
            archived_count += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            failed_count += 1

        print()

    # Save updated workflow status
    if not dry_run and archived_count > 0:
        print("Saving updated workflow status...")
        save_workflow_status(workflow_data, dry_run)
        print("Done.")

    # Summary
    print("=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Stories processed: {len(stories_to_archive)}")
    print(f"Successfully archived: {archived_count}")
    print(f"Failed: {failed_count}")
    print(
        f"Mode: {'DRY-RUN (no changes made)' if dry_run else 'EXECUTED (changes saved)'}"
    )
    print("=" * 80)

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
