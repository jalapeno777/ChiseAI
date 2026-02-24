# EP-LAUNCH-003: Training Integration & Model Ops
## Executable Story Breakdown

**Epic ID:** EP-LAUNCH-003  
**Sprint:** LAUNCH-SPRINT-2  
**Target Timeline:** Days 9-12 (Mar 1-4, 2026)  
**Total Points:** 10 (3 remaining stories)  
**Blocking:** Yes - Critical path to launch

---

## Executive Summary

EP-LAUNCH-003 completes the ML learning loop by integrating training pipeline, validation gates, and rollback mechanisms. With ST-LAUNCH-011 (Model Retraining Trigger) completed via PR #257, **3 stories remain** totaling 10 story points (~5-7 days).

### Critical Path Impact
```
ST-LAUNCH-012 (Training Pipeline) ──┬──> ST-LAUNCH-014 (E2E Test)
                                      │
ST-LAUNCH-013 (Validation/Rollback) ─┘
```

**Parallelization:** ST-LAUNCH-012 and ST-LAUNCH-013 can run in parallel (different scope globs)

---

## Story Status Overview

| Story ID | Title | Status | Points | Est. Time | Dependencies |
|----------|-------|--------|--------|-----------|--------------|
| ST-LAUNCH-011 | Model Retraining Trigger | ✅ COMPLETED | 5 | Done | None |
| ST-LAUNCH-012 | Training Pipeline Integration | ⏳ PLANNED | 4 | 2-3 days | ST-LAUNCH-007 ✅, ST-LAUNCH-011 ✅ |
| ST-LAUNCH-013 | Model Validation & Rollback | ⏳ PLANNED | 3 | 1-2 days | ST-LAUNCH-012 |
| ST-LAUNCH-014 | Training E2E Integration Test | ⏳ PLANNED | 3 | 1-2 days | ST-LAUNCH-011 ✅, ST-LAUNCH-012, ST-LAUNCH-013 |

---

## Existing Implementation Assets

Based on codebase analysis, significant infrastructure exists:

```
src/ml/training/
├── pipeline.py              # 16KB - Base pipeline logic
├── training_orchestrator.py # 21KB - Orchestration
├── extractor.py             # 29KB - Feature extraction (ST-LAUNCH-007 ✅)
├── retraining_trigger.py    # 32KB - Trigger logic (ST-LAUNCH-011 ✅)
└── exporter.py              # 26KB - Data export

src/ml/models/
├── model_registry.py        # 15KB - Version management
└── model_storage.py         # 14KB - Storage backend

src/ml/validation/
├── gate.py                  # 23KB - Validation gates
└── promotion.py             # 18KB - Model promotion

src/ml/rollback/
└── automatic.py             # 19KB - Automatic rollback

tests/e2e/
├── test_training_full_pipeline.py    # 36KB - Partial E2E
└── test_training_integration.py      # 9KB - Integration tests
```

---

## ST-LAUNCH-012: Training Pipeline Integration

### Overview
**Points:** 4 | **Effort:** 2-3 days | **Priority:** P0-CRITICAL  
**FR Coverage:** FR-020  
**Dependencies:** ST-LAUNCH-007 ✅ (Feature Extractor), ST-LAUNCH-011 ✅ (Retraining Trigger)

### Scope Globs
```yaml
scope_globs:
  - src/ml/training/training_pipeline.py
  - src/ml/models/model_registry.py
  - tests/test_ml/test_training_pipeline.py
```

### Description
Integrate feature extractor, training data, and model registry for seamless training pipeline execution.

---

### Granular Tasks (7 subtasks)

#### Task 12.1: Feature Extractor Pipeline Integration
**Effort:** 4 hours | **Dependencies:** None

**Work:**
- Wire `src/ml/training/extractor.py` to `training_pipeline.py`
- Create `TrainingDataLoader` class for feature retrieval
- Implement 70/15/15 train/validation/test split logic
- Add data quality validation (check freshness, completeness)

**Acceptance Criteria:**
- [ ] `extract_training_data()` method returns split datasets
- [ ] Data quality validation throws on <90% quality score
- [ ] Feature schema includes 10+ features per sample
- [ ] Data split respects time ordering (no data leakage)

