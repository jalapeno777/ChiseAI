# EP-CANARY-R2B-001: R2b 30-Day Canary

## Epic Overview

| Field | Value |
|---|---|
| **Epic ID** | EP-CANARY-R2B-001 |
| **Priority** | P1 |
| **Status** | queued (pending 72h burn-in gate) |
| **Burn-in Gate** | 2026-05-07T11:01:12Z |
| **Estimated Story Points** | 8 |
| **Owner** | jarvis |
| **Depends On** | RECON-BURN-IN-72H (72h post-pipeline-unblock burn-in) |

## Background

R2a canary has been running since 2026-04-12 with full pipeline operational status after remediation of BLK-001/002/003 on 2026-05-02. EP-PIPELINE-UNBLOCK-001 completed and merged at d3c7a286e on 2026-05-04. A 72h burn-in window was started to validate pipeline stability before transitioning to the R2b 30-day canary phase.

The R2b canary represents a clean-slate validation: fresh signal baselines, automated daily checkpoints, explicit Go/No-Go gates, and a promotion packet that compiles evidence for human approval to transition to live trading.

## Objective

Transition from R2a post-remediation to a clean R2b 30-day canary with:

- Fresh signal baseline independent of R2a contaminated data
- Automated checkpoint gates at day 7, 14, 21, and 30
- Kill switch readiness verified throughout the window
- Clear promotion path to live trading with evidence bundle

## Stories

### ST-CANARY-R2B-001: Reset Canary Clock for R2b

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Blocking** | ST-CANARY-R2B-002 through ST-CANARY-R2B-006 depend on this |

**Description**: Reset the canary clock to start the R2b 30-day window. Clear R2a checkpoint state and initialize fresh R2b tracking in Redis.

**Acceptance Criteria**:

1. Canary clock reset with new start date (post-burn-in, not before 2026-05-07T11:01:12Z)
2. Redis keys for R2a checkpoints cleared/archived to `r2a:archived:*` prefix
3. New Redis keys for R2b initialized under `r2b:canary:*` namespace:
   - `r2b:canary:start_ts` — ISO 8601 timestamp of R2b start
   - `r2b:canary:status` — set to `active`
   - `r2b:canary:day` — set to `0`
4. Clock start is gated on burn-in completion verification:
   - Check `bmad:chiseai:burnin:status` key in Redis
   - If burn-in not complete, abort with clear error message
   - If burn-in complete, proceed with clock reset

**Implementation Notes**:

- Use Redis pipeline for atomic multi-key operations
- Archive R2a keys with TTL of 90 days (not delete — may need for retrospective)
- Add `r2b:canary:version` = `2` to distinguish from future R2c+ phases
- Log clock reset event to `bmad:chiseai:iterlog:story:ST-CANARY-R2B-001`

**Scope**: `src/evaluation/canary/`, `scripts/ops/`

**Verification**: Redis canary keys reflect R2b state, clock shows day 0

---

### ST-CANARY-R2B-002: Fresh Signal Baseline Capture

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Depends On** | ST-CANARY-R2B-001 |

**Description**: Capture a fresh signal baseline at R2b start for comparison throughout the 30-day window.

**Acceptance Criteria**:

1. Signal quality metrics captured at R2b start:
   - Direction accuracy (bull/bear signal correctness over trailing 24h)
   - Confidence distribution (mean, p25, p50, p75, p95)
   - Signal volume (count per 4h window, total per day)
   - Signal-to-noise ratio (profitable signals / total signals)
2. Baseline stored in Redis under `r2b:baseline:*` namespace with:
   - `r2b:baseline:signal_metrics` — JSON blob of all metrics
   - `r2b:baseline:pipeline_health` — latency, error rate, throughput
   - `r2b:baseline:captured_ts` — ISO 8601 timestamp
   - `r2b:baseline:immutable` — `true` (prevent overwrites)
3. Baseline snapshot is immutable after capture:
   - Script checks `immutable` flag before writing
   - If baseline already exists and is immutable, log warning and exit
4. Baseline includes pipeline health metrics:
   - Average signal generation latency (ms)
   - Consumer processing throughput (signals/min)
   - Error rate (errors / total signals, trailing 24h)

**Implementation Notes**:

- Read metrics from InfluxDB via existing query patterns in `src/data/`
- Store as JSON hash in Redis for easy comparison during checkpoints
- Include a hash/sha256 of the baseline data for tamper detection
- Script should be idempotent — no-op if immutable baseline already exists

**Scope**: `src/evaluation/canary/`, `src/data/`

**Verification**: Redis contains R2b baseline with timestamp and immutable flag

---

### ST-CANARY-R2B-003: Daily Checkpoint Automation

| Field | Value |
|---|---|
| **Size** | 2SP |
| **Priority** | P1 |
| **Depends On** | ST-CANARY-R2B-001, ST-CANARY-R2B-002 |

