# EP-ICT-006 Observation Extension & Remediation Plan

**Audit Session**: 2026-03-29T21:25:00Z
**Epic**: EP-ICT-006 Intraday Contextual Trading
**Sprint**: ICT-S8 (Weeks 15-18)
**Original Observation End**: ~Apr 22, 2026
**Extended Observation End**: May 15, 2026
**Remediation Plan Story Points**: 11.5 SP
**Critical Path Duration**: ~8 days

## Executive Summary

The EP-ICT-006 observation period was scheduled to end approximately April 22, 2026, following a 4-week live paper trading data collection phase. However, during the observation period, three critical issues were identified that compromise the ability to draw statistically valid conclusions from the experiment data:

1. **Outcome Tracking Gap**: Position state was stored only in-memory, resulting in complete loss of P&L attribution data following any process restart since March 15, 2026.

2. **Data Collection Not Wired**: ICT data collection code exists in `src/ict/data_collector.py` but was never instantiated in production startup, resulting in zero experiment data being collected.

3. **Signal-Frequency Artifact**: Initial alarm over signal-frequency was determined to be a LOW severity issue caused by mock data generator artifacts during backtesting - production deployment confirmed realistic signal rates.

Given these findings, the observation period is extended to May 15, 2026, and a remediation plan of 11.5 story points has been designed to address the data pipeline issues before the statistical significance testing can proceed.

## Four Key Findings

### Finding 1: Signal-Frequency Alarm Clarification

- **Severity**: LOW (historical test artifact)
- **Status**: RESOLVED
- **Root Cause**: Mock data generator produced unrealistic signal bursts during backtesting
- **Evidence**: Signal count logs showing 10x baseline during specific test periods
- **Remediation**: None required - production deployment confirmed realistic signal rates

### Finding 2: Outcome Tracking Gap (Mar 15+)

- **Severity**: MEDIUM
- **Status**: IN REMEDIATION
- **Root Cause**: Position state stored only in-memory; lost on process restart
- **Impact**: Cannot attribute outcomes to ICT signals; no P&L attribution since Mar 15
- **Remediation**: Phase A - Redis position persistence + startup recovery

### Finding 3: Data Collection Not Wired

- **Severity**: HIGH
- **Status**: IN REMEDIATION
- **Root Cause**: ICT data collection code exists in src/ict/data_collector.py but never instantiated in production startup
- **Impact**: No experiment data being collected; zero keys observed
- **Remediation**: Phase B - Wire data collection + bootstrap experiments

### Finding 4: Zero Experiment Keys

- **Severity**: HIGH
- **Status**: IN REMEDIATION
- **Root Cause**: Dependency on Finding 3 (no data collection)
- **Impact**: Cannot validate ICT effectiveness without experiment data
- **Remediation**: Phase B - Activate B0-B5 experiments after data collection enabled

## Remediation Plan (11.5 SP)

### Phase A: Position Persistence & Recovery (4.5 SP)

- **A1**: Redis position state persistence (2 SP)
- **A2**: Startup state recovery from Redis (1.5 SP)
- **A3**: Reconciliation timing configuration (3600s/86400s) (0.5 SP)
- **A4**: Acceptance criteria retro-review (0.5 SP)

### Phase B: Experiment Activation (6 SP)

- **B0**: 24-hour ICT signal-rate dry-run (parallel with Phase A) (1 SP)
- **B1**: Data collection wiring - instantiate collector (1 SP)
- **B2**: Experiment key schema definition (1 SP)
- **B3**: B1 experiment - Baseline ICT (1 SP)
- **B4**: B2 experiment - Enhanced ICT with risk overlay (1 SP)
- **B5**: B3-B5 experiments - Variant configurations (1 SP)

## Dependencies & Critical Path

- B0 runs parallel with Phase A (starting immediately)
- Phase B depends on Phase A completion (position tracking must be stable)
- B3-B5 depends on B1-B2 (experiment infrastructure)

## Validation Registry Updates

The following validation entries are being added to support the remediation plan:

- VAL-ICT-015: Redis position persistence (verify writes/reads)
- VAL-ICT-016: Startup state recovery (verify recovery logic)
- VAL-ICT-017: Reconciliation timing (verify 3600/86400 config)
- VAL-ICT-018: Data collection wiring (verify instantiation)
- VAL-ICT-019: Experiment key generation (verify key format)
- VAL-ICT-020: B0 dry-run signal rates (verify within bounds)

## Residual Risks

1. **Redis persistence latency**: May affect high-frequency position updates - monitoring required
2. **Experiment key collision**: Potential collision with existing A/B tests in Redis
3. **Data collection overhead**: Performance impact on trading system latency

## Lessons Learned

1. **In-memory state without persistence creates data loss windows**: Position state should have been persisted from day one, not added as an afterthought.

2. **Code existence != code activation**: The data collector existed but was never wired into the production startup path. Need wiring verification as part of code review.

3. **Observation periods should include data pipeline validation from day 1**: The observation period was designed without data pipeline smoke tests. Should have validated data flow before the observation period started.

## Status Registry Updates

The following updates are being made to `docs/bmm-workflow-status.yaml`:

- `observation_end` extended from ~Apr 22, 2026 to May 15, 2026
- New stories added: ST-ICT-023 (Phase A) and ST-ICT-024 (Phase B)
- `remediation_plan_sp: 11.5` field added
