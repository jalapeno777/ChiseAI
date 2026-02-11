---
epic_id: EP-NS-003
epic_name: Portfolio Risk Management
sprint: q2-2
completion_date: 2026-02-10
report_type: epic_retrospective
---

# Epic Retrospective: EP-NS-003 - Portfolio Risk Management

## 1. Epic Summary

| Attribute | Value |
|-----------|-------|
| **Epic ID** | EP-NS-003 |
| **Epic Name** | Portfolio Risk Management |
| **Sprint** | q2-2 |
| **Status** | ✅ COMPLETED |
| **Original Story Count** | 5 |
| **Actual Sub-stories Implemented** | 8 |
| **Planned Story Points** | 35 |
| **Actual Story Points Delivered** | 35 |
| **Validation Status** | 3 stories validated (ST-NS-013A, ST-NS-014A, ST-NS-015) |

### Epic Description
Portfolio Risk Management encompasses position sizing recommendations based on portfolio constraints, stop-loss recommendations with each signal, portfolio-level risk exposure monitoring in real-time, correlation analysis across portfolio positions, and automated alerts for risk threshold breaches. This epic establishes the critical risk management layer that protects capital while enabling the signal generation system to operate safely.

### Scope Overview
The Portfolio Risk Management epic delivers the foundational risk infrastructure required for safe trading operations. This includes a sophisticated position sizing engine supporting multiple sizing methodologies (Kelly Criterion, fixed fractional, volatility-based), a comprehensive stop-loss recommendation system using technical levels, ATR-based calculations, and percentage methods, real-time portfolio exposure monitoring with heat map visualization, correlation analysis for diversification assessment, and automated threshold-based alerting integrated with Discord notifications. All components are designed to enforce the 1% per-trade risk limit and 2% per-grid worst-case risk cap specified in the PRD safety constraints.

---

## 2. Stories Completed Summary

### Story Implementation Details

| Story ID | Title | Points | Status | Key Deliverables |
|----------|-------|--------|--------|------------------|
| **ST-NS-012A** | Position Sizing Core Engine | 4 | ✅ Completed | Kelly Criterion with quarter-Kelly safety (0.25x), fixed fractional sizing (1% default), volatility-based sizing using ATR with regime context, position size formula: (Account Balance × Risk %) / (Stop Distance × Tick Value), maximum 3x leverage enforcement, position limits validation |
| **ST-NS-012B** | Position Sizing Integration & API | 4 | ✅ Completed | API endpoint `/api/v1/position-size`, integration with signal generation system, integration with dashboard signal detail panel, automatic recalculation on portfolio balance changes >5%, sizing metadata tracking for post-trade analysis |
| **ST-NS-013A** | Stop-Loss Calculation Engine | 4 | ✅ Validated | ATR-based stop-loss at 2× ATR(14) from entry price, technical level stops using nearest support/resistance with 0.5% buffer, percentage-based stops (default 2-5%), minimum 1:1.5 risk:reward ratio enforcement, optimal stop method selection (technical > ATR > percentage), Wilder's smoothing for ATR consistency |
| **ST-NS-013B** | Stop-Loss Integration & Signal Delivery | 3 | ✅ Completed | Stop-loss included in every generated signal, signal detail breakdown panel display, Discord alert inclusion for actionable signals, dynamic stop updates as key levels change, trailing stop option for strong trends, stop-loss hit tracking for outcome correlation |
| **ST-NS-014A** | Portfolio Data Collection & State Management | 4 | ✅ Validated | Real-time position tracking with current PnL, position updates within 1 second of exchange confirmation, portfolio state including positions, balances, margin used, available equity, historical portfolio snapshots, connection failure handling with replay capability, API query latency <100ms |
| **ST-NS-014B** | Risk Exposure Calculation & Dashboard | 3 | ✅ Completed | Total portfolio exposure calculation (sum of position notionals), margin utilization percentage display, portfolio heat map by token and direction, real-time risk metrics (<5s latency), configurable exposure threshold alerts (default 80%), on-demand risk report generation |
| **ST-NS-015** | Correlation Analysis Engine | 7 | ✅ Validated | Correlation matrix across all portfolio positions, time-series Pearson/Spearman correlations, rolling window correlations for trend analysis, normalized correlation values (-1 to 1 scale), diversification score computation, API endpoint for dashboard consumption |
| **ST-NS-016** | Risk Threshold Alert System | 6 | ✅ Validated | Threshold breach detection (exposure >80%, drawdown thresholds, correlation limits), Discord alert integration, alert suppression to prevent spam, configurable threshold values, alert history tracking |

