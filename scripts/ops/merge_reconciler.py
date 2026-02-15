#!/usr/bin/env python3
"""Merge queue + reconcile helpers for Opencode/Jarvis workflows.

Design goals:
- Keep merges serialized through Redis lock keys.
- Let workers enqueue and continue work in isolated worktrees.
- Perform bounded ticks so reconcile loops do not starve active development.
- Emit structured incidents for Jarvis/Merlin escalation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

MERGE_QUEUE_KEY = "bmad:chiseai:merge-queue:main"
INCIDENTS_KEY = "bmad:chiseai:reconcile:incidents"
RECONCILE_LOCK_KEY = "bmad:chiseai:reconcile-lock"
MERGE_LOCK_KEY = "bmad:chiseai:merge-lock:main"


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class MergeQueueItem:
    story_id: str
    branch: str
    pr_number: int
    head_sha: str
    queued_by: str
    queued_at: str = field(default_factory=_utc_now)
    retries: int = 0
    priority: str = "normal"
    global_lock_touched: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "story_id": self.story_id,
                "branch": self.branch,
                "pr_number": self.pr_number,
                "head_sha": self.head_sha,
                "queued_by": self.queued_by,
                "queued_at": self.queued_at,
                "retries": self.retries,
                "priority": self.priority,
                "global_lock_touched": self.global_lock_touched,
                "metadata": self.metadata,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> "MergeQueueItem":
        obj = json.loads(raw)
        return cls(
            story_id=str(obj["story_id"]),
            branch=str(obj["branch"]),
            pr_number=int(obj["pr_number"]),
            head_sha=str(obj["head_sha"]),
            queued_by=str(obj.get("queued_by", "unknown")),
            queued_at=str(obj.get("queued_at", _utc_now())),
            retries=int(obj.get("retries", 0)),
            priority=str(obj.get("priority", "normal")),
            global_lock_touched=bool(obj.get("global_lock_touched", False)),
            metadata=dict(obj.get("metadata", {})),
        )


@dataclass
class Incident:
    kind: str
    story_id: str
    branch: str
    pr_number: int | None
    pipeline_number: int | None
    message: str
    recommended_agent: str = "jarvis"
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "story_id": self.story_id,
                "branch": self.branch,
                "pr_number": self.pr_number,
                "pipeline_number": self.pipeline_number,
                "message": self.message,
                "recommended_agent": self.recommended_agent,
                "evidence": self.evidence,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )


class QueueStore(Protocol):
    def enqueue(self, key: str, value: str) -> None: ...

    def pop(self, key: str) -> str | None: ...

    def list(self, key: str, start: int = 0, end: int = -1) -> list[str]: ...

    def acquire_lock(self, key: str, owner: str, ttl_seconds: int) -> bool: ...

    def release_lock(self, key: str, owner: str) -> None: ...


class RedisCliStore:
    def __init__(self, host: str, port: int, db: int):
        self.host = host
        self.port = port
        self.db = db

    def _run(self, *args: str) -> str:
        proc = subprocess.run(
            ["redis-cli", "-h", self.host, "-p", str(self.port), "-n", str(self.db), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"redis-cli failed: {' '.join(args)}")
        return proc.stdout.strip()

    def enqueue(self, key: str, value: str) -> None:
        self._run("RPUSH", key, value)

    def pop(self, key: str) -> str | None:
        out = self._run("LPOP", key)
        if out == "":
            return None
        return out

    def list(self, key: str, start: int = 0, end: int = -1) -> list[str]:
        out = self._run("LRANGE", key, str(start), str(end))
        return [line for line in out.splitlines() if line.strip()]

    def acquire_lock(self, key: str, owner: str, ttl_seconds: int) -> bool:
        out = self._run("SET", key, owner, "NX", "EX", str(ttl_seconds))
        return out == "OK"

    def release_lock(self, key: str, owner: str) -> None:
        current = self._run("GET", key)
        if current == owner:
            self._run("DEL", key)


class GiteaClient:
    def __init__(self, base_url: str, owner: str, repo: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.owner = owner
        self.repo = repo
        self.token = token

    def _req_json(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"token {self.token}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            msg = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {msg}") from exc

    def get_pr(self, pr_number: int) -> dict[str, Any]:
        return self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}",
        )

    def get_commit_status(self, sha: str) -> dict[str, Any]:
        return self._req_json(
            "GET",
            f"/api/v1/repos/{self.owner}/{self.repo}/commits/{sha}/status",
        )

    def merge_pr(self, pr_number: int, head_sha: str, delete_branch: bool = True) -> dict[str, Any]:
        return self._req_json(
            "POST",
            f"/api/v1/repos/{self.owner}/{self.repo}/pulls/{pr_number}/merge",
            {
                "Do": "merge",
                "head_commit_id": head_sha,
                "merge_when_checks_succeed": False,
                "delete_branch_after_merge": delete_branch,
            },
        )


def required_context_state(
    commit_status: dict[str, Any],
    required_context: str,
) -> str:
    """Return success|pending|failure|missing for a required context."""
    statuses = commit_status.get("statuses")
    if isinstance(statuses, list):
        matching = [
            s for s in statuses if isinstance(s, dict) and str(s.get("context", "")) == required_context
        ]
        if matching:
            states = {str(s.get("state", "")).lower() for s in matching}
            if states.intersection({"failure", "error"}):
                return "failure"
            if "pending" in states:
                return "pending"
            if "success" in states and len(states) == 1:
                return "success"
            return "pending"
    overall = str(commit_status.get("state", "")).lower()
    if overall in {"failure", "error"}:
        return "failure"
    if overall == "success":
        return "success"
    if overall == "pending":
        return "pending"
    return "missing"


class MergeQueueEngine:
    def __init__(
        self,
        store: QueueStore,
        gitea: GiteaClient,
        *,
        queue_key: str = MERGE_QUEUE_KEY,
        incidents_key: str = INCIDENTS_KEY,
        lock_key: str = RECONCILE_LOCK_KEY,
    ):
        self.store = store
        self.gitea = gitea
        self.queue_key = queue_key
        self.incidents_key = incidents_key
        self.lock_key = lock_key

    def _emit_incident(self, incident: Incident) -> None:
        self.store.enqueue(self.incidents_key, incident.to_json())

    def enqueue_item(self, item: MergeQueueItem) -> None:
        self.store.enqueue(self.queue_key, item.to_json())

    def queue_items(self) -> list[MergeQueueItem]:
        return [MergeQueueItem.from_json(raw) for raw in self.store.list(self.queue_key, 0, -1)]

    def process_item(
        self,
        item: MergeQueueItem,
        *,
        required_context: str,
        max_retries: int,
        allow_merge: bool,
    ) -> tuple[str, MergeQueueItem | None]:
        pr = self.gitea.get_pr(item.pr_number)
        state = str(pr.get("state", "")).lower()
        merged = bool(pr.get("merged", False))

        if merged:
            return "merged_already", None
        if state == "closed":
            self._emit_incident(
                Incident(
                    kind="pr_closed_unmerged",
                    story_id=item.story_id,
                    branch=item.branch,
                    pr_number=item.pr_number,
                    pipeline_number=None,
                    message="PR closed without merge while in merge queue",
                    recommended_agent="jarvis",
                    evidence={"pr_state": state},
                )
            )
            return "closed_unmerged", None

        pr_head_sha = str((pr.get("head") or {}).get("sha", ""))
        if pr_head_sha and pr_head_sha != item.head_sha:
            item.head_sha = pr_head_sha
            item.retries += 1
            return "stale_head_requeued", item

        status = self.gitea.get_commit_status(item.head_sha)
        ctx_state = required_context_state(status, required_context)
        if ctx_state in {"pending", "missing"}:
            item.retries += 1
            return "waiting_ci_requeued", item
        if ctx_state == "failure":
            self._emit_incident(
                Incident(
                    kind="ci_not_green",
                    story_id=item.story_id,
                    branch=item.branch,
                    pr_number=item.pr_number,
                    pipeline_number=None,
                    message=f"Required context {required_context!r} is failing",
                    recommended_agent="merlin",
                    evidence={"required_context": required_context},
                )
            )
            item.retries += 1
            if item.retries >= max_retries:
                return "max_retries_dropped", None
            return "ci_failed_requeued", item

        if not allow_merge:
            return "merge_skipped_success", item

        if pr.get("mergeable") is False:
            self._emit_incident(
                Incident(
                    kind="merge_conflict",
                    story_id=item.story_id,
                    branch=item.branch,
                    pr_number=item.pr_number,
                    pipeline_number=None,
                    message="PR is not mergeable (conflict or blocked)",
                    recommended_agent="merlin",
                )
            )
            return "merge_conflict", None

        try:
            self.gitea.merge_pr(item.pr_number, item.head_sha, delete_branch=True)
            return "merge_triggered", None
        except RuntimeError as exc:
            self._emit_incident(
                Incident(
                    kind="merge_api_error",
                    story_id=item.story_id,
                    branch=item.branch,
                    pr_number=item.pr_number,
                    pipeline_number=None,
                    message=f"Merge API error: {exc}",
                    recommended_agent="merlin",
                )
            )
            item.retries += 1
            if item.retries >= max_retries:
                return "max_retries_dropped", None
            return "merge_error_requeued", item

    def queue_tick(
        self,
        *,
        owner: str,
        ttl_seconds: int,
        max_items: int,
        required_context: str,
        max_retries: int,
        allow_merge: bool,
    ) -> dict[str, Any]:
        if not self.store.acquire_lock(self.lock_key, owner, ttl_seconds):
            return {"status": "skipped_lock_held", "processed": 0, "actions": []}

        actions: list[str] = []
        processed = 0
        try:
            for _ in range(max_items):
                raw = self.store.pop(self.queue_key)
                if raw is None:
                    break
                item = MergeQueueItem.from_json(raw)
                processed += 1
                action, requeue = self.process_item(
                    item,
                    required_context=required_context,
                    max_retries=max_retries,
                    allow_merge=allow_merge,
                )
                actions.append(f"pr#{item.pr_number}:{action}")
                if requeue is not None:
                    self.store.enqueue(self.queue_key, requeue.to_json())
        finally:
            self.store.release_lock(self.lock_key, owner)

        return {"status": "ok", "processed": processed, "actions": actions}


def _run_git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def reconcile_git_hygiene(store: QueueStore) -> list[str]:
    """Non-destructive integrity checks written as incidents when needed."""
    actions: list[str] = []
    _run_git("fetch", "--all", "--prune")

    rc_main, main_sha, _ = _run_git("rev-parse", "main")
    rc_remote, remote_sha, _ = _run_git("rev-parse", "refs/remotes/gitea/main")
    if rc_main == 0 and rc_remote == 0 and main_sha != remote_sha:
        incident = Incident(
            kind="main_unsynced",
            story_id="RECONCILE",
            branch="main",
            pr_number=None,
            pipeline_number=None,
            message="Local main is not synced to gitea/main",
            recommended_agent="jarvis",
            evidence={"main_sha": main_sha, "gitea_main_sha": remote_sha},
        )
        store.enqueue(INCIDENTS_KEY, incident.to_json())
        actions.append("main_unsynced_incident")

    rc, out, _ = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    if rc == 0:
        local_branches = [b for b in out.splitlines() if b.strip() and b.strip() != "main"]
        for branch in local_branches:
            rc_a, ahead, _ = _run_git("rev-list", "--count", f"main..{branch}")
            if rc_a != 0:
                continue
            if int(ahead or "0") > 0:
                incident = Incident(
                    kind="local_branch_ahead_main",
                    story_id="RECONCILE",
                    branch=branch,
                    pr_number=None,
                    pipeline_number=None,
                    message="Local branch has commits ahead of main",
                    recommended_agent="jarvis",
                    evidence={"ahead_count": int(ahead)},
                )
                store.enqueue(INCIDENTS_KEY, incident.to_json())
                actions.append(f"ahead_incident:{branch}")

    return actions


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _build_store_from_env() -> RedisCliStore:
    host = _env("CHISE_REDIS_HOST", _env("REDIS_HOST", "host.docker.internal"))
    port = int(_env("CHISE_REDIS_PORT", _env("REDIS_PORT", "6380")) or "6380")
    db = int(_env("CHISE_REDIS_DB", _env("REDIS_DB", "0")) or "0")
    return RedisCliStore(host, port, db)


def _build_gitea_from_env() -> GiteaClient:
    token = _env("GITEA_TOKEN")
    if not token:
        raise RuntimeError("GITEA_TOKEN is required")
    base_url = _env("GITEA_BASE_URL", "http://host.docker.internal:3000")
    owner = _env("GITEA_OWNER", "craig")
    repo = _env("GITEA_REPO", "ChiseAI")
    return GiteaClient(base_url, owner, repo, token)


def cmd_enqueue(args: argparse.Namespace) -> int:
    store = _build_store_from_env()
    gitea = _build_gitea_from_env()
    engine = MergeQueueEngine(store, gitea)
    item = MergeQueueItem(
        story_id=args.story_id,
        branch=args.branch,
        pr_number=args.pr_number,
        head_sha=args.head_sha,
        queued_by=args.queued_by,
        priority=args.priority,
        global_lock_touched=args.global_lock_touched,
        metadata={"source": "opencode"},
    )
    engine.enqueue_item(item)
    print(f"enqueued pr#{item.pr_number} branch={item.branch} story={item.story_id}")
    return 0


def cmd_queue_status(args: argparse.Namespace) -> int:
    store = _build_store_from_env()
    gitea = _build_gitea_from_env()
    engine = MergeQueueEngine(store, gitea)
    rows = engine.queue_items()
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}. pr#{row.pr_number} branch={row.branch} story={row.story_id} "
            f"retries={row.retries} queued_at={row.queued_at}"
        )
    if not rows:
        print("merge queue is empty")
    return 0


def cmd_queue_tick(args: argparse.Namespace) -> int:
    store = _build_store_from_env()
    gitea = _build_gitea_from_env()
    engine = MergeQueueEngine(store, gitea)
    result = engine.queue_tick(
        owner=args.owner,
        ttl_seconds=args.lock_ttl_seconds,
        max_items=args.max_items,
        required_context=args.required_context,
        max_retries=args.max_retries,
        allow_merge=args.allow_merge,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_reconcile_tick(args: argparse.Namespace) -> int:
    store = _build_store_from_env()
    gitea = _build_gitea_from_env()
    engine = MergeQueueEngine(store, gitea)
    queue_result = engine.queue_tick(
        owner=args.owner,
        ttl_seconds=args.lock_ttl_seconds,
        max_items=args.max_items,
        required_context=args.required_context,
        max_retries=args.max_retries,
        allow_merge=args.allow_merge,
    )
    hygiene_actions = reconcile_git_hygiene(store)
    result = {
        "queue": queue_result,
        "hygiene_actions": hygiene_actions,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_intake_incidents(args: argparse.Namespace) -> int:
    store = _build_store_from_env()
    raw = store.list(INCIDENTS_KEY, 0, args.limit - 1)
    if args.drain:
        for _ in raw:
            store.pop(INCIDENTS_KEY)
    for idx, row in enumerate(raw, start=1):
        try:
            obj = json.loads(row)
        except json.JSONDecodeError:
            print(f"{idx}. {row}")
            continue
        print(
            f"{idx}. kind={obj.get('kind')} story={obj.get('story_id')} "
            f"branch={obj.get('branch')} agent={obj.get('recommended_agent')} "
            f"msg={obj.get('message')}"
        )
    if not raw:
        print("no reconcile incidents")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ChiseAI merge queue + reconcile utility")
    sub = p.add_subparsers(dest="cmd", required=True)

    enqueue = sub.add_parser("enqueue", help="Add PR item to main merge queue")
    enqueue.add_argument("--story-id", required=True)
    enqueue.add_argument("--branch", required=True)
    enqueue.add_argument("--pr-number", required=True, type=int)
    enqueue.add_argument("--head-sha", required=True)
    enqueue.add_argument("--queued-by", default="jarvis")
    enqueue.add_argument("--priority", default="normal")
    enqueue.add_argument("--global-lock-touched", action="store_true")
    enqueue.set_defaults(func=cmd_enqueue)

    qstatus = sub.add_parser("queue-status", help="List queued merge items")
    qstatus.set_defaults(func=cmd_queue_status)

    qtick = sub.add_parser("queue-tick", help="Process bounded merge queue tick")
    qtick.add_argument("--owner", default="jarvis/reconcile")
    qtick.add_argument("--lock-ttl-seconds", type=int, default=90)
    qtick.add_argument("--max-items", type=int, default=3)
    qtick.add_argument("--required-context", default="ci/woodpecker/push/woodpecker")
    qtick.add_argument("--max-retries", type=int, default=5)
    qtick.add_argument("--allow-merge", action="store_true")
    qtick.set_defaults(func=cmd_queue_tick)

    reconcile = sub.add_parser("reconcile-tick", help="Run queue tick + git hygiene checks")
    reconcile.add_argument("--owner", default="jarvis/reconcile")
    reconcile.add_argument("--lock-ttl-seconds", type=int, default=90)
    reconcile.add_argument("--max-items", type=int, default=3)
    reconcile.add_argument("--required-context", default="ci/woodpecker/push/woodpecker")
    reconcile.add_argument("--max-retries", type=int, default=5)
    reconcile.add_argument("--allow-merge", action="store_true")
    reconcile.set_defaults(func=cmd_reconcile_tick)

    intake = sub.add_parser("intake-incidents", help="List/drain reconcile incidents")
    intake.add_argument("--limit", type=int, default=50)
    intake.add_argument("--drain", action="store_true")
    intake.set_defaults(func=cmd_intake_incidents)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
