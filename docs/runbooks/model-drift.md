---
title: Model Drift Runbook
category: alerting
severity: warning
estimated_time_to_resolve: 1-4 hours
last_updated: 2026-02-11
maintainers: ml-team
---

# Model Drift Runbook

## Problem Description

Machine learning models (signal generation, confidence calibration) are experiencing performance degradation due to:
- Market regime changes
- Data distribution shifts
- Concept drift in predictive features
- Feature engineering pipeline issues

Model drift can result in:
- Degraded signal accuracy
- Poorly calibrated confidence scores
- Increased prediction errors
- Suboptimal trading decisions

## Symptoms and Indicators

### Primary Symptoms
1. **ECE (Expected Calibration Error) Degradation**
   - ECE increases above 0.10 threshold
   - Confidence scores no longer correlate with accuracy
   - High-confidence predictions failing more often

2. **Prediction Accuracy Decline**
   - Signal win rate dropping below baseline
   - Sharpe ratio deteriorating
   - Increased false signals

3. **Distribution Shift Detected**
   - Feature distributions differ from training data
   - Feature importance changes
   - Input data outside expected ranges

### Secondary Indicators
- Increased order rejections (bad signals)
- Rising drawdown trends
- Strategy performance divergence from backtests
- Anomaly detection alerts on feature values

## Root Cause Analysis

### Common Causes (in order of frequency)

1. **Market Regime Changes**
   - Transition from trending to ranging market
   - Increased volatility regime
   - Liquidity changes
   - Correlations breaking down

2. **Data Quality Issues**
   - Feature pipeline failures
   - Missing or corrupted data
   - Data source changes
   - Look-ahead bias introduction

3. **Feature Drift**
   - Feature engineering logic changes
   - New features with different distributions
   - Feature importance shifts
   - Feature relevance degradation

4. **Model Staleness**
   - Model not retrained for extended period
   - Training data no longer representative
   - Hyperparameters need adjustment
   - Ensemble weights need rebalancing

5. **External Factor Changes**
   - Exchange fee structure changes
   - Market microstructure evolution
   - Regulatory changes
   - News sentiment shifts

## Step-by-Step Resolution Procedures

### Phase 1: Detection and Assessment (15-30 minutes)

1. **Check Model Performance Metrics**
   ```bash
   # Query ECE metrics from InfluxDB
   influx query 'from(bucket:"chiseai")
     |> range(start: -24h)
     |> filter(fn:(r) => r._measurement == "model_metrics")
     |> filter(fn:(r) => r._field == "ece")
     |> last()'

   # Query accuracy metrics
   influx query 'from(bucket:"chiseai")
     |> range(start: -24h)
     |> filter(fn:(r) => r._measurement == "model_metrics")
     |> filter(fn:(r) => r._field == "accuracy")
     |> last()'
   ```

2. **Check Grafana Drift Detection Dashboard**
   - Navigate to Model Performance Dashboard
   - Review ECE trend over time
   - Compare recent vs. historical accuracy
   - Check feature distribution plots

3. **Analyze Signal Performance**
   ```bash
   # Query recent signal outcomes
   curl -s "http://localhost:8000/api/v1/signals?days=7" | jq '.[] | {
     signal_id: .id,
     confidence: .confidence,
     outcome: .outcome,
     accuracy_bucket: .accuracy_bucket
   }'

   # Calculate calibration breakdown
   ./scripts/ml/analyze_calibration.py --days 7
   ```

### Phase 2: Investigation (30-60 minutes)

1. **Identify Drift Characteristics**
   ```bash
   # Run drift detection analysis
   python3 scripts/ml/drift_detection.py \
     --reference_window 30d \
     --current_window 7d \
     --output drift_report.json

   # Check drift metrics
   cat drift_report.json | jq '.drift_scores'
   ```

2. **Analyze Feature Distributions**
   ```bash
   # Compare feature distributions
   python3 scripts/ml/compare_distributions.py \
     --features rsi,macd,bollinger \
     --reference_period 30d \
     --current_period 7d

   # Generate distribution plots
   python3 scripts/ml/plot_distributions.py --output /tmp/distributions/
   ```

3. **Review Market Regime**
   ```bash
   # Check current regime indicators
   python3 scripts/ml/analyze_regime.py --days 30

   # Identify regime changes
   python3 scripts/ml/detect_regime_changes.py --days 30
   ```

