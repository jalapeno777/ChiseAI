# ChiseAI Launch Action Plan - Detailed Implementation Planning

**Date:** February 21, 2026  
**Target Launch:** March 7, 2026 (14 days)  
**Team Capacity:** 5 developers in parallel  
**Sprint Structure:** 2-week sprints

---

## Executive Summary

This document provides detailed story breakdowns, sprint assignments, parallelization strategies, and testing requirements for the ChiseAI Launch Action Plan. All stories are sized in story points (SP) with hour estimates and include specific file paths, acceptance criteria, and testing strategies.

---

## Story Breakdown with Detailed Specifications

### Story 1: LAUNCH-001 - Bybit Safety Hardening
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 12h

**Description:**  
Implement comprehensive safety assertions and environment validation for Bybit connector to ensure safe paper trading operations.

**Files to Modify:**
- `src/data/exchange/bybit_connector.py` - Add safety assertions and validation
- `src/data/exchange/credential_resolver.py` - Enhance credential validation
- `tests/test_data_exchange/test_bybit_connector.py` - Unit tests
- `tests/integration/test_bybit_safety.py` - Integration tests

**Scope:**
```
SCOPE_GLOBS:
  - "src/data/exchange/bybit_connector.py"
  - "src/data/exchange/credential_resolver.py"
  - "tests/test_data_exchange/test_bybit_connector.py"
  - "tests/integration/test_bybit_safety.py"

FORBIDDEN_GLOBS:
  - "infrastructure/terraform/**"
  - "docs/bmm-workflow-status.yaml"
```

**Implementation Details:**
1. **Environment Assertion Layer** (4h)
   - Add `BybitEnvironmentValidator` class
   - Validate demo mode before any trade operation
   - Assert testnet/demo flags are explicitly set
   - Block live trading in paper trading mode

2. **API Response Validation** (3h)
   - Add response schema validation for all endpoints
   - Validate order parameters before submission
   - Check position limits against configured max

3. **Safety Decorators** (3h)
   - `@require_demo_mode` decorator
   - `@validate_order_params` decorator
   - `@log_all_operations` decorator

4. **Error Handling** (2h)
   - Custom exceptions for safety violations
   - Automatic kill-switch trigger on safety breach
   - Audit logging for all safety events

**Acceptance Criteria:**
```yaml
AC1: Environment Validation
  Given: Bybit connector is initialized
  When: Credentials are loaded
  Then: Demo mode is explicitly verified and logged
  And: Live trading is blocked if PAPER_TRADING=true

AC2: Order Safety
  Given: An order is being placed
  When: Order parameters are validated
  Then: Position size <= max_position_limit
  And: Leverage <= max_leverage_limit
  And: Symbol is in allowed_symbols list

AC3: Safety Audit Trail
  Given: Any Bybit operation occurs
  When: Operation completes (success or failure)
  Then: Safety audit log entry is created
  And: Log includes: timestamp, operation, params_hash, safety_checks_passed

AC4: Kill Switch Integration
  Given: A safety violation is detected
  When: Violation severity is CRITICAL
  Then: Kill switch is triggered automatically
  And: All trading operations are halted
```

**Testing Strategy:**
- **Unit Tests (8 tests):**
  - `test_demo_mode_assertion_passes` - Valid demo config accepted
  - `test_live_mode_blocked_in_paper_trading` - Live trading blocked
  - `test_order_params_validation` - Position/leverage limits enforced
  - `test_safety_audit_logging` - All operations logged
  - `test_kill_switch_trigger_on_violation` - Auto kill-switch works
  - `test_invalid_credentials_rejected` - Bad creds blocked
  - `test_symbol_whitelist_enforcement` - Unauthorized symbols blocked
  - `test_decorator_chain_order` - Multiple decorators work together

- **Integration Tests (4 tests):**
  - `test_bybit_demo_endpoint_connection` - Real demo API connection
  - `test_order_placement_safety_flow` - End-to-end order safety
  - `test_position_limit_enforcement_live` - Live position limit test
  - `test_kill_switch_integration` - Kill switch triggers correctly

- **E2E Test:**
  - `test_paper_trading_safety_end_to_end` - Full safety flow simulation

**Story Point Justification:**  
2 SP = ~12 hours. Complexity is moderate (familiar codebase, clear requirements) but requires careful implementation of safety-critical code with comprehensive testing. Risk factor increases estimate from 8h to 12h.

---

### Story 2: LAUNCH-002 - WebSocket Circuit Breaker
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 8h

**Description:**  
Implement circuit breaker pattern for WebSocket connections to prevent cascading failures and provide graceful degradation.

**Files to Modify:**
- `src/data/exchange/bybit_connector.py` - Add circuit breaker integration
- `src/common/circuit_breaker.py` - Enhance existing implementation (if needed)
- `tests/test_common/test_circuit_breaker.py` - Add WebSocket-specific tests
- `tests/test_data_exchange/test_websocket_circuit_breaker.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/data/exchange/bybit_connector.py"
  - "src/common/circuit_breaker.py"
  - "tests/test_common/test_circuit_breaker.py"
  - "tests/test_data_exchange/test_websocket_circuit_breaker.py"
```

**Implementation Details:**
1. **WebSocket Circuit Breaker Integration** (3h)
   - Add circuit breaker to WebSocket connection manager
   - Track connection failures per endpoint
   - Implement half-open state for recovery testing

