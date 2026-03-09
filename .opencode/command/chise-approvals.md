---
name: "chise-approvals"
description: "ChiseAI: list pending cadence approvals and approve/revoke guarded actions."
disable-model-invocation: true
---

List pending approvals:

```bash
python3 scripts/ops/manage_approvals.py --list-pending
```

Approve guarded Phase 3 strategy autopilot:

```bash
python3 scripts/ops/manage_approvals.py --approve strategy-autopilot
```

Revoke approval:

```bash
python3 scripts/ops/manage_approvals.py --revoke strategy-autopilot
```
