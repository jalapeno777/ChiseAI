# PR Pipeline ACP Integration Runbook

## Overview

This runbook describes the Autonomous Control Plane (ACP) integration with the PR Pipeline, providing circuit breaker protection, retry coordination, self-healing capabilities, and incident management for all PR lifecycle operations.

**Story**: ST-AUTO-006  
**Epic**: EP-AUTO-GIT-001  
**Related**: EP-NS-008 (Autonomous Control Plane)

---

## Table of Contents

1. [Architecture](#architecture)
2. [Circuit Breaker Behavior](#circuit-breaker-behavior)
3. [Retry Coordinator](#retry-coordinator)
4. [Self-Healing Engine](#self-healing-engine)
5. [Incident Manager](#incident-manager)
6. [Rollback Coordinator](#rollback-coordinator)
7. [Health Checks](#health-checks)
8. [Metrics and Monitoring](#metrics-and-monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Operational Procedures](#operational-procedures)

---

## Architecture

### Components

The ACP integration consists of the following components:

```
├── ACPIntegrationManager (main coordinator)
│   ├── Circuit Breaker Registry
│   │   ├── gitea_api
│   │   ├── discord_notifications
│   │   ├── redis_operations
│   │   └── pr_merge_operations
│   ├── Retry Coordinator
│   │   ├── Budget Manager
│   │   └── Metrics Collector
│   ├── Self-Healing Engine (ACP)
│   ├── Incident Manager (ACP)
│   └── Rollback Coordinator (ACP)
```

### Integration Points

The ACP integration wraps the following PR pipeline operations:

- **Gitea API calls**: PR creation, updates, merges, status checks
- **Discord notifications**: Success/failure notifications
- **Redis operations**: State management, caching
- **PR merge operations**: Automated merge attempts

---

## Circuit Breaker Behavior

### States

The circuit breaker has three states:

1. **CLOSED**: Normal operation, all calls pass through
2. **OPEN**: Failing fast, calls are rejected immediately
3. **HALF_OPEN**: Testing recovery, limited calls allowed

### State Transitions

```
CLOSED --(failure threshold reached)--> OPEN
OPEN --(recovery timeout)--> HALF_OPEN
HALF_OPEN --(success threshold reached)--> CLOSED
HALF_OPEN --(any failure)--> OPEN
```

### Configuration

Default configurations for PR operations:

| Service | Failure Threshold | Recovery Timeout | Success Threshold |
|---------|------------------|------------------|-------------------|
| gitea_api | 5 | 60s | 2 |
| discord_notifications | 3 | 30s | 1 |
| redis_operations | 10 | 30s | 3 |
| pr_merge_operations | 3 | 120s | 1 |

### Manual Control

```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()

# Force open a circuit
manager._circuit_registry.force_open("gitea_api", "maintenance_window")

# Force close a circuit
manager._circuit_registry.force_close("gitea_api", "maintenance_complete")

# Reset all circuits
manager._circuit_registry.reset_all()
```

---

## Retry Coordinator

### Retry Policy

Default retry policies:

| Service | Max Attempts | Base Delay | Max Delay | Budget/min |
|---------|-------------|------------|-----------|------------|
| gitea_api_call | 3 | 1.0s | 30s | 10 |
| discord_notification | 2 | 0.5s | 5s | 10 |
| redis_operation | 5 | 0.5s | 10s | 10 |
| pr_merge | 3 | 2.0s | 60s | 5 |

### Backoff Strategy

Exponential backoff with jitter:

```
delay = base_delay * (exponential_base ^ (attempt - 1))
delay = min(delay, max_delay)
if jitter:
    delay += random(0, jitter_max)
```

### Budget Management

Each service has a per-minute retry budget to prevent retry storms. When the budget is exceeded:

1. New retries are rejected immediately
2. A `BudgetExceededError` is raised
3. The operation should fall back to degraded mode

### Non-Retryable Exceptions

The following exceptions are not retried:

- `KeyboardInterrupt`
- `SystemExit`
- `ValueError`
- `TypeError`

---

## Self-Healing Engine

### Failure Patterns

The self-healing engine detects and responds to these failure patterns:

| Pattern | Action | Auto-Execute |
|---------|--------|--------------|
| REDIS_DISCONNECT | Restart Redis connection pool | Yes |
| API_TIMEOUT | Retry with backoff | Yes |
| CIRCUIT_BREAKER_OPEN | Reset circuit breaker | Yes |

### Anti-Flap Protection

- Maximum 3 healing attempts per hour per service
- Requires human approval for P0/P1 actions in production

### Manual Healing Request

```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()

result = manager.request_self_healing(
    failure_pattern="API_TIMEOUT",
    context={
        "service": "gitea_api",
        "endpoint": "/api/v1/repos/owner/repo/pulls",
    }
)
```

---

## Incident Manager

### Severity Levels

| Severity | Description | Auto-Remediation |
|----------|-------------|------------------|
| P0 | Critical - System down | No (requires approval) |
| P1 | High - Major functionality impaired | No (requires approval) |
| P2 | Medium - Degraded performance | Yes |
| P3 | Low - Minor issues | Yes |

### Automatic Incident Creation

Incidents are automatically created for:

- Circuit breaker open errors (P2)
- Budget exceeded errors (P2)
- Max retries exceeded (P1)
- Unhandled exceptions (P1)

### Incident Metadata

Each incident includes:

- Service name
- Operation name
- Error type and message
- Duration of failed operation
- Stack trace (if available)

---

## Rollback Coordinator

### Rollback Scenarios

Automatic rollback is triggered for:

1. **Post-merge CI failure**: If CI fails after auto-merge
2. **Health check failure**: If post-merge health checks fail
3. **Manual trigger**: Human-initiated rollback

### Rollback Steps

1. Validate PR state (ensure it can be rolled back)
2. Create revert commit
3. Notify stakeholders
4. Update PR state

### Manual Rollback

```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()

result = manager.trigger_rollback(
    pr_number=123,
    reason="Post-merge CI failure",
    validation_checks=[
        {"name": "no_dependent_prs", "status": "passed"},
    ]
)

if result["success"]:
    print(f"Rollback completed: {result['operation_id']}")
else:
    print(f"Rollback failed: {result['error']}")
```

---

## Health Checks

### Component Health

Health checks verify the availability of:

1. Circuit Breaker Registry
2. Retry Coordinator
3. Self-Healing Engine
4. Incident Manager
5. Rollback Coordinator

### Health Check API

```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()
health = manager.check_health()

print(f"Healthy components: {health.healthy_count}/5")
print(f"All healthy: {health.all_healthy}")

# Individual component status
print(f"Circuit Breaker: {health.circuit_breaker_registry}")
print(f"Retry Coordinator: {health.retry_coordinator}")
print(f"Self-Healing: {health.self_healing_engine}")
print(f"Incident Manager: {health.incident_manager}")
print(f"Rollback Coordinator: {health.rollback_coordinator}")
```

### Health Check Interval

Default: Every 30 seconds

---

## Metrics and Monitoring

### Available Metrics

```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()
metrics = manager.get_metrics()

# Health status
health = metrics["health_status"]

# Circuit breaker states
cb_states = metrics["circuit_breakers"]
for name, state in cb_states.items():
    print(f"{name}: {state['state']} "
          f"(failures: {state['failure_count']}, "
          f"successes: {state['success_count']})")

# Retry metrics
retry_metrics = metrics["retry_operations"]
print(f"Successes: {retry_metrics['successes']}")
print(f"Failures: {retry_metrics['failures']}")
print(f"Budget status: {retry_metrics['budget_status']}")
```

### InfluxDB Metrics

When InfluxDB is available, the following metrics are exported:

- `circuit_breaker_state`: Current state of each circuit breaker
- `circuit_breaker_failures`: Failure count per service
- `retry_attempts_total`: Total retry attempts
- `retry_success_total`: Successful retries
- `retry_failure_total`: Failed retries by reason
- `retry_budget_exceeded_total`: Budget exceeded events

---

## Troubleshooting

### Issue: Circuit Breaker Stuck Open

**Symptoms**: All calls to a service are rejected with `CircuitBreakerOpenError`

**Diagnosis**:
```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()
cb = manager._circuit_registry.get_circuit_breaker("gitea_api")
metrics = cb.get_metrics()

print(f"State: {metrics['state']}")
print(f"Failure count: {metrics['failure_count']}")
print(f"Last failure: {metrics['last_failure_time']}")
print(f"Consecutive successes: {metrics['consecutive_successes']}")
```

**Resolution**:
1. Check if the underlying service is healthy
2. If service is healthy, manually close the circuit:
   ```python
   manager._circuit_registry.force_close("gitea_api", "service_recovered")
   ```
3. If the issue persists, check service logs for recurring errors

### Issue: Retry Budget Exhausted

**Symptoms**: Operations fail with `BudgetExceededError`

**Diagnosis**:
```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()
metrics = manager.get_metrics()
budget_status = metrics["retry_operations"]["budget_status"]["gitea_api"]

print(f"Current count: {budget_status['current_count']}")
print(f"Limit: {budget_status['limit']}")
print(f"Remaining: {budget_status['remaining']}")
print(f"Window TTL: {budget_status['window_ttl']}s")
```

**Resolution**:
1. Wait for the budget window to reset (1 minute)
2. Check for underlying service issues causing retries
3. Consider increasing the budget limit if legitimate high-volume operations

### Issue: ACP Components Unavailable

**Symptoms**: Logs show "ACP Component not available, using local fallback"

**Diagnosis**:
```python
from scripts.pr_lifecycle.acp_integration import get_global_manager

manager = get_global_manager()
health = manager.check_health()

print(f"Circuit Breaker Registry: {health.circuit_breaker_registry}")
print(f"Retry Coordinator: {health.retry_coordinator}")
print(f"Self-Healing Engine: {health.self_healing_engine}")
print(f"Incident Manager: {health.incident_manager}")
print(f"Rollback Coordinator: {health.rollback_coordinator}")
```

**Resolution**:
1. Check if ACP services are running
2. Verify Redis connectivity
3. Check ACP service logs for errors
4. System will use local fallbacks - functionality is maintained with reduced features

### Issue: High Retry Rate

**Symptoms**: Many retry attempts, operations are slow

**Diagnosis**:
```python
metrics = manager.get_metrics()
failures = metrics["retry_operations"]["failures"]

for key, count in failures.items():
    service, reason = key.split(":")
    print(f"{service}: {reason} = {count}")
```

**Resolution**:
1. Identify the service with high failure rate
2. Check service health and logs
3. Consider adjusting retry policy (increase base_delay, reduce max_attempts)
4. Investigate root cause of failures

---

## Operational Procedures

### Pre-Deployment Checklist

- [ ] ACP components are healthy
- [ ] Circuit breakers are in CLOSED state
- [ ] Retry budgets are not exhausted
- [ ] Redis connectivity is verified
- [ ] InfluxDB metrics export is working (if enabled)

### Circuit Breaker Maintenance

**Periodic Review**:
```bash
# Check all circuit breaker states
python3 -c "
from scripts.pr_lifecycle.acp_integration import get_global_manager
manager = get_global_manager()
states = manager._circuit_registry.get_all_states()
for name, state in states.items():
    print(f'{name}: {state[\"state\"]}')
"
```

**Reset After Maintenance**:
```python
# After service maintenance, reset the circuit breaker
manager._circuit_registry.reset_all()
```

### Incident Response

**View Active Incidents**:
```python
# If ACP Incident Manager is available
from autonomous_control_plane.components.incident_manager import IncidentManager

im = IncidentManager()
incidents = im.list_active_incidents()
for incident in incidents:
    print(f"{incident.incident_id}: {incident.title} ({incident.severity})")
```

**Acknowledge Incident**:
```python
im.acknowledge_incident(incident_id, acknowledged_by="operator_name")
```

### Performance Tuning

**Adjusting Circuit Breaker Thresholds**:
```python
from circuit_breaker_pr import CircuitBreakerConfig

# Create custom config for high-latency service
config = CircuitBreakerConfig(
    failure_threshold=10,  # More tolerant
    recovery_timeout=120.0,  # Longer recovery time
    half_open_max_calls=5,
    success_threshold=3,
)

# Apply to circuit breaker
cb = manager._circuit_registry.get_circuit_breaker("slow_service")
cb._config = config
```

**Adjusting Retry Policy**:
```python
from retry_pr_operations import RetryPolicy

# More aggressive retry for critical operations
critical_policy = RetryPolicy(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    budget_limit_per_minute=20,
)

result = manager._retry_coordinator.execute_with_retry(
    service_name="critical_service",
    operation_name="critical_op",
    func=operation,
    policy=critical_policy,
)
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ACP_ENABLE_CIRCUIT_BREAKER` | Enable circuit breaker | `true` |
| `ACP_ENABLE_RETRY_COORDINATOR` | Enable retry coordinator | `true` |
| `ACP_ENABLE_SELF_HEALING` | Enable self-healing engine | `true` |
| `ACP_ENABLE_INCIDENT_MANAGER` | Enable incident manager | `true` |
| `ACP_ENABLE_ROLLBACK_COORDINATOR` | Enable rollback coordinator | `true` |
| `ACP_GRACEFUL_DEGRADATION_TIMEOUT` | Timeout for ACP calls | `5.0` |
| `ACP_FALLBACK_TO_LOCAL` | Use local fallback if ACP unavailable | `true` |

### Redis Keys

| Key Pattern | Description |
|-------------|-------------|
| `acp:circuit_breaker:*` | Circuit breaker states |
| `acp:retry_budget:*` | Retry budget counters |
| `acp:incidents:*` | Active incidents |
| `acp:healing:*` | Self-healing actions |

---

## Related Documentation

- [EP-NS-008 ACP Architecture](../../docs/architecture/acp.md)
- [Circuit Breaker Pattern](../../docs/patterns/circuit-breaker.md)
- [Retry Pattern](../../docs/patterns/retry.md)
- [PR Lifecycle Management](./pr-lifecycle.md)

---

## Support

For issues or questions:

1. Check this runbook for troubleshooting steps
2. Review logs in `/var/log/chiseai/pr_pipeline.log`
3. Check ACP dashboard at `http://localhost:3001` (Grafana)
4. Escalate to platform team for ACP component issues
