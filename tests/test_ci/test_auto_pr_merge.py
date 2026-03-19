from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "pr_lifecycle" / "auto_pr_merge.py"
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
    monkeypatch.setattr(auto_pr_merge, "_open_pr_for_head", lambda _cfg, _name: None)

    # Regression guard: we should no longer block PR creation just because
    # a historical (closed/merged) PR exists for this branch name.
    monkeypatch.setattr(
        auto_pr_merge,
        "_any_pr_for_head",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("_any_pr_for_head should not be used by ensure_prs")
        ),
    )

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
