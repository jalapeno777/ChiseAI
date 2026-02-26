# Agent Autonomous Workflow Runbook

## Overview

This runbook provides operational procedures for the ChiseAI Agent Swarm autonomous PR pipeline. It covers monitoring, incident response, and maintenance procedures for the tiered automation system (SAFE, STANDARD, COMPLEX paths).

## System Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Agent Swarm Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       ┌─────────────┐   │
│  │   Agent 1   │  │   Agent 2   │  │   Agent 3   │  ...  │   Agent N   │   │
│  │  (Worker)   │  │  (Worker)   │  │  (Worker)   │       │  (Worker)   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       └──────┬──────┘   │
│         │                │                │                     │          │
│         └────────────────┴────────────────┴─────────────────────┘          │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                              Jarvis                                 │   │
│  │                     (Orchestrator / Coordinator)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│         ┌─────────────────────────┼─────────────────────────┐              │
│         ▼                         ▼                         ▼              │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐      │
│  │ SAFE Path   │           │ STANDARD    │           │  COMPLEX    │      │
│  │  (Auto)     │           │   Path      │           │   Path      │      │
│  └──────┬──────┘           └──────┬──────┘           └──────┬──────┘      │
│         │                         │                         │              │
│         ▼                         ▼                         ▼              │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐      │
│  │ Auto-Merge  │           │GitReviewBot │           │   Human     │      │
│  │  <5 min    │           │  <12 min    │           │  Review     │      │
│  └─────────────┘           └─────────────┘           └─────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Stores

| Store | Purpose | Key Data |
|-------|---------|----------|
| **Redis** | State management, ownership, iterlogs | `bmad:chiseai:ownership`, `bmad:chiseai:iterlog:*` |
| **Qdrant** | Knowledge persistence, semantic search | Decisions, patterns, learnings |
| **Gitea** | Source control, PR management | Code, branches, PRs |
| **InfluxDB** | Metrics, observability | Performance, timing, success rates |

## Operational Procedures

### Daily Operations

#### Morning Check (09:00 UTC)

```bash
#!/bin/bash
# daily_health_check.sh

echo "=== Agent Swarm Daily Health Check ==="

# 1. Check infrastructure
echo "Checking infrastructure..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | \
  grep -E "(chiseai|gitea|woodpecker)"

# 2. Check Redis connectivity
echo "Checking Redis..."
redis-cli -p 6380 ping

# 3. Check Qdrant connectivity
echo "Checking Qdrant..."
curl -s http://localhost:6334/healthz

# 4. Check ownership conflicts
echo "Checking for ownership conflicts..."
redis-cli -p 6380 HGETALL bmad:chiseai:ownership | \
  awk 'NR%2==1 {key=$0} NR%2==0 {print key " -> " $0}'

# 5. Check emergency stop status
echo "Checking emergency stop..."
redis-cli -p 6380 HGET bmad:chiseai:system emergency_stop

# 6. Check pending PRs
echo "Checking pending PRs..."
gh pr list --repo chiseai/chiseai --state open

echo "=== Health Check Complete ==="
```

#### Evening Report (18:00 UTC)

Generate daily metrics report:

```python
#!/usr/bin/env python3
# daily_metrics_report.py

from datetime import datetime, timedelta
import json

def generate_daily_report():
    """Generate daily operational report."""
    
    report = {
        "date": datetime.now().isoformat(),
        "metrics": {
            "safe_path_prs": get_safe_path_count(),
            "standard_path_prs": get_standard_path_count(),
            "complex_path_prs": get_complex_path_count(),
            "avg_safe_time": get_avg_safe_time(),
            "avg_standard_time": get_avg_standard_time(),
            "gitreviewbot_accuracy": get_bot_accuracy(),
        },
        "incidents": get_daily_incidents(),
        "active_stories": get_active_stories(),
        "ownership_conflicts": get_ownership_conflicts(),
    }
    
    # Store in Redis
    redis_state_hset(
        name="bmad:chiseai:metrics:daily",
        key=datetime.now().strftime("%Y-%m-%d"),
        value=json.dumps(report)
    )
    
    return report

def get_safe_path_count():
    """Get count of SAFE path PRs processed today."""
    # Query from metrics store
    pass

def get_standard_path_count():
    """Get count of STANDARD path PRs processed today."""
    pass

def get_complex_path_count():
    """Get count of COMPLEX path PRs processed today."""
    pass

def get_avg_safe_time():
    """Get average time for SAFE path PRs."""
    pass

def get_avg_standard_time():
    """Get average time for STANDARD path PRs."""
    pass

def get_bot_accuracy():
    """Get GitReviewBot accuracy rating."""
    pass

def get_daily_incidents():
    """Get incidents from today."""
    pass

def get_active_stories():
    """Get currently active stories."""
    pass

def get_ownership_conflicts():
    """Get current ownership conflicts."""
    pass

if __name__ == "__main__":
    report = generate_daily_report()
    print(json.dumps(report, indent=2))
```

