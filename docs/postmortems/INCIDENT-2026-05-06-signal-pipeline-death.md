---
incident_id: "INCIDENT-2026-05-06-signal-pipeline-death"
date: "2026-05-03T14:20:00Z"
severity: P1
status: resolved
detection_method: "Jarvis Day-21 canary checkpoint investigation"
affected_components:
  - signal-generator
  - signal-consumer
  - influxdb
  - redis
story_id: "ST-PIPE-001, ST-PIPE-002, ST-PIPE-003"
batch: "R2A Canary Batch"
scope_globs:
  - docs/postmortems/
---

# Post-Mortem: Signal Pipeline Death (May 3-6, 2026)

## Summary

The ChiseAI signal pipeline was completely non-functional for approximately 4 days (May 3-6, 2026), producing zero trading signals despite the signal generator reporting a healthy status. The incident was caused by two independent failures introduced during the ST-PIPE-001/002/003 merges on May 3: (1) InfluxDB authentication token drift after a Terraform config fix that was never applied to the running container, and (2) a signal consumer TypeError crash from a missed `run_signal_consumer.py` update. The signal generator silently degraded to zero-output operation while falsely reporting `pipeline_status: healthy`. The incident was detected during Jarvis's Day-21 canary checkpoint review, investigated, and resolved on May 6 via InfluxDB volume wipe, Terraform apply, and container rebuilds. The canary clock was restarted from May 6 (new Day-0).

## Timeline

| Time (UTC)        | Event                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------- |
| 2026-04-12        | R2A canary restarted                                                                                       |
| 2026-05-02 21:11  | Last healthy signals observed (600+ `paper:signal:*` keys in Redis)                                        |
| 2026-05-03 ~14:20 | RECON-R2A commit "Align Redis DB default (1→0) and docker-compose" merged                                  |
| 2026-05-03 19:36  | ST-PIPE-001 merged to main (removed `symbol_throttle_seconds` from `SignalConsumer.__init__()`)            |
| 2026-05-03 19:36  | ST-PIPE-002 merged to main                                                                                 |
| 2026-05-03 20:05  | ST-PIPE-003 merged to main (fixed InfluxDB token in Terraform config)                                      |
| 2026-05-03 ~20:05 | InfluxDB container exited — token mismatch (old volume had stale token, Terraform fix only updated config) |
| 2026-05-03 ~20:05 | Signal consumer crashed on import — `TypeError` in `run_signal_consumer.py` (ST-PIPE-001 missed this file) |
| 2026-05-03 - 05   | Signal generator ran 3,746+ iterations producing 0 signals (InfluxDB unreachable for market data queries)  |
| 2026-05-04 06:57  | Follow-up fix for runner TypeError committed but container never rebuilt — fix never took effect           |
| 2026-05-06        | Jarvis investigation begins during Day-21 checkpoint review                                                |
| 2026-05-06 ~17:00 | InfluxDB volume wiped + `terraform apply` with correct token                                               |
| 2026-05-06 17:48  | Signal consumer restarted, confirmed active                                                                |
| 2026-05-06 18:01  | Signal generator producing signals again (`signals_generated=20`)                                          |
| 2026-05-06 18:02  | Remediation verified complete — pipeline fully operational                                                 |

## Root Cause Analysis

### Symptom

The signal generator heartbeat was reporting `pipeline_status: healthy` every 5 minutes while `signals_generated` was stuck at 0 for 3,746+ consecutive iterations (approximately 4 days). The signal consumer was entirely absent (crashed on import). InfluxDB container was in an exited state. No monitoring alerts fired for any of these failures.

### Underlying Causes

**Primary: InfluxDB Token Drift (ST-PIPE-003)**

1. Why was InfluxDB down? → The container exited because the authentication token was incorrect.
2. Why was the token incorrect? → ST-PIPE-003 updated the token in the Terraform config, but the running container was never recreated. The old InfluxDB volume retained the original (stale) token.
3. Why wasn't the container recreated? → The merge only updated Terraform state. No follow-up `terraform apply` + container recreation was performed as part of the story.
4. Why didn't anyone notice? → The signal generator's heartbeat reported healthy despite generating zero signals. There was no alert for InfluxDB being down.

**Secondary: Signal Consumer TypeError Crash (ST-PIPE-001)**