2. **Failure Detection** (2h)
   - Detect connection drops, timeouts, auth failures
   - Track latency spikes (>100ms threshold)
   - Monitor message rate anomalies

3. **Fallback Strategy** (2h)
   - REST API fallback when WebSocket is open
   - Exponential backoff for reconnection
   - Health check endpoint polling

4. **Metrics & Alerting** (1h)
   - Circuit breaker state metrics
   - Grafana dashboard updates
   - Alert on sustained OPEN state

**Acceptance Criteria:**
```yaml
AC1: Circuit Breaker States
  Given: WebSocket connection to Bybit
  When: 3 consecutive connection failures occur
  Then: Circuit breaker transitions to OPEN state
  And: No new WebSocket connection attempts for 30s

AC2: Half-Open Recovery
  Given: Circuit breaker is in OPEN state
  When: 30s timeout elapses
  Then: Circuit breaker transitions to HALF_OPEN
  And: Single test connection is attempted
  And: On success, transitions to CLOSED

AC3: REST Fallback
  Given: WebSocket circuit breaker is OPEN
  When: Market data is requested
  Then: System falls back to REST API polling
  And: Data freshness is maintained within 5s

AC4: Latency Monitoring
  Given: WebSocket is connected
  When: Message latency exceeds 100ms
  Then: Latency spike is recorded
  And: After 5 consecutive spikes, circuit opens
```

**Testing Strategy:**
- **Unit Tests (6 tests):**
  - `test_circuit_opens_after_failure_threshold` - State transition
  - `test_half_open_after_timeout` - Recovery testing
  - `test_rest_fallback_activated` - Fallback works
  - `test_latency_spike_detection` - Latency monitoring
  - `test_successful_recovery` - Close after success
  - `test_failure_in_half_open_reopens` - Reopen on failure

- **Integration Tests (3 tests):**
  - `test_websocket_failure_cascade_prevention` - No cascading failures
  - `test_rest_fallback_data_quality` - Fallback data is accurate
  - `test_circuit_metrics_export` - Metrics are exported

**Story Point Justification:**  
2 SP = ~8 hours. Building on existing circuit breaker pattern (see `test_common/test_circuit_breaker.py`). Main work is integration with WebSocket layer and testing failure scenarios.

---

### Story 3: LAUNCH-003 - Order Idempotency
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 8h

**Description:**  
Implement idempotency for order operations to prevent duplicate orders on retries and network failures.

**Files to Modify:**
- `src/execution/paper/order_simulator.py` - Add idempotency layer
- `src/data/execution/fill_model.py` - Track idempotency keys
- `src/common/idempotency.py` - New utility module
- `tests/test_execution/test_order_idempotency.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/execution/paper/order_simulator.py"
  - "src/data/execution/fill_model.py"
  - "src/common/idempotency.py"
  - "tests/test_execution/test_order_idempotency.py"
```

**Implementation Details:**
1. **Idempotency Key Generation** (2h)
   - UUID-based idempotency keys
   - Deterministic key generation from order params
   - Key persistence in Redis

2. **Order Operation Deduplication** (3h)
   - Check idempotency key before execution
   - Return cached result for duplicate keys
   - TTL-based key expiration (24h)

3. **Fill Tracking** (2h)
   - Link fills to original idempotency key
   - Prevent duplicate fill processing
   - Reconciliation on startup

4. **Edge Case Handling** (1h)
   - Partial fill scenarios
   - Order modification idempotency
   - Cancel operation idempotency

**Acceptance Criteria:**
```yaml
AC1: Duplicate Order Prevention
  Given: An order with idempotency key "abc123"
  When: Same order is submitted twice
  Then: Second submission returns cached result
  And: Only one order is placed with exchange

AC2: Idempotency Key Persistence
  Given: An order is placed successfully
  When: System restarts
  Then: Idempotency key remains in storage
  And: Duplicate detection works after restart

AC3: Partial Fill Handling
  Given: An order has partial fills
  When: Retry occurs with same idempotency key
  Then: New fills are aggregated
  And: Existing fills are not duplicated

AC4: TTL Expiration
  Given: An idempotency key is 24h old
  When: New order with same key is submitted
  Then: Key is treated as expired
  And: New order is processed normally
```

**Testing Strategy:**
- **Unit Tests (7 tests):**
  - `test_duplicate_order_detected` - Deduplication works
  - `test_idempotency_key_generation` - Keys are unique
  - `test_cached_result_returned` - Cache hit returns stored result
  - `test_redis_persistence` - Keys survive restart
  - `test_partial_fill_aggregation` - Partial fills handled
  - `test_ttl_expiration` - Old keys expire
  - `test_concurrent_order_handling` - Race condition safe

- **Integration Tests (3 tests):**
  - `test_end_to_end_idempotency` - Full flow test
  - `test_failure_recovery_idempotency` - Recovery scenario
  - `test_graceful_degradation_without_redis` - Redis down handling

**Story Point Justification:**  
2 SP = ~8 hours. Requires careful handling of distributed state (Redis) and edge cases around partial fills. Complexity is moderate due to state management requirements.

---

### Story 4: LAUNCH-004 - Scheduler Verification
**Priority:** P0 | **Story Points:** 1 SP | **Estimated Hours:** 6h

**Description:**  
Verify and harden ML optimization scheduler for reliable automated execution.

**Files to Modify:**
- `src/ml/scheduler.py` - Add verification and hardening
- `tests/test_ml/test_scheduler.py` - Enhance existing tests
- `src/ml/scheduler_health_check.py` - New health check module

