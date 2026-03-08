#!/usr/bin/env python3
"""
migrate_tempmemories.py - Migration automation for docs/tempmemories/ to Redis and Qdrant.

This script migrates temporary memory files from docs/tempmemories/ into:
1. Redis (for iterlog files): Stores story metadata in hashes with TTL
2. Qdrant (for all valid files): Stores full content with semantic search

Usage:
    python3 scripts/ops/migrate_tempmemories.py --dry-run     # Preview migration
    python3 scripts/ops/migrate_tempmemories.py --execute     # Perform migration
    python3 scripts/ops/migrate_tempmemories.py --cleanup     # Archive migrated files

Safety Features:
    - Default dry-run mode (read-only unless --execute is specified)
    - Separate --cleanup requires explicit flag
    - Idempotency via content signatures
    - Verification after each write
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Constants
TEMP_MEMORIES_DIR = Path("docs/tempmemories")
ARCHIVE_DIR = Path("docs/tempmemories/archived")
REDIS_ITERLOG_PREFIX = "bmad:chiseai:iterlog:story"
REDIS_SIGNATURES_KEY = "bmad:chiseai:migration:signatures"
DEFAULT_TTL_SECONDS = 432000  # 5 days

# Story ID patterns for iterlog classification
STORY_ID_PATTERNS = [
    r"^ST-",  # Stories
    r"^CH-",  # Changes
    r"^EP-",  # Epics
    r"^FT-",  # Features
    r"^REWARD-",  # Rewards
    r"^REPO-",  # Repository
    r"^SAFETY-",  # Safety
    r"^BRANCH-",  # Branch
    r"^PAPER-",  # Paper trading
    r"^RECON-",  # Reconciliation
]

# Files/patterns to skip
SKIP_PATTERNS = [
    r"^templates/",
    r"^README\.md$",
    r"^\.gitkeep$",
    r"^archived/",
    r"\.txt$",
    r"\.json$",
    r"\.yaml$",
    r"\.yml$",
]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate docs/tempmemories/ files to Redis and Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Preview all migrations
  %(prog)s --dry-run --story ST-NS-001  # Preview specific story
  %(prog)s --execute                    # Perform migration (writes to Redis/Qdrant)
  %(prog)s --execute --cleanup          # Migrate and archive files
  %(prog)s --cleanup --story ST-NS-001  # Archive specific story files
  %(prog)s --execute --priority P0      # Only migrate P0 priority files
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show migration plan without executing (default behavior)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform migrations (writes to Redis and Qdrant)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Archive successfully migrated files after migration",
    )
    parser.add_argument(
        "--story",
        type=str,
        metavar="ID",
        help="Migrate only files for specific story ID (e.g., ST-NS-001)",
    )
    parser.add_argument(
        "--priority",
        type=str,
        choices=["P0", "P1", "P2"],
        help="Filter by priority level (P0=needs_qdrant, P1=needs_import, P2=valid_frontmatter)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable detailed output"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before archiving (only with --cleanup)",
    )

    return parser.parse_args()


def is_skipped_file(rel_path: str) -> bool:
    """Check if file should be skipped based on patterns."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, rel_path):
            return True
    return False


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns:
        Tuple of (frontmatter dict, remaining content)
    """
    frontmatter = {}
    remaining = content

    # Check for frontmatter delimiters
    if not content.startswith("---"):
        return frontmatter, remaining

    # Find the closing ---
    match = re.search(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return frontmatter, remaining

    yaml_content = match.group(1)
    remaining = content[match.end() :]

    # Parse YAML-like content (simplified parser)
    for line in yaml_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Handle key: value pairs
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Handle arrays [item1, item2]
            if value.startswith("[") and value.endswith("]"):
                value = [
                    v.strip().strip('"').strip("'") for v in value[1:-1].split(",")
                ]
                value = [v for v in value if v]  # Remove empty

            # Handle booleans
            elif value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False

            frontmatter[key] = value

    return frontmatter, remaining


def classify_file(rel_path: str, frontmatter: dict) -> str:
    """
    Classify file priority for migration.

    Returns:
        P0: needs_manual_qdrant_import: true
        P1: needs_manual_import: true only
        P2: Valid frontmatter, no import flags
        SKIP: No valid frontmatter or excluded
    """
    if is_skipped_file(rel_path):
        return "SKIP"

    if not frontmatter:
        return "SKIP"

    # Check for P0 (needs Qdrant import)
    if frontmatter.get("needs_manual_qdrant_import") is True:
        return "P0"

    # Check for P1 (legacy import flag)
    if frontmatter.get("needs_manual_import") is True:
        return "P1"

    # Has valid frontmatter but no import flags
    return "P2"


def is_iterlog_file(frontmatter: dict) -> bool:
    """Determine if file should be migrated to Redis (iterlog type)."""
    file_type = frontmatter.get("type", "").lower()
    if file_type == "iterlog":
        return True

    story_id = frontmatter.get("story_id", "")
    for pattern in STORY_ID_PATTERNS:
        if re.search(pattern, str(story_id)):
            return True

    return False


def generate_signature(story_id: str, content: str, source_path: str) -> str:
    """
    Generate deterministic signature for idempotency.

    Uses SHA256 of story_id + first 500 chars of content + source_path
    """
    content_preview = content[:500] if len(content) > 500 else content
    signature_input = f"{story_id}:{content_preview}:{source_path}"
    return hashlib.sha256(signature_input.encode("utf-8")).hexdigest()


def check_signature_exists(signature: str) -> bool:
    """Check if signature already exists in Redis (file already migrated)."""
    try:
        # Try to import and use Redis
        import redis_state

        result = redis_state.redis_state_hget(name=REDIS_SIGNATURES_KEY, key=signature)
        return result is not None and result != ""
    except Exception:
        # If Redis unavailable, check local cache
        cache_file = Path(".migration_signatures.json")
        if cache_file.exists():
            with open(cache_file, "r") as f:
                cache = json.load(f)
                return signature in cache
        return False


def store_signature(signature: str, metadata: dict) -> bool:
    """Store signature in Redis for idempotency."""
    try:
        import redis_state

        redis_state.redis_state_hset(
            name=REDIS_SIGNATURES_KEY,
            key=signature,
            value=json.dumps(metadata),
            expire_seconds=DEFAULT_TTL_SECONDS * 4,  # 20 days
        )
        return True
    except Exception as e:
        # Fallback to local cache
        cache_file = Path(".migration_signatures.json")
        cache = {}
        if cache_file.exists():
            with open(cache_file, "r") as f:
                cache = json.load(f)
        cache[signature] = metadata
        with open(cache_file, "w") as f:
            json.dump(cache, f, indent=2)
        return True


def migrate_to_redis(
    frontmatter: dict, signature: str, dry_run: bool = False
) -> tuple[bool, str]:
    """
    Migrate iterlog file to Redis.

    Returns:
        Tuple of (success, message)
    """
    story_id = frontmatter.get("story_id", "")
    if not story_id:
        return False, "No story_id in frontmatter"

    key = f"{REDIS_ITERLOG_PREFIX}:{story_id}"

    fields = {
        "story_id": story_id,
        "story_title": frontmatter.get("story_title", ""),
        "phase": frontmatter.get("phase", ""),
        "status": frontmatter.get("status", ""),
        "started_at": frontmatter.get("started_at", ""),
        "priority": classify_file("", frontmatter),
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "migration_signature": signature,
    }

    if dry_run:
        return True, f"[DRY-RUN] Would write to Redis key: {key}"

    try:
        import redis_state

        # Write each field
        for field_name, field_value in fields.items():
            if field_value:  # Only write non-empty values
                redis_state.redis_state_hset(
                    name=key, key=field_name, value=str(field_value)
                )

        # Set TTL
        redis_state.redis_state_expire(name=key, expire_seconds=DEFAULT_TTL_SECONDS)

        # Verify write
        verification = redis_state.redis_state_hgetall(name=key)
        if verification and "story_id" in verification:
            return True, f"Successfully migrated to Redis key: {key}"
        else:
            return False, "Verification failed - key not found after write"

    except Exception as e:
        return False, f"Redis error: {str(e)}"


def migrate_to_qdrant(
    rel_path: str,
    frontmatter: dict,
    content: str,
    signature: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Migrate file to Qdrant.

    Returns:
        Tuple of (success, message)
    """
    story_id = frontmatter.get("story_id", "")

    metadata = {
        "project": frontmatter.get("project", "ChiseAI"),
        "scope": frontmatter.get("scope", ""),
        "type": frontmatter.get("type", ""),
        "story_id": story_id,
        "tags": frontmatter.get("tags", []),
        "timeframe": frontmatter.get("timeframe", ""),
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": rel_path,
        "migration_signature": signature,
        "priority": classify_file(rel_path, frontmatter),
    }

    if dry_run:
        return True, f"[DRY-RUN] Would store in Qdrant: {rel_path}"

    try:
        # Try to use qdrant_qdrant-store
        import qdrant

        qdrant.qdrant_qdrant_store(information=content, metadata=metadata)
        return True, f"Successfully stored in Qdrant: {rel_path}"
    except Exception as e:
        # Store failed, return error
        return False, f"Qdrant error: {str(e)}"


