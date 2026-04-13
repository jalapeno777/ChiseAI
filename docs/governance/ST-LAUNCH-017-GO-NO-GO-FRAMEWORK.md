# Go/No-Go Metrics Framework

**Story:** ST-LAUNCH-017  
**Created:** April 13, 2026  
**Status:** Draft — Ready for Apr 26 Canary Validation

---

## Part A: Infrastructure Validation (Feb 26 Baseline — ALL PASS)

All 11 items below were validated as PASS on February 26, 2026. These form the infrastructure foundation for canary live-trading.

| Item ID | Item Name                | Target Criteria                                                                                                | Status | Evidence Reference                |
| ------- | ------------------------ | -------------------------------------------------------------------------------------------------------------- | ------ | --------------------------------- |
| A1      | Docker Networking        | `chiseai` network exists, containers can reach each other                                                      | PASS   | `docker network inspect chiseai`  |
| A2      | Redis Connectivity       | `redis-cli ping` returns `PONG`                                                                                | PASS   | Container logs, `redis-cli ping`  |
| A3      | PostgreSQL Accessibility | Trade database queryable via configured credentials                                                            | PASS   | Connection string validated       |
| A4      | Container Labels         | All ChiseAI containers have `project=chiseai` label                                                            | PASS   | `docker inspect` output           |
| A5      | Protected Containers     | No accidental modification to `tradedev`, `intelligent_ride`, `aisetup-mcp-discord-1`, `duckduckgo-mcp-server` | PASS   | Protected container list verified |
| A6      | Network Connectivity     | `host.docker.internal` resolves from container context                                                         | PASS   | DNS resolution confirmed          |
| A7      | Governance Scripts       | `validate_docker_connectivity.py` passes                                                                       | PASS   | Script exit code 0                |
| A8      | Service Discovery        | Containers can resolve each other by name                                                                      | PASS   | Container-to-container DNS        |
| A9      | Discord MCP Config       | `aisetup-mcp-discord-1` container healthy and connected                                                        | PASS   | Container health check            |
| A10     | Grafana Accessibility    | Grafana endpoint reachable from agent context                                                                  | PASS   | HTTP response 200                 |
| A11     | Strategy DSL Schema      | Valid JSON schema for strategy configuration                                                                   | PASS   | Schema validation passed          |

> **Note:** Infrastructure items A1-A11 are already validated and passing. They do not need re-validation at Apr 26 but should be spot-checked.

---

## Part B: Canary Live-Trading Criteria (14 Items)

The following 14 criteria govern whether the canary goes live. **HARD** blocks must all pass. **SOFT** blocks are monitored but do not independently block launch.

| Criterion ID | Criterion Name       | Target                     | Block Type | Validation Method                              |
| ------------ | -------------------- | -------------------------- | ---------- | ---------------------------------------------- |
| B1           | OHLCV Data Ingestion | 95%+ uptime                | HARD       | Check container logs, Grafana uptime panel     |
| B2           | Signal Generation    | 100+ signals/day sustained | HARD       | Redis query: `ZCARD signals:generated`         |
| B3           | Consumer Polling     | Continuous health checks   | HARD       | Container process running, polling loop active |
| B4           | Durable Storage      | Redis signal persistence   | HARD       | `redis-cli GET last_signal_timestamp` exists   |
| B5           | Discord Delivery     | Alerts functional          | HARD       | Check Discord channel for recent messages      |
| B6           | Grafana Dashboard    | Health metrics visible     | SOFT       | Screenshot of key panels at Apr 26             |
| B7           | Error Rate           | Below 5%                   | SOFT       | Grafana error rate panel < 5%                  |
| B8           | Signal Latency       | P95 < 5s                   | SOFT       | Grafana latency histogram                      |
| B9           | Order Execution      | Demo connector functional  | HARD       | Test order submitted and acknowledged          |
| B10          | Position Tracking    | Stateful                   | SOFT       | Redis contains position data                   |
| B11          | Risk Guards          | Exposure caps enforced     | HARD       | Check risk config in Redis                     |
| B12          | Circuit Breaker      | Functional                 | HARD       | Test circuit breaker trigger/recovery          |
| B13          | Kill Switch          | Responsive < 30s           | HARD       | Manual trigger test                            |
| B14          | Burn-in Tracking     | PnL recorded               | SOFT       | Grafana PnL panel shows data                   |

---

## Part C: Fillable Go/No-Go Decision Template

Use this table at the Apr 26 checkpoint to record actual values and determine Go/No-Go status.

| Criterion ID | Criterion Name           | Target                        | Actual (TO BE FILLED) | Status (TO BE DETERMINED) | Notes (TO BE FILLED) |
| ------------ | ------------------------ | ----------------------------- | --------------------- | ------------------------- | -------------------- |
| A1           | Docker Networking        | `chiseai` network exists      |                       |                           |                      |
| A2           | Redis Connectivity       | `PONG` response               |                       |                           |                      |
| A3           | PostgreSQL Accessibility | Queryable                     |                       |                           |                      |
| A4           | Container Labels         | All labeled `project=chiseai` |                       |                           |                      |
| A5           | Protected Containers     | Unmodified                    |                       |                           |                      |
| A6           | Network Connectivity     | DNS resolves                  |                       |                           |                      |
| A7           | Governance Scripts       | Exit 0                        |                       |                           |                      |
| A8           | Service Discovery        | Name resolution works         |                       |                           |                      |
| A9           | Discord MCP Config       | Healthy                       |                       |                           |                      |
| A10          | Grafana Accessibility    | HTTP 200                      |                       |                           |                      |
| A11          | Strategy DSL Schema      | Valid JSON                    |                       |                           |                      |
| B1           | OHLCV Data Ingestion     | 95%+ uptime                   |                       |                           |                      |
| B2           | Signal Generation        | 100+ signals/day              |                       |                           |                      |
| B3           | Consumer Polling         | Continuous                    |                       |                           |                      |
| B4           | Durable Storage          | Signal persisted              |                       |                           |                      |
| B5           | Discord Delivery         | Alerts work                   |                       |                           |                      |
| B6           | Grafana Dashboard        | Metrics visible               |                       |                           |                      |
| B7           | Error Rate               | < 5%                          |                       |                           |                      |
| B8           | Signal Latency           | P95 < 5s                      |                       |                           |                      |
| B9           | Order Execution          | Demo connector works          |                       |                           |                      |
| B10          | Position Tracking        | Stateful                      |                       |                           |                      |
| B11          | Risk Guards              | Caps enforced                 |                       |                           |                      |
| B12          | Circuit Breaker          | Functional                    |                       |                           |                      |
| B13          | Kill Switch              | < 30s response                |                       |                           |                      |
| B14          | Burn-in Tracking         | PnL recorded                  |                       |                           |                      |