**Scope:**
```
SCOPE_GLOBS:
  - "src/ml/scheduler.py"
  - "tests/test_ml/test_scheduler.py"
  - "src/ml/scheduler_health_check.py"
```

**Implementation Details:**
1. **Scheduler Health Verification** (2h)
   - Add health check endpoint
   - Verify job queue processing
   - Check schedule state consistency

2. **Failure Recovery** (2h)
   - Automatic retry for failed jobs
   - State recovery on startup
   - Missed job detection and catch-up

3. **Monitoring Integration** (1.5h)
   - Prometheus metrics for scheduler
   - Grafana dashboard panel
   - Alert on scheduler failures

4. **Configuration Validation** (0.5h)
   - Validate schedule configs on load
   - Prevent overlapping job schedules
   - Warn on excessive job frequency

**Acceptance Criteria:**
```yaml
AC1: Health Check
  Given: Scheduler is running
  When: Health check endpoint is called
  Then: Returns 200 OK if all jobs healthy
  And: Returns 503 if any job failed last 3 attempts

AC2: Missed Job Recovery
  Given: Scheduler was down for 2 hours
  When: Scheduler restarts
  Then: Missed jobs are identified
  And: Critical jobs are executed immediately
  And: Non-critical jobs are skipped or rescheduled

AC3: Retry Logic
  Given: A scheduled job fails
  When: Failure is detected
  Then: Job is retried up to 3 times
  And: Exponential backoff between retries
  And: Alert is sent after final failure

AC4: Schedule Validation
  Given: A new schedule configuration
  When: Config is loaded
  Then: Overlapping schedules are detected
  And: Invalid cron expressions are rejected
  And: Warning logged for schedules < 1 hour interval
```

**Testing Strategy:**
- **Unit Tests (5 tests):**
  - `test_health_check_passes_when_healthy` - Health check logic
  - `test_missed_job_detection` - Detects missed jobs
  - `test_retry_with_backoff` - Retry logic
  - `test_schedule_overlap_detection` - Overlap detection
  - `test_config_validation` - Invalid config rejection

- **Integration Tests (2 tests):**
  - `test_scheduler_recovery_after_crash` - Recovery simulation
  - `test_metrics_export` - Prometheus metrics

**Story Point Justification:**  
1 SP = ~6 hours. Building on existing scheduler (`src/ml/scheduler.py`). Main work is adding health checks and failure recovery. Well-understood domain.

---

### Story 5: LAUNCH-005 - Signal-to-Outcome Pipeline
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 16h

**Description:**  
Build pipeline to capture signals and match them with actual trade outcomes for ML feedback loop.

**Files to Modify:**
- `src/ml/feedback/orchestrator.py` - Main orchestration logic
- `src/ml/feedback/matcher.py` - Enhance existing matcher
- `src/market_analysis/signal_storage/models.py` - Add outcome fields
- `tests/test_ml/test_feedback/test_pipeline.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/ml/feedback/orchestrator.py"
  - "src/ml/feedback/matcher.py"
  - "src/market_analysis/signal_storage/models.py"
  - "tests/test_ml/test_feedback/test_pipeline.py"
```

**Implementation Details:**
1. **Signal Capture** (4h)
   - Hook into signal generation pipeline
   - Store signal with unique ID
   - Capture signal metadata (confidence, features)

2. **Outcome Tracking** (4h)
   - Listen to fill events from execution
   - Track TP/SL hits
   - Record manual closes and timeouts

3. **Signal-Outcome Matching** (5h)
   - Time-window based matching (24h default)
   - Handle multiple outcomes per signal
   - Calculate P&L for each match

4. **Pipeline Orchestration** (3h)
   - Async processing queue
   - Batch processing for efficiency
   - Error handling and retry logic

**Acceptance Criteria:**
```yaml
AC1: Signal Capture
  Given: A signal is generated
  When: Signal passes confidence threshold
  Then: Signal is stored with unique ID
  And: Signal metadata is captured
  And: Timestamp is recorded with millisecond precision

AC2: Outcome Capture
  Given: A trade is executed from a signal
  When: Trade closes (TP, SL, or manual)
  Then: Outcome is recorded with signal ID reference
  And: P&L is calculated and stored
  And: Exit timestamp is recorded

AC3: Signal-Outcome Matching
  Given: Signals and outcomes exist in database
  When: Matching job runs
  Then: Signals are matched to outcomes within 24h window
  And: Match confidence is calculated
  And: Unmatched signals are marked as pending

AC4: Pipeline Throughput
  Given: 1000 signals generated in 1 hour
  When: Pipeline processes signals
  Then: All signals are processed within 5 minutes
  And: 95%+ of signals are successfully matched to outcomes
```

**Testing Strategy:**
- **Unit Tests (8 tests):**
  - `test_signal_capture_stores_metadata` - Signal storage
  - `test_outcome_capture_links_to_signal` - Outcome linking
  - `test_matching_within_time_window` - Time window matching
  - `test_multiple_outcome_handling` - Multiple outcomes
  - `test_unmatched_signal_marking` - Pending signals
  - `test_batch_processing_efficiency` - Batch processing
  - `test_error_recovery` - Retry logic
  - `test_pnl_calculation_accuracy` - P&L calculation

- **Integration Tests (4 tests):**
  - `test_end_to_end_signal_to_outcome` - Full pipeline
  - `test_high_volume_processing` - Volume test
  - `test_database_persistence` - Data survives restart
  - `test_concurrent_signal_processing` - Concurrency test

