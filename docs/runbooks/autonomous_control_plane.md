# Autonomous Control Plane Runbook

> **Story:** ST-NS-043  
> **Last Updated:** 2026-02-21  
> **Owner:** Platform Team

---

## Overview

This runbook covers operational procedures for the Autonomous Control Plane, which manages self-healing operations and incident management for the ChiseAI platform.

## Prerequisites

Before following procedures in this runbook, ensure you have:

- [ ] Access to Kubernetes cluster (`kubectl get pods` works)
- [ ] Access to ChiseAI namespace resources
- [ ] Redis connectivity (`redis-cli -h chiseai-redis ping` returns PONG)
- [ ] Prometheus/Grafana access for metrics verification
- [ ] Appropriate RBAC permissions to restart deployments
- [ ] PagerDuty access for escalation procedures

---

## Alert: ControlPlaneDown

### Symptoms
- Alert: `ControlPlaneDown` fires
- Expression: `up{job="autonomous-control-plane"} == 0`
- Duration: 1 minute

### Impact
- Self-healing operations may be delayed or fail
- Incident detection and response may be impacted
- Manual intervention may be required for system issues

### Response Procedure

1. **Immediate Verification (0-2 min)**
   ```bash
   # Check if the control plane pod/service is running
   kubectl get pods -n chiseai -l app=autonomous-control-plane
   
   # Check logs for errors
   kubectl logs -n chiseai -l app=autonomous-control-plane --tail=100
   ```

2. **Check Dependencies (2-5 min)**
   - Verify Redis connectivity: `redis-cli -h chiseai-redis ping`
   - Verify PostgreSQL connectivity
   - Check InfluxDB for metrics ingestion

3. **Recovery Actions**
   - If pod is crashed: `kubectl rollout restart deployment/autonomous-control-plane -n chiseai`
   - If resource-starved: Check node resources and scale if necessary
   - If dependency issue: Address the root cause dependency first

4. **Verification**
   - Confirm `up{job="autonomous-control-plane"} == 1` in Prometheus/Grafana
   - Check that healing operations resume

### Escalation
- If not resolved within 15 minutes, escalate to Platform Engineering Lead
- If multiple services affected, consider P0 incident declaration

---

## Alert: CircuitBreakerOpenTooLong

### Symptoms
- Alert: `CircuitBreakerOpenTooLong` fires
- Expression: `circuit_breaker_state == 1`
- Duration: 5 minutes

### Impact
- Circuit breaker is preventing calls to a failing service
- Self-healing actions may be blocked
- System is protecting itself from cascading failures

### Response Procedure

1. **Identify the Affected Service**
   ```bash
   # Check which circuit breaker is open
   curl http://localhost:8000/metrics | grep circuit_breaker_state
   ```

2. **Check Target Service Health**
   - Identify the service the circuit breaker is protecting
   - Check logs of the target service
   - Verify target service resource utilization

3. **Decision Matrix**

   | Scenario | Action |
   |----------|--------|
   | Target service is healthy | Manually close circuit breaker via API |
   | Target service is degraded | Scale target service or investigate root cause |
   | Target service is down | Restart target service, then close circuit breaker |

4. **Manual Circuit Breaker Reset**
   ```bash
   # Use the circuit breaker reset endpoint
   curl -X POST http://localhost:8000/api/v1/circuit-breaker/reset \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"service_name": "<affected-service>"}'
   ```

### Escalation
- If circuit breaker reopens after reset, escalate to Service Owner
- If multiple circuit breakers open, declare incident

---

## Alert: HealingFailureRateHigh

### Symptoms
- Alert: `HealingFailureRateHigh` fires
- Expression: `rate(healing_failures[5m]) / rate(healing_attempts[5m]) > 0.1`
- Duration: 2 minutes

### Impact
- More than 10% of self-healing attempts are failing
- System reliability may be degrading
- Manual intervention may be required

### Response Procedure

1. **Check Current Failure Rate**
   ```bash
   # Query current metrics
   curl "http://localhost:9090/api/v1/query?query=rate(healing_failures[5m])/rate(healing_attempts[5m])"
   ```

2. **Identify Failure Patterns**
   - Check Grafana dashboard: "Autonomous Control Plane - Self-Healing & Incident Management"
   - Look for specific healing action types that are failing
   - Review recent changes to the platform

3. **Common Causes and Fixes**

   | Cause | Fix |
   |-------|-----|
   | Insufficient permissions | Check service account RBAC |
   | Resource constraints | Scale affected services |
   | Dependency failures | Fix underlying dependency |
   | Configuration errors | Rollback recent config changes |

4. **Review Failed Healings**
   ```bash
   # Check healing engine logs
   kubectl logs -n chiseai -l app=autonomous-control-plane | grep -i "healing.*failed"
   ```

### Escalation
- If failure rate exceeds 50%, escalate immediately
- If failures correlate with deployment, consider rollback

---

## General Escalation Procedures

### Severity Levels

| Level | Criteria | Response Time | Escalation To |
|-------|----------|---------------|---------------|
| P0 | Complete control plane outage | 5 min | Platform Lead + On-call Engineer |
| P1 | Major functionality impaired | 15 min | Platform Lead |
| P2 | Partial degradation | 30 min | Team Channel |
| P3 | Minor issues | 2 hours | Ticket for next sprint |

### Escalation Contacts

- **Primary On-Call:** `#platform-oncall` Slack channel
- **Platform Engineering Lead:** @platform-lead
- **Incident Commander:** @incident-commander (for P0/P1)

### Communication

1. Acknowledge alert within defined response time
2. Update incident status in incident management system
3. Post updates to `#incidents` Slack channel every 15 minutes for active incidents
4. Schedule post-mortem for all P0/P1 incidents within 24 hours

---

## Useful Commands

```bash
# Check control plane health
curl http://localhost:8000/health

# Expected output:
# {"status": "healthy", "services": {"redis": "connected", "database": "connected"}}

# Get control plane metrics
curl http://localhost:8000/metrics

# View recent healing operations
kubectl logs -n chiseai -l app=autonomous-control-plane | grep -i "healing"

# Check circuit breaker status
curl http://localhost:8000/api/v1/circuit-breaker/status

# Manually trigger healing (emergency only)
curl -X POST http://localhost:8000/api/v1/healing/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"incident_id": "<incident-id>"}'
```

---

## References

- Dashboard: [Autonomous Control Plane](https://grafana.chiseai.com/d/autonomous-healing)
- Alert Rules: `infrastructure/grafana/alerts/autonomous_control_plane.yml`
- Source Code: `src/autonomous_control_plane/`
- Architecture Doc: `docs/architecture/autonomous-control-plane.md`
