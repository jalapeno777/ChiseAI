# Self-Healing Procedures

## Overview

This document provides runbook templates and operational procedures for manual intervention in the self-healing system.

## Quick Reference

| Scenario | Workflow | Priority | Auto-Approval |
|----------|----------|----------|---------------|
| Redis Disconnect | `redis_recovery` | P2 | Yes (paper), No (live) |
| API Timeout | `api_timeout_remediation` | P2 | Yes |
| Circuit Breaker Open | `circuit_breaker_reset` | P2 | No (live) |
| Service Unhealthy | `service_restart` | P1 | No (live) |
| DB Connection Failed | `database_recovery` | P2 | Yes |
| Memory Exhaustion | `memory_exhaustion` | P1 | No (live) |
| Disk Space Critical | `disk_space_cleanup` | P1 | Yes |
| CPU Spike | `cpu_spike_mitigation` | P2 | Yes |
| InfluxDB Write Failed | `influxdb_recovery` | P2 | Yes |
| Dead Letter Queue | `dlq_processing` | P3 | Yes |

## Runbook Templates

### Template 1: Service Restart Procedure

**Purpose:** Restart a service with full health verification

**Trigger:** Service health check failing for >2 minutes

**Steps:**

1. **Pre-Restart Checks**
   ```bash
   # Check current service status
   curl http://localhost:8000/health
   
   # Check dependent services
   curl http://localhost:8000/health/deps
   
   # Review recent logs
   tail -n 100 /var/log/service.log
   ```

2. **Initiate Restart**
   ```python
   from autonomous_control_plane.automation import AutomationController
   
   controller = AutomationController(trading_mode="live")
   workflow = await controller.start_remediation(
       service="my_service",
       pattern_type=FailurePatternType.SERVICE_UNHEALTHY
   )
   ```

3. **Monitor Restart**
   ```bash
   # Watch service startup
   watch -n 1 'curl -s http://localhost:8000/health | jq .status'
   
   # Check logs in real-time
   tail -f /var/log/service.log | grep -E "(started|error|fail)"
   ```

4. **Post-Restart Verification**
   - [ ] Health endpoint returns 200
   - [ ] All dependencies accessible
   - [ ] Response time < 500ms
   - [ ] No error spikes in logs

5. **Rollback (if needed)**
   ```bash
   # If restart fails, check rollback status
   # Automated rollback occurs within 30 seconds
   ```

**Escalation:**
- If restart fails twice → Escalate to on-call engineer
- If dependent services affected → Page on-call immediately

---

### Template 2: Circuit Breaker Reset

**Purpose:** Manually reset a tripped circuit breaker

**Trigger:** Circuit breaker OPEN for >5 minutes

**Pre-conditions:**
- Verify downstream service is healthy
- Check failure rate has decreased

**Steps:**

1. **Analyze Circuit State**
   ```python
   from common.circuit_breaker import CircuitBreakerRegistry
   
   registry = CircuitBreakerRegistry()
   state = registry.get("api_service").get_state_dict()
   print(f"State: {state['state']}, Failures: {state['metrics']['failure_count']}")
   ```

2. **Check Downstream Health**
   ```bash
   # Verify downstream is healthy
   curl http://downstream-service/health
   
   # Check recent error rate
   # Look for < 1% error rate in last 5 minutes
   ```

3. **Request Reset**
   ```python
   from autonomous_control_plane.automation import RunbookEngine
   from autonomous_control_plane.automation.workflows import RemediationWorkflows
   
   engine = RunbookEngine(trading_mode="live")
   workflows = RemediationWorkflows(engine)
   
   runbook = workflows.create_circuit_breaker_reset_runbook("api_service")
   execution = await engine.execute_runbook(runbook, triggered_by="operator")
   ```

4. **Approve Reset (Live Mode)**
   ```python
   # In live mode, approval is required
   engine.approve_step(
       execution_id=execution.execution_id,
       step_id=runbook.steps[2].step_id,  # Reset step
       approved_by="operator_name"
   )
   ```

5. **Verify Reset**
   ```python
   # Check circuit is CLOSED
   state = registry.get("api_service").get_state_dict()
   assert state['state'] == 'CLOSED'
   ```

**Escalation:**
- If circuit trips again within 5 minutes → Investigate root cause
- If multiple circuits trip → Possible infrastructure issue

---

### Template 3: Redis Connection Recovery

**Purpose:** Recover from Redis connection failures

**Trigger:** Redis connection errors in logs

**Steps:**

