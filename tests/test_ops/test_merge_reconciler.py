from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "merge_reconciler.py"
)
SPEC = importlib.util.spec_from_file_location("merge_reconciler", MODULE_PATH)
assert SPEC and SPEC.loader
merge_reconciler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = merge_reconciler
SPEC.loader.exec_module(merge_reconciler)


class FakeStore:
    def __init__(self) -> None:
        self.data: dict[str, list[str]] = {}
        self.lock_owner: str | None = None

    def enqueue(self, key: str, value: str) -> None:
        self.data.setdefault(key, []).append(value)

    def pop(self, key: str) -> str | None:
        queue = self.data.setdefault(key, [])
        if not queue:
            return None
        return queue.pop(0)

    def list(self, key: str, start: int = 0, end: int = -1) -> list[str]:
        queue = self.data.setdefault(key, [])
        if end == -1:
            return queue[start:]
        return queue[start : end + 1]

    def get(self, key: str) -> str | None:
        values = self.data.get(key, [])
        return values[-1] if values else None

    def acquire_lock(
        self, key: str, owner: str, ttl_seconds: int
    ) -> bool:  # noqa: ARG002
        if self.lock_owner is not None:
            return False
        self.lock_owner = owner
        return True

    def release_lock(self, key: str, owner: str) -> None:  # noqa: ARG002
        if self.lock_owner == owner:
            self.lock_owner = None


class FakeGitea:
    def __init__(self, *, pr: dict, status: dict, merge_error: bool = False) -> None:
        self.pr = pr
        self.status = status
        self.merge_error = merge_error
        self.merge_calls = 0

    def get_pr(self, pr_number: int) -> dict:
        assert pr_number == int(self.pr["number"])
        return self.pr

    def get_commit_status(self, sha: str) -> dict:
        assert sha == self.pr["head"]["sha"]
        return self.status

    def merge_pr(
        self, pr_number: int, head_sha: str, delete_branch: bool = True
    ) -> dict:  # noqa: ARG002
        assert pr_number == int(self.pr["number"])
        assert head_sha == self.pr["head"]["sha"]
        self.merge_calls += 1
        if self.merge_error:
            raise RuntimeError("merge failed")
        return {"ok": True}


def _mk_item() -> merge_reconciler.MergeQueueItem:
    return merge_reconciler.MergeQueueItem(
        story_id="ST-1",
        branch="feature/st1",
        pr_number=7,
        head_sha="abc123",
        queued_by="jarvis",
    )


def test_required_context_state_success_and_failure() -> None:
    assert (
        merge_reconciler.required_context_state(
            {
                "statuses": [
                    {"context": "ci/woodpecker/push/woodpecker", "state": "success"},
                ]
            },
            "ci/woodpecker/push/woodpecker",
        )
        == "success"
    )
    assert (
        merge_reconciler.required_context_state(
            {
                "statuses": [
                    {"context": "ci/woodpecker/push/woodpecker", "state": "failure"},
                ]
            },
            "ci/woodpecker/push/woodpecker",
        )
        == "failure"
    )


def test_process_item_ci_failure_emits_incident_and_requeues() -> None:
    store = FakeStore()
    gitea = FakeGitea(
        pr={
            "number": 7,
            "state": "open",
            "merged": False,
            "head": {"sha": "abc123"},
            "mergeable": True,
        },
        status={
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "failure"}
            ]
        },
    )
    engine = merge_reconciler.MergeQueueEngine(store, gitea)

    action, maybe_item = engine.process_item(
        _mk_item(),
        required_context="ci/woodpecker/push/woodpecker",
        max_retries=3,
        allow_merge=True,
    )

    assert action == "ci_failed_requeued"
    assert maybe_item is not None
    assert maybe_item.retries == 1
    incidents = store.list(merge_reconciler.INCIDENTS_KEY)
    assert len(incidents) == 1
    assert json.loads(incidents[0])["kind"] == "ci_not_green"


def test_queue_tick_merges_when_green_and_allow_merge() -> None:
    store = FakeStore()
    gitea = FakeGitea(
        pr={
            "number": 7,
            "state": "open",
            "merged": False,
            "head": {"sha": "abc123"},
            "mergeable": True,
        },
        status={
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "success"}
            ]
        },
    )
    engine = merge_reconciler.MergeQueueEngine(store, gitea)
    store.enqueue(merge_reconciler.MERGE_QUEUE_KEY, _mk_item().to_json())

    result = engine.queue_tick(
        owner="jarvis/test",
        ttl_seconds=30,
        max_items=1,
        required_context="ci/woodpecker/push/woodpecker",
        max_retries=3,
        allow_merge=True,
    )

    assert result["status"] == "ok"
    assert result["processed"] == 1
    assert gitea.merge_calls == 1
    assert store.list(merge_reconciler.MERGE_QUEUE_KEY) == []


def test_reconcile_git_hygiene_detects_main_unsynced(monkeypatch) -> None:
    store = FakeStore()

    def fake_run_git(*args: str) -> tuple[int, str, str]:
        cmd = " ".join(args)
        if cmd == "fetch --all --prune":
            return 0, "", ""
        if cmd == "rev-parse main":
            return 0, "aaa", ""
        if cmd == "rev-parse refs/remotes/origin/main":
            return 0, "bbb", ""
        if cmd == "for-each-ref --format=%(refname:short) refs/heads":
            return 0, "main\nfeature/x", ""
        if cmd == "rev-list --count main..feature/x":
            return 0, "2", ""
        return 1, "", "unknown"

    monkeypatch.setattr(merge_reconciler, "_run_git", fake_run_git)
    actions = merge_reconciler.reconcile_git_hygiene(store)

    assert "main_unsynced_incident" in actions
    assert "ahead_incident:feature/x" in actions
    incidents = store.list(merge_reconciler.INCIDENTS_KEY)
    kinds = [json.loads(row)["kind"] for row in incidents]
    assert "main_unsynced" in kinds
    assert "local_branch_ahead_main" in kinds


def test_require_merge_authority_rejects_non_merlin(monkeypatch) -> None:
    store = FakeStore()
    store.enqueue(merge_reconciler.MERGE_LOCK_KEY, "ST-1/merlin/2026-01-01T00:00:00Z")
    monkeypatch.setenv("AGENT_ID", "jarvis")
    monkeypatch.delenv("CHISE_ALLOW_NON_MERLIN_MERGE", raising=False)

    with pytest.raises(RuntimeError, match="restricted to agent 'merlin'"):
        merge_reconciler._require_merge_authority_and_lock(store, "jarvis/reconcile")


def test_require_merge_authority_requires_lock(monkeypatch) -> None:
    store = FakeStore()
    monkeypatch.setenv("AGENT_ID", "merlin")
    monkeypatch.delenv("CHISE_ALLOW_NON_MERLIN_MERGE", raising=False)

    with pytest.raises(RuntimeError, match="Main merge lock is not held"):
        merge_reconciler._require_merge_authority_and_lock(store, "merlin/queue")
