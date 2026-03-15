# Checkpoint Governance Module

## Overview

The Checkpoint Governance Module provides automated checkpoint auditing and governance gate validation to ensure system health and compliance during trading operations. It implements the G1-G9 checkpoint gates that validate critical system components before and during trading.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CheckpointManager                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ GateChecker │  │ EvidenceCollector│ │ StateManager     │  │
│  │   (G1-G9)   │  │               │  │                  │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼────────────────┼───────────────────┼────────────┘
          │                │                   │
          ▼                ▼                   ▼
    ┌──────────┐    ┌──────────┐     ┌──────────────┐
    │  Redis   │    │  Redis   │     │    Redis     │
    │ Gates    │    │ Evidence │     │    State     │
    └──────────┘    └──────────┘     └──────────────┘
          │                │                   │
          └────────────────┴───────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Discord    │
                    │ Notification │
                    └──────────────┘
```

## Module Structure

```
src/governance/checkpoint/
├── __init__.py           # Public API exports
├── checkpoint.py         # CheckpointManager orchestration
├── gates.py              # GateChecker (G1-G9 implementations)
├── alerts.py             # ActionableZeroAlert monitoring
├── evidence.py           # EvidenceCollector for audit trails
└── state.py              # StateManager for checkpoint history
```

## Checkpoint Gates (G1-G9)

| Gate | Name | Purpose | Status |
|------|------|---------|--------|
| G1 | Scheduler Continuity | Validates scheduler heartbeat freshness | ✅ Active |
| G2 | Signal Cadence | Checks signal generation with 4-state taxonomy | ✅ Active |
| G3 | Data Flow Movement | Validates outcomes are being recorded | ✅ Active |
| G4 | Kill Switch Active | Verifies kill switch is armed and ready | ✅ Active |
| G5 | Cron Job Cadence | Checks cron jobs execute on schedule | ✅ Active |
| G6 | Bybit Connectivity | Tests API reachability | ✅ Active |
| G7 | Observability Health | Validates Redis health and uptime | ✅ Active |
| G8 | End-to-End Pipeline | Burn-in verdict integration | ✅ Active |
| G9 | Metric Integrity | Validates aggregates match raw data | ✅ Active |

### G2 Signal Cadence Taxonomy

The G2 gate implements a 4-state taxonomy for signal pipeline health:

#### NO_SIGNALS
- **Meaning:** No signals generated in the 15-minute window
- **Status:** ✅ PASS when pipeline is healthy, ❌ FAIL when pipeline is stale
- **Cause:** Normal idle state when market conditions don't trigger signals

#### FILTERED
- **Meaning:** Signals generated but none actionable
- **Status:** ✅ PASS (filters working as designed)
- **Cause:** Confidence thresholds filtering out low-confidence signals
- **Alert:** ActionableZeroAlert fires after 3 consecutive windows

#### BOTTLENECK
- **Meaning:** Actionable signals present but downstream processing stalled
- **Status:** ⚠️ CHECK (non-blocking warning)
- **Cause:** Consumer backlog exceeds threshold (default: 10)

#### HEALTHY
- **Meaning:** Normal operation with signals flowing through pipeline
- **Status:** ✅ PASS
- **Cause:** All pipeline components functioning normally

## Usage Examples

### Basic Gate Checking

```python
from src.governance.checkpoint import GateChecker

# Create checker
checker = GateChecker()

# Check specific gate
result = checker.check_g2_signal_cadence()
print(f"{result.gate}: {result.status} - {result.detail}")
# Output: G2: ✅ PASS - HEALTHY: 12 signals, 3 actionable, backlog 2 (normal)

# Run all gates
summary = checker.run_all_checks()
print(f"Overall: {summary.overall_status}")
print(f"Pass: {summary.pass_count}, Fail: {summary.fail_count}, Check: {summary.check_count}")
```

### Full Checkpoint Audit

```python
from src.governance.checkpoint import CheckpointManager

# Create manager with default config
manager = CheckpointManager()

# Run checkpoint (async)
report = await manager.run_checkpoint()

# Check results
if report.success:
    print("✅ All gates passing")
else:
    print(f"❌ {report.summary.fail_count} gates failing")
    
# Access evidence
evidence = report.evidence
print(f"Evidence stored at: {evidence.redis_key}")
```

### Custom Configuration

```python
from src.governance.checkpoint import CheckpointManager
from src.governance.checkpoint.checkpoint import CheckpointConfig

config = CheckpointConfig(
    redis_host="custom-redis",
    redis_port=6380,
    discord_channel_id="123456789",
    auto_notify=True,
    auto_archive=True,
)

manager = CheckpointManager(config=config)
report = await manager.run_checkpoint()
```

### Actionable-Zero Alert

```python
from src.governance.checkpoint import ActionableZeroAlert

# Create alert checker
alert = ActionableZeroAlert()

# Check current state
result = alert.check()
if result.should_alert:
    print(f"🚨 Actionable-zero detected! Windows: {result.consecutive_windows}")
    
# Check with suppression
result = alert.check(suppress_for_minutes=60)
if result.suppressed:
    print(f"Alert suppressed until: {result.suppressed_until}")
