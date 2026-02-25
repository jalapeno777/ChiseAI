# ACP Rollback Runbook

> **Story:** EP-NS-008  
> **Last Updated:** 2026-02-25  
> **Owner:** Platform Team / On-Call Engineer  
> **Status:** READY FOR USE

---

## 1. Overview

### 1.1 Purpose

This runbook provides **emergency rollback procedures** for the Autonomous Control Plane (ACP). It is designed to be executed under high-pressure situations where rapid response is critical to system stability and safety.

### 1.2 Scope

This runbook covers all ACP components:

| Component | Description | Story ID |
|-----------|-------------|----------|
| Circuit Breaker Registry | Manages circuit breaker states across services | ST-NS-038 |
| Retry Coordinator | Handles retry logic with exponential backoff | ST-NS-039 |
| Self-Healing Engine | Executes automated remediation actions | ST-NS-040 |
| Incident Manager | Coordinates incident detection and response | ST-NS-041 |
| Rollback Coordinator | Manages rollback execution and validation | ST-NS-042 |
| Dashboard Sync | Telemetry and monitoring integration | ST-NS-043 |

### 1.3 Authority

| Role | Can Execute Rollback | Notes |
|------|---------------------|-------|
| On-Call Engineer | ✅ Yes | Primary responder; no additional approval needed for emergency rollback |
| SeniorDev | ✅ Yes | Can execute and approve rollbacks |
| Merlin | ✅ Yes | Can execute rollbacks; must document rationale |
| Captain Craig | ✅ Yes | Final authority; can override any rollback decision |
| Automated Systems | ✅ Conditional | Auto-rollback triggers for ECE >0.15 or P0 safety violations |

**Emergency Override:** Any engineer witnessing a P0 safety violation may execute immediate rollback without waiting for approval.

---

## 2. Emergency Contacts

### 2.1 Escalation Path

```
On-Call Engineer (Primary)
    ↓ (if unresolved in 5 min or needs guidance)
SeniorDev
    ↓ (if complex or cross-team impact)
Merlin
    ↓ (if policy/authority questions)
Captain Craig (Final Authority)
```

### 2.2 Contact Information

| Role | Contact Method | Response SLA |
|------|---------------|--------------|
| On-Call Engineer | PagerDuty → `#platform-oncall` Slack | < 2 minutes |
| SeniorDev | `@seniordev` Slack / Direct Call | < 5 minutes |
| Merlin | `@merlin` Slack / Direct Call | < 10 minutes |
| Captain Craig | `@captain-craig` Slack / Emergency Line | < 15 minutes |

### 2.3 Response SLA

| Metric | Target | Maximum |
|--------|--------|---------|
| Acknowledgment of rollback trigger | < 1 minute | 2 minutes |
| Rollback initiation | < 2 minutes | 5 minutes |
| Rollback completion | < 5 minutes | 10 minutes |
| Post-rollback validation | < 2 minutes | 5 minutes |
| **Total time from trigger to verified rollback** | **< 5 minutes** | **10 minutes** |

---

## 3. Rollback Scenarios

### 3.1 Scenario 1: ECE Degradation (>0.15)

**Trigger:** Expected Calibration Error (ECE) exceeds 0.15

**Indicators:**
- Grafana alert: `acp_ece_score > 0.15`
- Model confidence degradation detected
- Prediction accuracy drop > 15%

**Automatic Actions:**
- System auto-disables autonomy features
- Pages on-call engineer
- Logs incident in incident management system

**Manual Response:**
1. Verify auto-disable occurred: `redis-cli HGET bmad:chiseai:acp:flags autonomy_enabled`
2. If not auto-disabled, execute Section 4.1 (Immediate Actions)
3. Investigate root cause (ML model drift, data quality issues)
4. Document findings in incident ticket

---

### 3.2 Scenario 2: Safety Violations (Any P0)

**Trigger:** Any P0 safety violation detected

**Indicators:**
- Safety monitor alert: P0 severity
- Unauthorized action attempted
- Potential financial or data integrity risk

**Immediate Action:**
- **EXECUTE EMERGENCY STOP IMMEDIATELY** (no approval needed)
- Follow Section 4.1 Step 1

**Post-Stop Actions:**
1. Notify SeniorDev and Merlin within 5 minutes
2. Preserve all logs and state
3. Do NOT re-enable autonomy until root cause identified
4. Schedule post-mortem within 24 hours