**Test Command:**
```bash
pytest tests/test_ml/test_training_pipeline.py::test_feature_integration -v
```

---

#### Task 12.2: Model Registry Integration
**Effort:** 3 hours | **Dependencies:** Task 12.1

**Work:**
- Connect pipeline to `model_registry.py`
- Implement semantic versioning (MAJOR.MINOR.PATCH)
- Store model metadata: hyperparams, metrics, timestamp, training_data_hash
- Add `register_model()` and `get_latest_model()` methods

**Acceptance Criteria:**
- [ ] Models versioned with semver (e.g., v1.2.3)
- [ ] Metadata includes: `{version, hyperparams, accuracy, precision, recall, f1, timestamp, data_hash}`
- [ ] Model retrieval by version tag works
- [ ] `latest` tag points to current production model

**Test Command:**
```bash
pytest tests/test_ml/test_training_pipeline.py::test_registry_integration -v
```

---

#### Task 12.3: Incremental Training Mode
**Effort:** 4 hours | **Dependencies:** Task 12.2

**Work:**
- Implement incremental training using last 30 days of data
- Add `training_mode` parameter: `incremental` | `full`
- Create data windowing logic
- Add SLA tracking (must complete within 4 hours)

**Acceptance Criteria:**
- [ ] `incremental` mode uses only data from last 30 days
- [ ] Training completes within 4 hours
- [ ] Incremental model accuracy within 5% of full training
- [ ] Resource usage <8GB RAM

**Test Command:**
```bash
pytest tests/test_ml/test_training_pipeline.py::test_incremental_training -v
```

**SLA Gate:**
```bash
# Measure training time
time python -c "from src.ml.training.pipeline import TrainingPipeline; p = TrainingPipeline(); p.run(mode='incremental')"
# Must complete <4 hours
```

---

#### Task 12.4: Full Retraining Mode
**Effort:** 3 hours | **Dependencies:** Task 12.2

**Work:**
- Implement full historical data retraining
- Add batch processing for large datasets
- Implement checkpointing for long-running training
- Add SLA tracking (must complete within 24 hours)

**Acceptance Criteria:**
- [ ] `full` mode uses all historical data
- [ ] Training completes within 24 hours
- [ ] Checkpoint saves progress every 1 hour
- [ ] Can resume from checkpoint on failure

**Test Command:**
```bash
pytest tests/test_ml/test_training_pipeline.py::test_full_retraining -v
```

---

#### Task 12.5: Model Validation Integration
**Effort:** 3 hours | **Dependencies:** Task 12.3, Task 12.4

**Work:**
- Compute metrics on test set: accuracy, precision, recall, F1
- Compare against baseline model
- Implement threshold check (accuracy > baseline - 5%)
- Generate validation report

**Acceptance Criteria:**
- [ ] Metrics computed on held-out test set
- [ ] Model passes if `accuracy >= baseline_accuracy - 0.05`
- [ ] Validation report includes: confusion matrix, feature importance
- [ ] Failed validation logs reason and aborts deployment

**Test Command:**
```bash
pytest tests/test_ml/test_training_pipeline.py::test_model_validation -v
```

---

#### Task 12.6: Pipeline Orchestration
**Effort:** 3 hours | **Dependencies:** Task 12.5

**Work:**
- Wire to `training_orchestrator.py`
- Add scheduler integration
- Implement pipeline status tracking in Redis
- Add Discord notification on completion

**Acceptance Criteria:**
- [ ] Pipeline can be triggered via scheduler
- [ ] Status tracked in Redis: `launch:training:pipeline:status`
- [ ] Discord notification sent on completion with metrics
- [ ] Pipeline idempotent (can retry on failure)

**Redis Keys:**
```bash
redis-cli SET launch:training:pipeline:status "running"
redis-cli SET launch:training:pipeline:last_run "2026-03-02T14:30:00Z"
redis-cli SET launch:training:pipeline:mode "incremental"
```

---

