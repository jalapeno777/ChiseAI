# Autonomy Cadence Operations Runbook

## Overview
Operational procedures for managing the autonomy cadence controller and job health.

## Quick Health Check
```bash
# Full system health
python3 scripts/ops/autonomy_job_health.py

# Specific job health
python3 scripts/ops/autonomy_job_health.py --job ops.kpi_ingest_6h
```

## Missed Cadence Triage

### 1. Check Job State
```bash
python3 scripts/ops/autonomy_job_health.py --job <job_id>
```

### 2. Check Scheduler Health
```bash
# Check container
docker ps --filter name=scheduler

# Check Redis heartbeat
redis-cli -p 6380 HGETALL bmad:chiseai:scheduler:heartbeat
redis-cli -p 6380 GET bmad:chiseai:scheduler:last_seen
```

### 3. Check Recent Runs
```bash
grep '"job_id": "<job_id>"' _bmad-output/autonomy-cadence/runs.jsonl | tail -5
```

### 4. Check Idempotency
```bash
# Verify no duplicate executions for same idempotency key
python3 -c "
import json
from collections import Counter
runs = [json.loads(l) for l in open('_bmad-output/autonomy-cadence/runs.jsonl') if l.strip()]
idem_counts = Counter(r.get('idempotency_key') for r in runs if r.get('job_id') == '<job_id>')
duplicates = {k: v for k, v in idem_counts.items() if v > 1}
print('Duplicates:', duplicates if duplicates else 'None')
"
```

## Scheduler Heartbeat Verification

### Correct Redis Commands
```bash
# For heartbeat (type: hash)
redis-cli -p 6380 HGETALL bmad:chiseai:scheduler:heartbeat

# For last_seen (type: string)
redis-cli -p 6380 GET bmad:chiseai:scheduler:last_seen

# Check key types
redis-cli -p 6380 TYPE bmad:chiseai:scheduler:heartbeat
redis-cli -p 6380 TYPE bmad:chiseai:scheduler:last_seen
```

### Interpreting Results
- `status: running` = healthy
- `last_run_time` within 5 minutes = active
- TTL > 0 = key is being refreshed

## Memory Sweep Toggle

### Enable Job
Edit `config/autonomy_job_registry.yaml`:
```yaml
- job_id: memory.daily_sweep
  enabled: true
  command:
    - python3
    - scripts/ops/memory_sweep.py
    - --full-sweep
    - --enable  # Required flag
```

### Disable Job
Edit `config/autonomy_job_registry.yaml`:
```yaml
- job_id: memory.daily_sweep
  enabled: false
  # DISABLED: <reason>
```

### Test Job
```bash
# Dry run (safe)
python3 scripts/ops/memory_sweep.py --full-sweep --dry-run

# Full execution (requires --enable)
python3 scripts/ops/memory_sweep.py --full-sweep --enable
```

## Recovery Procedures

### Job Stuck in Running State
```bash
# Clear running state (use with caution)
python3 -c "
import json
from pathlib import Path
state = json.loads(Path('_bmad-output/autonomy-cadence/state.json').read_text())
if '<job_id>' in state['jobs']:
    state['jobs']['<job_id>'].pop('running_since', None)
    Path('_bmad-output/autonomy-cadence/state.json').write_text(json.dumps(state, indent=2))
    print('Cleared running state')
"
```

### Force Job Execution
```bash
# Run autonomy cadence controller with force flag
python3 scripts/evaluation/autonomy_cadence_controller.py --force-job <job_id>
```

## Alert Response

### Missed Cadence Alert
1. Check if job is already recovered: `python3 scripts/ops/autonomy_job_health.py --job <job_id>`
2. If recovered, alert is stale - no action needed
3. If not recovered, check scheduler health
4. If scheduler healthy, check job configuration

### Job Stuck Alert
1. Check process: `ps aux | grep <job_id>`
2. Check timeout: compare `running_since` to `timeout_seconds`
3. If truly stuck, clear running state and retry

## Idempotency Safety

### Key Format
- Format: `<job_id>:<date>` (e.g., `ops.kpi_ingest_6h:2026-03-11`)
- One successful execution per key per day
- State file tracks `last_idempotency_key`

### Manual Execution Safety
```bash
# Check current idempotency key
python3 -c "
import json
state = json.loads(open('_bmad-output/autonomy-cadence/state.json').read())
print(state['jobs']['<job_id>'].get('last_idempotency_key'))
"

# Only run if key would be different
```

## Related Documentation
- `docs/bmm-workflow-status.yaml` - Story tracking
- `config/autonomy_job_registry.yaml` - Job definitions
- `scripts/evaluation/autonomy_cadence_controller.py` - Controller source
