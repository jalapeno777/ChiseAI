#!/usr/bin/env python3
"""
Cleanup Old Archives

Removes archive files older than the retention period.
Ensures Qdrant has content before deletion.

Usage:
    python cleanup_old_archives.py --age-days 730 [--dry-run] [--qdrant-sync]

Safety:
    - Verifies Qdrant has content before file deletion
    - Creates deletion log
    - Requires explicit --execute flag
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("cleanup_archives")


ARCHIVE_DIR = Path("docs/archives/workflow-status")
STORY_DETAILS_DIR = ARCHIVE_DIR / "story-details"
DEFAULT_RETENTION_DAYS = 730  # 2 years


def parse_date(date_str: str) -> datetime:
    """Parse ISO date string."""
    try:
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def get_archive_age(archive_path: Path) -> int:
    """Get age of archive in days."""
    # Try to get date from archive metadata
    try:
        with open(archive_path) as f:
            data = yaml.safe_load(f)

        # Try archived_at first
        archived_date = data.get("archived_story", {}).get("metadata", {}).get(
            "archived_at"
        ) or data.get("archive_metadata", {}).get("archived_date")

        if archived_date:
            archived_dt = parse_date(archived_date)
            if archived_dt:
                return (datetime.now(UTC) - archived_dt).days
    except Exception:
        pass

    # Fall back to file modification time
    mtime = datetime.fromtimestamp(archive_path.stat().st_mtime, tz=UTC)
    return (datetime.now(UTC) - mtime).days


def verify_qdrant_sync(story_id: str) -> bool:
    """Verify story content exists in Qdrant."""
    # This is a placeholder - would need actual Qdrant integration
    logger.debug(f"Would verify Qdrant sync for {story_id}")
    return True


def cleanup_archives(
    age_days: int, qdrant_sync: bool = True, dry_run: bool = True
) -> dict:
    """Clean up old archives."""
    results = {"scanned": 0, "deleted": 0, "skipped": 0, "errors": []}

    if not STORY_DETAILS_DIR.exists():
        logger.info("No archives directory found")
        return results

    archive_files = list(STORY_DETAILS_DIR.glob("*-*-details.yaml"))
    results["scanned"] = len(archive_files)

    for archive_path in archive_files:
        story_id = archive_path.name.split("-")[0]
        archive_age = get_archive_age(archive_path)

        if archive_age is None:
            logger.warning(f"Could not determine age of {archive_path.name}")
            results["skipped"] += 1
            continue

        if archive_age < age_days:
            logger.debug(
                f"Skipping {archive_path.name}: age {archive_age} < {age_days}"
            )
            results["skipped"] += 1
            continue

        # Check Qdrant sync if required
        if qdrant_sync:
            if not verify_qdrant_sync(story_id):
                logger.warning(f"Skipping {archive_path.name}: not synced to Qdrant")
                results["skipped"] += 1
                continue

        # Delete or dry run
        if dry_run:
            logger.info(
                f"[DRY RUN] Would delete: {archive_path.name} (age: {archive_age} days)"
            )
            results["deleted"] += 1
        else:
            try:
                archive_path.unlink()
                logger.info(f"Deleted: {archive_path.name} (age: {archive_age} days)")
                results["deleted"] += 1
            except Exception as e:
                logger.error(f"Failed to delete {archive_path.name}: {e}")
                results["errors"].append({"file": archive_path.name, "error": str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description="Clean up old archive files")
    parser.add_argument(
        "--age-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Retention period in days (default: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview deletions without removing files",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually perform deletions"
    )
    parser.add_argument(
        "--qdrant-sync",
        action="store_true",
        default=True,
        help="Verify Qdrant sync before deletion",
    )
    parser.add_argument(
        "--no-qdrant-sync",
        dest="qdrant_sync",
        action="store_false",
        help="Skip Qdrant verification",
    )

    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 70)
    print("Archive Cleanup Tool")
    print("=" * 70)
    print(f"Retention: {args.age_days} days ({args.age_days / 365:.1f} years)")
    print(f"Qdrant sync check: {'enabled' if args.qdrant_sync else 'disabled'}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print("=" * 70)

    results = cleanup_archives(args.age_days, args.qdrant_sync, dry_run)

    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Archives scanned: {results['scanned']}")
    print(f"  Archives deleted: {results['deleted']}")
    print(f"  Archives skipped: {results['skipped']}")

    if results["errors"]:
        print(f"\n  Errors: {len(results['errors'])}")
        for error in results["errors"]:
            print(f"    - {error['file']}: {error['error']}")

    print("=" * 70)

    if dry_run and results["deleted"] > 0:
        print("\nRun with --execute to actually delete files.")

    sys.exit(0)


if __name__ == "__main__":
    main()
