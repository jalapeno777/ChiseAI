---
type: summary
story_id: ST-123
story_title: "Full Pilot Autonomy Setup, Follow-up, and Operating Procedures"
created: '2026-03-09T19:20:00Z'
phase: implementation
status: completed
started_at: '2026-03-09T14:00:00Z'
completed_at: '2026-03-09T19:20:00Z'
legacy_exempt: false
compliance_mode: strict_forward
---

## Summary

Implemented and operationalized Full Pilot phases 0-4:
- Phase 0: governance hardening (secrets/env, host normalization, legacy exemptions).
- Phase 1: unified autonomy cadence controller + registry + cron automation + Discord notifications.
- Phase 2: reflection/metacog/evolution wiring with event bus and generated artifacts.
- Phase 3: guarded autopilot path with explicit approval gates.
- Phase 4: scorecard + go/no-go packet generation and daily executive summary posting.

## Scope Ownership

- owner: codex
- workstream: governance-autonomy-full-pilot
- overlap_risk: low
- external_dependencies:
  - Discord webhook availability
  - Redis availability for runtime state and event stream

## Incidents

- `INC-20260309-AUTONOMY-001`: Discord webhook path intermittently returned HTTP 403 in this environment.
  - root cause: webhook requests without explicit `User-Agent` in some code paths.
  - fix: set explicit User-Agent in webhook HTTP requests.
  - outcome: successful webhook posts from test utility, cadence alerts, and daily summary poster.

## Structured Issues

issues:
  - issue_type: "runtime_integration"
    root_cause: "New phase runner import path assumed package context when run as script"
    fix_applied: "Added project root to sys.path before importing scripts.ops modules"
    time_lost_minutes: 12
    recurrence_hint: "Always test new scripts via direct python invocation from repo root"
    impact_area: "efficiency"
    resolved: true
  - issue_type: "notification_delivery"
    root_cause: "Discord rejected requests lacking explicit User-Agent header"
    fix_applied: "Added User-Agent headers to webhook POST logic in all relevant scripts"
    time_lost_minutes: 18
    recurrence_hint: "Standardize webhook helper with explicit headers and reuse everywhere"
    impact_area: "reliability"
    resolved: true

## Metacognitive Predictions
- `predicted_outcome`: Full-pilot automation can be made mostly autonomous with guardrails in one implementation cycle.
- `predicted_risks`: approval ambiguity, webhook reliability, cron/env drift, event schema drift.
- `confidence`: 0.78
- `verification_plan`: compile checks + phase runner dry/live + full E2E + Discord live post.
- `expected_metrics`: all E2E checks pass; cadence registry validates; daily summary posts successfully.

## Metacognitive Outcomes
- `actual_outcome`: implemented and validated full pipeline with E2E and live Discord posting.
- `actual_metrics`: full_pilot_e2e=pass, event_schema_validate=pass, summary_post=pass.
- `wins`: approval gating, phase wiring, event schema validation, cron automation.
- `misses`: scorecard initially mixed dry-run/live data in denominator and overstated NO_GO severity.
- `new_prevention_rules`: include metric-definition tests for scorecard calculations and keep dry/live metrics explicit.

## Metacognitive Calibration
- `predicted_confidence`: 0.78
- `observed_result`: success
- `calibration_delta`: 0.12
- `confidence_adjustment_recommendation`: keep medium-high confidence for similar infra refactors, but add early metric sanity checks.

## Thinking Partner Status
- tp_mode: ACTIVE
- tp_session_id: TPS-20260309-FULL-PILOT
- scope: full-pilot-autonomy-ops
- assumptions_open: 0
- risk_items_open: 1
- last_insight_packet_id: IP-20260309-FULL-PILOT-OPS
- last_aria_decision_id: AD-20260309-FULL-PILOT-OPS

## Insights Sent To Aria
INSIGHT_PACKET
- insight_packet_id: IP-20260309-FULL-PILOT-OPS
- story_id: ST-123
- summary: "Full pilot loops are operational; approvals + recovery visibility are now explicit."
- key_points:
  - "Phase 3 remains intentionally guarded until approval flag is set."
  - "Daily summary now includes 7-day operational score and pending approvals."
  - "Recovery signal added via job_recovered alerts and recovered-job counts."

## Aria Decisions
ARIA_DECISION
- aria_decision_id: AD-20260309-FULL-PILOT-OPS
- story_id: ST-123
- decision: APPROVE
- rationale: "System is operational with guardrails; continue autonomous cadence with daily oversight."
- risk_class: medium
- followups:
  - "Monitor recovered vs unresolved failures daily."
  - "Use approval command for strategy-autopilot only when governance-ready."

Thinking Partner Proof: ACTIVE | ST-123 | IP:IP-20260309-FULL-PILOT-OPS | AD:AD-20260309-FULL-PILOT-OPS | Risks:1

## Operating Procedures (Swarm Reference)

1. Autonomous cadence:
   - Cron tick: `scripts/cron/autonomy_cadence_tick.sh` (every minute).
   - Registry source: `config/autonomy_job_registry.yaml`.
   - State/logs:
     - `_bmad-output/autonomy-cadence/state.json`
     - `_bmad-output/autonomy-cadence/runs.jsonl`
     - `_bmad-output/autonomy-cadence/alerts.jsonl`

2. Daily executive summary:
   - Cron: `scripts/cron/full_pilot_daily_summary.sh` (13:00 UTC).
   - Manual run: `python3 scripts/ops/post_daily_full_pilot_summary.py --regenerate`
   - Includes:
     - 7-day operational score
     - 30-day cadence health
     - recovered/unresolved failures (24h)
     - pending approvals
     - go/no-go decision and required actions

3. Approvals:
   - List pending: `python3 scripts/ops/manage_approvals.py --list-pending`
   - Approve: `python3 scripts/ops/manage_approvals.py --approve strategy-autopilot`
   - Revoke: `python3 scripts/ops/manage_approvals.py --revoke strategy-autopilot`
   - Cadence emits `approval_required` alert when a gated job is blocked.

4. How to know fixes are applied:
   - `job_recovered` alerts emitted when failed/timeout job returns to success.
   - Daily summary shows:
     - `Fixes Applied (Recovered Jobs, 24h)`
     - `Unresolved Failed Jobs (24h)`
   - Confirm via runs log transitions in `_bmad-output/autonomy-cadence/runs.jsonl`.

5. E2E validation command:
   - `python3 scripts/e2e/full_pilot_e2e.py`
   - Validates cadence registry, dry-force tick, phase runs, event schema, and artifacts.