---

### 3.3 Scenario 3: Circuit Breaker Storm (>5 open in 1 min)

**Trigger:** More than 5 circuit breakers open within 1 minute

**Indicators:**
- Grafana alert: `circuit_breaker_open_count > 5`
- Multiple services failing simultaneously
- Cascading failure pattern detected

**Automatic Actions:**
- System disables auto-remediation
- Alerts on-call engineer

**Manual Response:**
1. Verify auto-remediation disabled: `redis-cli HGET bmad:chiseai:acp:flags auto_remediation`
2. Check individual circuit breaker states (Section 5.3)
3. Identify root cause service
4. Execute targeted rollback or service restart
5. Re-enable auto-remediation only after stability confirmed

---

### 3.4 Scenario 4: Human Request (Anytime)

**Trigger:** Any authorized human requests rollback

**Authorization:**
- On-call engineer
- SeniorDev
- Merlin
- Captain Craig
- Product owner during business hours

**Response:**
- Execute rollback within 5 minutes of request
- No additional justification required during request
- Document reason post-execution

---

## 4. Step-by-Step Rollback Procedures

### 4.1 Immediate Actions (Within 1 Minute)

#### Step 1: Execute Emergency Stop

```bash
# Method 1: API Emergency Stop (Preferred)
curl -X POST http://localhost:8000/api/v1/emergency-stop \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Emergency manual override - [SCENARIO]",
    "duration_minutes": 60,
    "initiated_by": "[YOUR_NAME]"
  }'

# Expected Response:
# {"status": "success", "message": "Emergency stop activated", "expires_at": "..."}
```

```bash
# Method 2: Redis Direct (If API unavailable)
redis-cli HSET bmad:chiseai:acp:flags emergency_stop true
redis-cli HSET bmad:chiseai:acp:flags emergency_stop_reason "[SCENARIO]"
redis-cli HSET bmad:chiseai:acp:flags emergency_stop_initiated_by "[YOUR_NAME]"
redis-cli HSET bmad:chiseai:acp:flags emergency_stop_expires_at "[TIMESTAMP+60MIN]"
```

#### Step 2: Disable All Autonomy Features

```bash
# Disable all ACP feature flags
redis-cli HSET bmad:chiseai:acp:flags circuit_breaker_auto false
redis-cli HSET bmad:chiseai:acp:flags self_healing_enabled false
redis-cli HSET bmad:chiseai:acp:flags auto_remediation false
redis-cli HSET bmad:chiseai:acp:flags incident_auto_response false
redis-cli HSET bmad:chiseai:acp:flags rollback_auto_execute false

# Verify all flags are disabled
redis-cli HGETALL bmad:chiseai:acp:flags
```

#### Step 3: Open All Circuit Breakers (Protective)

```bash
# Get list of all services
curl -X GET http://localhost:8000/api/v1/circuit-breakers \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.services[].name'

# Force open each service circuit breaker
for service in $(curl -s http://localhost:8000/api/v1/circuit-breakers -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.services[].name'); do
  curl -X POST "http://localhost:8000/api/v1/circuit-breakers/${service}/force-open" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"reason\": \"Emergency rollback - protective open\"}"
done
```

---

### 4.2 Verification Steps (Within 2 Minutes)

#### Verify Emergency Stop Active

```bash
# Check emergency stop status
curl -X GET http://localhost:8000/api/v1/emergency-stop/status \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: {"active": true, "reason": "...", "expires_at": "..."}
```

#### Verify Feature Flags Disabled

```bash
# All critical flags should show "false"
redis-cli HGET bmad:chiseai:acp:flags circuit_breaker_auto
redis-cli HGET bmad:chiseai:acp:flags self_healing_enabled
redis-cli HGET bmad:chiseai:acp:flags auto_remediation
redis-cli HGET bmad:chiseai:acp:flags incident_auto_response
```

#### Verify Circuit Breakers Open

```bash
# Check circuit breaker states
curl -X GET http://localhost:8000/api/v1/circuit-breakers \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.services[] | select(.state == "OPEN") | .name'

# Expected: All service names listed (all should be OPEN)
```

---

### 4.3 Post-Rollback Validation (Within 5 Minutes)

#### System Health Check

