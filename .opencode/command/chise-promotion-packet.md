---
name: "chise-promotion-packet"
description: "ChiseAI: generate a human approval promotion packet for a candidate strategy or brain version."
disable-model-invocation: true
---
Generate a promotion packet using the `chiseai-promotion-packet` skill.

Input:
- $ARGUMENTS should specify:
  - "strategy:<version_id>" OR
  - "brain:<version_id>"

Output:
- A concise packet suitable for a human approval decision:
  - summary, diffs, evidence (paper first), turnover, risks, rollback, monitoring
