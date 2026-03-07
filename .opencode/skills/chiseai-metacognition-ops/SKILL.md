---
name: chiseai-metacognition-ops
description: Enforce metacognitive prediction/outcome/calibration loops for Aria/Jarvis execution quality and safer autonomy.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-07"
---

# chiseai-metacognition-ops

## Goal

Make decision quality measurable and improvable by default via three loops:
- prediction (before execution)
- outcome capture (after execution)
- calibration (confidence vs reality over time)

## When To Use

- Story kickoff and story close (all story types).
- Aria/Jarvis orchestration where `INSIGHT_PACKET` and `ARIA_DECISION` are used.
- Incident-heavy or regression-prone workstreams.
- Any work that affects risk invariants, CI reliability, or delivery throughput.

## When Not To Use

- One-off exploratory notes that are not tied to a story.
- Work outside ChiseAI repo processes.

## Required Commands

1. Start:
   - `.opencode/command/chise-metacog-start.md`
2. Close:
   - `.opencode/command/chise-metacog-close.md`
3. Weekly trend review:
   - `.opencode/command/chise-metacog-weekly.md`

## Redis Memory Contract

Use these keys in DB 0:
- `bmad:chiseai:metacog:prediction:story:<story_id>`
- `bmad:chiseai:metacog:outcome:story:<story_id>`
- `bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<yyyy-Www>`
- `bmad:chiseai:metacog:prevention_rules`

TTL defaults:
- Story prediction/outcome: 5 days (match iterlog lifecycle).
- Weekly calibration: 30 days.
- Prevention rules: 90 days.

## Qdrant Promotion Contract

Promote durable learnings to collection `ChiseAI_metacognition` with payload:
- `project`: `crypto-chise-bmad`
- `story_id`
- `agent`
- `decision_type`
- `predicted_risk`
- `actual_outcome`
- `confidence`
- `calibration_delta`
- `prevention_rule`
- `scope_context`

If Qdrant is unavailable, use `docs/tempmemories/` fallback with:
- `needs_manual_qdrant_import: true`

## Required Iterlog Sections

For completed stories, include:
- `## Metacognitive Predictions`
- `## Metacognitive Outcomes`
- `## Metacognitive Calibration`

## Quantification Baseline

Track weekly deltas on:
- repeat incident fingerprint rate
- reopened fix rate
- cycle time median
- confidence calibration error
- prevention rule hit rate

Use a 4-week rolling baseline; tune autonomy thresholds only when trend is stable for >=2 weeks.

## Related Skills

- `chiseai-memory-ops`
- `chiseai-validation`
- `chiseai-incident-response`
- `chiseai-worker-contracts`