### Weekly Operations

#### Monday: Capacity Planning

Review upcoming week:

```markdown
## Weekly Capacity Planning Checklist

- [ ] Review backlog in docs/bmm-workflow-status.yaml
- [ ] Identify parallelizable work
- [ ] Check for dependencies and blockers
- [ ] Assign stories to agents
- [ ] Reserve capacity for incidents
- [ ] Schedule maintenance windows
```

#### Friday: Week Review

```bash
#!/bin/bash
# weekly_review.sh

echo "=== Weekly Agent Swarm Review ==="

# PR throughput
echo "PR Throughput:"
redis-cli -p 6380 HGETALL bmad:chiseai:metrics:weekly

# Incident summary
echo "Incidents this week:"
redis-cli -p 6380 LRANGE bmad:chiseai:incidents:weekly 0 -1

# Agent performance
echo "Agent performance:"
redis-cli -p 6380 HGETALL bmad:chiseai:metrics:agent

# Path distribution
echo "Path distribution:"
echo "SAFE: $(redis-cli -p 6380 HGET bmad:chiseai:metrics:paths safe)"
echo "STANDARD: $(redis-cli -p 6380 HGET bmad:chiseai:metrics:paths standard)"
echo "COMPLEX: $(redis-cli -p 6380 HGET bmad:chiseai:metrics:paths complex)"
```

## Monitoring and Observability

### Key Metrics

#### Performance Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| SAFE path time | <5 min | >10 min | >15 min |
| STANDARD path time | <12 min | >20 min | >30 min |
| GitReviewBot latency | <5 min | >10 min | >15 min |
| PR queue depth | <5 | >10 | >20 |

#### Quality Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| CI pass rate | >95% | <90% | <80% |
| GitReviewBot accuracy | >90% | <85% | <80% |
| Rollback rate | <2% | >5% | >10% |
| Incident rate | <1/day | >2/day | >5/day |

#### Operational Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Agent utilization | 70-80% | <50% | >95% |
| Ownership conflicts | 0 | >2/week | >5/week |
| Emergency stops | 0 | >1/month | >3/month |

### Grafana Dashboards

#### Dashboard 1: PR Pipeline Overview

```json
{
  "dashboard": {
    "title": "Agent Swarm PR Pipeline",
    "panels": [
      {
        "title": "PRs by Path",
        "type": "stat",
        "targets": [
          {
            "expr": "sum by (path) (pr_pipeline_total)"
          }
        ]
      },
      {
        "title": "Processing Time by Path",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, pr_processing_duration_seconds_bucket)"
          }
        ]
      },
      {
        "title": "Queue Depth",
        "type": "gauge",
        "targets": [
          {
            "expr": "pr_queue_depth"
          }
        ]
      }
    ]
  }
}
```

#### Dashboard 2: Agent Performance

```json
{
  "dashboard": {
    "title": "Agent Performance",
    "panels": [
      {
        "title": "Stories Completed by Agent",
        "type": "bar gauge",
        "targets": [
          {
            "expr": "sum by (agent) (stories_completed_total)"
          }
        ]
      },
      {
        "title": "Agent Utilization",
        "type": "graph",
        "targets": [
          {
            "expr": "agent_utilization_percent"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# alerting_rules.yml
groups:
  - name: agent_swarm_alerts
    rules:
      - alert: SafePathDelayed
        expr: pr_processing_duration_seconds{path="safe"} > 600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "SAFE path PRs taking too long"
          
      - alert: StandardPathDelayed
        expr: pr_processing_duration_seconds{path="standard"} > 1200
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "STANDARD path PRs taking too long"
          
      - alert: HighIncidentRate
        expr: rate(incidents_total[1h]) > 0.1
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "High incident rate detected"
          
      - alert: EmergencyStopActive
        expr: emergency_stop_status == 1
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "Emergency stop is active"
```

