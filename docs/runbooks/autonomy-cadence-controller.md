# Autonomy Cadence Controller Runbook

> **Story:** CH-AUTONOMY-PHASE1  
> **Last Updated:** 2026-03-09  
> **Owner:** Governance/Platform  
> **Status:** Active

## 1. Purpose

`scripts/evaluation/autonomy_cadence_controller.py` is the Phase 1 unified scheduler for autonomous jobs:
- registry-driven job orchestration
- persistent job state
- missed cadence and stuck/timeout alerting
- optional Discord notifications

## 2. Registry

Path:
- `config/autonomy_job_registry.yaml`

Current first-wave jobs:
- `ops.kpi_ingest_6h`
- `ops.daily_trends`
- `governance.daily_reflection`
- `governance.metacog_weekly`
- `memory.daily_sweep`
- `skills.autonomy_weekly`
- `strategy.experiment_triage_weekly`
- `strategy.canary_review_weekly`

## 3. Commands

Validate registry:
```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --validate-only
```

Single tick:
```bash
python3 scripts/evaluation/autonomy_cadence_controller.py
```

Dry-run forced smoke:
```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --dry-run --force
```

Daemon:
```bash
python3 scripts/evaluation/autonomy_cadence_controller.py --daemon
```

Cron wrapper:
```bash
scripts/cron/autonomy_cadence_tick.sh
```

## 4. State and Logs

Artifacts:
- `_bmad-output/autonomy-cadence/state.json`
- `_bmad-output/autonomy-cadence/runs.jsonl`
- `_bmad-output/autonomy-cadence/alerts.jsonl`
- `logs/autonomy-cadence/tick-YYYYMMDD.log` (cron wrapper)

Quick checks:
```bash
jq . _bmad-output/autonomy-cadence/state.json
tail -n 20 _bmad-output/autonomy-cadence/runs.jsonl
tail -n 20 _bmad-output/autonomy-cadence/alerts.jsonl
```

## 5. Discord Notifications

Webhook resolution priority:
1. `DISCORD_AUTONOMY_WEBHOOK_URL`
2. `DISCORD_DEV_WEBHOOK_URL`
3. `DISCORD_STANDUP_WEBHOOK`
4. `DISCORD_WEBHOOK_URL`
5. `CHISE_DISCORD_WEBHOOK_URL`

Enable/disable:
- `CHISE_AUTONOMY_NOTIFY_DISCORD=true|false` (default true)

Notes:
- `DISCORD_DEVELOPMENT_CHANNEL_ID` is a channel ID and cannot replace webhook URL.
- HTTP `403 Forbidden` indicates webhook permission/validity issue, not scheduler logic.

## 6. Cron Installation (host)

Run every minute:
```bash
* * * * * /home/tacopants/projects/ChiseAI/scripts/cron/autonomy_cadence_tick.sh
```

Verify:
```bash
tail -f /home/tacopants/projects/ChiseAI/logs/autonomy-cadence/tick-$(date -u +%Y%m%d).log
```

Daily executive summary post to Discord:
```bash
0 13 * * * /home/tacopants/projects/ChiseAI/scripts/cron/full_pilot_daily_summary.sh
```

## 7. Troubleshooting

No jobs run:
- Check cadence windows and last run timestamps in `state.json`.
- Use `--force` for immediate execution.

Missed cadence alerts:
- Inspect `_bmad-output/autonomy-cadence/alerts.jsonl`.
- Confirm job command availability and runtime dependencies.

Stuck/timeout alerts:
- Increase job `timeout_seconds` in registry if valid.
- Run the job command manually to isolate root cause.

Discord errors:
- Validate webhook by direct post:
```bash
python3 scripts/discord/test_webhook.py --webhook-url "<url>" --message "autonomy test"
```

## 8. Approval Workflow (Phase 3 Guardrails)

List pending approvals:
```bash
python3 scripts/ops/manage_approvals.py --list-pending
```

Approve guarded strategy autopilot:
```bash
python3 scripts/ops/manage_approvals.py --approve strategy-autopilot
```

Revoke approval:
```bash
python3 scripts/ops/manage_approvals.py --revoke strategy-autopilot
```

How you know fixes are applied:
- Daily summary includes:
  - `Fixes Applied (Recovered Jobs, 24h)`
  - `Unresolved Failed Jobs (24h)`
- Cadence alerts include `job_recovered` when a previously failed/timeout job returns to success.

## 9. Opencode Auto-Dispatch (Aria)

Purpose:
- automatically route policy-safe low/medium alerts to Aria via Opencode CLI prompt bundles.

Script:
```bash
python3 scripts/ops/opencode_autodispatch.py --dry-run
python3 scripts/ops/opencode_autodispatch.py
```

Cadence job:
- `ops.opencode_autodispatch_5m` (every 5 minutes)

Recommended settings:
- `CHISE_AUTODISPATCH_MAX_CONCURRENT=2`
- `CHISE_AUTODISPATCH_RETRY_BUDGET=2`
- `CHISE_AUTODISPATCH_DEDUPE_HOURS=24`
- `CHISE_OPENCODE_AUTODISPATCH_ENABLED=false` by default until ready

Optional CLI template:
```bash
CHISE_OPENCODE_AUTODISPATCH_CMD="opencode run --agent Aria --prompt-file {prompt_file}"
```

Artifacts:
- `_bmad-output/autonomy-dispatch/state.json`
- `_bmad-output/autonomy-dispatch/tasks.jsonl`
- `_bmad-output/autonomy-dispatch/prompts/*.md`