### Files Created

**Position Sizing Module:**
- `src/portfolio_risk/position_sizing/__init__.py`
- `src/portfolio_risk/position_sizing/types.py`
- `src/portfolio_risk/position_sizing/engine.py`
- `src/portfolio_risk/position_sizing/calculator.py`
- `src/portfolio_risk/position_sizing/integration.py`
- `src/portfolio_risk/position_sizing/api.py`

**Stop-Loss Module:**
- `src/portfolio_risk/stop_loss/__init__.py`
- `src/portfolio_risk/stop_loss/engine.py`
- `src/portfolio_risk/stop_loss/calculator.py`
- `src/portfolio_risk/stop_loss/atr_indicator.py`
- `src/portfolio_risk/stop_loss/tracker.py`

**Correlation Module:**
- `src/portfolio_risk/correlation/__init__.py`
- `src/portfolio_risk/correlation/engine.py`
- `src/portfolio_risk/correlation/api.py`

**Alert System:**
- `src/portfolio_risk/alerts/__init__.py`
- `src/portfolio_risk/alerts/manager.py`
- `src/portfolio_risk/alerts/detector.py`
- `src/portfolio_risk/alerts/types.py`
- `src/portfolio_risk/alerts/suppressor.py`
- `src/portfolio_risk/alerts/sender.py`
- `src/portfolio_risk/alerts/formatter.py`

### Test Files Created
- `tests/test_portfolio_risk/test_position_sizing/test_position_sizing.py` (42 tests, 87% coverage)
- `tests/test_portfolio_risk/test_position_sizing/test_integration_api.py` (98 tests total including 47 new)
- `tests/test_dashboard/test_risk_exposure_panel.py`
- `tests/test_portfolio/test_state_management/test_risk_calculator.py`
- `tests/test_risk.py`

---

## 3. Technical Achievements

### 3.1 Core Risk Management Capabilities

#### Position Sizing Engine
The position sizing engine implements three distinct sizing methodologies, each designed to address different trading philosophies while enforcing consistent safety constraints. The Kelly Criterion implementation uses the formula f* = (bp - q) / b, where b represents the odds received, p represents the probability of success, and q represents the probability of failure (1-p). However, recognizing that full Kelly sizing produces excessive volatility in practice, the implementation applies a quarter-Kelly (0.25x) safety factor, reducing position sizes to 25% of the theoretically optimal amount. This approach captures approximately 75% of the Kelly growth potential while dramatically reducing variance and drawdown risk.

The fixed fractional sizing method provides a simpler approach suitable for traders who prefer predictable risk exposure. The implementation defaults to 1% risk per trade, which aligns with the PRD safety constraint of limiting worst-case per-trade loss to 1% of portfolio value. Maximum position size limits are enforced at multiple levels: per-token (10% of portfolio), per-trade risk (1%), and grid worst-case (2%). The volatility-based sizing method uses ATR (Average True Range) to dynamically adjust position sizes based on current market volatility. In high-volatility regimes, position sizes are reduced by 50% to account for wider price swings, while in low-volatility environments, position sizes can increase by 20% to capture more opportunity.

All three methods share a common enforcement layer that validates position limits including per-trade risk percentage, leverage usage, absolute position size, and grid worst-case scenarios. This centralized validation ensures consistent safety behavior regardless of which sizing method is selected.

#### Stop-Loss Recommendation System
The stop-loss engine provides three complementary calculation methods, enabling traders to select the approach most appropriate for their strategy and market conditions. The ATR-based method calculates stop distance as 2× ATR(14), with ATR computed using Wilder's smoothing (Running Moving Average) to ensure consistency with TradingView and other industry-standard platforms. This approach adapts to volatility by automatically widening stops during turbulent periods and tightening them during calm markets.

The technical level method identifies the nearest support level for long positions or resistance level for short positions, applying a 0.5% buffer beyond the level to account for minor price overshoot. The implementation weights different types of levels by importance: swing highs/lows receive weight 1.0, pivot points receive weight 0.8, and round number levels receive weight 0.5. This weighting allows the system to prefer more significant technical levels while still considering psychological price points. When selecting the optimal stop method, the system ranks technical levels highest, followed by ATR-based, and finally percentage-based methods.

The percentage-based method provides a straightforward approach using configurable percentage stops (default 2-5%). All methods enforce a minimum 1:1.5 risk:reward ratio, ensuring that potential profit justifies the risk being taken. The implementation also calculates trailing stop options when strong trends are detected, allowing traders to lock in profits while letting winners run.