#### Task 12.7: Unit Tests & Coverage
**Effort:** 3 hours | **Dependencies:** All above

**Coverage Target:** 80%

**Test Files:**
```bash
tests/test_ml/test_training_pipeline.py
├── test_feature_integration
├── test_registry_integration  
├── test_incremental_training
├── test_full_retraining
├── test_model_validation
├── test_pipeline_orchestration
└── test_error_handling
```

**Run All Tests:**
```bash
pytest tests/test_ml/test_training_pipeline.py -v --cov=src/ml/training --cov-report=term-missing
```

---

### Acceptance Criteria Summary

| Criterion | Threshold | Verification |
|-----------|-----------|--------------|
| Feature integration | 70/15/15 split | Unit test |
| Model registry | Semantic versioning | Integration test |
| Incremental training | <4 hours | SLA gate |
| Full retraining | <24 hours | SLA gate |
| Model validation | accuracy > baseline - 5% | Unit test |

---

### Live Validation Gates

```bash
# Gate 1: Pipeline Performance
python scripts/ops/run_training_pipeline.py --mode incremental
# Expected: Completes within 4 hours

# Gate 2: Registry Functional
python -c "from src.ml.models.model_registry import ModelRegistry; r = ModelRegistry(); print(r.get_latest_version())"
# Expected: Returns valid semver

# Gate 3: Feature Integration
python scripts/ops/validate_training_data.py --sample-size 100
# Expected: All samples have 10+ features
```

---

### Risk Register

| Risk ID | Risk | Probability | Impact | Mitigation |
|---------|------|-------------|--------|------------|
| R-12-01 | Feature extractor returns incomplete data | Medium | High | Add data quality validation; abort on <90% quality |
| R-12-02 | Model registry storage failure | Low | Critical | Implement retry logic; fallback to local filesystem |
| R-12-03 | Training exceeds SLA | Medium | Medium | Add progress monitoring; auto-switch to incremental |
| R-12-04 | Memory exhaustion on full retrain | Medium | High | Implement batch processing; limit to 8GB |

---

### Rollback Plan

```bash
# Disable training pipeline
redis-cli SET launch:training:pipeline:enabled 0

# Revert to previous model version
python scripts/ops/revert_model.py --version previous

# Fallback to baseline model
python scripts/ops/load_baseline_model.py
```

---

## ST-LAUNCH-013: Model Validation & Rollback

### Overview
**Points:** 3 | **Effort:** 1-2 days | **Priority:** P1-HIGH  
**FR Coverage:** FR-018  
**Dependencies:** ST-LAUNCH-012 (can parallel develop, but integration requires 012)

### Scope Globs
```yaml
scope_globs:
  - src/ml/validation/model_validator.py
  - src/ml/rollback/model_rollback.py
  - tests/test_ml/test_model_validation.py
```

### Description
Implement model validation gates and automatic rollback on validation failure.

---

### Granular Tasks (6 subtasks)

#### Task 13.1: Validation Gate Implementation
**Effort:** 3 hours | **Dependencies:** None (parallel with 012)

**Work:**
- Extend `src/ml/validation/gate.py` with model-specific gates
- Implement accuracy threshold gate (configurable)
- Implement precision/recall/F1 gates
- Add composite gate (all must pass)

**Acceptance Criteria:**
- [ ] `AccuracyGate` configurable with threshold (default 0.60)
- [ ] `PrecisionGate`, `RecallGate`, `F1Gate` implemented
- [ ] `CompositeGate` runs all gates and returns pass/fail + details
- [ ] Gate results logged to InfluxDB

**Test Command:**
```bash
pytest tests/test_ml/test_model_validation.py::test_validation_gates -v
```

---

#### Task 13.2: A/B Testing Framework (Shadow Mode)
**Effort:** 4 hours | **Dependencies:** Task 13.1

**Work:**
- Implement shadow mode for new models
- Route signals to both current and new model
- Compare predictions without affecting trades
- Track shadow performance for 24 hours

**Acceptance Criteria:**
- [ ] Shadow mode runs for 24 hours before promotion
- [ ] Performance metrics tracked: win_rate, avg_pnl, sharpe
- [ ] Comparison report generated at end of shadow period
- [ ] Shadow mode can be disabled via feature flag

