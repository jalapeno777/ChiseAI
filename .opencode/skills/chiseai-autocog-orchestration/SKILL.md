---
name: chiseai-autocog-orchestration
description: Autonomous cognition orchestration for Aria: run backend evaluations, review severity, auto-implement low/medium items, escalate high/critical recommendations to Craig.
metadata:
  version: "1.0"
  opencode_min_version: "1.2.0"
  author: "ChiseAI Team"
  last_updated: "2026-03-13"
---

# chiseai-autocog-orchestration

## Goal

Operationalize Aria as the autonomous cognition orchestrator on top of backend jobs:
- run/inspect autonomous cognition cycle artifacts and logs,
- perform secondary Aria-level evaluation and synthesis,
- auto-implement low/medium priority improvements,
- escalate high/critical findings to Craig with concrete options and tradeoffs.

## When To Use

- Daily/weekly autonomous cognition operations.
- After backend `autocog` jobs complete.
- When evaluating quality/safety/risk improvements for reasoning, memory, neuro-symbolic, metacognition, and governance.

## Priority Policy (Required)

- `low|medium`: Aria may auto-implement within project scope and safety guardrails.
- `high|critical`: Aria must not auto-implement silently. Aria produces:
  - issue summary,
  - evidence,
  - recommended fix,
  - risk if deferred,
  - whether explicit Craig approval is required.

## Required Commands

1. Run backend cycle + collect evidence:
- `.opencode/command/chise-autocog-daily-run.md`

2. Aria review/synthesis:
- `.opencode/command/chise-autocog-review.md`

3. Priority action routing:
- `.opencode/command/chise-autocog-action.md`

## Evidence Inputs

Primary artifacts:
- `_bmad-output/autocog/cycles/*.json`
- `docs/governance/self_assessments/*.json`
- `docs/backlog/autocog-phase*.md`

Validation/log inputs:
- latest `pytest` bundle for autonomous cognition modules
- `scripts/ops/run_autonomous_self_assessment.py` output
- `scripts/ops/run_autonomous_full_cycle.py` output

## Output Contract

Aria must produce:
- `AUTOCog_REVIEW_PACKET` with:
  - `run_id`
  - `top_findings[]` (`severity`, `summary`, `evidence`, `recommended_action`)
  - `auto_actions[]` (low/medium only)
  - `escalations[]` (high/critical)
  - `open_risks[]`

## Safety Constraints

- Never auto-change protected risk caps or governance bypasses.
- Never suppress constitution violations.
- Always preserve Craig authority for high/critical changes.

## Related Skills

- `chiseai-metacognition-ops`
- `chiseai-skill-autonomy`
- `chiseai-validation`
- `chiseai-worker-contracts`