- **E2E Test:**
  - `test_signal_outcome_pipeline_production` - Production-like simulation

**Story Point Justification:**  
2 SP = ~16 hours. This is the most complex story - requires integration across signal generation, execution, and storage layers. High complexity due to async processing, data consistency requirements, and volume handling.

---

### Story 6: LAUNCH-006 - Feature Extractor Market Data
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 12h

**Description:**  
Complete the feature extractor to pull market data and technical indicators for ML training samples.

**Files to Modify:**
- `src/ml/training/extractor.py` - Complete stub implementations
- `src/ml/training/features.py` - Add missing feature calculations
- `tests/test_ml/test_training/test_extractor.py` - Enhance tests
- `tests/test_ml/test_training/test_features.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/ml/training/extractor.py"
  - "src/ml/training/features.py"
  - "tests/test_ml/test_training/test_extractor.py"
  - "tests/test_ml/test_training/test_features.py"
```

**Implementation Details:**
1. **Market Data Integration** (4h)
   - Connect to market data cache
   - Fetch OHLCV data for signal timeframe
   - Handle missing data gracefully

2. **Technical Indicator Calculation** (4h)
   - RSI, MACD, Bollinger Bands
   - ATR (Average True Range)
   - Volume SMA ratio
   - Implement in `features.py`

3. **Markov Chain State Detection** (2h)
   - Integrate with existing Markov chain module
   - Extract trend state and confidence
   - Cache state lookups

4. **Feature Aggregation** (2h)
   - Combine all features into `ExtractedFeatures` object
   - Validate feature completeness
   - Handle partial data scenarios

**Acceptance Criteria:**
```yaml
AC1: Feature Completeness
  Given: A signal ID is provided
  When: Feature extraction runs
  Then: At least 10 features are extracted
  And: All core features (RSI, MACD, BB, ATR) are present
  And: Features are returned within 500ms

AC2: Market Data Integration
  Given: Market data is available
  When: Features are extracted
  Then: OHLCV data is fetched from cache
  And: Data freshness is verified (< 5 minutes old)
  And: Missing data triggers fallback to API

AC3: Technical Indicators
  Given: OHLCV data is available
  When: Technical indicators are calculated
  Then: RSI is in range [0, 100]
  And: MACD components are calculated
  And: Bollinger Bands width is positive
  And: ATR is non-negative

AC4: Markov Chain Integration
  Given: Signal timeframe and token
  When: Trend state is requested
  Then: Markov chain state is returned
  And: Confidence score is included [0.0, 1.0]
  And: State is cached for subsequent calls
```

**Testing Strategy:**
- **Unit Tests (8 tests):**
  - `test_all_core_features_extracted` - Feature completeness
  - `test_rsi_calculation_accuracy` - RSI math
  - `test_macd_calculation_accuracy` - MACD math
  - `test_bollinger_bands_calculation` - BB math
  - `test_atr_calculation` - ATR math
  - `test_markov_state_extraction` - Markov integration
  - `test_missing_data_handling` - Graceful degradation
  - `test_feature_caching` - Cache behavior

- **Integration Tests (3 tests):**
  - `test_end_to_end_feature_extraction` - Full extraction
  - `test_market_data_fallback` - Fallback behavior
  - `test_performance_under_load` - Performance test

**Story Point Justification:**  
2 SP = ~12 hours. Mathematical calculations require careful testing. Integration with market data and Markov chain adds complexity. Building on existing stubs in `extractor.py`.

---

### Story 7: LAUNCH-007 - ECE from Outcomes
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 8h

**Description:**  
Update ECE (Expected Calibration Error) calculation to use actual trade outcomes instead of just predictions.

**Files to Modify:**
- `src/confidence/ece.py` - Add outcome-based calculation
- `src/confidence/ece_tracker.py` - Integrate with outcomes
- `src/ml/calibration/dynamic.py` - Update threshold adjuster
- `tests/test_confidence/test_ece_outcomes.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/confidence/ece.py"
  - "src/confidence/ece_tracker.py"
  - "src/ml/calibration/dynamic.py"
  - "tests/test_confidence/test_ece_outcomes.py"
```

**Implementation Details:**
1. **Outcome-Based ECE Calculation** (3h)
   - Modify `ece.py` to accept actual outcomes
   - Calculate accuracy per confidence bin using real P&L
   - Support different outcome types (TP hit, SL hit, etc.)

2. **ECE Tracker Integration** (2h)
   - Update `ece_tracker.py` to pull from signal-outcome pipeline
   - Daily ECE recalculation job
   - Store historical ECE trends

3. **Threshold Adjustment Integration** (2.5h)
   - Connect `dynamic.py` to outcome-based ECE
   - Trigger threshold adjustments on ECE changes
   - Maintain adjustment history

4. **Daily Update Job** (0.5h)
   - Scheduler job for daily ECE update
   - Alert on ECE degradation > 15%