**Redis Keys:**
```bash
redis-cli SET launch:training:shadow_mode:enabled 1
redis-cli SET launch:training:shadow_mode:model_version "v1.3.0"
redis-cli SET launch:training:shadow_mode:start_time "2026-03-03T00:00:00Z"
```

**Test Command:**
```bash
pytest tests/test_ml/test_model_validation.py::test_shadow_mode -v
```

---

#### Task 13.3: Degradation Detection
**Effort:** 3 hours | **Dependencies:** Task 13.2

**Work:**
- Implement performance monitoring for deployed models
- Detect degradation >10% from baseline
- Trigger rollback alert on detection
- Log degradation events to InfluxDB

**Acceptance Criteria:**
- [ ] Win rate, accuracy, pnl tracked hourly
- [ ] Degradation detected if metrics drop >10% from baseline
- [ ] Alert sent to Discord within 1 minute of detection
- [ ] Degradation events queryable from InfluxDB

**InfluxDB Query:**
```sql
SELECT mean(win_rate) FROM model_performance 
WHERE time > now() - 24h 
GROUP BY time(1h)
```

**Test Command:**
```bash
pytest tests/test_ml/test_model_validation.py::test_degradation_detection -v
```

---

#### Task 13.4: Automatic Rollback Implementation
**Effort:** 4 hours | **Dependencies:** Task 13.3

**Work:**
- Extend `src/ml/rollback/automatic.py`
- Implement automatic rollback trigger
- Ensure rollback completes in <5 minutes
- Protect current trades (new signals use rolled-back model)

**Acceptance Criteria:**
- [ ] Rollback triggered automatically on degradation >10%
- [ ] Rollback completes in <5 minutes (target: <2 minutes)
- [ ] In-flight trades continue with current model
- [ ] New signals use previous model version
- [ ] Rollback event logged with full context

**Test Command:**
```bash
pytest tests/test_ml/test_model_validation.py::test_automatic_rollback -v
```

**Performance Gate:**
```bash
# Measure rollback time
time python scripts/ops/test_rollback_performance.py
# Must complete <5 minutes
```

---

#### Task 13.5: Validation History & Audit
**Effort:** 2 hours | **Dependencies:** Task 13.4

**Work:**
- Store all validation results in database
- Track rollback events with timestamps and reasons
- Create audit trail for compliance
- Add query API for validation history

**Acceptance Criteria:**
- [ ] All validation results stored with timestamps
- [ ] Rollback events include: trigger_reason, old_version, new_version, metrics
- [ ] History queryable via API: `GET /api/v1/validation/history`
- [ ] Retention: 90 days

**Test Command:**
```bash
pytest tests/test_ml/test_model_validation.py::test_validation_history -v
```

---

#### Task 13.6: Unit Tests & Coverage
**Effort:** 2 hours | **Dependencies:** All above

**Coverage Target:** 85%

**Test Files:**
```bash
tests/test_ml/test_model_validation.py
├── test_validation_gates
├── test_shadow_mode
├── test_degradation_detection
├── test_automatic_rollback
├── test_rollback_performance
├── test_validation_history
└── test_concurrent_rollback
```

**Run All Tests:**
```bash
pytest tests/test_ml/test_model_validation.py -v --cov=src/ml/validation --cov=src/ml/rollback --cov-report=term-missing
```

---

### Validation Thresholds

| Metric | Pass Threshold | Warning | Critical |
|--------|---------------|---------|----------|
| Accuracy | >= 0.60 | 0.55-0.60 | < 0.55 |
| Precision | >= 0.55 | 0.50-0.55 | < 0.50 |
| Recall | >= 0.50 | 0.45-0.50 | < 0.45 |
| F1 Score | >= 0.52 | 0.47-0.52 | < 0.47 |
| Win Rate | >= 0.55 | 0.50-0.55 | < 0.50 |

**Degradation Trigger:** Any metric drops >10% from baseline

---

### Rollback Timing Requirements

