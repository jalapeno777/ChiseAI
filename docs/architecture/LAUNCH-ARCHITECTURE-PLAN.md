# ChiseAI Launch Architecture Plan
## Date: 2026-02-21
## Target Launch: 2026-03-07 (14 days)
## Current Max Story ID: ST-AUTO-008 / ST-NS-043

---

## Executive Summary

This document defines the architecture for ChiseAI Launch Phase (EP-LAUNCH-001 through EP-LAUNCH-004), building on completed EP-NS-008 (Autonomous Control Plane) and integrating with in-progress EP-AUTO-GIT-001 (AI Swarm PR Pipeline).

**Critical Path:** 12 days minimum, 2-day buffer
**Total Stories:** 20 stories (54 SP total)
**Team Capacity:** ML Team + Execution Team parallel work streams

---

## Epic Structure

### EP-LAUNCH-001: Bybit Safety & Infrastructure Foundation
**Status:** NOT_STARTED  
**Target:** Days 1-4 (Feb 21-24)  
**SP:** 14  
**Owner:** Execution Team  
**Goal:** Harden Bybit integration with production-grade safety mechanisms

**Success Criteria:**
- 100% WebSocket uptime with automatic reconnection
- Zero duplicate orders in paper trading
- All safety assertions validated
- Circuit breaker operational with <500ms trigger time

**Rollback Strategy:**
- Redis flag `launch:safety:enabled` controls all safety features
- Individual feature flags per component
- Fast rollback: `redis-cli SET launch:safety:enabled false`

---

### EP-LAUNCH-002: Feedback Loop & ML Pipeline
**Status:** NOT_STARTED  
**Target:** Days 4-9 (Feb 25-Mar 2)  
**SP:** 18  
**Owner:** ML Team (primary), Execution Team (support)  
**Goal:** Complete signal-to-outcome pipeline with feature extraction

**Success Criteria:**
- <1h signal-to-outcome latency
- 10+ feature dimensions extracted
- 100% prediction capture rate
- Daily ECE updates operational

**Rollback Strategy:**
- Feature flag `launch:feedback:mode` (disabled/capture-only/full)
- DB migration reversible (new tables only)
- Historical data preserved for reprocessing

---

### EP-LAUNCH-003: Training Integration & Model Ops
**Status:** NOT_STARTED  
**Target:** Days 9-12 (Mar 3-6)  
**SP:** 15  
**Owner:** ML Team  
**Goal:** Automated model retraining with training pipeline integration

**Success Criteria:**
- Automatic retraining triggers on threshold breach
- Model versioning and rollback capability
- Training pipeline 100% automated
- <4h end-to-end retraining time

**Rollback Strategy:**
- Model registry with version pinning
- Automatic rollback to previous model on validation failure
- Feature flag `launch:training:auto` controls automation

---

### EP-LAUNCH-004: Launch Readiness & Validation
**Status:** NOT_STARTED  
**Target:** Days 12-14 (Mar 6-7)  
**SP:** 7  
**Owner:** Execution Team (primary), Both teams (E2E)  
**Goal:** Final validation, load testing, and Go/No-Go preparation

**Success Criteria:**
- >95% trade execution rate sustained for 24h
- >99.5% system uptime
- All runbooks validated
- Stakeholder sign-off complete

**Rollback Strategy:**
- Kill-switch: Single command stops all trading
- Git-based rollback: `git checkout <tag>` + restart
- Feature flag `launch:trading:enabled` master control

---

## Story Breakdown

### EP-LAUNCH-001: Bybit Safety & Infrastructure Foundation (14 SP)

#### ST-LAUNCH-001: WebSocket Circuit Breaker Implementation
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** None  
**Files:**
- `src/data/exchange/bybit_connector.py`
- `src/data/exchange/circuit_breaker.py` (new)
- `tests/unit/exchange/test_circuit_breaker.py`

**Acceptance Criteria:**
1. Circuit breaker monitors WebSocket connection health
2. Triggers after 3 consecutive failures or >30s no heartbeat
3. Automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)
4. State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
5. <500ms trigger time from failure detection
6. Metrics exposed: `websocket_circuit_breaker_state`, `websocket_reconnect_count`

**Technical Design:**
```python
class WebSocketCircuitBreaker:
    states = Enum('CLOSED', 'OPEN', 'HALF_OPEN')
    
    def __init__(self, failure_threshold=3, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = State.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
    
    def record_success(self): ...
    def record_failure(self): ...
    def can_execute(self) -> bool: ...
```

**Feature Flag:** `launch:safety:circuit_breaker:enabled` (default: true)

---

#### ST-LAUNCH-002: Order Idempotency Implementation
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** None  
**Files:**
- `src/data/exchange/bybit_connector.py`
- `src/data/exchange/order_tracker.py` (new)
- `tests/unit/exchange/test_order_idempotency.py`

**Acceptance Criteria:**
1. Client-generated order IDs with deterministic format: `{strategy_id}:{timestamp}:{nonce}`
2. Order tracker maintains state in Redis with 24h TTL
3. Duplicate order detection before API call
4. Idempotency key validated on all order operations
5. <50ms overhead for idempotency check
6. Metrics: `order_duplicate_blocked_count`, `order_idempotency_latency_ms`

**Technical Design:**
```python
class OrderTracker:
    def generate_order_id(self, strategy_id: str) -> str:
        timestamp = int(time.time() * 1000)
        nonce = self._get_nonce(strategy_id)
        return f"{strategy_id}:{timestamp}:{nonce}"
    
    def is_duplicate(self, order_id: str) -> bool:
        return self.redis.exists(f"order:{order_id}")
    
    def record_order(self, order_id: str, status: str):
        self.redis.setex(f"order:{order_id}", 86400, status)
```

**Feature Flag:** `launch:safety:order_idempotency:enabled` (default: true)

---

#### ST-LAUNCH-003: Bybit Environment Assertions
**Points:** 2  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** None  
**Files:**
- `src/data/exchange/bybit_connector.py`
- `src/data/exchange/environment_assertions.py` (new)
- `tests/unit/exchange/test_environment_assertions.py`

