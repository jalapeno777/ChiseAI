from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "merlin_pr_sweep.py"
SPEC = importlib.util.spec_from_file_location("merlin_pr_sweep", MODULE_PATH)
assert SPEC and SPEC.loader
merlin_pr_sweep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = merlin_pr_sweep
SPEC.loader.exec_module(merlin_pr_sweep)


def test_resolve_story_id_prefers_exact_mapping() -> None:
    mapping = {"exact": {"feature/no-story-here": "CH-GIT-MERLIN-PR-002"}}
    assert (
        merlin_pr_sweep.resolve_story_id("feature/no-story-here", mapping)
        == "CH-GIT-MERLIN-PR-002"
    )


def test_resolve_story_id_falls_back_to_branch_regex() -> None:
    mapping = {"exact": {}}
    assert (
        merlin_pr_sweep.resolve_story_id("feature/ST-NS-019-risk-updates", mapping)
        == "ST-NS-019"
    )


def test_validate_consolidation_args_requires_supersession_pr() -> None:
    args = merlin_pr_sweep.parse_args(
        [
            "--consolidation-mode",
            "--supersede-pr",
            "101",
        ]
    )
    with pytest.raises(merlin_pr_sweep.SweepError, match="requires --supersession-pr"):
        merlin_pr_sweep.validate_consolidation_args(args)


def test_build_supersession_comment_contains_direct_link() -> None:
    comment = merlin_pr_sweep.build_supersession_comment(
        77,
        base_url="http://host.docker.internal:3000",
        owner="craig",
        repo="ChiseAI",
    )
    assert "#77" in comment
    assert "http://host.docker.internal:3000/craig/ChiseAI/pulls/77" in comment


def test_main_consolidation_mode_posts_comments(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[int, str]] = []

    def fake_post(pr_number: int, comment: str, **kwargs: object) -> None:  # noqa: ANN003
        calls.append((pr_number, comment))

    monkeypatch.setenv("AGENT_ID", "merlin")
    monkeypatch.setenv("GITEA_TOKEN", "token")
    monkeypatch.setattr(merlin_pr_sweep, "post_supersession_comment", fake_post)

    rc = merlin_pr_sweep.main(
        [
            "--dry-run",
            "--include-branch",
            "feature/ST-NS-020-ci-fix",
            "--consolidation-mode",
            "--supersession-pr",
            "88",
            "--supersede-pr",
            "70",
            "--supersede-pr",
            "71",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["consolidation_mode"] is True
    # dry-run path prints instead of API calls
    assert calls == []
