---
title: ML Operations Runbook
category: ml-operations
severity: high
estimated_time_to_resolve: 30-120 minutes
last_updated: 2026-02-22
maintainers: ml-team, data-team
story_id: ST-LAUNCH-021
executable: true
steps:
  - name: "Check model health"
    command: "curl -s http://localhost:8001/api/v1/ml/model/health | jq -r '.status'"
    verify: "healthy"
  - name: "Verify model version"
    command: "curl -s http://localhost:8001/api/v1/ml/model/current | jq -r '.version'"
  - name: "Check calibration status"
    command: "curl -s http://localhost:8001/api/v1/ml/calibration/status | jq -r '.ece'"
  - name: "Validate shadow mode results"
    command: "curl -s http://localhost:8001/api/v1/ml/shadow/status | jq -r '.ready_for_promotion'"
  - name: "Check training pipeline"
    command: "curl -s http://localhost:8001/api/v1/ml/training/status | jq -r '.status'"
---

# ML Operations Runbook

> **Story:** ST-LAUNCH-021  
> **Last Updated:** 2026-02-22  
> **Owner:** ML Platform Team  
> **Shadow Mode Duration:** 24 hours minimum before promotion

---

## Overview

This runbook covers all operational procedures for the ML components of the ChiseAI platform, including model retraining, validation gates, rollback procedures, shadow mode operations, A/B testing, and daily ECE (Expected Calibration Error) updates.

---

## 1. Model Retraining Trigger Conditions

### 1.1 Automatic Retraining Triggers

**Performance-Based Triggers:**

| Metric | Warning | Critical | Auto-Retrain |
|--------|---------|----------|--------------|
| Accuracy degradation | < 85% | < 80% | Yes (critical) |
| Precision drop | < 75% | < 70% | Yes (critical) |
| Recall drop | < 75% | < 70% | Yes (critical) |
| F1 score decline | < 78% | < 73% | Yes (critical) |
| ECE increase | > 0.15 | > 0.20 | Yes (critical) |
| Prediction drift | > 0.10 | > 0.15 | Yes (critical) |

**Data-Based Triggers:**

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Training data age | > 30 days | Schedule retrain |
| New labeled data available | > 10k samples | Consider retrain |
| Feature distribution shift | > 0.05 KL divergence | Retrain required |
| Concept drift detected | Drift score > 0.3 | Immediate retrain |
| Data quality issues | > 5% invalid | Fix data, then retrain |

**Operational Triggers:**

| Condition | Action |
|-----------|--------|
| Model not trained for 7 days | Schedule maintenance retrain |
| Hyperparameter update available | Manual retrain with new params |
| New feature engineering | Retrain with new features |
| Algorithm improvement | Schedule upgrade retrain |

### 1.2 Manual Retraining Decision

**When to Manually Trigger:**

```bash
# Check if retraining is recommended
curl -s http://localhost:8001/api/v1/ml/retraining/recommended | jq '.'

# Response:
# {
#   "recommended": true,
#   "reasons": ["accuracy_degradation", "data_age"],
#   "current_metrics": { "accuracy": 0.82, "ece": 0.18 },
#   "thresholds": { "accuracy": 0.85, "ece": 0.15 }
# }
```

**Decision Matrix:**

| Scenario | Auto-Trigger | Manual Review | Approval Required |
|----------|--------------|---------------|-------------------|
| Critical performance drop | Yes | After | No (emergency) |
| Warning performance drop | No | Yes | ML Lead |
| Scheduled maintenance | Yes | Before | No (planned) |
| Feature update | No | Yes | Product + ML Lead |
| Algorithm change | No | Yes | CTO |

### 1.3 Retraining Trigger API

```bash
# Trigger manual retraining
curl -X POST http://localhost:8001/api/v1/ml/training/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ML_TOKEN" \
  -d '{
    "reason": "manual_performance_review",
    "triggered_by": "<operator_id>",
    "priority": "high",
    "use_latest_data": true,
    "hyperparameters": {
      "learning_rate": 0.001,
      "epochs": 100
    }
  }'

# Response:
# {
#   "training_id": "train-20260222-001",
#   "status": "queued",
#   "estimated_duration": "4 hours",
#   "queue_position": 1
# }
```