**Acceptance Criteria:**
1. Assert paper trading mode on startup (fail fast if live)
2. Validate API key permissions (read + trade only, no withdraw)
3. Check account balance thresholds (>1000 USDT paper balance)
4. Verify symbol availability and trading status
5. All assertions logged with structured format
6. Startup blocked until all assertions pass

**Technical Design:**
```python
class BybitEnvironmentAssertions:
    REQUIRED_PERMISSIONS = ['Read', 'Trade']
    MIN_BALANCE_USDT = 1000
    
    def validate_all(self) -> AssertionResult:
        results = [
            self._assert_paper_trading(),
            self._assert_api_permissions(),
            self._assert_balance_threshold(),
            self._assert_symbol_availability(),
        ]
        return AssertionResult(all(r.passed for r in results), results)
```

**Feature Flag:** `launch:safety:assertions:enabled` (default: true)

---

#### ST-LAUNCH-004: Scheduler Verification & Monitoring
**Points:** 2  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** ST-LAUNCH-001 (optional, can run parallel)  
**Files:**
- `src/execution/scheduler/scheduler_verifier.py` (new)
- `src/execution/scheduler/scheduler_monitor.py` (new)
- `tests/unit/execution/test_scheduler_verification.py`

**Acceptance Criteria:**
1. Verify all scheduled tasks are registered and running
2. Monitor task execution latency and success rate
3. Alert on missed executions (>5min delay)
4. Health check endpoint for scheduler status
5. Metrics: `scheduler_task_latency_ms`, `scheduler_missed_executions`

**Technical Design:**
```python
class SchedulerVerifier:
    EXPECTED_TASKS = [
        'signal_generation',
        'order_execution',
        'position_reconciliation',
        'ece_update',
    ]
    
    def verify_all_tasks(self) -> VerificationReport:
        # Check task registration in Redis
        # Verify last execution timestamps
        # Alert on deviations
        pass
```

**Feature Flag:** `launch:scheduler:verification:enabled` (default: true)

---

#### ST-LAUNCH-005: Safety Integration & E2E Tests
**Points:** 4  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** ST-LAUNCH-001, ST-LAUNCH-002, ST-LAUNCH-003  
**Files:**
- `tests/e2e/test_bybit_safety.py` (new)
- `tests/integration/test_circuit_breaker_integration.py` (new)

**Acceptance Criteria:**
1. E2E test: Simulate WebSocket failure, verify circuit breaker triggers
2. E2E test: Submit duplicate order, verify blocked
3. E2E test: Start with live API key, verify assertion failure
4. All safety features tested together
5. <5min E2E test execution time
6. 90%+ code coverage on safety components

**Feature Flag:** N/A (tests validate flags work)

---

### EP-LAUNCH-002: Feedback Loop & ML Pipeline (18 SP)

#### ST-LAUNCH-006: Signal-to-Outcome Pipeline Core
**Points:** 5  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** None (can start immediately)  
**Files:**
- `src/ml/feedback/signal_outcome_pipeline.py` (new)
- `src/ml/feedback/models.py` (new - SignalOutcome dataclass)
- `src/ml/storage/signal_outcome_store.py` (new)
- `tests/unit/ml/test_signal_outcome_pipeline.py`

**Acceptance Criteria:**
1. Capture all signals with timestamp, prediction, confidence
2. Track signal lifecycle: generated → executed → filled → outcome
3. Store in PostgreSQL with proper indexing
4. <1h latency from signal generation to outcome recording
5. 100% capture rate (no dropped signals)
6. API for querying signal outcomes by date range, symbol, strategy

**Technical Design:**
```python
@dataclass
class SignalOutcome:
    signal_id: str
    timestamp: datetime
    symbol: str
    prediction: float  # predicted price move
    confidence: float  # model confidence
    signal_type: str   # entry, exit, adjust
    
    # Execution outcome
    executed: bool
    execution_timestamp: Optional[datetime]
    execution_price: Optional[float]
    
    # Fill outcome
    filled: bool
    fill_timestamp: Optional[datetime]
    fill_price: Optional[float]
    fill_quantity: Optional[float]
    
    # Actual outcome (after holding period)
    actual_return: Optional[float]
    outcome_timestamp: Optional[datetime]
    outcome_label: Optional[str]  # 'win', 'loss', 'breakeven'

class SignalOutcomePipeline:
    def capture_signal(self, signal: Signal) -> str:
        # Store signal generation event
        pass
    
    def record_execution(self, signal_id: str, execution: Execution):
        # Update with execution details
        pass
    
    def record_fill(self, signal_id: str, fill: Fill):
        # Update with fill details
        pass
    
    def calculate_outcome(self, signal_id: str):
        # Calculate actual return vs prediction
        pass
```

**Database Schema:**
```sql
CREATE TABLE signal_outcomes (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    prediction DECIMAL(12,8) NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    signal_type VARCHAR(32) NOT NULL,
    
    executed BOOLEAN DEFAULT FALSE,
    execution_timestamp TIMESTAMPTZ,
    execution_price DECIMAL(18,8),
    
    filled BOOLEAN DEFAULT FALSE,
    fill_timestamp TIMESTAMPTZ,
    fill_price DECIMAL(18,8),
    fill_quantity DECIMAL(18,8),
    
    actual_return DECIMAL(12,8),
    outcome_timestamp TIMESTAMPTZ,
    outcome_label VARCHAR(16),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_signal_outcomes_timestamp ON signal_outcomes(timestamp);
CREATE INDEX idx_signal_outcomes_symbol ON signal_outcomes(symbol);
CREATE INDEX idx_signal_outcomes_filled ON signal_outcomes(filled) WHERE filled = FALSE;
```

**Feature Flag:** `launch:feedback:signal_capture:enabled` (default: true)

---

#### ST-LAUNCH-007: Feature Extractor - Market Data
**Points:** 4  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-006 (uses signal timestamp)  
**Files:**
- `src/ml/training/extractor.py` (complete stubs)
- `src/ml/features/market_features.py` (new)
- `tests/unit/ml/test_feature_extractor.py`

**Acceptance Criteria:**
1. Extract 10+ features per signal:
   - Price features: current price, spread, ATR, volatility
   - Volume features: volume profile, volume delta, VWAP distance
   - Order book features: bid-ask imbalance, depth ratio
   - Time features: hour of day, day of week, session
   - Market regime: trend direction, volatility regime
