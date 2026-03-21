---
project: ChiseAI
scope: ci-workflow
type: decision
story_id: ST-CI-008
phase: implementation
tags: [swarm, worktree, ci, woodpecker, git]
needs_manual_qdrant_import: true
---

## Durable Decisions

1. Enforce per-story isolated worktree sessions via `scripts/swarm/session.py` and require explicit `BRANCH` + `WORKTREE_PATH` in worker contracts.
2. Add `swarm-context` as first CI gate (`scripts/ci/validate_swarm_context.py`) and include it in `ci-gate` status aggregation.
3. Treat `docs/bmm-workflow-status.yaml` and `docs/validation/validation-registry.yaml` as single-writer global-lock files; non-main edits require explicit lock signal.

## Prevention Rules

- Never infer branch from `HEAD`/current branch for PR/automerge flows; always pass explicit branch value.
- Run session verify before git actions in executor agents (`dev`, `quickdev`, `senior-dev`, `merlin`).