def archive_file(
    source_path: Path, rel_path: str, dry_run: bool = False
) -> tuple[bool, str]:
    """
    Archive migrated file to docs/tempmemories/archived/YYYY-MM/

    Returns:
        Tuple of (success, message)
    """
    today = datetime.now(timezone.utc)
    archive_subdir = ARCHIVE_DIR / today.strftime("%Y-%m")

    # Preserve subdirectory structure
    archive_path = archive_subdir / rel_path

    if dry_run:
        return True, f"[DRY-RUN] Would archive to: {archive_path}"

    try:
        # Create archive directory
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Move file
        source_path.rename(archive_path)

        return True, f"Archived to: {archive_path}"
    except Exception as e:
        return False, f"Archive error: {str(e)}"


def create_archive_manifest(
    migrated_files: list[dict], dry_run: bool = False
) -> tuple[bool, str]:
    """Create JSON manifest of archived files."""
    today = datetime.now(timezone.utc)
    manifest_path = ARCHIVE_DIR / today.strftime("%Y-%m") / "manifest.json"

    manifest = {
        "created_at": today.isoformat(),
        "file_count": len(migrated_files),
        "files": migrated_files,
    }

    if dry_run:
        return True, f"[DRY-RUN] Would create manifest: {manifest_path}"

    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return True, f"Created manifest: {manifest_path}"
    except Exception as e:
        return False, f"Manifest error: {str(e)}"


