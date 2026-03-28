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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

# Allow direct script execution from repo root in opencode harness:
# ensure both repo root and src are importable before bootstrap import.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config.bootstrap import bootstrap, check_environment
except ModuleNotFoundError:
    from src.config.bootstrap import bootstrap, check_environment

SESSION_FILE = ".swarm-session.json"
REPO_HOOKS_PATH = ".githooks"


def check_critical_environment() -> None:
    """Verify critical environment variables are set.

    Raises:
        SessionError: If required environment variables are missing.
    """
    # Session.py uses Redis for lease management
    result = check_environment(
        [
            "REDIS_HOST",
            "CHISE_REDIS_HOST",
        ]
    )

    if not result["ok"]:
        # Not a hard failure - Redis may use defaults
        # But warn if neither variable is set
        if not result["present"]:
            print(
                "WARN: No Redis host configured. Using default: host.docker.internal:6380",
                file=sys.stderr,
            )

    # Check for warnings
    for warning in result.get("warnings", []):
        print(f"WARN: {warning}", file=sys.stderr)


OWNERSHIP_KEY = "bmad:chiseai:ownership"
BRANCH_LEASE_PREFIX = "bmad:chiseai:branch-lease:"
WORKTREE_LEASE_PREFIX = "bmad:chiseai:worktree-lease:"
MAIN_MERGE_LOCK_KEY = "bmad:chiseai:merge-lock:main"
STARTUP_LOCK_KEY = "bmad:chiseai:repo-startup-lock"
STARTUP_LOCK_TTL_SECONDS = 300
MERGE_AUTHORITY_AGENT = "merlin"

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