---

## 2. Training Pipeline Execution

### 2.1 Pre-Training Checklist

**Before Starting Training:**

- [ ] Data validation passed (see data validation runbook)
- [ ] Feature store is synchronized
- [ ] Training environment resources available
- [ ] Previous model checkpoint backed up
- [ ] Experiment tracking configured
- [ ] Training config version controlled

**Verify Data Readiness:**
```bash
# Check data quality
curl -s http://localhost:8001/api/v1/ml/data/quality | jq '.'

# Expected:
# {
#   "status": "valid",
#   "samples": 100000,
#   "features": 50,
#   "missing_rate": 0.02,
#   "validation_passed": true
# }
```

### 2.2 Step-by-Step Training Procedure

**Step 1: Initialize Training Job**
```bash
# Start training pipeline
curl -X POST http://localhost:8001/api/v1/ml/training/start \
  -H "Content-Type: application/json" \
  -d '{
    "training_id": "train-20260222-001",
    "model_type": "xgboost",
    "dataset_version": "v2.3.1",
    "experiment_name": "accuracy_improvement_q1",
    "tracking_enabled": true
  }'
```

**Step 2: Monitor Training Progress**
```bash
# Check training status every 15 minutes
watch -n 900 'curl -s http://localhost:8001/api/v1/ml/training/train-20260222-001/status | jq '.'

# Key metrics to monitor:
# - loss curves (should be decreasing)
# - validation metrics (should be improving)
# - training time vs. estimated
# - resource utilization (GPU/CPU/Memory)
```

**Step 3: Validation During Training**
```bash
# Mid-training validation checkpoint
curl -s http://localhost:8001/api/v1/ml/training/train-20260222-001/checkpoint/latest | jq '.'

# If metrics degrading, consider early stopping
```

**Step 4: Training Completion**
```bash
# Get final training results
curl -s http://localhost:8001/api/v1/ml/training/train-20260222-001/results | jq '.'

# Response includes:
# - Final metrics (accuracy, precision, recall, F1, ECE)
# - Model artifact location
# - Training duration
# - Resource usage
```

### 2.3 Training Pipeline Stages

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Data Prep  │───→│   Training   │───→│  Validation  │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
  [validate]          [monitor]           [metrics]
  [transform]         [checkpoint]        [gates]
  [split]             [early_stop]        [artifacts]
```

**Stage Details:**

| Stage | Duration | Checkpoints | Failure Action |
|-------|----------|-------------|----------------|
| Data Prep | 10-30 min | Data validation report | Abort, alert data team |
| Training | 2-8 hours | Every epoch | Retry with reduced data |
| Validation | 15-30 min | Full metrics | Mark model as failed |
| Calibration | 5-10 min | ECE metrics | Use default calibration |
| Registration | 2-5 min | Model registry entry | Manual intervention |

### 2.4 Training Failure Recovery

**Common Failures and Recovery:**

| Failure Type | Symptom | Recovery Action |
|--------------|---------|-----------------|
| OOM Error | CUDA out of memory | Reduce batch size, retry |
| Data Error | Invalid samples | Fix data, restart from checkpoint |
| Divergence | Loss increasing | Lower learning rate, restart |
| Timeout | Training > 12 hours | Check resources, may need scale-up |
| Validation Fail | Metrics below baseline | Review features, retrain |

**Recovery Script:**
```bash
# Automatic retry with adjusted parameters
./scripts/ml/retry_training.sh \
  --training-id="train-20260222-001" \
  --failure-type="oom" \
  --adjust-params="batch_size=half"
