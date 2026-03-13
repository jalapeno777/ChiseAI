# Self-Healing Automation Architecture

## Overview

The Self-Healing Automation system provides comprehensive closed-loop remediation for the ChiseAI autonomous control plane. It extends the existing self-healing engine with full automation capabilities, runbook integration, and operational procedures.

## Components

### 1. Automation Controller (`controller.py`)

The Automation Controller is the core orchestration component that manages remediation workflows.

**Features:**
- Closed-loop remediation orchestration
- Integration with telemetry pipeline for metrics-driven healing
- Automated decision engine for healing action selection
- Escalation policies and thresholds
- Handles 50+ concurrent remediation workflows

**Key Classes:**
- `AutomationController`: Main controller class
- `RemediationWorkflow`: Workflow instance for a remediation
- `RemediationStep`: Individual step in a workflow
- `DecisionRule`: Rule for automated action selection
- `EscalationPolicy`: Policy for handling failures

**Usage:**
```python
from autonomous_control_plane.automation import AutomationController
from autonomous_control_plane.models.healing import FailurePatternType

controller = AutomationController(trading_mode="paper")
workflow = await controller.start_remediation(
    service="redis",
    pattern_type=FailurePatternType.REDIS_DISCONNECT
)
```

### 2. Runbook Engine (`runbook_engine.py`)

The Runbook Engine provides structured procedure automation with human approval checkpoints.

**Features:**
- Step-by-step procedure automation
- Human approval checkpoints
- Automatic rollback on step failure
- Parallel and sequential step execution
- Step latency <1s target

**Key Classes:**
- `RunbookEngine`: Main engine class
- `Runbook`: Procedure definition
- `RunbookStep`: Individual step in a runbook
- `RunbookExecution`: Execution instance

**Usage:**
```python
from autonomous_control_plane.automation import RunbookEngine, RunbookStep

engine = RunbookEngine(trading_mode="paper")
runbook = engine.create_runbook("Redis Recovery")
runbook.add_step(RunbookStep(
    name="Check Redis Status",
    action="check_redis_status",
    action_type="python"
))
execution = await engine.execute_runbook(runbook)
```

### 3. Remediation Workflows (`workflows/remediation_workflows.py`)

Provides 12+ predefined workflows for common failure scenarios.

**Available Workflows:**
1. **Redis Connection Recovery** - Recover Redis connections
2. **API Timeout Remediation** - Handle API timeouts with backoff
3. **Circuit Breaker Reset Sequence** - Reset tripped circuit breakers
4. **Service Restart with Health Checks** - Graceful service restart
5. **Database Connection Recovery** - Reset DB connection pools
6. **Memory Exhaustion Remediation** - Clear caches and free memory
7. **Disk Space Cleanup** - Clean temporary files and logs
8. **CPU Spike Mitigation** - Throttle and restart services
9. **InfluxDB Write Recovery** - Recover failed metric writes
10. **Dead Letter Queue Processing** - Process failed messages
11. **Service Health Recovery** - Comprehensive health restoration
12. **Configuration Reload** - Reload config without restart

**Usage:**
```python
from autonomous_control_plane.automation import RemediationWorkflows
from autonomous_control_plane.automation import RunbookEngine

engine = RunbookEngine()
workflows = RemediationWorkflows(engine)

# Create specific workflow
runbook = workflows.create_redis_recovery_runbook("redis")

# Or create by pattern type
from autonomous_control_plane.models.healing import FailurePatternType
runbook = workflows.create_workflow_for_pattern(
    FailurePatternType.REDIS_DISCONNECT
)
```

### 4. Healing Actions (`healing_actions/`)

Extended action library with automatic rollback capability.

**Actions:**
- `RedisRestartAction` - Restart Redis connections
- `APIRetryAction` - Retry API calls with backoff
- `CircuitBreakerResetAction` - Reset circuit breakers
- `ServiceRestartAction` - Restart services with health checks
- `ConfigReloadAction` - Reload configuration
- `ConnectionPoolResetAction` - Reset DB connection pools
- `CacheFlushAction` - Flush application caches
- `HealthCheckAction` - Perform comprehensive health checks

**All actions support:**
- Automatic rollback on failure
- Resource limits and sandboxing
- Human approval gates for P0/P1 in live mode
- Comprehensive logging

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Automation Controller                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Decision   │  │   Workflow   │  │   Escalation     │  │
│  │    Engine    │  │   Manager    │  │    Handler       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────┬───────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌─────────────┐
│   Runbook    │ │ Self-    │ │  Telemetry  │
│    Engine    │ │ Healing  │ │   Export    │
└──────────────┘ │  Engine  │ └─────────────┘
                 └──────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌──────────────┐ ┌─────────┐ ┌────────────┐
│  Predefined  │ │ Healing │ │  Runbook   │
│  Workflows   │ │ Actions │ │ Procedures │
└──────────────┘ └─────────┘ └────────────┘
```

## Integration Points

### Telemetry Pipeline Integration

The automation controller integrates with the telemetry pipeline for metrics-driven healing:

```python
# Metrics are automatically exported
collector = TelemetryCollector()
collector.record(
    measurement="remediation_workflow",
    tags={"service": "redis", "status": "completed"},
    fields={"duration_seconds": 45.0}
)
```

### Self-Healing Engine Integration

The automation controller uses the existing self-healing engine for action execution:

```python
# Controller delegates to healing engine
result = await self._healing_engine.process_log_entry(log_entry)
```

### Human Approval Gates

P0/P1 actions in live/production mode require human approval:

```python
if action.requires_human_approval("production"):
    # Queue for approval
    await self._request_approval(attempt)
```

## Configuration

### Decision Rules

Define custom decision rules for action selection:

```python
from autonomous_control_plane.automation import DecisionRule

rule = DecisionRule(
    name="custom_redis_rule",
    pattern_types=[FailurePatternType.REDIS_DISCONNECT],
    conditions={"service": "critical_redis"},
    action_type="redis_restart",
    priority=100
)
controller.register_decision_rule(rule)
```

### Escalation Policies

Configure escalation behavior:

```python
from autonomous_control_plane.automation import EscalationPolicy, EscalationLevel

policy = EscalationPolicy(
    max_auto_attempts=3,
    escalation_delay_seconds=300,
    notify_channels=["slack", "pagerduty"],
    auto_escalate_to=EscalationLevel.APPROVE
)
```

## Safety Controls

### Anti-Flap Protection

- Maximum 3 healing attempts per hour per service
- Global healing budget (20 healings per hour)
- Kill switch for emergency stop

### Approval Gates

- P0/P1 actions require approval in live/production mode
- Configurable approval timeout
- Audit trail for all approvals

### Rollback

- Automatic rollback on failure
- 30-second rollback window
- State capture before healing

## Monitoring

### Metrics

- `remediation_workflow`: Workflow execution metrics
- `remediation_escalation`: Escalation events
- `healing_attempt`: Individual healing attempts

### Status API

```python
# Get controller status
status = controller.get_status()

# Get active workflows
active = controller.get_active_workflows()

# Get workflow status
workflow_status = controller.get_workflow_status(workflow_id)
```

## Testing

### Unit Tests

```bash
pytest tests/test_autonomous_control_plane/test_automation/ -v
```

### Live Remediation Test

```python
# Test complete remediation cycle
controller = AutomationController()
result = controller.test_live_remediation()
```

## References

- ST-CONTROL-002: Self-Healing Automation
- ST-CONTROL-001: Telemetry Pipeline (dependency)
- ST-NS-040: Self-Healing Engine with Action Sandboxing