4. **Examine Data Pipeline**
   ```bash
   # Check feature generation pipeline
   docker logs chiseai-feature-engine --since 1h | tail -50

   # Verify feature data quality
   ./scripts/ml/validate_features.py --days 7
   ```

### Phase 3: Mitigation Strategies (1-2 hours)

#### Option A: Rapid Retraining (1-2 hours)

1. **Prepare Training Data**
   ```bash
   # Generate training dataset with recent data
   python3 scripts/ml/prepare_training_data.py \
     --start_date 2026-01-01 \
     --end_date 2026-02-11 \
     --output training_data.parquet
   ```

2. **Retrain Models**
   ```bash
   # Retrain all signal models
   python3 scripts/ml/retrain_models.py \
     --data training_data.parquet \
     --models signal,confidence \
     --output /tmp/model_output/

   # Evaluate on validation set
   python3 scripts/ml/evaluate_models.py \
     --model_dir /tmp/model_output/ \
     --val_data validation_data.parquet
   ```

3. **Deploy New Models**
   ```bash
   # Deploy to shadow mode first
   ./scripts/ml/deploy_models.py \
     --model_dir /tmp/model_output/ \
     --mode shadow \
     --duration 24h

   # Validate shadow performance
   python3 scripts/ml/validate_shadow.py --duration 24h

   # Promote to production
   ./scripts/ml/deploy_models.py \
     --model_dir /tmp/model_output/ \
     --mode production
   ```

#### Option B: Feature Engineering Update (2-4 hours)

1. **Identify Problematic Features**
   ```bash
   # Analyze feature importance drift
   python3 scripts/ml/feature_importance_drift.py \
     --reference_file features_reference.parquet \
     --current_file features_current.parquet

   # Find features with highest drift
   cat drift_report.json | jq '.feature_drift | to_entries | sort_by(.value) | reverse | .[:5]'
   ```

2. **Update Feature Engineering**
   ```bash
   # Modify feature engineering logic
   sed -i 's/.*rsi_period.*/RSI_PERIOD = 14  # Adjusted for current regime/' \
     src/features/technical_indicators.py

   # Rebuild feature pipeline
   python3 -m pytest tests/features/ -v
   ```

3. **Redeploy Feature Pipeline**
   ```bash
   # Build and deploy updated feature engineering
   docker build -t chiseai-feature-engine:v2.0 .
   docker tag chiseai-feature-engine:v2.0 chiseai-feature-engine:latest
   docker push chiseai-feature-engine:v2.0

   # Restart feature engineering service
   docker restart chiseai-feature-engine
   ```

#### Option C: Model Architecture Adjustment (4+ hours)

1. **Review Model Architecture**
   ```bash
   # Analyze model performance by segment
   python3 scripts/ml/analyze_by_segment.py \
     --model signal_model_v1 \
     --segments bull,bear,ranging

   # Identify underperforming segments
   ```

2. **Adjust Architecture**
   - Consider ensemble changes
   - Add regime-specific models
   - Implement online learning
   - Add uncertainty quantification

3. **Full Retraining Cycle**
   ```bash
   # Run complete retraining pipeline
   python3 scripts/ml/full_retrain.py \
     --config configs/ml/retrain_config.yaml \
     --output /tmp/retrain_output/

   # Validate against historical periods
   python3 scripts/ml/backtest_models.py \
     --model_dir /tmp/retrain_output/ \
     --start_date 2025-06-01 \
     --end_date 2025-12-31
   ```

### Phase 4: Validation (30-60 minutes)

1. **Validate Model Performance**
   ```bash
   # Run validation suite
   python3 scripts/ml/validate_models.py \
     --model_dir /tmp/model_output/ \
     --validation_set validation.parquet

   # Check ECE meets threshold (< 0.10)
   cat validation_results.json | jq '.ece'
   ```

2. **Shadow Mode Validation**
   ```bash
   # Deploy to shadow mode
   ./scripts/ml/deploy_models.py \
     --model_dir /tmp/model_output/ \
     --mode shadow \
     --duration 24h

   # Monitor shadow performance
   python3 scripts/ml/monitor_shadow.py --duration 24h

   # Compare shadow vs. production
   python3 scripts/ml/compare_shadow_production.py
   ```

