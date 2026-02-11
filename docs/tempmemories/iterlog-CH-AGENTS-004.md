---
story_id: CH-AGENTS-004
story_title: Add Merlin debugger subagent + swarm CI triage workflow
phase: implementation
status: in_progress
started_at: "2026-02-10T22:44:51-05:00"
acceptance_criteria:
  - "AC1: Add scripts/ci/swarm_triage.sh to replay CI wrappers and summarize failures."
  - "AC2: Add .opencode/agent/Merlin.md with OpenCode 1.1.48+ compatible syntax and Codex model matching Aria."
  - "AC3: Update Aria/Jarvis/AGENTS instructions for Merlin ownership of CI debugging and 5-attempt escalation."
  - "AC4: Validate with iterloop + status-sync checks and script smoke test."
---

# Iteration Log: CH-AGENTS-004

## Key Decisions

- Merlin is the dedicated debugger for CI and systemic blockers.
- `swarm_triage.sh` should replay Woodpecker wrapper behavior, not invent a parallel workflow.

## Learnings

- Local environments may block system pip installs (PEP 668), so triage tooling must auto-detect venvs.

## Scope Ownership

- `.opencode:agent` -> CH-AGENTS-004 / codex / 2026-02-10
- `scripts:ci` -> CH-AGENTS-004 / codex / 2026-02-10
- `AGENTS.md` -> CH-AGENTS-004 / codex / 2026-02-10

## Incidents

- 2026-02-10: Initial swarm_triage run failed due system Python package install restrictions; resolved by venv auto-detection and install policy auto mode.