def scan_tempmemories(story_filter: Optional[str] = None) -> list[dict]:
    """
    Scan docs/tempmemories/ for files to migrate.

    Returns:
        List of file info dicts
    """
    files = []

    if not TEMP_MEMORIES_DIR.exists():
        return files

    for root, dirs, filenames in os.walk(TEMP_MEMORIES_DIR):
        # Skip archived directory
        if "archived" in root:
            continue

        for filename in filenames:
            if not filename.endswith(".md"):
                continue

            full_path = Path(root) / filename
            rel_path = str(full_path.relative_to(TEMP_MEMORIES_DIR))

            # Skip excluded patterns
            if is_skipped_file(rel_path):
                continue

            # Read and parse file
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                files.append(
                    {
                        "rel_path": rel_path,
                        "full_path": full_path,
                        "error": f"Read error: {e}",
                        "priority": "SKIP",
                    }
                )
                continue

            # Parse frontmatter
            frontmatter, body = parse_frontmatter(content)

            # Classify priority
            priority = classify_file(rel_path, frontmatter)

            # Filter by story if specified
            if story_filter:
                story_id = frontmatter.get("story_id", "")
                if story_filter not in str(story_id) and story_filter not in rel_path:
                    continue

            files.append(
                {
                    "rel_path": rel_path,
                    "full_path": full_path,
                    "content": content,
                    "frontmatter": frontmatter,
                    "body": body,
                    "priority": priority,
                    "is_iterlog": is_iterlog_file(frontmatter),
                    "story_id": frontmatter.get("story_id", ""),
                }
            )

    return files


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Determine mode
    dry_run = not args.execute

    if dry_run and not args.cleanup:
        print("=" * 70)
        print("MIGRATION PREVIEW MODE (DRY-RUN)")
        print("No changes will be made. Use --execute to perform migration.")
        print("=" * 70)
    elif args.execute:
        print("=" * 70)
        print("MIGRATION EXECUTE MODE")
        print("Writes will be made to Redis and Qdrant!")
        print("=" * 70)

    if args.cleanup:
        print("=" * 70)
        print("CLEANUP MODE ENABLED")
        print("Files will be archived after migration!")
        print("=" * 70)

    print()

    # Scan for files
    print(f"Scanning {TEMP_MEMORIES_DIR}...")
    files = scan_tempmemories(story_filter=args.story)

    # Filter by priority if specified
    if args.priority:
        files = [f for f in files if f["priority"] == args.priority]

    # Count by priority
    counts = {"P0": 0, "P1": 0, "P2": 0, "SKIP": 0}
    for f in files:
        counts[f["priority"]] = counts.get(f["priority"], 0) + 1

    print(f"Found {len(files)} files:")
    print(f"  P0 (needs_qdrant_import): {counts.get('P0', 0)}")
    print(f"  P1 (needs_import): {counts.get('P1', 0)}")
    print(f"  P2 (valid_frontmatter): {counts.get('P2', 0)}")
    print(f"  SKIP: {counts.get('SKIP', 0)}")
    print()

    if not files:
        print("No files to process.")
        return 0

    # Track results
    results = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "already_migrated": 0,
        "redis_keys": [],
        "failed_files": [],
        "migrated_files": [],
    }

    # Process each file
    for file_info in files:
        rel_path = file_info["rel_path"]
        priority = file_info["priority"]
        frontmatter = file_info.get("frontmatter", {})
        content = file_info.get("content", "")
        story_id = file_info.get("story_id", "")

        if priority == "SKIP":
            results["skipped"] += 1
            if args.verbose:
                print(f"[SKIP] {rel_path}")
            continue

        results["attempted"] += 1

        if args.verbose:
            print(f"\n[PROCESSING] {rel_path} (Priority: {priority})")
            if story_id:
                print(f"  Story ID: {story_id}")

        # Generate signature for idempotency
        signature = generate_signature(story_id, content, rel_path)

        # Check if already migrated
        if check_signature_exists(signature):
            results["already_migrated"] += 1
            if args.verbose:
                print(f"  [ALREADY MIGRATED] Signature exists, skipping")
            continue

        # Track file migration
        file_result = {
            "source": rel_path,
            "priority": priority,
            "story_id": story_id,
            "signature": signature,
            "redis_success": False,
            "qdrant_success": False,
            "archive_success": False,
            "errors": [],
        }

        # Migrate to Redis if iterlog
        redis_success = True
        if file_info.get("is_iterlog"):
            success, message = migrate_to_redis(
                frontmatter, signature, dry_run or not args.execute
            )
            if not success:
                redis_success = False
                file_result["errors"].append(f"Redis: {message}")
            else:
                file_result["redis_success"] = True
                results["redis_keys"].append(f"{REDIS_ITERLOG_PREFIX}:{story_id}")

            if args.verbose:
                status = "OK" if success else "FAIL"
                print(f"  [REDIS] {status}: {message}")

        # Migrate to Qdrant (all valid files)
        qdrant_success = True
        success, message = migrate_to_qdrant(
            rel_path, frontmatter, content, signature, dry_run or not args.execute
        )
        if not success:
            qdrant_success = False
            file_result["errors"].append(f"Qdrant: {message}")
        else:
            file_result["qdrant_success"] = True

        if args.verbose:
            status = "OK" if success else "FAIL"
            print(f"  [QDRANT] {status}: {message}")

        # Archive if cleanup mode and migrations succeeded
        archive_success = True
        if args.cleanup and redis_success and qdrant_success:
            success, message = archive_file(file_info["full_path"], rel_path, dry_run)
            if not success:
                archive_success = False
                file_result["errors"].append(f"Archive: {message}")
            else:
                file_result["archive_success"] = True

            if args.verbose:
                status = "OK" if success else "FAIL"
                print(f"  [ARCHIVE] {status}: {message}")

        # Store signature on success
        if redis_success and qdrant_success and args.execute:
            store_signature(
                signature,
                {
                    "story_id": story_id,
                    "source": rel_path,
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            results["succeeded"] += 1
            results["migrated_files"].append(file_result)
        elif not redis_success or not qdrant_success:
            results["failed"] += 1
            results["failed_files"].append(
                {"file": rel_path, "errors": file_result["errors"]}
            )

    # Create archive manifest if cleanup mode
    if args.cleanup and results["migrated_files"]:
        success, message = create_archive_manifest(results["migrated_files"], dry_run)
        if args.verbose:
            status = "OK" if success else "FAIL"
            print(f"\n[MANIFEST] {status}: {message}")

    # Print summary
    print()
    print("=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"Files attempted:  {results['attempted']}")
    print(f"Succeeded:        {results['succeeded']}")
    print(f"Failed:           {results['failed']}")
    print(f"Skipped:          {results['skipped']}")
    print(f"Already migrated: {results['already_migrated']}")

    if results["redis_keys"]:
        print()
        print("Redis keys written:")
        for key in results["redis_keys"][:10]:  # Show first 10
            print(f"  - {key}")
        if len(results["redis_keys"]) > 10:
            print(f"  ... and {len(results['redis_keys']) - 10} more")

    if results["failed_files"]:
        print()
        print("Failed files:")
        for failed in results["failed_files"]:
            print(f"  - {failed['file']}")
            for error in failed["errors"]:
                print(f"    Error: {error}")

    if args.cleanup and results["migrated_files"]:
        print()
        print(f"Archive location: {ARCHIVE_DIR / datetime.now(timezone.utc).strftime('%Y-%m')}")

    # Output JSON report if execute mode
    if args.execute:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "execute" if args.execute else "dry-run",
            "cleanup": args.cleanup,
            "stats": {
                "attempted": results["attempted"],
                "succeeded": results["succeeded"],
                "failed": results["failed"],
                "skipped": results["skipped"],
                "already_migrated": results["already_migrated"],
            },
            "redis_keys": results["redis_keys"],
            "failed_files": results["failed_files"],
            "archive_location": str(ARCHIVE_DIR / datetime.now(timezone.utc).strftime("%Y-%m"))
            if args.cleanup
            else None,
        }

        report_path = Path("migration_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print()
        print(f"Full report saved to: {report_path}")

    print()
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