**Acceptance Criteria:**
```yaml
AC1: Outcome-Based ECE
  Given: Signals with outcomes exist
  When: ECE is calculated
  Then: Actual trade outcomes are used
  And: Accuracy per bin reflects real P&L
  And: ECE value is in range [0.0, 1.0]

AC2: Daily ECE Update
  Given: New outcomes are recorded daily
  When: Daily ECE job runs at 2 AM UTC
  Then: ECE is recalculated for all signal types
  And: Results are stored with timestamp
  And: Previous day's ECE is archived

AC3: ECE Trend Tracking
  Given: ECE is calculated daily
  When: 7 days of ECE data exists
  Then: Trend is calculated (improving/stable/degrading)
  And: Alert triggers if ECE degrades > 15%

AC4: Threshold Adjustment Trigger
  Given: ECE calculation completes
  When: ECE > 0.15 (degraded calibration)
  Then: Threshold adjustment is triggered
  And: Adjustment follows guardrails (max 10% change)
  And: Adjustment is logged with reason
```

**Testing Strategy:**
- **Unit Tests (6 tests):**
  - `test_ece_calculation_with_outcomes` - Outcome-based ECE
  - `test_accuracy_per_bin` - Bin accuracy
  - `test_daily_update_job` - Daily job
  - `test_trend_calculation` - Trend detection
  - `test_threshold_trigger_on_high_ece` - Auto adjustment
  - `test_guardrails_enforced` - Adjustment limits

- **Integration Tests (3 tests):**
  - `test_end_to_end_ece_pipeline` - Full flow
  - `test_alert_on_ece_degradation` - Alerting
  - `test_historical_trend_storage` - Persistence

**Story Point Justification:**  
2 SP = ~8 hours. Mathematical calculations are straightforward. Main work is integration with signal-outcome pipeline and existing calibration system. Building on existing `ece.py` and `dynamic.py`.

---

### Story 8: LAUNCH-008 - Model Retraining Trigger
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 10h

**Description:**  
Implement automatic model retraining triggers based on performance degradation and schedule.

**Files to Modify:**
- `src/ml/training/pipeline.py` - Add retraining trigger logic
- `src/ml/training/cli.py` - Add retraining commands
- `src/ml/scheduler.py` - Add retraining jobs
- `tests/test_ml/test_training/test_retraining.py` - New test file

**Scope:**
```
SCOPE_GLOBS:
  - "src/ml/training/pipeline.py"
  - "src/ml/training/cli.py"
  - "src/ml/scheduler.py"
  - "tests/test_ml/test_training/test_retraining.py"
```

**Implementation Details:**
1. **Retraining Trigger Conditions** (3h)
   - ECE degradation > 15%
   - Accuracy drop > 10% over 3 days
   - Scheduled weekly retraining
   - Manual trigger API

2. **Training Pipeline Integration** (3h)
   - Trigger `TrainingPipeline` with new data
   - Incremental vs full retraining decision
   - Model validation before promotion

3. **Scheduler Integration** (2h)
   - Weekly retraining job
   - Priority queue for urgent retraining
   - Job status tracking

4. **CLI & API** (2h)
   - `chiseai ml retrain` command
   - HTTP API endpoint for manual trigger
   - Status query endpoint

**Acceptance Criteria:**
```yaml
AC1: Automatic Trigger on Degradation
  Given: Model ECE exceeds 0.15 for 2 consecutive days
  When: Daily check runs
  Then: Retraining job is queued
  And: Alert is sent to team
  And: Job has HIGH priority

AC2: Scheduled Retraining
  Given: Weekly schedule is configured for Sunday 3 AM
  When: Scheduled time arrives
  Then: Retraining job starts automatically
  And: Uses last 30 days of data
  And: Previous model is backed up

AC3: Model Validation
  Given: Retraining completes
  When: New model is trained
  Then: Model is validated on holdout set
  And: If accuracy < previous - 5%, rollback
  And: If accuracy >= previous, auto-promote

AC4: Manual Trigger
  Given: Operator wants to trigger retraining
  When: CLI command or API is called
  Then: Retraining job is queued immediately
  And: Job ID is returned for tracking
  And: Status can be queried via API
```

**Testing Strategy:**
- **Unit Tests (7 tests):**
  - `test_ece_trigger_fires_correctly` - ECE trigger
  - `test_accuracy_drop_trigger` - Accuracy trigger
  - `test_scheduled_trigger` - Schedule trigger
  - `test_manual_trigger_api` - Manual trigger
  - `test_model_validation_pass` - Validation pass
  - `test_model_validation_fail_rollback` - Rollback
  - `test_job_priority_queue` - Priority handling

- **Integration Tests (3 tests):**
  - `test_end_to_end_retraining_flow` - Full retraining
  - `test_rollback_on_validation_failure` - Rollback test
  - `test_concurrent_retraining_prevention` - No concurrent jobs

**Story Point Justification:**  
2 SP = ~10 hours. Requires careful orchestration of training jobs, validation, and rollback. Integration with scheduler adds complexity. Model validation is critical for safety.

---

### Story 9: LAUNCH-009 - Auto-Threshold Adjustment
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 8h

**Description:**  
Complete auto-threshold adjustment with velocity limits and guardrails for production safety.

**Files to Modify:**
- `src/ml/calibration/dynamic.py` - Complete implementation
- `src/ml/calibration/controller.py` - Integration
- `tests/test_ml/test_calibration/test_dynamic.py` - Enhance tests

**Scope:**
```
SCOPE_GLOBS:
  - "src/ml/calibration/dynamic.py"
  - "src/ml/calibration/controller.py"
  - "tests/test_ml/test_calibration/test_dynamic.py"
```

**Implementation Details:**
1. **Velocity Limits** (2h)
   - Max 3 adjustments per hour per signal type
   - Track adjustment history in Redis
   - Cooldown period: 15 minutes

2. **Oscillation Detection** (2h)
   - Track last N adjustments
   - Detect rapid flip-flops (up/down/up)
   - Block adjustments if oscillating