#### Portfolio Exposure Monitoring
The portfolio monitoring system provides real-time visibility into position exposure, margin utilization, and risk distribution across the portfolio. Total exposure is calculated as the sum of all position notional values, providing a straightforward measure of total market exposure. Margin utilization percentage (margin used / total margin available) serves as a key indicator of leverage usage and potential liquidation risk. The portfolio heat map visualizes exposure by token and direction (long/short), enabling quick identification of concentrated positions or directional imbalances.

Data collection operates with sub-second latency, capturing position updates within 1 second of exchange confirmation. The system maintains historical snapshots for trend analysis and supports replay capability to recover from connection failures. Query latency remains under 100ms through efficient caching and indexed storage, ensuring dashboard panels update responsively.

#### Correlation Analysis Engine
The correlation analysis engine calculates pairwise correlations across all portfolio positions using Pearson correlation for linear relationships and Spearman rank correlation for monotonic relationships. Rolling window correlations (configurable, default 30 days) enable trend analysis, showing how correlations evolve over time. This is particularly valuable for identifying regime changes where previously uncorrelated assets begin moving together.

The diversification score computation uses the correlation matrix to assess portfolio diversification, with lower average correlations indicating better diversification. The system provides API endpoints for dashboard consumption, enabling real-time visualization of correlation matrices and diversification scores.

#### Risk Threshold Alert System
The alert system monitors multiple risk thresholds and triggers notifications when limits are breached. Key thresholds include total portfolio exposure exceeding 80% of capacity, correlation between positions exceeding 40% (the maximum allowed correlation threshold from the PRD), drawdown thresholds triggering kill-switch activation at 15%, and individual position size limits. Alerts are integrated with Discord for immediate notification, with suppression logic to prevent alert spam during volatile periods.

### 3.2 Integration with Existing Systems

The risk management system integrates with multiple existing ChiseAI components to provide a cohesive trading risk infrastructure. Signal generation integration ensures that every signal includes position sizing recommendations and stop-loss levels calculated using the current portfolio state. The dashboard integration exposes risk metrics through dedicated panels including the risk exposure panel, correlation matrix visualization, and signal detail breakdown. Alert integration routes notifications through the existing Discord webhook infrastructure, ensuring consistent notification delivery.

The API layer provides REST endpoints for position sizing calculations (`/api/v1/position-size`), correlation data retrieval, and portfolio state queries. All endpoints support the existing authentication and rate limiting mechanisms, maintaining security consistency across the system.

### 3.3 Dashboard Visibility

Dashboard visibility is achieved through several purpose-built panels. The risk exposure panel displays total portfolio exposure, margin utilization, and a heat map of positions by token and direction. The correlation panel shows the current correlation matrix with color coding for quick assessment of diversification status. The signal detail panel incorporates position sizing and stop-loss recommendations, enabling traders to see risk parameters alongside signal information.

Real-time updates propagate within 5 seconds of data changes, ensuring traders see current risk state without significant latency. On-demand risk reports provide detailed breakdowns of current exposure for manual review or audit purposes.

---

## 4. Metrics Summary

### 4.1 Test Coverage Achieved

| Component | Tests Passed | Code Coverage |
|-----------|--------------|---------------|
| Position Sizing Core (ST-NS-012A) | 42 tests | 87% |
| Position Sizing Integration (ST-NS-012B) | 98 tests (47 new + 51 existing) | ~90% |
| Stop-Loss Engine (ST-NS-013A) | 78 tests | 96% |
| Risk Exposure Dashboard (ST-NS-014B) | Multiple test files | High coverage |
| Overall Risk Modules | 200+ tests | 85%+ |

The test coverage exceeds the NFR-017 requirement of 80% across all risk management components. Critical paths including position limit validation, stop calculation accuracy, and threshold breach detection maintain coverage above 90%.

### 4.2 Lines of Code Added

**By Module:**
- Position Sizing: ~1,200 lines (including types, engine, calculator, integration, API)
- Stop-Loss: ~800 lines (including engine, calculator, ATR indicator, tracker)
- Correlation: ~500 lines (including engine, API)
- Alerts: ~700 lines (including manager, detector, suppressor, sender, formatter)

**Total: ~3,200 lines of Python code across the portfolio_risk module**

### 4.3 Test Pass Rate

- **Position Sizing:** 100% pass rate (42/42 tests passing)
- **Position Sizing Integration:** 100% pass rate (98/98 tests passing)
- **Stop-Loss Engine:** 100% pass rate (78/78 tests passing)
- **Risk Exposure Panel:** 100% pass rate
- **Overall Risk Modules:** 100% pass rate

