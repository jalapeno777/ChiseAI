# Rollback Plan: vNext-A (1.1.0-vnexta)

**Plan ID:** ROLLBACK-BRAIN-CICD-2026-03-01  
**Story ID:** BRAIN-CICD-2026-03-01  
**Brain Version:** vNext-A (1.1.0-vnexta)  
**Rollback Target:** vCurrent (1.0.0)  
**Created:** 2026-03-01  
**Last Updated:** 2026-03-01

---

## Overview

This document provides the detailed rollback procedure for reverting from vNext-A back to vCurrent in case of issues during or after promotion.

**Estimated Rollback Time:** 5 minutes  
**Tested in Dev Environment:** Yes  
**Last Tested:** 2026-03-01

---

## Trigger Conditions

### Automatic Triggers

The following conditions will trigger an automatic rollback:

| Condition | Threshold | Severity |
|-----------|-----------|----------|
| High False Positive Rate | > 0.30 for 3 consecutive evaluations | WARNING |
| Low Paper Carryover | Proxy < 30% | WARNING |
| Safety Violation | safety_compliance < 1.0 | CRITICAL |
| Elevated Turnover | > 20 trades/day sustained | INFO |

### Manual Triggers

- Human request via emergency rollback command
- Business decision to revert
- Unforeseen issues not captured by automatic triggers

---

## Rollback Steps

### Pre-Rollback Checklist

- [ ] Confirm rollback is necessary
- [ ] Notify team via #brain-cicd channel
- [ ] Document reason for rollback
- [ ] Ensure vCurrent artifacts are available

### Step 1: Stop Candidate Generation

**Objective:** Prevent new candidates from being generated during rollback.

**Command:**
```bash
python scripts/brain_control.py stop --env=paper
```

**Verification:**
```bash
python scripts/brain_control.py status --env=paper
```

**Expected Result:**
```
Status: STOPPED
Environment: paper
Current Version: vNext-A (1.1.0-vnexta)
```

**Estimated Time:** 30 seconds

**Troubleshooting:**
- If stop command fails, check process status: `ps aux | grep brain`
- Force kill if necessary: `pkill -f brain_control`

---

### Step 2: Verify No Active Orders [REQUIRES CONFIRMATION]

**Objective:** Ensure no orders are in flight before switching versions.

**Command:**
```bash
python scripts/order_monitor.py count --status=active
```

**Verification:**
```bash
python scripts/order_monitor.py list --status=active
```

**Expected Result:**
```
Active Orders: 0
```

**Estimated Time:** 15 seconds

**Decision Point:**
- If active orders == 0: Proceed to Step 3
- If active orders > 0: 
  - Wait for orders to complete, OR
  - Cancel orders: `python scripts/order_monitor.py cancel --all`

---

### Step 3: Switch to vCurrent BrainSpec [REQUIRES CONFIRMATION]

**Objective:** Activate the previous brain version.

**Command:**
```bash
python scripts/brain_version.py activate --version=vCurrent --env=paper
```

**Verification:**
```bash
python scripts/brain_version.py get-active --env=paper
```

**Expected Result:**
```
Active Brain Version: vCurrent (1.0.0)
Environment: paper
Activated At: 2026-03-01T14:20:00Z
```

**Estimated Time:** 60 seconds

**Troubleshooting:**
- If activation fails, check version availability: `python scripts/brain_version.py list`
- Ensure vCurrent artifacts exist in `_bmad-output/brain/versions/`

---

### Step 4: Verify Data Consistency

**Objective:** Ensure data integrity after version switch.

**Command:**
```bash
python scripts/consistency_check.py --brain-version=vCurrent
```

**Verification:**
```bash
python scripts/consistency_check.py --verify
```

**Expected Result:**
```
Consistency Check: PASS
Data Integrity: VERIFIED
Version: vCurrent (1.0.0)
```

**Estimated Time:** 120 seconds

