---
project: ChiseAI
scope: git-governance
type: iterlog
story_id: CH-GIT-MERLIN-PR-001
story_title: "Merlin-only PR governance and CI triage flow"
phase: implementation
status: completed
started_at: "2026-02-16T00:00:00Z"
completed_at: "2026-02-16T00:00:00Z"
acceptance_criteria:
  - "AC1: Governance docs state Merlin is the only agent allowed to open PRs and perform merge/prune git hygiene actions."
  - "AC2: Worker/Jarvis flow requires local CI + push + report to Jarvis; Jarvis delegates PR sweep to Merlin."
  - "AC3: Merlin instructions include deterministic Gitea/Woodpecker diagnosis flow using chise-ci-root-cause and failure bundles."
  - "AC4: Process defines branch discovery, systemic-failure consolidation branch strategy, and safe obsolete branch pruning without data loss."
  - "AC5: PR automation command/script enforces Merlin-only PR submission by default."
---

## Decisions

- Centralized PR authority in `merlin` to remove multi-agent PR drift.
- Kept `jarvis` as orchestrator and changed worker completion flow to `local CI -> push -> handoff`.
- Enforced Merlin-only PR submission in `scripts/gitea_pr_automerge.py` with explicit human override flag.
- Added a deterministic Merlin PR sweep command covering discovery, CI triage, consolidation, and safe pruning.

## Learnings

- Existing merge-reconcile tooling already covers much of this policy; governance drift came from authority ambiguity, not missing primitives.
- Script-level guardrails are necessary because docs-only governance is too easy to bypass during fast autonomous loops.

## Scope Ownership

- `AGENTS.md`: CH-GIT-MERLIN-PR-001/dev/2026-02-16T00:00:00Z
- `.opencode/agent/Jarvis.md`: CH-GIT-MERLIN-PR-001/dev/2026-02-16T00:00:00Z
- `.opencode/agent/Merlin.md`: CH-GIT-MERLIN-PR-001/dev/2026-02-16T00:00:00Z
- `.opencode/command/chise-pr-automerge.md`: CH-GIT-MERLIN-PR-001/dev/2026-02-16T00:00:00Z
- `scripts/gitea_pr_automerge.py`: CH-GIT-MERLIN-PR-001/dev/2026-02-16T00:00:00Z

## Incidents

- None.

## Evidence

- Redis iterlog initialized at `bmad:chiseai:iterlog:story:CH-GIT-MERLIN-PR-001` with TTL 432000.
- Qdrant collection checked at `http://host.docker.internal:6334/collections/ChiseAI`.
- Qdrant context scanned via `POST /collections/ChiseAI/points/scroll`.
- `pytest -q tests/test_gitea_pr_automerge.py` passed (`46 passed`).
- `python3 scripts/validate_iterloop_compliance.py --story-id=CH-GIT-MERLIN-PR-001` passed.
- `python3 scripts/validate_status_sync.py` passed.
