---
title: Incident Response Runbook
category: incident-response
severity: critical
estimated_time_to_resolve: 15-120 minutes
last_updated: 2026-02-22
maintainers: ops-team, platform-team, leadership
story_id: ST-LAUNCH-021
executable: true
steps:
  - name: "Check incident status"
    command: "curl -s http://localhost:8001/api/v1/incidents/active | jq 'length'"
  - name: "Verify alert channels"
    command: "curl -s http://localhost:8001/api/v1/alerts/channels/status | jq -r '.status'"
    verify: "operational"
  - name: "Check on-call schedule"
    command: "curl -s http://localhost:8001/api/v1/oncall/current | jq -r '.engineer'"
  - name: "Run incident classification"
    command: "python3 scripts/ops/validate_runbooks.py --scenario incident --check classification"
  - name: "Verify escalation paths"
    command: "curl -s http://localhost:8001/api/v1/incidents/escalation-paths | jq '.paths | length'"
---

# Incident Response Runbook

> **Story:** ST-LAUNCH-021  
> **Last Updated:** 2026-02-22  
> **Owner:** Platform Operations Team  
> **Alert Acknowledgment SLA:** < 15 minutes  
> **Response SLA:** Varies by severity (see Section 1)

---

## Overview

This runbook provides comprehensive procedures for incident management at ChiseAI, including classification, escalation, recovery, communication, post-mortem processes, and on-call procedures. All team members must be familiar with this runbook.

## Prerequisites

Before responding to incidents using this runbook, ensure you have:

- [ ] Access to the incident management system (API at localhost:8001)
- [ ] PagerDuty access and acknowledgment permissions
- [ ] Slack access with permissions to post in #incidents channel
- [ ] curl command-line tool for API interactions
- [ ] jq JSON processor for parsing responses
- [ ] Access to Grafana dashboards for monitoring
- [ ] Docker CLI access for service management
- [ ] Authorization tokens for protected API endpoints
- [ ] Contact information for escalation contacts (Engineering Manager, VP Engineering, CTO)
- [ ] Knowledge of current on-call schedule and rotation

---

## 1. Incident Classification

### 1.1 Severity Levels (P0-P3)

**P0 - CRITICAL (System Down / Major Impact)**

| Criteria | Examples | Response Time | Resolution Target |
|----------|----------|---------------|-------------------|
| Complete system outage | All trading halted | Immediate | 1 hour |
| Critical safety failure | Kill switch failed | Immediate | 30 minutes |
| Security breach | Unauthorized access | Immediate | 2 hours |
| Data corruption | Position data lost | Immediate | 2 hours |
| Financial impact | > $10k at risk | Immediate | 1 hour |

**P1 - HIGH (Major Feature Impaired)**

| Criteria | Examples | Response Time | Resolution Target |
|----------|----------|---------------|-------------------|
| Core feature degraded | Order execution slow | < 15 min | 4 hours |
| Single service down | ML prediction failed | < 15 min | 2 hours |
| Significant data issues | Data delayed > 1 hour | < 15 min | 4 hours |
| Performance degradation | API latency > 5s | < 15 min | 4 hours |
| Kill switch triggered | Safety system active | < 15 min | 1 hour |

**P2 - MEDIUM (Partial Feature Impact)**

| Criteria | Examples | Response Time | Resolution Target |
|----------|----------|---------------|-------------------|
| Non-critical feature broken | Reporting delayed | < 1 hour | 24 hours |
| Minor performance issues | Latency elevated | < 1 hour | 8 hours |
| Single data source issue | One exchange delayed | < 1 hour | 4 hours |
| Monitoring gaps | Metrics missing | < 1 hour | 8 hours |

**P3 - LOW (Minimal Impact / Cosmetic)**