## Incident Response

### Incident Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|---------------|------------|
| **P0** | System down, data loss | Immediate | Human + Emergency stop |
| **P1** | Major feature blocked | <30 min | Human review required |
| **P2** | Workaround exists | <4 hours | Jarvis handles |
| **P3** | Minor issue | <24 hours | Queue for next cycle |

### Incident Response Procedures

#### P0: Critical Incident

```markdown
## P0 Incident Response

1. **STOP all automation immediately**
   ```bash
   redis-cli -p 6380 HSET bmad:chiseai:system emergency_stop enabled
   ```

2. **Notify team**
   - Post in #incidents channel
   - Page on-call engineer
   - Create incident record

3. **Assess impact**
   - What systems are affected?
   - Is there data loss?
   - Can we rollback?

4. **Execute response**
   - If rollback possible: Execute rollback
   - If not: Implement hotfix
   - Document all actions

5. **Post-incident**
   - Schedule post-mortem
   - Update runbooks
   - Clear emergency stop when safe
```

#### P1: High Priority Incident

```markdown
## P1 Incident Response

1. **Assess scope**
   - What is affected?
   - Who is impacted?
   - Is there a workaround?

2. **Assign owner**
   - Assign to available senior agent
   - Set SLA for resolution

3. **Execute fix**
   - Follow normal PR process
   - May bypass GitReviewBot for hotfix
   - Require human review

4. **Verify resolution**
   - Run full test suite
   - Monitor for 1 hour post-fix
   - Document resolution
```

### Common Incident Scenarios

#### Scenario 1: Mass CI Failure

**Symptoms**: All PRs failing CI

**Response**:
```bash
# 1. Check CI system health
docker logs woodpecker-server --tail 100

# 2. Check for infrastructure issues
docker ps | grep -E "(woodpecker|gitea)"

# 3. If CI system down:
#    - Activate emergency stop
#    - Notify team
#    - Restart CI services
#    - Verify before clearing emergency stop
```

#### Scenario 2: Ownership Conflict Storm

**Symptoms**: Multiple agents reporting ownership conflicts

**Response**:
```python
# 1. Check ownership state
conflicts = redis_state_hgetall(name="bmad:chiseai:ownership")

# 2. Identify stale ownership (>5 days)
for scope, owner in conflicts.items():
    story_id, agent, timestamp = owner.split("/")
    if is_stale(timestamp):
        # Release stale ownership
        redis_state_hdel(name="bmad:chiseai:ownership", key=scope)

# 3. Re-plan parallel work as sequential if needed
```

#### Scenario 3: GitReviewBot Accuracy Drop

**Symptoms**: Bot approving bad PRs or rejecting good ones

**Response**:
```markdown
1. **Disable GitReviewBot auto-approve**
   - Set all STANDARD path to human review
   
2. **Analyze recent decisions**
   - Review last 50 bot decisions
   - Identify pattern of errors
   
3. **Retrain or adjust thresholds**
   - Update bot configuration
   - Add new rules
   
4. **Gradual re-enable**
   - Start with 10% of PRs
   - Monitor accuracy
   - Scale up when confident
```

## Maintenance Procedures

### Weekly Maintenance

#### Redis Cleanup

```bash
#!/bin/bash
# redis_cleanup.sh

echo "Cleaning up Redis..."

# Remove stale ownership (older than 7 days)
redis-cli -p 6380 EVAL "
  local keys = redis.call('HKEYS', 'bmad:chiseai:ownership')
  for i, key in ipairs(keys) do
    local value = redis.call('HGET', 'bmad:chiseai:ownership', key)
    -- Parse timestamp and check age
    -- Remove if older than 7 days
  end
" 0

# Archive old iterlogs (older than 30 days)
# (Move to long-term storage)

# Clean up expired keys
redis-cli -p 6380 EVAL "return redis.call('del', unpack(redis.call('keys', 'bmad:chiseai:iterlog:*:temp')))" 0

echo "Redis cleanup complete"
```

#### Qdrant Maintenance

```bash
#!/bin/bash
# qdrant_maintenance.sh

# Optimize collections
curl -X POST http://localhost:6334/collections/chiseai/optimize

# Check collection health
curl http://localhost:6334/collections/chiseai

# Archive old vectors (older than 90 days)
# (Implement based on retention policy)
```

