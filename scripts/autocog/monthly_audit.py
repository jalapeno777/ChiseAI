#!/usr/bin/env python3
"""
Autocog Monthly Audit Script.

Performs a complete state audit of the autocog system:
1. Scans all Redis keys in the bmad:chiseai:* namespace
2. Collects all metacog dimensions (predictions, outcomes, calibrations)
3. Normalizes lessons from docs/tempmemories/lessons.md (aggregate by fingerprint, dedup)
4. Promotes durable learnings to Qdrant (ChiseAI collection)
5. Writes full cycle JSON to _bmad-output/autocog/cycles/{date}-full-cycle.json

Usage:
    python scripts/autocog/monthly_audit.py [--dry-run] [--redis-url URL] [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Constants
REDIS_URL = os.environ.get("REDIS_URL", "redis://host.docker.internal:6380/1")
REDIS_KEY_PREFIX = "bmad:chiseai"
CYCLES_DIR = Path("_bmad-output/autocog/cycles")
LESSONS_FILE = Path("docs/tempmemories/lessons.md")
QDRANT_COLLECTION = "ChiseAI"

# Try to import optional dependencies
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MetacogDimension:
    """A single metacog prediction or outcome record."""

    story_id: str
    key_type: str  # "prediction" or "outcome"
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedLesson:
    """A deduplicated lesson with fingerprint."""

    id: str
    fingerprint: str
    context: str = ""
    trigger: str = ""
    actionable_rule: str = ""
    applies_to: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    evidence_ref: str = ""
    added_utc: str = ""
    supersedes: str = ""
    occurrence_count: int = 1
    superseded_by: str = ""


@dataclass
class DeferredItem:
    """A deferred item from autocog cycles."""

    cycle_id: str
    item_type: str
    description: str
    deferred_at: str = ""
    status: str = "pending"


@dataclass
class MonthlyAuditResult:
    """Complete monthly audit result."""

    timestamp: str = ""
    dry_run: bool = False
    redis_available: bool = False
    qdrant_available: bool = False
    all_redis_keys: list[str] = field(default_factory=list)
    all_metacog_dimensions: list[dict[str, Any]] = field(default_factory=list)
    lessons_normalized: list[dict[str, Any]] = field(default_factory=list)
    lessons_duplicate_count: int = 0
    durable_learnings_promoted: int = 0
    deferred_items_status: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def get_repo_root() -> Path:
    """Get the repository root directory."""
    env_root = Path(__file__).resolve().parent.parent.parent
    marker = env_root / "pyproject.toml"
    if marker.exists():
        return env_root
    return Path.cwd()


def fingerprint_lesson(context: str, trigger: str, actionable_rule: str) -> str:
    """
    Generate a stable fingerprint for deduplication.

    Uses normalized (lowercased, stripped) context + trigger + actionable_rule.
    """
    raw = f"{context.strip().lower()}|{trigger.strip().lower()}|{actionable_rule.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Redis audit
# ---------------------------------------------------------------------------


def scan_redis_keys(redis_url: str, pattern: str = "bmad:chiseai:*") -> list[str]:
    """
    Scan all Redis keys matching the given pattern using SCAN.

    Returns list of key names.
    """
    if not REDIS_AVAILABLE:
        return []

    client = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
    client.ping()

    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = client.scan(cursor=cursor, match=pattern, count=500)
        keys.extend(k.decode("utf-8") if isinstance(k, bytes) else k for k in batch)
        if cursor == 0:
            break

    return sorted(keys)


def collect_metacog_dimensions(
    redis_url: str, keys: list[str]
) -> list[MetacogDimension]:
    """
    Extract metacog prediction and outcome records from Redis keys.

    Looks for keys matching:
      - bmad:chiseai:metacog:prediction:story:<story_id>
      - bmad:chiseai:metacog:outcome:story:<story_id>
      - bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<week>
    """
    if not REDIS_AVAILABLE or not keys:
        return []

    client = redis.Redis.from_url(redis_url, socket_connect_timeout=5)

    dimensions: list[MetacogDimension] = []
    metacog_pattern = re.compile(
        r"^bmad:chiseai:metacog:(prediction|outcome|calibration)(?::.+)$"
    )

    for key in keys:
        m = metacog_pattern.match(key)
        if not m:
            continue

        key_type = m.group(1)

        try:
            key_type_actual = (
                client.type(key).decode("utf-8")
                if isinstance(client.type(key), bytes)
                else client.type(key)
            )

            if key_type_actual == "hash":
                raw_fields = client.hgetall(key)
                fields = {
                    (k.decode("utf-8") if isinstance(k, bytes) else k): (
                        v.decode("utf-8") if isinstance(v, bytes) else v
                    )
                    for k, v in raw_fields.items()
                }
            elif key_type_actual == "string":
                val = client.get(key)
                fields = {
                    "value": val.decode("utf-8") if isinstance(val, bytes) else val
                }
            else:
                fields = {"type": key_type_actual}

            # Extract story_id or identifier from the key
            story_id = key.split(":")[-1] if key else "unknown"

            dimensions.append(
                MetacogDimension(
                    story_id=story_id,
                    key_type=key_type,
                    fields=fields,
                )
            )
        except Exception as e:
            dimensions.append(
                MetacogDimension(
                    story_id=key.split(":")[-1] if key else "unknown",
                    key_type=key_type,
                    fields={"error": str(e)},
                )
            )

    return dimensions


# ---------------------------------------------------------------------------
# Lessons normalization
# ---------------------------------------------------------------------------


LESSON_BLOCK_RE = re.compile(r"```text\s*\nLESSON\s*\n(.*?)```", re.DOTALL)

LESSON_FIELD_RE = re.compile(r"-\s*(\w[\w-]*):\s*(.*)")

# Matches indented list items like "  - jarvis" or "  - senior-dev"
LESSON_LIST_ITEM_RE = re.compile(r"^\s+-\s+(.+)$", re.MULTILINE)


def parse_lessons_file(lessons_path: Path) -> list[dict[str, Any]]:
    """
    Parse all LESSON blocks from lessons.md.

    Returns list of raw lesson dicts with their fields.
    Handles multi-line list fields (e.g., applies_to) by collecting
    indented items that follow the field header.
    """
    if not lessons_path.exists():
        return []

    content = lessons_path.read_text(encoding="utf-8")
    blocks = LESSON_BLOCK_RE.findall(content)

    lessons: list[dict[str, Any]] = []
    for block_text in blocks:
        lesson: dict[str, Any] = {}
        last_list_field: str | None = None

        for line in block_text.splitlines():
            stripped = line.strip()

            # Try field match first (e.g., "- applies_to:")
            field_match = LESSON_FIELD_RE.match(stripped)
            if field_match:
                field_name = field_match.group(1).strip()
                field_value = field_match.group(2).strip()

                if field_name == "applies_to":
                    # Start collecting list items
                    lesson[field_name] = []
                    last_list_field = field_name
                    if field_value:  # Inline value like "- applies_to: aria"
                        lesson[field_name].append(field_value)
                else:
                    lesson[field_name] = field_value
                    last_list_field = None
                continue

            # Try list item match (e.g., "  - jarvis")
            if last_list_field:
                list_match = LESSON_LIST_ITEM_RE.match(line)
                if list_match:
                    item_value = list_match.group(1).strip()
                    lesson[last_list_field].append(item_value)
                    continue

            # Non-matching line: stop collecting list items
            last_list_field = None

        if lesson.get("id"):
            lessons.append(lesson)

    return lessons


def normalize_and_dedup_lessons(
    raw_lessons: list[dict[str, Any]],
) -> tuple[list[NormalizedLesson], int]:
    """
    Normalize and deduplicate lessons by fingerprint.

    Returns (normalized_lessons, duplicate_count).
    Keeps the most recent version of each unique lesson.
    """
    fingerprint_map: dict[str, NormalizedLesson] = {}
    duplicate_count = 0

    for raw in raw_lessons:
        context = raw.get("context", "")
        trigger = raw.get("trigger", "")
        actionable_rule = raw.get("actionable_rule", "")

        fp = fingerprint_lesson(context, trigger, actionable_rule)

        if fp in fingerprint_map:
            # Check if this one is newer
            existing = fingerprint_map[fp]
            new_utc = raw.get("added_utc", "")
            old_utc = existing.added_utc
            if new_utc and old_utc and new_utc > old_utc:
                # Replace with newer version, mark old as superseded
                existing.superseded_by = raw.get("id", "")
                existing.occurrence_count += 1
            else:
                existing.occurrence_count += 1
                # Mark new one as superseded
                raw["superseded_by"] = existing.id
            duplicate_count += 1
        else:
            applies_to = raw.get("applies_to", [])
            if isinstance(applies_to, str):
                applies_to = [applies_to]

            fingerprint_map[fp] = NormalizedLesson(
                id=raw.get("id", ""),
                fingerprint=fp,
                context=context,
                trigger=trigger,
                actionable_rule=actionable_rule,
                applies_to=applies_to,
                expected_outcome=raw.get("expected_outcome", ""),
                evidence_ref=raw.get("evidence_ref", ""),
                added_utc=raw.get("added_utc", ""),
                supersedes=raw.get("supersedes", ""),
                occurrence_count=1,
            )

    return list(fingerprint_map.values()), duplicate_count


# ---------------------------------------------------------------------------
# Qdrant promotion
# ---------------------------------------------------------------------------


def promote_to_qdrant(
    lessons: list[NormalizedLesson],
    dry_run: bool = False,
    qdrant_url: str = "http://localhost:6333",
) -> int:
    """
    Promote durable learnings to Qdrant ChiseAI collection.

    Only promotes lessons that are:
    - Not superseded
    - Have actionable_rule and context

    Returns count of promoted learnings.
    """
    if not QDRANT_AVAILABLE:
        return 0

    client = QdrantClient(url=qdrant_url, timeout=10)

    # Verify collection exists
    try:
        collections = [c.name for c in client.get_collections().collections]
        if QDRANT_COLLECTION not in collections:
            return 0
    except Exception:
        return 0

    promoted = 0
    for lesson in lessons:
        # Skip superseded or incomplete lessons
        if lesson.superseded_by or not lesson.actionable_rule or not lesson.context:
            continue

        if dry_run:
            promoted += 1
            continue

        try:
            # Use the fingerprint as the point ID (deterministic)
            point_id = int(
                hashlib.md5(lesson.fingerprint.encode()).hexdigest()[:16], 16
            ) % (2**63)

            # Create a deterministic pseudo-vector from the fingerprint
            # (384 dimensions matching ChiseAI collection)
            seed = int(lesson.fingerprint, 16)
            vector = []
            for i in range(384):
                val = ((seed * (i + 1) * 2654435761) % (2**32)) / (2**32) * 2 - 1
                vector.append(val)

            client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "project": "ChiseAI",
                            "scope": "autocog",
                            "type": "lesson",
                            "lesson_id": lesson.id,
                            "fingerprint": lesson.fingerprint,
                            "actionable_rule": lesson.actionable_rule,
                            "occurrence_count": lesson.occurrence_count,
                            "added_utc": lesson.added_utc,
                        },
                    )
                ],
            )
            promoted += 1
        except Exception as e:
            # Log but don't fail the whole audit
            print(
                f"Warning: Failed to promote lesson {lesson.id}: {e}", file=sys.stderr
            )

    return promoted


# ---------------------------------------------------------------------------
# Deferred items
# ---------------------------------------------------------------------------


def collect_deferred_items(cycles_dir: Path) -> list[DeferredItem]:
    """
    Collect deferred items from autocog cycle artifacts.

    Looks for cycles with rejections or skipped experiments that represent
    deferred work items.
    """
    if not cycles_dir.exists():
        return []

    items: list[DeferredItem] = []
    cycle_files = sorted(cycles_dir.glob("autocog-*.json"))

    for cf in cycle_files:
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))

            # Check for rejections (deferred promotions)
            rejections = data.get("rejections", [])
            for rej in rejections:
                if isinstance(rej, dict):
                    items.append(
                        DeferredItem(
                            cycle_id=data.get("run_id", cf.stem),
                            item_type="rejection",
                            description=rej.get("reason", str(rej)),
                            deferred_at=data.get("completed_at", ""),
                        )
                    )

            # Check for candidate_skips
            metrics = data.get("metrics", {})
            skip_check = metrics.get("skip_rate_check", {})
            if skip_check.get("alert_triggered", False):
                items.append(
                    DeferredItem(
                        cycle_id=data.get("run_id", cf.stem),
                        item_type="skip_rate_alert",
                        description=f"Skip rate: {skip_check.get('skip_rate', 'N/A')} "
                        f"(threshold: {skip_check.get('threshold', 'N/A')})",
                        deferred_at=data.get("completed_at", ""),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            continue

    return items


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------


def run_monthly_audit(
    dry_run: bool = False,
    redis_url: str = REDIS_URL,
    repo_root: Path | None = None,
    qdrant_url: str = "http://localhost:6333",
) -> MonthlyAuditResult:
    """
    Run the complete monthly audit.

    Returns a MonthlyAuditResult with all collected data.
    """
    result = MonthlyAuditResult(
        timestamp=datetime.now(UTC).isoformat(),
        dry_run=dry_run,
    )

    if repo_root is None:
        repo_root = get_repo_root()

    # --- Phase 1: Redis state audit ---
    if REDIS_AVAILABLE:
        try:
            result.redis_available = True
            result.all_redis_keys = scan_redis_keys(redis_url, f"{REDIS_KEY_PREFIX}:*")
            metacog_dims = collect_metacog_dimensions(redis_url, result.all_redis_keys)
            result.all_metacog_dimensions = [
                {
                    "story_id": d.story_id,
                    "key_type": d.key_type,
                    "fields": d.fields,
                }
                for d in metacog_dims
            ]
        except Exception as e:
            result.redis_available = False
            result.errors.append(f"Redis audit failed: {e}")
    else:
        result.warnings.append("Redis library not available; skipping Redis audit")

    # --- Phase 2: Lessons normalization ---
    lessons_path = repo_root / LESSONS_FILE
    raw_lessons = parse_lessons_file(lessons_path)
    normalized, dup_count = normalize_and_dedup_lessons(raw_lessons)
    result.lessons_normalized = [asdict(lesson) for lesson in normalized]
    result.lessons_duplicate_count = dup_count

    # --- Phase 3: Qdrant promotion ---
    if QDRANT_AVAILABLE:
        try:
            result.qdrant_available = True
            result.durable_learnings_promoted = promote_to_qdrant(
                normalized, dry_run=dry_run, qdrant_url=qdrant_url
            )
        except Exception as e:
            result.qdrant_available = False
            result.errors.append(f"Qdrant promotion failed: {e}")
    else:
        result.warnings.append(
            "Qdrant client not available; skipping promotion "
            "(set needs_manual_qdrant_import on fallback)"
        )

    # --- Phase 4: Deferred items ---
    cycles_dir = repo_root / CYCLES_DIR
    deferred = collect_deferred_items(cycles_dir)
    result.deferred_items_status = [asdict(d) for d in deferred]

    return result


def write_audit_result(
    result: MonthlyAuditResult, repo_root: Path | None = None
) -> Path:
    """
    Write the audit result JSON to the cycles directory.

    Returns the path to the written file.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    cycles_dir = repo_root / CYCLES_DIR
    cycles_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = cycles_dir / f"{date_str}-full-cycle.json"

    output_data = asdict(result)
    output_path.write_text(
        json.dumps(output_data, indent=2, default=str), encoding="utf-8"
    )

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autocog Monthly Audit - complete state audit and learning promotion"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run audit without writing output or promoting to Qdrant",
    )
    parser.add_argument(
        "--redis-url",
        default=REDIS_URL,
        help=f"Redis connection URL (default: {REDIS_URL})",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Path to repository root (auto-detected if not provided)",
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant server URL (default: http://localhost:6333)",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Custom output file path (default: _bmad-output/autocog/cycles/{date}-full-cycle.json)",
    )

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root()

    print(f"Monthly Audit - {datetime.now(UTC).isoformat()}")
    print(f"Repo root: {repo_root}")
    print(f"Dry run: {args.dry_run}")
    print()

    result = run_monthly_audit(
        dry_run=args.dry_run,
        redis_url=args.redis_url,
        repo_root=repo_root,
        qdrant_url=args.qdrant_url,
    )

    # Summary output
    print(f"Redis available: {result.redis_available}")
    print(f"Qdrant available: {result.qdrant_available}")
    print(f"Redis keys found: {len(result.all_redis_keys)}")
    print(f"Metacog dimensions: {len(result.all_metacog_dimensions)}")
    print(f"Lessons normalized: {len(result.lessons_normalized)}")
    print(f"Lessons duplicates: {result.lessons_duplicate_count}")
    print(f"Durable learnings promoted: {result.durable_learnings_promoted}")
    print(f"Deferred items: {len(result.deferred_items_status)}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  - {w}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for e in result.errors:
            print(f"  - {e}")

    if not args.dry_run:
        if args.output_file:
            output_path = Path(args.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path = write_audit_result(result, repo_root)

        output_data = asdict(result)
        output_path.write_text(
            json.dumps(output_data, indent=2, default=str), encoding="utf-8"
        )
        print(f"\nOutput written to: {output_path}")
    else:
        print("\n[DRY RUN] No output written, no Qdrant promotion performed")

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
