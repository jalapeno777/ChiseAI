# Brain Rollback Steps Documentation

## Overview

This document details the complete rollback procedure for Chise brain versions.
Rollback must complete within 5 minutes and includes verification at each stage.

## Rollback Triggers

The following conditions trigger an automatic or manual rollback:

1. **ECE Degradation > 0.15**
   - Expected Calibration Error increases by more than 0.15 from baseline
   - Indicates model confidence calibration has degraded

2. **Safety Violations**
   - Any critical safety check failure in production
   - Includes data consistency errors, unauthorized access attempts

3. **Human Request**
   - Manual rollback initiated by authorized personnel
   - Available via CLI with optional `--force` override

4. **Win Rate Drop Below 50%**
   - Rolling 24-hour win rate falls below 50%
   - Indicates model performance degradation

5. **Max Drawdown Exceeds 20%**
   - Portfolio drawdown exceeds 20% from peak
   - Risk management trigger

## Pre-Rollback Safety Checks

Before executing any rollback, the following checks must pass (or be overridden with `--force`):

### 1. No Active Trades
```bash
# Check command
python -m src.execution.check_trades --status=active --count

# Expected result
Active trade count = 0
```

If active trades exist:
- Wait for natural completion (preferred)
- Or manually close positions
- Document any forced closures

### 2. Data Consistency Verification
```bash
# Full consistency check
python -m src.data.consistency_check --full

# Summary only
python -m src.data.consistency_check --summary
```

Checks include:
- PostgreSQL data integrity
- InfluxDB time-series continuity
- Redis cache consistency
- Qdrant vector index validity

### 3. Signal Generation Status
```bash
# Check if signals are active
python -m src.brain.rollback_handler verify-state
```

## Rollback Steps

### Step 1: Stop Signal Generation (30 seconds)

**Command:**
```bash
python -m src.brain.rollback_handler stop-signals --version=CURRENT_VERSION
```

**Verification:**
```bash
python -m src.brain.rollback_handler check-signals --version=CURRENT_VERSION
```

**Expected Result:**
- Signal generation stopped
- No new signals being emitted
- Dashboard shows "Signal generation paused"

**On Failure:**
- Check process status: `ps aux | grep signal_generator`
- Force kill if necessary: `pkill -f signal_generator`
- Document any force kill in rollback log

---

### Step 2: Verify No Active Trades (15 seconds) [REQUIRES CONFIRMATION]

**Command:**
```bash
python -m src.execution.check_trades --status=active
```

**Verification:**
```bash
python -m src.execution.check_trades --status=active --count
```

**Expected Result:**
- Active trade count = 0

**If Trades Active:**
1. Check trade ages: `python -m src.execution.check_trades --status=active --age`
2. For trades < 1 hour old: Consider waiting
3. For trades > 1 hour old: Consider manual close
4. Document decision in rollback log

**Confirmation Prompt:**
```
⚠️  {N} active trades detected.
   Continue with rollback? [y/N]: 
```

---

### Step 3: Switch Brain Version (60 seconds) [REQUIRES CONFIRMATION]

**Command:**
```bash
python -m src.brain.rollback_handler switch-version \
  --from=CURRENT_VERSION \
  --to=PREVIOUS_VERSION
```

**Verification:**
```bash
python -m src.brain.rollback_handler get-current-version
```

**Expected Result:**
- Current version is previous stable version
- Model files loaded successfully
- Configuration updated

**Rollback Points:**
- Model weights directory: `models/brain/{version}/`
- Configuration file: `config/brain_config.yaml`
- Version symlink: `models/brain/current` → `models/brain/{version}/`

**On Failure:**
1. Check disk space: `df -h`
2. Check model file integrity: `sha256sum models/brain/{version}/*`
3. Restore from backup if needed: `aws s3 cp s3://chiseai-backups/models/{version}/ models/brain/{version}/`

---

### Step 4: Verify Data Consistency (120 seconds)

**Command:**
```bash
python -m src.data.consistency_check --full
```

**Verification:**
```bash
python -m src.data.consistency_check --summary
```

**Expected Result:**
- All consistency checks pass
- No data corruption detected
- Time-series data continuous

**Checks Include:**
- PostgreSQL table integrity
- InfluxDB measurement continuity
- Redis key validity
- Qdrant collection health

**On Failure:**
1. Identify corrupted data source
2. Restore from backup if needed
3. Run repair scripts: `python -m src.data.repair --source={source}`
4. Re-verify before proceeding

---

### Step 5: Resume Signal Generation (30 seconds)

**Command:**
```bash
python -m src.brain.rollback_handler start-signals --version=PREVIOUS_VERSION
```