```

## Integration Points

### Pre-Trade Validation

```python
from src.governance.checkpoint import GateChecker

def validate_before_trade():
    """Validate all gates before executing trades."""
    checker = GateChecker()
    summary = checker.run_all_checks()
    
    if summary.overall_status == "FAIL":
        failing = [r.gate for r in summary.results if r.status.startswith("❌")]
        raise RuntimeError(f"Cannot trade: gates failing: {failing}")
    
    return summary
```

### CI/CD Integration

```python
# scripts/check_gates.py
import sys
from src.governance.checkpoint import GateChecker

def main():
    checker = GateChecker()
    summary = checker.run_all_checks()
    
    # Exit with error if any gate fails
    if summary.overall_status == "FAIL":
        print("❌ Checkpoint gates failing - blocking deployment")
        sys.exit(1)
    
    print("✅ All checkpoint gates passing")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### Discord Notifications

The checkpoint module automatically sends Discord notifications when:
- A gate fails (immediate alert)
- A gate recovers (recovery notification)
- Daily summary at configured time

Configure via environment variables:
```bash
export DISCORD_DEVELOPMENT_CHANNEL_ID="123456789"
export DISCORD_BOT_TOKEN="your-bot-token"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

## Redis Key Reference

| Key | Type | Description |
|-----|------|-------------|
| `bmad:chiseai:scheduler:heartbeat` | Hash | Scheduler status and metrics |
| `bmad:chiseai:kill_switch` | Hash | Kill switch configuration |
| `bmad:chiseai:outcomes:index` | Set | Index of all outcome IDs |
| `bmad:chiseai:signals:*` | Hash | Individual signal data |
| `bmad:chiseai:signals:index` | Set | Index of all signal IDs |
| `bmad:chiseai:burnin:verdict` | String | Burn-in verdict (GO/NO-GO) |
| `bmad:chiseai:cron:*` | Hash | Cron job execution evidence |
| `bmad:chiseai:checkpoint:latest` | Hash | Latest checkpoint results |
| `bmad:chiseai:checkpoint:history` | List | Historical checkpoint results |
| `bmad:chiseai:alerts:actionable_zero` | Hash | Actionable-zero alert state |
| `bmad:chiseai:metric_integrity:latest` | Hash | Latest integrity check results |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `host.docker.internal` | Redis hostname |
| `REDIS_PORT` | `6380` | Redis port |
| `MONITORING_REDIS_HOST` | - | Alternative Redis host (falls back to REDIS_HOST) |
| `MONITORING_REDIS_PORT` | - | Alternative Redis port (falls back to REDIS_PORT) |
| `G2_BACKLOG_THRESHOLD` | `10` | Backlog threshold for bottleneck detection |
| `DISCORD_DEVELOPMENT_CHANNEL_ID` | - | Discord channel for notifications |
| `DISCORD_BOT_TOKEN` | - | Discord bot token |
| `DISCORD_WEBHOOK_URL` | - | Discord webhook URL for notifications |
| `CHECKPOINT_ARCHIVE_DIR` | `logs/checkpoints` | Directory for checkpoint archives |

## Testing

```bash
# Run gate checks manually
python -c "
from src.governance.checkpoint import GateChecker
checker = GateChecker()
summary = checker.run_all_checks()
for r in summary.results:
    print(f'{r.gate}: {r.status} - {r.detail}')
"

# Test specific gate
python -c "
from src.governance.checkpoint import GateChecker
print(GateChecker().check_g2_signal_cadence())
"
```

## Troubleshooting

### Gate Check Fails with "Redis unavailable"

1. Verify Redis is running:
   ```bash
   docker ps --filter name=chiseai-redis
   ```

2. Test connection:
   ```bash
   redis-cli -h host.docker.internal -p 6380 ping
   ```

3. Check environment variables:
   ```bash
   echo $REDIS_HOST $REDIS_PORT
   ```

### G2 Shows FILTERED State Continuously

1. Check confidence threshold:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:config confidence_threshold
   ```

2. Review signal quality in Grafana

3. See [Observability Guardrails](../../docs/runbooks/observability-guardrails.md)

### G9 Metric Integrity Fails

1. Check raw signal count:
   ```bash
   redis-cli -h host.docker.internal -p 6380 SCARD bmad:chiseai:signals:index
   ```

2. Compare to aggregate:
   ```bash
   redis-cli -h host.docker.internal -p 6380 HGET bmad:chiseai:scheduler:heartbeat signals_15m
   ```

3. See [Checkpoint Gates Runbook](../../docs/runbooks/checkpoint-gates.md)

## Related Documentation

- [Checkpoint Gates Runbook](../../docs/runbooks/checkpoint-gates.md) - Detailed gate reference
- [Observability Guardrails](../../docs/runbooks/observability-guardrails.md) - Actionable-zero alert and metric integrity
- [Kill Switch Runbook](../../docs/runbooks/kill-switch-trigger.md) - Emergency procedures
- [Incident Response](../../docs/runbooks/incident_response.md) - Incident handling

## Story Reference

- **Story:** PAPER-GOVERNANCE-001
- **Epic:** EP-GOV-001
- **Last Updated:** 2026-03-14