2. Feature extraction <100ms per signal
3. Features cached in Redis for reuse
4. Feature schema versioned for backward compatibility
5. Missing data handling with imputation

**Technical Design:**
```python
class MarketFeatureExtractor:
    FEATURES = [
        'price_current',
        'spread_bps',
        'atr_14',
        'volatility_24h',
        'volume_profile_1h',
        'volume_delta',
        'vwap_distance_bps',
        'book_imbalance',
        'depth_ratio',
        'hour_of_day',
        'day_of_week',
        'market_session',
        'trend_direction',
        'volatility_regime',
    ]
    
    def extract(self, symbol: str, timestamp: datetime) -> FeatureVector:
        # Check cache first
        cache_key = f"features:{symbol}:{timestamp.isoformat()}"
        cached = self.redis.get(cache_key)
        if cached:
            return FeatureVector.from_json(cached)
        
        # Extract from market data
        features = {}
        features['price_current'] = self._get_price(symbol, timestamp)
        features['spread_bps'] = self._get_spread(symbol, timestamp)
        features['atr_14'] = self._get_atr(symbol, timestamp, period=14)
        # ... etc
        
        # Cache and return
        vector = FeatureVector(features, schema_version='1.0')
        self.redis.setex(cache_key, 3600, vector.to_json())
        return vector
```

**Feature Flag:** `launch:feedback:feature_extraction:enabled` (default: true)

---

#### ST-LAUNCH-008: Prediction-Outcome Matcher
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-006  
**Files:**
- `src/ml/feedback/matcher.py` (prediction-outcome matching)
- `src/ml/feedback/matching_engine.py` (new)
- `tests/unit/ml/test_prediction_matcher.py`

**Acceptance Criteria:**
1. Match predictions to actual outcomes after configurable holding period (default: 4h)
2. Calculate actual return vs predicted return
3. Label outcomes: 'win' (actual > 0), 'loss' (actual < 0), 'breakeven' (|actual| < 0.1%)
4. Handle partial fills and multiple executions per signal
5. <5min batch processing time for daily matches
6. Metrics: `matcher_pending_count`, `matcher_processed_count`, `matcher_latency_ms`

**Technical Design:**
```python
class PredictionOutcomeMatcher:
    HOLDING_PERIOD_HOURS = 4
    BREAKEVEN_THRESHOLD = 0.001  # 0.1%
    
    def match_outcomes(self, end_time: datetime) -> List[MatchedOutcome]:
        # Query all signals with fills but no outcome
        pending = self.store.get_pending_outcomes(end_time)
        
        matched = []
        for signal in pending:
            outcome_time = signal.fill_timestamp + timedelta(hours=self.HOLDING_PERIOD_HOURS)
            if outcome_time > end_time:
                continue  # Not ready yet
            
            # Get price at outcome time
            outcome_price = self._get_price_at_time(signal.symbol, outcome_time)
            actual_return = (outcome_price - signal.fill_price) / signal.fill_price
            
            # Label outcome
            if abs(actual_return) < self.BREAKEVEN_THRESHOLD:
                label = 'breakeven'
            elif actual_return > 0:
                label = 'win'
            else:
                label = 'loss'
            
            matched.append(MatchedOutcome(
                signal_id=signal.signal_id,
                actual_return=actual_return,
                outcome_timestamp=outcome_time,
                outcome_label=label
            ))
        
        return matched
    
    def update_signal_outcomes(self, matched: List[MatchedOutcome]):
        # Batch update signal_outcomes table
        pass
```

**Feature Flag:** `launch:feedback:matcher:enabled` (default: true)

---

#### ST-LAUNCH-009: ECE Calculator - Outcome-Based Updates
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-008  
**Files:**
- `src/ml/calibration/ece_calculator.py` (outcome-based)
- `src/ml/calibration/calibration_store.py` (new)
- `tests/unit/ml/test_ece_calculator.py`

**Acceptance Criteria:**
1. Calculate Expected Calibration Error (ECE) from actual outcomes
2. Bin predictions by confidence (10 bins: 0-10%, 10-20%, ..., 90-100%)
3. Calculate calibration: average accuracy per bin vs average confidence
4. Update daily with new outcomes
5. ECE < 0.1 (10%) considered well-calibrated
6. Trigger alerts if ECE > 0.15 (15%)

**Technical Design:**
```python
class ECECalculator:
    N_BINS = 10
    ECE_THRESHOLD = 0.10
    ALERT_THRESHOLD = 0.15
    
    def calculate_ece(self, start_time: datetime, end_time: datetime) -> ECEMetrics:
        # Get all matched outcomes in time range
        outcomes = self.store.get_outcomes(start_time, end_time)
        
        # Create confidence bins
        bins = [[] for _ in range(self.N_BINS)]
        for outcome in outcomes:
            bin_idx = min(int(outcome.confidence * 10), 9)
            bins[bin_idx].append(outcome)
        
        # Calculate per-bin metrics
        bin_metrics = []
        total_samples = len(outcomes)
        ece = 0.0
        
        for i, bin_outcomes in enumerate(bins):
            if not bin_outcomes:
                continue
            
            avg_confidence = sum(o.confidence for o in bin_outcomes) / len(bin_outcomes)
            avg_accuracy = sum(1.0 for o in bin_outcomes if o.outcome_label == 'win') / len(bin_outcomes)
            calibration_error = abs(avg_accuracy - avg_confidence)
            
            bin_metrics.append(BinMetrics(
                bin_index=i,
                confidence_range=(i/10, (i+1)/10),
                avg_confidence=avg_confidence,
                avg_accuracy=avg_accuracy,
                calibration_error=calibration_error,
                sample_count=len(bin_outcomes)
            ))
            
            ece += (len(bin_outcomes) / total_samples) * calibration_error
        
        return ECEMetrics(
            ece=ece,
            bin_metrics=bin_metrics,
            total_samples=total_samples,
            timestamp=datetime.utcnow()
        )
    
    def update_calibration(self, metrics: ECEMetrics):
        # Store in calibration history
        # Trigger alerts if needed
        if metrics.ece > self.ALERT_THRESHOLD:
            self._alert_high_ece(metrics)
```

