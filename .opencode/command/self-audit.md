---
description: Audit the project for recurring mistakes, bottlenecks, and highest-ROI optimizations
agent: self-evaluator
subtask: true
---
Run a full self-audit of this project.

Inspect, when present:
- project structure and current git state
- `.opencode/` agents, commands, skills, plugins, and config
- recent diffs and recent implementation history
- test, lint, and typecheck signals
- docker/service state and logs when relevant
- telemetry under `.opencode/data/self-audit/`
- recurring permission denials, repeated retries, repeated failures, and common loop patterns

Return:
1. Executive summary
2. Top 5 issues
3. Repeated mistakes and friction patterns
4. Root causes
5. Quick wins under 30 minutes
6. Structural improvements
7. Next 3 implementation tickets with acceptance criteria

Important:
- Be read-only
- Prefer hard evidence
- Separate facts from inference
- Prioritize fixes by impact and likelihood
