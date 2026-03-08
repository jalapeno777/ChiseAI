# ChiseAI Skills Autonomy Control Plane

Status: draft-for-implementation  
Owner: Craig / Aria / Jarvis / Merlin  
Date: 2026-03-08

## 1) Objective

Run skills autonomously inside Opencode agent workflows while keeping delivery fluid.

Hard rule:
- Missing skills must **not** block task execution.
- Missing-skill events are logged as KPI/reflection signals.
- Existing skills are continuously hardened through eval, benchmark, and promotion loops.

## 2) Design Principles

1. Execution continuity over strict completeness.
2. Prefer skills when available, degrade gracefully when absent.
3. Measure capability gaps as data, not failures.
4. Promote only proven skill versions.
5. Roll back automatically on regressions.

## 3) Runtime Architecture

## 3.1 Components

1. Registry
- Source of truth for skill metadata and versions.
- Inputs: `.opencode/skills/*/SKILL.md`, `docs/metrics/skill-task-map.yaml`.

2. Router
- Maps task class -> recommended skills.
- Resolves `available`, `missing`, `fallback_plan`.

3. Executor
- Loads activated skills and runs task normally.
- If a recommended skill is missing, continue with best-effort baseline workflow.

4. Evaluator
- Scores post-task quality against objective metrics.
- Writes skill outcome data to Redis/Qdrant and markdown evidence.

5. Promoter
- Promotes/demotes skill versions based on rolling performance.

## 3.2 Data Flow (Per Story)

1. At iteration start: compute recommended skill coverage.
2. Record coverage snapshot (available/missing) as KPI.
3. Execute task with available skills + fallback.
4. At close: record outcome quality and whether missing skill likely impacted work.
5. Weekly: aggregate trends and decide add/harden/promote/rollback actions.

## 4) Non-Blocking Policy

## 4.1 Missing Skill Behavior

When recommended skill is missing:
- Continue execution.
- Emit `coverage_status: partial` or `none`.
- Persist a gap event with:
  - `story_id`
  - `task_class`
  - `missing_skills`
  - `fallback_used`
  - `impact_estimate`

## 4.2 KPI Escalation Thresholds

Do not gate execution. Escalate planning priority only if repeated:
- `missing_skill_rate_by_task_class >= 0.35` over 2 weeks, or
- same missing skill appears in `>= 5` stories in 14 days.

Escalation action:
- create backlog item to add that skill.
- enqueue candidate in `bmad:chiseai:skills:backlog:candidates` for planning ingestion.

## 5) Storage Contract

## 5.1 Redis (DB 0)

- `bmad:chiseai:skills:coverage:story:<story_id>`
- `bmad:chiseai:skills:gaps:task_class:<task_class>:weekly:<yyyy-Www>`
- `bmad:chiseai:skills:effectiveness:skill:<skill_name>:weekly:<yyyy-Www>`
- `bmad:chiseai:skills:promotions`

TTL:
- story coverage: 30 days
- weekly aggregates: 90 days
- promotions: 180 days

## 5.2 Qdrant

Collection:
- `ChiseAI_skills_ops`

Payload:
- `story_id`, `task_class`, `skill_name`, `skill_version`
- `coverage_status`, `fallback_used`, `quality_score`
- `cycle_time_minutes`, `rework_flag`, `regression_flag`
- `promotion_decision`, `evidence_ref`

Fallback when unavailable:
- `docs/tempmemories/` markdown artifact with `needs_manual_qdrant_import: true`

## 6) Effectiveness Testing Framework

## 6.1 Offline Bench

For each hardened skill:
1. Run baseline (no skill) on fixed test cases.
2. Run candidate skill on same cases.
3. Compare:
- pass rate
- defect rate
- median cycle time
- reviewer rejection rate

Promotion requires sustained improvement (default):
- +10% pass rate OR
- -20% defect/rework rate
- without worsening cycle time >10%

## 6.2 Shadow Mode (Live)

- Run old and candidate decision paths in parallel.
- Execute only incumbent output.
- Score both; no production risk.

## 6.3 Canary Mode

Traffic ramp by task class:
- 5% -> 25% -> 50% -> 100%

Auto-rollback triggers:
- regression spike > threshold
- rework increase > threshold
- repeated severe misses

## 6.4 Weekly Review Output

`chise-skill-weekly` emits:
- missing-skill leaderboard
- skill effectiveness leaderboard
- promotion/rollback recommendations
- top 3 new-skill candidates based on repeated gaps

## 7) Command Set

- `.opencode/command/chise-skill-autonomy-tick.md`
- `.opencode/command/chise-skill-backlog-ingest.md`
- `.opencode/command/chise-skill-eval.md`
- `.opencode/command/chise-skill-promote.md`
- `.opencode/command/chise-skill-rollback.md`
- `.opencode/command/chise-skill-weekly.md`

These commands are autonomous-friendly and non-blocking for missing skills.
Prefer `chise-skill-autonomy-tick` as the single orchestration entry point.

## 8) Integration Points

1. `chise-iterloop-start`
- run skill coverage snapshot (non-blocking)

2. `chise-iterloop-close`
- run skill effectiveness capture

3. `chise-precommit-gates`
- run skill KPI validator as warning-only gate

4. `chise-metacog-weekly`
- include skill coverage/effectiveness trends in weekly autonomy decision

## 9) Guardrails

- Missing skills never stop execution.
- Quality failures can still block (tests, CI, critical safety checks).
- Promotion/rollback decisions must include evidence links.

## 10) Rollout Plan

Phase A (now):
- add commands, validator, task map, and weekly KPI reporting.

Phase B (1-2 weeks):
- start shadow evaluations for top 3 skills.

Phase C (2-4 weeks):
- enable canary and automated promotion/rollback recommendations.

## 11) Performance Safeguards

- Runtime budget per tick (default 20s) to prevent workflow slowdown.
- Command timeout cap (default 12s) for child invocations.
- Sampling support for start/close instrumentation under load.
- Bounded weekly scan window (lookback + max artifacts).
- Degrade gracefully to warnings when telemetry dependencies are unavailable.
- Lock-based single-run protection to avoid duplicate concurrent ticks.

## 12) Automation Cadence

- Host cron wrapper: `scripts/cron/weekly_skill_autonomy.sh`
- Cron config template: `infrastructure/cron/chiseai-weekly-skill-autonomy`
- CI cron backup: `.woodpecker/cron-eval.yaml` step `skill-autonomy-weekly`
