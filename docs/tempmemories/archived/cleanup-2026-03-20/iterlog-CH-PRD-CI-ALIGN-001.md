---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-PRD-CI-ALIGN-001
story_title: "Align PRD+Status with live-trading roadmap; make Woodpecker CI real; prove PR->CI->merge"
phase: implementation
status: completed
started_at: "2026-02-08T19:23:26Z"
completed_at: "2026-02-08T19:50:49Z"
mem_scan:
  - AGENTS.md
  - docs/prd.md
  - docs/bmm-workflow-status.yaml
  - docs/validation/validation-registry.yaml
  - .opencode/agent/*
  - .woodpecker.yml
  - pyproject.toml
acceptance_criteria:
  - "AC1: docs/prd.md updated to reflect Binance market-data + Bybit paper + Bitget live phased execution (backtest+paper+live run in parallel), perps-only, leverage<=3x, 1% risk per trade, kill-switch rules, no jurisdiction scope."
  - "AC2: docs/bmm-workflow-status.yaml + docs/validation/validation-registry.yaml updated to match PRD (execution phases, Grafana-first observability, new/updated epics/stories)."
  - "AC3: Replace placeholder pyproject/CI with real Python quality gates (black+ruff+mypy+pytest+coverage) and status/iterloop validators."
  - "AC4: Add scripts/local-ci-checks.sh and scripts/validate_iterloop_compliance.py (CI-checkable via docs/tempmemories fallback)."
  - "AC5: Add minimal src/ + tests so CI is meaningful and green."
  - "AC6: Push branch to Gitea, create PR, run Woodpecker CI, auto-merge to main on green (via configured auto-merge or merge-bot script), then prune merged branches."
---

## Decisions
- Updated `docs/prd.md` scope from recommendation-only to phased perps execution (continuous backtest -> Bybit demo paper -> Bitget live) with shadow-modes kept running in parallel.
- Set Grafana as primary ops/debug UI; Streamlit optional for research/explainability only.
- Made CI gates real (black/ruff/mypy/pytest/coverage) and added CI-checkable iterloop compliance validator via `docs/tempmemories/`.

## Learnings
- This environment has `python3` but not `python`; agent commands/docs should use `python3`.
- Local pip installs are blocked by PEP 668; use a venv for local runs (Woodpecker CI is unaffected).
- Gitea swagger is available at `/swagger.v1.json`; PR merge API supports `merge_when_checks_succeed`.

## Scope Ownership

- TBD

## Incidents

- TBD


## Evidence
- `docs/prd.md` updated (v1.1.0) with phased execution + risk invariants.
- `docs/bmm-workflow-status.yaml` and `docs/validation/validation-registry.yaml` updated with new epics/stories and validation gates.
- `.woodpecker.yml`, `pyproject.toml`, and new scripts make CI blocking and green locally in a venv.