| Phase | Target | Max Allowed |
|-------|--------|-------------|
| Detection | <30s | 1 minute |
| Decision | <10s | 30 seconds |
| Execution | <60s | 3 minutes |
| Verification | <30s | 1 minute |
| **Total** | **<2 min** | **5 minutes** |

---

### Live Validation Gates

```bash
# Gate 1: Rollback Performance
python scripts/ops/test_rollback_performance.py
# Expected: Completes <5 minutes

# Gate 2: Validation Gates Functional
python -c "from src.ml.validation.gate import CompositeGate; g = CompositeGate(); print(g.validate(model_data))"
# Expected: Returns pass/fail with metrics

# Gate 3: Shadow Mode Toggle
redis-cli SET launch:training:shadow_mode:enabled 1
redis-cli GET launch:training:shadow_mode:enabled
# Expected: "1"
```

---

### Risk Register

| Risk ID | Risk | Probability | Impact | Mitigation |
|---------|------|-------------|--------|------------|
| R-13-01 | False positive rollback trigger | Medium | High | Require 3 consecutive degradation readings |
| R-13-02 | Rollback fails mid-execution | Low | Critical | Implement atomic model swap with transaction |
| R-13-03 | Shadow mode affects performance | Low | Medium | Run shadow in separate process with resource limits |
| R-13-04 | Validation history storage full | Low | Low | Implement 90-day retention with auto-purge |

---

### Rollback Plan

```bash
# Disable auto-rollback
redis-cli SET launch:training:auto_rollback:enabled 0

# Manual rollback
python scripts/ops/manual_rollback.py --version v1.2.0 --reason "Manual override"

# Disable shadow mode
redis-cli SET launch:training:shadow_mode:enabled 0
```

---

## ST-LAUNCH-014: Training E2E Integration Test

### Overview
**Points:** 3 | **Effort:** 1-2 days | **Priority:** P0-CRITICAL  
**FR Coverage:** FR-018, FR-020  
**Dependencies:** ST-LAUNCH-011 ✅, ST-LAUNCH-012, ST-LAUNCH-013

### Scope Globs
```yaml
scope_globs:
  - tests/e2e/test_training_lifecycle.py
  - tests/e2e/fixtures/training_test_data.py
```

### Description
Create comprehensive E2E test for the complete training lifecycle from trigger to deployment.

---

### Test Scenarios (5 scenarios)

#### Scenario 14.1: Full Training Flow
**Execution Time:** ~4 hours

**Flow:**
```
Trigger → Data Collection → Feature Extraction → Training → Validation → Deployment
```

**Test Steps:**
1. Set ECE to 0.18 (trigger threshold)
2. Wait for trigger to fire
3. Verify training pipeline starts
4. Monitor feature extraction (10+ features)
5. Monitor training progress
6. Verify validation passes
7. Verify model deployed to registry
8. Verify new model is `latest`

**Success Criteria:**
- [ ] All stages complete successfully
- [ ] New model appears in registry
- [ ] `latest` tag updated
- [ ] Total time <8 hours

**Test Command:**
```bash
pytest tests/e2e/test_training_lifecycle.py::test_full_training_flow -v --timeout=28800
```

---

#### Scenario 14.2: Trigger to Validation Flow
**Execution Time:** ~6 hours

**Flow:**
```
Trigger → Training → Validation → Deploy (if pass) → Alert (if fail)
```

**Test Steps:**
1. Trigger via API: `POST /api/v1/training/trigger`
2. Wait for training start
3. Inject test data with known patterns
4. Verify model learns patterns
5. Check validation metrics
6. If pass: verify deployment
7. If fail: verify alert sent

**Success Criteria:**
- [ ] Trigger to deployment <8 hours
- [ ] Validation metrics match expected
- [ ] Deployment confirmed via registry
- [ ] Alert sent on validation failure

**Test Command:**
```bash
pytest tests/e2e/test_training_lifecycle.py::test_trigger_to_validation -v --timeout=28800
```

---

#### Scenario 14.3: Rollback Flow
**Execution Time:** ~30 minutes