**Description**: Automate daily checkpoint collection throughout the 30-day canary window. Integrate with existing Woodpecker cron infrastructure.

**Acceptance Criteria**:

1. Daily cron job captures checkpoint metrics:
   - Signal count (24h window)
   - Signal accuracy (vs baseline)
   - Pipeline health (latency, error rate, throughput)
   - Container health (restart count, uptime)
2. Checkpoint data stored in Redis with daily keys:
   - `r2b:checkpoint:day-N` where N is 1-30
   - Each checkpoint is a JSON hash with: metrics, comparison_to_baseline, timestamp
3. Checkpoint includes comparison against baseline:
   - Delta from baseline for each metric
   - Percentage change
   - Pass/fail indicator per metric
4. Missing checkpoint triggers alert (not just log):
   - If day-N checkpoint is not captured by day-N+1 00:00 UTC, send Discord alert
   - Alert includes: expected day number, last successful checkpoint, suggested action
5. Checkpoint report format matches existing daily health report template:
   - Markdown summary section
   - JSON data section
   - Comparison table (baseline vs current)

**Implementation Notes**:

- Add cron step to `.woodpecker/cron-eval.yaml` (or equivalent cron config)
- Script: `scripts/ops/canary_checkpoint.py`
- Runs daily at 00:30 UTC (offset from other cron jobs to avoid resource contention)
- First checkpoint on day 1 (day 0 is baseline capture day)
- Checkpoint script should be safe to re-run (idempotent per day)
- Integrate with existing alerting patterns from `chiseai-incident-response`

**Scope**: `scripts/ops/`, `.woodpecker/cron-eval.yaml`

**Verification**: Manual trigger of checkpoint script produces valid daily checkpoint

---

### ST-CANARY-R2B-004: Go/No-Go Gate Implementation

| Field | Value |
|---|---|
| **Size** | 2SP |
| **Priority** | P1 |
| **Depends On** | ST-CANARY-R2B-002, ST-CANARY-R2B-003 |

**Description**: Implement Go/No-Go evaluation gates at day 7, 14, 21, and 30 with automated criteria checking.

**Acceptance Criteria**:

1. Gate evaluation at day 7/14/21/30 with defined pass/fail criteria:
   - **Day 7 (Early Stability)**:
     - Signal accuracy ≥ baseline accuracy (no degradation)
     - Error rate < 5% (strict)
     - Pipeline uptime > 99%
     - No container restart > 2 in any 24h window
   - **Day 14 (Mid-Point Confidence)**:
     - Signal accuracy ≥ baseline + 2% (improvement expected)
     - Error rate < 3%
     - Pipeline uptime > 99.5%
     - All previous checkpoints captured (no gaps)
   - **Day 21 (Pre-Final Validation)**:
     - Signal accuracy ≥ baseline + 3%
     - Error rate < 2%
     - Pipeline uptime > 99.5%
     - Kill switch tested at least once (ST-CANARY-R2B-005)
   - **Day 30 (Promotion Gate)**:
     - Signal accuracy ≥ baseline + 5%
     - Error rate < 1%
     - Pipeline uptime > 99.9%
     - Kill switch tested twice
     - All gates passed
     - No P0/P1 incidents unresolved
2. Gate results stored in Redis:
   - `r2b:gate:day-7:result` — `pass` | `fail` | `warning`
   - `r2b:gate:day-7:evidence` — JSON blob with all criteria and values
   - Same pattern for day 14, 21, 30
3. Gate failure triggers:
   - Discord alert with gate day, failed criteria, current values
   - Optional pause of canary (configurable via `r2b:config:pause_on_gate_fail`)
   - Does NOT auto-terminate — requires human decision
4. Day-30 gate produces promotion-ready evidence bundle:
   - Aggregates all checkpoint data
   - Includes gate pass history
   - Generates Markdown summary for human review
5. Gate evaluation can be triggered manually for testing:
   - `python scripts/ops/canary_gate.py --day 7 --dry-run`
   - Dry-run mode does not write Redis or send alerts

**Implementation Notes**:

- New module: `src/evaluation/canary/gates.py`
- Each gate day has its own criteria set (not hardcoded — configurable via dict/JSON)
- Unit tests are critical — cover all gate criteria with pass/fail/edge cases
- Gate evaluation reads from checkpoint data in Redis
- Consider adding a `r2b:gate:config` key for overriding thresholds during testing

**Scope**: `src/evaluation/canary/gates.py` (new), `tests/unit/evaluation/`

**Verification**: Unit tests cover all gate criteria with pass/fail/edge cases

---

### ST-CANARY-R2B-005: Kill Switch Readiness Verification

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Depends On** | ST-CANARY-R2B-001 |

**Description**: Verify and test the kill switch is ready for immediate activation during R2b canary.

**Acceptance Criteria**:

1. Kill switch E2E test passes:
   - Existing ST-LAUNCH-KILL-001 test coverage verified as current
   - Test validates: signal generation stops, positions closed, orders cancelled
