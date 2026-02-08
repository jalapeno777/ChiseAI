---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-AUTONOMY-001
story_title: "Tune Aria/Jarvis for uninterrupted autonomy; add security_scan CI gate + tracking"
phase: implementation
status: in_progress
started_at: "$(date -u +%FT%TZ)"
mem_scan:
  - AGENTS.md
  - .opencode/agent/Aria.md
  - .opencode/agent/Jarvis.md
  - .woodpecker.yml
  - docs/bmm-workflow-status.yaml
  - docs/validation/validation-registry.yaml
  - docs/ci-cd-gitea-woodpecker.md
acceptance_criteria:
  - "AC1: Aria and Jarvis agent instructions updated so in-scope decisions proceed autonomously with logged assumptions; human ping only for out-of-scope or safety-critical ambiguity."
  - "AC2: Add a deterministic security scan step to Woodpecker (bandit on src) and document it."
  - "AC3: Add tracking story+validation entry for security_scan gate in status+validation files."
  - "AC4: Changes merged via PR auto-merge with story-id CH-AUTONOMY-001; branch pruned; main clean."
---

## Decisions
- TBD

## Learnings
- TBD

## Evidence
- TBD
