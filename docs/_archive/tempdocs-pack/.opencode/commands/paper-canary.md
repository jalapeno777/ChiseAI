---
description: Prepare and validate a paper canary deployment plan for a candidate strategy.
agent: plan
subtask: true
---
Prepare a paper canary plan for the specified candidate strategy version.

Rules:
- Follow the `paper-trading-canary` and `strategy-cicd-gates` skills.
- Enforce trade budgeter (20 tokens/day).
- Do not deploy to live.

Input:
- $ARGUMENTS: candidate strategy version id

Output:
- Canary scope (symbols, notional limits, duration)
- Metrics to monitor (profit after costs, turnover avg/p95/max, execution stats)
- Pass/fail criteria and rollback plan
