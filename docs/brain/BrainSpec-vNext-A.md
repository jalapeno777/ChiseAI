# BrainSpec vNext-A: False Positive Reduction Focus

## Version
- **ID**: vNext-A
- **Parent**: vCurrent (1.0.0-current)
- **Target**: false_positive_rate < 0.30
- **Status**: DESIGN
- **Story ID**: BRAIN-CICD-2026-03-01
- **Created**: 2026-03-01

## Problem Statement

Current baseline metrics show a critical bottleneck:
- **false_positive_rate = 0.50** (50% of backtest winners fail in paper trading)
- **paper_carryover_rate = 0.0** (placeholder - no successful paper carryover tracked)

This represents a fundamental trust issue: backtest results do not correlate with paper trading outcomes. When half of our "winning" strategies from backtests fail in paper trading, we waste compute resources and erode confidence in the brain's decision-making.

### Impact Analysis
- **Compute Waste**: 50% of promoted strategies fail the next gate
- **Iteration Speed**: False positives slow down true improvement cycles
- **Trust Erosion**: High false positive rate undermines confidence in backtest results
- **Safety Risk**: Strategies that shouldn't advance may slip through if paper validation is bypassed

## Changes from vCurrent

### 1. Role Modifications

#### 1.1 Critic Agent Enhancement

**New Role: FalsePositiveSentinel**

The Critic agent gains explicit responsibility for false positive detection:

```markdown
## FalsePositiveSentinel Responsibilities

1. **Backtest-to-Paper Correlation Review**
   - Review all strategy promotions for backtest-to-paper correlation evidence
   - Challenge promotions where correlation data is missing or weak
   - Flag strategies with >40% confidence but historical paper failures

2. **Confidence Calibration Audit**
   - Verify confidence scores are calibrated against actual paper outcomes
   - Identify systematic overconfidence in specific strategy types
   - Require confidence threshold adjustments based on historical data

3. **Root Cause Analysis Trigger**
   - When false_positive_rate > 0.35, trigger mandatory root cause analysis
   - Document patterns in false positive strategies
   - Recommend BrainSpec adjustments based on findings
```

**Tool Usage Requirements:**
- MUST use `chiseai-risk-audit` skill on all strategy promotions
- MUST query Redis for historical `false_positive_rate` trends before approving promotions
- MUST check `brain:evaluation:*` keys for correlation data

#### 1.2 Dev Agent Enhancement

**New Responsibility: BacktestValidation**

The Dev agent gains explicit backtest validation duties:

```markdown
## BacktestValidation Responsibilities

1. **Correlation Documentation**
   - Document backtest-to-paper correlation evidence in PR descriptions
   - Include historical correlation data for similar strategy types
   - Note any deviations from expected correlation patterns

2. **Confidence Justification**
   - Justify confidence scores with specific evidence
   - Reference similar strategies that succeeded in paper trading
   - Flag strategies with high confidence but limited historical support

3. **Pre-Submission Self-Review**
   - Run `chiseai-risk-audit` before requesting promotion
   - Verify no risk cap violations or promotion gate bypasses
   - Confirm all required correlation data is present
```

**PR Description Template (Required):**
```markdown
## Backtest-to-Paper Correlation
- Strategy Type: [type]
- Historical Correlation for Type: [X%]
- Confidence Score: [Y%]
- Justification: [evidence]
- Risk Audit Result: [PASS/WARN/FAIL]
```

#### 1.3 Jarvis Agent Enhancement

**New Oversight: Paper-Trading Correlation Monitor**

Jarvis gains explicit oversight for paper-trading correlation:

```markdown
## Paper-Trading Correlation Oversight

1. **Pre-Promotion Gate Check**
   - Query Redis `bmad:chiseai:metrics:false_positive_rate` before approving promotions
   - If false_positive_rate > 0.35 for 3+ consecutive evaluations, HALT promotions
   - Require Critic review and root cause analysis before proceeding

2. **Batch Planning Constraints**
   - Include false_positive_rate trend check in batch planning
   - Adjust batch sizes based on correlation confidence
   - Prioritize false positive reduction work when rate > 0.40

3. **Escalation Rules**
   - Escalate to `merlin` if false_positive_rate > 0.45
   - Trigger BrainSpec revision process if rate > 0.50 (current baseline)
   - Document all escalation decisions in iterlog
```

### 2. Policy Additions

#### Policy 1: Mandatory Paper-Trading Correlation Check

```markdown
**Policy ID**: POLICY-BACKTEST-CORRELATION-001
**Applies To**: All strategy promotions
**Enforced By**: Critic, Jarvis

All backtest winners MUST have paper-trading correlation check before promotion:

1. Query historical correlation for strategy type
2. If correlation < 0.60, require additional evidence:
   - Minimum 3 similar strategies with paper success
   - Detailed market condition analysis
   - Risk audit with correlation focus
3. Document correlation check in promotion packet
4. If correlation data unavailable, default to conservative: require paper canary

**Violation**: Promotion without correlation check → Critic MUST reject
```

#### Policy 2: Confidence Threshold Calibration