1. **Check Redis Status**
   ```bash
   # Check Redis connectivity
   redis-cli -h host.docker.internal -p 6380 ping
   
   # Check connection count
   redis-cli -h host.docker.internal -p 6380 info clients
   ```

2. **Analyze Connection Pool**
   ```python
   # Check application connection pool status
   # Look for connection pool exhaustion
   ```

3. **Execute Recovery**
   ```python
   from autonomous_control_plane.automation import AutomationController
   
   controller = AutomationController()
   workflow = await controller.start_remediation(
       service="redis",
       pattern_type=FailurePatternType.REDIS_DISCONNECT
   )
   ```

4. **Verify Recovery**
   ```bash
   # Verify new connections work
   redis-cli -h host.docker.internal -p 6380 ping
   
   # Check application can connect
   curl http://localhost:8000/health/redis
   ```

**Escalation:**
- If Redis is down → Escalate to infrastructure team
- If recovery fails twice → Page on-call engineer

---

### Template 4: Memory Exhaustion Response

**Purpose:** Free memory when service approaches limits

**Trigger:** Memory usage > 85% for >5 minutes

**Steps:**

1. **Analyze Memory Usage**
   ```bash
   # Check current memory
   ps aux --sort=-%mem | head -10
   
   # Check application memory
   curl http://localhost:8000/metrics/memory
   ```

2. **Clear Caches**
   ```python
   from autonomous_control_plane.automation import AutomationController
   
   controller = AutomationController()
   workflow = await controller.start_remediation(
       service="app_service",
       pattern_type=FailurePatternType.MEMORY_EXHAUSTION,
       context={"memory_critical": True}
   )
   ```

3. **Monitor Recovery**
   ```bash
   # Watch memory usage
   watch -n 5 'ps -o %mem,pid,command -p <PID>'
   ```

4. **Restart if Necessary**
   - If memory not freed after cache clear
   - Requires approval in live mode

**Escalation:**
- If memory continues growing → Possible memory leak, escalate to dev team
- If restart doesn't help → Infrastructure issue

---

## Escalation Procedures

### Escalation Levels

1. **AUTO** - Fully automated, no human intervention
2. **NOTIFY** - Notify operators but continue automatically
3. **APPROVE** - Pause for human approval before continuing
4. **MANUAL** - Stop automation, manual intervention required
5. **EMERGENCY** - Page on-call immediately

### Escalation Matrix

| Condition | Level | Action |
|-----------|-------|--------|
| First failure | AUTO | Automated remediation |
| Second failure | NOTIFY | Notify, retry once |
| Third failure | APPROVE | Require approval |
| Critical service | APPROVE | Always require approval |
| Multiple services | EMERGENCY | Page on-call |
| Trading impact | EMERGENCY | Page on-call |

### Notification Channels

- **Log** - Application logs
- **Metrics** - InfluxDB metrics
- **Slack** - #alerts channel
- **PagerDuty** - On-call rotation

## Post-Healing Validation

### Validation Checklist

After any healing action:

- [ ] Service health endpoint returns 200
- [ ] Response time within SLA (< 500ms p95)
- [ ] Error rate < 1%
- [ ] All dependencies accessible
- [ ] No new errors in logs
- [ ] Metrics flowing to InfluxDB
- [ ] Circuit breakers in CLOSED state

### Automated Validation

```python
# Automated post-healing validation
async def validate_healing(service: str) -> bool:
    checks = [
        await check_health_endpoint(service),
        await check_dependencies(service),
        await check_error_rate(service),
        await check_metrics_flow(service),
    ]
    return all(checks)
```

## Emergency Procedures

### Kill Switch Activation

In case of runaway healing:

```bash
# Activate kill switch
redis-cli -h host.docker.internal -p 6380 SET acp:healing:kill_switch 1

# Verify all healing stopped
curl http://localhost:8000/api/v1/healing/status
```

### Manual Override

```python
# Disable automation controller
controller.disable()

# Stop all active workflows
for workflow_id in controller.get_active_workflows():
    await controller.cancel_workflow(workflow_id)
```

## Audit Trail

All healing actions are logged with:

- Timestamp
- Service name
- Action type
- Operator (if manual)
- Result (success/failure)
- Rollback status

### Querying Audit Logs

```python
# Get healing history
history = controller.get_healing_history(service="redis", limit=100)

# Get execution logs
execution = controller.get_workflow_status(workflow_id)
```

## References

- [Self-Healing Automation Architecture](./self-healing-automation.md)
- ST-CONTROL-002: Self-Healing Automation
- ST-CONTROL-001: Telemetry Pipeline
