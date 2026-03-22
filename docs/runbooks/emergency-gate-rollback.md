# Emergency Gate Rollback Runbook

## Overview

This runbook provides procedures for emergency rollback of blocking CI gates. The emergency gate disable mechanism allows authorized personnel to temporarily bypass all blocking gates in the CI pipeline during critical incidents.

**⚠️ WARNING**: This is an emergency mechanism. Use only when absolutely necessary and ensure gates are restored as soon as possible.

---

## When to Use Emergency Gate Disable

### Valid Use Cases

| Scenario | Justification |
|----------|---------------|
| Critical production bug requiring immediate hotfix | Gates may block urgent fixes; disable temporarily |
| Security vulnerability requiring immediate patching | Security takes precedence over process |
| CI infrastructure failure blocking all builds | Gates themselves may be the problem |
| False positive blocking critical path | Known issue with gate, fix in progress |
| Emergency data recovery operation | Time-sensitive recovery operations |

### Invalid Use Cases (Do NOT Disable)

- Regular feature development
- Convenience or impatience
- Avoiding known test failures
- Bypassing code review requirements
- Non-urgent fixes

---

## Decision Criteria

Before disabling gates, ALL of the following must be true:

1. **Urgency**: The issue requires resolution within 1 hour
2. **Impact**: The issue affects production or critical infrastructure
3. **Risk Assessment**: The risk of disabling gates is lower than the risk of waiting
4. **Approval**: Emergency change approval obtained (see below)
5. **Timeline**: Clear timeline for restoration (max 24 hours)

### Approval Requirements

| Severity | Approver | Documentation |
|----------|----------|---------------|
| P0 (Critical) | On-call SRE + Engineering Lead | Incident ticket required |
| P1 (High) | Engineering Lead | Change record required |
| P2 (Medium) | Senior Engineer | Email/Slack record acceptable |

---

## Step-by-Step Procedures

### 1. Pre-Disable Checklist

Before disabling gates, complete the following:

- [ ] Incident ticket created and assigned
- [ ] On-call SRE notified (for P0/P1)
- [ ] Engineering Lead approval obtained
- [ ] Reason documented in incident ticket
- [ ] Estimated restoration time communicated
- [ ] Team notified in #incidents Slack channel

### 2. Disabling Gates

Run the emergency disable script:

```bash
python3 scripts/ci/emergency_gate_disable.py \
    --disable \
    --reason "INCIDENT-123: Critical payment processing bug" \
    --user $(whoami)
```

**Verify the disable worked:**

```bash
python3 scripts/ci/emergency_gate_disable.py --status
```

Expected output:
```
STATUS: BLOCKING GATES ARE DISABLED
  Disabled at: 2026-03-17T03:59:22.264752+00:00
  Disabled by: your-username
  Reason: INCIDENT-123: Critical payment processing bug
  Auto-expires in: 604795 seconds (167 hours)
```

### 3. During Gate Disable Period

While gates are disabled:

1. **Monitor closely**: Watch CI pipelines for any issues
2. **Communicate**: Post updates every 30 minutes in #incidents
3. **Document**: Record all changes made during the disable period
4. **Limit scope**: Only merge the specific fix, no unrelated changes

### 4. Restoring Gates

**⚠️ CRITICAL**: Gates auto-expire after 7 days, but should be restored ASAP.

After the fix is deployed:

```bash
python3 scripts/ci/emergency_gate_disable.py \
    --restore \
    --reason "INCIDENT-123: Payment bug fixed, gates restored" \
    --user $(whoami)
```

**Verify restoration:**

```bash
python3 scripts/ci/emergency_gate_disable.py --status
```

Expected output:
```
STATUS: All blocking gates are ENABLED
```

### 5. Post-Rollback Actions

Within 24 hours of restoration:

- [ ] Close incident ticket with resolution notes
- [ ] Schedule post-mortem (required for P0/P1)
- [ ] Review audit log: `python3 scripts/ci/emergency_gate_disable.py --audit-log`
- [ ] Update runbook if procedures were unclear
- [ ] Notify team that gates are restored

---

## Audit and Compliance

### Audit Log

All disable/restore actions are logged to Redis:

```bash
# View recent audit log
python3 scripts/ci/emergency_gate_disable.py --audit-log

# View last 50 entries
python3 scripts/ci/emergency_gate_disable.py --audit-log --limit 50
```

### Log Retention

- Audit logs retained for 90 days
- Gate disable keys auto-expire after 7 days
- Manual backup recommended for compliance audits

### Required Documentation

For each emergency disable:

1. **Incident ticket** with:
   - Timeline of events
   - Decision rationale
   - Approvals obtained
   - Changes made during disable period

2. **Change record** (for P1+) with:
   - Pre-change state
   - Change description
   - Post-change verification
   - Rollback procedure

---

## Troubleshooting

### Cannot Connect to Redis

If you see:
```
ERROR: Could not connect to Redis
```

**Solutions:**
1. Check Redis is running: `redis-cli -h host.docker.internal -p 6380 PING`
2. Verify environment variables: `echo $REDIS_HOST $REDIS_PORT`
3. Try localhost: `REDIS_HOST=localhost python3 scripts/ci/emergency_gate_disable.py --status`

### Script Fails to Disable

If disable appears to succeed but status shows gates enabled:

1. Check Redis permissions
2. Verify you're connecting to the correct Redis instance
3. Check if another process is resetting the key

### Accidental Disable

If gates were disabled by mistake:

1. **Do not panic** - gates auto-expire in 7 days
2. Restore immediately: `python3 scripts/ci/emergency_gate_disable.py --restore --reason "Accidental disable, immediate restore"`
3. Document in incident ticket
4. Review access controls

---

## Contact Information

### Escalation Path

| Level | Contact | When to Escalate |
|-------|---------|------------------|
| L1 | On-call SRE | Cannot disable/restore gates |
| L2 | Engineering Lead | Dispute over gate disable necessity |
| L3 | VP Engineering | Policy violation or repeated issues |

### Emergency Contacts

- **On-call SRE**: Check PagerDuty rotation
- **Engineering Lead**: engineering-lead@chiseai.com
- **VP Engineering**: vp-eng@chiseai.com
- **#incidents Slack**: https://chiseai.slack.com/archives/incidents

---

## Related Documentation

- [CI Gate System](./checkpoint-gates.md)
- [Incident Response](./incident_response.md)
- [Emergency Merge Override](../.opencode/command/chise-emergency-merge-override.md)
- [Redis Failure Response](./redis-failure-response.md)

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-16 | senior-dev | Initial runbook creation |

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│           EMERGENCY GATE DISABLE - QUICK REF                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CHECK STATUS:                                              │
│  python3 scripts/ci/emergency_gate_disable.py --status      │
│                                                             │
│  DISABLE GATES:                                             │
│  python3 scripts/ci/emergency_gate_disable.py \             │
│      --disable --reason "INCIDENT-XXX: description"         │
│                                                             │
│  RESTORE GATES:                                             │
│  python3 scripts/ci/emergency_gate_disable.py \             │
│      --restore --reason "INCIDENT-XXX: resolved"            │
│                                                             │
│  VIEW AUDIT LOG:                                            │
│  python3 scripts/ci/emergency_gate_disable.py --audit-log   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  REMEMBER:                                                  │
│  • Gates auto-expire after 7 days                           │
│  • All actions are logged                                   │
│  • Approval required for P0/P1                              │
│  • Restore ASAP after fix                                   │
└─────────────────────────────────────────────────────────────┘
```