```markdown
**Policy ID**: POLICY-CONFIDENCE-CALIBRATION-001
**Applies To**: All confidence scores > 0.40
**Enforced By**: Dev, Critic

Confidence thresholds MUST be calibrated against paper outcomes:

1. Track actual vs predicted outcomes per confidence bucket:
   - 90-100% confidence: expected >90% paper success
   - 70-89% confidence: expected >75% paper success
   - 40-69% confidence: expected >50% paper success
2. If calibration is off by >15%, adjust thresholds
3. Document calibration data in `brain:evaluation:calibration`
4. Reject strategies with miscalibrated confidence scores

**Violation**: Overconfident scores without calibration → Require recalibration
```

#### Policy 3: High-Confidence Failure Root Cause Analysis

```markdown
**Policy ID**: POLICY-RCA-HIGH-CONFIDENCE-FAILURE-001
**Applies To**: Strategies with >40% confidence that fail paper
**Enforced By**: Critic, Jarvis

Signals with >40% confidence but paper failure REQUIRE root cause analysis:

1. Critic MUST trigger RCA within 24 hours of failure detection
2. RCA must include:
   - Strategy configuration analysis
   - Market condition comparison (backtest vs paper)
   - Execution difference identification
   - Pattern matching with other failures
3. Document findings in `brain:evaluation:rca:*`
4. Update strategy type correlation data
5. If pattern emerges, propose BrainSpec adjustment

**Escalation**: >3 similar RCAs in 7 days → Escalate to merlin for BrainSpec review
```

### 3. Tool Usage Updates

#### 3.1 Required Tool Patterns

**Critic Agent - Mandatory Tools:**
```python
# Before any promotion approval:
skill(name="chiseai-risk-audit")
redis_state_hget(name="bmad:chiseai:metrics", key="false_positive_rate")
redis_state_hget(name="bmad:chiseai:metrics", key="paper_carryover_rate")
qdrant_qdrant-find(query="false positive pattern strategy type")
```

**Dev Agent - Mandatory Tools:**
```python
# Before PR submission:
skill(name="chiseai-risk-audit")
# Document correlation in PR description
# Include risk audit output
```

**Jarvis Agent - Mandatory Tools:**
```python
# Before batch promotion approval:
redis_state_hget(name="bmad:chiseai:metrics", key="false_positive_rate")
redis_state_hget(name="bmad:chiseai:metrics", key="false_positive_trend")
# If rate > 0.35 for 3+ evaluations, halt and escalate
```

#### 3.2 New Tool Integration Points

**Redis Keys for False Positive Tracking:**
```
bmad:chiseai:metrics:false_positive_rate -> current rate (float)
bmad:chiseai:metrics:false_positive_trend -> trend direction (up/down/stable)
bmad:chiseai:metrics:false_positive_history -> list of historical rates
brain:evaluation:calibration -> confidence calibration data
brain:evaluation:rca:* -> root cause analysis records
brain:correlation:strategy_type:* -> per-type correlation data
```

### 4. Evaluation Gates

#### 4.1 New Promotion Gate: False Positive Rate

```markdown
**Gate ID**: GATE-FALSE-POSITIVE-001
**Type**: Hard Gate (blocking)
**Target**: false_positive_rate < 0.30

Promotion is BLOCKED unless:
- Current false_positive_rate < 0.30, OR
- Strategy has explicit exception with Critic approval, OR
- Emergency override with Jarvis + human approval

**Measurement**: 
- Computed from confusion matrix in brain evaluation
- Updated after each paper trading cycle
- Stored in Redis `bmad:chiseai:metrics:false_positive_rate`
```

#### 4.2 New Metric: Backtest-to-Paper Correlation per Strategy Type

```markdown
**Metric ID**: METRIC-CORRELATION-BY-TYPE
**Type**: Tracking Metric
**Target**: > 0.60 correlation for all strategy types

Track correlation coefficient per strategy type:
- Grid strategies
- Trend-following strategies
- Mean-reversion strategies
- Breakout strategies

**Storage**: 
- Redis hash `brain:correlation:strategy_type:{type}`
- Fields: correlation_coefficient, sample_size, last_updated

**Alert Threshold**: correlation < 0.50 triggers warning
```

#### 4.3 New Alert: False Positive Rate Trend

```markdown
**Alert ID**: ALERT-FP-TREND-001
**Type**: Warning Alert
**Trigger**: false_positive_rate > 0.35 for 3 consecutive evaluations

**Response Actions:**
1. Halt non-critical promotions
2. Trigger Critic review of recent promotions
3. Initiate root cause analysis
4. Notify Jarvis for batch replanning
5. If rate > 0.45, escalate to merlin

**Reset Condition**: 2 consecutive evaluations with rate < 0.35
```

## Expected Impact

### Primary KPI Improvements

| Metric | Current | Target | Expected Timeline |
|--------|---------|--------|-------------------|
| false_positive_rate | 0.50 | < 0.30 | 4-6 weeks |
| paper_carryover_rate | 0.0 | > 0.60 | 4-6 weeks (indirect) |
| safety_compliance | 1.0 | 1.0 | Maintain |

