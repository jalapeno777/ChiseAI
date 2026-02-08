---
description: Generate a human approval promotion packet for a candidate strategy or brain version.
agent: plan
subtask: true
---
Generate a promotion packet using the `promotion-packet` skill.

Input:
- $ARGUMENTS should specify:
  - "strategy:<version_id>" OR
  - "brain:<version_id>"

Output:
- A concise packet suitable for a human approval decision:
  - summary, diffs, evidence (paper first), turnover, risks, rollback, monitoring