### Monthly Maintenance

#### GitReviewBot Model Update

```python
#!/usr/bin/env python3
# update_gitreviewbot.py

"""
Monthly retraining of GitReviewBot model.
"""

def retrain_bot():
    """Retrain GitReviewBot with recent data."""
    
    # 1. Collect training data
    training_data = collect_training_data(days=30)
    
    # 2. Evaluate current model
    current_accuracy = evaluate_model(current_model, training_data)
    
    # 3. Train new model
    new_model = train_model(training_data)
    new_accuracy = evaluate_model(new_model, training_data)
    
    # 4. Deploy if better
    if new_accuracy > current_accuracy:
        deploy_model(new_model)
        print(f"Deployed new model: {new_accuracy:.2%} accuracy")
    else:
        print(f"Kept current model: {current_accuracy:.2%} accuracy")

def collect_training_data(days):
    """Collect PR data for training."""
    pass

def evaluate_model(model, data):
    """Evaluate model accuracy."""
    pass

def train_model(data):
    """Train new model."""
    pass

def deploy_model(model):
    """Deploy model to production."""
    pass

if __name__ == "__main__":
    retrain_bot()
```

## KPIs and Reporting

### Weekly KPI Report

```markdown
## Agent Swarm Weekly KPI Report
Week of: 2026-02-24 to 2026-03-02

### Throughput
- Total PRs processed: 45
- SAFE path: 18 (40%)
- STANDARD path: 22 (49%)
- COMPLEX path: 5 (11%)

### Performance
- Average SAFE time: 3.2 min (target: <5 min) ✅
- Average STANDARD time: 9.5 min (target: <12 min) ✅
- Average COMPLEX time: 4.2 hours (varies by complexity)

### Quality
- CI pass rate: 97% (target: >95%) ✅
- GitReviewBot accuracy: 93% (target: >90%) ✅
- Rollback rate: 1.2% (target: <2%) ✅

### Operational
- Active agents: 8/10
- Agent utilization: 76% (target: 70-80%) ✅
- Ownership conflicts: 2 (resolved)
- Incidents: 1 (P2)

### Recommendations
1. Consider adding 2 more agents to handle load
2. GitReviewBot performing well, can increase STANDARD path threshold
3. No action required on current metrics
```

### Monthly Business Review

```markdown
## Agent Swarm Monthly Business Review
Month: February 2026

### Executive Summary
- 180 PRs processed (20% increase from January)
- 99.2% uptime
- 0 P0 incidents
- $50K engineering time saved vs manual process

### Path Distribution Analysis
- SAFE path: 35% (healthy)
- STANDARD path: 55% (healthy)
- COMPLEX path: 10% (healthy)

### Agent Performance
- Top performer: Agent-A (23 stories)
- Average stories/agent: 18
- Utilization: 76%

### Improvements Made
1. Reduced STANDARD path time from 15 min to 9.5 min
2. Improved GitReviewBot accuracy from 88% to 93%
3. Added 2 new agents to swarm

### Plans for Next Month
1. Implement predictive path classification
2. Add automated rollback for failed deployments
3. Expand agent swarm to 12 agents
```

## Appendix

### A. Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| On-call Engineer | #on-call | P0/P1 incidents |
| Jarvis (Orchestrator) | @jarvis | General issues |
| Merlin (Merge Authority) | @merlin | PR/merge issues |
| Infrastructure Team | #infra | Infrastructure issues |

### B. Useful Commands

```bash
# Check all agent sessions
redis-cli -p 6380 KEYS "bmad:chiseai:iterlog:*"

# Check ownership status
redis-cli -p 6380 HGETALL bmad:chiseai:ownership

# View recent incidents
redis-cli -p 6380 LRANGE bmad:chiseai:incidents 0 10

# Check emergency stop
redis-cli -p 6380 HGET bmad:chiseai:system emergency_stop

# List open PRs
gh pr list --repo chiseai/chiseai --state open

# Check CI status
woodpecker-cli build list
```

### C. Runbook Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-02-26 | 1.0 | Initial runbook creation | ST-AUTO-008 |

---

**Document Owner**: Agent Swarm Operations Team  
**Review Schedule**: Monthly  
**Last Updated**: 2026-02-26
