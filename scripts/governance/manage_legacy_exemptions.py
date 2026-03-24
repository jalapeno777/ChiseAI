#!/usr/bin/env python3
"""
Manage deterministic legacy exemption manifest for iterlog validation.

This script maintains docs/governance/legacy-exemptions.yaml so forward-strict
validation can remain non-blocking for historical artifacts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ITERLOG_DIR = Path("docs/tempmemories")
ITERLOG_GLOB = "iterlog-*.md"
MANIFEST_PATH = Path("docs/governance/legacy-exemptions.yaml")


@dataclass(frozen=True)
class IterlogRecord:
    path: Path
    story_id: str
    started_at: datetime | None
    legacy_exempt_flag: bool
    compliance_mode_legacy_exempt: bool
    is_archived: bool


def _read_frontmatter(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    raw_yaml = text[4:end]
    data = yaml.safe_load(raw_yaml) or {}
    if isinstance(data, dict):
        return data
    return {}


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Normalize Zulu suffix for fromisoformat.
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iterlog_story_id(path: Path, frontmatter: dict[str, Any]) -> str:
    story_id = str(frontmatter.get("story_id", "")).strip()
    if story_id:
        return story_id
    stem = path.stem
    if stem.startswith("iterlog-"):
        return stem.replace("iterlog-", "", 1).strip()
    return ""


def _collect_iterlogs() -> list[IterlogRecord]:
    if not ITERLOG_DIR.exists():
        return []
    records: list[IterlogRecord] = []
    for path in sorted(ITERLOG_DIR.rglob(ITERLOG_GLOB)):
        fm = _read_frontmatter(path)
        story_id = _iterlog_story_id(path, fm)
        if not story_id:
            continue
        rel = path.as_posix()
        records.append(
            IterlogRecord(
                path=path,
                story_id=story_id,
                started_at=_parse_dt(fm.get("started_at")),
                legacy_exempt_flag=_to_bool(fm.get("legacy_exempt")),
                compliance_mode_legacy_exempt=str(fm.get("compliance_mode", ""))
                .strip()
                .lower()
                == "legacy_exempt",
                is_archived="/archived/" in rel,
            )
        )
    return records


def _load_existing_manifest() -> tuple[set[str], dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return set(), {}
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return set(), {}
    story_ids = data.get("iterlog_story_ids", [])
    if not isinstance(story_ids, list):
        story_ids = []
    cleaned = {str(item).strip() for item in story_ids if str(item).strip()}
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return cleaned, metadata


def _write_manifest(story_ids: list[str], generated_from: str, owner: str) -> None:
    metadata = {
        "owner": owner,
        "updated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": "strict_forward_with_legacy_exemptions",
        "generated_from": generated_from,
        "count": len(story_ids),
    }
    payload = {"iterlog_story_ids": story_ids, "metadata": metadata}
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _build_set(
    records: list[IterlogRecord],
    *,
    bootstrap_all: bool,
    cutoff_date: datetime | None,
    include_archived: bool,
    include_marked_legacy: bool,
    include_existing: bool,
) -> tuple[set[str], str]:
    selected: set[str] = set()
    source_parts: list[str] = []

    if include_existing:
        existing, _ = _load_existing_manifest()
        selected |= existing
        source_parts.append("existing_manifest")

    if bootstrap_all:
        selected |= {r.story_id for r in records}
        source_parts.append("bootstrap_all")
        return selected, "+".join(source_parts)

    if cutoff_date is not None:
        cutoff_selected = {
            r.story_id
            for r in records
            if r.started_at is not None and r.started_at <= cutoff_date
        }
        selected |= cutoff_selected
        source_parts.append(f"cutoff:{cutoff_date.date().isoformat()}")

    if include_archived:
        selected |= {r.story_id for r in records if r.is_archived}
        source_parts.append("archived")

    if include_marked_legacy:
        selected |= {
            r.story_id
            for r in records
            if r.legacy_exempt_flag or r.compliance_mode_legacy_exempt
        }
        source_parts.append("frontmatter_legacy")

    if not source_parts:
        source_parts.append("no_selection")
    return selected, "+".join(source_parts)


def _parse_cutoff(cutoff_date: str | None) -> datetime | None:
    if not cutoff_date:
        return None
    # Use end-of-day UTC to avoid accidental exclusion.
    day = datetime.strptime(cutoff_date, "%Y-%m-%d").replace(tzinfo=UTC)
    return day.replace(hour=23, minute=59, second=59)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maintain docs/governance/legacy-exemptions.yaml deterministically."
    )
    parser.add_argument(
        "--bootstrap-all",
        action="store_true",
        help="Include all current iterlog story IDs (baseline bootstrap).",
    )
    parser.add_argument(
        "--cutoff-date",
        help="Include iterlogs with started_at <= YYYY-MM-DD (UTC).",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        default=True,
        help="Include story IDs from docs/tempmemories/archived (default: true).",
    )
    parser.add_argument(
        "--no-include-archived",
        dest="include_archived",
        action="store_false",
        help="Do not include archived iterlogs by default.",
    )
    parser.add_argument(
        "--include-marked-legacy",
        action="store_true",
        default=True,
        help="Include frontmatter-marked legacy iterlogs (default: true).",
    )
    parser.add_argument(
        "--no-include-marked-legacy",
        dest="include_marked_legacy",
        action="store_false",
        help="Ignore frontmatter-marked legacy fields.",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        default=True,
        help="Keep current manifest story IDs unless explicitly disabled (default: true).",
    )
    parser.add_argument(
        "--no-include-existing",
        dest="include_existing",
        action="store_false",
        help="Do not merge existing manifest IDs.",
    )
    parser.add_argument(
        "--owner",
        default="governance",
        help="metadata.owner value (default: governance).",
    )
    parser.add_argument(
        "--generated-from",
        default="legacy_exemption_maintenance",
        help="metadata.generated_from label for audit provenance.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resulting manifest summary without writing.",
    )
    args = parser.parse_args()

    cutoff = _parse_cutoff(args.cutoff_date)
    records = _collect_iterlogs()
    selected, source = _build_set(
        records,
        bootstrap_all=args.bootstrap_all,
        cutoff_date=cutoff,
        include_archived=args.include_archived,
        include_marked_legacy=args.include_marked_legacy,
        include_existing=args.include_existing,
    )

    story_ids = sorted(selected)
    generated_from = f"{args.generated_from}:{source}"

    if args.dry_run:
        print(f"mode={generated_from}")
        print(f"iterlog_count={len(records)}")
        print(f"manifest_count={len(story_ids)}")
        print("first_10=" + ",".join(story_ids[:10]))
        return 0

    _write_manifest(story_ids, generated_from=generated_from, owner=args.owner)
    print(
        f"Updated {MANIFEST_PATH} with {len(story_ids)} story IDs "
        f"(source={generated_from})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
