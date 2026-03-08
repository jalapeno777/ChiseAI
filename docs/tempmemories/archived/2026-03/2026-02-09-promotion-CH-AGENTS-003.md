---
project: ChiseAI
scope: memory-promotion
type: pattern
story_id: CH-AGENTS-003
epic_id: EP-OPS-AUTONOMY
tags: [parallelism, scope-ownership, review-bot, ci]
date: 2026-02-09
---

## Summary

- What changed?
  - Added/standardized parallel delegation safety (scope ownership, incident logging) and autonomous PR review via `chise-review-bot`.
  - CI was briefly blocking merge due to `black --check` failing on `scripts/iterlog_ops.py`; fixed by formatting and pushing.

- Why it matters?
  - Parallel work is faster but unsafe without explicit scope ownership and a repeatable incident-to-prevention loop.
  - The "review required" gate can remain enabled while still being autonomous (bot approval).

- Where it applies?
  - Opencode agents: `.opencode/agent/*`
  - Ownership/incidents tooling: `scripts/iterlog_ops.py`, `.opencode/command/chise-*-ownership.md`, `.opencode/command/chise-append-incident.md`
  - PR review automation: `scripts/gitea_pr_review.py`, `.opencode/agent/GitReviewBot.md`

## Decisions (Promote)

- Decision: Keep required review gate enabled, satisfy it autonomously via dedicated Gitea bot user/token.
  - Rationale: preserves safety invariant (review before merge) without slowing day-to-day development.
  - Constraints: bot must deny with actionable feedback; approvals should be based on at least two independent review perspectives (senior-dev + critic).
  - Applies_to: all PRs to `main`.

## Patterns / Recipes (Promote)

- Pattern: "Parallel batch plan" + "scope ownership" before delegation.
  - When_to_use: Aria/Jarvis delegating multiple workstreams or multiple tasks within a story.
  - When_not_to_use: infra/CI/governance/global changes; treat as sequential-by-default.
  - Example_command_or_snippet:
    - `python3 scripts/iterlog_ops.py claim-ownership --story-id CH-AGENTS-003 --agent jarvis --scopes .opencode/ scripts/`

- Pattern: "Incident to prevention rule" logged during execution.
  - When_to_use: merge conflicts, CI regressions, repeated blockers.
  - Example_command_or_snippet:
    - `python3 scripts/iterlog_ops.py append-incident --story-id CH-AGENTS-003 --text "...prevention_rule: ..."`

## Incident Prevention Rules (Promote)

- prevention_rule:
  - incident_ref: iterlog `CH-AGENTS-003` (black formatting failure)
  - how_to_detect_early: run the full lint stack locally matching `.woodpecker.yml` before push.
  - how_to_prevent: keep scripts formatted; add a local pre-push hook if this becomes frequent.

## Verification

- Tests/commands run:
  - `black --check .`
  - `ruff check .`
  - `mypy src tests scripts`
  - `python3 scripts/validate_status_sync.py`
  - `python3 scripts/validate_iterloop_compliance.py`

- Evidence:
  - PR #28 merged to `main` (2026-02-09)
