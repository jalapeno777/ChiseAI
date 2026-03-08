---
name: chiseai-skill-autonomy
description: Autonomous skill routing/evaluation/promotion operations with non-blocking fallback when skills are missing.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-08"
---

# chiseai-skill-autonomy

## Goal

Operationalize skills as an autonomous subsystem:
- auto-detect recommended skills
- continue execution when skills are missing
- log missing coverage as KPI for reflection and roadmap
- harden existing skills via eval and benchmark loops

## When To Use

- Any story execution with agent delegation.
- Any task where skill coverage should be measured.
- Weekly autonomy review and promotion/rollback decisions.

## When Not To Use

- One-off ad-hoc tasks with no repeat potential.
- Emergency incident response where speed overrides instrumentation.

## Required Commands

0. Unified control-plane tick:
- `.opencode/command/chise-skill-autonomy-tick.md`

1. Coverage/eval:
- `.opencode/command/chise-skill-eval.md`

2. Promotion decision:
- `.opencode/command/chise-skill-promote.md`

3. Rollback decision:
- `.opencode/command/chise-skill-rollback.md`

4. Weekly summary:
- `.opencode/command/chise-skill-weekly.md`

5. Canonical backlog ingestion:
- `.opencode/command/chise-skill-backlog-ingest.md`

## Non-Blocking Rule

If recommended skills are missing:
- proceed with execution
- record KPI gap event
- do not fail task solely due to missing skill coverage

## KPI Fields

Minimum fields to capture:
- `story_id`
- `task_class`
- `recommended_skills`
- `available_skills`
- `missing_skills`
- `coverage_status` (`full|partial|none`)
- `fallback_used`
- `impact_estimate` (`none|low|medium|high`)

## Task-Class Mapping

Use:
- `docs/metrics/skill-task-map.yaml`

If task class is unknown:
- set `task_class: unclassified`
- continue execution
- log as KPI for taxonomy refinement

## Storage

Redis keys (DB 0):
- `bmad:chiseai:skills:coverage:story:<story_id>`
- `bmad:chiseai:skills:gaps:task_class:<task_class>:weekly:<yyyy-Www>`
- `bmad:chiseai:skills:effectiveness:skill:<skill_name>:weekly:<yyyy-Www>`

Fallback:
- write markdown artifact under `docs/tempmemories/`.

## Runtime Safeguards

Config:
- `config/skill_autonomy.yaml`

Controls:
- runtime budget
- command timeout
- sampling rate
- concurrent tick lock

Automation outputs:
- weekly KPI artifacts in `docs/tempmemories/`
- backlog candidates in `docs/backlog/`
- Redis backlog queue: `bmad:chiseai:skills:backlog:candidates`

## Effectiveness Criteria (Default)

A skill version is promotable only if it improves at least one quality metric without harmful regressions:
- quality/pass rate improves >= 10%, or
- rework/regression rate decreases >= 20%, and
- cycle time does not degrade > 10%

## Related Docs

- `docs/governance/skills-autonomy-control-plane.md`
- `docs/governance/metacognition-integration-blueprint.md`