**Flow:**
```
Deploy New Model → Detect Degradation → Trigger Rollback → Restore Previous
```

**Test Steps:**
1. Deploy new model version
2. Inject degradation patterns (lower accuracy)
3. Wait for degradation detection
4. Verify rollback triggered
5. Verify previous model restored
6. Verify system continues operating
7. Check in-flight trades unaffected

**Success Criteria:**
- [ ] Degradation detected within SLA
- [ ] Rollback completes <5 minutes
- [ ] Previous model restored
- [ ] No trade interruption
- [ ] Rollback event logged

**Test Command:**
```bash
pytest tests/e2e/test_training_lifecycle.py::test_rollback_flow -v --timeout=1800
```

---

#### Scenario 14.4: Data Quality Failure Flow
**Execution Time:** ~15 minutes

**Flow:**
```
Trigger → Validate Data Quality → Abort (if poor) → Alert with Details
```

**Test Steps:**
1. Trigger training
2. Inject poor quality data (<90% completeness)
3. Verify training aborts
4. Verify alert sent to Discord
5. Verify alert includes quality metrics
6. Verify no model deployed

**Success Criteria:**
- [ ] Training aborts on data quality failure
- [ ] Alert includes: quality_score, missing_features, timestamp
- [ ] No model deployed
- [ ] Retry possible after data fix

**Test Command:**
```bash
pytest tests/e2e/test_training_lifecycle.py::test_data_quality_failure -v --timeout=900
```

---

#### Scenario 14.5: Concurrent Training Prevention
**Execution Time:** ~10 minutes

**Flow:**
```
Training Running → New Trigger → Queue Trigger → Resume After Completion
```

**Test Steps:**
1. Start training pipeline
2. Trigger new training while running
3. Verify second trigger queued
4. Verify no duplicate training
5. Wait for first training to complete
6. Verify queued trigger executes

**Success Criteria:**
- [ ] Concurrent training prevented
- [ ] Second trigger queued
- [ ] Queue processed after completion
- [ ] No training data corruption

**Test Command:**
```bash
pytest tests/e2e/test_training_lifecycle.py::test_concurrent_prevention -v --timeout=600
```

---

### Test Data Fixtures

Create `tests/e2e/fixtures/training_test_data.py`:

```python
# Training test data fixtures

TRAINING_SIGNALS = [
    {
        "signal_id": "test_signal_001",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_price": 45000.0,
        "confidence": 0.75,
        "timestamp": "2026-03-01T00:00:00Z"
    },
    # ... 100+ test signals
]

TRAINING_OUTCOMES = [
    {
        "outcome_id": "test_outcome_001",
        "signal_id": "test_signal_001",
        "exit_price": 45500.0,
        "pnl": 0.0111,
        "win": True,
        "timestamp": "2026-03-01T01:00:00Z"
    },
    # ... matching outcomes
]

DEGRADATION_SIGNALS = [
    # Signals designed to trigger degradation
    {
        "signal_id": "degrade_001",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "confidence": 0.75,
        # ... will result in loss
    },
    # ... 20 degradation signals
]

POOR_QUALITY_DATA = {
    "signals": [...],  # Incomplete feature sets
    "quality_score": 0.75,  # Below 90% threshold
    "missing_features": ["rsi", "macd"]
}
```

**Load Fixtures:**
```bash
python tests/e2e/fixtures/load_training_fixtures.py --env test
```

---

### Success Criteria Summary

| Scenario | Target Time | Success Metric |
|----------|-------------|----------------|
| Full Training Flow | <8 hours | 100% stages pass |
| Trigger to Validation | <8 hours | Deployed <8h |
| Rollback Flow | <5 minutes | Restored <5min |
| Data Quality Failure | <1 minute | Alert sent |
| Concurrent Prevention | N/A | No duplicates |

---

### Execution Time Targets

| Test | Target | Max |
|------|--------|-----|
| Unit tests | 30s | 60s |
| Integration tests | 5min | 10min |
| E2E Scenario 14.1 | 4h | 8h |
| E2E Scenario 14.2 | 6h | 8h |
| E2E Scenario 14.3 | 15min | 30min |
| E2E Scenario 14.4 | 5min | 15min |
| E2E Scenario 14.5 | 5min | 10min |
| **Full Suite** | **11h** | **18h** |