```

---

## 3. Validation Gates

### 3.1 Pre-Deployment Validation Gates

**All Gates Must Pass Before Deployment:**

| Gate # | Check | Threshold | Enforcement |
|--------|-------|-----------|-------------|
| 1 | Accuracy ≥ baseline | ≥ current - 2% | Hard block |
| 2 | Precision ≥ threshold | ≥ 75% | Hard block |
| 3 | Recall ≥ threshold | ≥ 75% | Hard block |
| 4 | F1 score acceptable | ≥ 78% | Hard block |
| 5 | ECE (calibration) | ≤ 0.15 | Hard block |
| 6 | Inference latency | ≤ 100ms p99 | Hard block |
| 7 | Model size | ≤ 500MB | Soft warning |
| 8 | Feature coverage | 100% of required | Hard block |
| 9 | Schema compatibility | Pass validation | Hard block |
| 10 | Bias metrics | Within thresholds | Soft warning |

**Run All Gates:**
```bash
# Execute full validation suite
curl -X POST http://localhost:8001/api/v1/ml/validation/run \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "model-20260222-001",
    "gates": "all",
    "baseline_model": "current-production"
  }'

# Check results
curl -s http://localhost:8001/api/v1/ml/validation/model-20260222-001/results | jq '.'
```

### 3.2 Validation Gate Details

**Gate 1-4: Performance Metrics**
```bash
# Verify performance against baseline
curl -s http://localhost:8001/api/v1/ml/validation/performance | jq '{
  "accuracy": .accuracy,
  "precision": .precision,
  "recall": .recall,
  "f1": .f1_score,
  "passed": .all_passed
}'
```

**Gate 5: Calibration (ECE)**
```bash
# Check Expected Calibration Error
curl -s http://localhost:8001/api/v1/ml/calibration/check | jq '{
  "ece": .ece,
  "max_calibration_error": .mce,
  "bins": .bin_accuracies,
  "passed": .ece <= 0.15
}'
```

**Gate 6: Latency**
```bash
# Load test inference latency
curl -X POST http://localhost:8001/api/v1/ml/validation/latency-test \
  -d '{"requests": 1000, "concurrency": 10}'

# Expected p99 < 100ms
```

### 3.3 Gate Failure Procedures

**Hard Gate Failure (Blocks Deployment):**

1. **Stop deployment immediately**
2. **Notify ML team lead**
3. **Analyze failure cause**
   ```bash
   # Get detailed failure report
   curl -s http://localhost:8001/api/v1/ml/validation/failure-analysis | jq '.'
   ```
4. **Options:**
   - Fix issues and retrain
   - Adjust thresholds (requires approval)
   - Proceed with manual override (requires CTO approval)

**Soft Gate Failure (Warning Only):**

1. **Document the issue**
2. **Create remediation ticket**
3. **Can proceed with acknowledgment**
   ```bash
   # Acknowledge warning and proceed
   curl -X POST http://localhost:8001/api/v1/ml/validation/acknowledge \
     -d '{"warning": "model_size", "justification": "acceptable_for_feature"}'
   ```

---

## 4. Model Rollback on Degradation

### 4.1 Automatic Rollback Triggers

**Auto-Rollback Conditions:**

| Condition | Threshold | Time Window | Action |
|-----------|-----------|-------------|--------|
| Accuracy drop | > 5% vs baseline | 1 hour | Auto-rollback |
| Error rate spike | > 10x normal | 15 minutes | Auto-rollback |
| Latency spike | > 5x baseline | 30 minutes | Auto-rollback |
| Prediction anomaly | > 20% outliers | 1 hour | Alert + review |
| ECE degradation | > 0.05 increase | 1 hour | Auto-rollback |

### 4.2 Manual Rollback Procedure

**When to Manually Rollback:**
- Auto-rollback didn't trigger but degradation observed
- Business decision to revert
- Model behaving unexpectedly in specific scenarios
- New model has critical bug discovered post-deployment

**Rollback Steps:**

```bash
# Step 1: Identify rollback target
CURRENT=$(curl -s http://localhost:8001/api/v1/ml/model/current | jq -r '.version')
PREVIOUS=$(curl -s http://localhost:8001/api/v1/ml/model/previous | jq -r '.version')
echo "Rolling back from $CURRENT to $PREVIOUS"

# Step 2: Initiate rollback
curl -X POST http://localhost:8001/api/v1/ml/model/rollback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ML_TOKEN" \
  -d '{
    "from_version": "'$CURRENT'",
    "to_version": "'$PREVIOUS'",
    "reason": "performance_degradation",
    "operator_id": "<operator_id>",
    "skip_shadow": true
  }'

# Step 3: Verify rollback
curl -s http://localhost:8001/api/v1/ml/model/current | jq -r '.version'
# Expected: Previous version

# Step 4: Validate rolled-back model
curl -s http://localhost:8001/api/v1/ml/model/health | jq -r '.status'
# Expected: "healthy"
```

### 4.3 Rollback Verification

**Post-Rollback Checks:**

```bash
# Verify model is serving predictions
curl -X POST http://localhost:8001/api/v1/ml/predict \
  -H "Content-Type: application/json" \
  -d '{"features": [...], "validate": true}'

# Check performance metrics returning to baseline
curl -s http://localhost:8001/api/v1/ml/metrics/realtime | jq '{
  "accuracy": .accuracy,
  "latency_p99": .latency_p99,
  "error_rate": .error_rate
}'

