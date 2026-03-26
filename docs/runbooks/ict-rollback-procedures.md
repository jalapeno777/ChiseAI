# ICT Rollback Procedures

> **Story:** ST-ICT-022  
> **Last Updated:** 2026-03-25  
> **Owner:** Platform Team / On-Call Engineer  
> **Status:** READY FOR USE

---

## 1. Overview

### 1.1 Purpose

This runbook provides **rollback procedures** for the ICT (Inner Circle Trader) confluence feature. It is designed for scenarios where rapid disablement is required to maintain system stability and trading safety.

### 1.2 Scope

| Component             | Description                                       | Story ID   |
| --------------------- | ------------------------------------------------- | ---------- |
| ICT Confluence Scorer | Layer 2 signal scoring with confluence algorithm  | ST-ICT-018 |
| Layer 1 Integration   | Market structure detection for confluence context | EP-ICT-005 |
| Feature Flag          | Redis-based kill switch for ICT features          | ST-ICT-018 |

### 1.3 Authority

| Role             | Can Execute Rollback | Notes                                               |
| ---------------- | -------------------- | --------------------------------------------------- |
| On-Call Engineer | ✅ Yes               | Primary responder; no additional approval needed    |
| SeniorDev        | ✅ Yes               | Can execute and approve rollbacks                   |
| Merlin           | ✅ Yes               | Can execute rollbacks; must document rationale      |
| Captain Craig    | ✅ Yes               | Final authority; can override any rollback decision |

---

## 2. Feature Flag Reference

### 2.1 Flag Location

```
Redis Key: ict:feature_flags:integration
Type: String (true/false)
Default: true
TTL: 3600 seconds
Database: 1
```

### 2.2 Related Flags

| Flag                            | Description                            | Default |
| ------------------------------- | -------------------------------------- | ------- |
| `ict:feature_flags:integration` | Master kill switch for ICT integration | `true`  |
| `ict:feature_flags:cvd`         | CVD (Change of Character) signals      | `true`  |
| `ict:feature_flags:fvg`         | FVG (Fair Value Gap) signals           | `true`  |
| `ict:feature_flags:order_block` | Order Block signals                    | `true`  |
| `ict:feature_flags:bos_choch`   | BOS/CHoCH signals (SAFETY - disabled)  | `false` |

### 2.3 Flag Commands

```bash
# Check current status
redis-cli -h host.docker.internal -p 6380 -n 1 GET ict:feature_flags:integration

# Disable ICT integration (ROLLBACK)
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false

# Enable ICT integration (RE-DEPLOY)
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration true

# Check all ICT flags
redis-cli -h host.docker.internal -p 6380 -n 1 KEYS "ict:feature_flags:*"
```

---

## 3. Rollback Scenarios

### 3.1 Scenario 1: Validation Failure

**Trigger:** Statistical validation fails (p-value > 0.05 after minimum signals)

**Indicators:**

- Grafana alert: `ict_validation_pvalue > 0.05`
- Truth gate failure on validation metrics
- Backtest correlation below threshold

**Automated Actions:**

- Validation script exits with non-zero code
- Discord notification to `#trading-alerts`
- Incident created in tracking system

**Response Procedure:**

1. Verify validation failure:
   ```bash
   pytest scripts/validation/test_ict_rollback.py -v
   ```
2. Disable ICT integration:
   ```bash
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false
   ```
3. Verify flag is disabled:
   ```bash
   redis-cli -h host.docker.internal -p 6380 -n 1 GET ict:feature_flags:integration
   # Expected: "false"
   ```
4. Confirm system continues operating:
   ```bash
   curl -s http://localhost:8080/health | jq '.status'
   # Expected: "healthy"
   ```
5. Document findings in incident ticket

### 3.2 Scenario 2: Performance Degradation

**Trigger:** Trading performance drops beyond acceptable thresholds

**Indicators:**

- Win rate drop > 5% from baseline
- Latency increase > 500ms on signal generation
- Drawdown exceeds risk limits

**Performance Thresholds:**

| Metric             | Warning | Critical | Rollback |
| ------------------ | ------- | -------- | -------- |
| Win rate drop      | > 2%    | > 5%     | > 5%     |
| Signal latency p95 | > 200ms | > 500ms  | > 500ms  |
| Drawdown           | > 3%    | > 5%     | > 5%     |

**Response Procedure:**

1. Check performance metrics:

   ```bash
   # Check latency
   curl -s http://localhost:9090/metrics | grep ict_signal_latency

   # Check win rate
   redis-cli -h host.docker.internal -p 6380 GET chiseai:trading:win_rate:current
   ```

2. If critical threshold breached, execute rollback:
   ```bash
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false
   ```
3. Monitor system stability for 5 minutes
4. Document metrics before and after rollback

### 3.3 Scenario 3: Safety Issue

**Trigger:** Exception or error state in Layer 1 or confluence code

**Indicators:**

- Exception in signal aggregator logs
- Unhandled error in confluence modifier
- Invalid signal detected (NaN, extreme values)

