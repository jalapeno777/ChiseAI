#!/usr/bin/env python3
"""Prune aged skill autonomy artifacts to limit repo/log growth."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Cleanup skill autonomy artifacts")
    ap.add_argument("--weekly-dir", default="docs/tempmemories")
    ap.add_argument("--weekly-pattern", default="skill-autonomy-weekly-*.md")
    ap.add_argument("--weekly-retention-days", type=int, default=60)
    ap.add_argument("--backlog-dir", default="docs/backlog")
    ap.add_argument("--backlog-pattern", default="skills-autonomy-candidates-*.md")
    ap.add_argument("--backlog-retention-days", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    return ap.parse_args()


def collect_old_files(base: Path, pattern: str, cutoff: datetime) -> list[Path]:
    if not base.exists():
        return []
    old: list[Path] = []
    for path in base.glob(pattern):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            old.append(path)
    return sorted(old)


def main() -> int:
    args = parse_args()

    weekly_cutoff = utc_now() - timedelta(days=args.weekly_retention_days)
    backlog_cutoff = utc_now() - timedelta(days=args.backlog_retention_days)

    weekly_files = collect_old_files(
        Path(args.weekly_dir), args.weekly_pattern, weekly_cutoff
    )
    backlog_files = collect_old_files(
        Path(args.backlog_dir), args.backlog_pattern, backlog_cutoff
    )

    removed = []
    if not args.dry_run:
        for path in weekly_files + backlog_files:
            path.unlink(missing_ok=True)
            removed.append(str(path))

    print("SKILL_AUTONOMY_RETENTION_RESULT")
    print(f"dry_run: {str(args.dry_run).lower()}")
    print(f"weekly_candidates: {len(weekly_files)}")
    print(f"backlog_candidates: {len(backlog_files)}")
    print(f"removed: {len(removed)}")
    for p in (
        removed if not args.dry_run else [str(x) for x in weekly_files + backlog_files]
    ):
        print(f"- {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
