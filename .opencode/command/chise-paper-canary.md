---
name: "chise-paper-canary"
description: "ChiseAI: prepare and validate a paper canary deployment plan for a candidate strategy."
disable-model-invocation: true
---
Prepare a paper canary plan for the specified candidate strategy version.

Rules:
- Follow the `chiseai-paper-trading-canary` and `chiseai-strategy-cicd-gates` skills.
- Enforce trade budgeter (20 tokens/day).
- Do not deploy to live.

Input:
- $ARGUMENTS: candidate strategy version id

Output:
- Canary scope (symbols, notional limits, duration)
- Metrics to monitor (profit after costs, turnover avg/p95/max, execution stats)
- Pass/fail criteria and rollback plan
