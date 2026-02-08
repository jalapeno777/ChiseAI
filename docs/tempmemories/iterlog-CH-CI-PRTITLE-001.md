---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-CI-PRTITLE-001
story_title: "Add Woodpecker gate: PR builds require PR title with story ID"
phase: implementation
status: in_progress
started_at: "$(date -u +%FT%TZ)"
mem_scan:
  - AGENTS.md
  - .woodpecker.yml
  - scripts/*
  - .opencode/command/chise-pr-automerge.md
acceptance_criteria:
  - "AC1: Add CI check that fails on pull_request builds when PR title missing or lacks story id."
  - "AC2: Wire check into .woodpecker.yml and ensure CI still passes."
  - "AC3: Merge to main via standard PR auto-merge with story id CH-CI-PRTITLE-001; prune branches."
---

## Decisions
- TBD

## Learnings
- TBD

## Evidence
- TBD