**Verification:**
```bash
python -m src.brain.rollback_handler check-signals --version=PREVIOUS_VERSION
```

**Expected Result:**
- Signal generation resumed with previous version
- Dashboard shows "Signal generation active"
- New signals being generated

**Health Checks:**
- Signal latency < 1 second
- No errors in logs: `tail -f logs/signal_generator.log`
- Dashboard receiving updates

---

## Emergency Rollback

For critical situations requiring immediate rollback:

```bash
# Emergency rollback with force (skips safety checks)
python -m src.brain.rollback_handler emergency \
  --reason="Critical system failure" \
  --force
```

**⚠️  WARNING:** Emergency rollback with `--force` will:
- Skip active trade verification
- Skip data consistency checks
- May result in data loss or inconsistent state
- Must be followed by manual verification

## Post-Rollback Verification

After rollback completes, verify:

1. **Signal Generation**
   ```bash
   python -m src.brain.rollback_handler check-signals
   ```

2. **Trade Status**
   ```bash
   python -m src.execution.check_trades --status=all --summary
   ```

3. **Data Consistency**
   ```bash
   python -m src.data.consistency_check --summary
   ```

4. **Dashboard Health**
   ```bash
   curl http://localhost:8502/_stcore/health
   ```

5. **Log Review**
   ```bash
   tail -n 100 logs/rollback.log
   ```

## Rollback Logging

All rollback operations are logged for post-mortem analysis:

**Log Locations:**
- JSON: `_bmad-output/rollback-logs/{rollback_id}.json`
- Markdown: `_bmad-output/rollback-logs/{rollback_id}.md`

**View Rollback Report:**
```bash
python -m src.brain.rollback_handler report --rollback-id=RB-{timestamp}-{trigger}
```

**List All Rollbacks:**
```bash
python -m src.brain.rollback_handler list-logs
```

## Recovery Procedures

### If Rollback Fails Mid-Process

1. **Do not panic** - System is designed to be recoverable
2. Check current state: `python -m src.brain.rollback_handler verify-state`
3. Identify failed step from logs
4. Retry failed step manually
5. If stuck, contact: #incidents channel on Discord

### If Data Corruption Detected

1. Stop all services: `docker-compose stop`
2. Identify last known good backup
3. Restore from backup:
   ```bash
   # PostgreSQL
   pg_restore -h localhost -p 5434 -U chiseai -d chiseai backup.sql
   
   # InfluxDB
   influx restore --bucket chiseai /path/to/backup
   
   # Redis
   redis-cli -p 6380 FLUSHALL
   redis-cli -p 6380 RESTORE < backup.rdb
   ```
4. Re-verify consistency
5. Resume services

### If Model Files Corrupted

1. Remove corrupted model: `rm -rf models/brain/{version}/`
2. Restore from S3:
   ```bash
   aws s3 sync s3://chiseai-backups/models/{version}/ models/brain/{version}/
   ```
3. Verify checksums:
   ```bash
   sha256sum -c models/brain/{version}/checksums.sha256
   ```
4. Reload model

## Testing Rollback in Dev

Before any production deployment, test rollback in dev:

```bash
# 1. Deploy new version to dev
./scripts/deploy-dev.sh --version=NEW_VERSION

# 2. Verify it's working
./scripts/health-check-dev.sh

# 3. Trigger test rollback
python -m src.brain.rollback_handler trigger \
  --trigger=human_request \
  --reason="Dev rollback test" \
  --current-version=NEW_VERSION \
  --previous-version=OLD_VERSION

# 4. Verify rollback success
./scripts/health-check-dev.sh

# 5. Check rollback log
cat _bmad-output/rollback-logs/RB-*.md
```

**Mark as tested:**
```bash
python -m src.brain.promotion_packet mark-tested \
  --packet-id=PROMO-{id} \
  --tested-at=$(date -Iseconds)
```

## Rollback Checklist

- [ ] Rollback triggers documented and understood
- [ ] Safety checks verified (or consciously overridden)
- [ ] No active trades (or documented exception)
- [ ] Data consistency verified
- [ ] Each step verified before proceeding
- [ ] Rollback completed within 5 minutes
- [ ] Post-rollback verification passed
- [ ] Rollback logged with full context
- [ ] Team notified via #incidents
- [ ] Post-mortem scheduled if needed

## Contact Information

- **Primary On-Call:** See PagerDuty rotation
- **Slack Channel:** #incidents
- **Emergency Hotline:** +1-XXX-XXX-XXXX
- **Runbook Owner:** DevOps Team (devops@chiseai.com)