3. **Extreme Value Protection** (2h)
   - Hard limits: min 0.40, max 0.95
   - Gradual approach to limits
   - Alert on limit approach

4. **Guardrail Enforcement** (2h)
   - Max single adjustment: 10%
   - Emergency override capability
   - Audit logging for all adjustments

**Acceptance Criteria:**
```yaml
AC1: Velocity Limit
  Given: 3 adjustments made in last hour for "entry" signals
  When: 4th adjustment is attempted
  Then: Adjustment is blocked
  And: Warning is logged
  And: Retry is scheduled for 1 hour later

AC2: Cooldown Period
  Given: An adjustment was made 10 minutes ago
  When: New adjustment is attempted
  Then: Adjustment is blocked (cooldown = 15 min)
  And: Reason "cooldown_active" is returned

AC3: Oscillation Detection
  Given: Last 3 adjustments: +5%, -5%, +5%
  When: New +5% adjustment is attempted
  Then: Adjustment is blocked
  And: "oscillation_detected" alert is sent
  And: Manual review is required

AC4: Extreme Value Protection
  Given: Current threshold is 0.92
  When: Adjustment would set threshold to 0.97
  Then: Adjustment is capped at 0.95
  And: "approaching_max_threshold" warning is logged

AC5: Audit Trail
  Given: Any threshold adjustment occurs
  When: Adjustment is applied or blocked
  Then: Audit log entry is created
  And: Entry includes: timestamp, old_val, new_val, reason, ece_before
```

**Testing Strategy:**
- **Unit Tests (8 tests):**
  - `test_velocity_limit_enforcement` - Velocity limit
  - `test_cooldown_period` - Cooldown
  - `test_oscillation_detection` - Oscillation
  - `test_extreme_value_protection` - Limits
  - `test_max_adjustment_size` - Max change
  - `test_audit_logging` - Audit trail
  - `test_emergency_override` - Override
  - `test_guardrail_combinations` - Multiple guards

- **Integration Tests (2 tests):**
  - `test_end_to_end_adjustment_flow` - Full flow
  - `test_redis_persistence_of_history` - Persistence

**Story Point Justification:**  
2 SP = ~8 hours. Building on existing `dynamic.py` which already has guardrail stubs. Main work is implementing enforcement logic and comprehensive testing of edge cases.

---

### Story 10: LAUNCH-010 - End-to-End Testing
**Priority:** P0 | **Story Points:** 2 SP | **Estimated Hours:** 12h

**Description:**  
Create comprehensive E2E tests covering the complete learning loop from signal to model update.

**Files to Modify:**
- `tests/e2e/test_learning_loop.py` - New E2E test file
- `tests/e2e/conftest.py` - E2E test fixtures
- `tests/e2e/test_data/` - Test data fixtures

**Scope:**
```
SCOPE_GLOBS:
  - "tests/e2e/test_learning_loop.py"
  - "tests/e2e/conftest.py"
  - "tests/e2e/test_data/**"
```

**Implementation Details:**
1. **Test Infrastructure** (3h)
   - Docker Compose setup for E2E tests
   - Test database seeding
   - Mock exchange connector

2. **Signal-to-Outcome Flow** (3h)
   - Generate test signals
   - Simulate trade execution
   - Verify outcome recording

3. **Feature Extraction Flow** (2h)
   - Verify feature extraction from signals
   - Test training sample creation
   - Validate feature completeness

4. **Model Update Flow** (2h)
   - Trigger model retraining
   - Validate new model performance
   - Test model promotion

5. **Integration Scenarios** (2h)
   - Full loop: signal → outcome → features → retraining
   - Error recovery scenarios
   - Performance under load

**Acceptance Criteria:**
```yaml
AC1: Signal-to-Outcome E2E
  Given: E2E test environment is running
  When: Test signal is generated
  Then: Signal is stored in database
  And: Simulated trade executes
  And: Outcome is recorded and matched
  And: Complete flow completes within 30 seconds

AC2: Feature Extraction E2E
  Given: Signal with outcome exists
  When: Feature extraction runs
  Then: Training sample is created
  And: All 10+ features are present
  And: Sample is stored in training database

AC3: Model Retraining E2E
  Given: 100 training samples exist
  When: Retraining is triggered
  Then: Model trains successfully
  And: Validation accuracy is calculated
  And: Model is promoted if accuracy >= threshold

AC4: Full Learning Loop
  Given: Clean E2E environment
  When: 10 signals are generated over 5 minutes
  Then: All signals are processed end-to-end
  And: Outcomes are captured
  And: Features are extracted
  And: ECE is updated
  And: No errors occur in any component
```

**Testing Strategy:**
- **E2E Tests (5 tests):**
  - `test_signal_to_outcome_flow` - Basic flow
  - `test_feature_extraction_e2e` - Feature extraction
  - `test_model_retraining_e2e` - Retraining
  - `test_full_learning_loop` - Complete loop
  - `test_error_recovery_e2e` - Error handling

- **Performance Test:**
  - `test_learning_loop_performance` - 100 signals in 5 minutes

**Story Point Justification:**  
2 SP = ~12 hours. E2E tests require significant infrastructure setup (Docker, test data, mocks). Each test covers multiple components, making debugging complex. High value but time-intensive.

---

## Sprint Assignments

### Sprint 1: Days 1-7 (Feb 21 - Feb 27)
**Goal:** Foundation & Safety - Complete Phase 1, start Phase 2

