#!/usr/bin/env python3
"""Swarm session manager for isolated worktree execution.

Phase 1 goals:
- Isolate each story/agent execution in its own git worktree.
- Enforce explicit branch ownership via Redis leases.
- Provide a deterministic session contract workers can verify before git actions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

SESSION_FILE = ".swarm-session.json"
OWNERSHIP_KEY = "bmad:chiseai:ownership"
BRANCH_LEASE_PREFIX = "bmad:chiseai:branch-lease:"
WORKTREE_LEASE_PREFIX = "bmad:chiseai:worktree-lease:"

CANONICAL_FILES = {
    "docs/bmm-workflow-status.yaml",
    "docs/validation/validation-registry.yaml",
}


class SessionError(RuntimeError):
    pass


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _path_slug(path: str) -> str:
    p = path.strip().lstrip("./").strip("/")
    return p.lower().replace("/", ":")


def _run(*cmd: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SessionError(
            "Command failed "
            f"({' '.join(cmd)}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def _git_root() -> Path:
    root = _run("git", "rev-parse", "--show-toplevel")
    return Path(root)


def _git_branch(cwd: Path) -> str:
    return _run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def _branch_exists(branch: str, cwd: Path) -> bool:
    proc = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _redis_candidates() -> list[tuple[str, int, int]]:
    host = (
        os.getenv("CHISE_REDIS_HOST")
        or os.getenv("REDIS_HOST")
        or "host.docker.internal"
    )
    port = int(os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380")
    db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")
    candidates = [(host, port, db)]
    if host != "localhost":
        candidates.append(("localhost", port, db))
    return candidates


def _redis_cli(
    host: str, port: int, db: int, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["redis-cli", "-h", host, "-p", str(port), "-n", str(db), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _redis_ping() -> tuple[bool, tuple[str, int, int] | None]:
    for host, port, db in _redis_candidates():
        proc = _redis_cli(host, port, db, "PING")
        if proc.returncode == 0 and proc.stdout.strip() == "PONG":
            return True, (host, port, db)
    return False, None


def _set_lease(
    host: str,
    port: int,
    db: int,
    key: str,
    value: str,
    ttl_seconds: int,
    force: bool,
) -> None:
    existing = _redis_cli(host, port, db, "GET", key)
    if existing.returncode != 0:
        raise SessionError(existing.stderr.strip() or f"Failed reading lease {key}")
    existing_val = existing.stdout.strip()
    if existing_val and existing_val != value and not force:
        raise SessionError(
            f"Lease conflict for {key}: owned_by={existing_val!r} requested={value!r}"
        )

    res = _redis_cli(host, port, db, "SET", key, value, "EX", str(ttl_seconds))
    if res.returncode != 0:
        raise SessionError(res.stderr.strip() or f"Failed setting lease {key}")


def _claim_scope_ownership(
    host: str,
    port: int,
    db: int,
    story_id: str,
    agent: str,
    scopes: list[str],
    ttl_seconds: int,
    force: bool,
) -> None:
    ts = _utc_now()
    owner = f"{story_id}/{agent}/{ts}"
    for scope in scopes:
        slug = _path_slug(scope)
        get_res = _redis_cli(host, port, db, "HGET", OWNERSHIP_KEY, slug)
        if get_res.returncode != 0:
            raise SessionError(get_res.stderr.strip() or "Failed ownership lookup")
        val = get_res.stdout.strip()
        if val and not val.startswith(f"{story_id}/{agent}/") and not force:
            raise SessionError(
                "Scope ownership conflict for "
                f"{slug}: owned_by={val!r} requested={owner!r}"
            )
        set_res = _redis_cli(host, port, db, "HSET", OWNERSHIP_KEY, slug, owner)
        if set_res.returncode != 0:
            raise SessionError(set_res.stderr.strip() or "Failed ownership update")

    _redis_cli(host, port, db, "EXPIRE", OWNERSHIP_KEY, str(ttl_seconds))


def _session_payload(
    story_id: str,
    agent: str,
    branch: str,
    worktree_path: Path,
    base_ref: str,
    scopes: list[str],
) -> dict[str, Any]:
    sha = _run("git", "-C", str(worktree_path), "rev-parse", "HEAD")
    return {
        "story_id": story_id,
        "agent": agent,
        "branch": branch,
        "worktree_path": str(worktree_path),
        "base_ref": base_ref,
        "base_sha": sha,
        "scopes": scopes,
        "created_at": _utc_now(),
    }


def _write_session(worktree_path: Path, payload: dict[str, Any]) -> Path:
    path = worktree_path / SESSION_FILE
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _read_session(worktree_path: Path) -> dict[str, Any]:
    path = worktree_path / SESSION_FILE
    if not path.exists():
        raise SessionError(f"Missing {SESSION_FILE} under {worktree_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SessionError(f"Invalid session payload in {path}")
    return cast(dict[str, Any], data)


def _resolve_worktree_path(provided: str | None) -> Path:
    if provided:
        return Path(provided).resolve()
    return Path.cwd().resolve()


def cmd_start(args: argparse.Namespace) -> int:
    repo_root = _git_root()
    branch = args.branch.strip()
    if not branch:
        raise SessionError("--branch is required")
    if not re.match(r"^(feature|safety)/", branch):
        raise SessionError("Branch must start with feature/ or safety/")

    worktree_root = Path(args.worktree_root)
    if not worktree_root.is_absolute():
        worktree_root = (repo_root / worktree_root).resolve()
    worktree_root.mkdir(parents=True, exist_ok=True)

    safe_story = re.sub(r"[^A-Za-z0-9._-]", "-", args.story_id)
    safe_agent = re.sub(r"[^A-Za-z0-9._-]", "-", args.agent)
    worktree_path = (worktree_root / f"{safe_story}-{safe_agent}").resolve()

    if worktree_path.exists() and any(worktree_path.iterdir()) and not args.force:
        raise SessionError(
            "Worktree path exists and is not empty: "
            f"{worktree_path} (use --force to reuse)"
        )

    if not worktree_path.exists() or not any(worktree_path.iterdir()):
        if _branch_exists(branch, repo_root):
            _run("git", "worktree", "add", str(worktree_path), branch, cwd=repo_root)
        else:
            _run(
                "git",
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree_path),
                args.base,
                cwd=repo_root,
            )

    payload = _session_payload(
        story_id=args.story_id,
        agent=args.agent,
        branch=branch,
        worktree_path=worktree_path,
        base_ref=args.base,
        scopes=args.scopes,
    )
    session_path = _write_session(worktree_path, payload)

    ok, cfg = _redis_ping()
    lease_owner = f"{args.story_id}/{args.agent}/{_utc_now()}"
    if ok and cfg is not None:
        host, port, db = cfg
        _set_lease(
            host,
            port,
            db,
            f"{BRANCH_LEASE_PREFIX}{branch}",
            lease_owner,
            args.ttl_seconds,
            args.force,
        )
        _set_lease(
            host,
            port,
            db,
            f"{WORKTREE_LEASE_PREFIX}{_path_slug(str(worktree_path))}",
            lease_owner,
            args.ttl_seconds,
            args.force,
        )
        if args.scopes:
            _claim_scope_ownership(
                host,
                port,
                db,
                args.story_id,
                args.agent,
                args.scopes,
                args.ttl_seconds,
                args.force,
            )
        redis_msg = f"Redis leases set on {host}:{port}/{db}"
    else:
        redis_msg = "Redis unavailable; skipped lease writes"

    print("session.start: OK")
    print(f"- worktree: {worktree_path}")
    print(f"- branch: {branch}")
    print(f"- session: {session_path}")
    print(f"- {redis_msg}")
    return 0


def _validate_canonical_lock(args: argparse.Namespace, session: dict[str, Any]) -> None:
    if not args.check_canonical:
        return

    changed = _run(
        "git",
        "-C",
        session["worktree_path"],
        "show",
        "--pretty=",
        "--name-only",
        "HEAD",
    )
    changed_files = {line.strip() for line in changed.splitlines() if line.strip()}
    touches_canonical = bool(changed_files.intersection(CANONICAL_FILES))
    if not touches_canonical:
        return

    lock = os.getenv("CANONICAL_STATUS_LOCK", "").strip()
    if lock != "1":
        raise SessionError(
            "Canonical files are global-lock. Set CANONICAL_STATUS_LOCK=1 "
            "before running git actions that touch them."
        )


def cmd_verify(args: argparse.Namespace) -> int:
    worktree_path = _resolve_worktree_path(args.worktree_path)
    session = _read_session(worktree_path)
    branch = _git_branch(worktree_path)

    if args.branch and branch != args.branch:
        raise SessionError(
            f"Branch mismatch: current={branch!r} expected={args.branch!r}"
        )
    if branch != str(session.get("branch", "")):
        raise SessionError(
            "Session branch mismatch: "
            f"current={branch!r} session={session.get('branch')!r}"
        )

    if args.story_id and str(session.get("story_id", "")) != args.story_id:
        raise SessionError(
            "Story mismatch: "
            f"session={session.get('story_id')!r} expected={args.story_id!r}"
        )

    ok, cfg = _redis_ping()
    if ok and cfg is not None:
        host, port, db = cfg
        lease_key = f"{BRANCH_LEASE_PREFIX}{branch}"
        lease = _redis_cli(host, port, db, "GET", lease_key)
        if lease.returncode != 0:
            raise SessionError(lease.stderr.strip() or "Failed reading branch lease")
        lease_val = lease.stdout.strip()
        expected_prefix = f"{session['story_id']}/{session['agent']}/"
        if not lease_val.startswith(expected_prefix):
            raise SessionError(
                "Branch lease mismatch for "
                f"{lease_key}: {lease_val!r} does not start with "
                f"{expected_prefix!r}"
            )

    _validate_canonical_lock(args, session)

    print("session.verify: OK")
    print(f"- worktree: {worktree_path}")
    print(f"- branch: {branch}")
    print(f"- story: {session.get('story_id')}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    worktree_path = _resolve_worktree_path(args.worktree_path)
    session = _read_session(worktree_path)
    branch = str(session["branch"])

    ok, cfg = _redis_ping()
    if ok and cfg is not None:
        host, port, db = cfg
        _redis_cli(host, port, db, "DEL", f"{BRANCH_LEASE_PREFIX}{branch}")
        _redis_cli(
            host,
            port,
            db,
            "DEL",
            f"{WORKTREE_LEASE_PREFIX}{_path_slug(str(worktree_path))}",
        )

    session_file = worktree_path / SESSION_FILE
    if session_file.exists():
        session_file.unlink()

    if args.remove_worktree:
        _run("git", "worktree", "remove", str(worktree_path), cwd=_git_root())

    print(
        "session.close: OK"
        f"\n- worktree: {worktree_path}"
        f"\n- branch: {branch}"
        f"\n- removed_worktree: {str(args.remove_worktree).lower()}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ChiseAI swarm worktree session manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Create/resume isolated worktree session")
    start.add_argument("--story-id", required=True)
    start.add_argument("--agent", required=True)
    start.add_argument("--branch", required=True)
    start.add_argument("--base", default="main")
    start.add_argument("--worktree-root", default=".swarm-worktrees")
    start.add_argument("--ttl-seconds", type=int, default=432000)
    start.add_argument("--force", action="store_true")
    start.add_argument("--scopes", nargs="*", default=[])
    start.set_defaults(func=cmd_start)

    verify = sub.add_parser("verify", help="Verify session/branch/lease invariants")
    verify.add_argument("--worktree-path")
    verify.add_argument("--story-id")
    verify.add_argument("--branch")
    verify.add_argument("--check-canonical", action="store_true")
    verify.set_defaults(func=cmd_verify)

    close = sub.add_parser("close", help="Release leases and close worktree session")
    close.add_argument("--worktree-path")
    close.add_argument("--remove-worktree", action="store_true")
    close.set_defaults(func=cmd_close)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except SessionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