**Feature Flag:** `launch:feedback:ece_updates:enabled` (default: true)

---

#### ST-LAUNCH-010: Dynamic Threshold Adjustment
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-009  
**Files:**
- `src/ml/calibration/threshold_adjuster.py` (new)
- `src/ml/calibration/dynamic_thresholds.py` (new)
- `tests/unit/ml/test_threshold_adjuster.py`

**Acceptance Criteria:**
1. Auto-adjust confidence thresholds based on ECE trends
2. Velocity limits: max 5% adjustment per day, max 20% cumulative
3. Increase threshold if ECE > 10% (model overconfident)
4. Decrease threshold if ECE < 5% (model underconfident)
5. All adjustments logged with reason
6. Manual override capability

**Technical Design:**
```python
class DynamicThresholdAdjuster:
    MAX_DAILY_ADJUSTMENT = 0.05  # 5%
    MAX_CUMULATIVE_ADJUSTMENT = 0.20  # 20%
    ECE_TARGET_LOW = 0.05
    ECE_TARGET_HIGH = 0.10
    
    def __init__(self):
        self.base_threshold = self._load_base_threshold()
        self.current_threshold = self.base_threshold
        self.cumulative_adjustment = 0.0
        self.adjustment_history = []
    
    def adjust_threshold(self, ece_metrics: ECEMetrics) -> float:
        if ece_metrics.ece > self.ECE_TARGET_HIGH:
            # Model overconfident - increase threshold
            adjustment = min(
                self.MAX_DAILY_ADJUSTMENT,
                self.MAX_CUMULATIVE_ADJUSTMENT - self.cumulative_adjustment
            )
            reason = f"ECE {ece_metrics.ece:.2%} > target {self.ECE_TARGET_HIGH:.2%}"
        elif ece_metrics.ece < self.ECE_TARGET_LOW:
            # Model underconfident - decrease threshold
            adjustment = -min(
                self.MAX_DAILY_ADJUSTMENT,
                self.MAX_CUMULATIVE_ADJUSTMENT + self.cumulative_adjustment
            )
            reason = f"ECE {ece_metrics.ece:.2%} < target {self.ECE_TARGET_LOW:.2%}"
        else:
            # Within target range - no adjustment
            return self.current_threshold
        
        # Apply adjustment
        new_threshold = self.current_threshold + adjustment
        new_threshold = max(0.1, min(0.9, new_threshold))  # Clamp to [0.1, 0.9]
        
        # Record adjustment
        self.adjustment_history.append(ThresholdAdjustment(
            timestamp=datetime.utcnow(),
            old_threshold=self.current_threshold,
            new_threshold=new_threshold,
            adjustment=adjustment,
            reason=reason,
            ece=ece_metrics.ece
        ))
        
        self.cumulative_adjustment += adjustment
        self.current_threshold = new_threshold
        
        return new_threshold
    
    def set_manual_threshold(self, threshold: float, reason: str):
        # Manual override with audit trail
        pass
```

**Feature Flag:** `launch:feedback:auto_threshold:enabled` (default: true)

---

### EP-LAUNCH-003: Training Integration & Model Ops (15 SP)

#### ST-LAUNCH-011: Model Retraining Trigger
**Points:** 5  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-009, ST-LAUNCH-010  
**Files:**
- `src/ml/training/retraining_trigger.py` (new)
- `src/ml/training/training_orchestrator.py` (new)
- `tests/unit/ml/test_retraining_trigger.py`

**Acceptance Criteria:**
1. Trigger retraining on: ECE > 15%, accuracy drop > 10%, manual request, weekly schedule
2. Check prerequisites before triggering: min 1000 new samples, data quality checks
3. Prevent concurrent retraining (one at a time)
4. Queue retraining requests if already running
5. Notify on trigger with reason and estimated duration
6. <30s from trigger check to training start

**Technical Design:**
```python
class RetrainingTrigger:
    ECE_TRIGGER_THRESHOLD = 0.15
    ACCURACY_DROP_THRESHOLD = 0.10
    MIN_SAMPLES_FOR_RETRAINING = 1000
    
    def __init__(self):
        self.orchestrator = TrainingOrchestrator()
        self.state = self._load_state()
    
    def check_and_trigger(self) -> Optional[TrainingJob]:
        # Check if already running
        if self.state.status == TrainingStatus.RUNNING:
            return None
        
        # Evaluate triggers
        trigger_reason = self._evaluate_triggers()
        if not trigger_reason:
            return None
        
        # Check prerequisites
        if not self._check_prerequisites():
            self._log_skipped(trigger_reason)
            return None
        
        # Trigger training
        job = self.orchestrator.start_training(
            reason=trigger_reason,
            dataset=self._prepare_dataset(),
            config=self._get_training_config()
        )
        
        self._notify_triggered(job)
        return job
    
    def _evaluate_triggers(self) -> Optional[str]:
        # Check ECE threshold
        latest_ece = self._get_latest_ece()
        if latest_ece and latest_ece.ece > self.ECE_TRIGGER_THRESHOLD:
            return f"ECE exceeded threshold: {latest_ece.ece:.2%}"
        
        # Check accuracy drop
        accuracy_trend = self._get_accuracy_trend()
        if accuracy_trend and accuracy_trend.drop > self.ACCURACY_DROP_THRESHOLD:
            return f"Accuracy dropped: {accuracy_trend.drop:.2%}"
        
        # Check weekly schedule
        if self._is_weekly_retraining_due():
            return "Weekly scheduled retraining"
        
        # Check manual trigger
        manual_request = self._check_manual_trigger()
        if manual_request:
            return f"Manual request: {manual_request.reason}"
        
        return None
```

**Feature Flag:** `launch:training:auto_trigger:enabled` (default: true)

---

#### ST-LAUNCH-012: Training Pipeline Integration
**Points:** 4  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-011  
**Files:**
- `src/ml/training/pipeline.py` (integrate with existing)
- `src/ml/training/data_loader.py` (new - outcomes-based)
- `src/ml/models/model_registry.py` (new)
- `tests/unit/ml/test_training_pipeline.py`