### Secondary Benefits

1. **Compute Efficiency**: 40% reduction in wasted paper trading cycles
2. **Iteration Speed**: Faster true improvement cycles
3. **Trust Restoration**: Confidence in backtest results
4. **Risk Reduction**: Fewer false promotions reduce live trading risk

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Over-correction (too conservative) | Monitor paper_carryover_rate; if it drops, adjust thresholds |
| Increased evaluation time | Parallelize correlation checks; cache historical data |
| False negative increase | Track false_negative_rate; if > 0.20, investigate |
| Agent resistance to new policies | Training period with warnings before enforcement |

## Rollback Plan

If vNext-A underperforms or causes issues:

### Rollback Triggers
- false_positive_rate increases to > 0.55
- paper_carryover_rate drops below 0.40
- Safety compliance drops below 1.0
- 3+ incidents related to new policies in 1 week

### Rollback Steps
1. **Immediate** (T+0): Revert to vCurrent BrainSpec
   - Restore original agent instructions
   - Disable new policy gates
   - Preserve all evaluation data

2. **Analysis** (T+24h): Document learnings
   - What worked: [capture successes]
   - What failed: [capture failures]
   - Root cause: [why it didn't work]

3. **Iteration** (T+1 week): Design vNext-B
   - Incorporate learnings from vNext-A
   - Adjust approach based on data
   - Propose smaller, incremental changes

### Rollback Command
```bash
# Revert agent instructions
git checkout main -- .opencode/agent/Critic.md
git checkout main -- .opencode/agent/Dev.md
git checkout main -- .opencode/agent/Jarvis.md

# Archive vNext-A spec
git mv docs/brain/BrainSpec-vNext-A.md docs/brain/archive/
```

## Implementation Plan

### Phase 1: Documentation (Week 1)
- [ ] Update Critic.md with FalsePositiveSentinel role
- [ ] Update Dev.md with BacktestValidation responsibility
- [ ] Update Jarvis.md with Paper-Trading Correlation oversight
- [ ] Create policy reference cards

### Phase 2: Tool Integration (Week 2)
- [ ] Add Redis key patterns for correlation tracking
- [ ] Integrate `chiseai-risk-audit` into promotion workflow
- [ ] Build false positive rate dashboard queries

### Phase 3: Policy Enforcement (Week 3-4)
- [ ] Enable warning mode (log violations, don't block)
- [ ] Collect feedback and adjust
- [ ] Switch to enforcement mode

### Phase 4: Evaluation (Week 5-6)
- [ ] Measure false_positive_rate improvement
-- [ ] Evaluate paper_carryover_rate changes
- [ ] Assess safety_compliance maintenance
- [ ] Decide: continue, adjust, or rollback

## Success Criteria

vNext-A is successful if:
- [ ] false_positive_rate < 0.30 (measured over 2+ weeks)
- [ ] paper_carryover_rate > 0.50 (indirect improvement)
- [ ] safety_compliance remains 1.0
- [ ] No increase in false_negative_rate (don't miss good strategies)
- [ ] Agent workflow satisfaction (no major complaints)

## References

- Parent BrainSpec: vCurrent (1.0.0-current)
- Baseline Metrics: BRAIN-CICD-2026-03-01 Batch 1
- Related Skills: `chiseai-risk-audit`, `chiseai-brain-cicd`
- Related Commands: `chise-brain-evaluate`, `chise-brain-promote`

## Appendix A: Metric Computation

### false_positive_rate
```python
# From confusion matrix in brain evaluation
false_positive_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

# Where:
# fp = backtest winner that failed in paper
# tn = backtest loser that was correctly rejected
```

### paper_carryover_rate
```python
# Rate of paper trading successes
carryover_successes = len([s for s in paper_results if s.success])
backtest_winners = len([s for s in backtest_results if s.winner])
paper_carryover_rate = carryover_successes / backtest_winners if backtest_winners > 0 else 0.0
```

## Appendix B: Agent Instruction Diff Summary

### Critic.md Changes
```diff
+ ## FalsePositiveSentinel Role
+ 
+ Additional responsibilities for false positive detection...
+
+ ### Required Tools
+ - skill(name="chiseai-risk-audit")
+ - redis_state_hget(name="bmad:chiseai:metrics", key="false_positive_rate")
```

### Dev.md Changes
```diff
+ ## BacktestValidation Responsibility
+ 
+ Document correlation in PR descriptions...
+
+ ### PR Template Required
+ ## Backtest-to-Paper Correlation
+ - Strategy Type: [type]
+ - Historical Correlation: [X%]
```

### Jarvis.md Changes
```diff
+ ## Paper-Trading Correlation Oversight
+ 
+ Pre-promotion gate checks...
+
+ ### Escalation Rules
+ - false_positive_rate > 0.45 → Escalate to merlin
```

---

**Document Status**: DESIGN  
**Next Review**: After 2 weeks of implementation  
**Owner**: BRAIN-CICD-2026-03-01  
**Approved By**: [Pending Jarvis Review]