---

### Live Validation Gates

```bash
# Gate 1: Full Lifecycle
pytest tests/e2e/test_training_lifecycle.py -v
# Expected: 100% pass rate

# Gate 2: Rollback Performance
pytest tests/e2e/test_training_lifecycle.py::test_rollback_flow -v --timeout=1800
# Expected: Completes <5 minutes

# Gate 3: Data Quality Handling
pytest tests/e2e/test_training_lifecycle.py::test_data_quality_failure -v
# Expected: Proper abort and alert
```

---

### Risk Register

| Risk ID | Risk | Probability | Impact | Mitigation |
|---------|------|-------------|--------|------------|
| R-14-01 | E2E tests too slow for CI | Medium | Medium | Split into fast/slow suites; slow runs nightly |
| R-14-02 | Test data not representative | Low | High | Use production data samples (anonymized) |
| R-14-03 | Flaky tests due to timing | Medium | Medium | Use deterministic waits; retry logic |
| R-14-04 | Test environment resource limits | Low | Medium | Use dedicated test environment; mock long operations |

---

### Rollback Plan

```bash
# Disable training E2E tests
redis-cli SET launch:training:e2e_tests:enabled 0

# Use baseline model
redis-cli SET launch:training:enabled 0

# Fallback to integration tests only
pytest tests/test_ml/integration/ -v --ignore=tests/e2e/
```

---

## Parallelization Plan

### Dependency Analysis

```
ST-LAUNCH-012 ─────────────────────────────┐
                                            ├──> ST-LAUNCH-014
ST-LAUNCH-013 ─────────────────────────────┘
```

### Parallel Work Batches

#### BATCH A: Parallel Development (Days 9-10)

| Story | Agent | Scope | No Overlap |
|-------|-------|-------|------------|
| ST-LAUNCH-012 | Agent-A | `src/ml/training/`, `src/ml/models/` | ✅ |
| ST-LAUNCH-013 | Agent-B | `src/ml/validation/`, `src/ml/rollback/` | ✅ |

**Scope Isolation:**
- Agent-A: `training_pipeline.py`, `model_registry.py`
- Agent-B: `model_validator.py`, `model_rollback.py`

**No Conflicts:** Different files, can merge independently.

---

#### BATCH B: Sequential Integration (Day 11)

| Story | Agent | Dependencies |
|-------|-------|--------------|
| ST-LAUNCH-014 | Agent-C | Requires 012 + 013 merged |

**Prerequisite:**
```bash
# Verify 012 and 013 merged
git log --oneline | grep -E "ST-LAUNCH-012|ST-LAUNCH-013"
```

---

#### BATCH C: Final Validation (Day 12)

| Task | Agent | Dependencies |
|------|-------|--------------|
| E2E Test Execution | Agent-C | All stories complete |
| Integration Test Fix | All | E2E failures |
| Documentation Update | Agent-D | All stories complete |

---

### Parallelization Table

| Day | Batch | Stories | Agents | Parallel? |
|-----|-------|---------|--------|-----------|
| 9 | A | 012 (Tasks 1-4) | Agent-A | ✅ Yes |
| 9 | A | 013 (Tasks 1-2) | Agent-B | ✅ Yes |
| 10 | A | 012 (Tasks 5-7) | Agent-A | ✅ Yes |
| 10 | A | 013 (Tasks 3-6) | Agent-B | ✅ Yes |
| 11 | B | 014 (Scenarios 1-3) | Agent-C | ❌ Sequential |
| 12 | C | 014 (Scenarios 4-5) | Agent-C | ❌ Sequential |
| 12 | C | E2E Validation | All | ❌ Sequential |

---

### Ownership Registration

Before starting parallel work:

