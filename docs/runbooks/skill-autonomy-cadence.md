# Skill Autonomy Cadence Runbook

## Objective

Run skills-autonomy reporting and backlog-candidate generation weekly without manual intervention.

## Weekly Job

Primary command:
```bash
python3 scripts/ops/skill_autonomy_tick.py --mode=weekly
python3 scripts/ops/ingest_skill_backlog_candidates.py
python3 scripts/monitoring/skill_autonomy_queue_depth.py
python3 scripts/ops/cleanup_skill_autonomy_artifacts.py
```

Cron wrapper:
- `scripts/cron/weekly_skill_autonomy.sh`

Cron template:
- `infrastructure/cron/chiseai-weekly-skill-autonomy`

Schedule default:
- Monday 01:30 UTC

## Notifications and Auto-Commit

Environment variables used by `scripts/cron/weekly_skill_autonomy.sh`:
- `DISCORD_DEV_WEBHOOK_URL` or `DISCORD_WEBHOOK_URL`: optional success/failure notifications
- `SKILL_AUTONOMY_AUTO_COMMIT`: `0|1` (default `0`)
- `SKILL_AUTONOMY_COMMIT_BRANCH`: required when auto-commit is enabled
- `SKILL_AUTONOMY_COMMIT_MESSAGE`: optional custom commit message

Safety behavior:
- auto-commit is skipped unless explicitly enabled
- auto-commit only runs when current branch matches `SKILL_AUTONOMY_COMMIT_BRANCH`

## Outputs

1. Weekly KPI artifact:
- `docs/tempmemories/skill-autonomy-weekly-<week>-<timestamp>.md`

2. Backlog candidates (threshold-based):
- `docs/backlog/skills-autonomy-candidates-<week>.md`

3. Redis queue for planning ingestion:
- `bmad:chiseai:skills:backlog:candidates`

4. Canonical backlog ingestion target:
- `docs/bmm-workflow-status.yaml` under `backlog:`

## Performance Controls

Configured in `config/skill_autonomy.yaml`:
- runtime budget
- command timeout
- sampling
- scan bounds
- lock file

## Queue Alerting

Queue monitor:
```bash
python3 scripts/monitoring/skill_autonomy_queue_depth.py
```

Default thresholds:
- warn: 25
- critical: 100

## Retention Cleanup

Cleanup command:
```bash
python3 scripts/ops/cleanup_skill_autonomy_artifacts.py --dry-run
```

Default retention:
- weekly artifacts: 60 days
- backlog candidate artifacts: 120 days

## Safety Model

- Missing skills remain non-blocking.
- Only quality/safety gates block execution.
- Weekly cadence creates planning inputs, not runtime blockers.

## Verification

```bash
python3 scripts/ops/skill_autonomy_tick.py --mode=weekly --dry-run
python3 scripts/ops/skill_autonomy_tick.py --mode=weekly
```

Check artifacts:
```bash
ls -1 docs/tempmemories/skill-autonomy-weekly-*.md | tail -n 3
ls -1 docs/backlog/skills-autonomy-candidates-*.md | tail -n 3
```

Check Redis queue length:
```bash
redis-cli -h host.docker.internal -p 6380 LLEN bmad:chiseai:skills:backlog:candidates
```