| Criteria | Examples | Response Time | Resolution Target |
|----------|----------|---------------|-------------------|
| UI issues | Dashboard slow | < 4 hours | 72 hours |
| Documentation outdated | Wrong API docs | < 4 hours | 1 week |
| Cosmetic bugs | Wrong colors | < 24 hours | Next sprint |
| Non-urgent improvements | Feature request | N/A | Backlog |

### 1.2 Incident Classification Procedure

**Initial Classification (First 5 minutes):**

```bash
# Use classification helper
curl -X POST http://localhost:8001/api/v1/incidents/classify \
  -H "Content-Type: application/json" \
  -d '{"symptoms": ["trading_halted", "api_unresponsive"], "impact": "all_users", "financial_exposure": "high", "safety_systems_affected": true}'

# Response:
# {"severity": "P0", "reason": "Complete system outage with safety impact", "response_sla": "immediate", "escalation_required": true}
```

**Classification Decision Tree:**

```
Is the system completely down?
├── YES → P0
└── NO → Is a core feature severely impaired?
    ├── YES → P1
    └── NO → Is a non-critical feature broken?
        ├── YES → P2
        └── NO → P3
```

**Reclassification:**
- Severity can be adjusted as more information becomes available
- P0/P1 incidents require manager approval to downgrade
- Document reason for reclassification in incident log

---

## 2. Escalation Procedures

### 2.1 Escalation Matrix

**Who to Contact:**

| Severity | First Contact | Secondary | Escalation 1 | Escalation 2 |
|----------|---------------|-----------|--------------|--------------|
| P0 | On-call Engineer | Engineering Manager | VP Engineering | CTO |
| P1 | On-call Engineer | Team Lead | Engineering Manager | VP Engineering |
| P2 | On-call Engineer | Team Lead | Engineering Manager | - |
| P3 | Ticket System | - | - | - |

**When to Escalate:**

| Condition | Escalate To | Timeframe |
|-----------|-------------|-----------|
| P0 declared | All stakeholders | Immediate |
| P1 not resolved | Engineering Manager | 30 minutes |
| P2 not acknowledged | Team Lead | 2 hours |
| Customer impact reported | Customer Success | 15 minutes |
| Media/regulatory interest | Legal/Comms | Immediate |
| Data breach suspected | Security + Legal | Immediate |

### 2.2 Escalation Contacts

**Engineering Escalation:**

| Level | Name | Primary Contact | Secondary Contact |
|-------|------|-----------------|-------------------|
| On-call | Rotation | PagerDuty | Slack #incidents |
| Team Lead | [Name] | +1-XXX-XXX-XXXX | Slack DMs |
| Engineering Manager | [Name] | +1-XXX-XXX-XXXX | Email |
| VP Engineering | [Name] | +1-XXX-XXX-XXXX | Email |
| CTO | [Name] | +1-XXX-XXX-XXXX | Emergency line |

**Business Escalation:**

| Role | Name | Contact |
|------|------|---------|
| Customer Success Lead | [Name] | +1-XXX-XXX-XXXX |
| Legal Counsel | [Name] | +1-XXX-XXX-XXXX |
| Comms/PR Lead | [Name] | +1-XXX-XXX-XXXX |

### 2.3 Escalation Automation

**PagerDuty Integration:**
```bash
# Trigger PagerDuty escalation
curl -X POST http://localhost:8001/api/v1/incidents/escalate \
  -H "Content-Type: application/json" \
  -d '{"incident_id": "inc-20260222-001", "severity": "P0", "auto_page": true, "escalation_policy": "platform_critical"}'
```

**Slack Notification:**
```bash
# Post to #incidents channel
curl -X POST http://localhost:8001/api/v1/incidents/notify \
  -d '{"channel": "#incidents", "severity": "P1", "message": "Trading latency elevated - investigating"}'
```

---

## 3. Recovery Procedures

### 3.1 System Recovery

