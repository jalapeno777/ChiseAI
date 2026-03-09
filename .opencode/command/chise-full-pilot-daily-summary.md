---
name: "chise-full-pilot-daily-summary"
description: "ChiseAI: generate and post daily Full Pilot executive summary to Discord."
disable-model-invocation: true
---

Run a one-off post:

```bash
python3 scripts/ops/post_daily_full_pilot_summary.py --regenerate
```

Dry-run preview without posting:

```bash
python3 scripts/ops/post_daily_full_pilot_summary.py --regenerate --dry-run
```

Cron wrapper:

```bash
scripts/cron/full_pilot_daily_summary.sh
```