```bash
# 1. Check control plane health
curl http://localhost:8000/health

# Expected: {"status": "healthy", "emergency_stop": true, ...}

# 2. Verify no active healing operations
curl http://localhost:8000/api/v1/healing?status=active \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: {"count": 0, "operations": []}

# 3. Verify no auto-remediation in progress
curl http://localhost:8000/api/v1/incidents?status=remediating \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Expected: {"count": 0, "incidents": []}
```

#### Metrics Validation

```bash
# Check ACP metrics in Grafana
echo "Verify in Grafana: https://grafana.chiseai.com/d/acp-overview"
echo "Expected:"
echo "  - autonomy_enabled = 0"
echo "  - circuit_breaker_auto = 0"
echo "  - self_healing_enabled = 0"
echo "  - active_healing_operations = 0"
```

#### Log Verification

```bash
# Check rollback coordinator logs
kubectl logs -n chiseai -l app=autonomous-control-plane --tail=50 | grep -i "rollback\|emergency\|disable"

# Look for:
# - "Emergency stop activated"
# - "Feature flags disabled"
# - "Circuit breakers forced open"
```

---

## 5. Command Reference

### 5.1 Redis Commands to Disable Feature Flags

```bash
# Disable all autonomy features
redis-cli HSET bmad:chiseai:acp:flags circuit_breaker_auto false
redis-cli HSET bmad:chiseai:acp:flags self_healing_enabled false
redis-cli HSET bmad:chiseai:acp:flags auto_remediation false
redis-cli HSET bmad:chiseai:acp:flags incident_auto_response false
redis-cli HSET bmad:chiseai:flags autonomy_enabled false

# Verify all flags
redis-cli HGETALL bmad:chiseai:acp:flags

# Set emergency stop with TTL (3600 seconds = 1 hour)
redis-cli HSET bmad:chiseai:acp:flags emergency_stop true EX 3600

# Check individual flag
redis-cli HGET bmad:chiseai:acp:flags self_healing_enabled
```

### 5.2 API Commands for Emergency Stop

```bash
# Activate emergency stop
curl -X POST http://localhost:8000/api/v1/emergency-stop \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "[REASON]",
    "duration_minutes": 60,
    "initiated_by": "[NAME]"
  }'

# Check emergency stop status
curl -X GET http://localhost:8000/api/v1/emergency-stop/status \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Extend emergency stop
curl -X POST http://localhost:8000/api/v1/emergency-stop/extend \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"additional_minutes": 30}'

# Lift emergency stop (use with caution!)
curl -X POST http://localhost:8000/api/v1/emergency-stop/lift \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "[REASON]",
    "approved_by": "[NAME]"
  }'
```

### 5.3 Circuit Breaker Commands

```bash
# List all circuit breakers
curl -X GET http://localhost:8000/api/v1/circuit-breakers \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Get specific circuit breaker status
curl -X GET "http://localhost:8000/api/v1/circuit-breakers/{service_name}" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Force open a circuit breaker
curl -X POST "http://localhost:8000/api/v1/circuit-breakers/{service_name}/force-open" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "[REASON]"}'

# Force close a circuit breaker (use with caution)
curl -X POST "http://localhost:8000/api/v1/circuit-breakers/{service_name}/force-close" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "[REASON]", "approved_by": "[NAME]"}'

# Reset circuit breaker to automatic
curl -X POST "http://localhost:8000/api/v1/circuit-breakers/{service_name}/reset" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "[REASON]"}'
```

### 5.4 Rollback Execution Commands

```bash
# Execute emergency rollback
curl -X POST http://localhost:8000/api/v1/rollback \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_state": "last_known_good",
    "force": true,
    "reason": "[REASON]",
    "initiated_by": "[NAME]"
  }'

# Execute rollback to specific checkpoint
curl -X POST http://localhost:8000/api/v1/rollback \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_state": "checkpoint_20260225_120000",
    "force": true,
    "reason": "[REASON]",
    "initiated_by": "[NAME]"
  }'

# Get rollback status
curl -X GET "http://localhost:8000/api/v1/rollback/{rollback_id}/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 5.5 Commands to Verify Rollback Success

```bash
# 1. Verify emergency stop is active
curl -s http://localhost:8000/api/v1/emergency-stop/status \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.active'
# Expected: true

# 2. Verify no active healing
curl -s "http://localhost:8000/api/v1/healing?status=active" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.count'
# Expected: 0