| Story | Assignee | SP | Hours | Dependencies |
|-------|----------|-----|-------|--------------|
| LAUNCH-001 | Dev-A | 2 | 12h | None |
| LAUNCH-002 | Dev-B | 2 | 8h | LAUNCH-001 (partial) |
| LAUNCH-003 | Dev-C | 2 | 8h | None |
| LAUNCH-004 | Dev-D | 1 | 6h | None |
| LAUNCH-005 | Dev-E | 2 | 16h | LAUNCH-001, LAUNCH-003 |
| **Sprint 1 Total** | | **9** | **50h** | |

**Sprint 1 Capacity:** 5 devs × 7 days × 6h/day = 210h  
**Utilization:** 50h / 210h = 24% (conservative for first sprint)

**Sprint 1 Milestones:**
- Day 3: Bybit safety hardening complete (LAUNCH-001)
- Day 5: WebSocket circuit breaker + order idempotency complete
- Day 7: Signal-to-outcome pipeline operational, 1 week of data captured

---

### Sprint 2: Days 8-14 (Feb 28 - Mar 7)
**Goal:** Integration & Launch - Complete Phase 2, 3, 4

| Story | Assignee | SP | Hours | Dependencies |
|-------|----------|-----|-------|--------------|
| LAUNCH-006 | Dev-A | 2 | 12h | LAUNCH-005 |
| LAUNCH-007 | Dev-B | 2 | 8h | LAUNCH-005, LAUNCH-006 |
| LAUNCH-008 | Dev-C | 2 | 10h | LAUNCH-006, LAUNCH-007 |
| LAUNCH-009 | Dev-D | 2 | 8h | LAUNCH-007 |
| LAUNCH-010 | Dev-E | 2 | 12h | LAUNCH-005, LAUNCH-006, LAUNCH-007, LAUNCH-008 |
| **Sprint 2 Total** | | **10** | **50h** | |

**Sprint 2 Capacity:** 5 devs × 7 days × 6h/day = 210h  
**Utilization:** 50h / 210h = 24%

**Sprint 2 Milestones:**
- Day 9: Phase 2 complete, Phase 3 kickoff
- Day 10: Feature extractor + ECE from outcomes complete
- Day 12: Model retraining + auto-threshold complete
- Day 13: E2E tests passing
- Day 14: Go/No-Go decision

---

## Parallel Work Streams

### Stream A: Execution Safety (Dev-A, Dev-B)
**Stories:** LAUNCH-001, LAUNCH-002, LAUNCH-003  
**Parallelization:**
- LAUNCH-001 (Bybit Safety) and LAUNCH-003 (Order Idempotency) can start immediately in parallel
- LAUNCH-002 (WebSocket Circuit Breaker) needs partial LAUNCH-001 for WebSocket layer

**Integration Point:**  
All three stories integrate in `src/data/exchange/bybit_connector.py` - coordinate changes carefully.

### Stream B: Scheduler & Infrastructure (Dev-D)
**Stories:** LAUNCH-004  
**Parallelization:**
- Can run completely in parallel with all other stories
- No dependencies on other launch stories

**Integration Point:**  
LAUNCH-004 provides scheduler for LAUNCH-008 (retraining trigger) and LAUNCH-007 (daily ECE job).

### Stream C: ML Pipeline (Dev-E, Dev-A, Dev-B, Dev-C)
**Stories:** LAUNCH-005, LAUNCH-006, LAUNCH-007, LAUNCH-008, LAUNCH-009, LAUNCH-010  
**Parallelization:**
```
LAUNCH-005 (Signal-to-Outcome)
    ↓
LAUNCH-006 (Feature Extractor) ← can start after LAUNCH-005 core is done
    ↓
LAUNCH-007 (ECE from Outcomes) ← needs LAUNCH-005 and LAUNCH-006
    ↓
LAUNCH-008 (Model Retraining) ← needs LAUNCH-006 and LAUNCH-007
LAUNCH-009 (Auto-Threshold) ← needs LAUNCH-007
    ↓
LAUNCH-010 (E2E Testing) ← needs all above
```

**Optimization:**
- LAUNCH-006 can start once LAUNCH-005 has basic signal storage working
- LAUNCH-007 and LAUNCH-008 can overlap after LAUNCH-006 completes
- LAUNCH-009 is independent once LAUNCH-007 provides ECE data

---

## Testing Requirements Summary

### Unit Test Coverage per Story

| Story | Unit Tests | Integration Tests | E2E Tests |
|-------|------------|-------------------|-----------|
| LAUNCH-001 | 8 | 4 | 1 |
| LAUNCH-002 | 6 | 3 | 0 |
| LAUNCH-003 | 7 | 3 | 0 |
| LAUNCH-004 | 5 | 2 | 0 |
| LAUNCH-005 | 8 | 4 | 1 |
| LAUNCH-006 | 8 | 3 | 0 |
| LAUNCH-007 | 6 | 3 | 0 |
| LAUNCH-008 | 7 | 3 | 0 |
| LAUNCH-009 | 8 | 2 | 0 |
| LAUNCH-010 | 0 | 0 | 5 |
| **Total** | **63** | **27** | **7** |

### Test Infrastructure Requirements

1. **Docker Compose for E2E:**
   - PostgreSQL for signal storage
   - Redis for caching and idempotency
   - InfluxDB for metrics
   - Mock exchange server

