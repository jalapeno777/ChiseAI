---
name: chiseai-workflow-commands
description: Use Opencode BMAD Beta 7 workflow commands for planning, implementation, review, and research to reduce drift and enforce repeatability.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.48"
---

# chiseai-workflow-commands

## Goal

Prefer repeatable workflow execution through `.opencode/command/*` rather than ad-hoc prompting.

## When To Use

- Any BMAD Beta 7 workflow task (PRD, planning, dev-story, code review, research).
- Any time the swarm starts drifting from the repo's process requirements.

## Default Routing

- `aria` delegates workflow execution to `jarvis`.
- `jarvis` delegates executable work to `dev`, `quickdev`, `senior-dev`.
- Non-destructive roles: `research`, `web-research`, `critic`.

## Command Map (Common)

- PRD:
  - `.opencode/command/bmad-bmm-create-prd.md`
  - `.opencode/command/bmad-bmm-edit-prd.md`
  - `.opencode/command/bmad-bmm-validate-prd.md`
- Planning:
  - `.opencode/command/bmad-bmm-create-epics-and-stories.md`
  - `.opencode/command/bmad-bmm-sprint-planning.md`
- Implementation:
  - `.opencode/command/bmad-bmm-dev-story.md`
  - `.opencode/command/bmad-bmm-quick-dev.md`
- Review:
  - `.opencode/command/bmad-bmm-code-review.md`
  - `critic` agent for adversarial checks beyond the workflow output
- Research:
  - `.opencode/command/bmad-bmm-domain-research.md`
  - `.opencode/command/bmad-bmm-technical-research.md`
  - `web-research` agent for up-to-date source gathering

## ChiseAI-Specific Helpers

- Start/close iteration loop:
  - `.opencode/command/chise-iterloop-start.md`
  - `.opencode/command/chise-iterloop-close.md`
- Risk audit:
  - `.opencode/command/chise-risk-audit.md`
- Dashboard smoke:
  - `.opencode/command/chise-dashboard-smoke.md`