# 3. Verify all circuit breakers open
curl -s http://localhost:8000/api/v1/circuit-breakers \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '[.services[] | select(.state == "OPEN")] | length'
# Expected: Number should match total services

# 4. Verify feature flags
echo "circuit_breaker_auto: $(redis-cli HGET bmad:chiseai:acp:flags circuit_breaker_auto)"
echo "self_healing_enabled: $(redis-cli HGET bmad:chiseai:acp:flags self_healing_enabled)"
echo "auto_remediation: $(redis-cli HGET bmad:chiseai:acp:flags auto_remediation)"
# Expected: All should be "false"

# 5. Check system health
curl -s http://localhost:8000/health | jq '.status'
# Expected: "healthy"
```

---

## 6. Verification Checklist

### 6.1 Pre-Rollback Checks

Before executing rollback, confirm:

- [ ] **Scenario identified**: Which rollback scenario applies (Section 3)
- [ ] **Authority confirmed**: You are authorized to execute rollback (Section 1.3)
- [ ] **Communication initiated**: Relevant stakeholders notified (Section 7)
- [ ] **Evidence preserved**: Screenshots/logs of current state captured
- [ ] **Rollback scope defined**: Full vs. partial rollback determined

### 6.2 During-Rollback Checks

Execute and verify each step:

- [ ] **Step 1**: Emergency stop activated (Section 4.1)
- [ ] **Step 2**: All feature flags disabled (Section 4.1)
- [ ] **Step 3**: Circuit breakers opened (Section 4.1)
- [ ] **Verification**: Emergency stop confirmed active
- [ ] **Verification**: Feature flags confirmed disabled
- [ ] **Verification**: Circuit breakers confirmed open

### 6.3 Post-Rollback Checks

After rollback completion, verify:

- [ ] **Health check**: Control plane health endpoint returns healthy
- [ ] **No active healing**: Zero active healing operations
- [ ] **No auto-remediation**: Zero auto-remediation in progress
- [ ] **Metrics validated**: Grafana shows autonomy disabled
- [ ] **Logs reviewed**: Rollback logs show successful execution
- [ ] **Stakeholders notified**: Rollback completion communicated (Section 7)
- [ ] **Incident documented**: Rollback reason and actions logged
- [ ] **Monitoring active**: System being watched for stability

---

## 7. Communication Plan

### 7.1 Who to Notify

| Stakeholder | When to Notify | Method |
|-------------|----------------|--------|
| On-Call Engineer | Immediately | PagerDuty alert auto-triggers |
| SeniorDev | Within 5 min of rollback | Slack `@seniordev` |
| Merlin | Within 10 min of rollback | Slack `@merlin` |
| Captain Craig | Within 15 min for P0/P1 | Slack `@captain-craig` + call |
| #platform-oncall | Immediately | Slack channel |
| #incidents | Within 5 min | Slack channel |
| Product Team | Within 30 min (business hours) | Slack #product |

### 7.2 What to Communicate

**Initial Notification (Immediate):**
```
🚨 ACP ROLLBACK EXECUTED

Scenario: [ECE/Safety/CB Storm/Human Request]
Initiated by: [Name]
Time: [Timestamp]
Reason: [Brief description]

Status: Rollback in progress
Impact: Autonomy features disabled, circuit breakers open

Updates to follow in #incidents
```

**Completion Notification (Within 5 min):**
```
✅ ACP ROLLBACK COMPLETE

Rollback ID: [ID]
Completion Time: [Timestamp]

Verification Results:
- Emergency stop: ACTIVE
- Feature flags: DISABLED
- Circuit breakers: OPEN
- System health: HEALTHY

Next Steps:
- Monitoring for stability
- Root cause investigation in progress
- ETA for re-enablement: TBD