2. **Test Data:**
   - Historical OHLCV data (CSV format)
   - Sample signals with known outcomes
   - Pre-calculated feature expectations

3. **CI Integration:**
   - All unit tests run on every PR
   - Integration tests run on merge to main
   - E2E tests run nightly + on release candidate

---

## Acceptance Criteria Templates

### Standard AC Template
```yaml
AC[N]: [Title]
  Given: [Precondition]
  When: [Action]
  Then: [Expected result 1]
  And: [Expected result 2]
  And: [Expected result 3]
```

### Performance AC Template
```yaml
AC[N]: [Performance Title]
  Given: [Load condition]
  When: [Operation runs]
  Then: [Metric] is [operator] [threshold]
  And: [Metric 2] is [operator] [threshold 2]
  Examples:
    - 1000 signals → processed in < 5 minutes
    - 100 concurrent users → response < 200ms
```

### Safety AC Template
```yaml
AC[N]: [Safety Title]
  Given: [System state]
  When: [Safety-critical event]
  Then: [Safety action occurs]
  And: [Audit trail created]
  And: [Alert sent if applicable]
```

---

## Risk Mitigation & Contingency

### Risk: Signal-to-Outcome Pipeline Delays
**Mitigation:**
- Start with CSV export as fallback (Day 3)
- Add DB integration in parallel (Day 5-7)
- If delayed, use CSV for first week of data

### Risk: Feature Extractor Complexity
**Mitigation:**
- Ship with 5 core features if 10 is not achievable
- Use existing cache data, add real-time later
- Prioritize RSI, MACD, BB (most important)

### Risk: Model Retraining Too Slow
**Mitigation:**
- Use incremental updates instead of full retraining
- Weekly batch retraining as fallback
- Manual trigger for urgent updates

### Risk: Integration Failures
**Mitigation:**
- Daily integration check-ins
- Shared test environment
- E2E tests run on every story completion

---

## Story Point Justification Summary

| Story | SP | Hours | Justification |
|-------|-----|-------|---------------|
| LAUNCH-001 | 2 | 12h | Safety-critical, comprehensive testing needed |
| LAUNCH-002 | 2 | 8h | Building on existing pattern, integration work |
| LAUNCH-003 | 2 | 8h | Distributed state management (Redis) |
| LAUNCH-004 | 1 | 6h | Well-understood domain, existing code |
| LAUNCH-005 | 2 | 16h | Most complex - async, multi-component integration |
| LAUNCH-006 | 2 | 12h | Mathematical calculations, multi-source integration |
| LAUNCH-007 | 2 | 8h | Math + integration with existing calibration |
| LAUNCH-008 | 2 | 10h | Orchestration, validation, rollback complexity |
| LAUNCH-009 | 2 | 8h | Edge cases, guardrail enforcement |
| LAUNCH-010 | 2 | 12h | Infrastructure setup, multi-component testing |
| **Total** | **19** | **100h** | |

---

## Definition of Done (DoD) per Story

All stories must meet:
- [ ] All acceptance criteria pass
- [ ] Unit tests written and passing (≥80% coverage for new code)
- [ ] Integration tests written and passing
- [ ] Code reviewed by at least 1 peer
- [ ] Documentation updated (docstrings, README if needed)
- [ ] No linting errors (ruff, mypy)
- [ ] Performance criteria met (if applicable)
- [ ] Security review passed (if touching auth/safety)
- [ ] Redis iterlog updated with decisions

---

## File Paths Reference

### Core Files by Component

**Bybit Connector:**
- `src/data/exchange/bybit_connector.py` - Main connector
- `src/data/exchange/credential_resolver.py` - Credential resolution

**ML Pipeline:**
- `src/ml/training/extractor.py` - Feature extraction
- `src/ml/training/features.py` - Feature calculations
- `src/ml/training/pipeline.py` - Training pipeline
- `src/ml/feedback/matcher.py` - Signal-outcome matching
- `src/ml/feedback/orchestrator.py` - Pipeline orchestration

**Calibration:**
- `src/confidence/ece.py` - ECE calculation
- `src/confidence/ece_tracker.py` - ECE tracking
- `src/ml/calibration/dynamic.py` - Threshold adjustment
- `src/ml/calibration/controller.py` - Threshold controller

**Scheduler:**
- `src/ml/scheduler.py` - Optimization scheduler

**Execution:**
- `src/execution/paper/order_simulator.py` - Order simulation
- `src/data/execution/fill_model.py` - Fill tracking

**Common:**
- `src/common/circuit_breaker.py` - Circuit breaker pattern
- `src/common/idempotency.py` - Idempotency utility (new)

**Tests:**
- `tests/test_data_exchange/` - Bybit connector tests
- `tests/test_ml/test_training/` - ML training tests
- `tests/test_ml/test_feedback/` - Feedback loop tests
- `tests/test_ml/test_calibration/` - Calibration tests
- `tests/test_confidence/` - ECE tests
- `tests/test_execution/` - Execution tests
- `tests/e2e/` - E2E tests

---

## Next Steps

1. **Create Stories in Taiga:** Use story IDs (LAUNCH-001 through LAUNCH-010)
2. **Assign Developers:** Based on parallelization plan above
3. **Set Up E2E Environment:** Docker Compose for testing
4. **Daily Standups:** Track progress against milestones
5. **Integration Check-ins:** Every 2 days for cross-story dependencies

---

*Document Version: 1.0*  
*Created: February 21, 2026*  
*Target Launch: March 7, 2026*
