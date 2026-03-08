---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: ST-CI-HEALTH-20260215
story_title: "Repair Woodpecker CI health, validate pipeline execution, and add token-expiry hardening guard"
phase: implementation
status: in_progress
started_at: "2026-02-15T00:34:03Z"
acceptance_criteria:
  - "AC1: Woodpecker forge auth works again and new pipelines no longer fail with 'could not load config from forge'."
  - "AC2: At least one post-fix pipeline on main executes workflow steps (not pre-step error short-circuit)."
  - "AC3: Repo includes an automated token health check that detects JWT exp drift and near-expiry risk for Woodpecker forge users."
mem_scan:
  - AGENTS.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/workflow.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/steps/step-01-init.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/steps/step-02-mem-scan.md
  - .woodpecker.yml
  - scripts/ci/woodpecker_triage.py
  - scripts/validate_iterloop_compliance.py
notes:
  - "Redis/Qdrant MCP tools unavailable in this runtime. Using docs/tempmemories fallback per AGENTS.md and validate_iterloop_compliance policy."
---

## Decisions

- Repaired Woodpecker forge auth by refreshing Gitea OAuth token and updating `woodpecker.users` (`token`, `secret`, `expiry`) for `craig`.
- Added `scripts/ci/check_woodpecker_forge_token_health.py` as an automated drift/expiry guard for forge token health.
- Updated CI docs/runbook with deterministic diagnosis and recovery procedure for pre-step forge/config failures.
- Fixed Bandit `B110` in `src/execution/live_gating/grafana_exporter.py` to remove `except Exception: pass`.

## Learnings

- Woodpecker DB `users.expiry` can drift from JWT `exp`; if drift is wrong/high, refresh is skipped and forge calls fail with opaque errors.
- The Gitea API error `user does not exist [uid: 0, name: ]` can indicate expired OAuth access token in Woodpecker context.
- Pipeline state transition from immediate `error` to real step execution confirms forge auth remediation before step-level CI analysis.

## Scope Ownership

- scripts:ci: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- woodpecker.yml: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- docs:tempmemories: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- TBD

## Incidents

- symptom: Pipeline `#480` failed after forge fix even though pre-step errors were gone.
- root_cause: `ci-gate` observed `security-scan.status=1` caused by Bandit issue `B110` at `src/execution/live_gating/grafana_exporter.py:413`.
- fix: Replace silent `except Exception: pass` with warning log and re-run Bandit scan.
- prevention_rule: Keep Bandit `src` scan in CI gate and run `bandit -q -r src -s B311,B107` locally before pushing infra/CI remediations.

## Evidence

- DB evidence: prior failures in `pipelines.errors` were `could not load config from forge: %!w(<nil>)`; post-fix pipelines (`#480`, `#481`) progressed into step execution.
- OAuth repair validation: `curl -H "Authorization: token <new_token>" http://host.docker.internal:3000/api/v1/user` returned `200` with login `craig`.
- Health guard validation: `python3 scripts/ci/check_woodpecker_forge_token_health.py --dsn ... --require-user craig` returned `OK`.
- Security scan validation: `bandit -q -r src -s B311,B107` returns exit code `0` after `grafana_exporter.py` fix.
