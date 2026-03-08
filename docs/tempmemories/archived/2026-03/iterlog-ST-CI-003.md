---
story_id: ST-CI-003
story_title: Branch Hygiene Automation - Prune + Prevention (CI diagnostics + log visibility)
epic_id: EP-CI-001
sprint_id: p0-1
phase: implementation
status: in_progress
started_at: "2026-02-11T00:00:00Z"
acceptance_criteria:
  - "AC1: CI/local runs do not require Streamlit; Streamlit dashboard tests are opt-in via CHISE_ENABLE_STREAMLIT_TESTS=1."
  - "AC2: Importing the dashboard package does not hard-require Streamlit (no eager import chain)."
  - "AC3: Woodpecker posts or updates a single PR comment containing a concise failure summary and repro steps when CI fails."
  - "AC4: CI log capture covers lint and pytest paths (at least tails are available in the failure summary)."
  - "AC5: No CI gates are removed; black/ruff/mypy/status-sync/iterloop/pytest remain enforced."
---

# Iteration Log: ST-CI-003

## Key Decisions

- Use PR comments (deduped by marker) as the primary swarm-visible failure surface for Woodpecker runs.
- Keep Streamlit tests in-repo but skip them by default unless explicitly enabled.

## Learnings

- TBD

## Scope Ownership

- `ci:woodpecker` -> ST-CI-003 / codex / 2026-02-11
- `tests:test_dashboard` -> ST-CI-003 / codex / 2026-02-11
- `src:dashboard` -> ST-CI-003 / codex / 2026-02-11

## Incidents

- 2026-02-11: Local test runs imported a sibling repo's `streamlit` module due to PYTHONPATH contamination; fix by pinning PYTHONPATH in `scripts/local-ci-checks.sh`.

