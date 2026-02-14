# Chise v1 Rollback Procedures

## Overview

This document provides detailed rollback procedures for the Chise v1 brain system. Rollbacks are designed to be executed in **less than 5 minutes** with comprehensive safety checks.

## Rollback Triggers

The following conditions can trigger an automatic or manual rollback:

| Trigger | Threshold | Description |
|---------|-----------|-------------|
| ECE_DEGRADATION | > 0.15 | Expected Calibration Error exceeds threshold |
| WIN_RATE_DROP | Configurable | Win rate drops below baseline by threshold amount |
| MAX_DRAWDOWN_BREACH | Configurable | Maximum drawdown exceeds threshold |
| SAFETY_VIOLATION | Any | Safety constraints violated |
| HUMAN_REQUEST | N/A | Manual rollback request |

## Pre-Rollback State Verification

Before any rollback is executed, the following checks are performed:

### 1. No Active Trades
```bash
# Check for active trades
chise-trader status --active-trades
# Expected: 0 active trades
```

**Safety Consideration:** Rolling back with active trades can result in:
- Orphaned positions
- Inconsistent state between old and new versions
- Loss of trade tracking

### 2. Data Consistency Check
```bash
# Verify data consistency
chise-validate data --consistency-check
# Expected: "Data consistency: OK"
```

**Safety Consideration:** Inconsistent data may lead to:
- Corrupted backtest results
- Incorrect position calculations
- Failed strategy validations

### 3. Target Version Verification
```bash
# Verify target version exists
chise-version list --available
# Expected: Target version in list
```

**Safety Consideration:** Rolling to non-existent version will fail.

## Step-by-Step Rollback Procedure

### Standard Rollback (5 steps, target: <5 minutes)

#### Step 1: Stop Active Trading (Target: 30 seconds)
```bash
# Command
systemctl stop chise-trader

# Verification
systemctl status chise-trader

# Expected Result
# Active: inactive (dead)
```

**Safety Check:** Ensure all orders are cancelled before proceeding.

#### Step 2: Backup Current State (Target: 60 seconds)
```bash
# Command
chise-backup create --tag pre-rollback-$(date +%Y%m%d-%H%M%S)

# Verification
chise-backup list --latest

# Expected Result
# Backup created: pre-rollback-YYYYMMDD-HHMMSS
```

**Safety Check:** Verify backup size and integrity.

#### Step 3: Switch to Target Version (Target: 60 seconds)
```bash
# Command
chise-version switch <target_version>

# Verification
chise-version current

# Expected Result
# Current version: <target_version>
```

**Safety Check:** Confirm version is in registry and stable.

#### Step 4: Verify Version (Target: 30 seconds)
```bash
# Command
chise-version verify --full

# Verification
chise-health check

# Expected Result
# Version: <target_version>
# Status: healthy
# All checks passed
```

**Safety Check:** Run full health check before starting services.

#### Step 5: Restart Services (Target: 60 seconds)
```bash
# Command
systemctl start chise-trader

# Verification
systemctl status chise-trader
chise-health check --trader

# Expected Result
# Active: active (running)
# Trader health: OK
```

**Safety Check:** Monitor for errors in first 30 seconds.

## Emergency Rollback (--force)

In emergency situations, use the `--force` flag to bypass some safety checks:

```python
handler.emergency_rollback(
    target_version="v1.2.3",
    force=True
)
```

### Force Bypasses:
- Active trades check (logs warning)
- Data consistency check (logs warning)

### Force Does NOT Bypass:
- Target version existence check
- Backup creation
- Step verification

### When to Use Force:
- System is in critical failure state
- Safety violation requires immediate action
- Human judgment overrides automated checks

### When NOT to Use Force:
- Normal maintenance rollback
- Non-critical version switch
- When time permits full verification

## Pause/Resume Support

If a rollback fails mid-process, it can be resumed:

```python
# Resume from step 3
result = handler.execute_rollback(
    target_version="v1.2.3",
    steps=rollback_steps,
    resume_from=3
)
```

## Post-Mortem Reporting

After any rollback, generate a post-mortem report:

```python
report = handler.generate_postmortem(
    trigger=RollbackTrigger.ECE_DEGRADATION,
    result=rollback_result,
    root_cause_analysis="ECE degraded due to market regime change",
    metadata={
        "market_conditions": "high_volatility",
        "affected_strategies": ["grid_btc", "grid_eth"],
    }
)

# Export to JSON
json_report = report.to_json()

# Export to Markdown
markdown_report = report.to_markdown()
```

## Rollback Time Budget

| Phase | Target Time | Max Time |
|-------|-------------|----------|
| Pre-rollback validation | 30s | 60s |
| Step 1: Stop trading | 30s | 60s |
| Step 2: Backup state | 60s | 120s |
| Step 3: Switch version | 60s | 120s |
| Step 4: Verify version | 30s | 60s |
| Step 5: Restart services | 60s | 120s |
| **Total** | **<5 min** | **<10 min** |

## Safety Considerations

### Data Safety
- Always create backup before rollback
- Verify backup integrity before proceeding
- Keep backups for 7 days minimum

### Trading Safety
- Never rollback with active positions unless emergency
- Cancel all pending orders before rollback
- Verify no open orders after trader restart

### System Safety
- Run health checks after each step
- Monitor logs for errors
- Have rollback-of-rollback plan ready

### Human Safety
- Require two-person approval for force rollback
- Document all rollback decisions
- Review post-mortem within 24 hours

## Rollback Checklist

Before initiating rollback:
- [ ] Verify rollback trigger is valid
- [ ] Confirm target version is stable
- [ ] Check no critical operations in progress
- [ ] Notify team of rollback
- [ ] Ensure backup storage available

During rollback:
- [ ] Monitor each step completion
- [ ] Verify checkpoint after each step
- [ ] Log any warnings or errors
- [ ] Track actual vs target time

After rollback:
- [ ] Verify system health
- [ ] Check all services running
- [ ] Validate trading can resume
- [ ] Generate post-mortem report
- [ ] Update incident log
- [ ] Schedule root cause review

## Contact Information

For rollback assistance:
- On-call engineer: #incidents channel
- Brain team lead: brain-team@chise.ai
- Emergency hotline: See runbook

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-14 | Initial rollback procedures |