# Verify no degradation alerts
curl -s http://localhost:8001/api/v1/alerts/active | jq '.[] | select(.source == "ml")'
```

---

## 5. Shadow Mode Operation

### 5.1 Shadow Mode Overview

**What is Shadow Mode:**
- New model runs in parallel with production model
- Receives same inputs, makes predictions
- Predictions are logged but NOT acted upon
- Compare shadow vs production performance
- Minimum 24-hour shadow period before promotion

### 5.2 Shadow Mode Deployment

**Enable Shadow Mode:**

```bash
# Deploy new model to shadow mode
curl -X POST http://localhost:8001/api/v1/ml/shadow/enable \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ML_TOKEN" \
  -d '{
    "model_id": "model-20260222-001",
    "traffic_percentage": 100,
    "duration_hours": 24,
    "comparison_metrics": ["accuracy", "precision", "recall", "f1", "ece"]
  }'

# Response:
# {
#   "shadow_id": "shadow-20260222-001",
#   "status": "active",
#   "started_at": "2026-02-22T12:00:00Z",
#   "scheduled_end": "2026-02-23T12:00:00Z"
# }
```

### 5.3 Shadow Mode Monitoring

**Check Shadow Performance:**

```bash
# Get shadow comparison report
curl -s http://localhost:8001/api/v1/ml/shadow/shadow-20260222-001/comparison | jq '.'

# Response includes:
# - Side-by-side metrics comparison
# - Statistical significance tests
# - Recommendation (promote / reject / extend)
```

**Key Metrics to Monitor:**

| Metric | Shadow | Production | Delta | Action if Delta > Threshold |
|--------|--------|------------|-------|----------------------------|
| Accuracy | 87% | 85% | +2% | Good - consider promotion |
| Latency | 45ms | 50ms | -10% | Good |
| Error Rate | 0.1% | 0.2% | -50% | Good |
| ECE | 0.12 | 0.15 | -20% | Good |

### 5.4 Shadow Mode Completion

**After 24 Hours:**

```bash
# Check if ready for promotion
curl -s http://localhost:8001/api/v1/ml/shadow/shadow-20260222-001/status | jq '{
  "ready_for_promotion": .ready_for_promotion,
  "recommendation": .recommendation,
  "hours_remaining": .hours_remaining
}'

# If ready, promote to production
curl -X POST http://localhost:8001/api/v1/ml/shadow/promote \
  -H "Content-Type: application/json" \
  -d '{
    "shadow_id": "shadow-20260222-001",
    "operator_id": "<operator_id>",
    "gradual_rollout": true,
    "rollout_percentage": 10
  }'

# Gradually increase: 10% → 25% → 50% → 100%
```

### 5.5 Shadow Mode Early Termination

**If Shadow Model Fails:**

```bash
# Disable shadow mode early
curl -X POST http://localhost:8001/api/v1/ml/shadow/disable \
  -H "Content-Type: application/json" \
  -d '{
    "shadow_id": "shadow-20260222-001",
    "reason": "performance_below_threshold",
    "operator_id": "<operator_id>"
  }'