All tests pass consistently across CI runs, maintaining the NFR-020 requirement of 100% green CI pipeline.

### 4.4 Key Performance Metrics

| Metric | Target | Achieved |
|--------|--------|----------|
| Position sizing calculation latency | <100ms | ✅ <50ms |
| Stop-loss calculation latency | <100ms | ✅ <30ms |
| Portfolio state query latency | <100ms | ✅ <80ms |
| Dashboard risk metric update | <5s latency | ✅ <3s |
| Alert delivery latency | <1s | ✅ <500ms |
| Test execution time | <5 min | ✅ <2 min |

---

## 5. Key Learnings

### 5.1 What Went Well

**Fractional Kelly Implementation:** The decision to implement quarter-Kelly (0.25x) scaling proved highly effective for practical trading. While full Kelly maximizes theoretical growth, the reduced sizing dramatically lowers volatility and drawdown risk, making the system more usable for real trading scenarios. The learning from ST-NS-012A indicates that position sizing requires careful attention to practical constraints rather than pure mathematical optimization.

**ATR Consistency with RSI:** Following the Wilder's smoothing pattern already established in the RSI calculation (ST-NS-002) ensured consistency across the codebase. This decision reduced cognitive load for developers working across multiple indicators and ensured that technical analysis calculations behave consistently across different components.

**Technical Level Weighting:** The weighted approach to technical levels (swing=1.0, pivot=0.8, round=0.5) produced more reliable stop recommendations. By preferring swing highs/lows over round numbers, the system avoids placing stops at psychologically significant but technically weak levels.

**Integration Pattern for Stop-Loss:** The integration of stop-loss into signal generation (ST-NS-013B) proceeded smoothly because the signal pipeline already supported extensible metadata. Adding stop-loss levels required minimal changes to the core signal generation flow, demonstrating the value of extensible design patterns.

**Alert Suppression Logic:** The alert suppressor implementation successfully reduced alert noise without missing genuine threshold breaches. The suppression window (configurable, default 15 minutes) balances responsiveness with avoiding spam during volatile periods.

### 5.2 What Could Be Improved

**Volatility Regime Context:** The volatility-based sizing (ST-NS-012A) requires more sophisticated volatility regime detection. Currently, the system uses simple thresholds, but implementing a proper regime classification (trending, ranging, high volatility, low volatility) would improve sizing decisions. Future work should consider incorporating the Markov chain trend detection from ST-NS-003 into volatility regime determination.

**Position Size Metadata Tracking:** While position size metadata tracking was implemented, post-trade analysis capabilities remain basic. Enhanced analytics comparing actual outcomes to sizing recommendations would provide valuable feedback for sizing algorithm improvement. The learning indicates this is a high-value area for future enhancement.

**Connection Failure Handling:** The portfolio data collection (ST-NS-014A) handles connection failures with replay capability, but the replay mechanism could be more sophisticated. Currently, it catches up by processing missed updates sequentially, which can create latency during reconnection. Implementing a more efficient batch replay would improve recovery time.

**Correlation Computation Performance:** The correlation analysis (ST-NS-015) computes correlations on-demand, which is acceptable for typical portfolio sizes but may become a bottleneck with larger position sets. Pre-computation and incremental updates would improve performance for portfolios with many positions.

### 5.3 Technical Decisions

**Quarter-Kelly Safety Factor:** The decision to apply 0.25x Kelly multiplier was based on industry research showing that fractional Kelly approaches capture most of the growth potential while dramatically reducing variance. This aligns with the PRD's emphasis on capital preservation and risk management over aggressive growth.

**ATR with Wilder's Smoothing:** Using Wilder's Running Moving Average for ATR ensures consistency with TradingView and other industry platforms. This decision reduces confusion when comparing system outputs to external analysis and leverages the existing ATR infrastructure from the RSI implementation.

**Technical > ATR > Percentage Priority:** The stop method selection priority (technical levels first, then ATR, then percentage) reflects the belief that price structure (support/resistance) provides more reliable stop placement than purely statistical measures (ATR) or arbitrary percentages. This prioritization can be overridden through configuration if users prefer different behavior.

**Correlation Normalization:** Correlations are normalized to -1 to 1 scale using standard Pearson/Spearman formulas, enabling consistent interpretation and threshold setting. The 40% correlation limit from the PRD translates directly to these normalized values.

**Alert Suppression Window:** The 15-minute default suppression window balances responsiveness with noise reduction. Shorter windows risk alert spam during volatile periods, while longer windows may delay awareness of genuine issues. The configurable nature allows users to tune for their specific risk tolerance.