1. Why did the consumer crash? → `run_signal_consumer.py` still referenced `symbol_throttle_seconds` as a constructor argument after ST-PIPE-001 removed it from `SignalConsumer.__init__()`.
2. Why was this missed? → ST-PIPE-001 updated the class but not the runner script. The runner was not included in the scope of changes.
3. Why wasn't the fix applied? → A follow-up commit on May 4 corrected the runner, but the container was never rebuilt. The fix sat in the image layer cache without being deployed.

### Contributing Factors

- **Falsely healthy heartbeat**: The signal generator reported `pipeline_status: healthy` based on process uptime and schedule adherence, not actual signal output. A heartbeat that reports healthy while producing zero output is worse than no heartbeat — it provides false confidence.
- **Stale cron monitoring**: All 5 cron monitoring jobs were stale since March/April. The checkpoint-audit cron was in ERROR state since March 31 (Gates G10, G12). No automated alerting was functional.
- **Infrastructure change gap**: No process enforced that Terraform config changes must be followed by container recreation. The assumption was that merges to main would be deployed, but there was no deployment verification step.

### Missed Signals

| Signal                                      | When           | Why Missed                                    |
| ------------------------------------------- | -------------- | --------------------------------------------- |
| `signals_generated=0` for 3,746+ iterations | May 3-6        | No alert threshold for zero-output condition  |
| InfluxDB container exited                   | May 3          | No container health monitoring alert          |
| Signal consumer crash (import TypeError)    | May 3          | No consumer liveness check                    |
| All cron jobs stale                         | Since March    | No meta-monitoring of cron freshness          |
| Checkpoint-audit ERROR since March 31       | Since March 31 | Alert existed but cron job was non-functional |

## Impact Assessment

### Affected Systems/Services

- Signal generator (ran but produced zero output)
- Signal consumer (crashed, entirely non-functional)
- InfluxDB (container exited, no market data accessible)
- Paper trading pipeline (no new signals for strategy evaluation)

### Quantified Impact

| Metric                                 | Value                                                    |
| -------------------------------------- | -------------------------------------------------------- |
| **Duration of outage**                 | ~4 days (May 3 20:05 → May 6 18:02 UTC)                  |
| **Signal iterations with zero output** | 3,746+                                                   |
| **Signal data lost**                   | ~4 days of market signal data                            |
| **Historical signals preserved**       | ~189,796 keys in consumer state                          |
| **Canary checkpoint**                  | Day-21 FAILED                                            |
| **Canary clock**                       | Restarted from May 6 (new Day-0)                         |
| **Capital risk**                       | None (paper trading only)                                |
| **Monitoring gaps**                    | 5 stale cron jobs, checkpoint-audit ERROR since March 31 |

### Canary Impact

- Day-21 canary checkpoint window (7-day lookback) included 4 days of dead pipeline.
- Verdict: **FAIL** — pipeline non-functional for majority of validation window.
- Canary clock restarted from May 6, 2026 18:02 UTC (new Day-0).
- Next checkpoint: ~Day-21 from May 6.

## Resolution

### Immediate Fix

**InfluxDB Recovery:**

1. Identified InfluxDB container in exited state
2. Diagnosed token mismatch between Terraform config and container volume
3. Wiped InfluxDB volume to remove stale token
4. Ran `terraform apply` to recreate InfluxDB with correct token from Terraform state
5. Verified InfluxDB connectivity

**Signal Consumer Recovery:**

1. Confirmed May 4 runner fix was in source but never deployed
2. Ran `docker compose build --no-cache signal-consumer`
3. Ran `docker compose up -d signal-consumer`
4. Verified consumer active and processing signals

**Signal Generator Recovery:**

1. Confirmed generator was running but producing zero output (InfluxDB unreachable)
2. Rebuilt container: `docker compose build --no-cache signal-generator`
3. Restarted: `docker compose up -d signal-generator`
4. Verified `signals_generated=20` at 18:01 UTC

**Environment Fix:**

- Updated `.env` files with correct `INFLUXDB_TOKEN` value

### Verification

- 2026-05-06 18:01 UTC: Signal generator producing signals (`signals_generated=20`)
- 2026-05-06 18:02 UTC: Signal consumer active and consuming
- 2026-05-06 18:02 UTC: InfluxDB healthy and queryable
- 2026-05-06 18:02 UTC: Remediation declared complete

## Prevention Rules

### PR-001: InfluxDB Init Tokens Are One-Time — Clean Volume Required