# Review failure and retrain
./scripts/ml/analyze_shadow_failure.sh --shadow-id="shadow-20260222-001"
```

---

## 6. A/B Testing Framework

### 6.1 A/B Test Setup

**When to Use A/B Testing:**
- Comparing two different model architectures
- Testing impact of feature changes
- Measuring business metric impact
- Validating model improvements

**Create A/B Test:**

```bash
# Initialize A/B test
curl -X POST http://localhost:8001/api/v1/ml/ab-test/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ML_TOKEN" \
  -d '{
    "test_name": "feature_v2_comparison",
    "model_a": "model-current",
    "model_b": "model-feature-v2",
    "split_ratio": 0.5,
    "traffic_percentage": 20,
    "duration_days": 7,
    "primary_metric": "accuracy",
    "secondary_metrics": ["precision", "recall", "revenue"],
    "minimum_sample_size": 10000
  }'

# Response:
# {
#   "test_id": "ab-20260222-001",
#   "status": "running",
#   "model_a_traffic": "10%",
#   "model_b_traffic": "10%",
#   "control_traffic": "80%"
# }
```

### 6.2 A/B Test Monitoring

**Check Test Progress:**

```bash
# Get current test results
curl -s http://localhost:8001/api/v1/ml/ab-test/ab-20260222-001/results | jq '.'

# Key fields:
# - sample_sizes for each variant
# - metric comparisons
# - statistical significance (p-values)
# - confidence intervals
# - current winner (if significant)
```

### 6.3 A/B Test Completion

**End Test and Apply Winner:**

```bash
# Get final recommendation
curl -s http://localhost:8001/api/v1/ml/ab-test/ab-20260222-001/recommendation | jq '.'

# Apply winning model
curl -X POST http://localhost:8001/api/v1/ml/ab-test/ab-20260222-001/apply-winner \
  -H "Content-Type: application/json" \
  -d '{
    "operator_id": "<operator_id>",
    "gradual_rollout": true
  }'

# Archive test
curl -X POST http://localhost:8001/api/v1/ml/ab-test/ab-20260222-001/archive
```

---

## 7. Daily ECE Update Procedures

### 7.1 ECE (Expected Calibration Error) Overview

**What is ECE:**
- Measures how well model confidence aligns with actual accuracy
- Lower ECE = better calibrated model
- Target: ECE ≤ 0.15
- Critical threshold: ECE > 0.20

**ECE Calculation:**
```
ECE = Σ (bin_size * |accuracy_in_bin - confidence_in_bin|)
```

### 7.2 Daily ECE Check

**Morning ECE Verification (9:00 AM):**

```bash
# Get current ECE
curl -s http://localhost:8001/api/v1/ml/calibration/ece | jq '{
  "current_ece": .ece,
  "target": 0.15,
  "status": .status,
  "trend": .trend_7d
}'

# Expected: status == "good" or "acceptable"
# Trend should be stable or improving
```

**ECE Trend Analysis:**

```bash
# Check 7-day ECE trend
curl -s http://localhost:8001/api/v1/ml/calibration/trend?days=7 | jq '.'

# Alert if:
# - ECE increasing > 0.02 over 7 days
# - ECE exceeds 0.15
# - ECE trend is "degrading"
```

### 7.3 ECE Recalibration

**When ECE Exceeds Threshold:**

```bash
# Step 1: Verify ECE calculation
curl -s http://localhost:8001/api/v1/ml/calibration/verify | jq '.'

# Step 2: Run recalibration
curl -X POST http://localhost:8001/api/v1/ml/calibration/recalibrate \
  -H "Content-Type: application/json" \
  -d '{
    "method": "temperature_scaling",
    "validation_split": 0.2,
    "operator_id": "<operator_id>"
  }'