**Step 1: Assess Impact**
```bash
# Get system health overview
curl -s http://localhost:8001/api/v1/health | jq '.'

# Check affected services
curl -s http://localhost:8001/api/v1/health/services | jq '.[] | select(.status != "healthy")'

# Estimate affected users
curl -s http://localhost:8001/api/v1/metrics/active-users | jq '.count'
```

**Step 2: Immediate Mitigation**

For P0/P1 incidents, apply immediate mitigation:

```bash
# Option 1: Enable kill switch (if safety at risk)
curl -X POST http://localhost:8001/api/v1/safety/kill-switch/trigger \
  -d '{"reason": "incident_mitigation", "operator_id": "<id>"}'

# Option 2: Enable circuit breaker
curl -X POST http://localhost:8001/api/v1/safety/circuit-breaker/trip \
  -d '{"service": "<affected_service>", "reason": "incident"}'

# Option 3: Redirect traffic
curl -X POST http://localhost:8001/api/v1/traffic/redirect \
  -d '{"from": "<affected>", "to": "<fallback>"}'
```

**Step 3: Apply Fix**

Follow the appropriate runbook for the issue type:
- Service down → Restart service
- Database issue → Check [Database Recovery Runbook]
- Network issue → Check [Network Recovery Runbook]
- Data corruption → Check [Data Recovery Runbook]

**Step 4: Verify Recovery**
```bash
# Run health checks
curl -s http://localhost:8001/api/v1/health | jq -r '.status'
# Expected: "healthy"

# Test critical functions
curl -s http://localhost:8001/api/v1/execution/status | jq -r '.status'
# Expected: "active" or "paper"

# Monitor for 15 minutes
./scripts/ops/health_check.sh --continuous --duration=900
```

### 3.2 Data Recovery

**Data Loss Scenarios:**

| Scenario | Recovery Method | RTO | RPO |
|----------|-----------------|-----|-----|
| PostgreSQL corruption | Restore from backup | 2 hours | 1 hour |
| Redis data loss | Rebuild from source | 30 minutes | 0 (cache) |
| InfluxDB metrics lost | Accept loss | N/A | 24 hours |
| Configuration lost | Git restore | 15 minutes | 0 (version controlled) |

**PostgreSQL Recovery:**
```bash
# Identify last good backup
LATEST_BACKUP=$(aws s3 ls s3://chiseai-backups/postgres/ | tail -1 | awk '{print $4}')

# Restore database
./scripts/ops/recovery_orchestrator.sh \
  --type=database \
  --source="s3://chiseai-backups/postgres/$LATEST_BACKUP" \
  --target=chiseai-postgres \
  --verify

# Verify data integrity
curl -s http://localhost:8001/api/v1/health/database | jq '.integrity_check'
```

### 3.3 Service Restoration

**Restart Services (Ordered):**

```bash
# 1. Infrastructure services
docker start chiseai-redis chiseai-postgres chiseai-influxdb

# 2. Wait for infrastructure
echo "Waiting 30s for infrastructure..."
sleep 30

# 3. Core services
docker start chiseai-api chiseai-executor

# 4. Wait for core
echo "Waiting 60s for core services..."
sleep 60

# 5. Supporting services
docker start chiseai-dashboard chiseai-grafana

# 6. Verify all services
docker ps --filter "name=chiseai" --format "{{.Names}}: {{.Status}}"
```

---

## 4. Communication Templates

### 4.1 Internal Alert Templates

**P0 Incident - Initial Alert:**
```
🚨 P0 INCIDENT DECLARED 🚨

Incident ID: INC-YYYYMMDD-XXX
Severity: P0 - CRITICAL
Time Started: HH:MM UTC
Impact: [Brief description of impact]

Symptoms:
- [Symptom 1]
- [Symptom 2]

Current Status: Investigating
On-call Engineer: @engineer_name
Escalated to: @manager_name

Updates will be posted every 15 minutes in #incidents
```

