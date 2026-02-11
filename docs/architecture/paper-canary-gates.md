# Paper Canary Planning & Gates Architecture

**Story ID:** ST-BT-002  
**Epic ID:** EP-BT-001  
**Status:** Implemented

## Overview

The Paper Canary system provides safe deployment of new trading strategies through:
- Limited exposure (10% of paper portfolio)
- Automated gate criteria validation
- Automatic rollback on failure
- 15-minute monitoring intervals
- Human-gated promotion to paper full

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Paper Canary System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ CanaryDeployment │    │   GateCriteria   │                  │
│  │  - 10% allocation│    │  - Max 5% DD     │                  │
│  │  - 7-day duration│    │  - Min 55% WR    │                  │
│  │  - Metrics       │    │  - Min 10 trades │                  │
│  └────────┬─────────┘    └──────────────────┘                  │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────┐          │
│  │              GateEvaluator                        │          │
│  │  - evaluate_drawdown()                           │          │
│  │  - evaluate_win_rate()                           │          │
│  │  - evaluate_duration()                           │          │
│  │  - determine_status()                            │          │
│  └────────────────────┬─────────────────────────────┘          │
│                       │                                         │
│           ┌───────────┴───────────┐                            │
│           ▼                       ▼                            │
│  ┌──────────────────┐   ┌──────────────────┐                  │
│  │  CanaryMonitor   │   │ RollbackHandler  │                  │
│  │  - 15min checks  │   │  - Auto rollback │                  │
│  │  - Gate checks   │   │  - To champion   │                  │
│  │  - Persist results│  │  - Logging       │                  │
│  └────────┬─────────┘   └──────────────────┘                  │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────────────┐          │
│  │         PromotionPacketGenerator                  │          │
│  │  - Evidence collection                            │          │
│  │  - Risk assessment                                │          │
│  │  - Rollback plan                                  │          │
│  │  - Markdown output                                │          │
│  └────────────────────┬─────────────────────────────┘          │
│                       │                                         │
│           ┌───────────┴───────────┐                            │
│           ▼                       ▼                            │
│  ┌──────────────────┐   ┌──────────────────┐                  │
│  │  CanaryStorage   │   │  Grafana Panels  │                  │
│  │  - In-memory     │   │  - Metrics       │                  │
│  │  - InfluxDB      │   │  - Status        │                  │
│  └──────────────────┘   └──────────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Models (`models.py`)

**CanaryDeployment:**
- Unique canary ID
- Strategy ID being tested
- Champion strategy ID (for rollback)
- 10% default allocation
- Gate criteria configuration
- Metrics collection

**GateCriteria:**
- Max drawdown: 5%
- Min win rate: 55%
- Duration: 7 days
- Min trades: 10

**CanaryMetrics:**
- Equity tracking (start/current/peak)
- Trade counting (total/win/loss)
- PnL tracking
- Win rate calculation
- Drawdown calculation

### 2. Gate Evaluator (`gate_evaluator.py`)

Evaluates three primary gates:

**Drawdown Gate:**
```python
if max_drawdown_pct > 5.0:
    return FAIL
else:
    return PASS
```

**Win Rate Gate:**
```python
if total_trades < 10:
    return PENDING
if win_rate_pct < 55.0:
    return FAIL
else:
    return PASS
```

**Duration Gate:**
```python
if elapsed_days < 7:
    return PENDING
else:
    return PASS
```

### 3. Rollback Handler (`rollback.py`)

**Automatic Rollback Triggers:**
- Drawdown exceeds 5%
- Win rate below 55% (after min trades)

**Rollback Process:**
1. Halt new positions for candidate
2. Close existing positions
3. Activate champion strategy
4. Log rollback event

### 4. Monitor (`monitor.py`)

**15-Minute Check Cycle:**
```python
async def monitoring_loop():
    while running:
        await run_all_checks()
        await sleep(15 * 60)  # 15 minutes
```

**Check Actions:**
- `continue`: All gates pending/passing
- `rollback`: Any gate failed
- `ready_for_promotion`: All gates passed

### 5. Storage (`storage.py`)

**In-Memory Storage:**
- Development and testing
- Fast access
- No persistence

**InfluxDB Storage (TODO):**
- Production deployment
- Grafana integration
- Historical analysis

### 6. Promotion Packet (`promotion.py`)

**Packet Contents:**
- Executive summary
- Key metrics table
- Risk assessment
- Rollback plan
- Approval checklist

**Markdown Output:**
```markdown
# Promotion Packet: {strategy_id}

## Executive Summary
Strategy completed canary testing and is requesting promotion...

## Key Metrics
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Duration | 7.5 days | 7 days | ✅ PASS |
| Win Rate | 60% | 55% | ✅ PASS |
| Max Drawdown | 3.5% | 5% | ✅ PASS |

## Approval
- [ ] I have reviewed the evidence
- [ ] I understand the risks
- [ ] I approve promotion to paper full
```

## Gate Criteria Reference

| Gate | Threshold | Check Frequency | Failure Action |
|------|-----------|-----------------|----------------|
| Max Drawdown | ≤5% | Every 15 min | Auto rollback |
| Min Win Rate | ≥55% | Every 15 min (after 10 trades) | Auto rollback |
| Duration | ≥7 days | Every 15 min | Block promotion |

## Usage Examples

### Basic Canary Deployment

```python
from execution.canary import (
    create_canary_deployment,
    CanaryMonitor,
    create_canary_monitor,
)

# Create canary
canary = create_canary_deployment(
    canary_id="canary-001",
    strategy_id="strategy-v2",
    champion_strategy_id="strategy-v1",
    allocation_pct=10.0,
)

# Start canary
canary.start(initial_equity=10000.0)

# Set up monitoring
monitor = create_canary_monitor()
monitor.register_canary(canary)
await monitor.start()
```

### Manual Gate Check

```python
from execution.canary import GateEvaluator

evaluator = GateEvaluator()
checks = evaluator.evaluate_all_gates(canary)

for check in checks:
    print(f"{check.gate_name}: {check.result.value} - {check.message}")
```

### Generate Promotion Packet

```python
from execution.canary import PromotionPacketGenerator

generator = PromotionPacketGenerator()
packet = generator.generate_packet(canary, "packet-001")

if packet:
    markdown = generator.generate_markdown_packet(packet)
    print(markdown)
```

## Integration Points

### Strategy Registry (ST-SIG-002)
- Champion/challenger tracking
- Strategy metadata
- Version history

### Promotion Packet Workflow (ST-BT-003)
- Evidence collection
- Human approval gating
- Rollback plan integration

### Grafana Dashboard
- Real-time metrics
- Gate status visualization
- Historical canary results

## Testing

Run canary-specific tests:
```bash
pytest tests/test_canary/ -v --cov=src/execution/canary
```

Test coverage includes:
- Model serialization
- Gate evaluation logic
- Rollback execution
- Monitor scheduling
- Promotion packet generation

## Future Enhancements

1. **InfluxDB Persistence:** Full InfluxDB integration for production
2. **Grafana Panels:** Pre-built dashboard panels for canary metrics
3. **Discord Alerts:** Notifications on gate failures/promotions
4. **Multi-Strategy Canaries:** Support for testing strategy combinations
5. **Adaptive Gates:** Dynamic thresholds based on market conditions
