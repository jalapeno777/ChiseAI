---
name: "chise-reconcile-intake"
description: "ChiseAI: inspect or drain merge/reconcile incidents for escalation and cleanup handoff."
disable-model-invocation: true
---

Use this command to consume structured incidents emitted by `scripts/ops/merge_reconciler.py`.

Read incidents:

```bash
python3 scripts/ops/merge_reconciler.py intake-incidents --limit 100
```

Drain incidents after routing and logging:

```bash
python3 scripts/ops/merge_reconciler.py intake-incidents --limit 100 --drain
```

Escalation policy:
1. `recommended_agent=jarvis`: enqueue into Jarvis cleanup batch.
2. `recommended_agent=merlin`: run `.opencode/command/chise-ci-root-cause.md` and assign Merlin with evidence.
