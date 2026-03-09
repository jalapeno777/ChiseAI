---
name: "chise-full-pilot-e2e"
description: "ChiseAI: run full pilot E2E validation (cadence registry/controller + phase2/3/4 loops + event/scorecard artifacts)."
disable-model-invocation: true
---

Run end-to-end validation:

```bash
python3 scripts/e2e/full_pilot_e2e.py
```

Optional:

```bash
python3 scripts/e2e/full_pilot_e2e.py --skip-live-ops
python3 scripts/e2e/full_pilot_e2e.py --verbose
```