def _run_rc(*cmd: str, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _git_root() -> Path:
    root = _run("git", "rev-parse", "--show-toplevel")
    return Path(root)


def _ensure_repo_hooks_config(repo_root: Path) -> str:
    hooks_dir = repo_root / REPO_HOOKS_PATH
    if not hooks_dir.exists():
        raise SessionError(
            f"Required hooks directory is missing: {hooks_dir}. "
            "Restore repo-managed hooks before continuing."
        )

    rc, current, err = _run_rc(
        "git",
        "-C",
        str(repo_root),
        "config",
        "--local",
        "--get",
        "core.hooksPath",
    )
    if rc == 0 and current.strip() == REPO_HOOKS_PATH:
        return "already-configured"

    set_rc, _out, set_err = _run_rc(
        "git",
        "-C",
        str(repo_root),
        "config",
        "--local",
        "core.hooksPath",
        REPO_HOOKS_PATH,
    )
    if set_rc != 0:
        raise SessionError(
            "Failed to configure repo-managed git hooks "
            f"({REPO_HOOKS_PATH}): {set_err or err}"
        )
    return "configured"


def _git_branch(cwd: Path) -> str:
    return _run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def _branch_exists(branch: str, cwd: Path) -> bool:
    proc = subprocess.run(  # nosec B607
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
    return subprocess.run(  # nosec B607
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


# ---------------------------------------------------------------------------
# Repo startup lock — prevents concurrent worktree creation / branch ops
# when multiple opencode sessions share the same physical repo.
# Uses atomic SET NX with a TTL so crashed sessions don't block forever.
# ---------------------------------------------------------------------------


def _acquire_startup_lock(story_id: str, agent: str) -> str:
    """Acquire exclusive repo-level startup lock.

    Uses Redis SET NX for atomicity.  The lock auto-expires after
    STARTUP_LOCK_TTL_SECONDS (300s) to prevent permanent blocking if a
    session crashes during startup.

    Returns:
        The lock owner string (story_id/agent/timestamp).

    Raises:
        SessionError: If Redis is unavailable or lock is held by another session.
    """
    ok, cfg = _redis_ping()
    if not ok or cfg is None:
        raise SessionError(
            "Redis is required for repo startup lock. "
            "Ensure CHISE_REDIS_HOST/REDIS_HOST is reachable and retry."
        )
    host, port, db = cfg
    owner = f"{story_id}/{agent}/{_utc_now()}"
    # Atomic SET NX — only succeeds if key does not exist
    res = _redis_cli(
        host,
        port,
        db,
        "SET",
        STARTUP_LOCK_KEY,
        owner,
        "NX",
        "EX",
        str(STARTUP_LOCK_TTL_SECONDS),
    )
    if res.stdout.strip() != "OK":
        existing = _redis_cli(host, port, db, "GET", STARTUP_LOCK_KEY)
        held_by = existing.stdout.strip() if existing.returncode == 0 else "<unknown>"
        raise SessionError(
            f"Cannot start: another session is currently starting up ({held_by}). "
            f"Wait for it to finish (lock auto-expires in {STARTUP_LOCK_TTL_SECONDS}s) "
            f"or run: python3 scripts/swarm/session.py unlock --force"
        )
    return owner


def _release_startup_lock() -> None:
    """Release the repo startup lock (only if we hold it).

    This is a best-effort release; if Redis is down or the lock was already
    claimed by another session, we silently succeed.
    """
    ok, cfg = _redis_ping()
    if ok and cfg is not None:
        host, port, db = cfg
        _redis_cli(host, port, db, "DEL", STARTUP_LOCK_KEY)


def _force_release_startup_lock() -> str:
    """Force-release the repo startup lock regardless of ownership.

    Returns:
        Human-readable status message.

    Use with caution — only when a session has crashed mid-startup.
    """
    ok, cfg = _redis_ping()
    if not ok or cfg is None:
        return "Redis unavailable; cannot force-release startup lock."
    host, port, db = cfg
    get_res = _redis_cli(host, port, db, "GET", STARTUP_LOCK_KEY)
    previous = get_res.stdout.strip() if get_res.returncode == 0 else "<none>"
    del_res = _redis_cli(host, port, db, "DEL", STARTUP_LOCK_KEY)
    if del_res.returncode == 0 and del_res.stdout.strip() == "1":
        return f"Force-released startup lock (was held by: {previous})"
    return "Startup lock was not held or could not be released."


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


def _find_nested_session_candidates(worktree_path: Path) -> list[Path]:
    # Common legacy layout is /tmp/worktrees/<id>/<id>/.swarm-session.json.
    matches = sorted(
        p.parent for p in worktree_path.glob(f"*/{SESSION_FILE}") if p.is_file()
    )
    return matches


def _session_owner(session: dict[str, Any]) -> str:
    return f"{session.get('story_id')}/{session.get('agent')}"


def _acquire_main_merge_lock(
    session: dict[str, Any],
    ttl_seconds: int,
) -> str:
    if str(session.get("agent", "")).strip() != MERGE_AUTHORITY_AGENT:
        raise SessionError(
            "Main-merge operations are restricted to agent "
            f"{MERGE_AUTHORITY_AGENT!r}; current agent={session.get('agent')!r}"
        )

    ok, cfg = _redis_ping()
    if not ok or cfg is None:
        raise SessionError(
            "Cannot acquire main merge lock: Redis unavailable. "
            "Set CHISE_REDIS_HOST/PORT and retry."
        )

    host, port, db = cfg
    owner = f"{_session_owner(session)}/{_utc_now()}"
    existing = _redis_cli(host, port, db, "GET", MAIN_MERGE_LOCK_KEY)
    if existing.returncode != 0:
        raise SessionError(existing.stderr.strip() or "Failed reading main merge lock")
    existing_val = existing.stdout.strip()
    if existing_val and not existing_val.startswith(f"{_session_owner(session)}/"):
        raise SessionError(
            f"Main merge lock conflict: owned_by={existing_val!r} requested={owner!r}"
        )

    set_res = _redis_cli(
        host,
        port,
        db,
        "SET",
        MAIN_MERGE_LOCK_KEY,
        owner,
        "EX",
        str(ttl_seconds),
    )
    if set_res.returncode != 0:
        raise SessionError(set_res.stderr.strip() or "Failed setting main merge lock")

    return owner


def _release_main_merge_lock(session: dict[str, Any]) -> None:
    owner = str(session.get("main_merge_lock_owner", "")).strip()
    if not owner:
        return

    ok, cfg = _redis_ping()
    if not ok or cfg is None:
        print(
            "WARN: Redis unavailable while releasing main merge lock; "
            "lock will expire by TTL.",
            file=sys.stderr,
        )
        return

    host, port, db = cfg
    current = _redis_cli(host, port, db, "GET", MAIN_MERGE_LOCK_KEY)
    if current.returncode != 0:
        print(
            "WARN: Failed to read main merge lock during release: "
            f"{current.stderr.strip()}",
            file=sys.stderr,
        )
        return
    current_val = current.stdout.strip()
    if current_val == owner:
        _redis_cli(host, port, db, "DEL", MAIN_MERGE_LOCK_KEY)
    else:
        print(
            "WARN: Main merge lock owner changed before release; "
            f"current={current_val!r} expected={owner!r}",
            file=sys.stderr,
        )


def _branch_ahead_count(
    worktree_path: Path, branch: str, base_ref: str = "main"
) -> int:
    rc, out, err = _run_rc(
        "git",
        "-C",
        str(worktree_path),
        "rev-list",
        "--count",
        f"{base_ref}..{branch}",
    )
    if rc != 0:
        raise SessionError(
            f"Failed to compute ahead count for {branch} vs {base_ref}: {err or out}"
        )
    try:
        return int(out.strip())
    except ValueError as exc:
        raise SessionError(
            f"Invalid ahead-count output for {branch} vs {base_ref}: {out!r}"
        ) from exc


def _git_dirty_entries(worktree_path: Path) -> list[str]:
    rc, out, err = _run_rc(
        "git",
        "-C",
        str(worktree_path),
        "status",
        "--porcelain",
    )
    if rc != 0:
        raise SessionError(f"Failed to check worktree dirtiness: {err or out}")
    return [line for line in out.splitlines() if line.strip()]


def _stash_dirty_worktree(worktree_path: Path, story_id: str, branch: str) -> str:
    label = f"swarm-close:{story_id}:{branch}:{_utc_now()}"
    rc, out, err = _run_rc(
        "git",
        "-C",
        str(worktree_path),
        "stash",
        "push",
        "--include-untracked",
        "-m",
        label,
    )
    if rc != 0:
        raise SessionError(f"Failed to stash dirty worktree: {err or out}")
    return out or label


def _pr_exists_for_branch(branch: str, base_ref: str = "main") -> tuple[bool, str]:
    token = (os.getenv("GITEA_TOKEN") or "").strip()
    owner = (
        os.getenv("GITEA_OWNER")
        or os.getenv("CI_REPO_OWNER")
        or os.getenv("WOODPECKER_REPO_OWNER")
        or ""
    ).strip()
    repo = (
        os.getenv("GITEA_REPO")
        or os.getenv("CI_REPO_NAME")
        or os.getenv("WOODPECKER_REPO_NAME")
        or ""
    ).strip()
    base_url = (
        os.getenv("GITEA_BASE_URL") or "http://host.docker.internal:3000"
    ).rstrip("/")

    if not token or not owner or not repo:
        return False, "Gitea token/owner/repo env vars missing"

    page = 1
    while page <= 10:
        qs = urllib.parse.urlencode({"state": "all", "limit": 50, "page": page})
        url = f"{base_url}/api/v1/repos/{owner}/{repo}/pulls?{qs}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"token {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
                rows = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return False, f"Gitea PR check failed: {exc}"

        if not isinstance(rows, list) or not rows:
            break

        for pr in rows:
            if not isinstance(pr, dict):
                continue
            head_ref = str((pr.get("head") or {}).get("ref", "")).strip()
            base_pr_ref = str((pr.get("base") or {}).get("ref", "")).strip()
            if head_ref != branch or base_pr_ref != base_ref:
                continue
            if bool(pr.get("merged")):
                return True, f"merged PR #{pr.get('number')}"
            if str(pr.get("state", "")).lower() == "open":
                return True, f"open PR #{pr.get('number')}"

        if len(rows) < 50:
            break
        page += 1

    return False, "No open/merged PR found for branch"


def cmd_start(args: argparse.Namespace) -> int:
    # Acquire repo-level startup lock to prevent concurrent worktree
    # creation when multiple opencode sessions share the same repo.
    # The lock is released in the finally block once the worktree is ready.
    startup_lock_owner = _acquire_startup_lock(args.story_id, args.agent)

    repo_root = _git_root()
    hooks_status = _ensure_repo_hooks_config(repo_root)
    branch = args.branch.strip()
    if not branch:
        raise SessionError("--branch is required")
    # Branch naming is now advisory; any branch name is allowed
    # (PR title validation provides the authoritative story-ID gate)

    try:
        safe_story = re.sub(r"[^A-Za-z0-9._-]", "-", args.story_id)
        safe_agent = re.sub(r"[^A-Za-z0-9._-]", "-", args.agent)
        expected_leaf = f"{safe_story}-{safe_agent}"

        if args.worktree_path:
            worktree_path = Path(args.worktree_path).resolve()
        else:
            worktree_root = Path(args.worktree_root)
            if not worktree_root.is_absolute():
                worktree_root = (repo_root / worktree_root).resolve()
            # Backward compatibility: if caller passed a story-specific root, treat it
            # as the final worktree path instead of nesting the same suffix twice.
            if worktree_root.name == expected_leaf:
                worktree_path = worktree_root
            else:
                worktree_path = (worktree_root / expected_leaf).resolve()
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if worktree_path.exists() and any(worktree_path.iterdir()) and not args.force:
            raise SessionError(
                "Worktree path exists and is not empty: "
                f"{worktree_path} (use --force to reuse)"
            )

        if not worktree_path.exists() or not any(worktree_path.iterdir()):
            if _branch_exists(branch, repo_root):
                _run(
                    "git", "worktree", "add", str(worktree_path), branch, cwd=repo_root
                )
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
        print(f"- hooks_path: {REPO_HOOKS_PATH} ({hooks_status})")
        print(f"- startup_lock: {startup_lock_owner}")
        print(f"- {redis_msg}")
        return 0
    finally:
        _release_startup_lock()


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
        # Check for force-unlock override with mandatory justification.
        if getattr(args, "force_unlock", False):
            justification = getattr(args, "justification", "").strip()
            if not justification:
                raise SessionError(
                    "--force-unlock requires --justification '<reason>' to proceed. "
                    "Provide a reason for overriding the canonical status lock."
                )
            print(
                f"WARN: Canonical lock overridden with --force-unlock. "
                f"Justification: {justification}",
                file=sys.stderr,
            )
            return

        canonical_list = ", ".join(sorted(CANONICAL_FILES))
        raise SessionError(
            "Canonical status lock is enforced for story completion claims.\n"
            f"Canonical files ({canonical_list}) require CANONICAL_STATUS_LOCK=1 "
            "environment variable to be set.\n"
            "This prevents accidental status file modifications that could break "
            "CI validation.\n"
            "To override this safeguard, re-run with --force-unlock "
            '--justification "<reason>".\n'
            f"Current CANONICAL_STATUS_LOCK value: {os.getenv('CANONICAL_STATUS_LOCK', '<unset>')}"
        )


def _validate_evidence_requirements(
    args: argparse.Namespace, session: dict[str, Any]
) -> None:
    """Validate evidence requirements for the session."""
    # Check if evidence validation should be enforced
    # For now, we only enforce if the session has specific scopes or if files changed
    worktree_path = Path(session["worktree_path"])

    # Get changed files
    try:
        changed = _run("git", "-C", str(worktree_path), "diff", "--name-only", "HEAD")
        changed_files = {line.strip() for line in changed.splitlines() if line.strip()}
    except Exception:
        print(
            "WARN: Could not get changed files for evidence validation", file=sys.stderr
        )
        return

    # Check if any evidence-related files changed
    evidence_files = {
        f
        for f in changed_files
        if "docs/evidence/" in f or "docs/bmm-workflow-status.yaml" in f
    }

    if not evidence_files:
        print("- evidence-validation: No evidence-related files changed; skipping")
        return

    print(
        f"- evidence-validation: {len(evidence_files)} evidence-related file(s) changed"
    )

    # Run evidence validation
    try:
        result = subprocess.run(
            [sys.executable, "scripts/ci/evidence_gate_runner.py", "--verbose"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if result.returncode == 0:
            print("- evidence-validation: PASSED")
        else:
            print("- evidence-validation: FAILED", file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            raise SessionError("Evidence validation failed")
    except subprocess.TimeoutExpired:
        print("WARN: Evidence validation timed out after 300s", file=sys.stderr)
        raise SessionError("Evidence validation timeout")
    except Exception as e:
        print(f"WARN: Evidence validation error: {e}", file=sys.stderr)
        raise SessionError(f"Evidence validation error: {e}")


def cmd_verify(args: argparse.Namespace) -> int:
    requested_worktree_path = _resolve_worktree_path(args.worktree_path)
    repo_root = _git_root()
    hooks_status = _ensure_repo_hooks_config(repo_root)
    worktree_path = requested_worktree_path
    try:
        session = _read_session(worktree_path)
    except SessionError as exc:
        if f"Missing {SESSION_FILE}" not in str(exc):
            raise

        candidates = _find_nested_session_candidates(worktree_path)
        if len(candidates) == 1:
            worktree_path = candidates[0]
            session = _read_session(worktree_path)
            print(
                "WARN: Session file not found at requested path; using nested worktree "
                f"{worktree_path}",
                file=sys.stderr,
            )
        elif len(candidates) > 1:
            listed = "\n".join(f"  - {c}" for c in candidates)
            raise SessionError(
                f"Missing {SESSION_FILE} under {requested_worktree_path} "
                f"and found multiple nested session candidates:\n{listed}\n"
                "Re-run verify with an explicit --worktree-path to the correct child."
            ) from exc
        else:
            raise SessionError(
                f"Missing {SESSION_FILE} under {requested_worktree_path}. "
                "Initialize the session first with `session.py start`."
            ) from exc

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

    _validate_evidence_requirements(args, session)

    if args.require_main_merge_authority:
        if str(session.get("agent", "")).strip() != MERGE_AUTHORITY_AGENT:
            raise SessionError(
                "Main-merge operations are restricted to agent "
                f"{MERGE_AUTHORITY_AGENT!r}; current agent={session.get('agent')!r}"
            )

    if args.acquire_main_merge_lock:
        owner = _acquire_main_merge_lock(session, args.merge_lock_ttl_seconds)
        session["main_merge_lock_owner"] = owner
        session["main_merge_lock_acquired_at"] = _utc_now()
        _write_session(worktree_path, session)
        print(f"- main_merge_lock: {owner}")

    print("session.verify: OK")
    print(f"- worktree: {worktree_path}")
    print(f"- branch: {branch}")
    print(f"- story: {session.get('story_id')}")
    print(f"- hooks_path: {REPO_HOOKS_PATH} ({hooks_status})")
    return 0


def cmd_validate_evidence(args: argparse.Namespace) -> int:
    """Validate worker completion evidence using the evidence validator.

    Args:
        args: argparse.Namespace with attributes:
            - evidence_file: path to evidence file
            - strict: optional boolean flag

    Returns:
        Exit code: 0 for pass, 1 for fail
    """
    evidence_file = args.evidence_file

    if not evidence_file:
        print("ERROR: --evidence-file is required", file=sys.stderr)
        return 1

    # Build the command to run evidence_validator.py
    script_dir = Path(__file__).parent
    validator_script = script_dir / "evidence_validator.py"

    if not validator_script.exists():
        print(
            f"ERROR: evidence_validator.py not found at {validator_script}",
            file=sys.stderr,
        )
        return 1

    # Build command arguments
    cmd = [sys.executable, str(validator_script), "--evidence-file", evidence_file]

    # Add --strict flag if provided
    if getattr(args, "strict", False):
        cmd.append("--strict")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print("ERROR: Evidence validation timed out after 300s", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Evidence validation error: {e}", file=sys.stderr)
        return 1


def cmd_close(args: argparse.Namespace) -> int:
    worktree_path = _resolve_worktree_path(args.worktree_path)
    session = _read_session(worktree_path)
    branch = str(session["branch"])
    story_id = str(session.get("story_id", "")).strip() or "unknown-story"

    if args.auto_stash_dirty and not args.confirm_stash_last_resort:
        raise SessionError(
            "--auto-stash-dirty requires --confirm-stash-last-resort. "
            "Stash is intentionally guarded as a last-resort cleanup path."
        )

    dirty_entries = _git_dirty_entries(worktree_path)
    if dirty_entries:
        if args.auto_stash_dirty:
            stash_result = _stash_dirty_worktree(worktree_path, story_id, branch)
            print(f"- dirty_worktree: stashed ({stash_result})")
            dirty_entries = _git_dirty_entries(worktree_path)
            if dirty_entries:
                raise SessionError(
                    "Worktree still dirty after auto-stash; resolve manually and retry close."
                )
        elif args.allow_dirty:
            if not args.justification:
                raise SessionError(
                    'Using --allow-dirty requires --justification "<reason>". '
                    "Please provide a reason for closing with dirty worktree."
                )
            print(
                "WARN: Closing session with dirty worktree due to --allow-dirty.",
                file=sys.stderr,
            )
            # Log justification to iterlog
            ok, cfg = _redis_ping()
            if ok and cfg is not None:
                host, port, db = cfg
                key = f"bmad:chiseai:iterlog:story:{story_id}:close_justification"
                _redis_cli(host, port, db, "SET", key, args.justification)
        else:
            sample = "\n".join(f"  - {line}" for line in dirty_entries[:20])
            more = ""
            if len(dirty_entries) > 20:
                more = f"\n  ... ({len(dirty_entries) - 20} more)"
            raise SessionError(
                "Worktree has uncommitted changes; refusing to close session.\n"
                "Preferred resolution: commit, discard, or otherwise clean the "
                "worktree explicitly.\n"
                "Last resort: re-run with --auto-stash-dirty "
                "--confirm-stash-last-resort, or use --allow-dirty.\n"
                f"Dirty entries:\n{sample}{more}"
            )

    if args.remove_worktree and args.allow_dirty and dirty_entries:
        raise SessionError(
            "Cannot remove worktree while closing dirty session with --allow-dirty. "
            "Use --auto-stash-dirty or clean manually first."
        )

    if args.enforce_merged:
        ahead = _branch_ahead_count(worktree_path, branch, args.base_ref)
        if ahead > 0 and not args.allow_unmerged:
            has_pr, detail = _pr_exists_for_branch(branch, args.base_ref)
            if not has_pr:
                raise SessionError(
                    "Branch has commits ahead of "
                    f"{args.base_ref} (ahead={ahead}) and no open/merged PR was found. "
                    f"detail={detail}. Push/open PR before closing, or use --allow-unmerged."
                )
            print(
                f"- enforce_merged: ahead={ahead} but allowed due to PR status ({detail})"
            )
        else:
            print(f"- enforce_merged: ahead={ahead}")

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

    _release_main_merge_lock(session)

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


def cmd_unlock(args: argparse.Namespace) -> int:
    """Force-release the repo startup lock."""
    msg = _force_release_startup_lock()
    print(f"session.unlock: {msg}")
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
    start.add_argument("--worktree-path")
    start.add_argument("--ttl-seconds", type=int, default=432000)
    start.add_argument("--force", action="store_true")
    start.add_argument("--scopes", nargs="*", default=[])
    start.set_defaults(func=cmd_start)

    verify = sub.add_parser("verify", help="Verify session/branch/lease invariants")
    verify.add_argument("--worktree-path")
    verify.add_argument("--story-id")
    verify.add_argument("--branch")
    verify.add_argument("--check-canonical", action="store_true")
    verify.add_argument(
        "--force-unlock",
        action="store_true",
        help="Override canonical status lock; requires --justification.",
    )
    verify.add_argument(
        "--justification",
        default="",
        help="Reason for --force-unlock override (required with --force-unlock).",
    )
    verify.add_argument("--require-main-merge-authority", action="store_true")
    verify.add_argument("--acquire-main-merge-lock", action="store_true")
    verify.add_argument("--merge-lock-ttl-seconds", type=int, default=1800)
    verify.set_defaults(func=cmd_verify)

    validate_evidence = sub.add_parser(
        "validate-evidence", help="Validate worker completion evidence"
    )
    validate_evidence.add_argument(
        "--evidence-file", required=True, help="Path to evidence file"
    )
    validate_evidence.add_argument(
        "--strict", action="store_true", help="Enable strict validation mode"
    )
    validate_evidence.set_defaults(func=cmd_validate_evidence)

    close = sub.add_parser("close", help="Release leases and close worktree session")
    close.add_argument("--worktree-path")
    close.add_argument("--remove-worktree", action="store_true")
    close.add_argument("--auto-stash-dirty", action="store_true")
    close.add_argument("--confirm-stash-last-resort", action="store_true")
    close.add_argument("--allow-dirty", action="store_true")
    close.add_argument(
        "--justification",
        required=False,
        default="",
        help="Required when --allow-dirty is used. Reason for closing with dirty worktree.",
    )
    close.add_argument("--enforce-merged", action="store_true")
    close.add_argument("--allow-unmerged", action="store_true")
    close.add_argument("--base-ref", default="main")
    close.set_defaults(func=cmd_close)

    unlock = sub.add_parser(
        "unlock",
        help="Force-release the repo startup lock (use if a session crashed mid-startup)",
    )
    unlock.add_argument(
        "--force",
        action="store_true",
        help="Force release even if lock is held by another session",
    )
    unlock.set_defaults(func=cmd_unlock)

    return p


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)

    # Check critical environment variables
    check_critical_environment()

    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except SessionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