**Acceptance Criteria:**
1. Training pipeline uses signal outcomes as labeled data
2. Feature vectors automatically extracted for training samples
3. Model versioning with semantic versioning (MAJOR.MINOR.PATCH)
4. Automatic model validation after training
5. Pipeline completion <4h end-to-end
6. 80%+ test coverage on training code

**Technical Design:**
```python
class TrainingPipeline:
    def __init__(self):
        self.data_loader = OutcomeDataLoader()
        self.feature_extractor = MarketFeatureExtractor()
        self.model_registry = ModelRegistry()
        self.validator = ModelValidator()
    
    def run(self, config: TrainingConfig) -> TrainingResult:
        # 1. Load outcomes data
        outcomes = self.data_loader.load_labeled_outcomes(
            start_date=config.start_date,
            end_date=config.end_date,
            min_samples=config.min_samples
        )
        
        # 2. Extract features
        features = []
        labels = []
        for outcome in outcomes:
            feature_vector = self.feature_extractor.extract(
                outcome.symbol, outcome.timestamp
            )
            features.append(feature_vector.to_array())
            labels.append(self._label_to_target(outcome.outcome_label))
        
        # 3. Train model
        model = self._train_model(features, labels, config.hyperparameters)
        
        # 4. Validate
        validation_result = self.validator.validate(model, outcomes)
        
        # 5. Register if validation passes
        if validation_result.passed:
            version = self.model_registry.register(
                model=model,
                metrics=validation_result.metrics,
                config=config,
                parent_version=config.base_version
            )
            
            return TrainingResult(
                status=TrainingStatus.COMPLETED,
                model_version=version,
                metrics=validation_result.metrics,
                duration=datetime.utcnow() - config.start_time
            )
        else:
            return TrainingResult(
                status=TrainingStatus.FAILED,
                error=validation_result.errors,
                duration=datetime.utcnow() - config.start_time
            )
```

**Feature Flag:** `launch:training:pipeline:enabled` (default: true)

---

#### ST-LAUNCH-013: Model Validation & Rollback
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** ML Team  
**Dependencies:** ST-LAUNCH-012  
**Files:**
- `src/ml/models/model_validator.py` (new)
- `src/ml/models/rollback_manager.py` (new)
- `tests/unit/ml/test_model_validation.py`

**Acceptance Criteria:**
1. Validate new model on hold-out test set (20% of data)
2. Compare to current production model: must be better or within 2%
3. A/B test capability with traffic splitting (5% → 25% → 100%)
4. Automatic rollback if accuracy drops >5% in production
5. Rollback completes in <60s
6. All model versions preserved for audit

**Technical Design:**
```python
class ModelValidator:
    MIN_ACCURACY_IMPROVEMENT = 0.02  # 2%
    ROLLOBACK_ACCURACY_DROP = 0.05  # 5%
    
    def validate(self, new_model, test_data) -> ValidationResult:
        # Test on hold-out set
        new_metrics = self._evaluate_model(new_model, test_data)
        
        # Compare to current production model
        current_model = self.registry.get_production_model()
        current_metrics = self._evaluate_model(current_model, test_data)
        
        # Check improvement
        accuracy_diff = new_metrics.accuracy - current_metrics.accuracy
        
        if accuracy_diff < -self.MIN_ACCURACY_IMPROVEMENT:
            return ValidationResult(
                passed=False,
                errors=[f"Accuracy regression: {accuracy_diff:.2%}"],
                metrics=new_metrics
            )
        
        return ValidationResult(
            passed=True,
            metrics=new_metrics,
            comparison=ModelComparison(
                previous=current_metrics,
                new=new_metrics,
                improvement=accuracy_diff
            )
        )

class RollbackManager:
    def __init__(self):
        self.registry = ModelRegistry()
        self.production = ProductionDeployment()
    
    def rollback_to_version(self, version: str) -> RollbackResult:
        # Get previous version
        model = self.registry.load_version(version)
        
        # Deploy with zero-downtime swap
        self.production.deploy(model, traffic_percent=0)
        self.production.verify_health()
        self.production.set_traffic_percent(100)
        
        return RollbackResult(
            success=True,
            previous_version=self.registry.get_current_version(),
            rolled_to_version=version,
            duration_seconds=45
        )
    
    def auto_rollback_on_degradation(self):
        # Monitor production metrics
        # Trigger rollback if accuracy drops
        pass
```

**Feature Flag:** `launch:training:auto_rollback:enabled` (default: true)

---

#### ST-LAUNCH-014: Training E2E Integration Test
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** ML Team + Execution Team  
**Dependencies:** ST-LAUNCH-012, ST-LAUNCH-013  
**Files:**
- `tests/e2e/test_learning_loop.py` (create E2E test)
- `tests/e2e/test_model_lifecycle.py` (new)

**Acceptance Criteria:**
1. E2E test: Generate signal → execute → fill → match outcome → update ECE
2. E2E test: Trigger retraining → train model → validate → deploy → rollback
3. Both tests complete in <10min
4. Mock external dependencies (Bybit API)
5. Verify all components integrate correctly
6. 100% of critical path covered

**Feature Flag:** N/A (tests validate feature flags work)

---

### EP-LAUNCH-004: Launch Readiness & Validation (7 SP)

#### ST-LAUNCH-015: Load Testing & Performance Validation
**Points:** 3  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** All previous EP-LAUNCH stories  
**Files:**
- `tests/load/test_trading_performance.py` (new)
- `tests/load/locustfile.py` (new)
- `scripts/load_test.py` (new)

**Acceptance Criteria:**
1. Simulate 100x normal trading volume for 1 hour
2. Measure: latency (<100ms p99), throughput (>1000 signals/min), error rate (<0.1%)
3. Verify no memory leaks over 24h sustained load
4. Test circuit breaker under sustained failures
5. Grafana dashboards show all metrics within SLA
6. Generate load test report for stakeholders

**Technical Design:**
```python
class TradingLoadTest:
    DURATION_MINUTES = 60
    SIGNALS_PER_MINUTE = 1000
    
    def run(self):
        # Generate synthetic market data
        # Fire signals at target rate
        # Measure latency at each stage
        # Verify all SLAs met
        pass
```

**Feature Flag:** N/A (testing only)

---

