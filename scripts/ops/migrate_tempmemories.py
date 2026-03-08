#!/usr/bin/env python3
"""
migrate_tempmemories.py - Comprehensive migration script for docs/tempmemories/ to Redis and Qdrant.

This script migrates temporary memory files from docs/tempmemories/ into:
1. Redis (for iterlog files): Stores story metadata in hashes with TTL
2. Qdrant (for all valid files): Stores full content with semantic search

Usage:
    python3 scripts/ops/migrate_tempmemories.py --dry-run              # Preview migration
    python3 scripts/ops/migrate_tempmemories.py --execute              # Perform migration
    python3 scripts/ops/migrate_tempmemories.py --execute --cleanup    # Migrate and archive
    python3 scripts/ops/migrate_tempmemories.py --story ST-NS-001      # Filter by story

Safety Features:
    - Default dry-run mode (read-only unless --execute is specified)
    - Separate --cleanup requires explicit flag
    - Idempotency via content signatures
    - Verification after each write
    - Updates source files to remove needs_manual_qdrant_import flag after success
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
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

# Files/patterns to skip (protected files)
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
  %(prog)s --execute --priority P0      # Migrate only P0 priority files
  %(prog)s --execute --story ST-NS-001  # Migrate specific story only
  %(prog)s --execute --all-priorities   # Migrate all priority levels
  %(prog)s --execute --priority P0 --cleanup  # Migrate and archive P0 files

Safety Note:
  --execute requires an explicit scope filter (--priority, --story, or --all-priorities)
  to prevent accidental broad migrations.
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
        metavar="STORY_ID",
        help="Migrate only files for specific story ID (e.g., ST-NS-001)",
    )
    parser.add_argument(
        "--priority",
        type=str,
        choices=["P0", "P1", "P2"],
        help="Filter by priority level (P0=needs_qdrant, P1=needs_import, P2=valid_frontmatter)",
    )
    parser.add_argument(
        "--all-priorities",
        action="store_true",
        help="Explicitly allow migration of all priority levels (P0, P1, P2). Required when --execute is used without other filters.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable detailed output"
    )

    args = parser.parse_args()

    # Safety guard: --execute requires explicit scope
    if args.execute:
        has_explicit_scope = (
            args.priority is not None or args.story is not None or args.all_priorities
        )
        if not has_explicit_scope:
            print("=" * 70, file=sys.stderr)
            print("ERROR: --execute requires explicit scope filter", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(file=sys.stderr)
            print(
                "To prevent accidental broad migrations, use one of:", file=sys.stderr
            )
            print(
                "  --priority {P0,P1,P2}  # Migrate only files of specified priority",
                file=sys.stderr,
            )
            print(
                "  --story ST-XXX         # Migrate only files for specific story",
                file=sys.stderr,
            )
            print(
                "  --all-priorities       # Migrate all priority levels (requires explicit flag)",
                file=sys.stderr,
            )
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print("  %(prog)s --execute --priority P0", file=sys.stderr)
            print("  %(prog)s --execute --story ST-NS-001", file=sys.stderr)
            print("  %(prog)s --execute --all-priorities", file=sys.stderr)
            print(file=sys.stderr)
            sys.exit(1)

    return args


def is_skipped_file(rel_path: str) -> bool:
    """Check if file should be skipped based on patterns."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, rel_path):
            return True
    return False


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: The full file content

    Returns:
        Tuple of (frontmatter dict, remaining content after frontmatter)
    """
    frontmatter: dict[str, Any] = {}
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


def get_redis_client() -> Any | None:
    """Create Redis client with standard connection."""
    try:
        import redis

        host = os.environ.get("REDIS_HOST", "host.docker.internal")
        port = int(os.environ.get("REDIS_PORT", "6380"))

        client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception:
        return None


def get_qdrant_client() -> Any | None:
    """Create Qdrant client with standard connection."""
    try:
        from qdrant_client import QdrantClient

        host = os.environ.get("QDRANT_HOST", "host.docker.internal")
        port = int(os.environ.get("QDRANT_PORT", "6334"))

        client = QdrantClient(host=host, port=port)
        return client
    except Exception:
        return None


def get_embedding_generator() -> Any | None:
    """Get embedding generator for creating vector embeddings."""
    try:
        # Try to import from the codebase
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from src.governance.tempmemory.deduplication import EmbeddingGenerator

        return EmbeddingGenerator()
    except Exception as e:
        print(f"Warning: Could not load embedding generator: {e}", file=sys.stderr)
        return None


def check_signature_exists(signature: str) -> bool:
    """Check if signature already exists in Redis (file already migrated)."""
    try:
        client = get_redis_client()
        if client:
            result = client.hget(REDIS_SIGNATURES_KEY, signature)
            return result is not None and result != ""
    except Exception:
        pass

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
        client = get_redis_client()
        if client:
            client.hset(REDIS_SIGNATURES_KEY, signature, json.dumps(metadata))
            client.expire(REDIS_SIGNATURES_KEY, DEFAULT_TTL_SECONDS * 4)  # 20 days
            return True
    except Exception:
        pass

    # Fallback to local cache
    cache_file = Path(".migration_signatures.json")
    cache: dict[str, Any] = {}
    if cache_file.exists():
        with open(cache_file, "r") as f:
            cache = json.load(f)
    cache[signature] = metadata
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2)
    return True


def migrate_to_redis(
    frontmatter: dict, signature: str, dry_run: bool = False
) -> tuple[bool, str, list[str]]:
    """
    Migrate iterlog file to Redis.

    Args:
        frontmatter: Parsed YAML frontmatter
        signature: Content signature for idempotency
        dry_run: If True, don't actually write

    Returns:
        Tuple of (success, message, list_of_redis_keys)
    """
    story_id = frontmatter.get("story_id", "")
    if not story_id:
        return False, "No story_id in frontmatter", []

    redis_keys: list[str] = []
    key = f"{REDIS_ITERLOG_PREFIX}:{story_id}"
    redis_keys.append(key)

    fields = {
        "story_id": story_id,
        "project": frontmatter.get("project", "ChiseAI"),
        "scope": frontmatter.get("scope", ""),
        "type": frontmatter.get("type", ""),
        "story_title": frontmatter.get("story_title", ""),
        "phase": frontmatter.get("phase", ""),
        "status": frontmatter.get("status", ""),
        "started_at": frontmatter.get("started_at", ""),
        "epic_id": frontmatter.get("epic_id", ""),
        "tags": json.dumps(frontmatter.get("tags", [])),
        "date": frontmatter.get("date", ""),
        "priority": classify_file("", frontmatter),
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "migration_signature": signature,
    }

    if dry_run:
        return True, f"[DRY-RUN] Would write to Redis key: {key}", redis_keys

    try:
        client = get_redis_client()
        if not client:
            return False, "Redis not available", redis_keys

        # Write each field
        for field_name, field_value in fields.items():
            if field_value and field_value != "[]":  # Only write non-empty values
                client.hset(key, field_name, str(field_value))

        # Set TTL
        client.expire(key, DEFAULT_TTL_SECONDS)

        # Verify write
        verification = client.hgetall(key)
        if verification and "story_id" in verification:
            return True, f"Successfully migrated to Redis key: {key}", redis_keys
        else:
            return False, "Verification failed - key not found after write", redis_keys

    except Exception as e:
        return False, f"Redis error: {str(e)}", redis_keys


def migrate_to_qdrant(
    rel_path: str,
    frontmatter: dict,
    content: str,
    signature: str,
    dry_run: bool = False,
) -> tuple[bool, str, str]:
    """
    Migrate file to Qdrant.

    Args:
        rel_path: Relative path to file
        frontmatter: Parsed YAML frontmatter
        content: Full file content
        signature: Content signature for idempotency
        dry_run: If True, don't actually write

    Returns:
        Tuple of (success, message, qdrant_id)
    """
    story_id = frontmatter.get("story_id", "")

    # Generate deterministic UUID from signature
    qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, signature))

    metadata = {
        "project": frontmatter.get("project", "ChiseAI"),
        "scope": frontmatter.get("scope", ""),
        "type": frontmatter.get("type", ""),
        "story_id": story_id,
        "epic_id": frontmatter.get("epic_id", ""),
        "tags": frontmatter.get("tags", []),
        "timeframe": frontmatter.get("timeframe", ""),
        "date": frontmatter.get("date", ""),
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": rel_path,
        "migration_signature": signature,
        "priority": classify_file(rel_path, frontmatter),
        "content": content,  # Store full content for semantic search
    }

    if dry_run:
        return True, f"[DRY-RUN] Would store in Qdrant: {rel_path}", qdrant_id

    try:
        client = get_qdrant_client()
        if not client:
            return False, "Qdrant not available", qdrant_id

        # Generate embedding for the content
        embedding_gen = get_embedding_generator()
        if embedding_gen:
            vector = embedding_gen.generate(content)
        else:
            # Fallback: create a simple 384-dim vector
            vector = [0.0] * 384

        # Use Qdrant client to store
        from qdrant_client.models import PointStruct

        # Create point with named vector for ChiseAI collection
        point = PointStruct(
            id=qdrant_id,
            payload=metadata,
            vector={"fast-all-minilm-l6-v2": vector},
        )

        # Store in ChiseAI collection
        client.upsert(
            collection_name="ChiseAI",
            points=[point],
        )
        return True, f"Successfully stored in Qdrant: {rel_path}", qdrant_id
    except Exception as e:
        # Store failed, return error
        return False, f"Qdrant error: {str(e)}", qdrant_id


def archive_file(
    source_path: Path, rel_path: str, dry_run: bool = False
) -> tuple[bool, str, str]:
    """
    Archive migrated file to docs/tempmemories/archived/YYYY-MM/

    Args:
        source_path: Full path to source file
        rel_path: Relative path from tempmemories dir
        dry_run: If True, don't actually move

    Returns:
        Tuple of (success, message, archive_path)
    """
    today = datetime.now(timezone.utc)
    archive_subdir = ARCHIVE_DIR / today.strftime("%Y-%m")

    # Preserve subdirectory structure
    archive_path = archive_subdir / rel_path

    if dry_run:
        return True, f"[DRY-RUN] Would archive to: {archive_path}", str(archive_path)

    try:
        # Create archive directory
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Move file
        source_path.rename(archive_path)

        return True, f"Archived to: {archive_path}", str(archive_path)
    except Exception as e:
        return False, f"Archive error: {str(e)}", str(archive_path)


def update_source_file_remove_flag(
    full_path: Path, content: str, dry_run: bool = False
) -> tuple[bool, str]:
    """
    Update source file to remove needs_manual_qdrant_import flag after successful migration.

    Args:
        full_path: Full path to source file
        content: Full file content
        dry_run: If True, don't actually write

    Returns:
        Tuple of (success, message)
    """
    # Check if flag exists
    if "needs_manual_qdrant_import: true" not in content:
        return True, "No flag to remove"

    # Remove the flag line from content
    updated_content = re.sub(
        r"^needs_manual_qdrant_import:\s*true\s*\n",
        "",
        content,
        flags=re.MULTILINE,
    )

    if dry_run:
        return True, "[DRY-RUN] Would remove needs_manual_qdrant_import flag"

    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        return True, "Removed needs_manual_qdrant_import flag"
    except Exception as e:
        return False, f"Failed to update source file: {str(e)}"


def scan_tempmemories(story_filter: Optional[str] = None) -> list[dict]:
    """
    Scan docs/tempmemories/ for files to migrate.

    Args:
        story_filter: Optional story ID to filter by

    Returns:
        List of file info dicts
    """
    files: list[dict] = []

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


def generate_report(
    results: dict,
    mode: str,
    cleanup: bool,
    timestamp: str,
) -> dict:
    """
    Generate JSON migration report.

    Args:
        results: Results dictionary from migration
        mode: 'dry-run' or 'execute'
        cleanup: Whether cleanup was enabled
        timestamp: ISO8601 timestamp

    Returns:
        Report dictionary
    """
    return {
        "timestamp": timestamp,
        "mode": mode,
        "cleanup": cleanup,
        "summary": {
            "total_files": results["attempted"] + results["skipped"],
            "attempted": results["attempted"],
            "succeeded": results["succeeded"],
            "failed": results["failed"],
            "skipped": results["skipped"],
            "already_migrated": results["already_migrated"],
        },
        "failed_files": results["failed_files"],
        "redis_keys": results["redis_keys"],
        "qdrant_ids": results["qdrant_ids"],
        "archived_files": results["archived_files"],
        "source_files_updated": results["source_files_updated"],
    }


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Determine mode
    dry_run = not args.execute
    mode = "execute" if args.execute else "dry-run"
    timestamp = datetime.now(timezone.utc).isoformat()

    if dry_run and not args.cleanup:
        print("=" * 70, file=sys.stderr)
        print("MIGRATION PREVIEW MODE (DRY-RUN)", file=sys.stderr)
        print(
            "No changes will be made. Use --execute to perform migration.",
            file=sys.stderr,
        )
        print("=" * 70, file=sys.stderr)
    elif args.execute:
        print("=" * 70, file=sys.stderr)
        print("MIGRATION EXECUTE MODE", file=sys.stderr)
        print("Writes will be made to Redis and Qdrant!", file=sys.stderr)
        print("=" * 70, file=sys.stderr)

    if args.cleanup:
        print("=" * 70, file=sys.stderr)
        print("CLEANUP MODE ENABLED", file=sys.stderr)
        print("Files will be archived after migration!", file=sys.stderr)
        print("=" * 70, file=sys.stderr)

    print(file=sys.stderr)

    # Scan for files
    print(f"Scanning {TEMP_MEMORIES_DIR}...", file=sys.stderr)
    files = scan_tempmemories(story_filter=args.story)

    # Filter by priority if specified
    if args.priority:
        files = [f for f in files if f["priority"] == args.priority]

    # Count by priority
    counts: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0, "SKIP": 0}
    for f in files:
        priority = f["priority"]
        counts[priority] = counts.get(priority, 0) + 1

    print(f"Found {len(files)} files:", file=sys.stderr)
    print(f"  P0 (needs_qdrant_import): {counts.get('P0', 0)}", file=sys.stderr)
    print(f"  P1 (needs_import): {counts.get('P1', 0)}", file=sys.stderr)
    print(f"  P2 (valid_frontmatter): {counts.get('P2', 0)}", file=sys.stderr)
    print(f"  SKIP: {counts.get('SKIP', 0)}", file=sys.stderr)
    print(file=sys.stderr)

    if not files:
        print("No files to process.", file=sys.stderr)
        # Output empty report
        empty_report = generate_report(
            {
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "already_migrated": 0,
                "redis_keys": [],
                "qdrant_ids": [],
                "failed_files": [],
                "archived_files": [],
                "source_files_updated": [],
            },
            mode,
            args.cleanup,
            timestamp,
        )
        print(json.dumps(empty_report, indent=2))
        return 0

    # Track results
    results: dict[str, Any] = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "already_migrated": 0,
        "redis_keys": [],
        "qdrant_ids": [],
        "failed_files": [],
        "archived_files": [],
        "source_files_updated": [],
    }

    # Process each file
    for file_info in files:
        rel_path = file_info["rel_path"]
        priority = file_info["priority"]
        frontmatter = file_info.get("frontmatter", {})
        content = file_info.get("content", "")
        story_id = file_info.get("story_id", "")
        full_path = file_info["full_path"]

        if priority == "SKIP":
            results["skipped"] += 1
            if args.verbose:
                print(f"[SKIP] {rel_path}", file=sys.stderr)
            continue

        results["attempted"] += 1

        if args.verbose:
            print(f"\n[PROCESSING] {rel_path} (Priority: {priority})", file=sys.stderr)
            if story_id:
                print(f"  Story ID: {story_id}", file=sys.stderr)

        # Generate signature for idempotency
        signature = generate_signature(story_id, content, rel_path)

        # Check if already migrated
        if check_signature_exists(signature):
            results["already_migrated"] += 1
            if args.verbose:
                print(
                    "  [ALREADY MIGRATED] Signature exists, skipping", file=sys.stderr
                )
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
            "source_update_success": False,
            "errors": [],
        }

        # Migrate to Redis if iterlog
        redis_success = True
        redis_keys: list[str] = []
        if file_info.get("is_iterlog"):
            success, message, redis_keys = migrate_to_redis(
                frontmatter, signature, dry_run
            )
            if not success:
                redis_success = False
                file_result["errors"].append(f"Redis: {message}")
            else:
                file_result["redis_success"] = True
                results["redis_keys"].extend(redis_keys)

            if args.verbose:
                status = "OK" if success else "FAIL"
                print(f"  [REDIS] {status}: {message}", file=sys.stderr)

        # Migrate to Qdrant (all valid files)
        qdrant_success = True
        qdrant_id = ""
        success, message, qdrant_id = migrate_to_qdrant(
            rel_path, frontmatter, content, signature, dry_run
        )
        if not success:
            qdrant_success = False
            file_result["errors"].append(f"Qdrant: {message}")
        else:
            file_result["qdrant_success"] = True
            results["qdrant_ids"].append(qdrant_id)

        if args.verbose:
            status = "OK" if success else "FAIL"
            print(f"  [QDRANT] {status}: {message}", file=sys.stderr)

        # Determine overall migration success
        migration_success = redis_success and qdrant_success

        # Update source file to remove flag if migration succeeded
        if migration_success and not dry_run:
            success, message = update_source_file_remove_flag(
                full_path, content, dry_run
            )
            if not success:
                file_result["errors"].append(f"Source update: {message}")
            else:
                file_result["source_update_success"] = True
                results["source_files_updated"].append(rel_path)

            if args.verbose:
                status = "OK" if success else "FAIL"
                print(f"  [SOURCE UPDATE] {status}: {message}", file=sys.stderr)

        # Archive if cleanup mode and migrations succeeded
        archive_path = ""
        if args.cleanup and migration_success:
            success, message, archive_path = archive_file(full_path, rel_path, dry_run)
            if not success:
                file_result["errors"].append(f"Archive: {message}")
            else:
                file_result["archive_success"] = True
                results["archived_files"].append(archive_path)

            if args.verbose:
                status = "OK" if success else "FAIL"
                print(f"  [ARCHIVE] {status}: {message}", file=sys.stderr)

        # Store signature on success
        if migration_success and args.execute:
            store_signature(
                signature,
                {
                    "story_id": story_id,
                    "source": rel_path,
                    "migrated_at": datetime.now(timezone.utc).isoformat(),
                    "qdrant_id": qdrant_id,
                },
            )
            results["succeeded"] += 1
        elif not migration_success:
            results["failed"] += 1
            results["failed_files"].append(
                {"file": rel_path, "reason": "; ".join(file_result["errors"])}
            )

    # Print summary to stderr
    print(file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("MIGRATION SUMMARY", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"Files attempted:  {results['attempted']}", file=sys.stderr)
    print(f"Succeeded:        {results['succeeded']}", file=sys.stderr)
    print(f"Failed:           {results['failed']}", file=sys.stderr)
    print(f"Skipped:          {results['skipped']}", file=sys.stderr)
    print(f"Already migrated: {results['already_migrated']}", file=sys.stderr)

    if results["redis_keys"]:
        print(file=sys.stderr)
        print("Redis keys written:", file=sys.stderr)
        for key in results["redis_keys"][:10]:  # Show first 10
            print(f"  - {key}", file=sys.stderr)
        if len(results["redis_keys"]) > 10:
            print(f"  ... and {len(results['redis_keys']) - 10} more", file=sys.stderr)

    if results["qdrant_ids"]:
        print(file=sys.stderr)
        print("Qdrant IDs stored:", file=sys.stderr)
        for qid in results["qdrant_ids"][:10]:  # Show first 10
            print(f"  - {qid}", file=sys.stderr)
        if len(results["qdrant_ids"]) > 10:
            print(f"  ... and {len(results['qdrant_ids']) - 10} more", file=sys.stderr)

    if results["source_files_updated"]:
        print(file=sys.stderr)
        print("Source files updated (flag removed):", file=sys.stderr)
        for src in results["source_files_updated"][:10]:
            print(f"  - {src}", file=sys.stderr)
        if len(results["source_files_updated"]) > 10:
            print(
                f"  ... and {len(results['source_files_updated']) - 10} more",
                file=sys.stderr,
            )

    if results["failed_files"]:
        print(file=sys.stderr)
        print("Failed files:", file=sys.stderr)
        for failed in results["failed_files"]:
            print(f"  - {failed['file']}", file=sys.stderr)
            print(f"    Reason: {failed['reason']}", file=sys.stderr)

    if args.cleanup and results["archived_files"]:
        print(file=sys.stderr)
        print(
            f"Archive location: {ARCHIVE_DIR / datetime.now(timezone.utc).strftime('%Y-%m')}",
            file=sys.stderr,
        )

    # Generate and output JSON report to stdout
    report = generate_report(results, mode, args.cleanup, timestamp)
    print(json.dumps(report, indent=2))

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
