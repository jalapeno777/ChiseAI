# ST-AUTOCOG-R-002b: Cron Verification Evidence

**Story ID**: ST-AUTOCOG-R-002b  
**Task**: Verify 5 autocog cron schedules are registered in Woodpecker and triggering  
**Date**: 2026-03-29  
**Agent**: Dev (Executor)  
**Branch**: feature/ST-AUTOCOG-R-002b-cron-verification  
**Status**: **P0 BLOCKER FOUND**

---

## Executive Summary

**VERIFICATION FAILED - P0 BLOCKER**: The 5 autocog cron schedules defined in `.woodpecker/autocog-scheduler.yaml` are **NOT currently operational**.

- Woodpecker cron is deprecated (see `docs/evidence/woodpecker-cron-deprecated.md`)
- Replacement Docker scheduler (`chiseai-brain-scheduler`) is **Exited 8 days ago**
- The Docker scheduler was running BrainEval jobs, NOT AutoCog jobs
- AutoCog crons have NOT been running

---

## 1. YAML Definitions Verification: ✅ PASS

The 5 autocog cron schedules are correctly defined in `.woodpecker/autocog-scheduler.yaml`:

| Cron Name                      | Schedule                | Cron Expression | YAML Defined |
| ------------------------------ | ----------------------- | --------------- | ------------ |
| `autocog-hourly`               | Every hour              | `0 * * * *`     | ✅           |
| `autocog-improvement-daily`    | Daily at 02:00 UTC      | `0 2 * * *`     | ✅           |
| `autocog-constitution-daily`   | Daily at 03:00 UTC      | `0 3 * * *`     | ✅           |
| `autocog-calibration-weekly`   | Weekly Monday 01:00 UTC | `0 1 * * 1`     | ✅           |
| `autocog-autonomy-tune-weekly` | Weekly Monday 02:00 UTC | `0 2 * * 1`     | ✅           |

**Evidence**: `.woodpecker/autocog-scheduler.yaml` lines 8-13, 26-31

---

## 2. Woodpecker Registration: ⚠️ CANNOT VERIFY

**Issue**: Woodpecker API is not accessible from this agent environment.

- Agent runs inside a container where `localhost:8012` (Woodpecker port) is not reachable
- Woodpecker server runs on Docker host with port mapping `0.0.0.0:8012->8000`
- Connection tests returned HTTP 000 (connection refused)

**Commands Attempted**:

```bash
curl -s http://localhost:8012/api/repos/1/ChiseAI/cron  # Connection refused
curl -s http://host.docker.internal:8012/api/repos/1/ChiseAI/cron  # Connection refused
```

**Workaround**: Could not query Woodpecker API directly. Need manual verification or exec access to Woodpecker container.

---

## 3. Docker Scheduler Status: ❌ FAILED

**Replacement Scheduler**: `chiseai-brain-scheduler`  
**Status**: **Exited (0) 8 days ago**

```bash
$ docker ps -a | grep brain-scheduler
chiseai-brain-scheduler   Exited (0) 8 days ago
```

**Last Logs** (2026-03-20 17:32):

```
2026-03-20 17:32:00,186 - kpi_scheduler - INFO - Weekly cycle completed successfully
2026-03-20 17:31:55,080 - Received signal 15, initiating graceful shutdown...
```

**Critical Finding**: The Docker scheduler was running **BrainEval** jobs, NOT **AutoCog** jobs:

- `run_mini_eval.py` (6h cycle)
- `run_daily_trends.py` (daily cycle)
- `run_weekly_reflection.py` (weekly cycle)

**No AutoCog job references found in scheduler logs**:

```bash
$ docker logs chiseai-brain-scheduler | grep -i "autocog\|constitution\|improvement\|calibration\|autonomy"
# NO MATCHES
```

---

## 4. Deprecation Context

From `docs/evidence/woodpecker-cron-deprecated.md`:

> **Date**: 2026-03-03  
> **Status**: DEPRECATED  
> **Replacement**: Docker-based scheduler (`chiseai-brain-scheduler`)

The deprecation notice explicitly states:

- Woodpecker cron is deprecated
- Replacement is Docker-based scheduler
- Migration happened ~3 weeks ago (2026-03-03)

