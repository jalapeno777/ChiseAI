#!/usr/bin/env python3
"""Archive old workflow status items (stories + epics) with lean stubs.

Default mode is dry-run. Use --execute to persist changes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

WORKFLOW_FILE = Path("docs/bmm-workflow-status.yaml")
ARCHIVE_DIR = Path("docs/archives/workflow-status/entries")
ARCHIVE_INDEX_FILE = Path("docs/archives/workflow-status/archive-index.yaml")
RETENTION_DAYS_DEFAULT = 7
ARCHIVE_SCHEMA_VERSION = "1.0.0"
MIGRATION_SCRIPT_VERSION = "1.1.0"

STORY_SECTIONS = ["completed", "backlog", "launch_stories"]
EPIC_SECTION = "epics"

STORY_STUB_FIELDS = [
    "id",
    "status",
    "title",
    "priority",
    "epic_id",
    "completion_date",
    "merge_commit",
    "pr_number",
]

EPIC_STUB_FIELDS = [
    "id",
    "status",
    "name",
    "title",
    "completion_date",
    "story_count",
    "story_points",
    "sprint_id",
]

COMPLETION_EVIDENCE_FIELDS = [
    "pr_number",
    "merge_commit",
    "pr_numbers",
    "merge_commits",
    "commit_sha",
    "evidence_files",
    "ci_evidence",
]


@dataclass
class Candidate:
    item_id: str
    item_type: str
    section: str
    index: int
    age_days: int
    completion_date: str
    status: str
    title: str


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping root in {path}")
    return data


def _dump_yaml(data: Any) -> str:
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _create_backup(path: Path) -> Path:
    stamp = _now_utc().strftime("%Y%m%d%H%M%S")
    backup = path.parent / f"{path.name}.backup.archive.{stamp}"
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") if text.endswith("\n") else text.count("\n") + 1


def _parse_date(date_str: Any) -> datetime | None:
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _story_date_map(data: dict[str, Any]) -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    for section in STORY_SECTIONS:
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                continue
            dt = _parse_date(
                item.get("completion_date")
                or item.get("completed_date")
                or item.get("merged_date")
                or item.get("created_date")
            )
            if dt and (item_id not in out or dt > out[item_id]):
                out[item_id] = dt
    return out


def _get_completion_dt(item: dict[str, Any], item_type: str, story_dates: dict[str, datetime]) -> datetime | None:
    direct = _parse_date(
        item.get("completion_date")
        or item.get("completed_date")
        or item.get("merged_date")
        or item.get("created_date")
    )
    if direct:
        return direct

    if item_type != "epic":
        return None

    story_ids = item.get("story_ids")
    if not isinstance(story_ids, list):
        return None

    candidates = [story_dates.get(str(story_id)) for story_id in story_ids]
    candidates = [d for d in candidates if d is not None]
    if not candidates:
        return None
    return max(candidates)


def _should_archive(item: dict[str, Any], item_type: str, retention_days: int, now: datetime, story_dates: dict[str, datetime]) -> tuple[bool, str, int | None, datetime | None]:
    if item.get("archive_ref"):
        return False, "already archived", None, None

    status = str(item.get("status", "")).strip().lower()
    if item_type == "epic":
        allowed = {"completed", "merged"}
    else:
        allowed = {"completed", "merged", "cancelled"}

    if status not in allowed:
        return False, f"status '{status}' not eligible", None, None

    completion_dt = _get_completion_dt(item, item_type, story_dates)
    if not completion_dt:
        return False, "missing completion date", None, None

    age_days = (now - completion_dt).days
    if age_days <= retention_days:
        return False, f"age {age_days}d <= threshold {retention_days}d", age_days, completion_dt

    return True, "age", age_days, completion_dt


def _has_completion_evidence(item: dict[str, Any]) -> bool:
    """Return True when completion evidence exists for an item."""

    def _valid_scalar(val: Any) -> bool:
        if val is None:
            return False
        s = str(val).strip()
        return s not in {"", "N/A", "LEGACY"}

    if _valid_scalar(item.get("pr_number")):
        return True
    if _valid_scalar(item.get("merge_commit")):
        return True

    pr_numbers = item.get("pr_numbers")
    if isinstance(pr_numbers, list) and any(_valid_scalar(v) for v in pr_numbers):
        return True

    merge_commits = item.get("merge_commits")
    if isinstance(merge_commits, list) and any(_valid_scalar(v) for v in merge_commits):
        return True

    completion_evidence = item.get("completion_evidence")
    if isinstance(completion_evidence, dict) and completion_evidence:
        return True

    return False


def _title_for(item: dict[str, Any], item_type: str) -> str:
    if item_type == "epic":
        return str(item.get("title") or item.get("name") or item.get("id") or "(untitled)")
    return str(item.get("title") or item.get("name") or item.get("id") or "(untitled)")


def _make_archive_ref(item_id: str) -> str:
    ts = _now_utc().strftime("%Y%m%d-%H%M%S")
    return f"ARCH-{ts}-{item_id}"


def _checksum(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_stub(item: dict[str, Any], item_type: str, archive_ref: str, completion_dt: datetime | None) -> dict[str, Any]:
    fields = EPIC_STUB_FIELDS if item_type == "epic" else STORY_STUB_FIELDS
    stub: dict[str, Any] = {"archive_ref": archive_ref}

    for field in fields:
        if field in item:
            stub[field] = item[field]

    if "title" not in stub:
        derived_title = _title_for(item, item_type)
        stub["title"] = derived_title
    if item_type == "epic" and "name" not in stub:
        stub["name"] = str(item.get("name") or stub.get("title"))

    if completion_dt and "completion_date" not in stub:
        stub["completion_date"] = completion_dt.date().isoformat()

    stub["id"] = item.get("id")
    stub["status"] = "archived"
    return stub


def _build_archive_entry(
    item: dict[str, Any],
    item_type: str,
    section: str,
    archive_ref: str,
    reason: str,
    reason_detail: str,
    stub: dict[str, Any],
    migrated_by: str,
    archive_dir: Path,
) -> dict[str, Any]:
    preserved = set(stub.keys())
    preserved.discard("archive_ref")

    archived_fields: dict[str, Any] = {}
    for key, value in item.items():
        if key not in preserved and key != "archive_ref":
            archived_fields[key] = value

    completion_evidence = {k: item[k] for k in COMPLETION_EVIDENCE_FIELDS if k in item}

    entry: dict[str, Any] = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "archive_ref": archive_ref,
        "original_story_id": item.get("id"),
        "item_type": item_type,
        "source_section": section,
        "archived_at": _now_utc().isoformat().replace("+00:00", "Z"),
        "archive_reason": reason,
        "archive_reason_detail": reason_detail,
        "migration": {
            "phase": "batch_auto",
            "migrated_by": migrated_by,
            "migration_script_version": MIGRATION_SCRIPT_VERSION,
            "verification_status": "verified",
        },
        "lean_status": stub,
        "archived_fields": archived_fields,
        "completion_evidence": completion_evidence or None,
        "archive_location": f"{archive_dir}/{archive_ref}.yaml",
        "integrity": {
            "original_checksum": _checksum(item),
            "archived_checksum": None,
            "verification_date": _now_utc().isoformat().replace("+00:00", "Z"),
        },
    }

    entry["integrity"]["archived_checksum"] = _checksum(entry)
    return entry


def _collect_candidates(
    data: dict[str, Any],
    retention_days: int,
    ids_filter: set[str] | None,
    require_completion_evidence: bool = False,
) -> tuple[list[Candidate], dict[str, Any]]:
    now = _now_utc()
    story_dates = _story_date_map(data)

    candidates: list[Candidate] = []
    skipped: list[dict[str, Any]] = []

    def consider(section: str, item: Any, idx: int, item_type: str) -> None:
        if not isinstance(item, dict):
            return
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            return

        if ids_filter and item_id not in ids_filter:
            skipped.append({"id": item_id, "section": section, "reason": "not in --id filter"})
            return

        should, reason, age_days, completion_dt = _should_archive(
            item=item,
            item_type=item_type,
            retention_days=retention_days,
            now=now,
            story_dates=story_dates,
        )
        if not should:
            skipped.append({"id": item_id, "section": section, "reason": reason})
            return
        if require_completion_evidence and not _has_completion_evidence(item):
            skipped.append(
                {
                    "id": item_id,
                    "section": section,
                    "reason": "missing completion evidence",
                }
            )
            return

        candidates.append(
            Candidate(
                item_id=item_id,
                item_type=item_type,
                section=section,
                index=idx,
                age_days=int(age_days or 0),
                completion_date=(completion_dt.date().isoformat() if completion_dt else ""),
                status=str(item.get("status", "")),
                title=_title_for(item, item_type),
            )
        )

    for section in STORY_SECTIONS:
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            consider(section, item, idx, "story")

    epic_items = data.get(EPIC_SECTION, [])
    if isinstance(epic_items, list):
        for idx, item in enumerate(epic_items):
            consider(EPIC_SECTION, item, idx, "epic")

    return candidates, {"skipped": skipped}


def _archive(
    workflow_file: Path,
    archive_dir: Path,
    retention_days: int,
    ids: list[str],
    batch_size: int,
    execute: bool,
    migrated_by: str,
    require_completion_evidence: bool = False,
    update_index: bool = False,
    archive_index_file: Path = ARCHIVE_INDEX_FILE,
) -> dict[str, Any]:
    original_text = workflow_file.read_text(encoding="utf-8")
    before_lines = _count_lines(original_text)

    data = _load_yaml(workflow_file)
    working = copy.deepcopy(data)

    ids_filter = {x.strip() for x in ids if x.strip()} if ids else None
    candidates, aux = _collect_candidates(
        working,
        retention_days,
        ids_filter,
        require_completion_evidence=require_completion_evidence,
    )

    if batch_size > 0:
        selected = candidates[:batch_size]
    else:
        selected = candidates

    archived_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for c in selected:
        section_items = working.get(c.section)
        if not isinstance(section_items, list) or c.index >= len(section_items):
            errors.append({"id": c.item_id, "error": "index mismatch in section"})
            continue

        item = section_items[c.index]
        if not isinstance(item, dict):
            errors.append({"id": c.item_id, "error": "item is not mapping"})
            continue

        archive_ref = _make_archive_ref(c.item_id)
        completion_dt = _parse_date(
            item.get("completion_date")
            or item.get("completed_date")
            or item.get("merged_date")
            or item.get("created_date")
        )
        if c.item_type == "epic" and not completion_dt:
            story_dates = _story_date_map(working)
            completion_dt = _get_completion_dt(item, "epic", story_dates)

        stub = _build_stub(item, c.item_type, archive_ref, completion_dt)
        detail = (
            f"Item completed {c.age_days} days ago, exceeds {retention_days}-day threshold"
        )
        archive_entry = _build_archive_entry(
            item=item,
            item_type=c.item_type,
            section=c.section,
            archive_ref=archive_ref,
            reason="age",
            reason_detail=detail,
            stub=stub,
            migrated_by=migrated_by,
            archive_dir=archive_dir,
        )

        section_items[c.index] = stub

        archived_records.append(
            {
                "id": c.item_id,
                "item_type": c.item_type,
                "section": c.section,
                "title": c.title,
                "age_days": c.age_days,
                "completion_date": c.completion_date,
                "archive_ref": archive_ref,
                "archive_path": str(archive_dir / f"{archive_ref}.yaml"),
                "stub": stub,
                "archive_entry": archive_entry,
            }
        )

    projected_text = _dump_yaml(working)
    projected_lines = _count_lines(projected_text)
    line_reduction = before_lines - projected_lines
    line_reduction_pct = round((line_reduction / before_lines) * 100, 2) if before_lines else 0.0

    backup_path = None
    index_updated = 0
    write_errors: list[dict[str, str]] = []
    if execute and archived_records:
        archive_dir.mkdir(parents=True, exist_ok=True)

        for rec in archived_records:
            archive_path = Path(rec["archive_path"])
            if archive_path.exists():
                write_errors.append(
                    {"id": rec["id"], "error": f"archive exists: {archive_path}"}
                )
                continue
            try:
                _atomic_write(archive_path, _dump_yaml(rec["archive_entry"]))
            except Exception as exc:  # pragma: no cover - filesystem failure path
                write_errors.append(
                    {"id": rec["id"], "error": f"failed to write archive: {exc}"}
                )

        if write_errors:
            errors.extend(write_errors)
        else:
            if update_index:
                index_updated = _append_archive_index(
                    archive_index_file=archive_index_file,
                    archived_records=archived_records,
                )
            backup_path = str(_create_backup(workflow_file))
            _atomic_write(workflow_file, projected_text)

    workflow_updated = bool(execute and archived_records and not errors)
    committed_records = archived_records if (not execute or workflow_updated) else []

    actual_lines_after = projected_lines
    if execute:
        actual_lines_after = _count_lines(workflow_file.read_text(encoding="utf-8"))

    stories_archived = sum(1 for r in committed_records if r["item_type"] == "story")
    epics_archived = sum(1 for r in committed_records if r["item_type"] == "epic")

    result = {
        "mode": "execute" if execute else "dry_run",
        "workflow_file": str(workflow_file),
        "archive_dir": str(archive_dir),
        "retention_days": retention_days,
        "metrics": {
            "candidates_total": len(candidates),
            "candidates_stories": sum(1 for c in candidates if c.item_type == "story"),
            "candidates_epics": sum(1 for c in candidates if c.item_type == "epic"),
            "items_selected_this_run": len(selected),
            "items_archived_this_run": len(committed_records),
            "stories_archived_this_run": stories_archived,
            "epics_archived_this_run": epics_archived,
            "line_count_before": before_lines,
            "line_count_after_projected": projected_lines,
            "line_count_after_actual": actual_lines_after,
            "line_reduction": line_reduction,
            "line_reduction_percent": line_reduction_pct,
            "workflow_status_updated": workflow_updated,
            "archive_index_updated_entries": index_updated,
            "errors": len(errors),
            "skipped": len(aux.get("skipped", [])),
        },
        "backup_path": backup_path,
        "archived": [
            {
                "id": r["id"],
                "item_type": r["item_type"],
                "section": r["section"],
                "title": r["title"],
                "age_days": r["age_days"],
                "completion_date": r["completion_date"],
                "archive_ref": r["archive_ref"],
                "archive_path": r["archive_path"],
            }
            for r in committed_records
        ],
        "errors": errors,
        "skipped": aux.get("skipped", []),
    }
    return result


def _append_archive_index(archive_index_file: Path, archived_records: list[dict[str, Any]]) -> int:
    """Append archived records to archive-index.yaml preserving legacy structure."""
    if archive_index_file.exists():
        with archive_index_file.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f) or {}
    else:
        idx = {}

    if "archive_index" not in idx or not isinstance(idx.get("archive_index"), dict):
        idx["archive_index"] = {
            "version": "1.0",
            "created_date": _now_utc().date().isoformat(),
            "retention_policy": {
                "active_file_keep_days": 7,
                "archive_location": "docs/archives/workflow-status/",
            },
            "entries": [],
        }

    archive_index = idx["archive_index"]
    entries = archive_index.get("entries")
    if not isinstance(entries, list):
        entries = []
        archive_index["entries"] = entries

    for rec in archived_records:
        completion_date = rec.get("completion_date")
        original_timestamp = (
            f"{completion_date}T00:00:00Z" if completion_date else _now_utc().isoformat().replace("+00:00", "Z")
        )
        entries.append(
            {
                "story_id": rec.get("id"),
                "action": "archived_to_entries",
                "archived_to": rec.get("archive_path"),
                "archive_ref": rec.get("archive_ref"),
                "original_timestamp": original_timestamp,
                "epic_id": rec.get("stub", {}).get("epic_id"),
                "actor": "archive_workflow_status_items.py",
                "description": f"Archived {rec.get('item_type')} {rec.get('id')} to entries",
            }
        )

    archive_index["last_updated"] = _now_utc().date().isoformat()
    _atomic_write(archive_index_file, _dump_yaml(idx))
    return len(archived_records)


def _print_human(result: dict[str, Any]) -> None:
    metrics = result["metrics"]
    print("=" * 80)
    print("WORKFLOW STATUS ARCHIVE")
    print("=" * 80)
    print(f"Mode: {result['mode']}")
    print(f"Workflow file: {result['workflow_file']}")
    print(f"Archive dir: {result['archive_dir']}")
    print(f"Retention days: {result['retention_days']}")
    print("-" * 80)
    print(f"Candidates: {metrics['candidates_total']} (stories={metrics['candidates_stories']}, epics={metrics['candidates_epics']})")
    print(f"Selected this run: {metrics['items_selected_this_run']}")
    print(
        f"Archived this run: {metrics['items_archived_this_run']} "
        f"(stories={metrics['stories_archived_this_run']}, epics={metrics['epics_archived_this_run']})"
    )
    print("-" * 80)
    print("Line metrics")
    print(f"  Before: {metrics['line_count_before']}")
    print(f"  After (projected): {metrics['line_count_after_projected']}")
    print(f"  After (actual): {metrics['line_count_after_actual']}")
    print(
        f"  Reduction: {metrics['line_reduction']} "
        f"({metrics['line_reduction_percent']}%)"
    )
    if result.get("backup_path"):
        print("-" * 80)
        print(f"Backup: {result['backup_path']}")

    if result["archived"]:
        print("-" * 80)
        header = "Would archive:" if result["mode"] == "dry_run" else "Archived:"
        print(header)
        for item in result["archived"]:
            print(
                f"  - {item['id']} [{item['item_type']}] "
                f"section={item['section']} age={item['age_days']}d "
                f"ref={item['archive_ref']}"
            )

    if result["errors"]:
        print("-" * 80)
        print("Errors:")
        for err in result["errors"]:
            print(f"  - {err['id']}: {err['error']}")

    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive workflow-status stories/epics older than retention threshold"
    )
    parser.add_argument("--file", type=Path, default=WORKFLOW_FILE, help="Workflow status YAML path")
    parser.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR, help="Archive entries directory")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS_DEFAULT)
    parser.add_argument("--id", action="append", default=[], help="Archive specific ID(s); can be repeated")
    parser.add_argument("--batch-size", type=int, default=0, help="Max items this run (0 = all)")
    parser.add_argument("--migrated-by", default="opencode")
    parser.add_argument("--execute", action="store_true", help="Persist archive + stub changes")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    parser.add_argument(
        "--require-completion-evidence",
        action="store_true",
        help="Only archive entries with completion evidence (pr/merge metadata)",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Append archival records to docs/archives/workflow-status/archive-index.yaml",
    )
    parser.add_argument(
        "--archive-index-file",
        type=Path,
        default=ARCHIVE_INDEX_FILE,
        help="Archive index file path (used with --update-index)",
    )
    args = parser.parse_args()

    try:
        result = _archive(
            workflow_file=args.file,
            archive_dir=args.archive_dir,
            retention_days=args.retention_days,
            ids=args.id,
            batch_size=args.batch_size,
            execute=args.execute,
            migrated_by=args.migrated_by,
            require_completion_evidence=args.require_completion_evidence,
            update_index=args.update_index,
            archive_index_file=args.archive_index_file,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
