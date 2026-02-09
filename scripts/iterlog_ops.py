#!/usr/bin/env python3
"""
Small helper for agents to avoid hand-rolling Redis iterlog operations.

This script uses redis-cli (no Python redis dependency) and falls back to
docs/tempmemories iterlog markdown when Redis is not reachable.

Defaults follow AGENTS.md:
- Redis: db=0, port=6380, host=host.docker.internal (auto-fallback to localhost)
- Ownership: bmad:chiseai:ownership (HASH) path_slug -> story/agent/timestamp
- Incidents: bmad:chiseai:iterlog:story:<story_id>:incidents (LIST)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ITERLOG_DIR = Path("docs/tempmemories")
OWNERSHIP_KEY = "bmad:chiseai:ownership"


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _slug_path(path: str) -> str:
    # Normalize to repo-relative-ish slug.
    p = path.strip().lstrip("./")
    p = p.strip("/")
    return p.lower().replace("/", ":")


def _redis_candidates() -> list[tuple[str, int, int]]:
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    # Try configured host first, then localhost (common when not running inside Docker).
    candidates = [(host, port, db)]
    if host != "localhost":
        candidates.append(("localhost", port, db))
    return candidates


def _run_redis_cli(
    host: str, port: int, db: int, *args: str
) -> subprocess.CompletedProcess[str]:
    cmd = ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _redis_ping() -> tuple[bool, tuple[str, int, int] | None]:
    for host, port, db in _redis_candidates():
        p = _run_redis_cli(host, port, db, "PING")
        if p.returncode == 0 and p.stdout.strip() == "PONG":
            return True, (host, port, db)
    return False, None


def _ensure_iterlog_file(
    story_id: str, story_title: str | None, phase: str | None, status: str | None
) -> Path:
    ITERLOG_DIR.mkdir(parents=True, exist_ok=True)
    path = ITERLOG_DIR / f"iterlog-{story_id}.md"
    if path.exists():
        return path

    title = story_title or "TBD"
    ph = phase or "implementation"
    st = status or "in_progress"
    text = (
        "---\n"
        "project: ChiseAI\n"
        "scope: iteration-log\n"
        "type: iterlog\n"
        f"story_id: {story_id}\n"
        f"story_title: \"{title}\"\n"
        f"phase: {ph}\n"
        f"status: {st}\n"
        f"started_at: \"{_utc_now()}\"\n"
        "needs_manual_qdrant_import: true\n"
        "---\n\n"
        "## Decisions\n\n- TBD\n\n"
        "## Learnings\n\n- TBD\n\n"
        "## Scope Ownership\n\n- TBD\n\n"
        "## Incidents\n\n- TBD\n\n"
        "## Evidence\n\n- TBD\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def _append_under_heading(md_path: Path, heading: str, lines: list[str]) -> None:
    text = md_path.read_text(encoding="utf-8")
    if heading not in text:
        # Append missing heading at end.
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n{heading}\n\n- TBD\n"
    # Insert directly after heading line (after any blank line).
    parts = text.split(heading, 1)
    before = parts[0] + heading
    after = parts[1]
    if after.startswith("\n"):
        after = after[1:]
    if after.startswith("\n"):
        after = after[1:]
    insertion = "\n\n" + "\n".join(lines) + "\n"
    new_text = before + insertion + after
    md_path.write_text(new_text, encoding="utf-8")


def cmd_path_slug(args: argparse.Namespace) -> int:
    for p in args.paths:
        print(_slug_path(p))
    return 0


def cmd_claim_ownership(args: argparse.Namespace) -> int:
    ok, cfg = _redis_ping()
    ts = _utc_now()
    slugs = [_slug_path(p) for p in args.scopes]
    value = f"{args.story_id}/{args.agent}/{ts}"

    if not ok or cfg is None:
        md = _ensure_iterlog_file(
            args.story_id, args.story_title, args.phase, args.status
        )
        lines = [f"- {_slug_path(p)}: {value}" for p in args.scopes]
        _append_under_heading(md, "## Scope Ownership", lines)
        print(f"Redis not reachable; wrote scope ownership to {md}")
        return 0

    host, port, db = cfg
    for slug in slugs:
        existing = _run_redis_cli(host, port, db, "HGET", OWNERSHIP_KEY, slug)
        existing_val = existing.stdout.strip()
        if existing.returncode != 0:
            print(existing.stderr.strip(), file=sys.stderr)
            return 1
        if existing_val and not existing_val.startswith(
            f"{args.story_id}/{args.agent}/"
        ):
            print(
                f"Ownership conflict for {slug}: owned_by={existing_val!r} "
                f"requested={value!r}",
                file=sys.stderr,
            )
            return 2

        r = _run_redis_cli(host, port, db, "HSET", OWNERSHIP_KEY, slug, value)
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)
            return 1

    # Keep ownership key alive (best-effort).
    _run_redis_cli(host, port, db, "EXPIRE", OWNERSHIP_KEY, str(args.ttl_seconds))
    print(f"Claimed ownership for {len(slugs)} scopes in Redis ({host}:{port}/{db})")
    return 0


def cmd_check_ownership(args: argparse.Namespace) -> int:
    ok, cfg = _redis_ping()
    slugs = [_slug_path(p) for p in args.scopes]
    expected_prefix = f"{args.story_id}/{args.agent}/"

    if not ok or cfg is None:
        print(
            "Redis not reachable; cannot check ownership (use markdown fallback).",
            file=sys.stderr,
        )
        return 3

    host, port, db = cfg
    for slug in slugs:
        r = _run_redis_cli(host, port, db, "HGET", OWNERSHIP_KEY, slug)
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)
            return 1
        val = r.stdout.strip()
        if not val:
            print(f"Missing ownership for {slug}", file=sys.stderr)
            return 2
        if not val.startswith(expected_prefix):
            print(
                f"Ownership mismatch for {slug}: owned_by={val!r} "
                f"expected_prefix={expected_prefix!r}",
                file=sys.stderr,
            )
            return 2
    print("Ownership OK")
    return 0


def cmd_append_incident(args: argparse.Namespace) -> int:
    ok, cfg = _redis_ping()
    md = _ensure_iterlog_file(args.story_id, args.story_title, args.phase, args.status)

    entry = args.text.rstrip()
    if not entry.startswith("INCIDENT:"):
        entry = "INCIDENT:\n" + entry

    # Always append to markdown fallback too (useful even when Redis works).
    _append_under_heading(md, "## Incidents", ["```text", entry, "```"])

    if not ok or cfg is None:
        print(f"Redis not reachable; appended incident to {md}")
        return 0

    host, port, db = cfg
    list_key = f"bmad:chiseai:iterlog:story:{args.story_id}:incidents"
    r = _run_redis_cli(host, port, db, "RPUSH", list_key, entry)
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        return 1
    _run_redis_cli(host, port, db, "EXPIRE", list_key, str(args.ttl_seconds))
    print(f"Appended incident to Redis list {list_key} and markdown {md}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="ChiseAI iterlog helper ops (ownership + incidents)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_slug = sub.add_parser("path-slug", help="Convert repo path(s) into a path_slug")
    p_slug.add_argument("paths", nargs="+")
    p_slug.set_defaults(func=cmd_path_slug)

    p_claim = sub.add_parser(
        "claim-ownership", help="Claim scope ownership (Redis or markdown fallback)"
    )
    p_claim.add_argument("--story-id", required=True)
    p_claim.add_argument(
        "--agent", required=True, help="agent id (dev/quickdev/senior-dev/...)"
    )
    p_claim.add_argument(
        "--scopes", nargs="+", required=True, help="repo-relative scope paths"
    )
    p_claim.add_argument("--ttl-seconds", type=int, default=432000)
    p_claim.add_argument("--story-title")
    p_claim.add_argument("--phase")
    p_claim.add_argument("--status")
    p_claim.set_defaults(func=cmd_claim_ownership)

    p_check = sub.add_parser(
        "check-ownership", help="Check scope ownership in Redis (fails if mismatch)"
    )
    p_check.add_argument("--story-id", required=True)
    p_check.add_argument("--agent", required=True)
    p_check.add_argument("--scopes", nargs="+", required=True)
    p_check.set_defaults(func=cmd_check_ownership)

    p_inc = sub.add_parser(
        "append-incident", help="Append incident entry (Redis list + markdown fallback)"
    )
    p_inc.add_argument("--story-id", required=True)
    p_inc.add_argument("--ttl-seconds", type=int, default=432000)
    p_inc.add_argument("--story-title")
    p_inc.add_argument("--phase")
    p_inc.add_argument("--status")
    p_inc.add_argument(
        "--text",
        required=True,
        help="Incident text. If it doesn't start with 'INCIDENT:' it will be wrapped.",
    )
    p_inc.set_defaults(func=cmd_append_incident)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