**However**: The Docker scheduler was built for BrainEval (ST-EVAL-SCHEDULER-001), NOT AutoCog (AUTOCOG-SCHED-001).

---

## 5. P0 Blocker Summary

### What's Broken

| Component                  | Status        | Issue                                 |
| -------------------------- | ------------- | ------------------------------------- |
| AutoCog cron in Woodpecker | Likely broken | Woodpecker cron deprecated            |
| Docker scheduler           | Not running   | Exited 8 days ago                     |
| AutoCog jobs               | Not running   | Never implemented in Docker scheduler |
| BrainEval jobs             | Not running   | Docker scheduler stopped              |

### Root Cause Analysis

1. **Design Gap**: AutoCog schedules were defined in `.woodpecker/autocog-scheduler.yaml` but:
   - Woodpecker cron was deprecated before the AutoCog scheduler was fully deployed
   - No clear path from deprecated Woodpecker cron to operational scheduler

2. **Scope Mismatch**: The Docker scheduler (`chiseai-brain-scheduler`) was built for BrainEval (ST-EVAL-SCHEDULER-001), running different scripts:
   - `run_mini_eval.py`
   - `run_daily_trends.py`
   - `run_weekly_reflection.py`

   It does NOT run AutoCog scripts like:
   - `run_autonomous_full_cycle.py --mode belief_consistency`
   - `run_autonomous_full_cycle.py --mode improvement_cycle`
   - etc.

3. **Operational Gap**: Even though the Docker scheduler container exists, it stopped running 8 days ago and was not restarted.

---

## 6. Fix Requirements (For P0 Remediation)

### Option A: Fix Docker Scheduler for AutoCog (Recommended)

1. **Update `docker-compose.scheduler.yml`** to include AutoCog schedules:
   - Add `SCHEDULER_INTERVAL_HOURLY`, `SCHEDULER_INTERVAL_DAILY_2AM`, etc.
   - Point to `scripts/ops/run_autonomous_full_cycle.py` with appropriate modes

2. **Update `Dockerfile.scheduler`** to include AutoCog scripts

3. **Create new image and restart container**:

   ```bash
   docker build -f infrastructure/docker/Dockerfile.scheduler -t chiseai-brain-scheduler:latest .
   docker compose -f infrastructure/docker/docker-compose.scheduler.yml up -d
   ```

4. **Add health monitoring** for AutoCog cycles

### Option B: Restore Woodpecker Cron (Emergency)

If Docker scheduler is not ready, restore Woodpecker cron via Woodpecker UI/API:

- Note: Woodpecker cron is deprecated and may not be reliable

### Option C: Hybrid Approach

1. **Immediate**: Restore `chiseai-brain-scheduler` with BrainEval jobs (quick fix)
2. **Medium-term**: Add AutoCog schedules to Docker scheduler
3. **Long-term**: Deprecate Woodpecker cron entirely

---

## 7. Verification Commands

To manually verify cron status when Woodpecker API is accessible:

```bash
# List Woodpecker crons
curl -H "Authorization: Bearer $WOODPECKER_TOKEN" \
  "http://woodpecker:9000/api/repos/{repo_id}/ChiseAI/cron"

# Check recent pipeline runs for cron
curl -H "Authorization: Bearer $WOODPECKER_TOKEN" \
  "http://woodpecker:9000/api/repos/{repo_id}/ChiseAI/pipelines?event=cron&after=2026-03-22"
```

---

## 8. Evidence References

| File                                                 | Description                   |
| ---------------------------------------------------- | ----------------------------- |
| `.woodpecker/autocog-scheduler.yaml`                 | AutoCog cron YAML definitions |
| `docs/evidence/woodpecker-cron-deprecated.md`        | Deprecation notice            |
| `infrastructure/docker/docker-compose.scheduler.yml` | Docker scheduler config       |
| `docker ps -a`                                       | Container status evidence     |

---

## 9. Next Steps

1. **P0 Owner**: Needs to decide on Option A/B/C
2. **Implementation**: Requires ST-AUTOCOG-SCHED-001 or similar story
3. **Verification**: After fix, re-run ST-AUTOCOG-R-002b verification

---

**Report Generated**: 2026-03-29  
**Verification Status**: INCOMPLETE - P0 BLOCKER FOUND  
**Recommendation**: STOP and fix P0 before continuing with AutoCog development