### Decision Rules

- **GO:** All HARD blocks (B1-B5, B9, B11-B13) pass AND at least 4 SOFT blocks pass
- **NO-GO:** Any HARD block fails
- **CONDITIONAL-GO:** All HARD blocks pass but fewer than 4 SOFT blocks pass — requires Aria approval

---

## Part D: Contingency Plan (3-Tier)

### Tier 1: Fix & Restart

**Trigger:** Recoverable issues (disk space, service restart needed, temporary connectivity loss)

**Response:**

1. Identify failing component from container logs or Grafana
2. Restart service: `docker-compose restart <service>`
3. Re-validate the specific criterion
4. If persistent, escalate to Tier 2

**Examples:**

- Redis container OOM → restart with higher memory limit
- Polling consumer lag → restart consumer service
- Discord webhook timeout → restart Discord connector

### Tier 2: Fall Back

**Trigger:** Persistent failures (data integrity issues, repeated crashes, unrecoverable state)

**Response:**

1. Disable canary: Set `canary_enabled=false` in Redis
2. Rollback to last known good state (last stable Docker image tag)
3. Investigate root cause in isolation
4. Do not restart canary until Tier 3 review complete if systemic

**Examples:**

- OHLCV data corruption → rollback and re-sync
- Signal generation loop → disable and investigate
- Repeated circuit breaker trips → hard stop, escalate

### Tier 3: Architecture Review

**Trigger:** Systemic issues (design flaws, fundamental problems, repeated Tier 2 escalations)

**Response:**

1. Escalate to Aria with BLOCKER_PACKET
2. Convene architecture review (Winston, senior-dev, merlin)
3. Document findings in `docs/postmortems/`
4. Produce new implementation plan before any restart attempt

**Examples:**

- Database schema incompatible with strategy requirements
- Fundamental latency issue in execution path
- Risk guard logic cannot be safely configured

---

## Part E: Evidence Collection Commands (Apr 26 Checkpoint)

Run these commands at the Apr 26 checkpoint to gather evidence for the Go/No-Go decision.

### Infrastructure Checks (Part A)

```bash
# A2: Redis health
redis-cli ping

# A1: Docker networking
docker network inspect chiseai 2>&1 | grep -c "chiseai"

# A4: Container labels
docker ps --filter "label=project=chiseai" --format "{{.Names}}" | wc -l
```

### Canary Criteria Checks (Part B)

```bash
# B2: Signal generation count (last 24h)
redis-cli --scan --pattern "signals:*" | wc -l

# B4: Last signal timestamp
redis-cli GET last_signal_timestamp

# B1: OHLCV container logs (recent errors)
docker logs chiseai-ohlcv-1 --since 30m 2>&1 | grep -i error | wc -l

# B5: Discord delivery check (recent messages in #alerts channel)
# Use Grafana dashboard panel or Discord API query

# B7: Error rate from Grafana
# Screenshot: Grafana panel "Error Rate" for last 24h

# B8: Signal latency P95 from Grafana
# Screenshot: Grafana histogram panel

# B9: Order execution test (demo connector)
# Submit test order via strategy DSL endpoint, verify acknowledgment

# B12: Circuit breaker functional test
# Trigger test circuit breaker, verify response < 5s

# B13: Kill switch responsive test
# Manual trigger, measure response time

# B14: Burn-in tracking (PnL recorded)
# Screenshot: Grafana PnL panel
```

### Grafana Screenshots (for evidence)

```bash
# Panel 1: System Health Overview
# Screenshot: dashboards/system-health

# Panel 2: Signal Generation Rate
# Screenshot: dashboards/signals/generated

# Panel 3: Error Rate
# Screenshot: dashboards/errors/rate-24h

# Panel 4: PnL Burn-in
# Screenshot: dashboards/pnl/burn-in
```

### Verification Checklist

| Check             | Command                            | Expected       |
| ----------------- | ---------------------------------- | -------------- |
| Redis alive       | `redis-cli ping`                   | `PONG`         |
| Container running | `docker ps --filter "name=ohlcv"`  | 1 container    |
| Signals exist     | `redis-cli SCAN 0 MATCH signals:*` | keys found     |
| Discord connected | Check #alerts channel              | recent message |
| Grafana up        | `curl -s grafana:3000/api/health`  | JSON healthy   |

---

## Document Metadata

- **Story:** ST-LAUNCH-017
- **Created:** 2026-04-13
- **Next Review:** 2026-04-26 (Canary Checkpoint)
- **Owner:** Aria / Jarvis
- **Classification:** Internal — Governance

---

## Changelog

| Date       | Version | Changes          |
| ---------- | ------- | ---------------- |
| 2026-04-13 | 1.0     | Initial creation |