3. **Production Deployment**
   ```bash
   # Once shadow validation passes, promote to production
   ./scripts/ml/deploy_models.py \
     --model_dir /tmp/model_output/ \
     --mode production

   # Monitor closely for first 24 hours
   ./scripts/ml/monitor_deployment.py --duration 24h
   ```

4. **Update Monitoring**
   - Update ECE threshold alerts
   - Adjust feature drift detection sensitivity
   - Document changes in model registry

## Estimated Time to Resolve

| Scenario | Estimated Time |
|----------|---------------|
| Minor drift (rapid retrain) | 1-2 hours |
| Moderate drift (feature update) | 2-4 hours |
| Major drift (architecture change) | 4-8 hours |
| Market regime adaptation | 1-2 weeks |

## Prevention Measures

### Proactive Monitoring

1. **Continuous Drift Detection**
   - Real-time ECE monitoring with alerts at 0.08 (warning), 0.10 (critical)
   - Daily feature distribution comparison
   - Weekly model performance reviews
   - Automated drift score calculation

2. **Regular Retraining Cadence**
   - Weekly retraining of confidence models
   - Monthly retraining of signal models
   - Triggered retraining on drift detection
   - Rolling window training data

3. **Performance Baselines**
   - Establish baseline ECE (<0.08)
   - Track accuracy by confidence bucket
   - Monitor Sharpe ratio trends
   - Alert on sustained underperformance

### Preventive Maintenance

1. **Feature Engineering Health**
   - Feature monitoring dashboards
   - Data quality checks on inputs
   - Feature importance tracking
   - Automated feature validation

2. **Model Registry**
   - Version all models
   - Track performance history
   - Maintain rollback capability
   - Document model lineage

3. **Regime Detection**
   - Automatic regime classification
   - Regime-specific model weights
   - Regime transition alerts
   - Adaptive model selection

## Related Alerts and Dashboards

### Grafana Dashboards
- [Model Performance Dashboard](../infrastructure/grafana/dashboards/model-performance.json)
- [Signal Accuracy Dashboard](../infrastructure/grafana/dashboards/signal-accuracy.json)
- [Calibration Metrics Dashboard](../infrastructure/grafana/dashboards/calibration.json)

### Related Runbooks
- [Order Rejects](order-rejects.md) - May result from model issues
- [Data Gaps](data-gaps.md) - Can cause model input issues

### Alert Rules
- `Alert: ECEDegraded` - Triggered when ECE > 0.08
- `Alert: AccuracyDecline` - Triggered when accuracy drops > 10%
- `Alert: FeatureDriftDetected` - Triggered on distribution shift
- `Alert: RegimeChange` - Triggered on market regime transition

## Escalation Path

### Level 1: ML Engineer (0-4 hours)
- Monitors model performance
- Investigates drift alerts
- Executes retraining procedures
- Documents findings

### Level 2: ML Team Lead (4-8 hours)
- Escalated for significant drift
- Reviews retraining strategies
- Coordinates architecture changes
- Communicates with stakeholders

### Level 3: Principal Engineer (8+ hours)
- Escalated for persistent issues
- Makes architectural decisions
- Coordinates with research team
- Communicates with leadership

## Quick Reference Commands

```bash
# Quick ECE check
influx query 'from(bucket:"chiseai") |> range(start:-24h) |> filter(fn:(r) => r._measurement == "model_metrics") |> filter(fn:(r) => r._field == "ece") |> last()'

# Run drift detection
python3 scripts/ml/drift_detection.py --output drift_report.json

# Quick retrain
python3 scripts/ml/quick_retrain.py --days 30 --output /tmp/model/

# Deploy shadow
./scripts/ml/deploy_models.py --model_dir /tmp/model/ --mode shadow

# Monitor deployment
python3 scripts/ml/monitor_deployment.py --duration 1h

# Check feature health
./scripts/ml/validate_features.py --days 7

# View calibration
python3 scripts/ml/analyze_calibration.py --days 7

# Regime analysis
python3 scripts/ml/analyze_regime.py --days 30
```

## References

- [Model Performance Metrics](docs/ml/model-metrics.md)
- [Drift Detection Methods](docs/ml/drift-detection.md)
- [Retraining Procedures](docs/ml/retraining-procedures.md)
- [Confidence Calibration Guide](docs/ml/confidence-calibration.md)
- [ECE Threshold Guidelines](docs/ml/ece-guidelines.md)