**Safety Limits:**

| Check                | Limit           | Action              |
| -------------------- | --------------- | ------------------- |
| Signal value         | Must be 0.0-1.0 | Reject out-of-range |
| Confluence score     | Must be 0.0-1.0 | Clamp to range      |
| Exception in Layer 1 | Any unhandled   | Disable confluence  |
| NaN/Infinity         | Must not exist  | Reject signal       |

**Response Procedure:**

1. Check logs for exception:
   ```bash
   docker logs chiseai-brain-scheduler --tail 100 | grep -i "exception\|error\|traceback"
   ```
2. Immediately disable to prevent cascade:
   ```bash
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:cvd false
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:fvg false
   redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:order_block false
   ```
3. Verify no signals being generated:
   ```bash
   redis-cli -h host.docker.internal -p 6380 -n 1 GET ict:feature_flags:integration
   # Expected: "false"
   ```
4. Capture logs for debugging:
   ```bash
   docker logs chiseai-brain-scheduler > /tmp/ict-rollback-$(date +%Y%m%d-%H%M%S).log
   ```
5. File incident report with log attachment

---

## 4. Rollback Execution

### 4.1 Quick Rollback (One-Liner)

```bash
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false
```

### 4.2 Full Rollback with Verification

```bash
#!/bin/bash
# ICT Integration Full Rollback Script

set -e

REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
REDIS_PORT="${REDIS_PORT:-6380}"
REDIS_DB=1

echo "=== ICT Integration Rollback ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Disable flags
echo "Disabling ICT integration..."
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" SET ict:feature_flags:integration false
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" SET ict:feature_flags:cvd false
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" SET ict:feature_flags:fvg false
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" SET ict:feature_flags:order_block false

# Verify
INTEGRATION=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" GET ict:feature_flags:integration)

echo ""
echo "Verification:"
echo "  ICT_INTEGRATION_ENABLED: $INTEGRATION"

if [ "$INTEGRATION" != "false" ]; then
    echo "ERROR: Rollback failed - integration flag not disabled"
    exit 1
fi

echo ""
echo "✅ Rollback successful"
```

### 4.3 Post-Rollback Validation

```bash
# Run the rollback test suite
pytest scripts/validation/test_ict_rollback.py -v

# Verify no ICT signals in recent output
redis-cli -h host.docker.internal -p 6380 -n 1 LRANGE chiseai:signals:recent 0 9

# Check system health
curl -s http://localhost:8080/health
```

---

## 5. Recovery After Rollback

### 5.1 Investigation Requirements

Before re-enabling ICT confluence, complete these investigations:

| Requirement           | Description                        | Evidence             |
| --------------------- | ---------------------------------- | -------------------- |
| Root cause identified | What caused the issue?             | Incident ticket      |
| Fix planned           | How will it be prevented?          | Engineering ticket   |
| Test coverage         | Are there tests for this scenario? | Test evidence        |
| Monitoring added      | Can we detect this earlier?        | Dashboard screenshot |

### 5.2 Re-Enable Procedure

```bash
# 1. Verify investigation complete
# 2. Apply fix
# 3. Enable in staging first
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration true

# 4. Run validation
pytest scripts/validation/test_ict_rollback.py -v

# 5. Monitor for 1 hour before full deploy
```

---

## 6. Monitoring and Alerts

### 6.1 Alert Definitions

| Alert                 | Condition               | Severity | Action             |
| --------------------- | ----------------------- | -------- | ------------------ |
| `ict_validation_fail` | Validation script fails | Medium   | Investigate        |
| `ict_latency_high`    | p95 latency > 500ms     | High     | Disable confluence |
| `ict_exception`       | Unhandled exception     | Critical | Immediate rollback |
| `ict_winrate_drop`    | Win rate drop > 5%      | High     | Disable confluence |

### 6.2 Dashboard Queries

```promql
# ICT Signal Latency
histogram_quantile(0.95, rate(ict_signal_latency_seconds_bucket[5m]))

# ICT Signal Volume
rate(ict_signals_total[5m])

# Confluence Score Distribution
histogram_quantile(0.5, rate(ict_confluence_score_bucket[5m]))
```

---

## 7. Contact Information

| Role             | Contact                       | Response SLA |
| ---------------- | ----------------------------- | ------------ |
| On-Call Engineer | PagerDuty → `#trading-alerts` | < 2 min      |
| SeniorDev        | `@seniordev`                  | < 5 min      |
| Merlin           | `@merlin`                     | < 10 min     |
| Captain Craig    | `@captain-craig`              | < 15 min     |

---

## 8. References

- Feature Flag Implementation: `docs/architecture/ict-two-layer-pipeline.md`
- ICT Layer 2 Confirmation: `docs/architecture/ict-layer-2-confirmation.md`
- Validation Test: `scripts/validation/test_ict_rollback.py`
- ICT Learnings: `docs/tempmemories/ict-rollback-learnings.md`