```bash
# Agent-A claims ST-LAUNCH-012 scope
redis-cli HSET bmad:chiseai:ownership src:ml:training "ST-LAUNCH-012/agent-a"
redis-cli HSET bmad:chiseai:ownership src:ml:model_registry "ST-LAUNCH-012/agent-a"

# Agent-B claims ST-LAUNCH-013 scope
redis-cli HSET bmad:chiseai:ownership src:ml:validation "ST-LAUNCH-013/agent-b"
redis-cli HSET bmad:chiseai:ownership src:ml:rollback "ST-LAUNCH-013/agent-b"
```

---

## Model Registry Dependency (ST-LAUNCH-019)

### Status Check

ST-LAUNCH-019 (Model Registry Implementation) is **PLANNED** but:
- `src/ml/models/model_registry.py` already exists (15KB)
- `src/ml/models/model_storage.py` already exists (14KB)

### Assessment

**ST-LAUNCH-019 appears partially implemented.** ST-LAUNCH-012 should:
1. Verify model_registry.py has required features
2. Extend if missing: semantic versioning, metadata schema
3. Document any gaps for ST-LAUNCH-019 completion

### Required Model Registry Features

| Feature | Required By | Status |
|---------|-------------|--------|
| Semantic versioning | ST-LAUNCH-012 | TBD - verify |
| Model storage | ST-LAUNCH-012 | TBD - verify |
| Metadata schema | ST-LAUNCH-012 | TBD - verify |
| Rollback support | ST-LAUNCH-013 | TBD - verify |
| S3 backend | ST-LAUNCH-019 | Not required for launch |

---

## Test Coverage Matrix

| Story | Unit Tests | Integration Tests | E2E Tests | Target |
|-------|------------|-------------------|-----------|--------|
| ST-LAUNCH-012 | 8 | 3 | 1 | 80% |
| ST-LAUNCH-013 | 7 | 3 | 2 | 85% |
| ST-LAUNCH-014 | 0 | 2 | 5 | N/A |
| **TOTAL** | **15** | **8** | **8** | **80%+** |

---

## Rollback Summary

| Story | Rollback Command | Recovery Time |
|-------|------------------|---------------|
| ST-LAUNCH-012 | `redis-cli SET launch:training:pipeline:enabled 0` | <30s |
| ST-LAUNCH-013 | `redis-cli SET launch:training:auto_rollback:enabled 0` | <30s |
| ST-LAUNCH-014 | `redis-cli SET launch:training:enabled 0` | <30s |

---

## Sign-Off Checklist

### Before Starting
- [ ] ST-LAUNCH-007 verified complete (Feature Extractor)
- [ ] ST-LAUNCH-011 verified complete (Retraining Trigger)
- [ ] Model registry state verified
- [ ] Ownership claimed for each story scope

### During Execution
- [ ] Daily progress updates to Discord
- [ ] Redis ownership maintained
- [ ] Test coverage tracked
- [ ] Blocking issues escalated immediately

### Before Close
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] All E2E scenarios passing
- [ ] Coverage targets met
- [ ] Documentation updated
- [ ] PR created with all changes

---

## Document Metadata

**Version:** 1.0  
**Created:** 2026-02-23  
**Author:** Aria (Executor Agent)  
**Story:** EP-LAUNCH-003  
**Status:** Ready for Execution

---

## Appendix: Quick Reference Commands

### Run All Tests
```bash
# Unit tests
pytest tests/test_ml/test_training_pipeline.py tests/test_ml/test_model_validation.py -v

# Integration tests
pytest tests/test_ml/integration/ -v

# E2E tests (long running)
pytest tests/e2e/test_training_lifecycle.py -v --timeout=28800
```

### Feature Flags
```bash
# Training pipeline
redis-cli GET launch:training:pipeline:enabled

# Auto-rollback
redis-cli GET launch:training:auto_rollback:enabled

# Shadow mode
redis-cli GET launch:training:shadow_mode:enabled

# Auto-trigger
redis-cli GET launch:training:auto_trigger:enabled
```

### Health Checks
```bash
# Pipeline status
redis-cli GET launch:training:pipeline:status

# Current model version
python -c "from src.ml.models.model_registry import ModelRegistry; print(ModelRegistry().get_latest_version())"

# Last training run
redis-cli GET launch:training:pipeline:last_run
```
