#!/usr/bin/env python3
"""
Workflow Status Archive Verification Script
Story: ST-WORKFLOW-ARCHIVAL-001

Verifies data integrity of archived stories by comparing archived entries
with their original workflow-status.yaml entries.

Usage:
    python scripts/workflow/migration/verify_archive.py --archive-ref ARCH-20260309-...
    python scripts/workflow/migration/verify_archive.py --story-id ST-LAUNCH-001
    python scripts/workflow/migration/verify_archive.py --all
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

ARCHIVE_ENTRIES_DIR = Path("docs/archives/workflow-status/entries")
WORKFLOW_STATUS_PATH = Path("docs/bmm-workflow-status.yaml")


def compute_checksum(data: dict) -> str:
    """Compute SHA-256 checksum of data."""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


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


def find_story_in_workflow(workflow_data: dict, story_id: str) -> dict | None:
    """Find story in workflow status."""
    sections = ["completed", "backlog", "launch_stories"]

    for section in sections:
        if section not in workflow_data:
            continue
        for story in workflow_data[section]:
            if story.get("id") == story_id:
                return story

    return None


def verify_archive_entry(archive_entry: dict) -> dict:
    """Verify single archive entry integrity."""
    results = {
        "archive_ref": archive_entry.get("archive_ref"),
        "story_id": archive_entry.get("original_story_id"),
        "checks": {},
        "passed": True,
    }

    # Check 1: Required fields present
    required_fields = [
        "archive_ref",
        "original_story_id",
        "archived_at",
        "archive_reason",
        "lean_status",
        "archived_fields",
        "integrity",
    ]

    missing_fields = []
    for field in required_fields:
        if field not in archive_entry:
            missing_fields.append(field)

    results["checks"]["required_fields"] = {
        "passed": len(missing_fields) == 0,
        "missing": missing_fields,
    }

    if missing_fields:
        results["passed"] = False

    # Check 2: Lean status has required fields
    lean_status = archive_entry.get("lean_status", {})
    required_lean = ["id", "status", "title", "archive_ref"]
    missing_lean = [f for f in required_lean if f not in lean_status]

    results["checks"]["lean_status"] = {
        "passed": len(missing_lean) == 0,
        "missing": missing_lean,
    }

    if missing_lean:
        results["passed"] = False

    # Check 3: Integrity checksums match
    integrity = archive_entry.get("integrity", {})
    archived_checksum = integrity.get("archived_checksum")

    # Method 1 (EXCLUDE): Remove 'archived_checksum' key entirely before hashing
    verification_entry = {k: v for k, v in archive_entry.items() if k != "integrity"}
    if "integrity" in archive_entry:
        verification_entry["integrity"] = {
            k: v
            for k, v in archive_entry["integrity"].items()
            if k != "archived_checksum"
        }

    computed_checksum = compute_checksum(verification_entry)
    checksum_match = archived_checksum == computed_checksum

    # Method 2 (INCLUDE): Set 'archived_checksum' to None before hashing,
    # matching the approach used by archive_workflow_status_items.py which
    # includes archived_checksum=None in the dict, hashes it, then sets
    # the real value afterwards.
    if not checksum_match:
        fallback_entry = {k: v for k, v in archive_entry.items() if k != "integrity"}
        if "integrity" in archive_entry:
            fallback_entry["integrity"] = dict(archive_entry["integrity"])
            fallback_entry["integrity"]["archived_checksum"] = None

        fallback_checksum = compute_checksum(fallback_entry)
        checksum_match = archived_checksum == fallback_checksum

    results["checks"]["checksum"] = {
        "passed": checksum_match,
        "stored": archived_checksum,
        "computed": computed_checksum,
    }

    if not checksum_match:
        results["passed"] = False

    # Check 4: Archive file exists at specified location
    archive_location = archive_entry.get("archive_location", "")
    archive_path = Path(archive_location)

    results["checks"]["file_exists"] = {
        "passed": archive_path.exists(),
        "path": str(archive_path),
    }

    if not archive_path.exists():
        results["passed"] = False

    # Check 5: Archive reason is valid
    archive_reason = archive_entry.get("archive_reason", "")
    valid_reasons = ["age", "size", "completion_status", "manual"]

    results["checks"]["archive_reason"] = {
        "passed": archive_reason in valid_reasons,
        "value": archive_reason,
    }

    if archive_reason not in valid_reasons:
        results["passed"] = False

    return results


def verify_no_data_loss(archive_entry: dict, workflow_data: dict) -> dict:
    """Verify no data loss between original and archived entry."""
    results = {
        "story_id": archive_entry.get("original_story_id"),
        "checks": {},
        "passed": True,
    }

    story_id = archive_entry.get("original_story_id")

    # Find story in workflow status
    current_story = find_story_in_workflow(workflow_data, story_id)

    if not current_story:
        results["checks"]["story_exists"] = {
            "passed": False,
            "error": f"Story {story_id} not found in workflow-status.yaml",
        }
        results["passed"] = False
        return results

    results["checks"]["story_exists"] = {"passed": True}

    # Check that lean status fields are preserved
    lean_status = archive_entry.get("lean_status", {})

    lean_checks = {}
    for key, value in lean_status.items():
        if key == "archive_ref":
            continue
        if key in current_story:
            if current_story[key] == value:
                lean_checks[key] = "match"
            else:
                lean_checks[key] = (
                    f"mismatch (archive: {value}, current: {current_story[key]})"
                )
                results["passed"] = False
        else:
            lean_checks[key] = "missing in current"
            results["passed"] = False

    results["checks"]["lean_status_match"] = {
        "passed": all(v == "match" for v in lean_checks.values()),
        "fields": lean_checks,
    }

    # Check that archived fields are NOT in current story (they were moved)
    archived_fields = archive_entry.get("archived_fields", {})
    fields_still_present = []

    for field in archived_fields:
        if field in current_story:
            fields_still_present.append(field)

    results["checks"]["fields_archived"] = {
        "passed": len(fields_still_present) == 0,
        "still_present": fields_still_present,
    }

    if fields_still_present:
        results["passed"] = False

    return results


def verify_all_archives() -> dict:
    """Verify all archive entries."""
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "entries": [],
    }

    if not ARCHIVE_ENTRIES_DIR.exists():
        return results

    workflow_data = load_workflow_status()

    for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
        with open(archive_file) as f:
            archive_entry = yaml.safe_load(f)

        results["total"] += 1

        # Verify archive entry integrity
        entry_results = verify_archive_entry(archive_entry)

        # Verify no data loss
        data_loss_results = verify_no_data_loss(archive_entry, workflow_data)

        # Combine results
        combined_passed = entry_results["passed"] and data_loss_results["passed"]

        results["entries"].append(
            {
                "archive_ref": archive_entry.get("archive_ref"),
                "story_id": archive_entry.get("original_story_id"),
                "integrity_passed": entry_results["passed"],
                "no_data_loss_passed": data_loss_results["passed"],
                "overall_passed": combined_passed,
                "integrity_checks": entry_results["checks"],
                "data_loss_checks": data_loss_results["checks"],
            }
        )

        if combined_passed:
            results["passed"] += 1
        else:
            results["failed"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Verify workflow status archive integrity"
    )
    parser.add_argument(
        "--archive-ref",
        type=str,
        help="Verify specific archive by reference",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        help="Verify archive for specific story ID",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Verify all archive entries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("WORKFLOW STATUS ARCHIVE VERIFICATION")
    print("=" * 80)
    print()

    if args.archive_ref:
        # Verify specific archive
        archive_entry = load_archive_entry(args.archive_ref)
        if not archive_entry:
            print(f"ERROR: Archive {args.archive_ref} not found")
            return 1

        results = verify_archive_entry(archive_entry)
        workflow_data = load_workflow_status()
        data_loss_results = verify_no_data_loss(archive_entry, workflow_data)

        if args.json:
            print(
                json.dumps(
                    {
                        "integrity": results,
                        "data_loss": data_loss_results,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Archive: {args.archive_ref}")
            print(f"Story ID: {results['story_id']}")
            print()
            print("Integrity Checks:")
            for check, result in results["checks"].items():
                status = "✓ PASS" if result["passed"] else "✗ FAIL"
                print(f"  {status}: {check}")
            print()
            print("Data Loss Checks:")
            for check, result in data_loss_results["checks"].items():
                if isinstance(result, dict) and "passed" in result:
                    status = "✓ PASS" if result["passed"] else "✗ FAIL"
                    print(f"  {status}: {check}")
            print()
            overall = results["passed"] and data_loss_results["passed"]
            print(f"Overall: {'✓ PASSED' if overall else '✗ FAILED'}")

        return 0 if results["passed"] and data_loss_results["passed"] else 1

    elif args.story_id:
        # Find archive by story ID
        if not ARCHIVE_ENTRIES_DIR.exists():
            print("ERROR: No archive entries found")
            return 1

        for archive_file in ARCHIVE_ENTRIES_DIR.glob("ARCH-*.yaml"):
            with open(archive_file) as f:
                archive_entry = yaml.safe_load(f)

            if archive_entry.get("original_story_id") == args.story_id:
                results = verify_archive_entry(archive_entry)
                workflow_data = load_workflow_status()
                data_loss_results = verify_no_data_loss(archive_entry, workflow_data)

                if args.json:
                    print(
                        json.dumps(
                            {
                                "integrity": results,
                                "data_loss": data_loss_results,
                            },
                            indent=2,
                        )
                    )
                else:
                    print(f"Archive: {archive_entry.get('archive_ref')}")
                    print(f"Story ID: {args.story_id}")
                    print()
                    print("Integrity Checks:")
                    for check, result in results["checks"].items():
                        status = "✓ PASS" if result["passed"] else "✗ FAIL"
                        print(f"  {status}: {check}")
                    print()
                    overall = results["passed"] and data_loss_results["passed"]
                    print(f"Overall: {'✓ PASSED' if overall else '✗ FAILED'}")

                return 0 if results["passed"] and data_loss_results["passed"] else 1

        print(f"ERROR: No archive found for story {args.story_id}")
        return 1

    elif args.all:
        # Verify all archives
        results = verify_all_archives()

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Total Archives: {results['total']}")
            print(f"Passed: {results['passed']}")
            print(f"Failed: {results['failed']}")
            print()

            for entry in results["entries"]:
                status = "✓ PASS" if entry["overall_passed"] else "✗ FAIL"
                print(f"{status}: {entry['archive_ref']} ({entry['story_id']})")

                if not entry["overall_passed"]:
                    if not entry["integrity_passed"]:
                        print("  - Integrity check failed")
                    if not entry["no_data_loss_passed"]:
                        print("  - Data loss check failed")

        return 0 if results["failed"] == 0 else 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