#### ST-LAUNCH-016: Runbook Validation & Documentation
**Points:** 2  
**Status:** NOT_STARTED  
**Owner:** Execution Team  
**Dependencies:** All previous EP-LAUNCH stories  
**Files:**
- `docs/runbooks/launch_runbook.md` (new)
- `docs/runbooks/incident_response.md` (update)
- `docs/runbooks/rollback_procedures.md` (new)

**Acceptance Criteria:**
1. Complete runbook for launch day procedures
2. Incident response playbooks for P0/P1 scenarios
3. Rollback procedures tested and validated
4. All team members walk through runbooks
5. Sign-off from all stakeholders
6. Runbooks stored in version control

**Feature Flag:** N/A (documentation)

---

#### ST-LAUNCH-017: Final E2E Validation & Go/No-Go
**Points:** 2  
**Status:** NOT_STARTED  
**Owner:** Both Teams  
**Dependencies:** ST-LAUNCH-015, ST-LAUNCH-016  
**Files:**
- `tests/e2e/test_full_system.py` (new)
- `docs/launch/go_no_go_checklist.md` (new)

**Acceptance Criteria:**
1. Full system E2E test with all components
2. Validate all launch readiness checklist items
3. Go/No-Go decision meeting with stakeholders
4. Document decision and any launch blockers
5. If Go: proceed with launch procedures
6. If No-Go: document mitigation plan and reschedule

**Launch Readiness Checklist:**
- [ ] Bybit safety assertions tested (ST-LAUNCH-001 to 005)
- [ ] Signal-to-outcome pipeline 100% capture (ST-LAUNCH-006)
- [ ] Feature extractor 10+ features (ST-LAUNCH-007)
- [ ] ECE daily updates from outcomes (ST-LAUNCH-009)
- [ ] Auto-threshold with velocity limits (ST-LAUNCH-010)
- [ ] Model retraining automatic (ST-LAUNCH-011 to 014)
- [ ] 7+ days paper trading data (by Mar 7)
- [ ] All tests passing (unit, integration, E2E, load)
- [ ] Runbooks validated (ST-LAUNCH-016)
- [ ] Stakeholder sign-off

**Feature Flag:** N/A (validation)

---

## Technical Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ChiseAI Launch Architecture                          │
│                        (Target: March 7, 2026)                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ EP-LAUNCH-001: Safety & Infrastructure (Days 1-4)                           │
│ ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐         │
│ │  Circuit Breaker │───→│  Order Tracker   │───→│ Env Assertions   │         │
│ │   (ST-001)       │    │   (ST-002)       │    │   (ST-003)       │         │
│ └────────┬────────┘    └────────┬─────────┘    └────────┬─────────┘         │
│          │                      │                       │                    │
│          └──────────────────────┼───────────────────────┘                    │
│                                 ↓                                            │
│                    ┌─────────────────────┐                                   │
│                    │  Bybit Connector    │                                   │
│                    │  (src/data/exchange)│                                   │
│                    └──────────┬──────────┘                                   │
└───────────────────────────────┼──────────────────────────────────────────────┘
                                │
                                ↓ WebSocket / REST
┌───────────────────────────────┼──────────────────────────────────────────────┐
│                               │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                     Bybit Paper Trading API                              │ │
│  │                         (Testnet)                                        │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                               │                                              │
└───────────────────────────────┼──────────────────────────────────────────────┘
                                │
                                ↓ Fills, Executions
┌───────────────────────────────┼──────────────────────────────────────────────┐
│ EP-LAUNCH-002: Feedback Loop (Days 4-9)                                      │
│                               │                                              │
│  ┌────────────────────────────┼──────────────────────────────────────────┐   │
│  │                            ↓                                          │   │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │   │
│  │  │ Signal-Outcome   │   │  Feature         │   │ Prediction-      │   │   │
│  │  │ Pipeline         │←──│  Extractor       │   │ Outcome Matcher  │   │   │
│  │  │ (ST-006)         │   │ (ST-007)         │   │ (ST-008)         │   │   │
│  │  └────────┬─────────┘   └──────────────────┘   └────────┬─────────┘   │   │
│  │           │                                             │              │   │
│  │           ↓                                             ↓              │   │
│  │  ┌──────────────────┐                         ┌──────────────────┐     │   │
│  │  │ PostgreSQL       │←────────────────────────│  Signal Outcomes │     │   │
│  │  │ (signal_outcomes)│                         │  Table           │     │   │
│  │  └──────────────────┘                         └──────────────────┘     │   │
│  │                                                                         │   │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐     │   │
│  │  │ ECE Calculator   │←──│ Dynamic Threshold│   │ Feature Cache    │     │   │
│  │  │ (ST-009)         │   │ Adjuster (ST-010)│   │ (Redis)          │     │   │
│  │  └────────┬─────────┘   └──────────────────┘   └──────────────────┘     │   │
│  │           │                                                            │   │
│  └───────────┼────────────────────────────────────────────────────────────┘   │
│              │                                                                 │
│              ↓ ECE metrics, thresholds                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                         Grafana Dashboards                               │  │
│  │  - Signal capture rate                                                   │  │
│  │  - ECE trends                                                            │  │
│  │  - Threshold adjustments                                                 │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
                                │
                                ↓ Retraining trigger
┌───────────────────────────────┼──────────────────────────────────────────────┐
│ EP-LAUNCH-003: Model Ops (Days 9-12)                                         │
│                               │                                              │
│  ┌────────────────────────────┼──────────────────────────────────────────┐   │
│  │                            ↓                                          │   │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │   │
│  │  │ Retraining       │──→│ Training         │──→│ Model Registry   │   │   │
│  │  │ Trigger (ST-011) │   │ Pipeline (ST-012)│   │ (ST-013)         │   │   │
│  │  └──────────────────┘   └────────┬─────────┘   └────────┬─────────┘   │   │
│  │                                  │                      │              │   │
│  │                                  ↓                      ↓              │   │
│  │                         ┌──────────────────┐   ┌──────────────────┐   │   │
│  │                         │ Model Validator  │──→│ Rollback Manager │   │   │
│  │                         │ (ST-013)         │   │ (ST-013)         │   │   │
│  │                         └──────────────────┘   └──────────────────┘   │   │
│  │                                                                         │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │   │
│  │  │                     Model Store (S3/Local)                      │   │   │
│  │  │  - Versioned model artifacts                                    │   │   │
│  │  │  - Training configurations                                      │   │   │
│  │  │  - Validation reports                                           │   │   │
│  │  └──────────────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────┘
                                │
                                ↓ Production deployment
