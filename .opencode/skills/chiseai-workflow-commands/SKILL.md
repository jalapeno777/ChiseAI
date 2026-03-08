---
name: chiseai-workflow-commands
description: Use Opencode BMAD Beta 7 workflow commands for planning, implementation, review, and research to reduce drift and enforce repeatability.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-workflow-commands

## Goal

Prefer repeatable workflow execution through `.opencode/command/*` rather than ad-hoc prompting.

## When To Use

- Any BMAD Beta 7 workflow task (PRD, planning, dev-story, code review, research).
- Any time the swarm starts drifting from the repo's process requirements.
- Standardizing execution patterns.
- Onboarding new agents to workflows.

## When Not To Use

- Novel situations without existing commands.
- Emergency procedures (use specific emergency commands).
- One-off investigations (document findings instead).
- External tool operations (use native tools).

## Default Routing

- `aria` delegates workflow execution to `jarvis`.
- `jarvis` delegates executable work to `dev`, `quickdev`, `senior-dev`.
- Non-destructive roles: `research`, `web-research`, `critic`.
- For all Craig-facing sessions, include `THINKING_PARTNER_STATUS` and `Thinking Partner Proof` in summaries by default.

## Command Map (Common)

### PRD
- `.opencode/command/bmad-bmm-create-prd.md`
- `.opencode/command/bmad-bmm-edit-prd.md`
- `.opencode/command/bmad-bmm-validate-prd.md`

### Planning
- `.opencode/command/bmad-bmm-create-epics-and-stories.md`
- `.opencode/command/bmad-bmm-sprint-planning.md`

### Implementation
- `.opencode/command/bmad-bmm-dev-story.md`
- `.opencode/command/bmad-bmm-quick-dev.md`

### Review
- `.opencode/command/bmad-bmm-code-review.md`
- `critic` agent for adversarial checks beyond the workflow output

### Research
- `.opencode/command/bmad-bmm-domain-research.md`
- `.opencode/command/bmad-bmm-technical-research.md`
- `web-research` agent for up-to-date source gathering

## ChiseAI-Specific Helpers

### Start/close iteration loop:
- `.opencode/command/chise-iterloop-start.md`
- `.opencode/command/chise-iterloop-close.md`

### Metacognition loop:
- `.opencode/command/chise-metacog-start.md`
- `.opencode/command/chise-metacog-close.md`
- `.opencode/command/chise-metacog-weekly.md`

### Skills autonomy loop:
- `.opencode/command/chise-skill-autonomy-tick.md`
- `.opencode/command/chise-skill-backlog-ingest.md`
- `.opencode/command/chise-skill-eval.md`
- `.opencode/command/chise-skill-promote.md`
- `.opencode/command/chise-skill-rollback.md`
- `.opencode/command/chise-skill-weekly.md`

### PR review bot setup + review:
- `.opencode/command/chise-gitea-review-bot-setup.md`
- `.opencode/command/chise-pr-review-bot.md`

### Parallel safety (ownership + incidents):
- `.opencode/command/chise-claim-ownership.md`
- `.opencode/command/chise-check-ownership.md`
- `.opencode/command/chise-append-incident.md`

### Risk audit:
- `.opencode/command/chise-risk-audit.md`

### Dashboard smoke:
- `.opencode/command/chise-dashboard-smoke.md`

## Parallel Work Policy (ChiseAI)

When running parallel executors on a story/sprint:
- Claim ownership BEFORE edits using `.opencode/command/chise-claim-ownership.md`.
- Executors check ownership at start using `.opencode/command/chise-check-ownership.md`.
- On conflict/regression, append incident using `.opencode/command/chise-append-incident.md` and STOP until `jarvis` re-plans.

## Exit Conditions

- Appropriate command identified for task type.
- Command executed with documented results.
- Workflow drift detected and corrected.
- Repeatable pattern established.

## Troubleshooting/Safety

- **Command not found**: Check spelling; verify command exists in `.opencode/command/`.
- **Workflow drift**: Reference this skill; redirect to appropriate command.
- **Ad-hoc execution**: Document pattern; consider creating new command if reusable.
- **Parallel conflict**: Use ownership commands; do not proceed without resolution.

## Related Skills

- `chiseai-parallel-safety` - Ownership for parallel execution
- `chiseai-validation` - Validates workflow compliance
- `chiseai-prd-quality` - PRD-specific quality gates

## Related Commands

See Command Map sections above for full list.