**Troubleshooting:**
- If consistency check fails:
  - Review error logs: `cat logs/consistency_check.log`
  - Run repair if available: `python scripts/consistency_check.py --repair`
  - Escalate to data team if unresolved

---

### Step 5: Resume Candidate Generation

**Objective:** Restart brain with vCurrent version.

**Command:**
```bash
python scripts/brain_control.py start --env=paper --version=vCurrent
```

**Verification:**
```bash
python scripts/brain_control.py status --env=paper
```

**Expected Result:**
```
Status: RUNNING
Environment: paper
Current Version: vCurrent (1.0.0)
Uptime: 0m 10s
```

**Estimated Time:** 30 seconds

**Troubleshooting:**
- If start fails, check logs: `tail -f logs/brain_control.log`
- Verify configuration: `python scripts/brain_control.py config --validate`

---

## Post-Rollback Actions

### Immediate Actions (Within 5 minutes)

1. **Verify System Health**
   ```bash
   python scripts/health_check.py --env=paper
   ```

2. **Confirm vCurrent is Active**
   ```bash
   python scripts/brain_version.py get-active --env=paper
   ```

3. **Check Candidate Generation**
   ```bash
   python scripts/brain_control.py status --env=paper
   ```

### Documentation Actions (Within 30 minutes)

1. **Log Rollback Event**
   ```bash
   python scripts/log_event.py \
     --type=ROLLBACK \
     --story-id=BRAIN-CICD-2026-03-01 \
     --from-version=vNext-A \
     --to-version=vCurrent \
     --reason="[Document reason]"
   ```

2. **Update Iterlog**
   - Add entry to `docs/tempmemories/iterlog-BRAIN-CICD-2026-03-01.md`
   - Include timestamp, reason, and outcome

3. **Notify Stakeholders**
   - Post in #brain-cicd channel
   - Tag relevant team members
   - Include rollback reason and current status

### Analysis Actions (Within 24 hours)

1. **Preserve vNext-A Artifacts**
   ```bash
   python scripts/preserve_artifacts.py \
     --version=vNext-A \
     --story-id=BRAIN-CICD-2026-03-01 \
     --reason=rollback
   ```

2. **Schedule Post-Mortem**
   - Create post-mortem document
   - Schedule team review meeting
   - Identify lessons learned

3. **Plan vNext-B Design Review**
   - Schedule design review meeting
   - Address issues that caused rollback
   - Update BrainSpec accordingly

---

## Rollback Testing

### Dev Environment Testing

The rollback procedure has been tested in the dev environment:

| Test Case | Result | Date |
|-----------|--------|------|
| Normal rollback | ✅ PASS | 2026-03-01 |
| Rollback with active orders | ✅ PASS | 2026-03-01 |
| Rollback after consistency failure | ✅ PASS | 2026-03-01 |
| Emergency rollback | ✅ PASS | 2026-03-01 |

### Test Commands

To test the rollback procedure in dev:

```bash
# Test normal rollback
python scripts/test_rollback.py --scenario=normal --env=dev

# Test rollback with active orders
python scripts/test_rollback.py --scenario=with-orders --env=dev

# Test emergency rollback
python scripts/test_rollback.py --scenario=emergency --env=dev
```

---

## Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| Primary On-Call | #brain-cicd channel | Immediate |
| Engineering Lead | [Lead Name] | If unresolved in 15 min |
| Product Owner | [PO Name] | If business impact |

---

## Related Documents

- [Promotion Packet](../docs/promotion/BRAIN-CICD-2026-03-01-promotion-packet.md)
- [Decision Log](./decision-log.json)
- [BrainSpec vNext-A](../docs/brain/BrainSpec-vNext-A.md)
- [BrainSpec vCurrent](../docs/brain/BrainSpec-vCurrent.md)

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-03-01 | 1.0 | Initial rollback plan | system |

---

*This rollback plan is part of Brain CI/CD Cycle #1 (Batch 5).*