Incident ticket: [LINK]
```

### 7.3 When to Escalate

| Condition | Escalate To | Timeframe |
|-----------|-------------|-----------|
| Rollback fails to complete | SeniorDev + Merlin | Immediate |
| System unstable after rollback | SeniorDev + Captain Craig | Within 5 min |
| P0 safety violation involved | Captain Craig | Immediate |
| Multiple rollback attempts needed | Merlin + Captain Craig | Within 10 min |
| Rollback reason unclear | SeniorDev | Within 15 min |
| Re-enablement decision needed | Merlin | When stable |

---

## 8. Post-Rollback Procedures

### 8.1 Immediate Post-Rollback (0-30 min)

1. **Monitor system stability**
   - Watch Grafana dashboard for anomalies
   - Check error rates and latency
   - Verify no cascading failures

2. **Preserve evidence**
   - Save all relevant logs
   - Capture metrics snapshots
   - Document timeline of events

3. **Begin root cause analysis**
   - Identify what triggered the rollback
   - Review recent changes/deployments
   - Check for correlation with alerts

### 8.2 Short-Term Follow-Up (30 min - 4 hours)

1. **Update incident ticket** with:
   - Rollback execution details
   - Verification results
   - Initial root cause findings

2. **Determine re-enablement timeline**
   - Assess when autonomy can be safely restored
   - Plan gradual re-enablement if appropriate
   - Get approval from Merlin or Captain Craig

3. **Communicate updates** every 30 minutes to stakeholders

### 8.3 Long-Term Follow-Up (4-24 hours)

1. **Complete root cause analysis**
2. **Schedule post-mortem** for P0/P1 incidents
3. **Update runbooks** if gaps identified
4. **Plan preventive measures** to avoid recurrence

---

## 9. Re-Enablement Procedures

### 9.1 When to Re-Enable

**DO NOT re-enable autonomy until:**
- [ ] Root cause identified and addressed
- [ ] System stable for minimum 30 minutes
- [ ] SeniorDev or Merlin approval obtained
- [ ] Rollback triggers no longer active
- [ ] Monitoring confirmed operational

### 9.2 Gradual Re-Enablement Steps

```bash
# Step 1: Lift emergency stop
curl -X POST http://localhost:8000/api/v1/emergency-stop/lift \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Root cause addressed, system stable",
    "approved_by": "[NAME]"
  }'

# Step 2: Enable circuit breaker automation
redis-cli HSET bmad:chiseai:acp:flags circuit_breaker_auto true

# Step 3: Wait 5 minutes, monitor for stability
# Check Grafana dashboard

# Step 4: Enable incident auto-response
redis-cli HSET bmad:chiseai:acp:flags incident_auto_response true

# Step 5: Wait 5 minutes, monitor for stability

# Step 6: Enable auto-remediation
redis-cli HSET bmad:chiseai:acp:flags auto_remediation true

# Step 7: Wait 5 minutes, monitor for stability

# Step 8: Enable self-healing
redis-cli HSET bmad:chiseai:acp:flags self_healing_enabled true

# Step 9: Final verification
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/circuit-breakers
```

### 9.3 Re-Enablement Verification

After each step:
- [ ] No new alerts triggered
- [ ] Error rates remain stable
- [ ] Circuit breakers functioning normally
- [ ] No unexpected healing operations initiated

---

## 10. References

### 10.1 Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| EP-NS-008 Promotion Packet | `docs/promotion/EP-NS-008-canary-close-packet.md` | Promotion approval and evidence |
| ACP General Runbook | `docs/runbooks/autonomous_control_plane.md` | General operational procedures |
| ACP Batch 2 Outcomes | `docs/runbooks/acp-canary-batch2-outcomes.md` | Canary testing results |
| Incident Response | `docs/runbooks/incident_response.md` | General incident procedures |
| Kill Switch Runbook | `docs/runbooks/kill-switch-trigger.md` | Emergency kill procedures |

### 10.2 External Resources

- **Grafana Dashboard**: https://grafana.chiseai.com/d/acp-overview
- **Grafana ACP Details**: https://grafana.chiseai.com/d/autonomous-healing
- **PagerDuty**: https://chiseai.pagerduty.com
- **Incident Management**: [Internal tool URL]

### 10.3 Component Source Code

| Component | Source Location |
|-----------|-----------------|
| Circuit Breaker Registry | `src/autonomous_control_plane/components/circuit_breaker_registry.py` |
| Retry Coordinator | `src/autonomous_control_plane/components/retry_coordinator.py` |
| Self-Healing Engine | `src/autonomous_control_plane/components/self_healing_engine.py` |
| Incident Manager | `src/autonomous_control_plane/components/incident_manager.py` |
| Rollback Coordinator | `src/autonomous_control_plane/components/rollback_coordinator.py` |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-25 | SeniorDev | Initial runbook creation |

---

*This runbook was created per EP-NS-008 promotion packet requirements and is ready for operational use.*