**Status Update Template:**
```
📊 INCIDENT UPDATE - INC-YYYYMMDD-XXX

Time: HH:MM UTC (+XX minutes)
Status: [Investigating/Identified/Monitoring/Resolved]

What we know:
- [Update 1]
- [Update 2]

What we're doing:
- [Action 1]
- [Action 2]

ETA for resolution: [Time or "Unknown"]
Next update: HH:MM UTC
```

**Resolution Notice:**
```
✅ INCIDENT RESOLVED - INC-YYYYMMDD-XXX

Time Resolved: HH:MM UTC
Total Duration: XX minutes

Root Cause: [Brief description]
Resolution: [What fixed it]

Impact:
- Duration: XX minutes
- Affected users: X%
- Financial impact: $X (if applicable)

Post-mortem scheduled: [Date/Time]
```

### 4.2 Stakeholder Communication

**Customer Notification (High Impact):**
```
Subject: [ChiseAI] Service Incident - Resolved

Dear Customer,

We experienced a service disruption today from HH:MM to HH:MM UTC that 
may have affected [specific impact].

What happened:
[2-3 sentence description]

What we're doing:
[Prevention measures]

We sincerely apologize for any inconvenience. A detailed post-mortem 
is available at [link].

If you have questions, contact support@chiseai.com
```

**Executive Summary:**
```
EXECUTIVE SUMMARY - INC-YYYYMMDD-XXX

Incident Severity: P[X]
Duration: XX minutes (HH:MM - HH:MM UTC)
Business Impact: [High/Medium/Low]
Financial Impact: $X (if applicable)

Executive Summary:
[2-3 sentences]

Customer Impact:
- X% of users affected
- [Specific functionality impacted]

Root Cause:
[1 sentence]

Resolution:
[1 sentence]

Preventive Actions:
- [Action 1]
- [Action 2]
```

### 4.3 Post-Incident Report

**Post-Incident Report Template:**
```markdown
# Post-Incident Report: INC-YYYYMMDD-XXX

## Incident Summary
- **Incident ID:** INC-YYYYMMDD-XXX
- **Severity:** P[X]
- **Duration:** XX minutes
- **Date:** YYYY-MM-DD
- **Lead Responder:** [Name]

## Timeline
| Time (UTC) | Event |
|------------|-------|
| HH:MM | Incident detected via [method] |
| HH:MM | PagerDuty alert sent |
| HH:MM | Engineer acknowledged |
| HH:MM | Root cause identified |
| HH:MM | Fix applied |
| HH:MM | Service restored |
| HH:MM | Incident closed |

## Root Cause Analysis
### What happened
[Detailed description]

### Why it happened
[Technical explanation]

### Contributing factors
- [Factor 1]
- [Factor 2]

## Impact Assessment
- Users affected: X%
- Features impacted: [List]
- Data loss: [Yes/No, details]
- Financial impact: $X

## Resolution
### Actions taken
1. [Action 1]
2. [Action 2]

### What worked well
- [Positive 1]
- [Positive 2]

### What could be improved
- [Improvement 1]
- [Improvement 2]

## Follow-up Actions
| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| [Action] | [Name] | YYYY-MM-DD | [Open/Closed] |

## Lessons Learned
[Key insights]
```

---

## 5. Post-Mortem Process

### 5.1 Timeline Reconstruction

**Gather Evidence:**
```bash
# Collect logs from incident period
./scripts/ops/recovery_audit_query.sh \
  --start="2026-02-22T12:00:00Z" \
  --end="2026-02-22T14:00:00Z" \
  --output=/tmp/incident-evidence/

# Get metrics snapshot
curl -s "http://localhost:8001/api/v1/metrics/export?start=...&end=..." \
  > /tmp/incident-evidence/metrics.json

# Export incident record
curl -s http://localhost:8001/api/v1/incidents/INC-20260222-001 \
  > /tmp/incident-evidence/incident.json
```

