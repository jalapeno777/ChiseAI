---
name: "chise-precommit-gates"
description: "ChiseAI: run local pre-commit gates (CI checks, status sync, iterloop compliance, metacog compliance, insight-governance conformance). Uses best-available commands in this repo."
disable-model-invocation: true
---

Run these gates before PR/merge. If a referenced script is missing, explicitly note it and run the closest available equivalent.


1. Repo sanity
   - `git status -sb`
   - `git branch --show-current`
   - If this is agent-run story work, verify session:
     - `python3 scripts/swarm/session.py verify --story-id=<story_id> --branch=<branch> --worktree-path=<worktree_path> --check-canonical`
   - For merge-to-main actions, enforce authority + lock:
     - `python3 scripts/swarm/session.py verify --story-id=<story_id> --branch=<branch> --worktree-path=<worktree_path> --check-canonical --require-main-merge-authority --acquire-main-merge-lock`

2. Local CI checks (best available)
   - If `scripts/local-ci-checks.sh` exists, run it.
   - Otherwise, run the repo's test/lint entry points that exist (for example `pytest`, `ruff`, `black`) and report what you ran.

3. Status sync (if present)
   - If `scripts/validate_status_sync.py` exists, run: `python3 scripts/validate_status_sync.py`
   - If this change edits `docs/bmm-workflow-status.yaml`, require explicit `docs/validation/validation-registry.yaml` impact review and co-update when status semantics/validation requirements/evidence mappings changed.

4. Iterloop compliance (if present)
   - If `scripts/validate_iterloop_compliance.py` exists, run:
     - `python3 scripts/validate_iterloop_compliance.py --story-id=<story_id>`
   - Forward-strict default:
     - Do **not** pass `--include-legacy` for normal/new story work.
     - Legacy items are controlled via `docs/governance/legacy-exemptions.yaml`.
     - To refresh the baseline manifest deterministically:
       - `python3 scripts/governance/manage_legacy_exemptions.py --bootstrap-all --no-include-existing --generated-from validator_findings_baseline_<YYYY-MM-DD>`

5. Metacognition compliance (REQUIRED for completed stories)
   - **For P0/P1 stories (BLOCKING GATE):**
     - If `scripts/validation/validate_metacog_compliance.py` exists and `<story_id>` is known:
       ```bash
       python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict --require-artifacts
       ```
     - Forward-strict default:
       - Do **not** pass `--include-legacy` for normal/new story work.
     - `--require-artifacts` requires Redis availability and validates:
       - `bmad:chiseai:metacog:prediction:story:<story_id>`
       - `bmad:chiseai:metacog:outcome:story:<story_id>`
     - **Gate FAILS if metacog artifacts are missing:**
       - Missing prediction card (`bmad:chiseai:metacog:prediction:story:<story_id>`)
       - Missing outcome card (`bmad:chiseai:metacog:outcome:story:<story_id>`)
       - Missing calibration section in iterlog
     - **Metacog compliance is always blocking for P0/P1 stories**
   
   - **For P2+ stories (NON-BLOCKING with warning):**
     - If `scripts/validation/validate_metacog_compliance.py` exists and `<story_id>` is known:
       ```bash
       python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict
       ```
     - Warn if artifacts missing but allow proceed
   - **If `<story_id>` is not known:**
     - Run non-blocking scan:
       ```bash
       python3 scripts/validation/validate_metacog_compliance.py --require-for-completed-only
       ```
   
   - **If script is missing and `<story_id>` is known:**
     - Treat as blocking gate failure for P0/P1
     - Warn and continue for P2+

6. Insight-governance conformance (if present)
   - If `scripts/validation/validate_insight_governance.py` exists, run:
     - `python3 scripts/validation/validate_insight_governance.py --story-id=<story_id> --strict --tp-session-artifact-mode=warn --tp-session-self-heal`
   - Forward-strict default:
     - Do **not** pass `--include-legacy` for normal/new story work.
   - Phased enforcement policy (default autonomous mode):
     - Week 1: `--tp-session-artifact-mode=warn` (non-blocking warning + self-heal).
     - Week 2+: use `--tp-session-artifact-mode=strict` only for `P0/P1` and completed stories.
     - Keep `P2+` in-progress stories on `warn` mode to avoid productivity stalls.
   - If `<story_id>` is not known, run a non-blocking scan:
     - `python3 scripts/validation/validate_insight_governance.py --require-for-completed-only`

6.1 Question-routing governance conformance (if present)
   - If `scripts/validation/validate_question_routing_policy.py` exists, run:
     - `python3 scripts/validation/validate_question_routing_policy.py`
   - Policy:
     - BLOCKING for orchestrator/runtime/agent-definition changes
     - Warning-only for unrelated story work

7. Skills autonomy KPI check (WARNING-ONLY)
   - If `scripts/ops/skill_autonomy_tick.py` exists and `<story_id>` is known, run:
     ```bash
     python3 scripts/ops/skill_autonomy_tick.py --mode=start --story-id=<story_id> --task-class=<task_class_or_unclassified>
     ```
   - Purpose:
     - capture missing-skill coverage signals
     - persist KPI/reflection artifact
   - Policy:
     - missing skills are never blocking in this gate
     - script failure should warn, not fail precommit

7.1 Skill stack registry validation (WARNING-ONLY)
   - If `scripts/validation/validate_skill_stack_registry.py` exists, run:
     ```bash
     python3 scripts/validation/validate_skill_stack_registry.py --stack-map-path=docs/metrics/skill-stacks.yaml --skills-dir=.opencode/skills
     ```
   - Policy:
     - structural registry errors: warn in precommit gate output
     - missing skill refs: warning by default; use `--strict-missing-skills` only in hardening sweeps

8. Session close anti-drift (handoff/finish only; not every precommit run)
   - `python3 scripts/swarm/session.py close --worktree-path=<worktree_path> --enforce-merged`
   - If intentionally closing with open PR and branch ahead of main:
     - `python3 scripts/swarm/session.py close --worktree-path=<worktree_path> --enforce-merged --allow-unmerged`

## Priority-Based Gate Summary

| Gate                | P0/P1        | P2+          |
| ------------------- | ------------ | ------------ |
| Metacog compliance  | BLOCKING     | Warning only |
| Insight governance  | BLOCKING     | BLOCKING     |
| Iterloop compliance | BLOCKING     | BLOCKING     |
| Skills autonomy KPI | Warning only | Warning only |
| Local CI checks     | BLOCKING     | BLOCKING     |

