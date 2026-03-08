---
project: ChiseAI
scope: ci-title-governance
type: iterlog
story_id: CH-CI-PRTITLE-002
story_title: "PR title normalization and story-id awareness across agents/scripts"
phase: implementation
status: completed
started_at: "2026-02-17T00:00:00Z"
completed_at: "2026-02-17T00:30:00Z"
---

## Acceptance Criteria

- AC1: `validate_pr_title` accepts active story-id patterns used by automated branches/PRs (including PAPER-LOOP style) and keeps digit requirement.
- AC2: `gitea_pr_automerge` generates/patches PR titles without duplicate story-id prefixes and validates provided story-id format.
- AC3: `merlin_pr_sweep` story-id resolution supports same accepted patterns as validation/automerge.
- AC4: opencode command/skill guidance explicitly requires passing canonical `STORY_ID` to PR automation paths.
- AC5: CI tests cover new PR-title behaviors and pass.

## Decisions

- Added shared parser module `scripts/story_id.py` and used it in title validation + PR automation scripts.
- Expanded accepted prefixes for active automation flows to include `PAPER-*` and `RECON-*`.

## Learnings

- Title-validation and PR-creation logic drift is a recurrent source of CI noise; shared parser removes this class of mismatch.
- Prefixing logic must be token-aware to avoid duplicated title prefixes.

## Scope Ownership

- scripts/validate_pr_title.py
- scripts/gitea_pr_automerge.py
- scripts/ops/merlin_pr_sweep.py
- .opencode/command/*.md and .opencode/skills/chiseai-git-workflow/SKILL.md

## Incidents

- None.

## Evidence

- `python3 -m pytest -q tests/test_ci/test_validate_pr_title.py tests/test_ops/test_merlin_pr_sweep.py tests/test_gitea_pr_automerge.py`
- `python3 scripts/validate_status_sync.py`
