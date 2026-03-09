---
name: "chise-opencode-autodispatch"
description: "ChiseAI: auto-dispatch policy-safe cadence alerts to Opencode Aria tasks."
disable-model-invocation: true
---

Dry-run routing and queueing:

```bash
python3 scripts/ops/opencode_autodispatch.py --dry-run
```

Live dispatch (requires `CHISE_OPENCODE_AUTODISPATCH_ENABLED=true`):

```bash
python3 scripts/ops/opencode_autodispatch.py
```

Recommended defaults:
- `CHISE_AUTODISPATCH_MAX_CONCURRENT=2`
- `CHISE_AUTODISPATCH_RETRY_BUDGET=2`
- `CHISE_AUTODISPATCH_DEDUPE_HOURS=24`

Optional command template:

```bash
CHISE_OPENCODE_AUTODISPATCH_CMD="opencode run --agent Aria --prompt-file {prompt_file}"
```