**Build Timeline:**
```bash
# Use timeline builder tool
python3 scripts/ops/build_timeline.py \
  --incident-id="INC-20260222-001" \
  --output="timeline.md"
```

### 5.2 Root Cause Analysis

**5 Whys Technique:**
```
Problem: [What happened]

Why? → [Reason 1]
Why? → [Reason 2]
Why? → [Reason 3]
Why? → [Reason 4]
Why? → [Root Cause]
```

**Fishbone Diagram Categories:**
- People: Human error, training gaps, communication
- Process: Missing procedures, unclear responsibilities
- Technology: Bugs, infrastructure failures, dependencies
- Environment: External services, network, third-party

### 5.3 Prevention Measures

**Action Items Template:**

| ID | Action | Owner | Priority | Due Date | Status |
|----|--------|-------|----------|----------|--------|
| A1 | [Specific action] | [Name] | P0/P1/P2 | YYYY-MM-DD | Open |

**Action Priorities:**
- **P0:** Prevents recurrence of same incident - Complete within 1 week
- **P1:** Significantly reduces risk - Complete within 2 weeks
- **P2:** Nice to have improvement - Complete within 1 month

### 5.4 Post-Mortem Meeting

**Meeting Schedule:**
- Within 48 hours for P0 incidents
- Within 1 week for P1 incidents
- Optional for P2/P3 (async acceptable)

**Attendees:**
- Incident commander (required)
- Engineers involved in response (required)
- Affected service owners (required)
- Engineering manager (P0/P1)
- Optional: Representatives from other teams

**Meeting Structure (60 minutes):**
1. **Context (5 min):** Incident summary
2. **Timeline Review (15 min):** Walk through events
3. **Root Cause (15 min):** Deep dive into why
4. **Impact (5 min):** Business and technical impact
5. **Resolution (5 min):** How we fixed it
6. **Lessons (10 min):** What we learned
7. **Actions (5 min):** Assign follow-ups

### 5.5 Post-Mortem Storage

**Location:**
- All post-mortems stored in: `docs/postmortems/`
- Naming: `postmortem-INC-YYYYMMDD-XXX.md`
- Indexed in: `docs/postmortems/index.md`

**Storage:**
```bash
# Log post-mortem completion
curl -X POST http://localhost:8001/api/v1/incidents/postmortem/complete \
  -d '{"incident_id": "INC-20260222-001", "postmortem_url": "docs/postmortems/postmortem-INC-20260222-001.md", "action_items": 5, "completed_by": "<name>"}'
```

---

## 6. On-Call Procedures

### 6.1 On-Call Schedule

**Rotation:**
- Primary: Week-long rotations
- Secondary: Same rotation (backup)
- Handoff: Every Monday 9:00 AM UTC

**Schedule Location:**
- PagerDuty: https://chiseai.pagerduty.com/schedules
- Internal: http://localhost:8001/oncall

### 6.2 Alert Acknowledgment

**SLA: Acknowledge within 15 minutes**

**Acknowledgment Methods:**
```bash
# Via PagerDuty app
# Click "Acknowledge" on alert

# Via Slack
/incident acknowledge INC-XXX

# Via API
curl -X POST http://localhost:8001/api/v1/incidents/acknowledge \
  -d '{"incident_id": "INC-XXX", "engineer": "<name>"}'
```

**Missed Alert Escalation:**
- 15 min: Reminder notification
- 20 min: Escalate to secondary
- 25 min: Escalate to manager
- 30 min: Page manager

### 6.3 Response SLAs by Severity

| Severity | Acknowledge | First Response | Update Frequency | Resolution |
|----------|-------------|----------------|------------------|------------|
| P0 | 5 min | 15 min | 15 min | 1 hour |
| P1 | 15 min | 30 min | 30 min | 4 hours |
| P2 | 1 hour | 2 hours | 4 hours | 24 hours |
| P3 | 4 hours | 8 hours | Daily | 72 hours |

