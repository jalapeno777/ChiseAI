#!/usr/bin/env python3
"""
Identify Archival Candidates

Identifies stories in the workflow status that are eligible for archival
based on age and completion status.

Usage:
    python identify_archival_candidates.py [--age-days N] [--status LIST] [--output PATH]
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("identify_candidates")


WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
DEFAULT_AGE_DAYS = 7
DEFAULT_STATUSES = ["completed", "merged"]


def parse_date(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 date string."""
    if not date_str:
        return None
    try:
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def calculate_age_days(date_str: str | None) -> int | None:
    """Calculate age in days from date string."""
    date = parse_date(date_str)
    if not date:
        return None
    now = datetime.now(UTC)
    return (now - date).days


def is_candidate(story: dict, age_days: int, statuses: list[str]) -> tuple[bool, str]:
    """Check if story is an archival candidate."""
    story.get("id", "UNKNOWN")
    status = story.get("status", "").lower()

    # Check status
    if status not in statuses:
        return False, f"Status '{status}' not in {statuses}"

    # Check completion date
    completed_date = story.get("completed_date") or story.get("merged_date")
    if not completed_date:
        return False, "No completion date"

    age = calculate_age_days(completed_date)
    if age is None:
        return False, "Invalid completion date"

    if age <= age_days:
        return False, f"Age {age} days <= threshold {age_days} days"

    # Check completion evidence
    if not story.get("pr_number") and not story.get("merge_commit"):
        return False, "Missing completion evidence"

    return True, f"Age {age} days > threshold {age_days} days"


def identify_candidates(
    workflow_data: dict, age_days: int, statuses: list[str]
) -> list[dict]:
    """Identify all archival candidates."""
    candidates = []

    for section in ["completed", "backlog", "launch_stories"]:
        stories = workflow_data.get(section, [])
        for story in stories:
            if not isinstance(story, dict):
                continue

            is_eligible, reason = is_candidate(story, age_days, statuses)

            if is_eligible:
                candidates.append(
                    {
                        "story_id": story.get("id"),
                        "title": story.get("title"),
                        "status": story.get("status"),
                        "completed_date": story.get("completed_date")
                        or story.get("merged_date"),
                        "age_days": calculate_age_days(
                            story.get("completed_date") or story.get("merged_date")
                        ),
                        "section": section,
                        "reason": reason,
                    }
                )

    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Identify stories eligible for archival"
    )
    parser.add_argument(
        "--age-days",
        type=int,
        default=DEFAULT_AGE_DAYS,
        help=f"Age threshold in days (default: {DEFAULT_AGE_DAYS})",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=",".join(DEFAULT_STATUSES),
        help=f"Statuses to consider (default: {','.join(DEFAULT_STATUSES)})",
    )
    parser.add_argument("--output", type=Path, help="Output file for candidates")
    parser.add_argument(
        "--workflow",
        type=Path,
        default=WORKFLOW_FILE,
        help="Path to workflow status file",
    )

    args = parser.parse_args()

    statuses = [s.strip().lower() for s in args.status.split(",")]

    print("=" * 70)
    print("Archival Candidate Identification")
    print("=" * 70)
    print(f"Age threshold: {args.age_days} days")
    print(f"Statuses: {statuses}")
    print("=" * 70)

    # Load workflow
    if not args.workflow.exists():
        logger.error(f"Workflow file not found: {args.workflow}")
        sys.exit(1)

    with open(args.workflow) as f:
        workflow_data = yaml.safe_load(f) or {}

    # Identify candidates
    candidates = identify_candidates(workflow_data, args.age_days, statuses)

    # Output results
    print(f"\nFound {len(candidates)} archival candidates:\n")

    for c in candidates:
        print(f"  {c['story_id']}: {c['title'][:50]}...")
        print(f"    Status: {c['status']}, Age: {c['age_days']} days")
        print(f"    Completed: {c['completed_date']}")
        print()

    # Save to file if requested
    if args.output:
        output_data = {
            "generated_at": datetime.now(UTC).isoformat(),
            "criteria": {"age_days": args.age_days, "statuses": statuses},
            "total_candidates": len(candidates),
            "candidates": candidates,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            yaml.dump(output_data, f, default_flow_style=False)

        logger.info(f"Saved candidates to {args.output}")

    print("=" * 70)
    print(f"Total candidates: {len(candidates)}")
    print("=" * 70)

    sys.exit(0)


if __name__ == "__main__":
    main()