┌───────────────────────────────┼──────────────────────────────────────────────┐
│ EP-LAUNCH-004: Launch Readiness (Days 12-14)                                 │
│                               │                                              │
│  ┌────────────────────────────┼──────────────────────────────────────────┐   │
│  │                            ↓                                          │   │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │   │
│  │  │ Load Testing     │   │ Runbook          │   │ Go/No-Go         │   │   │
│  │  │ (ST-015)         │   │ Validation       │   │ Decision         │   │   │
│  │  └──────────────────┘   │ (ST-016)         │   │ (ST-017)         │   │   │
│  │                         └──────────────────┘   └──────────────────┘   │   │
│  │                                                                       │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │   │
│  │  │                    Feature Flag Control                          │ │   │
│  │  │  launch:trading:enabled         - Master kill switch            │ │   │
│  │  │  launch:safety:*                - Safety features               │ │   │
│  │  │  launch:feedback:*              - Feedback loop                 │ │   │
│  │  │  launch:training:*              - Model training                │ │   │
│  │  └──────────────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Integration with EP-NS-008 (Autonomous Control Plane)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Uses Scheduler from EP-NS-008 for: signal generation, ECE updates,       │
│    retraining checks, threshold adjustments                                   │
│  • Uses Kill-switch from EP-NS-008 for: emergency stop, circuit breaker      │
│  • Uses Health Monitoring from EP-NS-008 for: component health checks        │
│  • Uses Alerting from EP-NS-008 for: ECE alerts, training notifications      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Integration with EP-AUTO-GIT-001 (AI Swarm PR Pipeline)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  • All model training code changes go through PR pipeline                    │
│  • Model artifacts versioned with git-based tags                             │
│  • Automated testing on all PRs affecting ML pipeline                        │
│  • Staged rollout coordination with PR pipeline gates                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Feature Flag Design

### Flag Hierarchy

```
launch:trading:enabled                    # Master kill switch
├── launch:safety:enabled                 # All safety features
│   ├── launch:safety:circuit_breaker:enabled
│   ├── launch:safety:order_idempotency:enabled
│   └── launch:safety:assertions:enabled
├── launch:feedback:enabled               # All feedback features
│   ├── launch:feedback:signal_capture:enabled
│   ├── launch:feedback:feature_extraction:enabled
│   ├── launch:feedback:matcher:enabled
│   ├── launch:feedback:ece_updates:enabled
│   └── launch:feedback:auto_threshold:enabled
└── launch:training:enabled               # All training features
    ├── launch:training:pipeline:enabled
    ├── launch:training:auto_trigger:enabled
    └── launch:training:auto_rollback:enabled
```

### Flag Implementation

```python
# src/infrastructure/feature_flags.py

import redis
from typing import Optional

class LaunchFeatureFlags:
    PREFIX = "launch"
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    def is_enabled(self, flag: str) -> bool:
        """Check if a feature flag is enabled."""
        full_key = f"{self.PREFIX}:{flag}"
        value = self.redis.get(full_key)
        
        if value is None:
            # Default to True for safety features during launch
            if flag.startswith("safety:"):
                return True
            # Default to False for new ML features
            return False
        
        return value.decode() == "true"
    
    def set_flag(self, flag: str, enabled: bool, ttl: Optional[int] = None):
        """Set a feature flag value."""
        full_key = f"{self.PREFIX}:{flag}"
        value = "true" if enabled else "false"
        
        if ttl:
            self.redis.setex(full_key, ttl, value)
        else:
            self.redis.set(full_key, value)
    
    def get_all_flags(self) -> dict:
        """Get all launch flags and their values."""
        pattern = f"{self.PREFIX}:*"
        flags = {}
        
        for key in self.redis.scan_iter(match=pattern):
            flag = key.decode().replace(f"{self.PREFIX}:", "")
            value = self.redis.get(key).decode()
            flags[flag] = value == "true"
        
        return flags
    
    # Convenience methods
    def is_trading_enabled(self) -> bool:
        return self.is_enabled("trading:enabled")
    
    def is_safety_enabled(self) -> bool:
        return self.is_enabled("safety:enabled")
    
    def is_feedback_enabled(self) -> bool:
        return self.is_enabled("feedback:enabled")
    
    def is_training_enabled(self) -> bool:
        return self.is_enabled("training:enabled")
```

### Flag Usage Pattern

```python
# Example usage in components
from src.infrastructure.feature_flags import LaunchFeatureFlags

class BybitConnector:
    def __init__(self, redis_client):
        self.flags = LaunchFeatureFlags(redis_client)
        self.circuit_breaker = WebSocketCircuitBreaker()
    
    async def connect_websocket(self):
        # Check if circuit breaker feature is enabled
        if self.flags.is_enabled("safety:circuit_breaker:enabled"):
            if not self.circuit_breaker.can_execute():
                raise CircuitBreakerOpenError()
        
        # Proceed with connection
        ...
    
    async def place_order(self, order_request):
        # Check idempotency feature
        if self.flags.is_enabled("safety:order_idempotency:enabled"):
            if self.order_tracker.is_duplicate(order_request.id):
                raise DuplicateOrderError(order_request.id)
        
        # Proceed with order
        ...
```

### Emergency Procedures

```bash
# Full system shutdown (kill switch)
redis-cli SET launch:trading:enabled false

# Disable all ML feedback (revert to baseline)
redis-cli SET launch:feedback:enabled false

# Disable automatic retraining
redis-cli SET launch:training:auto_trigger:enabled false

# Check current flag status
redis-cli KEYS "launch:*" | xargs -I {} sh -c 'echo "{}: $(redis-cli GET {})"'

# Restore all safety features
redis-cli SET launch:safety:circuit_breaker:enabled true
redis-cli SET launch:safety:order_idempotency:enabled true
redis-cli SET launch:safety:assertions:enabled true
```

---

## Integration Points

### With EP-NS-008 (Autonomous Control Plane)