```
Rule: InfluxDB token rotation requires volume wipe
When: Changing INFLUXDB_TOKEN in Terraform config or .env files
Then: The InfluxDB container volume MUST be wiped before recreation.
      InfluxDB init tokens are one-time-use. The container writes the token
      to its data volume on first init. Subsequent starts read from the volume,
      ignoring the config token. Terraform apply alone is insufficient.
Verification: curl http://localhost:8086/health after recreation.
```

### PR-002: Docker Host Port Mapping Can Silently Fail with nftables

```
Rule: Verify port mapping with actual connectivity test
When: Rebuilding or restarting Docker containers that expose host ports
Then: Verify connectivity with `curl http://localhost:<port>/health` or equivalent.
      Do NOT rely on `docker ps` showing the port mapping — nftables rules can
      silently prevent host-level access even when Docker reports the port as mapped.
Verification: curl test from the host, not just docker ps output.
```

### PR-003: Heartbeat Must Report Degraded on Zero Output

```
Rule: Heartbeat semantics require output verification
When: Signal generator heartbeat reports pipeline status
Then: If signals_generated=0 for more than 3 consecutive iterations (15 minutes),
      the heartbeat MUST report pipeline_status: degraded, NOT healthy.
      A healthy report without output verification is a false positive that
      delays incident detection.
Verification: Alert triggers on 3 consecutive zero-output heartbeats.
```

## Follow-up Actions

- [ ] Create story for supervisor PID tracking bug (spawns multiple child processes, loses track of PID) — Owner: @aria, Due: 2026-05-08
- [ ] Create story for monitoring alerts on: `signals_generated=0` for >15 min, InfluxDB down, consumer dead — Owner: @aria, Due: 2026-05-08
- [ ] Create story for heartbeat fix: report `degraded` when `signals_generated=0` for >3 iterations — Owner: @aria, Due: 2026-05-08
- [ ] Restart all 5 stale cron monitoring jobs — Owner: @jarvis, Due: 2026-05-07
- [ ] Fix checkpoint-audit cron (Gates G10, G12) — Owner: @jarvis, Due: 2026-05-07
- [ ] Refresh promotion gate TTL (expired 2026-04-29) — Owner: @jarvis, Due: 2026-05-07

## Lessons Learned

### What Went Well

- **Independent verification**: Jarvis did not accept workflow status claims at face value. LESSON-20260329-completion-fraud-detection was applied — the Day-21 checkpoint review independently verified pipeline health by checking actual Redis keys and signal counts, not just status strings.
- **Historical data preserved**: ~189,796 historical signal keys in consumer state survived the outage. The InfluxDB volume wipe only affected recent data (which was already absent).
- **No capital risk**: Paper trading only — the pipeline death had zero financial impact.

### What Could Be Better

- **Infrastructure change follow-through**: ST-PIPE-003 updated Terraform config but no process ensured the change was actually deployed. Merges to main must include deployment verification for infrastructure changes.
- **Container rebuild enforcement**: The May 4 runner fix was committed but the container was never rebuilt. Code changes in running containers require explicit rebuild + redeploy steps.
- **Monitoring coverage**: Zero functional monitoring for the signal pipeline. All cron jobs were stale, and the only "monitoring" was a heartbeat that falsely reported healthy.

### Key Insights

- **"Healthy" heartbeats that don't verify actual output are worse than no heartbeat.** They provide false confidence and delay incident detection. The signal generator ran 3,746+ iterations reporting healthy while producing nothing.
- **Infrastructure changes (Terraform, env vars) must be followed by container recreation.** Config-only changes are invisible to running containers.
- **Independent verification at checkpoints is critical.** Without the Day-21 canary checkpoint review, this outage could have persisted much longer.

---

## Blameless Culture Reminder

This post-mortem follows the ChiseAI blameless culture:

- Focus on system/process failures, not individual blame
- Ask "How did the process allow this?" not "Why did YOU do that?"
- Look for patterns across incidents
- Thank people for admitting mistakes and sharing learnings

**Remember:** The goal is learning and prevention, not blame.

---

## Metadata

| Field             | Value                                     |
| ----------------- | ----------------------------------------- |
| Incident ID       | INCIDENT-2026-05-06-signal-pipeline-death |
| Created           | 2026-05-06                                |
| Severity          | P1                                        |
| Stories           | ST-PIPE-001, ST-PIPE-002, ST-PIPE-003     |
| Lead Investigator | @jarvis                                   |
| Reviewers         | @aria                                     |
| Status            | Complete                                  |
