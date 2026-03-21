# Swarm Policy Baseline Snapshot - 2026-03-17

## Purpose

Baseline snapshot used for Unified Cleanup implementation and rollback traceability.

## Prior Drift Categories (captured before alignment)

- Legacy blocker escalation references used a 5-attempt rule in orchestrator paths.
- Routing defaults still referenced `quickdev-fast` as a primary 1SP route.
- Critic remediation loop was not explicitly capped at two rounds.
- Plan approval and replan gates were not consistently explicit across Aria/Jarvis runtime profiles.
- Worker completion evidence contract was inconsistent across executor profiles.
- Agent selection matrix in `.opencode/agent/README.md` had model/routing drift versus actual files.

## Baseline Scope

- `AGENTS.md`
- `.opencode/agent/Aria.md`
- `.opencode/agent/AriaRuntime.md`
- `.opencode/agent/Jarvis.md`
- `.opencode/agent/JarvisRuntime.md`
- `.opencode/agent/Quickdev.md`
- `.opencode/agent/Dev.md`
- `.opencode/agent/SeniorDev.md`
- `.opencode/agent/Merlin.md`
- `.opencode/agent/Critic.md`
- `.opencode/agent/QuickdevFast.md`
- `.opencode/agent/Juniordev.md`
- `.opencode/agent/README.md`

## Rollback Note

Use git history from this date to restore pre-cleanup policy text if cutover regression is detected.
