from __future__ import annotations

import sys
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock, patch

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "pr_lifecycle"
    / "auto_pr_merge.py"
)
_SPEC = spec_from_file_location("auto_pr_merge", _MODULE_PATH)
assert _SPEC and _SPEC.loader
auto_pr_merge = module_from_spec(_SPEC)
sys.modules["auto_pr_merge"] = auto_pr_merge
_SPEC.loader.exec_module(auto_pr_merge)


def _cfg() -> auto_pr_merge.Config:
    return auto_pr_merge.Config(
        base_url="http://example.test",
        token="token",
        owner="craig",
        repo="ChiseAI",
        default_base="main",
        protected={"main", "develop"},
        allowed_authors={"chise-bot"},
        max_branch_age_min=30,
        source_branch="feature/test-branch",
        enable_server_automerge=False,
        dry_run=False,
    )


def test_ensure_prs_creates_new_pr_even_if_historical_pr_exists(monkeypatch) -> None:
    cfg = _cfg()
    ts = datetime.now(UTC).isoformat()

    monkeypatch.setattr(
        auto_pr_merge,
        "list_branches",
        lambda _cfg: [
            {"name": "feature/test-branch", "commit": {"timestamp": ts}},
        ],
    )
    monkeypatch.setattr(
        auto_pr_merge,
        "_branch_is_behind_main",
        lambda _cfg, _head_branch, _base_branch="main": (False, "up-to-date"),
    )
    monkeypatch.setattr(auto_pr_merge, "_open_pr_for_head", lambda _cfg, _name: None)

    calls: list[tuple[str, str, dict[str, str]]] = []

    def _fake_req(_cfg, method: str, path: str, body=None):
        if method == "POST" and path.endswith("/pulls"):
            calls.append((method, path, body))
            return {"number": 999}
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(auto_pr_merge, "_safe_req_json", _fake_req)

    created = auto_pr_merge.ensure_prs(cfg)
    assert created == 1
    assert len(calls) == 1


def test_branch_is_behind_main_uses_compare_api(monkeypatch) -> None:
    cfg = _cfg()

    def _fake_req(_cfg, method: str, path: str, body=None):
        assert method == "GET"
        assert path.endswith("/compare/main...feature%2Ftest-branch")
        return {"behind_by": 2, "ahead_by": 1}

    monkeypatch.setattr(auto_pr_merge, "_safe_req_json", _fake_req)

    is_stale, reason = auto_pr_merge._branch_is_behind_main(
        cfg, "feature/test-branch", "main"
    )
    assert is_stale is True
    assert "behind main by 2 commit(s)" in reason


@patch("auto_pr_merge._safe_req_json")
def test_auto_merge_merges_green_conflict_free_pr(mock_req_json: MagicMock) -> None:
    cfg = _cfg()
    cfg.enable_server_automerge = True
    pr = {
        "number": 42,
        "state": "open",
        "mergeable": True,
        "head": {
            "ref": "feature/test-branch",
            "sha": "abc123",
            "label": "craig:feature/test-branch",
        },
        "user": {"login": "chise-bot"},
    }

    def _fake_req(_cfg, method: str, path: str, body=None):
        if method == "GET" and "/pulls?state=open" in path:
            return [pr]
        if method == "GET" and path.endswith("/pulls/42"):
            return pr
        if method == "GET" and path.endswith("/commits/abc123/status"):
            return {"state": "success"}
        if method == "GET" and path.endswith("/commits/abc123/statuses"):
            return []  # ci-gate context not posted yet — pass through
        if method == "POST" and path.endswith("/pulls/42/merge"):
            return {"merged": True}
        raise AssertionError(f"Unexpected request: {method} {path}")

    mock_req_json.side_effect = _fake_req

    assert auto_pr_merge.auto_merge(cfg) == 1


@patch("auto_pr_merge._safe_req_json")
def test_auto_merge_skips_unmerged_pr_when_status_not_green(
    mock_req_json: MagicMock,
) -> None:
    cfg = _cfg()
    cfg.enable_server_automerge = True
    pr = {
        "number": 42,
        "state": "open",
        "mergeable": True,
        "head": {
            "ref": "feature/test-branch",
            "sha": "abc123",
            "label": "craig:feature/test-branch",
        },
        "user": {"login": "chise-bot"},
    }

    def _fake_req(_cfg, method: str, path: str, body=None):
        if method == "GET" and "/pulls?state=open" in path:
            return [pr]
        if method == "GET" and path.endswith("/pulls/42"):
            return pr
        if method == "GET" and path.endswith("/commits/abc123/status"):
            return {"state": "pending"}
        raise AssertionError(f"Unexpected request: {method} {path}")

    mock_req_json.side_effect = _fake_req

    assert auto_pr_merge.auto_merge(cfg) == 0


@patch("auto_pr_merge._safe_req_json")
def test_auto_merge_skips_when_ci_gate_context_fails(
    mock_req_json: MagicMock,
) -> None:
    cfg = _cfg()
    cfg.enable_server_automerge = True
    pr = {
        "number": 42,
        "state": "open",
        "mergeable": True,
        "head": {
            "ref": "feature/test-branch",
            "sha": "abc123",
            "label": "craig:feature/test-branch",
        },
        "user": {"login": "chise-bot"},
    }

    def _fake_req(_cfg, method: str, path: str, body=None):
        if method == "GET" and "/pulls?state=open" in path:
            return [pr]
        if method == "GET" and path.endswith("/pulls/42"):
            return pr
        if method == "GET" and path.endswith("/commits/abc123/status"):
            return {"state": "success"}  # aggregate passes
        if method == "GET" and path.endswith("/commits/abc123/statuses"):
            return [{"context": "ci-gate", "status": "failure"}]  # ci-gate fails
        raise AssertionError(f"Unexpected request: {method} {path}")

    mock_req_json.side_effect = _fake_req

    assert auto_pr_merge.auto_merge(cfg) == 0


@patch("auto_pr_merge._safe_req_json")
def test_auto_merge_skips_when_ci_gate_context_error(
    mock_req_json: MagicMock,
) -> None:
    cfg = _cfg()
    cfg.enable_server_automerge = True
    pr = {
        "number": 42,
        "state": "open",
        "mergeable": True,
        "head": {
            "ref": "feature/test-branch",
            "sha": "abc123",
            "label": "craig:feature/test-branch",
        },
        "user": {"login": "chise-bot"},
    }

    def _fake_req(_cfg, method: str, path: str, body=None):
        if method == "GET" and "/pulls?state=open" in path:
            return [pr]
        if method == "GET" and path.endswith("/pulls/42"):
            return pr
        if method == "GET" and path.endswith("/commits/abc123/status"):
            return {"state": "success"}  # aggregate passes
        if method == "GET" and path.endswith("/commits/abc123/statuses"):
            return [{"context": "ci-gate", "status": "error"}]  # ci-gate errors
        raise AssertionError(f"Unexpected request: {method} {path}")

    mock_req_json.side_effect = _fake_req

    assert auto_pr_merge.auto_merge(cfg) == 0