# Step 3: Verify improved ECE
curl -s http://localhost:8001/api/v1/ml/calibration/ece | jq '.ece'
# Expected: < previous ECE
```

**Recalibration Methods:**

| Method | When to Use | Complexity | Effectiveness |
|--------|-------------|------------|---------------|
| Temperature Scaling | General miscalibration | Low | Good |
| Platt Scaling | Binary classification | Medium | Very Good |
| Isotonic Regression | Complex miscalibration | High | Excellent |
| Beta Calibration | Probabilities near 0/1 | Medium | Good |

### 7.4 ECE Alert Response

**ECE Alert Levels:**

| ECE Value | Level | Response Time | Action |
|-----------|-------|---------------|--------|
| 0.10 - 0.15 | Good | N/A | Monitor |
| 0.15 - 0.18 | Warning | 24 hours | Schedule recalibration |
| 0.18 - 0.20 | Elevated | 4 hours | Immediate recalibration |
| > 0.20 | Critical | 1 hour | Recalibrate + consider rollback |

**Critical ECE Response:**

```bash
# If ECE > 0.20:
# 1. Trigger recalibration immediately
curl -X POST http://localhost:8001/api/v1/ml/calibration/recalibrate \
  -d '{"priority": "critical", "operator_id": "<id>"}'

# 2. If recalibration fails, consider model rollback
# See Section 4: Model Rollback

# 3. Log incident
./scripts/ops/log_incident.sh \
  --severity="high" \
  --category="ml-ece-critical" \
  --story="ST-LAUNCH-021"
```

---

## 8. ML Model Registry

### 8.1 Model Version Management

**Model Naming Convention:**
```
{model-type}-{YYYYMMDD}-{sequence}
Example: xgboost-20260222-001
```

**Model Registry Operations:**

```bash
# List all models
curl -s http://localhost:8001/api/v1/ml/registry/models | jq '.'

# Get model details
curl -s http://localhost:8001/api/v1/ml/registry/model-xgboost-20260222-001 | jq '.'

# Tag model as production
curl -X POST http://localhost:8001/api/v1/ml/registry/tag \
  -d '{
    "model_id": "xgboost-20260222-001",
    "tag": "production",
    "operator_id": "<operator_id>"
  }'

# Archive old model
curl -X POST http://localhost:8001/api/v1/ml/registry/archive \
  -d '{"model_id": "xgboost-20260215-003"}'
```

### 8.2 Model Artifact Management

**Artifact Storage:**
- Models: `s3://chiseai-models/`
- Metadata: PostgreSQL model_registry table
- Metrics: InfluxDB

**Artifact Cleanup:**

```bash
# List unused artifacts
curl -s http://localhost:8001/api/v1/ml/registry/unused | jq '.'

# Clean up old artifacts (keeps last 10 versions)
./scripts/ml/cleanup_artifacts.sh --keep=10 --dry-run
./scripts/ml/cleanup_artifacts.sh --keep=10 --confirm
```

---

## 9. Monitoring and Alerting

### 9.1 ML-Specific Metrics

| Metric | Source | Threshold | Alert |
|--------|--------|-----------|-------|
| Model accuracy | Real-time evaluation | < 85% | P1 |
| Inference latency | API metrics | p99 > 100ms | P2 |
| Prediction drift | Drift detection | > 0.10 | P1 |
| ECE | Calibration service | > 0.15 | P2 |
| Training job failures | Pipeline logs | Any failure | P2 |
| Shadow mode delta | Comparison service | < -5% | P1 |

### 9.2 ML Dashboards

- **Model Performance:** http://localhost:3001/d/chiseai/ml-performance
- **Model Drift:** http://localhost:3001/d/chiseai/ml-drift
- **Calibration:** http://localhost:3001/d/chiseai/ml-calibration
- **Training Jobs:** http://localhost:3001/d/chiseai/ml-training
- **Shadow Mode:** http://localhost:3001/d/chiseai/ml-shadow

### 9.3 ML Alert Routing

| Alert Type | Primary | Escalation |
|------------|---------|------------|
| Model degradation | ML On-call | ML Lead (30 min) |
| Training failure | ML Platform | ML Lead (1 hour) |
| Drift detection | Data Team | ML Lead (2 hours) |
| Calibration issues | ML Engineer | ML Lead (4 hours) |
| Shadow mode failure | ML Engineer | ML Lead (30 min) |

---

## 10. Related Runbooks

- [Model Drift](model-drift.md) - Handling model drift detection
- [Data Gaps](data-gaps.md) - Data quality and availability
- [Launch Safety](launch_runbook.md) - Safety procedures
- [Incident Response](incident_response.md) - General incident handling

---

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-22 | ML Platform Team | Initial creation for ST-LAUNCH-021 |