### 6.4 On-Call Handoff

**Handoff Checklist:**

- [ ] Review active incidents
- [ ] Check recent alerts (last 24h)
- [ ] Review ongoing maintenance
- [ ] Check system health dashboard
- [ ] Transfer PagerDuty to new primary
- [ ] Update on-call Slack status

**Handoff Command:**
```bash
# Generate handoff report
./scripts/ops/oncall_handoff.sh --from="<outgoing>" --to="<incoming>"

# Creates report with:
# - Active incidents
# - Recent alerts
# - System health summary
# - Known issues
```

### 6.5 On-Call Runbook Access

**Quick Access Commands:**

```bash
# List all runbooks
ls docs/runbooks/

# Search runbooks
grep -r "keyword" docs/runbooks/

# Quick health check
./scripts/ops/health_check.sh

# Quick incident log
./scripts/ops/log_incident.sh --interactive
```

**On-Call Toolkit:**
- Runbooks: docs/runbooks/
- Scripts: scripts/ops/
- Dashboards: http://localhost:3001
- API: http://localhost:8001/docs

---

## 7. Incident Lifecycle

### 7.1 Incident States

```
DETECTED → ACKNOWLEDGED → INVESTIGATING → IDENTIFIED → 
  MITIGATING → MONITORING → RESOLVED → CLOSED
     ↑                                                ↓
     └─────────────── REOPENED ←──────────────────────┘
```

| State | Description | Who Can Set |
|-------|-------------|-------------|
| Detected | Alert fired, no human action | System |
| Acknowledged | On-call engineer notified | On-call |
| Investigating | Root cause analysis | Responder |
| Identified | Root cause known | Responder |
| Mitigating | Fix in progress | Responder |
| Monitoring | Fix applied, watching | Responder |
| Resolved | Service restored | Responder |
| Closed | Post-mortem complete | Incident Commander |
| Reopened | Issue recurred | Anyone |

### 7.2 State Transitions

```bash
# Update incident state
curl -X POST http://localhost:8001/api/v1/incidents/INC-XXX/state \
  -d '{
    "state": "investigating",
    "note": "Checking database logs",
    "operator": "<name>"
  }'

# Auto-transitions:
# - Acknowledged → Investigating (after first update)
# - Monitoring → Resolved (after 30 min stable)
# - Resolved → Closed (after post-mortem)
```

---

## 8. War Room Procedures

### 8.1 War Room Activation

**Activate for:**
- P0 incidents
- Complex P1 incidents
- Multi-service failures
- Security incidents

**War Room Setup:**
```bash
# Create war room channel
/incident war-room create INC-XXX

# Invite responders
/incident war-room invite INC-XXX @user1 @user2

# Share dashboard
/incident war-room dashboard INC-XXX http://localhost:3001/d/incident-XXX
```

### 8.2 War Room Roles

| Role | Responsibility | Usually |
|------|----------------|---------|
| Incident Commander | Overall coordination | On-call lead |
| Technical Lead | Technical decisions | Senior engineer |
| Scribe | Documentation | Any engineer |
| Communications | External updates | Manager |
| Subject Matter Expert | Domain expertise | Service owner |

### 8.3 War Room Communication

**Communication Protocol:**
- All updates in war room channel
- No side conversations
- Regular status updates (every 15 min for P0)
- Clear action item assignment
- Document all decisions

---

## 9. Related Runbooks

- [Kill Switch Trigger](kill-switch-trigger.md) - Emergency procedures
- [Launch Safety](launch_runbook.md) - Safety systems
- [ML Operations](ml_operations.md) - ML-specific incidents
- [Paper Trading Operations](paper-trading-operations.md) - Daily operations
- [Autonomous Control Plane](autonomous_control_plane.md) - Self-healing

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-22 | Platform Team | Initial creation for ST-LAUNCH-021 |