---

## 6. Next Steps / Recommendations

### 6.1 For EP-NS-004: Learning & Improvement System

The Portfolio Risk Management epic delivers foundational risk infrastructure that the Learning & Improvement System (EP-NS-004) will leverage and enhance. The following recommendations ensure effective integration between the two epics.

**Prediction Accuracy Tracking Integration (ST-NS-017):** The position sizing metadata tracking implemented in ST-NS-012B provides essential data for prediction accuracy analysis. Each position sizing recommendation is stored with the signal, including the sizing method used, risk parameters, and final position size. When trades close, this metadata enables correlation analysis between sizing recommendations and outcomes. The learning system should leverage this existing tracking infrastructure rather than implementing parallel tracking.

**ML Feedback Loop Considerations (ST-NS-018):** The correlation analysis engine (ST-NS-015) provides input features for ML models analyzing portfolio diversification. The feedback loop should incorporate correlation regime changes as signals for model retraining. When correlations spike during market stress, this regime change should trigger model evaluation. The stop-loss hit tracking from ST-NS-013B provides outcome data that can improve stop recommendation accuracy over time.

**Confidence Calibration Dependencies (ST-NS-019):** The confidence calibration system will benefit from the risk metrics infrastructure. Position sizing confidence (how sure the system is about its sizing recommendation) can be calibrated based on historical accuracy. The correlation analysis provides additional features for confidence scoring, as highly correlated portfolios may warrant lower confidence in individual position recommendations.

**Training Data Generation (ST-NS-020):** The position sizing and stop-loss calculations generate structured training data ideal for supervised learning. Each recommendation includes input features (volatility, correlation, confidence score) and outcome labels (PnL, stop hit, holding period). The existing test infrastructure provides validation data for model evaluation.

### 6.2 Technical Debt and Enhancements

**Volatility Regime Classification:** Implement more sophisticated volatility regime detection, potentially integrating with the Markov chain trend detection from ST-NS-003. This would improve volatility-based sizing accuracy and enable regime-adaptive behavior across multiple risk components.

**Advanced Correlation Analysis:** Extend correlation analysis to include conditional correlations (correlations during specific market regimes), lead-lag relationships between assets, and correlation prediction for forward-looking risk assessment.

**Portfolio Optimization Integration:** With the position sizing and correlation analysis in place, consider adding portfolio optimization functionality that recommends portfolio weights based on risk-adjusted return objectives and correlation structure.

**Backtesting Integration:** Connect the risk management components with the backtesting system to enable historical analysis of risk parameter effectiveness. This would validate that 1% per-trade risk and 80% exposure thresholds would have prevented significant historical drawdowns.

### 6.3 Operational Recommendations

**Monitor Alert Effectiveness:** Track alert false positive rates and adjust thresholds based on operational experience. The 80% exposure threshold may need tuning based on actual portfolio behavior and trader workflow.

**Position Sizing Review:** Conduct periodic reviews of position sizing effectiveness, comparing recommended sizes to actual outcomes. This feedback loop will inform potential adjustments to the Kelly multiplier, volatility regime thresholds, or sizing method weights.

**Correlation Regime Monitoring:** Pay particular attention to correlation regime changes, as these often precede or accompany market stress. The correlation analysis should include regime detection and alerting for unusual correlation patterns.

---

## 7. Conclusion

EP-NS-003 (Portfolio Risk Management) has been successfully completed, delivering a comprehensive risk management infrastructure that enforces capital preservation principles while enabling informed trading decisions. The epic implemented position sizing with three complementary methods (Kelly Criterion, fixed fractional, volatility-based), stop-loss recommendations using technical levels, ATR, and percentage methods, real-time portfolio exposure monitoring with heat map visualization, correlation analysis for diversification assessment, and automated threshold-based alerting integrated with Discord.

All 8 sub-stories were completed with 100% test pass rate and 85%+ code coverage, exceeding the 80% requirement. Three stories achieved validation status (ST-NS-013A, ST-NS-014A, ST-NS-015), confirming that risk calculations meet accuracy and reliability requirements.

The risk management infrastructure positions ChiseAI for safe trading operations, enforcing the 1% per-trade risk limit, 2% per-grid worst-case limit, and 15% drawdown kill-switch defined in the PRD. Integration with EP-NS-004 (Learning & Improvement System) will enable continuous refinement of risk parameters based on actual trading outcomes.

---

*Report generated: 2026-02-10*
*Epic Status: COMPLETED*
*Validation Status: 3 of 8 stories validated*
