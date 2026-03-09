---
name: "chise-autonomy-cadence-tick"
description: "ChiseAI: run the unified autonomy cadence controller tick/daemon with registry-driven jobs and alerting."
disable-model-invocation: true
---

Run unified autonomy cadence jobs from `config/autonomy_job_registry.yaml`.

## Validate registry

```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --validate-only
```

## Run one scheduler tick (normal mode)

```bash
python3 scripts/evaluation/autonomy_cadence_controller.py
```

## Force-run all registered jobs in dry-run mode (smoke test)

```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --dry-run --force
```

## Force-run selected job IDs only

```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --force --job-id governance.metacog_weekly
python3 scripts/evaluation/autonomy_cadence_controller.py --force --job-id strategy.canary_review_weekly
```

## Daemon mode

```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --daemon
```

## Cron mode wrapper (recommended for host cron)

```bash
scripts/cron/autonomy_cadence_tick.sh
```

## Outputs

- State: `_bmad-output/autonomy-cadence/state.json`
- Run log: `_bmad-output/autonomy-cadence/runs.jsonl`
- Alerts: `_bmad-output/autonomy-cadence/alerts.jsonl`

## Discord notification env vars

- `DISCORD_AUTONOMY_WEBHOOK_URL` (preferred)
- `DISCORD_DEV_WEBHOOK_URL` (fallback)
- `DISCORD_STANDUP_WEBHOOK` / `DISCORD_WEBHOOK_URL` / `CHISE_DISCORD_WEBHOOK_URL` (fallbacks)
- `CHISE_AUTONOMY_NOTIFY_DISCORD=true|false`