| EP-NS-008 Component | Integration Point | Usage in Launch |
|--------------------|--------------------|-----------------|
| Scheduler | Task registration | Signal generation, ECE daily updates, retraining checks |
| Kill-switch | Emergency stop | Circuit breaker integration, full trading halt |
| Health Monitor | Component health | All launch components report health status |
| Alert Manager | Notification | ECE alerts, training notifications, threshold alerts |
| State Manager | State persistence | Circuit breaker state, training job state |
| Config Manager | Configuration | Feature flags, thresholds, training hyperparameters |

### With EP-AUTO-GIT-001 (AI Swarm PR Pipeline)

| EP-AUTO-GIT-001 Component | Integration Point | Usage in Launch |
|---------------------------|--------------------|-----------------|
| PR Pipeline | Code review | All ML training code changes |
| Test Automation | CI/CD | Automated testing on training pipeline changes |
| Model Registry | Versioning | Git-based tags for model versions |
| Staged Rollout | Deployment | Model A/B testing, gradual rollout |
| Audit Log | Change tracking | All model training and deployment events |

---

## Rollback Strategy Summary

| Epic | Rollback Strategy | Recovery Time |
|------|-------------------|---------------|
| EP-LAUNCH-001 | Redis flags disable safety features | <30s |
| EP-LAUNCH-002 | Set `launch:feedback:mode` to `disabled` | <30s |
| EP-LAUNCH-003 | Model registry rollback to previous version | <60s |
| EP-LAUNCH-004 | Kill-switch + git checkout | <5min |

### Rollback Decision Tree

```
Issue Detected
      │
      ├── Is it a safety/circuit breaker issue?
      │   └── YES → Set launch:safety:enabled false
      │       └─→ Still failing? → Kill-switch
      │
      ├── Is it a prediction/feedback issue?
      │   └── YES → Set launch:feedback:enabled false
      │       └─→ Still failing? → Kill-switch
      │
      ├── Is it a model accuracy issue?
      │   └── YES → Rollback to previous model version
      │       └─→ Still failing? → Disable auto-training
      │           └─→ Still failing? → Kill-switch
      │
      └── Unknown/Other
          └── Kill-switch + investigate

Kill-switch Procedure:
1. redis-cli SET launch:trading:enabled false
2. Verify all orders stopped
3. git checkout <last_known_good_tag>
4. docker-compose up -d
5. Verify health checks pass
6. Re-enable gradually with monitoring
```

---

## Story Summary Table

| Story | Epic | Points | Owner | Dependencies | Target Day |
|-------|------|--------|-------|--------------|------------|
| ST-LAUNCH-001 | EP-LAUNCH-001 | 3 | Execution | None | Day 1-2 |
| ST-LAUNCH-002 | EP-LAUNCH-001 | 3 | Execution | None | Day 1-2 |
| ST-LAUNCH-003 | EP-LAUNCH-001 | 2 | Execution | None | Day 1-2 |
| ST-LAUNCH-004 | EP-LAUNCH-001 | 2 | Execution | Optional ST-001 | Day 3-4 |
| ST-LAUNCH-005 | EP-LAUNCH-001 | 4 | Execution | ST-001,002,003 | Day 4 |
| ST-LAUNCH-006 | EP-LAUNCH-002 | 5 | ML | None | Day 4-6 |
| ST-LAUNCH-007 | EP-LAUNCH-002 | 4 | ML | ST-006 | Day 5-7 |
| ST-LAUNCH-008 | EP-LAUNCH-002 | 3 | ML | ST-006 | Day 6-7 |
| ST-LAUNCH-009 | EP-LAUNCH-002 | 3 | ML | ST-008 | Day 7-8 |
| ST-LAUNCH-010 | EP-LAUNCH-002 | 3 | ML | ST-009 | Day 8-9 |
| ST-LAUNCH-011 | EP-LAUNCH-003 | 5 | ML | ST-009,010 | Day 9-10 |
| ST-LAUNCH-012 | EP-LAUNCH-003 | 4 | ML | ST-011 | Day 10-11 |
| ST-LAUNCH-013 | EP-LAUNCH-003 | 3 | ML | ST-012 | Day 11-12 |
| ST-LAUNCH-014 | EP-LAUNCH-003 | 3 | Both | ST-012,013 | Day 12 |
| ST-LAUNCH-015 | EP-LAUNCH-004 | 3 | Execution | All | Day 12-13 |
| ST-LAUNCH-016 | EP-LAUNCH-004 | 2 | Execution | All | Day 12-13 |
| ST-LAUNCH-017 | EP-LAUNCH-004 | 2 | Both | ST-015,016 | Day 14 |

**Total:** 20 stories, 54 SP

**Team Allocation:**
- Execution Team: ST-001, 002, 003, 004, 005, 015, 016, 017 (18 SP)
- ML Team: ST-006, 007, 008, 009, 010, 011, 012, 013 (30 SP)
- Both Teams: ST-014, 017 partial (6 SP)

---

## Risk Mitigation

| Risk | Mitigation | Owner |
|------|------------|-------|
| Signal-to-outcome pipeline fails | Start with CSV export, add DB in parallel | ML Team |
| Feature extractor delays | Use existing cache, ship with 5 core features | ML Team |
| Model retraining slow | Use incremental updates, weekly batch default | ML Team |
| Bybit API issues | Circuit breaker + paper trading mode | Execution Team |
| Database performance | Proper indexing, Redis caching | ML Team |
| Integration failures | E2E tests early (ST-005, ST-014) | Both Teams |
| Team capacity constraints | Parallel work streams, daily standups | Project Lead |

---

## Next Steps

1. **Immediate (Today):** 
   - Review and approve this architecture plan
   - Assign story owners
   - Set up feature flag keys in Redis

2. **Day 1 (Feb 21):**
   - Begin ST-LAUNCH-001, 002, 003 in parallel
   - Daily standup to track progress

3. **Ongoing:**
   - Update `docs/bmm-workflow-status.yaml` with story assignments
   - Track progress in validation registry
   - Log all learnings in memory system

---

*Document Version:* 1.0  
*Created:* 2026-02-21  
*Author:* SENIORDEV (Party Mode)  
*Review:* Requires approval from Project Lead before execution