2. Kill switch activation latency < 5 seconds:
   - Measured from trigger to confirmed stop of all trading activity
   - Latency tracked and stored in Redis
3. Kill switch test run at canary start and day-15:
   - Scheduled via checkpoint automation or separate cron entry
   - Test results stored in `r2b:kill_switch:test:<timestamp>`
4. Kill switch verification results stored in Redis:
   - `r2b:kill_switch:last_test_ts` — timestamp of last successful test
   - `r2b:kill_switch:latency_ms` — measured latency
   - `r2b:kill_switch:status` — `ready` | `degraded` | `failed`
5. Alert if kill switch test fails:
   - Block canary continuation until kill switch is verified
   - Alert includes: failure details, remediation steps, impact assessment

**Implementation Notes**:

- Leverage existing `src/execution/kill_switch.py` — do NOT rewrite
- Add a verification wrapper script that runs the existing test and captures metrics
- Kill switch test should be non-destructive in canary mode (dry-run kill)
- Coordinate with ST-INFRA-002 (container monitoring) to ensure kill switch container is monitored

**Scope**: `src/execution/kill_switch.py`, `tests/`

**Verification**: Kill switch test suite passes, Redis has verification timestamp

---

### ST-CANARY-R2B-006: Promotion Packet Template for R2b → Live

| Field | Value |
|---|---|
| **Size** | 1SP |
| **Priority** | P1 |
| **Depends On** | ST-CANARY-R2B-004 |

**Description**: Create promotion packet template that compiles R2b canary evidence for human approval to transition to live trading.

**Acceptance Criteria**:

1. Template captures all required evidence:
   - 30-day signal accuracy (daily trend + aggregate)
   - Pipeline uptime (daily trend + aggregate)
   - Kill switch test results (both test dates)
   - Incident log (any incidents during R2b)
   - Gate results (day 7, 14, 21, 30)
   - Baseline comparison (R2b start vs end)
2. Template generates Markdown + JSON output:
   - Markdown: human-readable summary for Craig review
   - JSON: machine-readable for automated processing
   - Both outputs include same data, different formats
3. Template includes risk assessment section:
   - Residual risks identified during canary
   - Risk severity and likelihood
   - Mitigation in place for each risk
4. Template includes rollback plan section:
   - Steps to revert to R2a configuration if live trading fails
   - Estimated rollback time
   - Required approvals for rollback
5. Template follows `chiseai-promotion-packet` skill format:
   - Compatible with existing promotion packet workflow
   - Includes all required fields from skill schema

**Implementation Notes**:

- New script: `scripts/ops/canary_promotion_packet.py`
- Reads all R2b data from Redis and generates the packet
- Template location: `docs/templates/canary-promotion-packet.md.j2` (Jinja2 template)
- JSON output: same data as Markdown but in structured format
- Should be runnable standalone for testing with `--sample-data` flag

**Scope**: `scripts/ops/canary_promotion_packet.py` (new), `docs/templates/`

**Verification**: Template renders with sample data, follows promotion packet skill schema

## Dependencies

| Dependency | Type | Gate Date |
|---|---|---|
| RECON-BURN-IN-72H | Hard gate | 2026-05-07T11:01:12Z |

All stories are blocked until burn-in gate passes. Burn-in verification checks:

- Pipeline components stable (no crash-loops, no consumer idle, no zombie processes)
- Signal generation consistent (no gaps > 2h)
- CI pipelines green for 72h

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Signal quality degradation during canary | Medium | High | Daily checkpoint comparison against baseline, Go/No-Go gates |
| Pipeline failure during canary | Low | Critical | Automated alerting + kill switch readiness (ST-CANARY-R2B-005) |
| False positive gate failure | Medium | Medium | Manual override option with documented justification |
| Baseline capture during anomalous market | Low | High | Baseline includes market context, can be flagged for review |
| Kill switch degraded during canary | Low | Critical | Dual verification (start + day-15), block continuation on failure |

## Success Criteria

1. All 6 stories completed and merged
2. R2b canary runs for 30 days with all gate checks passing
3. Promotion packet generated with evidence for Craig approval
4. Kill switch tested and verified at least twice during canary
5. No P0/P1 incidents unresolved at day-30 gate
6. All daily checkpoints captured (zero gaps)

## Execution Order

```
ST-CANARY-R2B-001 (clock reset)
├── ST-CANARY-R2B-002 (baseline capture)
│   └── ST-CANARY-R2B-003 (daily checkpoints)
│       └── ST-CANARY-R2B-004 (Go/No-Go gates)
│           └── ST-CANARY-R2B-006 (promotion packet)
└── ST-CANARY-R2B-005 (kill switch verification)
```

ST-CANARY-R2B-005 can run in parallel with ST-CANARY-R2B-002/003 since it only depends on the clock reset.
